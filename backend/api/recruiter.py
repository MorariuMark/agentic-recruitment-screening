"""Recruiter workspace routes, reusing the existing agents, factory and repositories."""
import asyncio
import copy
import secrets
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Cookie, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from pydantic import Field
from sqlalchemy import func, select

from backend.api import routes as existing
from backend.agents.matching_agent import MatchingAgent
from backend.agents.llm_factory import DynamicLLMClient
from backend.config import settings
from backend.schemas.models_catalog import CATALOG_PROVIDERS
from backend.db.models import BatchJobModel, CandidateModel, InterviewPlanModel, JobRequisitionModel, MatchEvaluationModel, ScreeningRunModel, ScreeningFeatureCacheModel
from backend.db.repository import DatabaseRepository
from backend.db.session import async_session_scope
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription
from backend.schemas.screening import FastRankRequest, PreScreenRow, ReviewDecision, ShortlistRequest
from backend.services.pre_ranking import PreRankingEngine
from backend.services.hybrid_screening import HybridRankingEngine, feature_key, snapshot_hash
from backend.services.screening_reranker import get_reranker
from backend.services.screening_duplicates import candidate_name_key, evaluation_key

router = APIRouter(prefix="/api/v1", tags=["Recruiter workspace"])
_sessions: dict[str, tuple[str, float]] = {}
_run_lock = asyncio.Lock()
_screening_slots = asyncio.Semaphore(2)


@router.get("/screening/statistics")
async def statistics():
    """Read-only platform totals, independent of frontend list pagination."""
    async with async_session_scope() as db:
        totals = {}
        for key, model in [("candidates", CandidateModel), ("jobs", JobRequisitionModel),
                           ("screening_runs", ScreeningRunModel), ("evaluations", MatchEvaluationModel),
                           ("interview_plans", InterviewPlanModel)]:
            totals[key] = await db.scalar(select(func.count()).select_from(model))
        totals["cv_text_characters"] = await db.scalar(select(func.coalesce(func.sum(func.length(CandidateModel.sanitized_text)), 0)))
        batch = (await db.execute(select(func.coalesce(func.sum(BatchJobModel.total_files), 0),
            func.coalesce(func.sum(BatchJobModel.processed_files), 0),
            func.coalesce(func.sum(BatchJobModel.failed_files), 0)))).one()
        totals.update(batch_files=batch[0], batch_processed=batch[1], batch_failed=batch[2])
        from backend.services.token_tracker import token_tracker
        totals.update(token_tracker.get_processing_totals())
        recent = (await db.execute(select(ScreeningRunModel.id, ScreeningRunModel.payload["diagnostics"], ScreeningRunModel.payload["pipeline_version"])
            .order_by(ScreeningRunModel.created_at.desc(), ScreeningRunModel.id.desc()).limit(5))).all()
        totals["recent_screening"] = [{"run_id": run_id, "pipeline_version": version or "v1", **(diagnostics or {})} for run_id, diagnostics, version in recent]
        return totals


class LoginRequest(BaseModel):
    role: Literal["admin", "user"]
    password: str


@router.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    if not secrets.compare_digest(payload.password, "1234"):
        raise HTTPException(401, "Incorrect password. Try again.")
    now = time.time()
    for key, (_, expiry) in list(_sessions.items()):
        if expiry < now:
            _sessions.pop(key, None)
    token = secrets.token_urlsafe(32)
    _sessions[token] = (payload.role, now + 43200)
    response.set_cookie("atos_workspace", token, httponly=True, samesite="lax", max_age=43200)
    return {"role": payload.role}


@router.get("/auth/session")
async def session(atos_workspace: str | None = Cookie(None)):
    value = _sessions.get(atos_workspace or "")
    return {"role": value[0] if value and value[1] > time.time() else None}


@router.post("/auth/logout")
async def logout(response: Response, atos_workspace: str | None = Cookie(None)):
    _sessions.pop(atos_workspace or "", None)
    response.delete_cookie("atos_workspace")
    return {"status": "ok"}


