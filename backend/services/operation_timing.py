"""Persist actual action elapsed time; child durations never substitute for wall time."""
import asyncio
import inspect
import logging
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import uuid4

from sqlalchemy import case, func, select, update

from backend.db.models import OperationTimingModel as Timing
from backend.db.session import async_session_scope

logger = logging.getLogger(__name__)
_clock = time.perf_counter
_current = ContextVar("operation_timing_context", default={})
LABELS = {
    "cv_parse": "CV parsing", "batch_parse": "CV batch parsing",
    "batch_screening": "CV batch parsing and screening", "screening_run": "Job screening run",
    "candidate_screening": "Candidate evaluation", "ranking": "Candidate ranking",
    "job_extraction": "Job description extraction", "interview_generation": "Interview generation",
    "candidate_comparison": "Candidate comparison",
    "cv_import": "CV library import", "shortlist_creation": "Comparison shortlist",
    "recruiter_review": "Recruiter decision",
    "cv_processing": "CV parsing and evaluation",
}


def mark_reused_profile():
    """Reuse remains auditable without distorting actual parsing averages."""
    if _current.get():
        _current.get()["cached"] = True


async def _save(values, initial=False):
    # Measurement failures must not change recruitment outcomes.
    try:
        async with async_session_scope() as db:
            if initial:
                db.add(Timing(**values))
            else:
                record = await db.get(Timing, values["id"])
                if record:
                    for key, value in values.items():
                        setattr(record, key, value)
            await db.commit()
    except Exception:
        logger.exception("Could not persist operation timing %s", values.get("id"))


@asynccontextmanager
async def measure(operation, **metadata):
    parent = _current.get()
    values = dict(id=str(uuid4()), operation=operation, label=LABELS.get(operation, operation),
                  status="running", started_at=datetime.now(timezone.utc), item_count=1,
                  completed_count=0, failed_count=0, cached=False,
                  parent_id=parent.get("id"),
                  **{key: parent[key] for key in ("batch_id", "run_id", "job_id") if parent.get(key)})
    values.update({key: str(value) if key.endswith("_id") else value
                   for key, value in metadata.items() if value is not None})
    values["label"] = values["label"][:300]
    await _save(values, initial=True)
    token = _current.set(values)
    started = _clock()
    try:
        yield values
        if values["status"] == "running":
            values.update(status="completed", completed_count=values["item_count"])
    except asyncio.CancelledError:
        values["status"] = "cancelled"
        raise
    except BaseException as error:
        if getattr(error, "retryable", False):
            values.update(status="deferred", failed_count=0)
        else:
            values.update(status="failed", failed_count=max(1, values["item_count"] - values["completed_count"]))
        raise
    finally:
        values.update(finished_at=datetime.now(timezone.utc), duration_ms=round(max(0, _clock() - started) * 1000, 3))
        _current.reset(token)
        await _save(values)


