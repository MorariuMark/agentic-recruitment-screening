from backend.services.parsing_timing import parsing_statistics


def test_averages_exclude_failed_cached_missing_and_negative_timings():
    good = {"status": "COMPLETED", "started_at": "2026-10-20T10:00:00+00:00",
            "finished_at": "2026-10-20T10:00:02+00:00"}
    result = parsing_statistics([None, {"files": [good, {**good, "finished_at": "2026-10-20T10:00:04+00:00"},
        {**good, "status": "FAILED"}, {**good, "duplicate_removed": True},
        {"status": "COMPLETED"}, {**good, "finished_at": "2026-10-20T09:00:00+00:00"}]}])
    assert result["sample_count"] == 2
    assert result["average_ms"] == 3000
    assert [row["duration_ms"] for row in result["estimates"]] == [3000, 30000, 75000, 150000, 300000]


def test_empty_statistics_do_not_invent_timings():
    result = parsing_statistics([])
    assert result["sample_count"] == 0 and result["average_ms"] is None
    assert all(row["duration_ms"] is None for row in result["estimates"])


import pytest
from uuid import uuid4
from backend.db.repository import DatabaseRepository
from backend.api.routes import get_batch_job_status


@pytest.mark.asyncio
async def test_batch_timer_starts_and_freezes_on_completion_and_cancellation():
    for terminal in ("COMPLETED", "CANCELLED"):
        batch_id = uuid4()
        await DatabaseRepository.create_batch_job(1, batch_id=batch_id)
        await DatabaseRepository.initialize_batch_files(batch_id, ["timer.txt"], 1)
        active = await get_batch_job_status(batch_id)
        assert active.started_at and active.finished_at is None
        await DatabaseRepository.update_batch_file(batch_id, "0", "Parsing")
        if terminal == "COMPLETED":
            await DatabaseRepository.update_batch_progress(batch_id, {"file_id": "0", "status": "COMPLETED", "filename": "timer.txt"})
        else:
            await DatabaseRepository.finish_batch_files(batch_id, terminal)
        finished = await get_batch_job_status(batch_id)
        assert finished.started_at == active.started_at
        assert finished.finished_at and finished.status == terminal
        again = await get_batch_job_status(batch_id)
        assert again.finished_at == finished.finished_at
