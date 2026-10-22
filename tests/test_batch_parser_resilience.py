"""Reproductions of CV truncation, JSON rejection and cascading batch interruption."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from backend.agents import llm_factory as factory
from backend.schemas.cv import ParsedCV
from backend.schemas.match import RequirementMatch


@pytest.fixture(autouse=True)
def isolated_breakers(monkeypatch):
    monkeypatch.setattr(factory, "_MODEL_COOLDOWNS", {})
    monkeypatch.setattr(factory, "_GROQ_NEXT_CALL", {})
    monkeypatch.setattr(factory.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(factory.settings, "fallback_enabled", True)
    monkeypatch.setattr(factory.settings, "llm_provider", "groq")
    monkeypatch.setattr(factory.settings, "groq_model", "qwen/qwen3.8-27b")


def response(content='{"contact_info":{"full_name":"Synthetic Person"},"skills":["Python"]}', finish="stop"):
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))])


class JsonRejected(Exception):
    status_code = 400

    def __init__(self, generated="{incomplete"):
        super().__init__("Failed to validate JSON. json_validate_failed")
        self.body = {"error": {"failed_generation": generated}}


def groq(model="qwen/qwen3.8-27b"):
    client = factory.GroqClient(api_key="synthetic-key", model=model, compatibility_mode="auto")
    client.client = MagicMock()
    client.secondary_client = None
    client.tertiary_client = None
    return client


def test_full_profile_budget_is_not_limited_by_short_decision_budget(monkeypatch):
    monkeypatch.setattr(factory.settings, "groq_max_output_tokens", 800)
    monkeypatch.setattr(factory.settings, "groq_parser_max_output_tokens", 8192)
    client = groq()
    client.client.chat.completions.create.return_value = response()
    profile = client.generate_structured("Synthetic CV", ParsedCV)
    assert profile.skills == ["Python"]
    options = client.client.chat.completions.create.call_args.kwargs
    assert options["max_tokens"] == 8192
    assert options["reasoning_effort"] == "none"
    assert options["reasoning_format"] == "hidden"
    assert '"raw_text":' not in options["messages"][0]["content"]
    assert '"audit_metadata":' not in options["messages"][0]["content"]
    assert '"benchmark_annotations":' not in options["messages"][0]["content"]
    client.client.chat.completions.create.return_value = response('{"requirement_id":"r","status":"met","score":1,"reasoning":"Documented"}')
    client.generate_structured("Criterion", RequirementMatch)
    assert client.client.chat.completions.create.call_args.kwargs["max_tokens"] == 700


def test_gpt_oss_uses_its_supported_reasoning_parameters():
    client = groq("openai/gpt-oss-20b")
    client.client.chat.completions.create.return_value = response()
    client.generate_structured("Synthetic CV", ParsedCV)
    options = client.client.chat.completions.create.call_args.kwargs
    assert options["reasoning_effort"] == "low"
    assert options["include_reasoning"] is False
    assert "reasoning_format" not in options


def test_json_rejection_retries_once_without_json_mode():
    client = groq()
    client.client.chat.completions.create.side_effect = [JsonRejected(), response()]
    assert client.generate_structured("Synthetic CV", ParsedCV).skills == ["Python"]
    calls = client.client.chat.completions.create.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls[1].kwargs


def test_complete_rejected_generation_is_validated_without_another_request():
    client = groq()
    generated = '{"contact_info":{"full_name":"Synthetic Person"},"skills":["SQL"]}'
    client.client.chat.completions.create.side_effect = JsonRejected(generated)
    assert client.generate_structured("Synthetic CV", ParsedCV).skills == ["SQL"]
    assert client.client.chat.completions.create.call_count == 1
    assert client.last_raw_response == generated


def test_truncation_never_accepts_a_partial_profile_or_retries_same_budget():
    client = groq()
    client.client.chat.completions.create.return_value = response(finish="length")
    with pytest.raises(factory.StructuredOutputTruncatedError):
        client.generate_structured("Synthetic CV", ParsedCV)
    assert client.client.chat.completions.create.call_count == 1


@pytest.mark.parametrize("failure", [factory.StructuredOutputTruncatedError("truncated"), ValueError("invalid JSON"), JsonRejected()])
def test_bad_document_output_does_not_disable_the_provider(failure):
    factory.record_model_failure("groq", "model", failure, "key")
    assert not factory.is_model_in_cooldown("groq", "model", "key")


def test_failed_model_is_skipped_across_keys_for_this_document_only(monkeypatch):
    first, same_model, fallback = [MagicMock(api_key=key, last_usage={}, last_raw_response="", last_key_used="primary") for key in ["one", "two", "three"]]
    first.generate_structured.side_effect = factory.StructuredOutputTruncatedError("truncated")
    fallback.generate_structured.return_value = ParsedCV(skills=["Python"])
    client = factory.DynamicLLMClient()
    monkeypatch.setattr(client, "get_fallback_chain", lambda: [("groq", "small", first), ("groq", "small", same_model), ("groq", "large", fallback)])
    assert client.generate_structured("Synthetic CV", ParsedCV).skills == ["Python"]
    same_model.generate_structured.assert_not_called()
    assert not factory.is_model_in_cooldown("groq", "small", "one")
    # The next CV is eligible for the primary model again.
    first.generate_structured.side_effect = None
    first.generate_structured.return_value = ParsedCV(skills=["SQL"])
    assert client.generate_structured("Another synthetic CV", ParsedCV).skills == ["SQL"]


@pytest.mark.asyncio
async def test_schema_failure_affects_one_cv_and_does_not_interrupt_the_queue(monkeypatch):
    from backend.api import routes
    from backend.db.repository import DatabaseRepository
    from backend.services.batch_processor import BatchProcessorService

    calls = []
    async def process(self, content, filename, job_description=None):
        calls.append(filename)
        if filename == "bad.txt":
            raise ValueError("Incomplete profile JSON")
        return {"filename": filename, "status": "COMPLETED", "candidate_id": str(uuid4())}

    monkeypatch.setattr(BatchProcessorService, "process_single_candidate", process)
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(3, batch_id=batch_id)
    await routes._batch_processor.execute_parse_batch(batch_id, [(name, str(uuid4()).encode()) for name in ["first.txt", "bad.txt", "last.txt"]], 1)
    batch = await DatabaseRepository.get_batch_job(batch_id)
    assert calls == ["first.txt", "bad.txt", "last.txt"]
    assert batch.status == "PARTIAL" and batch.processed_files == 2 and batch.failed_files == 1


@pytest.mark.asyncio
async def test_long_cooldown_uses_the_wait_budget_instead_of_interrupting_immediately(monkeypatch):
    from backend.api import routes
    from backend.db.repository import DatabaseRepository
    from backend.services import batch_processor

    clock, waits = [0.0], []
    async def unavailable(*args, **kwargs):
        raise factory.LLMProvidersCoolingDownError(60)
    async def wait(seconds):
        waits.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr(batch_processor, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(batch_processor, "_provider_delay", wait)
    monkeypatch.setattr(batch_processor.BatchProcessorService, "process_single_candidate", unavailable)
    monkeypatch.setattr(factory.settings, "parser_provider_wait_seconds", 2)
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(1, batch_id=batch_id)
    await routes._batch_processor.execute_parse_batch(batch_id, [("waiting.txt", str(uuid4()).encode())], 1)
    assert waits == [2]
    batch = await DatabaseRepository.get_batch_job(batch_id)
    assert batch.status == "INTERRUPTED" and batch.failed_files == 0


@pytest.mark.asyncio
async def test_waiting_batch_can_be_cancelled(monkeypatch):
    from backend.api import routes
    from backend.db.repository import DatabaseRepository
    from backend.services import batch_processor

    waiting = asyncio.Event()
    async def unavailable(*args, **kwargs):
        raise factory.LLMProvidersCoolingDownError(5)
    async def wait(seconds):
        waiting.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(batch_processor, "_provider_delay", wait)
    monkeypatch.setattr(batch_processor.BatchProcessorService, "process_single_candidate", unavailable)
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(1, batch_id=batch_id)
    task = asyncio.create_task(routes._batch_processor.execute_parse_batch(batch_id, [("cancel.txt", str(uuid4()).encode())], 1))
    await asyncio.wait_for(waiting.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    batch = await DatabaseRepository.get_batch_job(batch_id)
    assert batch.status == "CANCELLED" and batch.failed_files == 0
