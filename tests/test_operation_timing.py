"""Workflow timings survive sessions and distinguish wall time, reuse and failures."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.db.models import OperationTimingModel as Timing
from backend.db.repository import DatabaseRepository
from backend.db.session import async_session_scope
from backend.services.operation_timing import measure, operation_statistics, record_operation, recover_interrupted_timings


@pytest.mark.asyncio
async def test_nested_parallel_timings_keep_batch_identity_and_elapsed_time():
    batch_id = str(uuid4())
    async def child(name):
        async with measure("cv_parse", label=name):
            await asyncio.sleep(.01)
    async with measure("batch_parse", batch_id=batch_id, item_count=2) as parent:
        await asyncio.gather(child("first.txt"), child("second.txt"))
    result = await operation_statistics(batch_id=batch_id)
    assert result["total"] == 3
    children = [row for row in result["history"] if row["operation"] == "cv_parse"]
    assert {row["label"] for row in children} == {"first.txt", "second.txt"}
    assert all(row["parent_id"] == parent["id"] and row["batch_id"] == batch_id for row in children)
    assert all(row["duration_ms"] > 0 and row["finished_at"] for row in children)
    # The batch has its own actual measurement, never the sum of child durations.
    assert parent["duration_ms"] is not None and parent["completed_count"] == 2


@pytest.mark.asyncio
async def test_elapsed_seconds_are_saved_as_milliseconds(monkeypatch):
    from backend.services import operation_timing
    ticks = iter([100, 100.25])
    monkeypatch.setattr(operation_timing, "_clock", lambda: next(ticks))
    batch_id = str(uuid4())
    async with measure("cv_parse", batch_id=batch_id):
        pass
    assert (await operation_statistics(batch_id=batch_id))["history"][0]["duration_ms"] == 250


@pytest.mark.asyncio
async def test_combined_parsing_and_screening_does_not_bias_parse_only_averages():
    batch_id = str(uuid4())
    @record_operation(lambda a: "cv_processing" if a["screen"] else "cv_parse", lambda a: {"batch_id": batch_id})
    async def action(screen=False):
        return {"status": "COMPLETED"}
    await action()
    await action(True)
    result = await operation_statistics(batch_id=batch_id, operation="cv_parse")
    assert result["total"] == 1 and len(result["summary"]) == 1


@pytest.mark.asyncio
async def test_provider_cooldown_is_deferred_not_a_failed_cv_measurement():
    from backend.agents.llm_factory import LLMProvidersCoolingDownError
    batch_id = str(uuid4())
    with pytest.raises(LLMProvidersCoolingDownError):
        async with measure("cv_parse", batch_id=batch_id):
            raise LLMProvidersCoolingDownError(5)
    result = await operation_statistics(batch_id=batch_id)
    assert result["history"][0]["status"] == "deferred"
    assert result["summary"][0]["failed"] == 0 and result["summary"][0]["deferred"] == 1
    assert result["summary"][0]["success_rate"] is None


@pytest.mark.asyncio
async def test_summary_excludes_failures_reuse_and_running_from_duration_average():
    batch_id = str(uuid4())
    now = datetime.now(timezone.utc)
    async with async_session_scope() as db:
        for status, duration, cached in [("completed", 2000, False), ("completed", 4000, False),
                                         ("completed", 1, True), ("failed", 90000, False), ("running", None, False)]:
            db.add(Timing(id=str(uuid4()), operation="cv_parse", label="CV", status=status,
                batch_id=batch_id, started_at=now, duration_ms=duration, cached=cached,
                item_count=1, completed_count=int(status == "completed"), failed_count=int(status == "failed")))
        await db.commit()
    result = await operation_statistics(batch_id=batch_id, limit=2)
    item = result["summary"][0]
    assert item["average_ms"] == 3000 and item["min_ms"] == 2000 and item["max_ms"] == 4000
    assert item["items_per_minute"] == 20 and item["success_rate"] == 75
    assert item["failed"] == item["running"] == item["cached"] == 1
    assert result["has_more"] and len(result["history"]) == 2
    next_page = await operation_statistics(batch_id=batch_id, limit=2, offset=2)
    assert not ({row["id"] for row in result["history"]} & {row["id"] for row in next_page["history"]})


@pytest.mark.asyncio
async def test_failures_cancellation_and_returned_failures_are_saved():
    batch_id = str(uuid4())
    @record_operation("cv_parse", lambda a: {"batch_id": batch_id})
    async def failed():
        return {"status": "FAILED"}
    await failed()
    with pytest.raises(ValueError):
        async with measure("cv_parse", batch_id=batch_id):
            raise ValueError("Unreadable")
    with pytest.raises(asyncio.CancelledError):
        async with measure("cv_parse", batch_id=batch_id):
            raise asyncio.CancelledError()
    data = await operation_statistics(batch_id=batch_id)
    assert data["summary"][0]["failed"] == 2 and data["summary"][0]["cancelled"] == 1
    assert all(row["finished_at"] and row["duration_ms"] is not None for row in data["history"])


@pytest.mark.asyncio
async def test_filters_and_restart_do_not_invent_completion_times():
    job_id, batch_id = str(uuid4()), str(uuid4())
    async with async_session_scope() as db:
        db.add(Timing(id=str(uuid4()), operation="screening_run", label="Old", status="running", job_id=job_id,
                      batch_id=batch_id, started_at=datetime.now(timezone.utc) - timedelta(days=10)))
        await db.commit()
    await recover_interrupted_timings()
    result = await operation_statistics(job_id=job_id, batch_id=batch_id)
    assert result["history"][0]["status"] == "interrupted"
    assert result["history"][0]["duration_ms"] is None and result["history"][0]["finished_at"] is None
    assert (await operation_statistics(job_id=job_id, days=7))["total"] == 0
    assert (await operation_statistics(job_id=str(uuid4())))["total"] == 0


@pytest.mark.asyncio
async def test_batch_and_each_cv_are_instrumented_without_provider_calls(monkeypatch):
    from backend.api import routes
    from backend.services.batch_processor import BatchProcessorService
    from backend.services import cv_library
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(2, batch_id=batch_id)
    async def store(filename, content):
        return SimpleNamespace(id=str(uuid4()), deleted_at=None, candidate_id=None), False
    async def attach(*args):
        pass
    async def parse(self, content, filename, job_description=None):
        return {"status": "COMPLETED" if filename == "good.txt" else "FAILED", "filename": filename}
    monkeypatch.setattr(cv_library, "store_file", store)
    monkeypatch.setattr(cv_library, "attach_candidate", attach)
    monkeypatch.setattr(BatchProcessorService, "_process_single_candidate", parse)
    await routes._batch_processor.execute_parse_batch(batch_id, [("good.txt", b"a"), ("bad.txt", b"b")], 1)
    result = await operation_statistics(batch_id=batch_id)
    assert result["total"] == 3
    parent = next(row for row in result["history"] if row["operation"] == "batch_parse")
    assert parent["status"] == "partial" and parent["completed_count"] == parent["failed_count"] == 1
    assert {row["label"] for row in result["history"] if row["operation"] == "cv_parse"} == {"good.txt", "bad.txt"}


def test_statistics_api_is_bounded_and_protected(monkeypatch):
    from backend.main import app
    from backend.config import settings
    client = TestClient(app)
    assert client.get("/api/v1/screening/statistics/actions?limit=101").status_code == 422
    assert client.get("/api/v1/screening/statistics/actions?offset=-1").status_code == 422
    assert client.get("/api/v1/screening/statistics/actions").status_code == 200
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_demo_mode", False)
    assert client.get("/api/v1/screening/statistics/actions").status_code == 401
