"""
tests/test_candidate_comparison.py
Tests for multi-candidate side-by-side comparison matrix and ranking report.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend.db.repository import DatabaseRepository
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
from backend.services.pii_scrubber import PIIScrubber


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_compare_candidates_endpoint(client):
    """Verify POST /api/v1/match/compare produces side-by-side requirement matrix and ranking."""
    scrubber = PIIScrubber()

    # 1. Seed Job
    jid = uuid4()
    job = JobDescription(
        id=jid,
        title="Senior Distributed Systems Architect",
        requirements=[
            JobRequirement(
                id="req_k8s",
                title="Kubernetes",
                category=RequirementCategory.MUST_HAVE,
                weight=1.5,
                description="Production K8s",
            ),
            JobRequirement(
                id="req_go",
                title="Go Concurrency",
                category=RequirementCategory.NICE_TO_HAVE,
                weight=1.0,
                description="Go routines and channels",
            ),
        ],
    )
    await DatabaseRepository.save_job(job)

    # 2. Seed Candidate 1 (Strong)
    cid1 = uuid4()
    raw1 = ParsedCV(
        contact_info=ContactInfo(full_name="Alice Smith", email="alice@test.com"),
        skills=["Kubernetes", "Go"],
    )
    anon1 = scrubber.anonymize_cv(raw1)
    anon1.candidate_id = cid1
    await DatabaseRepository.save_candidate(raw1, anon1, chunks_indexed=3, filename="alice_cv.pdf")

    eval1 = MatchEvaluationResult(
        id=uuid4(),
        candidate_id=cid1,
        job_id=jid,
        overall_score=94.0,
        must_have_score=96.0,
        nice_to_have_score=90.0,
        recommendation=Recommendation.STRONG_MATCH,
        must_have_gaps_count=0,
        citation_verification_score=1.0,
        requirement_matches=[
            RequirementMatch(
                requirement_id="req_k8s",
                status=MatchStatus.MET,
                score=0.96,
                confidence=1.0,
                reasoning="Exemplary Kubernetes production operations.",
                citations=[VerbatimCitation(quote="Managed production K8s", verified=True)],
            ),
            RequirementMatch(
                requirement_id="req_go",
                status=MatchStatus.MET,
                score=0.90,
                confidence=1.0,
                reasoning="Built concurrent Go services.",
            ),
        ],
    )
    await DatabaseRepository.save_evaluation(eval1, cid1, jid)

    # 3. Seed Candidate 2 (Borderline with a gap)
    cid2 = uuid4()
    raw2 = ParsedCV(
        contact_info=ContactInfo(full_name="Bob Jones", email="bob@test.com"),
        skills=["Go"],
    )
    anon2 = scrubber.anonymize_cv(raw2)
    anon2.candidate_id = cid2
    await DatabaseRepository.save_candidate(raw2, anon2, chunks_indexed=2, filename="bob_cv.pdf")

    eval2 = MatchEvaluationResult(
        id=uuid4(),
        candidate_id=cid2,
        job_id=jid,
        overall_score=58.0,
        must_have_score=40.0,
        nice_to_have_score=85.0,
        recommendation=Recommendation.BORDERLINE,
        must_have_gaps_count=1,
        citation_verification_score=1.0,
        requirement_matches=[
            RequirementMatch(
                requirement_id="req_k8s",
                status=MatchStatus.NOT_MET,
                score=0.40,
                confidence=0.9,
                reasoning="No evidence of Kubernetes operations.",
                gap_analysis="Missing K8s administration experience",
            ),
            RequirementMatch(
                requirement_id="req_go",
                status=MatchStatus.MET,
                score=0.85,
                confidence=1.0,
                reasoning="Go concurrency demonstrated.",
            ),
        ],
    )
    await DatabaseRepository.save_evaluation(eval2, cid2, jid)

    # 4. Request comparison report
    payload = {
        "candidate_ids": [str(cid1), str(cid2)],
        "job_id": str(jid),
    }

    res = client.post("/api/v1/match/compare", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["job_id"] == str(jid)
    assert len(data["candidates"]) == 2
    assert len(data["matrix"]) == 2

    # Top recommended candidate should be Alice (cid1)
    assert data["top_recommended_id"] == str(cid1)
    assert "Alice" in data["comparative_analysis"] or "Candidate" in data["comparative_analysis"]

    # Verify matrix structure
    matrix = data["matrix"]
    k8s_row = next(r for r in matrix if r["requirement_id"] == "req_k8s")
    assert k8s_row["candidate_cells"][str(cid1)]["status"] == "met"
    assert k8s_row["candidate_cells"][str(cid2)]["status"] == "not_met"


def test_compare_candidates_validation(client):
    """Verify endpoint enforces at least 2 candidates."""
    res = client.post(
        "/api/v1/match/compare",
        json={"candidate_ids": [str(uuid4())], "job_id": str(uuid4())},
    )
    assert res.status_code == 422