@router.get("/screening/models")
async def model_catalog():
    """Use the shared catalog without rescanning disks/hardware on every UI visit."""
    return {"active_provider": settings.llm_provider,
            "active_model": existing._get_active_model_for_provider(settings.llm_provider),
            "fallback_enabled": settings.fallback_enabled,
            "providers_catalog": {key: value.model_dump(mode="json") for key, value in CATALOG_PROVIDERS.items()}}


class ModelSelection(BaseModel):
    provider: Literal["agnes", "groq", "openrouter", "nvidia_nim", "gemini", "ollama", "lmstudio"]
    model: str = Field(min_length=1, max_length=300)


@router.post("/screening/failover")
async def set_failover(request: existing.FallbackToggleRequest):
    """Update the same factory failover switch as Admin without a hardware scan."""
    settings.fallback_enabled = request.enabled
    return await model_catalog()


@router.post("/screening/models")
async def select_model(request: ModelSelection):
    provider = CATALOG_PROVIDERS.get(request.provider)
    active_model = existing._get_active_model_for_provider(request.provider)
    if not provider or (request.model != active_model and not any(m.id == request.model for m in provider.models)):
        raise HTTPException(400, "Choose a model from the available catalog.")
    # DynamicLLMClient resolves these shared settings at execution time, exactly as Admin does.
    settings.llm_provider = request.provider
    setattr(settings, f"{request.provider}_model", request.model)
    from backend.agents.llm_factory import clear_last_fallback_event
    clear_last_fallback_event()
    return await model_catalog()


async def read_run(run_id: UUID | str) -> dict:
    async with async_session_scope() as db:
        record = await db.get(ScreeningRunModel, str(run_id))
        if not record:
            raise HTTPException(404, "Screening run not found.")
        return copy.deepcopy(record.payload)


async def save_run(payload: dict):
    async with async_session_scope() as db:
        record = await db.get(ScreeningRunModel, payload["id"])
        if record:
            if record.payload.get("attempt", 0) > payload.get("attempt", 0):
                return
            record.payload = copy.deepcopy(payload)
        else:
            db.add(ScreeningRunModel(id=payload["id"], job_id=payload["job_id"], payload=copy.deepcopy(payload)))
        await db.commit()


async def recover_interrupted_runs():
    """Local single-process runner: make interrupted work retryable after a restart."""
    async with async_session_scope() as db:
        records = list((await db.scalars(select(ScreeningRunModel).where(ScreeningRunModel.payload["status"].as_string().in_(["ranking", "evaluating"])))).all())
        for record in records:
            payload = copy.deepcopy(record.payload)
            if payload["status"] not in {"ranking", "evaluating"}:
                continue
            payload["status"] = "partial" if payload["rows"] else "failed"
            payload["error"] = "Screening was interrupted by a server restart. Run screening again to finish."
            payload["phase"] = "interrupted"
            for row in payload["rows"]:
                if row["deep_status"] == "pending":
                    row.update(deep_status="failed", error=payload["error"])
            record.payload = payload
        await db.commit()


