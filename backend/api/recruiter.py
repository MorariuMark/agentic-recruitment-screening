"""Recruiter workspace routes, reusing the existing agents, factory and repositories."""
from backend.services.process_control import CancellableRoute, schedule_job
import asyncio
import concurrent.futures
import copy
import json
import logging
import secrets
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Header, HTTPException, Query, Response, UploadFile
from backend.api.auth import require_role, get_current_user
from backend.services.evidence import is_benchmark_profile, language_priority
from pydantic import BaseModel
from pydantic import Field
from sqlalchemy import func, select

from backend.api import routes as existing
from backend.api.job_errors import job_parse_http_error
from backend.agents.matching_agent import MatchingAgent, EvaluationDeferredError
from backend.agents.llm_factory import DynamicLLMClient
from backend.config import settings
from backend.schemas.models_catalog import CATALOG_PROVIDERS
from backend.db.models import AuditLogModel, BatchJobModel, CandidateModel, InterviewPlanModel, JobRequisitionModel, MatchEvaluationModel, ScreeningRunModel, ScreeningFeatureCacheModel
from backend.db.repository import DatabaseRepository
from backend.db.session import async_session_scope
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription
from backend.schemas.match import RequirementMatch
from backend.schemas.screening import DeepEvaluationRequest, FastRankRequest, PreScreenRow, ReviewDecision, ShortlistRequest
from backend.services.operation_timing import record_operation, measure, operation_statistics
from backend.services.pre_ranking import PreRankingEngine
from backend.services.hybrid_screening import HybridRankingEngine, feature_key, snapshot_hash
from backend.services.screening_reranker import get_reranker
from backend.services.screening_duplicates import candidate_name_key, evaluation_key

router = APIRouter(route_class=CancellableRoute, prefix="/api/v1", tags=["Recruiter workspace"], dependencies=[Depends(get_current_user)])
auth_router = APIRouter(prefix="/api/v1", tags=["Authentication"])
_run_lock = asyncio.Lock()
_screening_slots = asyncio.Semaphore(2)
_RERANKER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="recruiter_reranker")


async def _wait_for_evaluation_provider(delay):
    await asyncio.sleep(delay)


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
        from backend.services.parsing_timing import parsing_statistics
        progress_records = (await db.scalars(select(BatchJobModel.progress_json))).all()
        totals["cv_parsing"] = parsing_statistics(progress_records)
        from backend.services.token_tracker import token_tracker
        totals.update(token_tracker.get_processing_totals())
        recent = (await db.execute(select(ScreeningRunModel.id, ScreeningRunModel.payload["diagnostics"], ScreeningRunModel.payload["pipeline_version"])
            .order_by(ScreeningRunModel.created_at.desc(), ScreeningRunModel.id.desc()).limit(5))).all()
        totals["recent_screening"] = [{"run_id": run_id, "pipeline_version": version or "v1", **(diagnostics or {})} for run_id, diagnostics, version in recent]
        return totals


@router.get("/screening/statistics/actions")
async def action_statistics(days: int = Query(default=0, ge=0, le=3650),
                            operation: str | None = None, job_id: UUID | None = None,
                            batch_id: UUID | None = None, run_id: UUID | None = None,
                            limit: int = Query(default=25, ge=1, le=100),
                            offset: int = Query(default=0, ge=0)):
    return await operation_statistics(days=days, operation=operation, job_id=job_id,
                                      batch_id=batch_id, run_id=run_id, limit=limit, offset=offset)