def record_operation(operation, describe=None):
    """Instrument async business actions, including handled failures and cached CVs."""
    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            action = operation(bound.arguments) if callable(operation) else operation
            metadata = describe(bound.arguments) if describe else {}
            evaluated_ids = None
            if action == "screening_run" and bound.arguments["payload"].get("rows"):
                payload = bound.arguments["payload"]
                selected = set(payload.get("evaluation_candidate_ids", payload.get("deep_candidate_ids", [])))
                evaluated_ids = {row["candidate_id"] for row in payload["rows"]
                                 if row["candidate_id"] in selected and row.get("deep_status") != "completed"}
                metadata["item_count"] = len(evaluated_ids)
            async with measure(action, **metadata) as timing:
                result = await function(*args, **kwargs)
                try:
                    if isinstance(result, dict):
                        timing["cached"] = bool(result.get("duplicate_removed"))
                        if result.get("status") == "FAILED":
                            timing.update(status="failed", failed_count=1)
                        if result.get("candidate_id"):
                            timing["candidate_id"] = str(result["candidate_id"])
                        if result.get("job_id"):
                            timing["job_id"] = str(result["job_id"])
                    elif getattr(result, "candidate_id", None):
                        timing["candidate_id"] = str(result.candidate_id)
                    if action == "job_extraction" and getattr(result, "job_description", None):
                        timing["job_id"] = str(result.job_description.id)
                    if action in ("batch_parse", "batch_screening"):
                        from backend.db.repository import DatabaseRepository
                        record = await DatabaseRepository.get_batch_job(timing["batch_id"])
                        if record:
                            match_failures = sum(bool(row.get("match_error")) for row in (record.results_json or [])) if action == "batch_screening" else 0
                            completed = max(0, record.processed_files - match_failures)
                            failed = record.failed_files + match_failures
                            timing.update(completed_count=completed, failed_count=failed,
                                          status=("partial" if completed else "failed") if failed else "completed")
                            if record.status in ("FAILED", "CANCELLED", "INTERRUPTED"):
                                timing["status"] = record.status.lower()
                            elif record.processed_files + record.failed_files < record.total_files:
                                timing["status"] = "failed"
                    if action == "screening_run":
                        from backend.db.models import ScreeningRunModel
                        async with async_session_scope() as db:
                            run = await db.get(ScreeningRunModel, timing["run_id"])
                            if run:
                                rows = run.payload.get("rows", [])
                                if evaluated_ids is not None:
                                    rows = [row for row in rows if row["candidate_id"] in evaluated_ids]
                                failures = sum(row.get("deep_status") == "failed" for row in rows)
                                deferred = sum(row.get("deep_status") == "deferred" for row in rows)
                                status = "deferred" if deferred == len(rows) and rows else run.payload["status"]
                                timing.update(status=status, completed_count=len(rows) - failures - deferred,
                                              failed_count=failures)
                except Exception:
                    logger.exception("Could not enrich operation timing %s", timing["id"])
                return result
        return wrapped
    return decorate


async def recover_interrupted_timings():
    """A restart proves interruption, but cannot establish an exact finish time."""
    async with async_session_scope() as db:
        await db.execute(update(Timing).where(Timing.status == "running").values(status="interrupted"))
        await db.commit()


def filters(days=0, operation=None, job_id=None, batch_id=None, run_id=None):
    clauses = []
    if days:
        clauses.append(Timing.started_at >= datetime.now(timezone.utc) - timedelta(days=days))
    for field, value in ((Timing.operation, operation), (Timing.job_id, job_id), (Timing.batch_id, batch_id), (Timing.run_id, run_id)):
        if value:
            clauses.append(field == str(value))
    return clauses


async def operation_statistics(*, days=0, operation=None, job_id=None, batch_id=None, run_id=None, limit=25, offset=0):
    clauses = filters(days, operation, job_id, batch_id, run_id)
    measured = (Timing.status == "completed") & (Timing.cached.is_(False)) & Timing.duration_ms.is_not(None)
    async with async_session_scope() as db:
        summary = await db.execute(select(Timing.operation,
            func.count().label("count"),
            *[func.sum(case((Timing.status == status, 1), else_=0)).label(status)
              for status in ("completed", "failed", "partial", "cancelled", "running", "interrupted", "deferred")],
            func.sum(case((Timing.cached.is_(True), 1), else_=0)).label("cached"),
            func.avg(case((measured, Timing.duration_ms))).label("average_ms"),
            func.min(case((measured, Timing.duration_ms))).label("min_ms"),
            func.max(case((measured, Timing.duration_ms))).label("max_ms"),
            func.sum(case((measured, Timing.duration_ms), else_=0)).label("total_ms"),
            func.sum(case((measured, Timing.completed_count), else_=0)).label("items")
        ).where(*clauses).group_by(Timing.operation).order_by(Timing.operation))
        groups = []
        for row in summary.mappings():
            item = dict(row)
            item["label"] = LABELS.get(item["operation"], item["operation"])
            terminal = item["count"] - item["running"] - item["deferred"]
            item["success_rate"] = item["completed"] / terminal * 100 if terminal else None
            item["items_per_minute"] = item["items"] * 60000 / item["total_ms"] if item["total_ms"] else None
            groups.append(item)
        total = await db.scalar(select(func.count()).select_from(Timing).where(*clauses))
        rows = (await db.scalars(select(Timing).where(*clauses)
            .order_by(Timing.started_at.desc(), Timing.id.desc()).offset(offset).limit(limit))).all()
        def serialize(row):
            result = {column.name: getattr(row, column.name) for column in Timing.__table__.columns}
            for field in ("started_at", "finished_at"):
                value = result[field]
                result[field] = (value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value).isoformat() if value else None
            return result
        return {"summary": groups, "history": [serialize(row) for row in rows], "total": total,
                "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}