async def hybrid_rank(payload, candidates, job, embedding_fn):
    model_key = f"{existing._vector_store.model_name}:{getattr(settings, 'screening_embedding_cache_version', '1')}"
    keys = [feature_key(candidate, model_key) for candidate in candidates]
    async with async_session_scope() as db:
        cached = list((await db.scalars(select(ScreeningFeatureCacheModel).where(ScreeningFeatureCacheModel.key.in_(keys)))).all())
    engine = HybridRankingEngine(embedding_fn, model_key, {entry.key: entry.payload for entry in cached})
    payload["phase"] = "Matching requirement evidence"
    await save_run(payload)
    rebuilt_cache = False
    try:
        rows = await asyncio.to_thread(engine.rank, candidates, job, payload.get("evidence_per_requirement", 3))
    except (ValueError, TypeError):
        if not cached:
            raise
        engine = HybridRankingEngine(embedding_fn, model_key)
        rows = await asyncio.to_thread(engine.rank, candidates, job, payload.get("evidence_per_requirement", 3))
        rebuilt_cache = True
        engine.diagnostics["warnings"].append("Invalid evidence cache rebuilt from source profiles.")
    try:
        async with async_session_scope() as db:
            existing_keys = {record.key for record in cached}
            for key, value in engine.cache_updates.items():
                if key not in existing_keys:
                    db.add(ScreeningFeatureCacheModel(key=key, payload=value))
                elif rebuilt_cache:
                    await db.merge(ScreeningFeatureCacheModel(key=key, payload=value))
            await db.commit()
    except Exception:
        # Cache contention must not fail an otherwise valid screening run.
        engine.diagnostics["warnings"].append("Evidence cache write skipped; ranking results are unaffected.")
    if payload.get("rerank_enabled", True):
        payload["phase"] = "Reranking evidence"
        await save_run(payload)
        started = time.perf_counter()
        try:
            reranker = await asyncio.wait_for(asyncio.to_thread(get_reranker), timeout=settings.screening_reranker_timeout_seconds)
            # Use a copy so a failed prediction cannot leave partially modified rows.
            rows = await asyncio.wait_for(asyncio.to_thread(engine.rerank, copy.deepcopy(rows), job, reranker, max(payload["top_k"], payload.get("rerank_pool_size", 100))), timeout=settings.screening_reranker_timeout_seconds)
            engine.diagnostics["reranker_model"] = reranker.model_name
        except Exception as error:
            engine.diagnostics["warnings"].append("Local reranker unavailable or timed out; hybrid order retained.")
            engine.diagnostics["reranker_error"] = type(error).__name__
            engine.diagnostics["reranker_fallback"] = True
        engine.diagnostics["timings_ms"]["reranking"] = round((time.perf_counter() - started) * 1000, 2)
    engine.diagnostics["reranked_candidates"] = sum(row.reranked for row in rows)
    payload["diagnostics"] = engine.diagnostics
    return rows


async def execute_rank(payload: dict, candidates: list[AnonymizedCandidate], job: JobDescription, frozen_client=None):
    async with _screening_slots:
        await _execute_rank(payload, candidates, job, frozen_client)


