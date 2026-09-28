"""
tests/test_job_requirements_api.py
Tests for Job Requisition criteria calibration and enhanced candidate pipeline listing.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend.db.repository import DatabaseRepository
from backend.main import app
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_job_crud_and_requirements_update(client):
    """Verify POST /jobs creates requisition and PUT /jobs/{id}/requirements updates criteria weights."""
    job_id = uuid4()
    job_data = {
        "id": str(job_id),
        "title": "Principal AI Platform Engineer",
        "department": "Infrastructure",
        "seniority_level": "Principal",
        "requirements": [
            {
                "id": "req_k8s",
                "title": "Kubernetes Architecture",
                "category": "must_have",
                "weight": 1.0,
                "description": "Production Kubernetes multi-cluster management",
                "minimum_years_experience": 5,
            },
            {
                "id": "req_fastapi",
                "title": "FastAPI Async Services",
                "category": "nice_to_have",
                "weight": 0.5,
                "description": "High-throughput asynchronous Python microservices",
            },
        ],
    }

    # 1. Create job via POST /api/v1/jobs
    res = client.post("/api/v1/jobs", json=job_data)
    assert res.status_code == 201
    created = res.json()
    assert created["id"] == str(job_id)
    assert len(created["requirements"]) == 2

    # 2. Update criteria weights and categories via PUT /api/v1/jobs/{job_id}/requirements
    updated_reqs = [
        {
            "id": "req_k8s",
            "title": "Kubernetes Architecture",
            "category": "must_have",
            "weight": 2.0,  # increased weight
            "description": "Production Kubernetes multi-cluster management",
            "minimum_years_experience": 6,
        },
        {
            "id": "req_fastapi",
            "title": "FastAPI Async Services",
            "category": "must_have",  # promoted to must-have
            "weight": 1.5,
            "description": "High-throughput asynchronous Python microservices",
        },
        {
            "id": "req_rag",
            "title": "Asymmetric RAG",
            "category": "nice_to_have",
            "weight": 1.0,
            "description": "Vector indexing with ChromaDB",
        },
    ]

    res_update = client.put(
        f"/api/v1/jobs/{job_id}/requirements",
        json={"requirements": updated_reqs},
    )
    assert res_update.status_code == 200
    updated_job = res_update.json()
    assert len(updated_job["requirements"]) == 3

    # 3. Verify changes persisted in database via GET /api/v1/jobs
    res_list = client.get("/api/v1/jobs")
    assert res_list.status_code == 200
    all_jobs = res_list.json()
    found = next((j for j in all_jobs if j["id"] == str(job_id)), None)
    assert found is not None
    assert len(found["requirements"]) == 3

    k8s_req = next(r for r in found["requirements"] if r["id"] == "req_k8s")
    assert k8s_req["weight"] == 2.0
    assert k8s_req["minimum_years_experience"] == 6

    fastapi_req = next(r for r in found["requirements"] if r["id"] == "req_fastapi")
    assert fastapi_req["category"] == "must_have"
    assert fastapi_req["weight"] == 1.5


def test_candidates_list_with_metadata(client):
    """Verify GET /api/v1/candidates returns structured metadata schema."""
    res = client.get("/api/v1/candidates")
    assert res.status_code == 200
    candidates = res.json()
    assert isinstance(candidates, list)
    if candidates:
        first = candidates[0]
        assert "id" in first
        assert "masked_name" in first
        assert "skills" in first
