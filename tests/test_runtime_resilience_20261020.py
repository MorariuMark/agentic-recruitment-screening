"""Offline regressions for provider limits, evidence policy and approval."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.agents import llm_factory as factory
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import MatchEvaluationResult, RequirementMatch, VerbatimCitation
from backend.services.evidence import clean_model_text, is_benchmark_profile, language_priority
from backend.services.interview_service import InterviewValidationService
from backend.services.scoring_engine import ScoringEngine


def test_groq_criterion_reserves_only_700_tokens(monkeypatch):
    monkeypatch.setattr(factory.time, "sleep", lambda seconds: None)
    client = factory.GroqClient(api_key="test", compatibility_mode="auto")
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"requirement_id":"r","status":"met","score":1,"reasoning":"Source"}'))], usage=None)
    client.client = MagicMock()
    client.client.chat.completions.create.return_value = response
    client.generate_structured("Evaluate", RequirementMatch)
    assert client.client.chat.completions.create.call_args.kwargs["max_tokens"] == 700


def test_empty_free_response_fails_without_same_provider_retry():
    client = factory.OpenRouterClient(api_key="test", compatibility_mode="auto")
    client.client = MagicMock()
    client.client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="  "))])
    with pytest.raises(ValueError, match="empty response"):
        client.generate_structured("Evaluate", RequirementMatch)
    assert client.client.chat.completions.create.call_count == 1


def test_timeout_does_not_repeat_as_format_retry():
    client = factory.NvidiaNimClient(api_key="test", compatibility_mode="auto")
    client.client = MagicMock()
    client.client.chat.completions.create.side_effect = TimeoutError("provider hung")
    with pytest.raises(TimeoutError):
        client.generate_structured("Evaluate", RequirementMatch)
    assert client.client.chat.completions.create.call_count == 1


@pytest.mark.parametrize("category", ["must_have", "nice_to_have", "soft_skill"])
def test_scoring_inherits_job_category(category):
    req = JobRequirement(id="r", title="Python", description="Python", category=category)
    result = ScoringEngine().compute_evaluation(AnonymizedCandidate(sanitized_text="Python"), JobDescription(title="Dev", requirements=[req]),
        [RequirementMatch(requirement_id="r", category="nice_to_have", status="met", score=1, reasoning="Source", citations=[VerbatimCitation(quote="Python")])])
    assert result.model_dump(mode="json")["requirement_matches"][0]["category"] == category


def test_benchmark_labels_are_removed_from_model_inputs():
    value = "Project [tier_1] at Company (STRONG Tier) [tier_3]"
    assert clean_model_text(value) == "Project at Company"
    assert is_benchmark_profile({"project": value})


def test_recruiter_defined_local_presence_gate_requires_documentation():
    job = JobDescription(title="Onsite", requirements=[JobRequirement(id="r", category="must_have", title="Local presence", description="Must be locally available", eligibility_evidence="Available onsite in Bucharest")])
    assert language_priority(AnonymizedCandidate(sanitized_text="Available onsite in Bucharest"), job) == 0
    assert language_priority(AnonymizedCandidate(sanitized_text="Worked in Bucharest previously"), job) == 1


def test_reviewed_model_match_requires_explicit_recruiter_approval():
    result = MatchEvaluationResult(candidate_id=uuid4(), job_id=uuid4(), overall_score=90, must_have_score=90, recommendation="strong_match", hitl_validated=True)
    with pytest.raises(HTTPException) as error:
        InterviewValidationService.check_progression_approval(result)
    assert error.value.status_code == 409
    result.recruiter_decision = "strong_match"
    assert InterviewValidationService.check_progression_approval(result) == (False, True)


def test_candidate_pagination_rejects_unbounded_or_negative_requests():
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    assert client.get("/api/v1/candidates?limit=10000").status_code == 422
    assert client.get("/api/v1/candidates?offset=-1").status_code == 422


@pytest.mark.asyncio
async def test_recruiter_evidence_gate_survives_job_reload():
    from backend.api.routes import _reconstruct_job_from_db
    from backend.db.repository import DatabaseRepository
    job = JobDescription(title="Local role", requirements=[JobRequirement(id=str(uuid4()), category="must_have", title="Presence", description="Local", eligibility_evidence="Available onsite in Bucharest")])
    await DatabaseRepository.save_job(job)
    record = await DatabaseRepository.get_job(job.id)
    assert _reconstruct_job_from_db(record).requirements[0].eligibility_evidence == "Available onsite in Bucharest"


def test_retired_nim_is_excluded_even_from_saved_fallback_configuration(monkeypatch):
    monkeypatch.setattr(factory.settings, "llm_provider", "nvidia_nim")
    monkeypatch.setattr(factory.settings, "nvidia_nim_model", "nvidia/llama-3.1-nemotron-70b-instruct")
    monkeypatch.setattr(factory.settings, "nvidia_nim_api_key", "test")
    monkeypatch.setattr(factory.DynamicLLMClient, "_get_or_create_client", lambda *a, **kw: MagicMock())
    assert all(model != "nvidia/llama-3.1-nemotron-70b-instruct" for _, model, _ in factory.DynamicLLMClient().get_fallback_chain())


def test_seed_ground_truth_is_metadata_not_profile_or_filename():
    from scripts.generate_and_seed_cohort import build_candidate, PROFILE_SKILLS
    parsed = build_candidate(next(iter(PROFILE_SKILLS)), "strong", 1)
    assert parsed.benchmark_annotations["tier"] == "strong"
    assert "Tier)" not in parsed.raw_text and "[tier_" not in parsed.raw_text
    assert "benchmark_annotations" not in AnonymizedCandidate.model_fields
