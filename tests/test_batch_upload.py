"""
tests/test_batch_upload.py
Tests for asynchronous multi-file CV batch ingestion, tracking, and evaluation.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

import backend.api.routes as routes
from backend.main import app
from backend.schemas.cv import ContactInfo, ParsedCV, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    Recommendation,
    RequirementMatch,
    VerbatimCitation,
)
from backend.services.batch_processor import BatchProcessorService


@pytest.fixture
def client():
    return TestClient(app)


def test_batch_upload_validation(client):
    """Verify batch upload rejects empty file list."""
    res = client.post("/api/v1/cv/batch-upload", files=[])
    # Empty files list in multipart payload triggers 422 or 400
    assert res.status_code in [400, 422]


@pytest.mark.asyncio
async def test_batch_processor_service_single_candidate(monkeypatch):
    """Verify BatchProcessorService processes a candidate and records match evaluation."""
    processor = BatchProcessorService()

    mock_parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Bruce Wayne", email="bruce@wayne-enterprises.com"),
        skills=["Python", "FastAPI", "Kubernetes"],
        experiences=[
            WorkExperience(
                job_title="Lead AI Architect",
                company_name="Wayne Enterprises",
                work_description=["Built high-throughput RAG search with FastAPI and ChromaDB."],
                skills_used=["Python", "FastAPI"]
            )
        ]
    )

    monkeypatch.setattr(
        processor.parser_agent,
        "parse_and_anonymize",
        lambda source, filename=None: (
            mock_parsed,
            processor.parser_agent.pii_scrubber.anonymize_cv(mock_parsed)
        )
    )
    monkeypatch.setattr(
        processor.vector_store,
        "index_candidate",
        lambda candidate, force=False: 4
    )

    jid = uuid4()
    job = JobDescription(
        id=jid,
        title="AI Engineer",
        requirements=[
            JobRequirement(
                id="req_fastapi",
                title="FastAPI",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="FastAPI REST microservices",
            )
        ]
    )

    mock_eval = MatchEvaluationResult(
        id=uuid4(),
        candidate_id=uuid4(),
        job_id=jid,
        overall_score=92.0,
        must_have_score=95.0,
        nice_to_have_score=85.0,
        must_have_gaps_count=0,
        recommendation=Recommendation.STRONG_MATCH,
        citation_verification_score=1.0,
        requirement_matches=[
            RequirementMatch(
                requirement_id="req_fastapi",
                status=MatchStatus.MET,
                score=0.95,
                confidence=0.95,
                reasoning="Demonstrated FastAPI RAG search experience.",
                citations=[
                    VerbatimCitation(
                        quote="Built high-throughput RAG search with FastAPI and ChromaDB.",
                        source_section="Wayne Enterprises",
                        verified=True,
                    )
                ]
            )
        ]
    )

    monkeypatch.setattr(
        processor.matching_agent,
        "match_candidate",
        lambda candidate, job_description: mock_eval
    )

    res = await processor.process_single_candidate(
        content_bytes=b"Bruce Wayne resume text",
        filename="bruce_cv.pdf",
        job_description=job,
    )

    assert res["status"] == "COMPLETED"
    assert res["filename"] == "bruce_cv.pdf"
    assert res["overall_score"] == 92.0
    assert res["recommendation"] == "strong_match"
    assert "candidate_id" in res
    assert "evaluation_id" in res


def test_batch_upload_api_flow(client, monkeypatch):
    """Verify POST /api/v1/cv/batch-upload enqueues job and GET /batch/{id} retrieves status."""
    # Mock parse and vector indexing to isolate from external model downloads in test
    mock_parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Clark Kent", email="clark@dailyplanet.com"),
        skills=["Python"],
    )
    monkeypatch.setattr(
        routes._parser_agent,
        "parse_and_anonymize",
        lambda source, filename=None: (
            mock_parsed,
            routes._parser_agent.pii_scrubber.anonymize_cv(mock_parsed)
        )
    )
    monkeypatch.setattr(
        routes._vector_store,
        "index_candidate",
        lambda candidate, force=False: 2
    )

    files = [
        ("files", ("clark_cv_1.txt", b"Clark Kent Resume 1 content", "text/plain")),
        ("files", ("clark_cv_2.txt", b"Clark Kent Resume 2 content", "text/plain")),
    ]

    res = client.post("/api/v1/cv/batch-upload", files=files)
    assert res.status_code == 202
    data = res.json()
    assert "batch_id" in data
    assert data["total_files"] == 2
    assert data["status"] == "PROCESSING"

    bid = data["batch_id"]

    # Poll status endpoint
    res_status = client.get(f"/api/v1/cv/batch/{bid}")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["batch_id"] == bid
    assert status_data["total_files"] == 2
    assert "progress_percentage" in status_data
