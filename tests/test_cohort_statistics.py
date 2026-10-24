from uuid import uuid4
import pytest
from backend.db.models import ScreeningRunModel, AuditLogModel
from backend.db.session import async_session_scope
from backend.services.cohort_statistics import screening_statistics
from backend.services.operation_timing import measure


@pytest.mark.asyncio
async def test_cohorts_include_historical_runs_and_deduplicate_live_calls(monkeypatch):
    from backend.services.action_logger import action_logger
    run_id, job_id, call_id = (str(uuid4()) for _ in range(3))
    call = {"id": call_id, "tokens": {"prompt": 100, "completion": 25, "total": 125}}
    monkeypatch.setattr(action_logger, "get_logs", lambda **kwargs: [call] if kwargs.get("run_id") == run_id else [])
    async with async_session_scope() as db:
        db.add(ScreeningRunModel(id=run_id, job_id=job_id, payload={
            "job": {"title": "Engineer"}, "status": "completed", "candidate_ids": ["a", "b"],
            "rows": [{"deep_status": "completed"}, {"deep_status": "not_selected"}],
            "pre_screening_ms": 150, "deep_evaluation_ms": 800}))
        db.add(AuditLogModel(id=call_id, entity_type="screening_run", entity_id=run_id,
                            action="model_call", details_json=call))
        await db.commit()
    async with measure("screening_run", run_id=run_id, job_id=job_id):
        pass
    result = await screening_statistics(job_id=job_id)
    row = result["history"][0]
    assert result["total"] == 1
    assert row["candidate_count"] == 2 and row["evaluated_count"] == 1
    assert row["pre_screening_ms"] == 150 and row["deep_evaluation_ms"] == 800
    assert row["total_ms"] is not None
    assert row["tokens"] == {"input": 100, "output": 25, "total": 125}
    assert row["model_calls"] == 1
    assert not (await screening_statistics(job_id=str(uuid4())))["history"]
    assert not (await screening_statistics(job_id=job_id, offset=25))["history"]


@pytest.mark.asyncio
async def test_missing_historical_measurements_are_not_fabricated():
    run_id, job_id = str(uuid4()), str(uuid4())
    async with async_session_scope() as db:
        db.add(ScreeningRunModel(id=run_id, job_id=job_id, payload={"status": "completed", "rows": []}))
        await db.commit()
    row = (await screening_statistics(job_id=job_id))["history"][0]
    assert row["tokens"] is None
    assert row["total_ms"] is None
    assert row["pre_screening_ms"] is None
    assert row["deep_evaluation_ms"] is None
