"""CV file storage, exact-byte deduplication and a recoverable 30-day trash."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from weakref import WeakValueDictionary

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import undefer

from backend.db.models import CVDocumentModel, CandidateModel, ScreeningRunModel
from backend.db.session import async_session_scope

library_lock = asyncio.Lock()
_file_locks = WeakValueDictionary()


class IngestionGate:
    """Allow concurrent parsing, but finish in-flight writes before library deletion."""
    def __init__(self):
        self.condition = asyncio.Condition()
        self.readers = 0
        self.writer = False
        self.waiting = 0

    @asynccontextmanager
    async def parsing(self, content):
        key = hashlib.sha256(content).hexdigest()
        lock = _file_locks.setdefault(key, asyncio.Lock())
        async with lock:
            async with self.condition:
                await self.condition.wait_for(lambda: not self.writer and not self.waiting)
                self.readers += 1
            try:
                yield
            finally:
                async with self.condition:
                    self.readers -= 1
                    self.condition.notify_all()

    @asynccontextmanager
    async def editing(self):
        async with self.condition:
            self.waiting += 1
            try:
                await self.condition.wait_for(lambda: not self.writer and self.readers == 0)
                self.writer = True
            finally:
                self.waiting -= 1
                self.condition.notify_all()
        try:
            yield
        finally:
            async with self.condition:
                self.writer = False
                self.condition.notify_all()


ingestion_gate = IngestionGate()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def describe(record):
    return dict(id=record.id, filename=record.filename, candidate_id=record.candidate_id,
                size=record.size_bytes,
                content_hash=record.content_hash, created_at=utc(record.created_at).isoformat(),
                deleted_at=utc(record.deleted_at).isoformat() if record.deleted_at else None,
                expires_at=(utc(record.deleted_at) + timedelta(days=30)).isoformat() if record.deleted_at else None)


async def store_file(filename, content):
    digest = hashlib.sha256(content).hexdigest()
    async with library_lock, async_session_scope() as db:
        record = await db.scalar(select(CVDocumentModel).options(undefer(CVDocumentModel.content)).where(CVDocumentModel.content_hash == digest))
        if record:
            # A hash match is also checked byte-for-byte before discarding the upload.
            if record.content != content:
                raise HTTPException(409, "File hash collision; import was not saved.")
            if not record.deleted_at:
                return record, True

            async def replace_trashed():
                from backend.api import routes
                from sqlalchemy import delete
                if record.candidate_id:
                    try:
                        await routes.delete_candidate(UUID(record.candidate_id))
                    except HTTPException as error:
                        if error.status_code != 404:
                            raise
                await db.execute(delete(CVDocumentModel).where(CVDocumentModel.id == record.id))
                replacement = CVDocumentModel(id=str(uuid4()), filename=filename, content_hash=digest,
                                              content=content, size_bytes=len(content))
                db.add(replacement)
                await db.commit()
                await db.refresh(replacement, ["content", "created_at"])
                return replacement, False

            # Finish replacing this one file even if a bulk import is cancelled midway.
            step = asyncio.create_task(replace_trashed())
            try:
                return await asyncio.shield(step)
            except asyncio.CancelledError:
                await step
                raise
        record = CVDocumentModel(id=str(uuid4()), filename=filename, content_hash=digest, content=content, size_bytes=len(content))
        db.add(record)
        await db.commit()
        await db.refresh(record, ["content", "created_at"])
        return record, False


async def attach_candidate(document_id, candidate_id):
    async with library_lock, async_session_scope() as db:
        legacy = await db.scalar(select(CVDocumentModel).where(CVDocumentModel.candidate_id == str(candidate_id), CVDocumentModel.id != document_id))
        if legacy:
            await db.delete(legacy)
            await db.flush()
        record = await db.get(CVDocumentModel, document_id)
        if record:
            record.candidate_id = str(candidate_id)
            await db.commit()


async def is_trashed(candidate_ids):
    async with async_session_scope() as db:
        hidden = set((await db.scalars(select(CVDocumentModel.candidate_id).where(CVDocumentModel.deleted_at.is_not(None)))).all())
        return bool(hidden.intersection(candidate_ids))


async def require_available(candidate_ids):
    if await is_trashed({str(id) for id in candidate_ids}):
        raise HTTPException(409, "Restore trashed CVs before using them in verification or interviews.")


async def sync_candidates():
    """Expose pre-existing profiles without inventing hashes for missing original files."""
    async with library_lock, async_session_scope() as db:
        linked = select(CVDocumentModel.candidate_id).where(CVDocumentModel.candidate_id.is_not(None))
        candidates = (await db.scalars(select(CandidateModel).where(CandidateModel.id.not_in(linked)))).all()
        for candidate in candidates:
            db.add(CVDocumentModel(id=str(uuid4()), filename=candidate.original_filename or "Existing CV",
                                  candidate_id=candidate.id, created_at=candidate.created_at))
        await db.commit()


async def change_documents(ids, action):
    from backend.api import routes
    from backend.services.process_control import jobs
    if any(key.startswith("batch:") for key in jobs):
        raise HTTPException(409, "Cancel active CV parsing before changing library files.")
    async with ingestion_gate.editing(), library_lock, async_session_scope() as db:
        # Select by set membership in Python to support large select-all operations on SQLite.
        records = [r for r in (await db.scalars(select(CVDocumentModel))).all() if r.id in set(ids)]
        if len(records) != len(set(ids)):
            raise HTTPException(404, "Some CVs no longer exist. Refresh the library.")
        candidate_ids = {r.candidate_id for r in records if r.candidate_id}
        runs = (await db.scalars(select(ScreeningRunModel))).all()
        if any(r.payload.get("status") in {"ranking", "evaluating"} and
               candidate_ids.intersection(r.payload.get("candidate_ids", [])) for r in runs):
            raise HTTPException(409, "Cancel the screening using these CVs before deleting or restoring them.")
        for record in records:
            if action == "trash":
                if not record.deleted_at:
                    record.deleted_at = datetime.now(timezone.utc)
            elif action == "restore":
                if record.deleted_at and utc(record.deleted_at) + timedelta(days=30) <= datetime.now(timezone.utc):
                    raise HTTPException(409, "This CV's 30-day retention period has expired.")
                record.deleted_at = None
            else:
                async def erase():
                    if record.candidate_id:
                        # Includes relational results, run redaction, vectors and in-memory caches.
                        try:
                            await routes.delete_candidate_profile(UUID(record.candidate_id), session=db)
                        except HTTPException as error:
                            if error.status_code != 404:
                                raise
                    # The shared candidate erasure may already have removed the original.
                    from sqlalchemy import delete
                    await db.execute(delete(CVDocumentModel).where(CVDocumentModel.id == record.id))
                    await db.commit()
                # Cancel between CVs; finish the current erasure so no original is left half deleted.
                step = asyncio.create_task(erase())
                try:
                    await asyncio.shield(step)
                except asyncio.CancelledError:
                    await step
                    raise
        await db.commit()
        return len(records)


async def purge_expired():
    async with async_session_scope() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        ids = list((await db.scalars(select(CVDocumentModel.id).where(CVDocumentModel.deleted_at <= cutoff))).all())
    if ids:
        await change_documents(ids, "delete")


async def maintenance_loop():
    import logging
    while True:
        try:
            await purge_expired()
        except Exception:
            logging.getLogger(__name__).exception("CV trash cleanup failed; will retry")
        await asyncio.sleep(60)