async def _execute_rank(payload: dict, candidates: list[AnonymizedCandidate], job: JobDescription, frozen_client=None):
    started = time.perf_counter()
    try:
        if payload.get("rows"):
            rows = [PreScreenRow.model_validate(row) for row in payload["rows"]]
            selected_ids = set(payload.get("deep_candidate_ids", []))
            selected = [row for row in rows if str(row.candidate_id) in selected_ids and row.deep_status != "completed"]
        else:
            embedding_fn = await asyncio.to_thread(lambda: existing._vector_store.embedding_fn)
            if payload.get("pipeline_version") == "v2":
                rows = await hybrid_rank(payload, candidates, job, embedding_fn)
            else:
                rows = await asyncio.to_thread(PreRankingEngine(embedding_fn).rank, candidates, job)
            selected = rows[:payload["top_k"]] if payload["deep_enabled"] else []
            payload["deep_candidate_ids"] = [str(row.candidate_id) for row in selected]
        for row in selected:
            row.deep_status = "pending"
            row.error = None
        payload["rows"] = [row.model_dump(mode="json") for row in rows]
        payload["status"] = "evaluating" if selected else "completed"
        payload["phase"] = "Deep evaluating Top-K" if selected else "Completed"
        await save_run(payload)
        profiles = {str(c.candidate_id): c for c in candidates}
        # Each run owns its agent's mutable state while retaining the configured factory.
        client = frozen_client
        if selected and payload.get("pipeline_version") == "v2" and client is None:
            client = DynamicLLMClient()
            await asyncio.to_thread(client.freeze_configuration)
        agent = MatchingAgent(llm_client=client, vector_store=existing._vector_store, scoring_engine=existing._scoring_engine) if selected else None
        seen_evaluations = {evaluation_key(PreScreenRow.model_validate(row).deep_evaluation): row["candidate_id"] for row in payload["rows"] if row["deep_status"] == "completed"}
        duplicate_ids: set[str] = set()
        selected_ids = {str(row.candidate_id) for row in selected}
        deep_started = time.perf_counter()
        for row in [row for row in payload["rows"] if row["candidate_id"] in selected_ids]:
            try:
                result = await asyncio.to_thread(agent.match_candidate, candidate=profiles[row["candidate_id"]], job_description=job)
                await DatabaseRepository.save_evaluation(result, row["candidate_id"], job.id)
                row["deep_evaluation"] = result.model_dump(mode="json")
                row["deep_status"] = "completed"
                key = evaluation_key(result)
                if key in seen_evaluations:
                    duplicate_ids.add(row["candidate_id"])
                    payload.setdefault("duplicates", []).append({
                        "candidate_id": row["candidate_id"],
                        "kept_candidate_id": seen_evaluations[key],
                        "reason": "identical_evaluation",
                    })
                else:
                    seen_evaluations[key] = row["candidate_id"]
            except Exception as error:
                row["deep_status"] = "failed"
                row["error"] = str(error)
            # Keep the highest pre-ranked representative and contiguous ranks.
            payload["rows"] = [r for r in payload["rows"] if r["candidate_id"] not in duplicate_ids]
            for rank, retained in enumerate(payload["rows"], 1):
                retained["rank"] = rank
            await save_run(payload)
        payload.setdefault("diagnostics", {}).setdefault("timings_ms", {})["deep_evaluation"] = round((time.perf_counter() - deep_started) * 1000, 2)
        payload["status"] = "partial" if any(r["deep_status"] == "failed" for r in payload["rows"]) else "completed"
        representatives = {item["candidate_id"]: item["kept_candidate_id"] for item in payload.get("duplicates", [])}
        for item in payload.get("duplicates", []):
            while item["kept_candidate_id"] in representatives:
                item["kept_candidate_id"] = representatives[item["kept_candidate_id"]]
        payload["phase"] = "Completed" if payload["status"] == "completed" else "Completed with evaluation errors"
    except Exception as error:
        payload["status"] = "failed"
        payload["error"] = str(error)
        payload["phase"] = "Failed"
    payload["ended_at"] = int(time.time() * 1000)
    payload.setdefault("diagnostics", {}).setdefault("timings_ms", {})["attempt_total"] = round((time.perf_counter() - started) * 1000, 2)
    await save_run(payload)


@router.post("/screening/rank", status_code=202)
async def start_rank(request: FastRankRequest, background_tasks: BackgroundTasks):
    record = await DatabaseRepository.get_job(request.job_id)
    if not record:
        raise HTTPException(404, "Job not found.")
    job = existing._reconstruct_job_from_db(record)
    if request.pipeline_version == "v2" and not 1 <= len([r for r in job.requirements if r.weight > 0]) <= 100:
        raise HTTPException(422, "Improved screening requires 1 to 100 weighted job criteria.")
    async with async_session_scope() as db:
        records = list((await db.scalars(select(CandidateModel).where(CandidateModel.id.in_([str(cid) for cid in request.candidate_ids])))).all())
    if len(records) != len(request.candidate_ids):
        raise HTTPException(404, "One or more selected candidates no longer exist. Refresh the cohort.")
    by_id = {r.id: r for r in records}
    candidates = []
    duplicates = []
    names: dict[str, str] = {}
    # Request order chooses the representative, independent of database ordering.
    for candidate_id in request.candidate_ids:
        record = by_id[str(candidate_id)]
        key = candidate_name_key(record.raw_cv_json)
        if key and key in names:
            duplicates.append({"candidate_id": record.id, "kept_candidate_id": names[key], "reason": "same_name"})
            continue
        if key:
            names[key] = record.id
        candidates.append(AnonymizedCandidate.model_validate(record.anonymized_cv_json))
    payload = {"id": str(uuid4()), "job_id": str(job.id), "job": job.model_dump(mode="json"), "status": "ranking", "started_at": int(time.time() * 1000), "top_k": request.top_k, "deep_enabled": request.deep_evaluation, "rows": [], "duplicates": duplicates, "shortlist_ids": [], "decisions": {}, "error": None}
    payload.update(pipeline_version=request.pipeline_version, rerank_enabled=request.rerank_enabled,
        rerank_pool_size=max(request.top_k, request.rerank_pool_size), evidence_per_requirement=request.evidence_per_requirement,
        phase="Queued", attempt=1, candidate_ids=[str(c.candidate_id) for c in candidates],
        profile_hashes={str(c.candidate_id): snapshot_hash(c.model_dump(mode="json")) for c in candidates},
        job_hash=snapshot_hash(job.model_dump(mode="json")),
        model_configuration={"provider": settings.llm_provider, "model": existing._get_active_model_for_provider(settings.llm_provider), "failover": settings.fallback_enabled})
    frozen_client = None
    if request.pipeline_version == "v2" and request.deep_evaluation:
        frozen_client = DynamicLLMClient()
        await asyncio.to_thread(frozen_client.freeze_configuration)
    await save_run(payload)
    background_tasks.add_task(execute_rank, copy.deepcopy(payload), candidates, job, frozen_client)
    return payload


