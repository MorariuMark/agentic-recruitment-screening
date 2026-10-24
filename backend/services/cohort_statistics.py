"""Run-scoped durable screening statistics, including retry model calls."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from backend.db.models import ScreeningRunModel, OperationTimingModel, AuditLogModel
from backend.db.session import async_session_scope


async def screening_statistics(*, job_id=None, days=0, limit=25, offset=0):
    from backend.services.action_logger import action_logger
    filters = []
    if job_id:
        filters.append(ScreeningRunModel.job_id == str(job_id))
    if days:
        filters.append(ScreeningRunModel.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    async with async_session_scope() as db:
        total = await db.scalar(select(func.count()).select_from(ScreeningRunModel).where(*filters))
        runs = (await db.scalars(select(ScreeningRunModel).where(*filters).order_by(
            ScreeningRunModel.created_at.desc(), ScreeningRunModel.id.desc()).offset(offset).limit(limit))).all()
        ids = [run.id for run in runs]
        timings = (await db.scalars(select(OperationTimingModel).where(OperationTimingModel.run_id.in_(ids)))).all() if ids else []
        logs = (await db.scalars(select(AuditLogModel).where(AuditLogModel.entity_type == "screening_run",
            AuditLogModel.entity_id.in_(ids), AuditLogModel.action == "model_call"))).all() if ids else []
    history = []
    for run in runs:
        payload = run.payload
        rows = payload.get("rows", [])
        measured = [t for t in timings if t.run_id == run.id]
        def elapsed(operation):
            values = [t for t in measured if t.operation == operation]
            if not values:
                return None
            return sum(t.duration_ms if t.duration_ms is not None else max(0, (
                datetime.now(timezone.utc) - t.started_at.replace(tzinfo=timezone.utc)).total_seconds() * 1000) for t in values)
        calls = {entry.id: entry.details_json for entry in logs if entry.entity_id == run.id}
        calls.update({entry["id"]: entry for entry in action_logger.get_logs(limit=0, run_id=run.id)})
        tokens = None
        if calls:
            tokens = {key: sum((entry.get("tokens") or {}).get(field, 0) or 0 for entry in calls.values())
                      for key, field in (("input", "prompt"), ("output", "completion"), ("total", "total"))}
        pre = payload.get("pre_screening_ms", elapsed("ranking"))
        deep = payload.get("deep_evaluation_ms", payload.get("diagnostics", {}).get("timings_ms", {}).get("deep_evaluation"))
        history.append(dict(run_id=run.id, job_id=run.job_id, job_title=payload.get("job", {}).get("title", "Job"),
            status=payload.get("status", "unknown"), started_at=payload.get("started_at"),
            candidate_count=len(payload.get("candidate_ids", rows)),
            evaluated_count=sum(row.get("deep_status") == "completed" for row in rows),
            pre_screening_ms=pre, deep_evaluation_ms=deep,
            total_ms=elapsed("screening_run"), tokens=tokens, model_calls=len(calls)))
    return dict(history=history, total=total, has_more=offset + len(history) < total)
