"""Quota exhaustion and malformed fallback replies must not become candidate findings."""
from collections import Counter
from types import SimpleNamespace
from unittest.mock import MagicMock
import time

import pytest

from backend.agents import llm_factory as factory
from backend.agents.matching_agent import MatchingAgent, EvaluationDeferredError
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import RequirementMatch, VerbatimCitation


@pytest.fixture(autouse=True)
def isolate_cooldowns(monkeypatch):
    monkeypatch.setattr(factory, "_MODEL_COOLDOWNS", {})
    monkeypatch.setattr(factory.settings, "fallback_enabled", True)


@pytest.mark.parametrize("choices", [None, [], [None], [SimpleNamespace(message=None)]])
def test_openrouter_missing_completion_is_a_provider_response_error(choices):
    client = factory.OpenRouterClient(api_key="synthetic")
    client.client = MagicMock()
    client.client.chat.completions.create.return_value = SimpleNamespace(choices=choices)
    with pytest.raises(factory.ProviderResponseError, match="no completion choices"):
        client.generate_structured("Evaluate", RequirementMatch)
    assert client.client.chat.completions.create.call_count == 1


def test_slow_fallback_cannot_hide_earlier_rate_limits(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(factory.time, "time", lambda: clock[0])
    quota = MagicMock(api_key="synthetic")
    quota.generate_structured.side_effect = RuntimeError("429 Rate limit reached; try again in 1s")
    slow = MagicMock(api_key="synthetic")
    def timeout(**kwargs):
        clock[0] += 40
        raise TimeoutError("Request timed out")
    slow.generate_structured.side_effect = timeout
    malformed = MagicMock(api_key="synthetic")
    malformed.generate_structured.side_effect = factory.ProviderResponseError("No completion choices")
    client = factory.DynamicLLMClient()
    monkeypatch.setattr(client, "get_fallback_chain", lambda: [
        ("groq", "limited", quota), ("nvidia_nim", "slow", slow), ("openrouter", "empty", malformed)])
    with pytest.raises(factory.LLMProvidersCoolingDownError) as failure:
        client.generate_structured("Evaluate", RequirementMatch)
    assert failure.value.retryable and failure.value.retry_after >= 1


def test_queued_cooldown_remains_retryable_when_timer_expires(monkeypatch):
    client = factory.DynamicLLMClient()
    queued = MagicMock(api_key="synthetic")
    queued.generate_structured.side_effect = factory.ProviderCoolingDownError("Entered cooldown while queued")
    monkeypatch.setattr(client, "get_fallback_chain", lambda: [("groq", "queued", queued)])
    with pytest.raises(factory.LLMProvidersCoolingDownError):
        client.generate_structured("Evaluate", RequirementMatch)


def test_gemini_retry_info_respects_the_daily_quota_reset(monkeypatch):
    error = RuntimeError("429 quota exhausted; Please retry in 7h15m31.217s")
    error.body = [{"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "26131s"}]}}]
    monkeypatch.setattr(factory.time, "time", lambda: 1000)
    assert factory._retry_after_seconds(error) == 26131
    factory.record_model_failure("gemini", "limited", error, "synthetic")
    assert factory._MODEL_COOLDOWNS[("gemini", "limited", "synthetic")] == pytest.approx(27131.25)


def test_compound_retry_duration_without_structured_body():
    assert factory._retry_after_seconds(RuntimeError("Please retry in 7h15m31.217s")) == pytest.approx(26131.217)


def requirements():
    return [JobRequirement(id=str(index), title=title, description=title, category="must_have")
            for index, title in enumerate(["Python", "Collaboration"], 1)]


def result(req):
    return RequirementMatch(requirement_id=req.id, status="met", score=1, reasoning="Documented",
                            citations=[VerbatimCitation(quote=req.title)])


def test_partial_requirement_results_survive_quota_failure_and_resume(monkeypatch):
    reqs = requirements()
    job = JobDescription(title="Engineer", requirements=reqs)
    candidate = AnonymizedCandidate(sanitized_text="Python Collaboration")
    agent = MatchingAgent(llm_client=MagicMock(), vector_store=MagicMock())
    calls = []
    limited = [True]
    def evaluate(candidate_id, requirement, **kwargs):
        calls.append(requirement.id)
        if requirement.id == "2" and limited[0]:
            raise factory.LLMProvidersCoolingDownError(10)
        return result(requirement)
    monkeypatch.setattr(agent, "evaluate_requirement", evaluate)
    with pytest.raises(EvaluationDeferredError) as failure:
        agent.match_candidate(candidate, job)
    assert failure.value.retryable and failure.value.retry_after == 10
    assert [match.requirement_id for match in agent.completed_matches] == ["1"]
    agent.resume_matches = agent.completed_matches
    limited[0] = False
    completed = agent.match_candidate(candidate, job)
    assert Counter(calls) == {"1": 1, "2": 2}
    assert completed.overall_score == 100
    assert [match.requirement_id for match in completed.requirement_matches] == ["1", "2"]


def test_dynamic_groq_matching_serializes_requirement_calls(monkeypatch):
    client = factory.DynamicLLMClient()
    client._snapshot_chain = [("groq", "synthetic", MagicMock())]
    agent = MatchingAgent(llm_client=client, vector_store=MagicMock())
    active = peak = 0
    def evaluate(candidate_id, requirement, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        time.sleep(.01)
        active -= 1
        return result(requirement)
    monkeypatch.setattr(agent, "evaluate_requirement", evaluate)
    agent.match_candidate(AnonymizedCandidate(sanitized_text="Python Collaboration"), JobDescription(title="Role", requirements=requirements()))
    assert peak == 1