@router.post("/screening/runs/{run_id}/retry", status_code=202)
async def retry_rank(run_id: UUID, background_tasks: BackgroundTasks):
    async with _run_lock:
        payload = await read_run(run_id)
        if payload["status"] not in {"failed", "partial"} or not payload.get("profile_hashes"):
            raise HTTPException(409, "Only interrupted or failed versioned runs can be retried.")
        async with async_session_scope() as db:
            records = list((await db.scalars(select(CandidateModel).where(CandidateModel.id.in_(payload["candidate_ids"])))).all())
        candidates = [AnonymizedCandidate.model_validate(record.anonymized_cv_json) for record in records]
        if {str(c.candidate_id): snapshot_hash(c.model_dump(mode="json")) for c in candidates} != payload["profile_hashes"]:
            raise HTTPException(409, "Candidate data changed or was removed. Start a new screening run.")
        history = payload.setdefault("attempt_history", [])
        history.append({"attempt": payload.get("attempt", 1), "model_configuration": payload.get("model_configuration", {})})
        payload.update(status="ranking", phase="Queued for retry", error=None, attempt=payload.get("attempt", 0) + 1,
            model_configuration={"provider": settings.llm_provider, "model": existing._get_active_model_for_provider(settings.llm_provider), "failover": settings.fallback_enabled})
        payload.setdefault("diagnostics", {}).setdefault("warnings", []).append("Retry uses current shared model settings; completed evaluations are retained.")
        frozen_client = None
        if payload.get("pipeline_version") == "v2" and payload["deep_enabled"]:
            frozen_client = DynamicLLMClient()
            await asyncio.to_thread(frozen_client.freeze_configuration)
        await save_run(payload)
        background_tasks.add_task(execute_rank, copy.deepcopy(payload), candidates, JobDescription.model_validate(payload["job"]), frozen_client)
        return payload


@router.get("/screening/runs/{run_id}")
async def get_run(run_id: UUID):
    return await read_run(run_id)


@router.get("/screening/jobs/{job_id}/latest")
async def latest_run(job_id: UUID):
    async with async_session_scope() as db:
        record = await db.scalar(select(ScreeningRunModel).where(ScreeningRunModel.job_id == str(job_id)).order_by(ScreeningRunModel.created_at.desc(), ScreeningRunModel.id.desc()).limit(1))
        return record.payload if record else None


@router.post("/screening/runs/{run_id}/shortlist")
async def shortlist(run_id: UUID, request: ShortlistRequest):
    async with _run_lock:
        payload = await read_run(run_id)
        if payload["status"] not in {"completed", "partial"}:
            raise HTTPException(409, "Wait for ranking to finish before creating the comparison matrix.")
        rows = payload["rows"][:request.count]
        if not rows or any(r["deep_status"] != "completed" for r in rows):
            raise HTTPException(409, "The selected top candidates need completed deep evaluations. Reduce the comparison count or rerun with a larger top K.")
        payload["shortlist_ids"] = [r["candidate_id"] for r in rows]
        await save_run(payload)
        return payload


