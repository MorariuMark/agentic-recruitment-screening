"""
tests/test_api.py
Integration tests for FastAPI REST endpoints using TestClient.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

import backend.api.routes as routes
from backend.main import app
from backend.schemas.cv import ContactInfo, ParsedCV, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import MatchEvaluationResult, Recommendation


@pytest.fixture
def api_client():
    """Provides a FastAPI TestClient."""
    return TestClient(app)


def test_health_and_root_endpoints(api_client):
    """Verify /health and root service endpoints."""
    res_health = api_client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    res_root = api_client.get("/")
    assert res_root.status_code == 200
    assert "docs_url" in res_root.json()


def test_cv_upload_pipeline(api_client, monkeypatch):
    """Verify POST /api/v1/cv/upload parses, scrubs PII, and indexes candidate."""
    mock_parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Alex Wright", email="alex@example.com"),
        skills=["Python", "FastAPI"],
        experiences=[
            WorkExperience(
                job_title="AI Engineer",
                company_name="NovaTech",
                work_description=["Alex Wright engineered RAG pipelines with Python."],
                skills_used=["Python"]
            )
        ]
    )

    # Mock parse_and_anonymize to isolate from external LLM costs during unit test run
    monkeypatch.setattr(
        routes._parser_agent,
        "parse_and_anonymize",
        lambda source, filename=None: (
            mock_parsed,
            routes._parser_agent.pii_scrubber.anonymize_cv(mock_parsed)
        )
    )

    dummy_content = b"Alex Wright resume with Python RAG experience."
    res = api_client.post(
        "/api/v1/cv/upload",
        files={"file": ("alex_cv.txt", dummy_content, "text/plain")}
    )
    assert res.status_code == 201
    data = res.json()
    assert "candidate_id" in data
    assert data["chunks_indexed"] > 0
    assert data["parsed_cv"]["contact_info"]["full_name"] == "Alex Wright"


def test_hitl_validation_endpoint(api_client):
    """Verify POST /api/v1/hitl/validate records recruiter decisions and notes."""
    eval_id = uuid4()
    candidate_id = uuid4()
    job_id = uuid4()

    mock_eval = MatchEvaluationResult(
        id=eval_id,
        candidate_id=candidate_id,
        job_id=job_id,
        overall_score=75.0,
        must_have_score=75.0,
        nice_to_have_score=75.0,
        recommendation=Recommendation.BORDERLINE,
        must_have_gaps_count=1,
        citation_verification_score=1.0,
        hitl_validated=False
    )
    routes._EVALUATION_STORE[eval_id] = mock_eval

    payload = {
        "evaluation_id": str(eval_id),
        "recruiter_decision": "strong_match",
        "recruiter_notes": "Recruiter verified candidate has equivalent transferrable skills."
    }
    res = api_client.post("/api/v1/hitl/validate", json=payload)
    assert res.status_code == 200
    updated = res.json()
    assert updated["recommendation"] == "strong_match"
    assert updated["hitl_validated"] is True
    assert "equivalent transferrable skills" in updated["recruiter_notes"]
