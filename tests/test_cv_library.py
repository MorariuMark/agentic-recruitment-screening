import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api import routes
from backend.api.cv_library import router
from backend.db.models import CVDocumentModel, CandidateModel, ScreeningRunModel
from backend.db.repository import DatabaseRepository
from backend.db.session import async_session_scope
from backend.main import app
from backend.schemas.cv import ParsedCV, ContactInfo
from backend.services import cv_library as library
from backend.services.process_control import CancellableRoute, run_job, jobs, requests


def test_import_has_no_parser_or_screening_and_removes_exact_duplicates(monkeypatch):
    parser = Mock(side_effect=AssertionError("Import must never parse"))
    monkeypatch.setattr(routes._parser_agent, "parse_and_anonymize", parser)
    content = f"CV {uuid4()}".encode()
    client = TestClient(app)
    uid = uuid4().hex[:8]
    first_name = f"first_{uid}.txt"
    renamed_name = f"renamed_{uid}.txt"
    result = client.post("/api/v1/cv-library/import", files=[
        ("files", (first_name, content)), ("files", (renamed_name, content)),
        ("files", (first_name, content + b" changed"))])
    assert result.status_code == 200, result.text
    assert result.json() == {"imported": 2, "duplicates_removed": 1}
    assert not parser.called
    listed = client.get("/api/v1/cv-library").json()
    matching = [cv for cv in listed if cv["filename"] == first_name]
    assert len(matching) == 2
    assert all(cv["candidate_id"] is None for cv in matching)
    assert all("content" not in cv for cv in listed)


@pytest.mark.parametrize("filename,content", [("bad.exe", b"CV"), ("empty.txt", b"")])
def test_import_validation(filename, content):
    response = TestClient(app).post("/api/v1/cv-library/import", files={"files": (filename, content)})
    assert response.status_code == 400


def test_raw_preview_does_not_parse_or_create_a_profile(monkeypatch):
    from backend.agents.parser_agent import ParserAgent

    def forbidden(*args, **kwargs):
        raise AssertionError("Preview must never invoke the AI parser")

    monkeypatch.setattr(ParserAgent, "parse_and_anonymize", forbidden)
    client = TestClient(app)
    name = f"raw-preview-{uuid4()}.txt"
    raw = f"Original CV {uuid4()}\nSkills: Python & SQL\n<script>plain text</script>"
    assert client.post("/api/v1/cv-library/import", files={"files": (name, raw.encode())}).status_code == 200
    document = next(cv for cv in client.get("/api/v1/cv-library").json() if cv["filename"] == name)
    preview = client.get(f"/api/v1/cv-library/{document['id']}/text")
    assert preview.status_code == 200
    assert preview.json()["text"] == raw
    refreshed = next(cv for cv in client.get("/api/v1/cv-library").json() if cv["id"] == document["id"])
    assert refreshed["candidate_id"] is None
    assert client.get(f"/api/v1/cv-library/{uuid4()}/text").status_code == 404


def test_preparing_is_explicit_and_repeated_uploads_reuse_profile(monkeypatch):
    from backend.agents.parser_agent import ParserAgent
    calls = []
    parsed = ParsedCV(contact_info=ContactInfo(full_name="Explicit preparation"), skills=["Python"])

    def parse(self, source, filename=None):
        calls.append(filename)
        return parsed, self.pii_scrubber.anonymize_cv(parsed)

    monkeypatch.setattr(ParserAgent, "parse_and_anonymize", parse)
    monkeypatch.setattr(routes._vector_store, "index_candidate", lambda candidate: 2)
    name = f"explicit-{uuid4()}.txt"
    content = f"Independent CV {uuid4()}".encode()
    client = TestClient(app)
    assert client.post("/api/v1/cv-library/import", files={"files": (name, content)}).status_code == 200
    assert not calls
    document = next(cv for cv in client.get("/api/v1/cv-library").json() if cv["filename"] == name)
    assert document["size"] == len(content)
    response = client.post("/api/v1/cv-library/prepare", json={"ids": [document["id"]]})
    assert response.status_code == 202, response.text
    batch = client.get(f"/api/v1/cv/batch/{response.json()['batch_id']}").json()
    assert batch["status"] == "COMPLETED", batch
    assert calls == [name]
    cid = batch["results"][0]["candidate_id"]
    repeat = client.post("/api/v1/cv/upload", files={"file": ("another-name.txt", content)})
    assert repeat.status_code == 201, repeat.text
    assert repeat.json()["candidate_id"] == cid
    assert calls == [name]


