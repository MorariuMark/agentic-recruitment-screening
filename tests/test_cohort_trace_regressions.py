"""Offline reproductions of the supplied ServiceNow cohort trace's failure modes."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.agents import llm_factory as factory
from backend.agents.matching_agent import MatchingAgent, EvaluationSourceError, is_interpretive_requirement, generate_clarification_question
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import RequirementMatch
from backend.services.scoring_engine import ScoringEngine


@pytest.fixture(autouse=True)
def isolated_breaker(monkeypatch):
    monkeypatch.setattr(factory, "_MODEL_COOLDOWNS", {})
    monkeypatch.setattr(factory, "_GROQ_NEXT_CALL", {})
    monkeypatch.setattr(factory.time, "sleep", lambda seconds: None)


class RateLimited(Exception):
    status_code = 429
    response = SimpleNamespace(headers={"Retry-After": "13.56"})


def test_exhausted_key_is_not_called_again_by_queued_requirements(monkeypatch):
    monkeypatch.setattr(factory.time, "time", lambda: 1000)
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = RateLimited("output tokens per minute exhausted")
    kwargs = {"model": "qwen/qwen3.8-27b", "max_tokens": 700}
    with pytest.raises(RateLimited):
        factory._paced_groq_call(sdk, kwargs, "test-key")
    with pytest.raises(factory.ProviderCoolingDownError):
        factory._paced_groq_call(sdk, kwargs, "test-key")
    assert sdk.chat.completions.create.call_count == 1
    assert factory._MODEL_COOLDOWNS[("groq", kwargs["model"], "test-key")] == pytest.approx(1013.81)


def test_waiting_request_rechecks_a_new_cooldown_before_dispatch(monkeypatch):
    sdk = MagicMock()
    model = "openai/gpt-oss-20b"
    def cooldown_during_wait(seconds):
        factory.record_model_failure("groq", model, RateLimited("429"), "key")
    monkeypatch.setattr(factory.time, "sleep", cooldown_during_wait)
    with pytest.raises(factory.ProviderCoolingDownError):
        factory._paced_groq_call(sdk, {"model": model}, "key")
    sdk.chat.completions.create.assert_not_called()


def test_queued_skip_does_not_extend_a_rate_limit_cooldown():
    key = ("groq", "model", "key")
    factory._MODEL_COOLDOWNS[key] = 1234
    factory.record_model_failure("groq", "model", factory.ProviderCoolingDownError("queued"), "key")
    assert factory._MODEL_COOLDOWNS[key] == 1234


@pytest.mark.parametrize("message, expected", [
    ("Please try again in 9.06s.", 9.06), ("Please try again in 150ms.", .15),
    ("Retry after 2 minutes", 120), ("Rate limit reached", None)])
def test_retry_delay_is_parsed_without_guessing(message, expected):
    assert factory._retry_after_seconds(RuntimeError(message)) == expected


@pytest.mark.parametrize("source", ["Product leadership and enterprise software experience.", "Current location: another city. Product leadership."])
def test_location_silence_requires_clarification_not_an_objective_rejection(source):
    requirement = JobRequirement(id="location", title="Location & On-Site Presence (Timisoara, Romania)",
        description="Candidate must be based in or able to work on-site at Timisoara, Romania.", category="must_have")
    assert is_interpretive_requirement(requirement) is True
    assert "Timisoara" in generate_clarification_question(requirement)
    llm = MagicMock()
    llm.generate_structured.return_value = RequirementMatch(requirement_id="location", status="not_met", score=0,
        reasoning="The CV describes a role in another city and contains no relocation commitment.")
    vectors = MagicMock()
    vectors.query_candidate_chunks.return_value = []
    agent = MatchingAgent(llm_client=llm, vector_store=vectors, scoring_engine=ScoringEngine())
    candidate = AnonymizedCandidate(sanitized_text=source)
    result = agent.evaluate_requirement(candidate.candidate_id, requirement, candidate=candidate)
    assert result.status == "clarification_needed" and result.is_objective is False
    assert result.score == .5 and result.clarification_question


def test_historical_onsite_support_experience_remains_an_objective_skill():
    requirement = JobRequirement(id="support", title="On-site support experience", description="Five years supporting users", category="must_have")
    assert is_interpretive_requirement(requirement) is False


def test_missing_source_stops_before_provider_calls_or_negative_scoring():
    llm, vectors, scoring = MagicMock(), MagicMock(), MagicMock()
    agent = MatchingAgent(llm_client=llm, vector_store=vectors, scoring_engine=scoring)
    candidate = AnonymizedCandidate(anonymized_skills=["ServiceNow"])
    job = JobDescription(title="ServiceNow product manager", requirements=[JobRequirement(id="platform", title="ServiceNow", description="Platform expertise", category="must_have")])
    with pytest.raises(EvaluationSourceError, match="Reparse the original CV"):
        agent.match_candidate(candidate, job)
    vectors.index_candidate.assert_not_called()
    llm.generate_structured.assert_not_called()
    scoring.compute_evaluation.assert_not_called()


def test_every_provider_in_cooldown_returns_a_retryable_error_not_empty_attempts(monkeypatch):
    sdk = MagicMock(api_key="key")
    monkeypatch.setattr(factory.settings, "fallback_enabled", True)
    client = factory.DynamicLLMClient()
    monkeypatch.setattr(client, "get_fallback_chain", lambda: [("groq", "model", sdk)])
    factory.record_model_failure("groq", "model", RateLimited("429"), "key")
    with pytest.raises(factory.LLMProvidersCoolingDownError) as result:
        client.generate_structured("parse", RequirementMatch)
    assert result.value.retryable and result.value.retry_after > 0
    assert "no new requests" in str(result.value).lower()
    assert "Last error: None" not in str(result.value)
    sdk.generate_structured.assert_not_called()


def test_groq_full_cv_has_a_separate_budget_and_truncated_output_is_rejected():
    from backend.schemas.cv import ParsedCV
    client = factory.GroqClient(api_key="test", compatibility_mode="auto")
    sdk = MagicMock()
    client.client = sdk
    sdk.chat.completions.create.return_value = SimpleNamespace(usage=None, choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content='{"contact_info":{"full_name":"Example"}}'))])
    client.generate_structured("parse CV", ParsedCV)
    assert sdk.chat.completions.create.call_args.kwargs["max_tokens"] == factory.settings.groq_parser_max_output_tokens
    sdk.chat.completions.create.return_value.choices[0].finish_reason = "length"
    with pytest.raises(ValueError, match="truncated"):
        client.generate_structured("parse CV", ParsedCV)


def test_rate_limit_does_not_trigger_a_second_parse_with_a_shortened_cv():
    from backend.agents.parser_agent import ParserAgent
    llm = MagicMock()
    llm.generate_structured.side_effect = RuntimeError("429 Rate limit reached; retry later")
    with pytest.raises(RuntimeError, match="429"):
        ParserAgent(llm_client=llm).parse_cv_text("Original CV with critical evidence at its end. " * 300)
    assert llm.generate_structured.call_count == 1


@pytest.mark.asyncio
async def test_long_provider_outage_preserves_pending_cvs_without_failing_them(monkeypatch):
    from uuid import uuid4
    from backend.api import routes
    from backend.db.repository import DatabaseRepository
    from backend.services.batch_processor import BatchProcessorService
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(3, batch_id=batch_id)
    calls = []
    async def unavailable(self, content, filename, job_description=None):
        calls.append(filename)
        raise factory.LLMProvidersCoolingDownError(45)
    monkeypatch.setattr(factory.settings, "parser_provider_wait_seconds", 0)
    monkeypatch.setattr(BatchProcessorService, "process_single_candidate", unavailable)
    payloads = [(f"{i}.txt", f"{batch_id}-{i}".encode()) for i in range(3)]
    await routes._batch_processor.execute_parse_batch(batch_id, payloads, 1)
    record = await DatabaseRepository.get_batch_job(batch_id)
    assert record.status == "INTERRUPTED" and record.failed_files == 0
    assert len(calls) == 1 and not record.results_json
    assert all(row["status"] == "INTERRUPTED" for row in record.progress_json["files"])
    from backend.db.models import CVDocumentModel
    from backend.db.session import async_session_scope
    from sqlalchemy import select
    import hashlib
    async with async_session_scope() as db:
        hashes = [hashlib.sha256(content).hexdigest() for _, content in payloads]
        retained = (await db.scalars(select(CVDocumentModel).where(CVDocumentModel.content_hash.in_(hashes)))).all()
        assert len(retained) == 3 and all(row.candidate_id is None for row in retained)


@pytest.mark.asyncio
async def test_temporary_cooldown_retries_the_same_cv_before_advancing(monkeypatch):
    from uuid import uuid4
    from backend.api import routes
    from backend.db.repository import DatabaseRepository
    from backend.services import batch_processor
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(2, batch_id=batch_id)
    first, second = f"cooldown-{batch_id}-first.txt", f"cooldown-{batch_id}-second.txt"
    calls, waits = [], []
    async def process(self, content, filename, job_description=None):
        calls.append(filename)
        if len(calls) == 1:
            raise factory.LLMProvidersCoolingDownError(1)
        return {"status": "COMPLETED", "filename": filename}
    async def wait(seconds):
        waits.append(seconds)
    monkeypatch.setattr(batch_processor.BatchProcessorService, "process_single_candidate", process)
    monkeypatch.setattr(batch_processor, "_provider_delay", wait)
    await routes._batch_processor.execute_parse_batch(batch_id, [(first, b"a"), (second, b"b")], 1)
    record = await DatabaseRepository.get_batch_job(batch_id)
    assert calls == [first, first, second] and waits == [1]
    assert record.status == "COMPLETED" and record.processed_files == 2 and record.failed_files == 0
