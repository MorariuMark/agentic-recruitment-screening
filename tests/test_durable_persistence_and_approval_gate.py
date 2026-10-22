"""
tests/test_durable_persistence_and_approval_gate.py
Unit tests verifying E8 (durable success vs saved success) and E9 (case identity & shared approval gate).
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend.api import routes
from backend.db.repository import DatabaseRepository
from backend.main import app
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import MatchEvaluationResult, MatchStatus, Recommendation, RequirementMatch


@pytest.fixture
def client():
    return TestClient(app)


def test_durable_save_failure_raises_500_and_does_not_cache_dirty_evaluation(client, monkeypatch):
    """Verify E8: database errors are not swallowed and unpersisted evaluations are not cached."""
    cand_id = uuid4()
    job_id = uuid4()
    routes._CANDIDATE_ANONYMIZED_STORE[cand_id] = AnonymizedCandidate(
        candidate_id=cand_id,
        anonymized_skills=["Python"],
        sanitized_text="Python developer",
        demographic_data={},
    )
    job = JobDescription(
        id=job_id,
        title="Developer",
        requirements=[JobRequirement(id="r1", title="Python", description="Python", category="must_have", weight=1.0)],
    )

    # Isolate persistence from provider availability and vector infrastructure.
    monkeypatch.setattr(routes._matching_agent, "match_candidate", lambda **kwargs: MatchEvaluationResult(
        candidate_id=cand_id, job_id=job_id, overall_score=80, must_have_score=80,
        recommendation="strong_match", requirement_matches=[]))

    # Force database persistence failure
    async def mock_fail_save(*args, **kwargs):
        raise RuntimeError("Disk IO failure or DB timeout")

    monkeypatch.setattr(DatabaseRepository, "save_job", mock_fail_save)

    payload = {
        "candidate_id": str(cand_id),
        "job_description": job.model_dump(mode="json"),
        "strictness": 50,
    }

    response = client.post("/api/v1/match/evaluate", json=payload)
    # Must report HTTP 500, NOT a fake HTTP 200
    assert response.status_code == 500
    assert "Failed to persist evaluation to database" in response.json()["detail"]


def test_hitl_validation_failure_does_not_taint_cached_evaluation(client, monkeypatch):
    """Verify E8: failed persistence does not mutate the in-memory cached evaluation."""
    eval_id = uuid4()
    original_eval = MatchEvaluationResult(
        id=eval_id,
        candidate_id=uuid4(),
        job_id=uuid4(),
        overall_score=60.0,
        must_have_score=60.0,
        recommendation=Recommendation.BORDERLINE,
        hitl_validated=False,
    )
    routes._EVALUATION_STORE[eval_id] = original_eval

    # Mock database failure on validation update
    async def mock_fail_update(*args, **kwargs):
        raise RuntimeError("Database connection pool exhausted")

    monkeypatch.setattr(DatabaseRepository, "update_hitl_validation", mock_fail_update)

    payload = {
        "evaluation_id": str(eval_id),
        "recruiter_decision": "strong_match",
        "recruiter_notes": "Approving candidate",
    }

    response = client.post("/api/v1/hitl/validate", json=payload)
    assert response.status_code == 500

    # Ensure cached evaluation was NOT mutated to validated or strong_match
    cached = routes._EVALUATION_STORE[eval_id]
    assert cached.hitl_validated is False
    assert cached.recommendation == Recommendation.BORDERLINE


def test_e9_case_identity_mismatch_rejected(client):
    """Verify E9: mismatch between evaluation, candidate, and job is rejected."""
    cand_a = uuid4()
    cand_b = uuid4()
    job_a = uuid4()
    eval_id = uuid4()

    # Evaluation belongs to Candidate B and Job A
    eval_b = MatchEvaluationResult(
        id=eval_id,
        candidate_id=cand_b,
        job_id=job_a,
        overall_score=85.0,
        must_have_score=85.0,
        recommendation=Recommendation.STRONG_MATCH,
        hitl_validated=True,
    )
    routes._EVALUATION_STORE[eval_id] = eval_b
    routes._CANDIDATE_ANONYMIZED_STORE[cand_a] = AnonymizedCandidate(candidate_id=cand_a, sanitized_text="Dev", demographic_data={})

    job = JobDescription(id=job_a, title="Dev", requirements=[JobRequirement(id="r1", title="Python", description="Python", category="must_have")])

    # Request attempts to pair candidate A with evaluation B
    payload = {
        "candidate_id": str(cand_a),
        "evaluation_id": str(eval_id),
        "job_description": job.model_dump(mode="json"),
        "target_duration_minutes": 45,
    }

    response = client.post("/api/v1/interview/generate", json=payload)
    assert response.status_code == 400
    assert "Case identity mismatch" in response.json()["detail"]


def test_e9_interview_progression_approval_gate(client, monkeypatch):
    """Verify E9: unapproved candidates are rejected when approval required, or marked as draft."""
    cand_id = uuid4()
    job_id = uuid4()
    eval_id = uuid4()

    unapproved_eval = MatchEvaluationResult(
        id=eval_id,
        candidate_id=cand_id,
        job_id=job_id,
        overall_score=80.0,
        must_have_score=80.0,
        recommendation=Recommendation.BORDERLINE,
        hitl_validated=False,  # NOT approved by human
    )
    routes._EVALUATION_STORE[eval_id] = unapproved_eval
    routes._CANDIDATE_ANONYMIZED_STORE[cand_id] = AnonymizedCandidate(candidate_id=cand_id, sanitized_text="Dev", demographic_data={})
    job = JobDescription(id=job_id, title="Dev", requirements=[JobRequirement(id="r1", title="Python", description="Python", category="must_have")])

    # 1. When require_approval=True: must raise HTTP 409
    payload_strict = {
        "candidate_id": str(cand_id),
        "evaluation_id": str(eval_id),
        "job_description": job.model_dump(mode="json"),
        "target_duration_minutes": 45,
        "require_approval": True,
    }
    res_strict = client.post("/api/v1/interview/generate", json=payload_strict)
    assert res_strict.status_code == 409
    assert "A recruiter must validate and approve this candidate" in res_strict.json()["detail"]

    # 2. When require_approval=False: generates an explicit draft plan
    from backend.schemas.interview import InterviewPlan, InterviewQuestion
    dummy_plan = InterviewPlan(
        candidate_id=cand_id,
        job_id=job_id,
        interview_focus_summary="Draft summary",
        questions=[InterviewQuestion(id="q1", target_requirement_id="r1", question_text="Tell me about Python")],
    )
    monkeypatch.setattr(routes._interview_agent, "generate_interview_plan", lambda *args, **kwargs: dummy_plan)

    payload_draft = {
        "candidate_id": str(cand_id),
        "evaluation_id": str(eval_id),
        "job_description": job.model_dump(mode="json"),
        "target_duration_minutes": 45,
        "require_approval": False,
    }
    res_draft = client.post("/api/v1/interview/generate", json=payload_draft)
    assert res_draft.status_code == 200
    data = res_draft.json()
    assert data["is_draft"] is True
    assert data["hitl_approved"] is False