def test_library_and_cancellation_require_auth(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "auth_required", True)
    client = TestClient(app)
    assert client.get("/api/v1/cv-library").status_code == 401
    assert client.post(f"/api/v1/processes/{uuid4()}/cancel").status_code == 401


@pytest.mark.asyncio
async def test_trash_restore_expiry_and_exact_duplicate_in_trash():
    record, _ = await library.store_file("retention.txt", str(uuid4()).encode())
    await library.change_documents([record.id], "trash")
    async with async_session_scope() as db:
        first = (await db.get(CVDocumentModel, record.id)).deleted_at
    await library.change_documents([record.id], "trash")
    async with async_session_scope() as db:
        assert (await db.get(CVDocumentModel, record.id)).deleted_at == first
    await library.change_documents([record.id], "restore")
    async with async_session_scope() as db:
        stored = await db.get(CVDocumentModel, record.id)
        assert stored.deleted_at is None
        stored.deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
        await db.commit()
    with pytest.raises(HTTPException):
        await library.change_documents([record.id], "restore")
    await library.purge_expired()
    async with async_session_scope() as db:
        assert await db.get(CVDocumentModel, record.id) is None


@pytest.mark.asyncio
async def test_existing_profiles_listed_trash_hidden_restore_permanent_removes_data(monkeypatch):
    parsed = ParsedCV(contact_info=ContactInfo(full_name="Library Test"), skills=["Python"])
    anonymized = routes._parser_agent.pii_scrubber.anonymize_cv(parsed)
    candidate = await DatabaseRepository.save_candidate(parsed, anonymized, filename="legacy.txt")
    await library.sync_candidates()
    async with async_session_scope() as db:
        from sqlalchemy import select
        record = await db.scalar(select(CVDocumentModel).where(CVDocumentModel.candidate_id == candidate.id))
    assert record.content_hash is None  # No unsafe deduplication based on contact identity.
    await library.change_documents([record.id], "trash")
    assert await DatabaseRepository.get_candidate(candidate.id) is None
    assert candidate.id not in {c.id for c in await DatabaseRepository.list_candidates(50000)}
    await library.change_documents([record.id], "restore")
    assert await DatabaseRepository.get_candidate(candidate.id)
    remove_vectors = Mock(return_value=1)
    monkeypatch.setattr(routes._vector_store, "delete_candidate", remove_vectors)
    await library.change_documents([record.id], "delete")
    remove_vectors.assert_called_once()
    async with async_session_scope() as db:
        assert await db.get(CandidateModel, candidate.id) is None
        assert await db.get(CVDocumentModel, record.id) is None


@pytest.mark.asyncio
async def test_background_and_request_cancellation_stop_later_side_effects():
    started = asyncio.Event()
    persisted = []
    mini = FastAPI()
    mini.include_router(router)
    from fastapi import APIRouter
    controlled = APIRouter(route_class=CancellableRoute)

    @controlled.post("/slow")
    async def slow():
        started.set()
        await asyncio.Event().wait()
        persisted.append(True)

    mini.include_router(controlled)
    process_id = str(uuid4())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mini), base_url="http://test") as client:
        pending = asyncio.create_task(client.post("/slow", headers={"X-Process-ID": process_id}))
        await started.wait()
        result = await client.post(f"/api/v1/processes/{process_id}/cancel")
        assert result.status_code == 200
        assert (await pending).status_code == 409
    assert not persisted and process_id not in requests
    started.clear()
    pending = asyncio.create_task(run_job("test-job", slow))
    await started.wait()
    from backend.services.process_control import cancel_job
    await cancel_job("test-job")
    await pending
    assert not persisted and "test-job" not in jobs


