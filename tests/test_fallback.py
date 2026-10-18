"""
tests/test_fallback.py
Unit tests verifying multi-tier automatic LLM fallback and failover resilience.
"""

from typing import Optional
import pytest
from pydantic import BaseModel

from backend.agents.llm_factory import (
    BaseLLMClient,
    DynamicLLMClient,
    get_last_fallback_event,
)


class MockResultSchema(BaseModel):
    name: str
    score: int
    summary: Optional[str] = None


def test_frozen_run_keeps_factory_targets_and_failover_when_shared_settings_change(monkeypatch):
    from backend.config import settings
    original = DynamicLLMClient.get_fallback_chain
    first = DummyClient(should_fail=True)
    second = DummyClient(text_response="Frozen fallback")
    monkeypatch.setattr(settings, "fallback_enabled", True)
    monkeypatch.setattr(DynamicLLMClient, "get_fallback_chain", lambda self: [("groq", "first", first), ("agnes", "second", second)])
    client = DynamicLLMClient()
    client.freeze_configuration()
    monkeypatch.setattr(DynamicLLMClient, "get_fallback_chain", original)
    monkeypatch.setattr(settings, "fallback_enabled", False)
    assert client.generate_text("Synthetic check") == "Frozen fallback"
    assert settings.fallback_enabled is False


class DummyClient(BaseLLMClient):
    def __init__(self, should_fail: bool = False, fail_message: str = "Rate limit 429", text_response: str = "OK"):
        self.should_fail = should_fail
        self.fail_message = fail_message
        self.text_response = text_response

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.1) -> str:
        if self.should_fail:
            raise RuntimeError(self.fail_message)
        return self.text_response

    def generate_structured(self, prompt: str, response_model, system_prompt: Optional[str] = None, temperature: float = 0.0):
        if self.should_fail:
            raise RuntimeError(self.fail_message)
        return response_model(name="Test Candidate", score=95, summary="Seamless fallback success")


def test_fallback_chain_construction():
    client = DynamicLLMClient()
    chain = client.get_fallback_chain()
    assert len(chain) >= 2, "Fallback chain must include primary plus at least one fallback candidate"
    prov, model, cli = chain[0]
    assert prov is not None and model is not None
    assert isinstance(cli, BaseLLMClient)


def test_text_generation_seamless_failover(monkeypatch):
    dyn = DynamicLLMClient()

    primary_failing = DummyClient(should_fail=True, fail_message="Groq 429 RateLimit: Daily TPM reached")
    secondary_ok = DummyClient(should_fail=False, text_response="Recovered seamlessly by NVIDIA NIM")

    mock_chain = [
        ("groq", "openai/gpt-oss-20b", primary_failing),
        ("nvidia_nim", "meta/llama-3.2-11b-vision-instruct", secondary_ok),
    ]
    monkeypatch.setattr(dyn, "get_fallback_chain", lambda: mock_chain)

    result = dyn.generate_text("Evaluate candidate experience.")
    assert result == "Recovered seamlessly by NVIDIA NIM"

    event = get_last_fallback_event()
    assert event is not None
    assert event["from_provider"] == "groq"
    assert event["to_provider"] == "nvidia_nim"
    assert "Daily TPM reached" in event["error"]

    from backend.config import settings
    assert settings.llm_provider == "nvidia_nim"
    assert settings.nvidia_nim_model == "meta/llama-3.2-11b-vision-instruct"


def test_structured_generation_seamless_failover(monkeypatch):
    dyn = DynamicLLMClient()

    primary_failing = DummyClient(should_fail=True, fail_message="Ollama connection dropped")
    secondary_ok = DummyClient(should_fail=False)

    mock_chain = [
        ("ollama", "qwen3.5:2b-q4_K_M", primary_failing),
        ("groq", "openai/gpt-oss-20b", secondary_ok),
    ]
    monkeypatch.setattr(dyn, "get_fallback_chain", lambda: mock_chain)

    parsed = dyn.generate_structured("Parse test input", response_model=MockResultSchema)
    assert isinstance(parsed, MockResultSchema)
    assert parsed.name == "Test Candidate"
    assert parsed.score == 95

    event = get_last_fallback_event()
    assert event["from_provider"] == "ollama"
    assert event["to_provider"] == "groq"

    from backend.config import settings
    assert settings.llm_provider == "groq"
    assert settings.groq_model == "openai/gpt-oss-20b"


def test_clear_last_fallback_event():
    from backend.agents.llm_factory import clear_last_fallback_event
    assert get_last_fallback_event() is not None
    clear_last_fallback_event()
    assert get_last_fallback_event() is None


def test_clear_fallback_api_endpoint():
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.agents.llm_factory import _LAST_FALLBACK_EVENT, get_last_fallback_event
    import backend.agents.llm_factory as llm_fac

    llm_fac._LAST_FALLBACK_EVENT = {"timestamp": 12345.0, "from_provider": "groq", "to_provider": "gemini"}
    assert get_last_fallback_event() is not None

    client = TestClient(app)
    res = client.post("/api/v1/settings/llm/clear-fallback")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert get_last_fallback_event() is None


def test_all_candidates_fail_raises_descriptive_error(monkeypatch):
    dyn = DynamicLLMClient()

    c1 = DummyClient(should_fail=True, fail_message="Primary failure")
    c2 = DummyClient(should_fail=True, fail_message="Secondary failure")

    mock_chain = [
        ("groq", "model1", c1),
        ("nvidia_nim", "model2", c2),
    ]
    monkeypatch.setattr(dyn, "get_fallback_chain", lambda: mock_chain)

    with pytest.raises(RuntimeError) as exc_info:
        dyn.generate_text("Prompt that will fail all")

    err_msg = str(exc_info.value)
    assert "All LLM models in fallback chain failed" in err_msg
    assert "groq:model1" in err_msg
    assert "nvidia_nim:model2" in err_msg


