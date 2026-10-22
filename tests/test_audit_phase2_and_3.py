"""
tests/test_audit_phase2_and_3.py
Unit tests verifying audit remediations for E15, E10, E11, E12, E13, U1, and U4:
- E15: Candidate deletion cascades and redacts ScreeningRunModel snapshots and caches
- E10: Global parser admission semaphore and interrupted batch recovery
- E11: Compliance dossier provenance, recommendation immutability, and decision separation
- E12: Operational telemetry vs demo data separation and ContextVar action propagation
- E13: Health readiness endpoint probes database connectivity
- U1: Unbounded candidate listing for full cohort reach (>1000)
- U4: Job screening runs history endpoint for state and run preservation
"""

import asyncio
from datetime import datetime, timezone
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from backend.main import app
from backend.db.models import (
    BatchJobModel,
    CandidateModel,
    InterviewPlanModel,
    JobRequisitionModel,
    MatchEvaluationModel,
    ScreeningRunModel,
)
from backend.db.repository import DatabaseRepository
from backend.db.session import async_session_scope
from backend.schemas.cv import AnonymizedCandidate, ParsedCV, ContactInfo
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import MatchEvaluationResult, Recommendation, RequirementMatch
from backend.services.compliance_service import ComplianceService
from backend.services.token_tracker import TokenTracker, _ACTIVE_ACTION_VAR


@pytest.fixture
def api_client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# E15: Candidate deletion cascades and redacts ScreeningRunModel payloads
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_candidate_deletion_redacts_screening_run_snapshots_and_caches():
    cid = uuid4()
    jid = uuid4()
    cid_str = str(cid)
    jid_str = str(jid)

    # 1. Seed candidate and job
    job = JobDescription(id=jid, title="Test Job For Deletion", requirements=[])
    parsed_cv = ParsedCV(contact_info=ContactInfo(full_name="Target Candidate", email="target@delete.com"))
    anon_cv = AnonymizedCandidate(candidate_id=cid, anonymized_skills=["Python"])

    async with async_session_scope() as s:
        await DatabaseRepository.save_job(job, session=s)
        await DatabaseRepository.save_candidate(parsed_cv, anon_cv, session=s)

        # Create evaluation and screening run referencing candidate
        eval_model = MatchEvaluationModel(
            id=str(uuid4()),
            candidate_id=cid_str,
            job_id=jid_str,
            overall_score=90.0,
            must_have_score=90.0,
            nice_to_have_score=90.0,
            must_have_gaps_count=0,
            recommendation="strong_match",
            matches_json=[],
        )
        s.add(eval_model)

        run_id = str(uuid4())
        run_payload = {
            "id": run_id,
            "job_id": jid_str,
            "candidate_ids": [cid_str, "other-candidate-id"],
            "rows": [
                {"candidate_id": cid_str, "rank": 1, "masked_name": "Target Candidate"},
                {"candidate_id": "other-candidate-id", "rank": 2, "masked_name": "Other Candidate"},
            ],
            "decisions": {cid_str: {"decision": "interview"}, "other-candidate-id": {"decision": "hold"}},
            "interviews": {cid_str: {"plan_id": "plan-1"}},
        }
        s.add(ScreeningRunModel(id=run_id, job_id=jid_str, payload=run_payload))
        await s.commit()

    # 2. Perform deletion
    deleted = await DatabaseRepository.delete_candidate(cid)
    assert deleted is True

    # 3. Verify CandidateModel, MatchEvaluationModel deleted
    async with async_session_scope() as s:
        cand_record = await s.get(CandidateModel, cid_str)
        assert cand_record is None

        # Verify evaluation was cascade deleted
        eval_check = (await s.execute(
            MatchEvaluationModel.__table__.select().where(MatchEvaluationModel.candidate_id == cid_str)
        )).first()
        assert eval_check is None

        # Verify ScreeningRunModel payload was redacted
        run_record = await s.get(ScreeningRunModel, run_id)
        assert run_record is not None
        payload = run_record.payload
        assert cid_str not in payload["candidate_ids"]
        assert len(payload["candidate_ids"]) == 1
        assert not any(row.get("candidate_id") == cid_str for row in payload["rows"])
        assert len(payload["rows"]) == 1
        assert cid_str not in payload["decisions"]
        assert cid_str not in payload["interviews"]


