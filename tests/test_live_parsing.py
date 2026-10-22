import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from backend.api import routes
from backend.api.cv_library import PrepareDocuments, prepare_documents
from backend.db.repository import DatabaseRepository
from backend.main import app
from backend.schemas.cv import ContactInfo, ParsedCV
from backend.services import cv_library as library
from backend.services.batch_processor import BatchProcessorService


@pytest.mark.asyncio
async def test_live_files_and_saved_profiles_are_visible_before_batch_finishes(monkeypatch):
    documents = [await library.store_file("same-name.txt", str(uuid4()).encode()) for _ in range(3)]
    started = [asyncio.Event() for _ in documents]
    gates = [asyncio.Event() for _ in documents]
    ids_by_content = {document.content: index for index, (document, _) in enumerate(documents)}

    async def process(self, content, filename, job_description=None):
        index = ids_by_content[content]
        started[index].set()
        await gates[index].wait()
        parsed = ParsedCV(contact_info=ContactInfo(full_name=f"Live candidate {uuid4()}"), skills=["Python"])
        anon = routes._parser_agent.pii_scrubber.anonymize_cv(parsed)
        await DatabaseRepository.save_candidate(parsed, anon, filename=filename)
        await library.attach_candidate(documents[index][0].id, anon.candidate_id)
        return {"filename": filename, "status": "COMPLETED", "candidate_id": str(anon.candidate_id)}

    monkeypatch.setattr(BatchProcessorService, "process_single_candidate", process)
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(3, batch_id=batch_id)
    task = asyncio.create_task(routes._batch_processor.execute_parse_batch(batch_id,
        [(document.filename, document.content) for document, _ in documents], 1, [document.id for document, _ in documents]))
    try:
        await asyncio.wait_for(started[0].wait(), 5)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            first = (await client.get(f"/api/v1/cv/batch/{batch_id}")).json()
            assert first["remaining_files"] == 3 and first["queued_files"] == 2
            assert [item["id"] for item in first["currently_processing"]] == ["0"]
            assert first["concurrency_limit"] == 1
            gates[0].set()
            await asyncio.wait_for(started[1].wait(), 5)
            midway = (await client.get(f"/api/v1/cv/batch/{batch_id}")).json()
            assert midway["status"] == "PROCESSING" and midway["processed_files"] == 1
            assert midway["remaining_files"] == 2 and midway["queued_files"] == 1
            assert [item["status"] for item in midway["files"]] == ["COMPLETED", "PROCESSING", "QUEUED"]
            cid = midway["files"][0]["candidate_id"]
            candidates = (await client.get("/api/v1/candidates?limit=100")).json()
            assert cid in {candidate["id"] for candidate in candidates}
            cvs = (await client.get("/api/v1/cv-library")).json()
            assert next(cv for cv in cvs if cv["id"] == documents[0][0].id)["candidate_id"] == cid
            # Cancelling keeps the finished profile and marks both unfinished files accurately.
            result = await client.post(f"/api/v1/screening/batches/{batch_id}/cancel")
            # Directly spawned test task is not registered with the API's background registry.
            assert result.status_code == 200
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            cancelled = (await client.get(f"/api/v1/cv/batch/{batch_id}")).json()
            assert cancelled["processed_files"] == 1 and not cancelled["currently_processing"]
            assert [item["status"] for item in cancelled["files"]] == ["COMPLETED", "CANCELLED", "CANCELLED"]
            assert await DatabaseRepository.get_candidate(cid)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_batch_limit_preserves_selection_order_and_skips_ready_profiles(monkeypatch):
    documents = [(await library.store_file(f"limit-{index}.txt", str(uuid4()).encode()))[0] for index in range(4)]
    await library.attach_candidate(documents[3].id, uuid4())
    seen = []

    async def capture(batch_id, files, concurrency, document_ids):
        seen.append((files, concurrency, document_ids))

    monkeypatch.setattr(routes._batch_processor, "execute_parse_batch", capture)
    background = BackgroundTasks()
    selection = [documents[index].id for index in [3, 1, 2, 0]]
    response = await prepare_documents(PrepareDocuments(ids=selection, limit=2, concurrency=1), background)
    assert response["total_files"] == 2 and response["remaining_unparsed"] == 1
    record = await DatabaseRepository.get_batch_job(response["batch_id"])
    assert [item["document_id"] for item in record.progress_json["files"]] == selection[1:3]
    assert all(item["status"] == "QUEUED" for item in record.progress_json["files"])
    await background()
    assert seen[0][1:] == (1, selection[1:3])
    assert [name for name, _ in seen[0][0]] == ["limit-1.txt", "limit-2.txt"]
    await DatabaseRepository.finish_batch_files(response["batch_id"], "CANCELLED")