def test_groq_dual_key_failover(monkeypatch):
    from unittest.mock import MagicMock
    from backend.agents.llm_factory import GroqClient
    from backend.config import settings

    client = GroqClient(
        api_key="gsk_primary_test_key",
        secondary_api_key="gsk_secondary_test_key",
        model="qwen/qwen3.8-27b",
    )
    assert client.secondary_client is not None

    # Mock primary client to fail with 429 RateLimitError
    primary_mock = MagicMock()
    primary_mock.chat.completions.create.side_effect = RuntimeError("Rate limit 429: TPM exceeded")
    client.client = primary_mock

    # Mock secondary client to succeed
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content='{"name": "Secondary Candidate", "score": 98}'))]
    mock_resp.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    secondary_mock = MagicMock()
    secondary_mock.chat.completions.create.return_value = mock_resp
    client.secondary_client = secondary_mock

    # Test structured generation failover
    result = client.generate_structured("Evaluate", response_model=MockResultSchema)
    assert result.name == "Secondary Candidate"
    assert result.score == 98
    assert client.last_key_used == "secondary"
    assert primary_mock.chat.completions.create.called
    assert secondary_mock.chat.completions.create.called


def test_fallback_chain_prioritizes_qwen38_27b():
    from backend.config import settings
    settings.llm_provider = "groq"
    settings.groq_model = "qwen/qwen3.8-27b"

    dyn = DynamicLLMClient()
    chain = dyn.get_fallback_chain()
    assert len(chain) >= 2

    # Tier 1 must be qwen/qwen3.8-27b
    prov, mod, cli = chain[0]
    assert prov == "groq"
    assert mod == "qwen/qwen3.8-27b"


def test_groq_triple_key_failover(monkeypatch):
    from unittest.mock import MagicMock
    from backend.agents.llm_factory import GroqClient

    client = GroqClient(
        api_key="gsk_primary_test_key",
        secondary_api_key="gsk_secondary_test_key",
        tertiary_api_key="gsk_tertiary_test_key",
        model="qwen/qwen3.8-27b",
    )
    assert client.secondary_client is not None
    assert client.tertiary_client is not None

    # Mock primary and secondary to fail
    primary_mock = MagicMock()
    primary_mock.chat.completions.create.side_effect = RuntimeError("Rate limit 429: primary key exhausted")
    client.client = primary_mock

    secondary_mock = MagicMock()
    secondary_mock.chat.completions.create.side_effect = RuntimeError("Rate limit 429: secondary key exhausted")
    client.secondary_client = secondary_mock

    # Mock tertiary to succeed
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content='{"name": "Tertiary Candidate", "score": 99}'))]
    mock_resp.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    tertiary_mock = MagicMock()
    tertiary_mock.chat.completions.create.return_value = mock_resp
    client.tertiary_client = tertiary_mock

    result = client.generate_structured("Evaluate", response_model=MockResultSchema)
    assert result.name == "Tertiary Candidate"
    assert result.score == 99
    assert client.last_key_used == "tertiary"
    assert primary_mock.chat.completions.create.called
    assert secondary_mock.chat.completions.create.called
    assert tertiary_mock.chat.completions.create.called


def test_gemini_dual_key_failover(monkeypatch):
    from unittest.mock import MagicMock
    from backend.agents.llm_factory import GeminiClient

    client = GeminiClient(
        api_key="AQ.primary_test_key",
        secondary_api_key="AQ.secondary_test_key",
        model="gemini-flash-latest",
    )
    assert client.secondary_client is not None

    # Mock primary client to fail with 429 RateLimitError
    primary_mock = MagicMock()
    primary_mock.chat.completions.create.side_effect = RuntimeError("Rate limit 429: RESOURCE_EXHAUSTED")
    client.client = primary_mock

    # Mock secondary client to succeed
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content='{"name": "Gemini Backup Candidate", "score": 94}'))]
    mock_resp.usage = MagicMock(prompt_tokens=80, completion_tokens=40, total_tokens=120)
    secondary_mock = MagicMock()
    secondary_mock.chat.completions.create.return_value = mock_resp
    client.secondary_client = secondary_mock

    result = client.generate_structured("Evaluate candidate", response_model=MockResultSchema)
    assert result.name == "Gemini Backup Candidate"
    assert result.score == 94
    assert client.last_key_used == "secondary"
    assert primary_mock.chat.completions.create.called
    assert secondary_mock.chat.completions.create.called


def test_fallback_chain_switches_to_same_model_on_secondary_key(monkeypatch):
    from backend.config import settings
    settings.llm_provider = "gemini"
    settings.gemini_model = "gemini-flash-latest"
    settings.gemini_api_key = "AQ.key1"
    settings.gemini_secondary_api_key = "AQ.key2"

    dyn = DynamicLLMClient()
    chain = dyn.get_fallback_chain()

    # The first candidate should be gemini:gemini-flash-latest on key1
    assert chain[0][0] == "gemini"
    assert chain[0][1] == "gemini-flash-latest"
    assert getattr(chain[0][2], "api_key", None) == "AQ.key1"

    # The second candidate must be the SAME MODEL (gemini-flash-latest) on key2!
    assert chain[1][0] == "gemini"
    assert chain[1][1] == "gemini-flash-latest"
    assert getattr(chain[1][2], "api_key", None) == "AQ.key2"



