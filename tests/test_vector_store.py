"""
tests/test_vector_store.py
Unit tests verifying local ChromaDB persistence, candidate chunking, and semantic querying.
"""

import shutil
from pathlib import Path
from uuid import uuid4
import pytest

from backend.schemas.cv import AnonymizedCandidate, WorkExperience
from backend.services.vector_store import VectorStoreService

TEST_CHROMA_DIR = "./data/chroma_db_pytest"


@pytest.fixture
def vector_service():
    """Provides a dedicated vector store service for testing."""
    svc = VectorStoreService(persist_directory=TEST_CHROMA_DIR)
    yield svc
    svc.reset()
    if Path(TEST_CHROMA_DIR).exists():
        shutil.rmtree(TEST_CHROMA_DIR, ignore_errors=True)


def test_index_and_query_candidate(vector_service):
    """Verify candidate experience bullets and skills are chunked and retrievable."""
    cid = uuid4()
    candidate = AnonymizedCandidate(
        candidate_id=cid,
        anonymized_work_experiences=[
            WorkExperience(
                job_title="MLOps Engineer",
                company_name="CloudAI",
                work_description=[
                    "Built real-time RAG systems with vector similarity search.",
                    "Configured automated deployment pipelines for LLM endpoints."
                ],
                skills_used=["Python", "ChromaDB"]
            )
        ],
        anonymized_education=[],
        anonymized_skills=["Python", "ChromaDB", "Docker"],
        demographic_data={}
    )

    indexed_count = vector_service.index_candidate(candidate)
    assert indexed_count == 3  # 2 bullets + 1 aggregated skills chunk

    # Query for vector similarity
    results = vector_service.query_candidate_chunks(
        candidate_id=cid,
        query_text="vector similarity search RAG",
        n_results=2
    )
    assert len(results) > 0
    top_result = results[0]
    assert "text" in top_result
    assert "distance" in top_result
    assert "metadata" in top_result
    assert top_result["metadata"]["candidate_id"] == str(cid)


def test_candidate_isolation_in_query(vector_service):
    """Verify queries strictly filter by candidate_id to avoid cross-candidate leakage."""
    cid_1 = uuid4()
    cand_1 = AnonymizedCandidate(
        candidate_id=cid_1,
        anonymized_work_experiences=[
            WorkExperience(
                job_title="Frontend Developer",
                company_name="WebCo",
                work_description=["Developed user interfaces in React and TypeScript."]
            )
        ],
        anonymized_education=[],
        anonymized_skills=["React", "TypeScript"],
        demographic_data={}
    )

    cid_2 = uuid4()
    cand_2 = AnonymizedCandidate(
        candidate_id=cid_2,
        anonymized_work_experiences=[
            WorkExperience(
                job_title="Database Admin",
                company_name="DataCo",
                work_description=["Managed Oracle and PostgreSQL clustering."]
            )
        ],
        anonymized_education=[],
        anonymized_skills=["PostgreSQL"],
        demographic_data={}
    )

    vector_service.index_candidate(cand_1)
    vector_service.index_candidate(cand_2)

    # Querying candidate 1 for database keywords must NOT return candidate 2's documents
    results = vector_service.query_candidate_chunks(
        candidate_id=cid_1,
        query_text="PostgreSQL clustering and database management",
        n_results=5
    )
    for r in results:
        assert r["metadata"]["candidate_id"] == str(cid_1)