@pytest.mark.asyncio
async def test_cancel_durable_run_and_batch():
    from backend.api.cv_library import cancel_screening, cancel_batch
    from backend.api.recruiter import save_run, read_run
    run_id, job_id, cid = str(uuid4()), str(uuid4()), str(uuid4())
    payload = {"id": run_id, "job_id": job_id, "status": "evaluating", "candidate_ids": [cid],
               "rows": [{"candidate_id": cid, "deep_status": "pending"}], "attempt": 0}
    await save_run(payload)
    result = await cancel_screening(UUID(run_id))
    assert result["status"] == "cancelled"
    assert (await read_run(run_id))["rows"][0]["deep_status"] == "failed"
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(3, batch_id=batch_id)
    await cancel_batch(batch_id)
    assert (await DatabaseRepository.get_batch_job(batch_id)).status == "CANCELLED"


@pytest.mark.asyncio
async def test_no_deletion_during_screening():
    record, _ = await library.store_file("busy.txt", str(uuid4()).encode())
    cid = str(uuid4())
    await library.attach_candidate(record.id, cid)
    run_id = str(uuid4())
    async with async_session_scope() as db:
        db.add(ScreeningRunModel(id=run_id, job_id=str(uuid4()), payload={"status": "ranking", "candidate_ids": [cid]}))
        await db.commit()
    with pytest.raises(HTTPException) as error:
        await library.change_documents([record.id], "delete")
    assert error.value.status_code == 409
    async with async_session_scope() as db:
        await db.delete(await db.get(ScreeningRunModel, run_id))
        await db.commit()
    await library.change_documents([record.id], "trash")


def test_vector_deletion_uses_all_chunks_without_cache_conditions():
    from backend.services.vector_store import VectorStoreService
    store = object.__new__(VectorStoreService)
    store.candidate_collection = Mock()
    store.candidate_collection.get.return_value = {"ids": ["old", "new"]}
    assert store.delete_candidate("candidate") == 2
    store.candidate_collection.delete.assert_called_once_with(ids=["old", "new"])


@pytest.mark.asyncio
async def test_distinct_cvs_parse_concurrently_but_exact_duplicates_only_once(monkeypatch):
    from backend.services.batch_processor import BatchProcessorService
    monkeypatch.setattr(library, "ingestion_gate", library.IngestionGate())
    processor = BatchProcessorService()
    active = maximum = calls = 0
    both_started = asyncio.Event()

    async def parse(content, filename, job_description=None):
        nonlocal active, maximum, calls
        active += 1
        maximum = max(maximum, active)
        calls += 1
        if calls == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=5)
        active -= 1
        return {"candidate_id": str(uuid4()), "filename": filename, "status": "COMPLETED"}

    monkeypatch.setattr(processor, "_process_single_candidate", parse)
    first, second = str(uuid4()).encode(), str(uuid4()).encode()
    results = await asyncio.gather(processor.process_single_candidate(first, "a.txt"),
                                   processor.process_single_candidate(first, "copy.txt"),
                                   processor.process_single_candidate(second, "b.txt"))
    assert calls == 2 and maximum == 2
    assert results[0]["candidate_id"] == results[1]["candidate_id"]


@pytest.mark.asyncio
async def test_reupload_replaces_trashed_original_and_erases_old_profile(monkeypatch):
    parsed = ParsedCV(contact_info=ContactInfo(full_name="Replace trashed CV"), skills=["Python"])
    anon = routes._parser_agent.pii_scrubber.anonymize_cv(parsed)
    candidate = await DatabaseRepository.save_candidate(parsed, anon, filename="old.txt")
    content = str(uuid4()).encode()
    old, _ = await library.store_file("old.txt", content)
    await library.attach_candidate(old.id, candidate.id)
    await library.change_documents([old.id], "trash")
    vectors = Mock(return_value=2)
    monkeypatch.setattr(routes._vector_store, "delete_candidate", vectors)
    replacement, duplicate = await library.store_file("new-name.txt", content)
    assert not duplicate and replacement.id != old.id
    assert replacement.filename == "new-name.txt"
    assert replacement.deleted_at is None and replacement.candidate_id is None
    assert replacement.content == content
    vectors.assert_called_once()
    async with async_session_scope() as db:
        assert await db.get(CandidateModel, candidate.id) is None
        assert await db.get(CVDocumentModel, old.id) is None
        assert await db.get(CVDocumentModel, replacement.id)
    retained, duplicate = await library.store_file("another-name.txt", content)
    assert duplicate and retained.id == replacement.id


