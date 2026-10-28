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


@pytest.mark.parametrize("provider", ["ollama", "lmstudio"])
@pytest.mark.parametrize("method", ["generate_text", "generate_structured"])
@pytest.mark.parametrize("fallback_enabled", [True, False])
def test_local_failure_is_reported_and_next_request_can_retry(monkeypatch, provider, method, fallback_enabled):
    monkeypatch.setattr(factory.settings, "fallback_enabled", fallback_enabled)
    monkeypatch.setattr(factory.time, "sleep", lambda _: None)
    local = MagicMock(api_key=None, last_usage={}, last_raw_response="", last_key_used=None)
    call = getattr(local, method)
    failures = 1 if fallback_enabled else 3
    call.side_effect = [RuntimeError("Local server connection failed") for _ in range(failures)] + ["recovered"]
    client = factory.DynamicLLMClient()
    monkeypatch.setattr(client, "get_fallback_chain", lambda: [(provider, "local-model", local)])
    kwargs = {"response_model": RequirementMatch} if method == "generate_structured" else {}

    with pytest.raises(RuntimeError, match="Local server connection failed"):
        getattr(client, method)("Evaluate", **kwargs)
    assert not factory.is_model_in_cooldown(provider, "local-model")
    assert not factory.get_active_cooldown_statuses()
    assert getattr(client, method)("Evaluate", **kwargs) == "recovered"
    assert call.call_count == failures + 1


@pytest.mark.parametrize("provider", ["ollama", "lmstudio"])
@pytest.mark.parametrize("method", ["generate_text", "generate_structured"])
def test_local_model_retries_same_request_when_failover_disabled(monkeypatch, provider, method):
    monkeypatch.setattr(factory.settings, "fallback_enabled", False)
    delays = []
    monkeypatch.setattr(factory.time, "sleep", delays.append)
    local = MagicMock(api_key=None, last_usage={}, last_raw_response="", last_key_used=None)
    call = getattr(local, method)
    call.side_effect = [TimeoutError("local timeout"), "recovered"]
    client = factory.DynamicLLMClient()
    monkeypatch.setattr(client, "get_fallback_chain", lambda: [(provider, "local-model", local)])
    kwargs = {"response_model": RequirementMatch} if method == "generate_structured" else {}
    assert getattr(client, method)("Evaluate", **kwargs) == "recovered"
    assert call.call_count == 2
    assert call.call_args_list[0] == call.call_args_list[1]
    assert delays == [1]


def test_api_provider_is_not_retried_when_failover_disabled(monkeypatch):
    monkeypatch.setattr(factory.settings, "fallback_enabled", False)
    remote = MagicMock(api_key="synthetic", last_raw_response="")
    remote.generate_text.side_effect = RuntimeError("remote failure")
    client = factory.DynamicLLMClient()
    monkeypatch.setattr(client, "get_fallback_chain", lambda: [("groq", "remote", remote)])
    with pytest.raises(RuntimeError):
        client.generate_text("Evaluate")
    assert remote.generate_text.call_count == 1


def test_ollama_uses_native_thinking_control_without_assistant_prefill(monkeypatch):
    monkeypatch.setattr(factory.settings, "local_thinking_enabled", False)
    local = factory.OllamaClient.__new__(factory.OllamaClient)
    local.model = "local-model"
    local.client = MagicMock()
    local.client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content='{"answer":"ok"}'))
    local._record_telemetry = MagicMock()
    from pydantic import BaseModel
    class Answer(BaseModel):
        answer: str
    assert local.generate_structured("Evaluate", Answer).answer == "ok"
    request = local.client.chat.call_args.kwargs
    assert request["think"] is False
    assert [message["role"] for message in request["messages"]] == ["system", "user"]


def test_local_gpu_load_uses_max_and_reports_failure(monkeypatch):
    from backend.services import local_model_service as module
    service = module.LocalModelService()
    monkeypatch.setattr(service, "get_gpu_telemetry", lambda: {"profile": {"is_low_end": True}})
    monkeypatch.setattr(service, "_find_lms_cli", lambda: "lms")
    monkeypatch.setattr(service, "start_lmstudio_server", lambda: {"success": True})
    run = MagicMock(return_value=SimpleNamespace(returncode=1, stdout=b"", stderr=b"not enough GPU memory"))
    monkeypatch.setattr(module.subprocess, "run", run)
    result = service.load_model("lmstudio", "model", context_window=4096)
    assert not result["success"]
    assert "not enough GPU memory" in result["error"]
    command = run.call_args.args[0]
    assert command[command.index("--gpu") + 1] == "max"
    assert run.call_count == 1


def test_ollama_inference_requests_all_gpu_layers(monkeypatch):
    monkeypatch.setattr(factory.settings, "local_gpu_layers", 0)
    local = factory.OllamaClient.__new__(factory.OllamaClient)
    assert local._get_execution_options()["num_gpu"] == 999


def test_stale_local_cooldown_is_ignored():
    factory._MODEL_COOLDOWNS[("ollama", "local-model", None)] = time.time() + 30
    assert not factory.is_model_in_cooldown("ollama", "local-model")
    assert not factory.get_active_cooldown_statuses()


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