@pytest.mark.parametrize("options", [{"limit": 0}, {"limit": 1001}, {"concurrency": 0}, {"concurrency": 5}])
def test_invalid_batch_limits_are_rejected(options):
    result = TestClient(app).post("/api/v1/cv-library/prepare", json={"ids": [str(uuid4())], **options})
    assert result.status_code == 422


@pytest.mark.asyncio
async def test_failures_are_reported_per_file_without_stopping_the_remaining_queue(monkeypatch):
    async def process(self, content, filename, job_description=None):
        if filename == "bad.txt":
            raise ValueError("Unreadable document")
        return {"filename": filename, "status": "COMPLETED", "candidate_id": str(uuid4())}

    monkeypatch.setattr(BatchProcessorService, "process_single_candidate", process)
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(3, batch_id=batch_id)
    await routes._batch_processor.execute_parse_batch(batch_id, [(name, b"test") for name in ["a.txt", "bad.txt", "b.txt"]], 1)
    result = await routes.get_batch_job_status(batch_id)
    assert result.status == "PARTIAL" and result.processed_files == 2 and result.failed_files == 1
    assert result.remaining_files == 0 and result.progress_percentage == 100
    assert result.files[1]["error"] == "Unreadable document"
    assert [item["status"] for item in result.files] == ["COMPLETED", "FAILED", "COMPLETED"]


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "INTERRUPTED"])
async def test_finished_parsing_session_cannot_be_replayed(monkeypatch, terminal):
    calls = []

    async def process(*args, **kwargs):
        calls.append(True)
        raise AssertionError("A finished session must not parse any CV again")

    monkeypatch.setattr(BatchProcessorService, "process_single_candidate", process)
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(1, batch_id=batch_id)
    await DatabaseRepository.initialize_batch_files(batch_id, ["finished.txt"])
    await DatabaseRepository.finish_batch_files(batch_id, terminal)
    before = await DatabaseRepository.get_batch_job(batch_id)
    await routes._batch_processor.execute_parse_batch(batch_id, [("finished.txt", b"finished CV")], 1)
    after = await DatabaseRepository.get_batch_job(batch_id)
    assert not calls
    assert after.status == terminal
    assert after.progress_json == before.progress_json


@pytest.mark.asyncio
async def test_reentered_active_batch_skips_files_already_finished(monkeypatch):
    calls = []

    async def process(self, content, filename, job_description=None):
        calls.append(filename)
        return {"filename": filename, "status": "COMPLETED", "candidate_id": str(uuid4())}

    monkeypatch.setattr(BatchProcessorService, "process_single_candidate", process)
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(2, batch_id=batch_id)
    documents = [(await library.store_file(name, str(uuid4()).encode()))[0] for name in ["done.txt", "next.txt"]]
    await DatabaseRepository.initialize_batch_files(batch_id, [d.filename for d in documents], 1, [d.id for d in documents])
    await DatabaseRepository.update_batch_progress(batch_id,
        {"file_id": "0", "filename": "done.txt", "status": "COMPLETED", "candidate_id": str(uuid4())})
    await routes._batch_processor.execute_parse_batch(batch_id, [(d.filename, d.content) for d in documents], 1, [d.id for d in documents])
    assert calls == ["next.txt"]
    final = await DatabaseRepository.get_batch_job(batch_id)
    assert final.status == "COMPLETED" and final.processed_files == 2