@router.get("/screening/statistics/cohorts")
async def cohort_statistics(job_id: UUID | None = None, days: int = Query(default=0, ge=0, le=3650),
                            limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    from backend.services.cohort_statistics import screening_statistics
    return await screening_statistics(job_id=job_id, days=days, limit=limit, offset=offset)


class LoginRequest(BaseModel):
    role: Literal["admin", "user"]
    password: str


@auth_router.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    from backend.api.auth import create_session_token
    # Role-based credential verification (E4)
    expected_pw = settings.auth_admin_password if payload.role == "admin" else settings.auth_user_password
    matched = secrets.compare_digest(payload.password, expected_pw)
    if not matched and settings.auth_demo_mode:
        matched = secrets.compare_digest(payload.password, "1234")
    if not matched:
        raise HTTPException(401, "Incorrect password. Try again.")

    token = create_session_token(payload.role)
    response.set_cookie("atos_workspace", token, httponly=True, samesite="lax", max_age=43200)
    return {"role": payload.role, "token": token}


@auth_router.get("/auth/session")
async def session(atos_workspace: str | None = Cookie(None), authorization: str | None = Header(None)):
    from backend.api.auth import verify_session_token
    token = atos_workspace
    if not token and authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()
    user = verify_session_token(token or "")
    if user:
        return {"role": user.get("role"), "token": token}
    return {"role": None}


@auth_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("atos_workspace")
    return {"status": "ok"}


_CACHED_CATALOG_PROVIDERS = {key: value.model_dump(mode="json") for key, value in CATALOG_PROVIDERS.items()}

@router.get("/screening/models")
async def model_catalog():
    """Use the shared catalog without rescanning disks/hardware on every UI visit."""
    from backend.agents.llm_factory import get_active_cooldown_statuses, get_last_fallback_event
    return {"active_provider": settings.llm_provider,
            "active_model": existing._get_active_model_for_provider(settings.llm_provider),
            "fallback_enabled": settings.fallback_enabled,
            "parallel_screening_enabled": getattr(settings, "parallel_screening_enabled", False),
            "cooldown_statuses": get_active_cooldown_statuses(),
            "last_fallback_event": get_last_fallback_event(),
            "providers_catalog": _CACHED_CATALOG_PROVIDERS}


@router.post("/screening/models/clear-failover")
async def clear_failover_alert():
    """Clear active failover alert in recruiter workspace."""
    from backend.agents.llm_factory import clear_last_fallback_event
    clear_last_fallback_event()
    return await model_catalog()


@router.post("/screening/models/refresh-local")
async def refresh_local_models():
    """Refresh local discovery without importing models or changing the active engine."""
    from backend.services.local_model_scanner import get_local_model_scanner
    result = await asyncio.to_thread(get_local_model_scanner().refresh_local_engines)
    return {**await model_catalog(), "local_discovery": result}


@router.post("/screening/parallel-toggle")
async def set_parallel(request: existing.ParallelToggleRequest):
    """Update parallel screening mode in recruiter workspace."""
    settings.parallel_screening_enabled = request.enabled
    return await model_catalog()


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
    """Allow authenticated recruiters to select a catalog model for subsequent work."""
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


def sort_screening_rows(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows

    def sort_key(row: dict):
        deep_status = row.get("deep_status")
        deep_eval = row.get("deep_evaluation") or {}
        overall_score = deep_eval.get("overall_score")
        if deep_status == "completed" and overall_score is not None:
            return (
                0,
                -round(float(overall_score), 4),
                -round(float(row.get("pre_screen_score") or 0), 4),
                row.get("initial_rank") or row.get("rank") or 999999,
            )
        elif deep_status in {"deferred", "failed"}:
            return (
                1,
                0,
                -round(float(row.get("pre_screen_score") or 0), 4),
                row.get("initial_rank") or row.get("rank") or 999999,
            )
        else:
            return (
                2,
                0,
                -round(float(row.get("pre_screen_score") or 0), 4),
                row.get("initial_rank") or row.get("rank") or 999999,
            )

    sorted_rows = sorted(rows, key=sort_key)
    for rank, row in enumerate(sorted_rows, 1):
        row["rank"] = rank
    return sorted_rows


async def read_run(run_id: UUID | str) -> dict:
    async with async_session_scope() as db:
        record = await db.get(ScreeningRunModel, str(run_id))
        if not record:
            raise HTTPException(404, "Screening run not found.")
        payload = copy.deepcopy(record.payload)
        if payload.get("rows") and not payload.get("evaluation_candidate_ids") and any(r.get("deep_status") == "completed" for r in payload["rows"]):
            payload["rows"] = sort_screening_rows(payload["rows"])
        return payload


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
            loop = asyncio.get_running_loop()
            reranker = await asyncio.wait_for(loop.run_in_executor(_RERANKER_EXECUTOR, get_reranker), timeout=settings.screening_reranker_load_timeout_seconds)
            # Use a copy so a failed prediction cannot leave partially modified rows.
            rerank_pool = min(len(rows), max(payload["top_k"], payload.get("rerank_pool_size", 100)))
            rows_copy = copy.deepcopy(rows)
            rows = await asyncio.wait_for(loop.run_in_executor(_RERANKER_EXECUTOR, lambda: engine.rerank(rows_copy, job, reranker, rerank_pool)), timeout=settings.screening_reranker_timeout_seconds)
            engine.diagnostics["reranker_model"] = reranker.model_name
        except Exception as error:
            logging.exception("Screening reranker failed for model %s", settings.screening_reranker_model)
            engine.diagnostics["warnings"].append("Local reranker unavailable or timed out; hybrid order retained.")
            engine.diagnostics["reranker_error"] = type(error).__name__
            engine.diagnostics["reranker_model"] = settings.screening_reranker_model
            engine.diagnostics["warnings"].append(
                f"Reranker model: {settings.screening_reranker_model}. "
                "Retry reranking; if local model files are missing, run scripts/cache_screening_reranker.py.")
            engine.diagnostics["reranker_fallback"] = True
        engine.diagnostics["timings_ms"]["reranking"] = round((time.perf_counter() - started) * 1000, 2)
    engine.diagnostics["reranked_candidates"] = sum(row.reranked for row in rows)
    payload["diagnostics"] = engine.diagnostics
    return rows


@record_operation("screening_run", lambda a: {"run_id": a["payload"]["id"], "job_id": a["job"].id, "item_count": len(a["candidates"]), "label": a["job"].title})
async def execute_rank(payload: dict, candidates: list[AnonymizedCandidate], job: JobDescription, frozen_client=None):
    if (await read_run(payload["id"]))["status"] == "cancelled":
        return
    async with _screening_slots:
        await _execute_rank(payload, candidates, job, frozen_client)


async def _execute_rank(payload: dict, candidates: list[AnonymizedCandidate], job: JobDescription, frozen_client=None):
    started = time.perf_counter()
    try:
        if payload.get("rows"):
            rows = [PreScreenRow.model_validate(row) for row in payload["rows"]]
            selected_ids = set(payload.get("evaluation_candidate_ids", payload.get("deep_candidate_ids", [])))
            selected = [row for row in rows if str(row.candidate_id) in selected_ids and row.deep_status != "completed"]
        else:
            async with measure("ranking", item_count=len(candidates), label=job.title):
                embedding_fn = await asyncio.to_thread(lambda: existing._vector_store.embedding_fn)
                if payload.get("pipeline_version") == "v2":
                    rows = await hybrid_rank(payload, candidates, job, embedding_fn)
                else:
                    rows = await asyncio.to_thread(PreRankingEngine(embedding_fn).rank, candidates, job)
            payload["pre_screening_ms"] = round((time.perf_counter() - started) * 1000, 2)
            source_ready = {str(candidate.candidate_id) for candidate in candidates if candidate.sanitized_text.strip()}
            selected = [row for row in rows if row.language_priority == 0 and str(row.candidate_id) in source_ready][:payload["top_k"]] if payload["deep_enabled"] else []
            deferred = sum(row.language_priority > 0 for row in rows)
            if deferred:
                payload.setdefault("diagnostics", {}).setdefault("warnings", []).append(
                    f"{deferred} candidates need review of mandatory evidence and are outside automatic Top-K evaluation. Select profiles explicitly to evaluate them.")
            payload["deep_candidate_ids"] = [str(row.candidate_id) for row in selected]
            missing_source = sum(not candidate.sanitized_text.strip() for candidate in candidates)
            if missing_source:
                payload.setdefault("diagnostics", {}).setdefault("warnings", []).append(
                    f"{missing_source} profiles have no original CV source text. Their structured profiles can be ranked, "
                    "but deep evaluation is unavailable until the original CV is reparsed; this is not a negative candidate finding.")
        warnings = payload.setdefault("diagnostics", {}).setdefault("warnings", [])
        active_requirements = sum(req.weight > 0 for req in job.requirements)
        if active_requirements < 3:
            warning = (f"This job has only {active_requirements} active requirement(s). Scores cover only those criteria; "
                       "100% does not establish overall suitability for the job title. Review the job requirements before shortlisting.")
            if warning not in warnings:
                warnings.append(warning)
        if not (job.raw_text or "").strip():
            warning = "No original job description is stored. Confirm that the configured requirements fully describe the intended role."
            if warning not in warnings:
                warnings.append(warning)
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
        if agent:
            agent.execution_context = {"run_id": payload["id"], "attempt": payload.get("attempt", 1), "job_id": str(job.id)}
        selected_ids = {str(row.candidate_id) for row in selected}
        deep_started = time.perf_counter()
        provider_wait_remaining = settings.screening_provider_wait_seconds
        eval_rows = [row for row in payload["rows"] if row["candidate_id"] in selected_ids]
        for eval_idx, row in enumerate(eval_rows):
            cand_profile = profiles.get(row["candidate_id"])
            cand_name = getattr(cand_profile, "masked_name", None) or row.get("candidate_name") or f"Candidate {row['candidate_id'][:8]}"
            payload["active_candidate_id"] = row["candidate_id"]
            payload["phase"] = f"Evaluating {cand_name} ({eval_idx + 1}/{len(eval_rows)})"
            await save_run(payload)
            while True:
                agent.resume_matches = [RequirementMatch.model_validate(match) for match in row.get("deep_requirement_matches", [])]
                agent.completed_matches = []
                try:
                    async with measure("candidate_screening", candidate_id=row["candidate_id"], label=f"Candidate {row['candidate_id'][:8]}"):
                        result = await asyncio.to_thread(agent.match_candidate, candidate=profiles[row["candidate_id"]], job_description=job)
                        await DatabaseRepository.save_evaluation(result, row["candidate_id"], job.id)
                    row.update(deep_evaluation=result.model_dump(mode="json"), deep_status="completed", error=None, retry_after=None)
                    row["deep_requirement_matches"] = [match.model_dump(mode="json") for match in agent.completed_matches]
                    break
                except EvaluationDeferredError as error:
                    row["deep_requirement_matches"] = [match.model_dump(mode="json") for match in agent.completed_matches]
                    delay = max(1.0, error.retry_after)
                    row.update(deep_status="deferred", error=str(error), retry_after=delay)
                    if delay > min(provider_wait_remaining, 30):
                        break
                    payload["phase"] = f"Waiting for AI providers; retrying unfinished criteria in {delay:.0f}s"
                    await save_run(payload)
                    await _wait_for_evaluation_provider(delay)
                    provider_wait_remaining -= delay
                    row.update(deep_status="pending", error=None, retry_after=None)
                    payload["phase"] = "Deep evaluating unfinished criteria"
                except Exception as error:
                    row["deep_requirement_matches"] = [match.model_dump(mode="json") for match in agent.completed_matches]
                    row.update(deep_status="failed", error=str(error))
                    break
            for warning in getattr(agent, "retrieval_warnings", []):
                if warning not in warnings:
                    warnings.append(warning)
            try:
                from backend.services.action_logger import action_logger
                await action_logger.persist_run(payload["id"])
            except Exception:
                payload.setdefault("diagnostics", {}).setdefault("warnings", []).append("Action log persistence failed; trace may be incomplete.")
            await save_run(payload)
        payload["active_candidate_id"] = None
        if not payload.get("evaluation_candidate_ids"):
            payload["rows"] = sort_screening_rows(payload.get("rows", []))
        payload.setdefault("diagnostics", {}).setdefault("timings_ms", {})["deep_evaluation"] = round((time.perf_counter() - deep_started) * 1000, 2)
        payload["deep_evaluation_ms"] = payload.get("deep_evaluation_ms", 0) + payload["diagnostics"]["timings_ms"]["deep_evaluation"]
        payload["status"] = "partial" if any(r["deep_status"] in {"failed", "deferred"} for r in payload["rows"]) else "completed"
        representatives = {item["candidate_id"]: item["kept_candidate_id"] for item in payload.get("duplicates", [])}
        for item in payload.get("duplicates", []):
            while item["kept_candidate_id"] in representatives:
                item["kept_candidate_id"] = representatives[item["kept_candidate_id"]]
        payload["phase"] = "Completed" if payload["status"] == "completed" else "Completed with deferred or unavailable evaluations"
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
    if not any(req.weight > 0 for req in job.requirements):
        raise HTTPException(422, "Screening requires a job with criteria.")
    if not 1 <= len([r for r in job.requirements if r.weight > 0]) <= 100:
        raise HTTPException(422, "Improved screening requires 1 to 100 weighted job criteria.")
    cid_strs = [str(cid) for cid in request.candidate_ids]
    records = []
    chunk_size = 500
    async with async_session_scope() as db:
        for i in range(0, len(cid_strs), chunk_size):
            chunk = cid_strs[i:i + chunk_size]
            sub = list((await db.scalars(select(CandidateModel).where(CandidateModel.id.in_(chunk)))).all())
            records.extend(sub)
    from backend.services.cv_library import is_trashed
    if await is_trashed(cid_strs):
        raise HTTPException(409, "Restore trashed CVs before screening them.")
    if len(records) != len(request.candidate_ids):
        raise HTTPException(404, "One or more selected candidates no longer exist. Refresh the cohort.")
    by_id = {r.id: r for r in records}
    if not request.include_benchmark and any(is_benchmark_profile(r.raw_cv_json) for r in records):
        raise HTTPException(422, "Demo profiles must be screened separately. Enable demo screening explicitly.")
    if request.include_benchmark and not all(is_benchmark_profile(r.raw_cv_json) for r in records):
        raise HTTPException(422, "Keep demo profiles and recruiting candidates in separate screening runs.")
    candidates = []
    duplicates = []
    names: dict[str, str] = {}
    # Request order chooses the representative, independent of database ordering.
    for candidate_id in request.candidate_ids:
        record = by_id[str(candidate_id)]
        key = candidate_name_key(record.raw_cv_json)
        if key and key in names:
            duplicates.append({"candidate_id": record.id, "kept_candidate_id": names[key], "reason": "same_document_or_contact"})
            continue
        if key:
            names[key] = record.id
        candidates.append(AnonymizedCandidate.model_validate(record.anonymized_cv_json))
    payload = {"id": str(uuid4()), "job_id": str(job.id), "job": job.model_dump(mode="json"), "status": "ranking", "started_at": int(time.time() * 1000), "top_k": request.top_k, "deep_enabled": request.deep_evaluation, "rows": [], "duplicates": duplicates, "shortlist_ids": [], "decisions": {}, "error": None}
    payload.update(pipeline_version=request.pipeline_version, rerank_enabled=request.rerank_enabled,
        ranking_policy_version="mandatory-evidence-v2", evidence_policy_version="source-v2", dataset="benchmark" if request.include_benchmark else "recruiting",
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
    schedule_job(background_tasks, f"run:{payload['id']}", execute_rank, copy.deepcopy(payload), candidates, job, frozen_client)
    return payload


@router.post("/screening/runs/{run_id}/retry", status_code=202)
async def retry_rank(run_id: UUID, background_tasks: BackgroundTasks):
    return await resume_rank(run_id, background_tasks)


@router.post("/screening/runs/{run_id}/evaluate", status_code=202)
async def evaluate_selected(run_id: UUID, request: DeepEvaluationRequest, background_tasks: BackgroundTasks):
    return await resume_rank(run_id, background_tasks, {str(cid) for cid in request.candidate_ids})


async def resume_rank(run_id: UUID, background_tasks: BackgroundTasks, selected_ids: set[str] | None = None):
    async with _run_lock:
        payload = await read_run(run_id)
        allowed = {"completed", "partial", "failed", "cancelled"} if selected_ids else {"failed", "partial", "cancelled"}
        if payload.get("evidence_policy_version") != "source-v2":
            raise HTTPException(409, "Start a new screening to use the corrected evidence and language policy.")
        if payload["status"] not in allowed or not payload.get("profile_hashes"):
            raise HTTPException(409, "Only interrupted or failed versioned runs can be retried.")
        if selected_ids:
            eligible = {row["candidate_id"] for row in payload["rows"] if row["deep_status"] != "completed"}
            if not selected_ids <= eligible:
                raise HTTPException(422, "Select unevaluated candidates belonging to this run.")
            payload["deep_candidate_ids"] = list(dict.fromkeys([*payload.get("deep_candidate_ids", []), *sorted(selected_ids)]))
            payload["deep_enabled"] = True
            payload["evaluation_candidate_ids"] = sorted(selected_ids)
        else:
            payload.pop("evaluation_candidate_ids", None)
        cid_strs = [str(cid) for cid in payload["candidate_ids"]]
        from backend.services.cv_library import require_available
        await require_available(cid_strs)
        records = []
        chunk_size = 500
        async with async_session_scope() as db:
            for i in range(0, len(cid_strs), chunk_size):
                chunk = cid_strs[i:i + chunk_size]
                sub = list((await db.scalars(select(CandidateModel).where(CandidateModel.id.in_(chunk)))).all())
                records.extend(sub)
        candidates = [AnonymizedCandidate.model_validate(record.anonymized_cv_json) for record in records]
        if {str(c.candidate_id): snapshot_hash(c.model_dump(mode="json")) for c in candidates} != payload["profile_hashes"]:
            raise HTTPException(409, "Candidate data changed or was removed. Start a new screening run.")
        history = payload.setdefault("attempt_history", [])
        history.append({"attempt": payload.get("attempt", 1), "model_configuration": payload.get("model_configuration", {})})
        payload.update(status="ranking", phase="Queued for retry", error=None, attempt=payload.get("attempt", 0) + 1,
            model_configuration={"provider": settings.llm_provider, "model": existing._get_active_model_for_provider(settings.llm_provider), "failover": settings.fallback_enabled})
        payload.setdefault("diagnostics", {}).setdefault("warnings", []).append("Additional evaluation uses current model settings; completed evaluations and ranking are retained.")
        frozen_client = None
        if payload.get("pipeline_version") == "v2" and payload["deep_enabled"]:
            frozen_client = DynamicLLMClient()
            await asyncio.to_thread(frozen_client.freeze_configuration)
        await save_run(payload)
        schedule_job(background_tasks, f"run:{payload['id']}", execute_rank, copy.deepcopy(payload), candidates, JobDescription.model_validate(payload["job"]), frozen_client)
        return payload


@router.get("/screening/runs/{run_id}")
async def get_run(run_id: UUID, job_id: UUID | None = None):
    payload = await read_run(run_id)
    if job_id and payload["job_id"] != str(job_id):
        raise HTTPException(409, "This screening run belongs to another job. Choose a run for the selected role.")
    return payload


@router.get("/screening/jobs/{job_id}/latest")
async def latest_run(job_id: UUID):
    async with async_session_scope() as db:
        record = await db.scalar(select(ScreeningRunModel).where(ScreeningRunModel.job_id == str(job_id)).order_by(ScreeningRunModel.created_at.desc(), ScreeningRunModel.id.desc()).limit(1))
        if not record:
            return None
        payload = copy.deepcopy(record.payload)
        if payload.get("rows") and not payload.get("evaluation_candidate_ids") and any(r.get("deep_status") == "completed" for r in payload["rows"]):
            payload["rows"] = sort_screening_rows(payload["rows"])
        return payload


@router.get("/screening/jobs/{job_id}/runs")
async def list_job_runs(job_id: UUID):
    """Lists historical screening runs for a job requisition (U4)."""
    async with async_session_scope() as db:
        records = await db.scalars(
            select(ScreeningRunModel)
            .where(ScreeningRunModel.job_id == str(job_id))
            .order_by(ScreeningRunModel.created_at.desc())
        )
        runs_list = []
        for r in records.all():
            p = r.payload or {}
            runs_list.append({
                "id": r.id,
                "job_id": r.job_id,
                "status": p.get("status"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "pipeline_version": p.get("pipeline_version"),
                "total_candidates": len(p.get("candidate_ids", [])),
                "ranked_candidates": len(p.get("rows", [])),
                "deep_completed": sum(1 for row in p.get("rows", []) if row.get("deep_status") == "completed"),
            })
        return runs_list


@router.post("/screening/runs/{run_id}/shortlist")
@record_operation("shortlist_creation", lambda a: {"run_id": a["run_id"]})
async def shortlist(run_id: UUID, request: ShortlistRequest):
    async with _run_lock:
        payload = await read_run(run_id)
        if payload["status"] not in {"completed", "partial"}:
            raise HTTPException(409, "Wait for ranking to finish before creating the comparison matrix.")
        if request.candidate_ids:
            requested = {str(cid) for cid in request.candidate_ids}
            rows = [row for row in payload["rows"] if row["candidate_id"] in requested]
            if len(rows) != len(requested):
                raise HTTPException(422, "Comparison candidates must belong to this run.")
        else:
            rows = [row for row in payload["rows"] if row["deep_status"] == "completed"][:request.count]
        if not rows or any(r["deep_status"] != "completed" for r in rows):
            raise HTTPException(409, "The selected top candidates need completed deep evaluations. Reduce the comparison count or rerun with a larger top K.")
        payload["shortlist_ids"] = [r["candidate_id"] for r in rows]
        await save_run(payload)
        return payload


@router.post("/screening/runs/{run_id}/decisions/{candidate_id}")
@record_operation("recruiter_review", lambda a: {"run_id": a["run_id"], "candidate_id": a["candidate_id"]})
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
        evaluation.update(hitl_validated=True, recommendation=recommendation, recruiter_decision=recommendation, recruiter_notes=request.notes)
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
    row = next((r for r in payload["rows"] if r["candidate_id"] == str(request.candidate_id)), None)
    if not row:
        raise HTTPException(404, "Candidate not found in screening run.")
    job_desc = JobDescription.model_validate(payload["job"])
    eval_dict = row.get("deep_evaluation")
    eval_id = UUID(eval_dict["id"]) if eval_dict and eval_dict.get("id") else uuid4()

    try:
        plan = await existing.generate_interview_plan(
            existing.InterviewGenerateRequest(
                candidate_id=request.candidate_id,
                evaluation_id=eval_id,
                job_description=job_desc,
                target_duration_minutes=request.duration_minutes,
                require_approval=False,
            )
        )
    except Exception as exc:
        logger.warning(
            "Primary interview generation failed or timed out (%s). Falling back to resilient rubric plan synthesis.",
            exc,
        )
        cand_tuple = existing._CANDIDATE_ANONYMIZED_STORE.get(request.candidate_id)
        if not cand_tuple:
            cand_rec = await DatabaseRepository.get_candidate(request.candidate_id)
            if cand_rec:
                _, cand_tuple, _ = existing._reconstruct_candidate_from_db(cand_rec)

        eval_result = None
        if eval_dict:
            try:
                eval_result = existing.MatchEvaluationResult.model_validate(eval_dict)
            except Exception:
                pass

        if cand_tuple and eval_result:
            plan = existing._interview_agent._synthesize_offline_rubric_plan(
                candidate=cand_tuple,
                job_description=job_desc,
                evaluation_result=eval_result,
                target_minutes=request.duration_minutes,
            )
        else:
            raise HTTPException(500, detail=f"Could not synthesize interview guide: {exc}")

    async with _run_lock:
        payload = await read_run(run_id)
        payload.setdefault("interviews", {})[str(request.candidate_id)] = plan.model_dump(mode="json")
        await save_run(payload)
    return plan


@router.post("/screening/jobs/parse")
@record_operation("job_extraction")
async def parse_job_draft(request: existing.JobTextParseRequest):
    """Extract an editable draft without creating a second, hidden job record."""
    try:
        return await asyncio.to_thread(existing._job_parser_agent.parse_job_text, request.text)
    except Exception as error:
        raise job_parse_http_error(error) from error


@router.post("/screening/jobs/parse-url")
@record_operation("job_extraction")
async def parse_job_url_draft(request: existing.JobUrlParseRequest):
    """Use the same URL extraction engine as Admin, returning a draft for review."""
    try:
        return await asyncio.to_thread(existing._job_parser_agent.parse_job_url, request.url)
    except Exception as error:
        raise job_parse_http_error(error) from error


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
    await DatabaseRepository.initialize_batch_files(batch_id, [name for name, _ in payloads])
    schedule_job(background_tasks, f"batch:{batch_id}", existing._batch_processor.execute_parse_batch, batch_id, payloads)
    return {"batch_id": str(batch_id), "total_files": len(payloads), "status": "PROCESSING"}


@router.get("/screening/llm/live-logs")
async def get_live_llm_logs(limit: int = Query(default=50, ge=1, le=200)):
    """
    Returns real-time LLM telemetry:
    - in_flight: list of active requests currently being generated on GPU/cloud with live elapsed timers
    - recent: completed actions with full prompts, raw model responses, parsed JSON, and errors
    """
    from backend.services.action_logger import action_logger
    return action_logger.get_live_state(limit=limit)


@router.post("/screening/llm/live-logs/clear")
async def clear_live_llm_logs():
    """Flushes in-memory LLM live action buffer and in-flight tracking."""
    from backend.services.action_logger import action_logger
    action_logger.clear()
    return {"status": "ok"}


class LocalModelLoadRequest(BaseModel):
    provider: str = Field(default="lmstudio", description="Local provider ('lmstudio' or 'ollama')")
    model: str = Field(description="Model identifier to load into GPU VRAM")
    context_window: int | None = Field(default=None, description="Context window size in tokens, or None to auto-tune based on detected VRAM")
    gpu_layers: int = Field(default=99, description="GPU layer offload count (99 for max)")
    gpu_offload_mode: str = Field(default="auto", description="GPU offload mode ('auto' for safe layer split on 4GB laptops, or 'max')")
    set_as_active: bool = Field(default=True, description="Hot-swap runtime LLM provider to this model")


class LocalModelUnloadRequest(BaseModel):
    provider: str = Field(default="lmstudio", description="Local provider ('lmstudio' or 'ollama')")
    model: str | None = Field(default=None, description="Model identifier to unload, or None for all")


class LocalServerStartRequest(BaseModel):
    provider: str = Field(default="lmstudio")
    port: int = Field(default=1234)


@router.get("/screening/local-models/status")
async def get_local_models_status():
    """
    Returns consolidated status of local LLM runtimes and NVIDIA GPU:
    - GPU hardware: RTX 4060 Ti, VRAM used/total, GPU utilization
    - LM Studio: HTTP availability, loaded models, catalog on disk, active model
    - Ollama: HTTP availability, VRAM loaded models, active model
    - High Context & Rolling Window configurations
    """
    from backend.services.local_model_service import local_model_service
    return local_model_service.get_full_state()


@router.post("/screening/local-models/load")
async def load_local_model(req: LocalModelLoadRequest):
    """
    Loads a local model into GPU VRAM with 100% GPU layer offload and 16,384 context length.
    Guarantees rolling context window to prevent out-of-memory errors during screening.
    """
    from backend.services.local_model_service import local_model_service
    result = local_model_service.load_model(
        provider=req.provider,
        model=req.model,
        context_window=req.context_window,
        gpu_layers=req.gpu_layers,
        gpu_offload_mode=req.gpu_offload_mode,
        set_as_active=req.set_as_active,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Model loading failed"))
    return result


@router.post("/screening/local-models/unload")
async def unload_local_model(req: LocalModelUnloadRequest):
    """
    Unloads local model(s) from VRAM immediately to free up GPU memory.
    """
    from backend.services.local_model_service import local_model_service
    result = local_model_service.unload_model(
        provider=req.provider,
        model=req.model,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Model unloading failed"))
    return result


@router.post("/screening/local-models/start-server")
async def start_local_server(req: LocalServerStartRequest):
    """
    Starts local LM Studio server on specified port (default 1234).
    """
    from backend.services.local_model_service import local_model_service
    result = local_model_service.start_lmstudio_server(port=req.port)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed starting server"))
    return result


@router.get("/screening/action-trace")
@router.get("/screening/jobs/{job_id}/action-trace")
async def action_trace(job_id: str | None = None, run_id: str | None = None):
    """
    Returns an end-to-end, high-fidelity audit trail formatted for AI agent analysis:
    - Raw unparsed JD and atomic criteria
    - Raw unparsed candidate CV texts, sanitized texts, and structured profiles
    - Chronological action log with exact LLM prompts, raw outputs, and parsed JSON payloads
    - Screening run results, scores, citations, reasoning, and interview plans
    """
    from datetime import datetime, timezone
    from backend.services.action_logger import action_logger

    async with async_session_scope() as db:
        job_record = None
        if job_id:
            try:
                job_record = await DatabaseRepository.get_job(UUID(job_id) if len(str(job_id)) == 36 else job_id, session=db)
            except Exception:
                job_record = None

        run_payload = None
        if run_id:
            try:
                run_rec = await db.get(ScreeningRunModel, str(run_id))
                if run_rec:
                    run_payload = copy.deepcopy(run_rec.payload)
                    if not job_record:
                        job_record = await DatabaseRepository.get_job(UUID(run_rec.job_id), session=db)
            except Exception:
                pass

        if not job_record:
            job_record = await db.scalar(
                select(JobRequisitionModel).order_by(JobRequisitionModel.created_at.desc(), JobRequisitionModel.id.desc()).limit(1)
            )

        if not run_payload and job_record:
            run_rec = await db.scalar(
                select(ScreeningRunModel)
                .where(ScreeningRunModel.job_id == str(job_record.id))
                .order_by(ScreeningRunModel.created_at.desc(), ScreeningRunModel.id.desc())
                .limit(1)
            )
            if run_rec:
                run_payload = copy.deepcopy(run_rec.payload)

        if run_payload and job_id and run_payload["job_id"] != str(job_id):
            raise HTTPException(409, "The selected run belongs to another job.")
        if job_id and (not job_record or str(job_record.id) != str(job_id)):
            raise HTTPException(404, "Job not found.")
        if run_id and (not run_payload or run_payload["id"] != str(run_id)):
            raise HTTPException(404, "Screening run not found.")
        job_data = None
        if job_record:
            job_data = {
                "id": str(job_record.id),
                "title": job_record.title,
                "department": job_record.department,
                "seniority_level": job_record.seniority_level,
                "location": job_record.location,
                "work_model": job_record.work_model,
                "employment_type": job_record.employment_type,
                "source_url": job_record.source_url,
                "raw_text": job_record.raw_text or "",
                "requirements": [
                    {
                        "id": req.id,
                        "title": req.title,
                        "category": str(getattr(req.category, "value", req.category)),
                        "weight": float(req.weight),
                        "description": req.description,
                        "minimum_years_experience": req.minimum_years_experience,
                    }
                    for req in (job_record.requirements or [])
                ],
                "custom_sections": job_record.custom_sections_json or [],
                "unused_details": job_record.unused_details_json or [],
            }

        if run_payload and run_payload.get("job"):
            job_data = {**(job_data or {}), **run_payload["job"]}

        cand_ids = []
        if run_payload and run_payload.get("candidate_ids"):
            cand_ids = [str(cid) for cid in run_payload["candidate_ids"]]
        elif run_payload and run_payload.get("rows"):
            cand_ids = [str(r["candidate_id"]) for r in run_payload["rows"]]

        if cand_ids:
            candidates_records = list((await db.scalars(select(CandidateModel).where(CandidateModel.id.in_(cand_ids)))).all())
        elif job_id or run_id:
            candidates_records = []
        else:
            candidates_records = list((await db.scalars(select(CandidateModel).order_by(CandidateModel.created_at.desc()).limit(50))).all())

        candidates_data = []
        for cr in candidates_records:
            c_raw = cr.raw_cv_json or {}
            c_contact = c_raw.get("contact_info") or {}
            c_name = c_contact.get("full_name") or cr.full_name_redacted or f"Candidate-{cr.id[:8].upper()}"
            raw_text = c_raw.get("raw_text") or cr.sanitized_text or ""
            candidates_data.append({
                "candidate_id": str(cr.id),
                "candidate_name": c_name,
                "original_filename": cr.original_filename,
                "raw_cv_text": raw_text,
                "sanitized_text": cr.sanitized_text,
                "anonymized_profile": cr.anonymized_cv_json,
                "created_at": cr.created_at.isoformat() if cr.created_at else None,
            })

        trace_run_id = run_payload.get("id") if run_payload else None
        captured = action_logger.get_logs(limit=0, job_id=str(job_record.id) if job_record else None, run_id=trace_run_id)
        if trace_run_id:
            stored = await db.scalars(select(AuditLogModel).where(
                AuditLogModel.entity_type == "screening_run", AuditLogModel.entity_id == trace_run_id,
                AuditLogModel.action == "model_call"))
            captured = [record.details_json for record in stored if record.details_json] + captured
        actions = list({entry["id"]: entry for entry in captured}.values())

        captured_count = len(actions)
        existing_action_keys = {
            (a.get("action_type"), a.get("metadata", {}).get("candidate_id"), a.get("metadata", {}).get("requirement_id"))
            for a in actions
        }

        if run_payload and run_payload.get("rows"):
            for row in run_payload["rows"]:
                deep_eval = row.get("deep_evaluation")
                matches = (deep_eval or {}).get("requirement_matches") or (deep_eval or {}).get("matches") or []
                if not matches:
                    continue
                cid = row.get("candidate_id")
                cname = row.get("candidate_name") or f"Candidate-{str(cid)[:8]}"
                for match in matches:
                    req_id = match.get("requirement_id")
                    if ("candidate_evaluation", cid, req_id) not in existing_action_keys:
                        actions.append({
                            "id": str(uuid4()),
                            "timestamp": deep_eval.get("created_at") or None,
                            "action_type": "candidate_evaluation",
                            "provider": run_payload.get("model_configuration", {}).get("provider", "system"),
                            "model": run_payload.get("model_configuration", {}).get("model", "system"),
                            "status": "success",
                            "latency_ms": 0.0,
                            "tokens": {
                                "prompt": 0,
                                "completion": 0,
                                "total": 0,
                            },
                            "prompt": f"Candidate: {cname} (ID: {cid})\nRequirement ID: {req_id}\nTitle: {match.get('title')}\nDescription: {match.get('jd_citation') or match.get('reasoning')}",
                            "system_prompt": "MatchingAgent candidate evaluation",
                            "raw_response": json.dumps(match, indent=2),
                            "parsed_json": match,
                            "error": None,
                            "metadata": {
                                "candidate_id": str(cid),
                                "candidate_name": cname,
                                "requirement_id": req_id,
                                "requirement_title": match.get("title"),
                                "synthetic_historical": True,
                                "source": "reconstructed_evaluation",
                                "run_id": trace_run_id,
                                "job_id": run_payload["job_id"],
                            },
                        })

        return {
            "export_metadata": {
                "schema_version": "2.0",
                "captured_actions": captured_count,
                "reconstructed_actions": sum(bool(entry.get("metadata", {}).get("synthetic_historical")) for entry in actions),
                "history_complete": False,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "job_id": job_data["id"] if job_data else None,
                "job_title": job_data["title"] if job_data else None,
                "run_id": run_payload.get("id") if run_payload else None,
                "total_actions": len(actions),
                "total_candidates": len(candidates_data),
                "active_engine": {
                    "provider": settings.llm_provider,
                    "model": existing._get_active_model_for_provider(settings.llm_provider),
                    "fallback_enabled": settings.fallback_enabled,
                },
                "instruction_for_agent": (
                    "This trace contains captured calls and explicitly marked reconstructed summaries; raw historical coverage may be incomplete. "
                    "Inspect 'job' for raw job description text and atomic requirements, 'candidates' for raw and parsed CVs, "
                    "'actions' for LLM prompts, raw outputs, and JSON outputs, and 'screening_run' for scores, citation "
                    "verifications, gap analyses, and interview plans."
                ),
            },
            "job": job_data,
            "candidates": candidates_data,
            "actions": actions,
            "screening_run": run_payload,
        }
