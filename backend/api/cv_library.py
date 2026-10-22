from backend.services.operation_timing import record_operation
import asyncio
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import undefer

from backend.api.auth import get_current_user
from backend.db.models import CVDocumentModel, BatchJobModel
from backend.db.session import async_session_scope
from backend.services import cv_library as library
from backend.services.process_control import CancellableRoute, requests, jobs, cancel_job, schedule_job, job_scopes, request_scope, resetting_scopes

router = APIRouter(prefix="/api/v1", dependencies=[Depends(get_current_user)], route_class=CancellableRoute)


@router.get("/cv-library")
async def list_documents():
    await library.purge_expired()
    await library.sync_candidates()
    async with async_session_scope() as db:
        return [library.describe(r) for r in (await db.scalars(select(CVDocumentModel).order_by(CVDocumentModel.created_at.desc()))).all()]


@router.post("/cv-library/import")
@record_operation("cv_import", lambda a: {"item_count": len(a["files"])})
async def import_documents(files: list[UploadFile] = File(...)):
    if not 1 <= len(files) <= 1000:
        raise HTTPException(400, "Choose 1–1000 CV files.")
    payloads, total = [], 0
    for file in files:
        filename = (file.filename or "").replace("\\", "/").split("/")[-1]
        content = await file.read(20 * 1024 * 1024 + 1)
        total += len(content)
        if not filename.lower().endswith((".pdf", ".docx", ".txt")) or not content or len(content) > 20 * 1024 * 1024:
            raise HTTPException(400, f"{filename}: use a non-empty PDF, DOCX or TXT up to 20 MB.")
        if total > 200 * 1024 * 1024:
            raise HTTPException(413, "Import at most 200 MB at once.")
        payloads.append((filename, content))
    imported = duplicates = 0
    for filename, content in payloads:
        _, duplicate = await library.store_file(filename, content)
        duplicates += int(duplicate)
        imported += int(not duplicate)
    return dict(imported=imported, duplicates_removed=duplicates)


@router.get("/cv-library/{document_id}/text")
async def document_text(document_id: UUID):
    """Preview the original without invoking AI parsing or creating a profile."""
    from backend.agents.parser_agent import extract_text_from_pdf, extract_text_from_docx
    from starlette.concurrency import run_in_threadpool
    async with async_session_scope() as db:
        record = await db.scalar(select(CVDocumentModel).options(undefer(CVDocumentModel.content))
                                 .where(CVDocumentModel.id == str(document_id)))
        if not record:
            raise HTTPException(404, "CV file not found.")
        content, filename = record.content, record.filename
    if not content:
        raise HTTPException(409, "The original file is unavailable. Reimport the CV to preview it.")
    try:
        if filename.lower().endswith(".pdf") or content.startswith(b"%PDF"):
            text = await run_in_threadpool(extract_text_from_pdf, content)
        elif filename.lower().endswith(".docx") or content.startswith(b"PK\x03\x04"):
            text = await run_in_threadpool(extract_text_from_docx, content)
        else:
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = content.decode("latin-1")
    except Exception as error:
        raise HTTPException(422, "The original CV text could not be extracted.") from error
    return {"id": str(document_id), "filename": filename, "text": text}


class LibraryAction(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=50000)
    action: Literal["trash", "restore", "delete"]


class PrepareDocuments(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=50000)
    limit: int = Field(default=25, ge=1, le=1000)
    concurrency: int = Field(default=4, ge=1, le=4)