@pytest.mark.asyncio
async def test_workspace_reset_cancels_only_its_tabs_requests_and_background_jobs():
    from fastapi import APIRouter, BackgroundTasks
    from backend.services.process_control import schedule_job, job_scopes
    mini = FastAPI()
    mini.include_router(router)
    controlled = APIRouter(route_class=CancellableRoute)
    tab_a, tab_b = str(uuid4()), str(uuid4())
    batch_a, batch_b = uuid4(), uuid4()
    started = {str(batch_a): asyncio.Event(), str(batch_b): asyncio.Event()}
    slow_started = asyncio.Event()

    async def parse_forever(identifier):
        started[str(identifier)].set()
        await asyncio.Event().wait()

    @controlled.post("/launch")
    async def launch(identifier: UUID, background_tasks: BackgroundTasks):
        await DatabaseRepository.create_batch_job(2, batch_id=identifier)
        schedule_job(background_tasks, f"batch:{identifier}", parse_forever, identifier)
        return {"batch_id": str(identifier)}

    @controlled.post("/slow")
    async def slow():
        slow_started.set()
        await asyncio.Event().wait()

    mini.include_router(controlled)
    owner = "Bearer shared-session"
    headers_a = {"X-Workspace-ID": tab_a, "Authorization": owner}
    headers_b = {"X-Workspace-ID": tab_b, "Authorization": owner}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mini), base_url="http://test") as client:
        a = asyncio.create_task(client.post(f"/launch?identifier={batch_a}", headers=headers_a))
        b = asyncio.create_task(client.post(f"/launch?identifier={batch_b}", headers=headers_b))
        slow_request = asyncio.create_task(client.post("/slow", headers={**headers_a, "X-Process-ID": str(uuid4())}))
        try:
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values()), slow_started.wait()), 5)
            result = await client.post("/api/v1/processes/reset", headers=headers_a)
            assert result.status_code == 200, result.text
            assert result.json()["stopped_jobs"] == [f"batch:{batch_a}"]
            assert (await slow_request).status_code == 409
            assert (await a).status_code == 200
            assert not b.done() and f"batch:{batch_b}" in jobs
            assert (await DatabaseRepository.get_batch_job(batch_a)).status == "CANCELLED"
            assert (await DatabaseRepository.get_batch_job(batch_b)).status == "PROCESSING"
            visible = (await client.get("/api/v1/processes", headers=headers_b)).json()
            assert [entry["id"] for entry in visible] == [f"batch:{batch_b}"]
            assert (await client.post("/api/v1/processes/reset")).status_code == 400
        finally:
            await client.post(f"/api/v1/screening/batches/{batch_b}/cancel", headers=headers_b)
            await asyncio.gather(a, b, slow_request, return_exceptions=True)
    assert f"batch:{batch_a}" not in job_scopes and f"batch:{batch_b}" not in job_scopes


@pytest.mark.asyncio
async def test_reset_prevents_a_queued_background_job_from_starting():
    from fastapi import BackgroundTasks, Request
    from backend.api.cv_library import reset_workspace
    from backend.services.process_control import schedule_job, workspace_scope
    tab_id, batch_id = str(uuid4()), uuid4()
    await DatabaseRepository.create_batch_job(1, batch_id=batch_id)
    background = BackgroundTasks()
    called = []

    async def queued():
        called.append(True)

    token = workspace_scope.set(("Bearer queue-owner", tab_id))
    try:
        schedule_job(background, f"batch:{batch_id}", queued)
    finally:
        workspace_scope.reset(token)
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer queue-owner"), (b"x-workspace-id", tab_id.encode())]})
    assert (await reset_workspace(request))["status"] == "reset"
    await background()
    assert not called
    assert (await DatabaseRepository.get_batch_job(batch_id)).status == "CANCELLED"
