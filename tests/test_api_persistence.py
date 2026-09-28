"""
tests/test_api_persistence.py
Tests verifying that REST API endpoints seamlessly fall back to the relational database
when in-memory state caches are evicted or cleared.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

import backend.api.routes as routes
from backend.main import app
from backend.schemas.cv import ContactInfo, ParsedCV, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    Recommendation,
    RequirementMatch,
    VerbatimCitation,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_cv_persistence_survives_cache_clear(client, monkeypatch):
    """Verify CV upload persists to DB and is retrievable after memory cache is cleared."""
    mock_parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Sarah Connor", email="sarah@resistance.ai"),
        skills=["Python", "FastAPI", "Cybersecurity"],
        experiences=[
            WorkExperience(
                job_title="Security Lead",
                company_name="Skynet Defense",
                work_description=["Defended distributed systems against unauthorized access."],
                skills_used=["Python", "Cybersecurity"]
            )
        ]
    )

    monkeypatch.setattr(
        routes._parser_agent,
        "parse_and_anonymize",
        lambda source, filename=None: (
            mock_parsed,
            routes._parser_agent.pii_scrubber.anonymize_cv(mock_parsed)
        )
    )

    # 1. Upload CV
    res = client.post(
        "/api/v1/cv/upload",
        files={"file": ("sarah_cv.txt", b"Sarah Connor resume with Python experience.", "text/plain")}
    )
    assert res.status_code == 201
    cid = res.json()["candidate_id"]

    # 2. CLEAR ALL IN-MEMORY CACHES
    routes._CANDIDATE_RAW_STORE.clear()
    routes._CANDIDATE_ANONYMIZED_STORE.clear()
    routes._CANDIDATE_CHUNKS_STORE.clear()

    # 3. Export CV must still succeed via DB fallback
    res_export = client.get(f"/api/v1/cv/{cid}/export")
    assert res_export.status_code == 200
    export_data = res_export.json()
    assert export_data["candidate_id"] == cid
    assert any(item["category"] == "skills" for item in export_data["items"])


def test_list_candidates_and_jobs_endpoints(client):
    """Verify GET /api/v1/candidates and GET /api/v1/jobs return database records."""
    res_cands = client.get("/api/v1/candidates")
    assert res_cands.status_code == 200
    assert isinstance(res_cands.json(), list)

    res_jobs = client.get("/api/v1/jobs")
    assert res_jobs.status_code == 200
    assert isinstance(res_jobs.json(), list)


def test_get_candidate_detail_endpoint(client):
    """Verify GET /api/v1/candidates/{candidate_id} returns sanitized text and profile."""
    # List candidates to pick an existing id
    res_cands = client.get("/api/v1/candidates")
    assert res_cands.status_code == 200
    cands = res_cands.json()
    if cands:
        cid = cands[0]["id"]
        res_detail = client.get(f"/api/v1/candidates/{cid}")
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert detail["id"] == cid
        assert "sanitized_text" in detail
        assert "skills" in detail
        assert "experiences" in detail