@router.post("/screening/runs/{run_id}/decisions/{candidate_id}")
async def review(run_id: UUID, candidate_id: UUID, request: ReviewDecision):
    async with _run_lock:
        payload = await read_run(run_id)
        if str(candidate_id) not in payload["shortlist_ids"]:
            raise HTTPException(409, "Candidate must be in the comparison shortlist.")
        row = next(r for r in payload["rows"] if r["candidate_id"] == str(candidate_id))
        evaluation = row["deep_evaluation"]
        recommendation = {"interview": "strong_match", "hold": "borderline", "reject": "reject"}[request.decision]
        # Persist before reporting success; failed writes must never advance a candidate.
        persisted = await DatabaseRepository.update_hitl_validation(evaluation["id"], recommendation, request.notes)
        if not persisted:
            raise HTTPException(409, "This evaluation no longer exists. Rank the cohort again.")
        existing._EVALUATION_STORE.pop(UUID(evaluation["id"]), None)
        evaluation.update(hitl_validated=True, recommendation=recommendation, recruiter_notes=request.notes)
        payload["decisions"][str(candidate_id)] = request.model_dump()
        await save_run(payload)
        return payload


class RecruiterInterviewRequest(BaseModel):
    candidate_id: UUID
    duration_minutes: int = Field(default=45, ge=15, le=120)


@router.post("/screening/runs/{run_id}/interview")
async def interview(run_id: UUID, request: RecruiterInterviewRequest):
    payload = await read_run(run_id)
    if str(request.candidate_id) not in payload["shortlist_ids"] or payload["decisions"].get(str(request.candidate_id), {}).get("decision") != "interview":
        raise HTTPException(409, "A recruiter must approve this candidate for interview first.")
    row = next(r for r in payload["rows"] if r["candidate_id"] == str(request.candidate_id))
    plan = await existing.generate_interview_plan(existing.InterviewGenerateRequest(candidate_id=request.candidate_id, evaluation_id=UUID(row["deep_evaluation"]["id"]), job_description=JobDescription.model_validate(payload["job"]), target_duration_minutes=request.duration_minutes))
    async with _run_lock:
        payload = await read_run(run_id)
        payload.setdefault("interviews", {})[str(request.candidate_id)] = plan.model_dump(mode="json")
        await save_run(payload)
    return plan


@router.post("/screening/jobs/parse")
async def parse_job_draft(request: existing.JobTextParseRequest):
    """Extract an editable draft without creating a second, hidden job record."""
    try:
        return await asyncio.to_thread(existing._job_parser_agent.parse_job_text, request.text)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/screening/jobs/parse-url")
async def parse_job_url_draft(request: existing.JobUrlParseRequest):
    """Use the same URL extraction engine as Admin, returning a draft for review."""
    try:
        return await asyncio.to_thread(existing._job_parser_agent.parse_job_url, request.url)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/screening/cohort/upload", status_code=202)
async def upload_cohort(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)):
    if not 1 <= len(files) <= 1000:
        raise HTTPException(400, "Choose between 1 and 1000 CV files.")
    payloads = []
    total_bytes = 0
    for file in files:
        name = file.filename or ""
        if not name.lower().endswith((".pdf", ".docx", ".txt")):
            raise HTTPException(400, f"Unsupported file: {name}. Use PDF, DOCX or TXT.")
        content = await file.read(20 * 1024 * 1024 + 1)
        if not content or len(content) > 20 * 1024 * 1024:
            raise HTTPException(400, f"{name}: file must contain data and be at most 20 MB.")
        total_bytes += len(content)
        if total_bytes > 200 * 1024 * 1024:
            raise HTTPException(413, "Upload at most 200 MB in one cohort batch.")
        payloads.append((name, content))
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(len(payloads), batch_id=batch_id)
    background_tasks.add_task(existing._batch_processor.execute_parse_batch, batch_id, payloads)
    return {"batch_id": str(batch_id), "total_files": len(payloads), "status": "PROCESSING"}
