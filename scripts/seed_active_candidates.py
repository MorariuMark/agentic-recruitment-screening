"""
scripts/seed_active_candidates.py
Imports the 248 parsed active CV candidates from data/active_candidates/parsed_cvs.json
into SQLite (data/screening.db) and indexes their chunks into ChromaDB.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select

from backend.db.models import CandidateModel, CVDocumentModel
from backend.db.session import async_session_scope
from backend.schemas.cv import AnonymizedCandidate
from backend.services.vector_store import VectorStoreService


async def seed_active_candidates():
    json_path = Path("data/active_candidates/parsed_cvs.json")
    if not json_path.exists():
        print(f"Error: {json_path} not found.")
        return

    print("=" * 70)
    print("Loading active parsed candidates from data/active_candidates/parsed_cvs.json")
    print("=" * 70)

    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    total = len(records)
    print(f"Found {total} candidate records in JSON file.")

    vector_store = VectorStoreService()
    now = datetime.now(timezone.utc)

    added_candidates = 0
    updated_candidates = 0
    added_docs = 0
    indexed_chunks = 0

    async with async_session_scope() as db:
        existing_cand_ids = set((await db.scalars(select(CandidateModel.id))).all())
        existing_doc_cand_ids = set((await db.scalars(select(CVDocumentModel.candidate_id).where(CVDocumentModel.candidate_id.is_not(None)))).all())

        for idx, item in enumerate(records, start=1):
            cid = str(item["id"])
            filename = item.get("original_filename") or f"Candidate_{cid[:8]}.pdf"
            full_name = item.get("full_name_redacted") or f"Candidate-{cid[:8].upper()}"

            raw_cv = item.get("raw_cv") or {}
            anon_cv = item.get("anonymized_cv") or {}
            sanitized_text = item.get("sanitized_text") or ""
            demographics = item.get("demographics") or {}
            chunks_cnt = item.get("chunks_indexed", 0)

            # 1. Database CandidateModel
            if cid in existing_cand_ids:
                record = await db.get(CandidateModel, cid)
                if record:
                    record.original_filename = filename
                    record.full_name_redacted = full_name
                    record.raw_cv_json = raw_cv
                    record.anonymized_cv_json = anon_cv
                    record.sanitized_text = sanitized_text
                    record.demographics_json = demographics
                    record.updated_at = now
                    updated_candidates += 1
            else:
                record = CandidateModel(
                    id=cid,
                    original_filename=filename,
                    full_name_redacted=full_name,
                    raw_cv_json=raw_cv,
                    anonymized_cv_json=anon_cv,
                    sanitized_text=sanitized_text,
                    demographics_json=demographics,
                    chunks_indexed=chunks_cnt,
                    created_at=now,
                    updated_at=now,
                )
                db.add(record)
                existing_cand_ids.add(cid)
                added_candidates += 1

            # 2. Database CVDocumentModel for CV Library
            if cid not in existing_doc_cand_ids:
                doc = CVDocumentModel(
                    id=str(uuid4()),
                    filename=filename,
                    candidate_id=cid,
                    size_bytes=len(sanitized_text.encode("utf-8")),
                    created_at=now,
                )
                db.add(doc)
                existing_doc_cand_ids.add(cid)
                added_docs += 1

            # Commit in batches of 50
            if idx % 50 == 0:
                await db.commit()
                print(f"  [DB Progress] Processed {idx}/{total} candidates...")

        await db.commit()

    print(f"[DB Complete] Added {added_candidates} new candidates, updated {updated_candidates}, created {added_docs} CV documents.")

    # 3. Vector indexing in ChromaDB
    print("\nIndexing candidates into ChromaDB vector store...")
    for idx, item in enumerate(records, start=1):
        try:
            anon_cv = item.get("anonymized_cv") or {}
            if anon_cv:
                anon_obj = AnonymizedCandidate.model_validate(anon_cv)
                chunks = vector_store.index_candidate(anon_obj, force=False)
                indexed_chunks += chunks
        except Exception as e:
            print(f"  Warning: failed to index candidate {item.get('id')}: {e}")

        if idx % 50 == 0 or idx == total:
            print(f"  [Vector Progress] {idx}/{total} indexed ({indexed_chunks} chunks)...")

    print("\n" + "=" * 70)
    print(f"SUCCESS: {total} candidates are now loaded in SQLite and indexed in ChromaDB.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_active_candidates())