@router.post("/cv-library/prepare", status_code=202)
async def prepare_documents(payload: PrepareDocuments, background_tasks: BackgroundTasks):
    from uuid import uuid4
    from backend.api.routes import _batch_processor
    from backend.db.repository import DatabaseRepository
    selected = list(dict.fromkeys(str(id) for id in payload.ids))
    async with async_session_scope() as db:
        records = []
        for start in range(0, len(selected), 400):
            records.extend((await db.scalars(select(CVDocumentModel).where(CVDocumentModel.id.in_(selected[start:start + 400])))).all())
        by_id = {record.id: record for record in records}
        if len(records) != len(selected) or any(r.deleted_at for r in records):
            raise HTTPException(409, "Choose available CVs from the active library.")
        eligible = [by_id[id] for id in selected if not by_id[id].candidate_id]
        chosen = eligible[:payload.limit]
        if not chosen:
            raise HTTPException(409, "These CVs have already been prepared for verification.")
        if any(not record.content_hash for record in chosen):
            raise HTTPException(409, "An original file is unavailable. Reimport the CV before parsing.")
        if sum(record.size_bytes or 0 for record in chosen) > 200 * 1024 * 1024:
            raise HTTPException(413, "Choose a smaller batch: parse at most 200 MB at once.")
        contents = {}
        for start in range(0, len(chosen), 400):
            chunk = [record.id for record in chosen[start:start + 400]]
            loaded = (await db.scalars(select(CVDocumentModel).options(undefer(CVDocumentModel.content)).where(CVDocumentModel.id.in_(chunk)))).all()
            contents.update({record.id: record.content for record in loaded})
        if any(not contents.get(record.id) for record in chosen):
            raise HTTPException(409, "An original file is unavailable. Refresh the library.")
        files = [(record.filename, contents[record.id]) for record in chosen]
        document_ids = [record.id for record in chosen]
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(len(files), batch_id=batch_id)
    await DatabaseRepository.initialize_batch_files(batch_id, [name for name, _ in files], payload.concurrency, document_ids)
    schedule_job(background_tasks, f"batch:{batch_id}", _batch_processor.execute_parse_batch, batch_id, files, payload.concurrency, document_ids)
    return {"batch_id": str(batch_id), "total_files": len(files), "remaining_unparsed": len(eligible) - len(files),
            "concurrency_limit": payload.concurrency, "status": "PROCESSING"}


@router.get("/processes")
async def active_jobs(request: Request):
    scope = request_scope(request)
    return [{"id": key, "label": "Screening candidates" if key.startswith("run:") else "Parsing CVs"}
            for key in jobs if not scope[1] or job_scopes.get(key) == scope]


@router.post("/processes/reset")
async def reset_workspace(request: Request):
    scope = request_scope(request)
    try:
        UUID(scope[1])
    except ValueError:
        raise HTTPException(400, "A valid browser-tab workspace ID is required.")
    if scope in resetting_scopes:
        raise HTTPException(409, "Workspace reset is already running.")
    resetting_scopes.add(scope)
    try:
        pending = [entry[1] for entry in list(requests.values()) if (entry[0], entry[2]) == scope]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        stopped = []
        # Includes jobs queued in a response but not yet started.
        for key, owner in list(job_scopes.items()):
            if owner != scope:
                continue
            kind, identifier = key.split(":", 1)
            if kind == "run":
                await cancel_screening(UUID(identifier))
            elif kind == "batch":
                await cancel_batch(UUID(identifier))
            stopped.append(key)
        return {"status": "reset", "stopped_jobs": stopped}
    finally:
        resetting_scopes.discard(scope)


@router.post("/cv-library/actions")
async def update_documents(payload: LibraryAction):
    return {"changed": await library.change_documents([str(id) for id in payload.ids], payload.action)}


@router.post("/processes/{process_id}/cancel")
async def cancel_request(process_id: UUID, request: Request):
    entry = requests.get(str(process_id))
    if entry:
        owner = request.headers.get("authorization") or request.cookies.get("atos_workspace", "")
        if entry[0] != owner:
            raise HTTPException(403, "This process belongs to another session.")
        entry[1].cancel()
        await asyncio.gather(entry[1], return_exceptions=True)
    return {"status": "cancelled" if entry else "finished"}


@router.post("/screening/runs/{run_id}/cancel")
async def cancel_screening(run_id: UUID):
    from backend.api.recruiter import read_run, save_run, _run_lock
    await cancel_job(f"run:{run_id}")
    async with _run_lock:
        payload = await read_run(run_id)
        if payload["status"] in {"ranking", "evaluating"}:
            payload.update(status="cancelled", phase="Cancelled", error="Cancelled by recruiter.")
            for row in payload["rows"]:
                if row.get("deep_status") == "pending":
                    row.update(deep_status="failed", error="Cancelled by recruiter.")
            await save_run(payload)
        return payload


@router.post("/screening/batches/{batch_id}/cancel")
async def cancel_batch(batch_id: UUID):
    await cancel_job(f"batch:{batch_id}")
    async with async_session_scope() as db:
        record = await db.get(BatchJobModel, str(batch_id))
        if not record:
            raise HTTPException(404, "Batch not found.")
        if record.status in {"QUEUED", "PROCESSING"}:
            record.status = "CANCELLED"
            await db.commit()
    from backend.db.repository import DatabaseRepository
    if record.status == "CANCELLED":
        await DatabaseRepository.finish_batch_files(batch_id, "CANCELLED", "Cancelled before completion")
    return {"status": record.status}
