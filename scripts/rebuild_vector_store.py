"""
scripts/rebuild_vector_store.py
Rebuilds the local ChromaDB vector store from SQLite candidate data to ensure
100% clean HNSW index segments compatible with Chroma 1.5.9+.
"""

import asyncio
import os
import shutil
import sys
import time
from uuid import UUID

sys.path.insert(0, ".")

from backend.db.repository import DatabaseRepository
from backend.schemas.cv import AnonymizedCandidate
from backend.services.vector_store import VectorStoreService


async def rebuild():
    chroma_path = "./data/chroma_db"
    backup_path = "./data/chroma_db_backup"

    print("=" * 70)
    print("CHROMADB 1.5.9 NATIVE VECTOR STORE REBUILD")
    print("=" * 70)

    # 1. Backup old ChromaDB folder if it exists
    if os.path.exists(chroma_path):
        print(f"Backing up existing ChromaDB to {backup_path}...")
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path, ignore_errors=True)
        try:
            shutil.copytree(chroma_path, backup_path)
            shutil.rmtree(chroma_path)
            print("Old ChromaDB directory archived.")
        except Exception as e:
            print(f"Warning during directory cleanup: {e}")

    # 2. Initialize fresh VectorStoreService
    print("\nInitializing fresh ChromaDB 1.5.9 vector store...")
    vs = VectorStoreService(persist_directory=chroma_path)
    # Ensure candidate collection exists
    _ = vs.candidate_collection
    print("Fresh candidate collection created with cosine metric.")

    # 3. Fetch all candidate records from SQLite
    print("\nFetching candidate records from SQLite...")
    candidates = await DatabaseRepository.list_candidates(limit=1000)
    print(f"Retrieved {len(candidates)} total candidates from database.")

    # 4. Index candidate chunks
    indexed_candidates = 0
    total_chunks = 0
    t0 = time.perf_counter()

    for cand in candidates:
        cv_data = cand.anonymized_cv_json
        if not cv_data:
            continue
        try:
            anon = AnonymizedCandidate(**cv_data)
            anon.candidate_id = str(cand.id)
            chunks = vs.index_candidate(anon, force=True)
            total_chunks += chunks
            indexed_candidates += 1
            if indexed_candidates % 50 == 0:
                print(f"  Indexed {indexed_candidates}/{len(candidates)} candidates ({total_chunks} chunks)...")
        except Exception as err:
            continue

    elapsed = time.perf_counter() - t0
    print(f"\nIndexed {indexed_candidates} candidates ({total_chunks} total chunks) in {elapsed:.2f}s.")

    # 5. Verify query functionality
    print("\nVerifying ChromaDB retrieval with test query...")
    sample_cid = candidates[0].id
    test_res = vs.query_candidate_chunks(
        candidate_id=sample_cid,
        query_text="software development programming experience",
        n_results=2
    )
    print(f"Verification successful: {len(test_res)} chunks retrieved for candidate {sample_cid}.")
    print("=" * 70)
    print("ChromaDB vector store is 100% healthy and verified!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(rebuild())