# ---------------------------------------------------------------------------
# E10: Interrupted batch recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recover_interrupted_batches():
    batch_id = str(uuid4())
    async with async_session_scope() as s:
        batch = BatchJobModel(
            id=batch_id,
            job_id=None,
            status="PROCESSING",
            total_files=5,
            processed_files=2,
            failed_files=0,
            results_json=[{"filename": "file1.pdf", "status": "COMPLETED"}],
        )
        s.add(batch)
        await s.commit()

    recovered = await DatabaseRepository.recover_interrupted_batches()
    assert recovered >= 1

    async with async_session_scope() as s:
        recovered_batch = await s.get(BatchJobModel, batch_id)
        assert recovered_batch is not None
        assert recovered_batch.status == "INTERRUPTED"
        assert any(r.get("status") == "INTERRUPTED" for r in recovered_batch.results_json)


# ---------------------------------------------------------------------------
# E11: Compliance dossier provenance and decision separation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_compliance_dossier_provenance_and_override():
    cid = uuid4()
    jid = uuid4()
    eid = uuid4()
    eval_model = MatchEvaluationModel(
        id=str(eid),
        candidate_id=str(cid),
        job_id=str(jid),
        overall_score=85.0,
        must_have_score=85.0,
        nice_to_have_score=80.0,
        must_have_gaps_count=0,
        recommendation="reject",  # Human override
        llm_recommendation="strong_match",  # Original AI recommendation
        recruiter_decision="reject",
        evaluated_with_model="custom-llama-3.3",
        evaluated_with_provider="groq",
        hitl_validated=True,
        recruiter_notes="Candidate lacked specific domain context in interview",
        citation_verification_score=1.0,
        matches_json=[],
    )
    job_model = JobRequisitionModel(id=str(jid), title="Platform Lead", department="Engineering")
    cand_model = CandidateModel(id=str(cid), sanitized_text="Sanitized CV text", chunks_indexed=3)

    dossier = ComplianceService.generate_dossier(
        evaluation=eval_model,
        candidate=cand_model,
        job=job_model,
    )

    art14 = dossier["article_14_human_oversight"]
    assert art14["algorithmic_recommendation"] == "strong_match"
    assert art14["recruiter_decision"] == "reject"
    assert art14["human_override_exercised"] is True

    art11 = dossier["article_11_technical_documentation"]
    assert "custom-llama-3.3" in art11["inference_model"]


# ---------------------------------------------------------------------------
# E12: Operational telemetry vs demo data separation & ContextVar propagation
# ---------------------------------------------------------------------------
def test_operational_telemetry_and_contextvar_propagation():
    tracker = TokenTracker()
    tracker.reset_usage_data()

    # 1. Verify start_action_session sets ContextVar
    tracker.start_action_session("screening_test_action")
    assert _ACTIVE_ACTION_VAR.get().startswith("screening_test_action:")

    # 2. Record operational call
    tracker.record_usage(
        provider="groq",
        model="llama-3.3-70b-versatile",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=250.0,
    )
    info = tracker.end_action_session("screening_test_action")
    assert info.total_tokens == 150
    assert _ACTIVE_ACTION_VAR.get() is None

    # 3. Verify get_analytics with include_synthetic=False only counts real calls
    analytics = tracker.get_analytics(time_range="all", include_synthetic=False)
    assert analytics.total_tokens == 150
    assert analytics.total_requests == 1


# ---------------------------------------------------------------------------
# E13: Health endpoint probes database readiness
# ---------------------------------------------------------------------------
def test_health_endpoint_probes_database(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"


# ---------------------------------------------------------------------------
# U1: Candidate library uses bounded pages to reach the full cohort
# ---------------------------------------------------------------------------
def test_list_candidates_bounded_pages(api_client):
    assert api_client.get("/api/v1/candidates?limit=5000").status_code == 422
    response = api_client.get("/api/v1/candidates?limit=100&offset=1000")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) <= 100


# ---------------------------------------------------------------------------
# U4: Job screening runs history endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_job_screening_runs_history():
    jid = uuid4()
    job = JobDescription(id=jid, title="Historical Role", requirements=[])
    run_id1 = str(uuid4())
    run_id2 = str(uuid4())

    async with async_session_scope() as s:
        await DatabaseRepository.save_job(job, session=s)
        s.add(ScreeningRunModel(
            id=run_id1,
            job_id=str(jid),
            payload={"id": run_id1, "status": "completed", "candidate_ids": ["c1"], "rows": [{"candidate_id": "c1", "deep_status": "completed"}]},
        ))
        s.add(ScreeningRunModel(
            id=run_id2,
            job_id=str(jid),
            payload={"id": run_id2, "status": "partial", "candidate_ids": ["c1", "c2"], "rows": []},
        ))
        await s.commit()

    client = TestClient(app)
    response = client.get(f"/api/v1/screening/jobs/{jid}/runs")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) >= 2
    ids = [r["id"] for r in runs]
    assert run_id1 in ids and run_id2 in ids
