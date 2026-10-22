"""End-to-end policy regressions using synthetic evidence and isolated persistence."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.agents.llm_factory import DynamicLLMClient
from backend.api.recruiter import save_run
from backend.config import settings
from backend.db.repository import DatabaseRepository
from backend.main import app
from backend.schemas.cv import AnonymizedCandidate, LanguageSkill, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import RequirementMatch, VerbatimCitation
from backend.services.action_logger import action_logger
from backend.services.evidence import assess_language, clean_model_text, source_quote
from backend.services.hybrid_screening import HybridRankingEngine
from backend.services.interview_service import InterviewValidationService
from backend.services.pre_ranking import PreRankingEngine
from backend.services.scoring_engine import ScoringEngine
from backend.services.screening_duplicates import candidate_name_key
from backend.services.vector_store import VectorStoreService


def requirement(title="German Language", description="German B2 proficiency", **kwargs):
    return JobRequirement(id=str(uuid4()), title=title, description=description, category="must_have", **kwargs)


@pytest.mark.parametrize("engine_type", [PreRankingEngine, HybridRankingEngine])
def test_documented_mandatory_language_precedes_generic_similarity(engine_type):
    job = JobDescription(title="Support with German", requirements=[requirement(),
        requirement("Technical troubleshooting", "Technical troubleshooting"),
        requirement("Ticket management", "Ticket management")])
    generic = AnonymizedCandidate(anonymized_languages=[LanguageSkill(language="English", proficiency="C1")],
        anonymized_work_experiences=[WorkExperience(job_title="IT support", work_description=["Technical troubleshooting and ticket management."])])
    german = AnonymizedCandidate(anonymized_languages=[LanguageSkill(language="German", proficiency="C1")])
    rows = engine_type(lambda texts: [[1., 0.] for _ in texts]).rank([generic, german], job)
    assert rows[0].candidate_id == german.candidate_id
    assert rows[0].language_priority == 0 and rows[1].language_priority == 1
    assert rows[1].pre_screen_score > 0  # Unknown does not erase legitimate strengths.


def test_unspecified_language_threshold_is_not_a_missing_candidate_level():
    candidate = AnonymizedCandidate(anonymized_languages=[LanguageSkill(language="German", proficiency="C1")])
    assert assess_language(candidate, requirement(description="Proficiency in German is required."))[:2] == ("supported", 100)
    candidate.anonymized_languages = []
    assert assess_language(candidate, requirement())[0] == "unknown"


def test_citation_policy_requires_support_and_preserves_original_span():
    req = requirement("English language", "English proficiency")
    job = JobDescription(title="Support", requirements=[req])
    candidate = AnonymizedCandidate(sanitized_text="Languages\nEnglish: Native\nC++ development")
    match = RequirementMatch(requirement_id=req.id, status="met", score=1, reasoning="Native English")
    unsupported = ScoringEngine().compute_evaluation(candidate, job, [match])
    assert unsupported.overall_score <= 50 and unsupported.recommendation != "strong_match"
    match.citations = [VerbatimCitation(quote="English (Native)")]
    supported = ScoringEngine().compute_evaluation(candidate, job, [match])
    assert supported.overall_score == 100
    assert supported.requirement_matches[0].citations[0].quote == "English: Native"
    assert source_quote("C++", "C") is None
    assert source_quote("JavaScript", "Java") is None


def test_inactive_job_is_not_an_evaluation():
    with pytest.raises(ValueError, match="active"):
        ScoringEngine().compute_evaluation(AnonymizedCandidate(),
            JobDescription(title="Inactive", requirements=[requirement(weight=0)]), [])


def test_storage_outage_is_not_missing_evidence():
    class BrokenCollection:
        def query(self, **kwargs):
            raise OSError("Synthetic storage outage")
    store = VectorStoreService.__new__(VectorStoreService)
    store.candidate_collection = BrokenCollection()
    with pytest.raises(RuntimeError, match="retrieval is unavailable"):
        store.query_candidate_chunks(uuid4(), "Ticket management")


def test_benchmark_answers_and_same_names_do_not_become_evidence_or_identity():
    assert clean_model_text("Cloud migration (REJECT Tier)") == "Cloud migration"
    assert candidate_name_key({"contact_info": {"full_name": "Alex Example"}, "raw_text": "First resume"}) != candidate_name_key(
        {"contact_info": {"full_name": "Alex Example"}, "raw_text": "Second resume"})


def test_strict_api_auth_and_admin_permissions(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_demo_mode", False)
    client = TestClient(app)
    assert client.get("/api/v1/candidates").status_code == 401
    assert client.get("/api/v1/screening/statistics").status_code == 401
    from backend.api.auth import create_session_token
    client.cookies.set("atos_workspace", create_session_token("user"))
    assert client.get("/api/v1/screening/models").status_code == 200
    assert client.get("/api/v1/settings/llm").status_code == 403


@pytest.mark.parametrize("decision", ["reject", "borderline"])
def test_review_is_not_interview_approval(decision):
    evaluation = SimpleNamespace(hitl_validated=True, recommendation=decision)
    with pytest.raises(HTTPException) as error:
        InterviewValidationService.check_progression_approval(evaluation, require_approval=True)
    assert error.value.status_code == 409
    assert InterviewValidationService.check_progression_approval(evaluation, require_approval=False) == (True, False)


def test_concurrent_requirement_context_is_isolated(monkeypatch):
    class Result(BaseModel):
        value: str
    barrier = Barrier(2)
    class Provider:
        last_usage = {}
        def generate_structured(self, prompt, response_model, **kwargs):
            barrier.wait(timeout=5)
            return response_model(value=prompt)
    client = DynamicLLMClient()
    monkeypatch.setattr(client, "get_fallback_chain", lambda: [("test", "synthetic", Provider())])
    action_logger.clear()
    def run(req):
        client.set_action_context("candidate_evaluation", {"requirement_id": req})
        return client.generate_structured(req, Result)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, ["A", "B"]))
    logs = action_logger.get_all_logs()
    assert {entry["prompt"]: entry["metadata"]["requirement_id"] for entry in logs} == {"A": "A", "B": "B"}


@pytest.mark.asyncio
async def test_trace_survives_buffer_clear_and_rejects_wrong_job():
    job = JobDescription(title="Synthetic trace", requirements=[requirement()])
    other = JobDescription(title="Other role", requirements=[requirement()])
    await DatabaseRepository.save_job(job)
    await DatabaseRepository.save_job(other)
    run_id = str(uuid4())
    await save_run({"id": run_id, "job_id": str(job.id), "job": job.model_dump(mode="json"),
        "candidate_ids": [], "rows": [], "status": "completed"})
    action_logger.clear()
    action_logger.record_action("candidate_evaluation", "test", "synthetic", "Captured source",
        metadata={"job_id": str(job.id), "run_id": run_id})
    action_logger.record_action("candidate_evaluation", "test", "synthetic", "Unrelated",
        metadata={"job_id": str(other.id), "run_id": str(uuid4())})
    await action_logger.persist_run(run_id)
    client = TestClient(app)
    before_clear = client.get(f"/api/v1/screening/jobs/{job.id}/action-trace?run_id={run_id}").json()
    assert before_clear["export_metadata"]["captured_actions"] == 1
    assert before_clear["candidates"] == []
    action_logger.clear()
    response = client.get(f"/api/v1/screening/jobs/{job.id}/action-trace?run_id={run_id}")
    assert response.status_code == 200
    assert [entry["prompt"] for entry in response.json()["actions"]] == ["Captured source"]
    assert client.get(f"/api/v1/screening/runs/{run_id}?job_id={other.id}").status_code == 409
    assert client.get(f"/api/v1/screening/jobs/{other.id}/action-trace?run_id={run_id}").status_code == 409


def test_same_action_telemetry_does_not_mix_concurrent_candidates():
    from backend.services.token_tracker import TokenTracker
    tracker = TokenTracker()
    barrier = Barrier(2)
    def process(tokens):
        tracker.start_action_session("candidate_evaluation")
        barrier.wait(timeout=5)
        tracker.record_usage("test", "synthetic", tokens, 0)
        barrier.wait(timeout=5)
        return tracker.end_action_session("candidate_evaluation").total_tokens
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(process, [11, 29])) == [11, 29]


def test_ticket_retrieval_does_not_accept_mathematical_queues():
    from backend.services.evidence import relevant_source_passages
    source = "University module: queue management and queueing theory.\n\nResolved tickets using ServiceNow queues."
    assert relevant_source_passages(source, "Ticket management and queue handling") == ["Resolved tickets using ServiceNow queues."]


def test_legacy_evaluation_reads_preserve_saved_verdicts():
    from backend.api.routes import _reconstruct_evaluation_from_db
    from backend.db.models import MatchEvaluationModel
    record = MatchEvaluationModel(id=str(uuid4()), candidate_id=str(uuid4()), job_id=str(uuid4()),
        overall_score=55, must_have_score=55, nice_to_have_score=0, recommendation="reject",
        must_have_gaps_count=1, hitl_validated=False, citation_verification_score=0,
        matches_json=[{"requirement_id": "night_shift", "status": "not_met", "score": 0, "reasoning": "Not available for night shift"}])
    result = _reconstruct_evaluation_from_db(record)
    assert result.recommendation == "reject"
    assert result.requirement_matches[0].status == "not_met"
    assert result.must_have_gaps_count == 1
