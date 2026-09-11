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
