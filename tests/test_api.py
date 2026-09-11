"""
tests/test_api.py
Integration tests for FastAPI REST endpoints using TestClient.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

import backend.api.routes as routes
from backend.main import app
from backend.schemas.cv import ContactInfo, ParsedCV, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import MatchEvaluationResult, Recommendation


@pytest.fixture
def api_client():
    """Provides a FastAPI TestClient."""
    return TestClient(app)


def test_health_and_root_endpoints(api_client):
    """Verify /health and root service endpoints."""
    res_health = api_client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    res_root = api_client.get("/")
    assert res_root.status_code == 200
    assert "docs_url" in res_root.json()


def test_cv_upload_pipeline(api_client, monkeypatch):
    """Verify POST /api/v1/cv/upload parses, scrubs PII, and indexes candidate."""
    mock_parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Alex Wright", email="alex@example.com"),
        skills=["Python", "FastAPI"],
        experiences=[
            WorkExperience(
                job_title="AI Engineer",
                company_name="NovaTech",
                work_description=["Alex Wright engineered RAG pipelines with Python."],
                skills_used=["Python"]
            )
        ]
    )

    # Mock parse_and_anonymize to isolate from external LLM costs during unit test run
    monkeypatch.setattr(
        routes._parser_agent,
        "parse_and_anonymize",
        lambda source, filename=None: (
            mock_parsed,
            routes._parser_agent.pii_scrubber.anonymize_cv(mock_parsed)
        )
    )

    dummy_content = b"Alex Wright resume with Python RAG experience."
    res = api_client.post(
        "/api/v1/cv/upload",
        files={"file": ("alex_cv.txt", dummy_content, "text/plain")}
    )
    assert res.status_code == 201
    data = res.json()
    assert "candidate_id" in data
    assert data["chunks_indexed"] > 0
    assert data["parsed_cv"]["contact_info"]["full_name"] == "Alex Wright"


def test_hitl_validation_endpoint(api_client):
    """Verify POST /api/v1/hitl/validate records recruiter decisions and notes."""
    eval_id = uuid4()
    candidate_id = uuid4()
    job_id = uuid4()

    mock_eval = MatchEvaluationResult(
        id=eval_id,
        candidate_id=candidate_id,
        job_id=job_id,
        overall_score=75.0,
        must_have_score=75.0,
        nice_to_have_score=75.0,
        recommendation=Recommendation.BORDERLINE,
        must_have_gaps_count=1,
        citation_verification_score=1.0,
        hitl_validated=False
    )
    routes._EVALUATION_STORE[eval_id] = mock_eval

    payload = {
        "evaluation_id": str(eval_id),
        "recruiter_decision": "strong_match",
        "recruiter_notes": "Recruiter verified candidate has equivalent transferrable skills."
    }
    res = api_client.post("/api/v1/hitl/validate", json=payload)
    assert res.status_code == 200
    updated = res.json()
    assert updated["recommendation"] == "strong_match"
    assert updated["hitl_validated"] is True
    assert "equivalent transferrable skills" in updated["recruiter_notes"]


def test_llm_settings_get_endpoint(api_client):
    """Verify GET /api/v1/settings/llm returns active configuration and full catalog."""
    res = api_client.get("/api/v1/settings/llm")
    assert res.status_code == 200
    data = res.json()
    assert "active_provider" in data
    assert "active_model" in data
    assert "compatibility_mode" in data
    assert "providers_catalog" in data
    catalog = data["providers_catalog"]
    assert "groq" in catalog
    assert "openrouter" in catalog
    assert "nvidia_nim" in catalog
    assert "gemini" in catalog
    assert "ollama" in catalog
    # Verify rate limits are present in model definitions
    for prov in catalog.values():
        for model in prov["models"]:
            assert "rate_limits" in model
            assert "context_window" in model


def test_llm_settings_update_endpoint(api_client):
    """Verify POST /api/v1/settings/llm dynamically hot-swaps provider and model."""
    payload = {
        "provider": "openrouter",
        "model": "openrouter/free",
        "compatibility_mode": "schema_prompt",
    }
    res = api_client.post("/api/v1/settings/llm", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["active_provider"] == "openrouter"
    assert data["active_model"] == "openrouter/free"
    assert data["compatibility_mode"] == "schema_prompt"


def test_llm_settings_test_endpoint_mock(api_client, monkeypatch):
    """Verify POST /api/v1/settings/test runs connection probe and measures latency."""
    class MockClient:
        def generate_text(self, prompt, temperature=0.0):
            return "CONNECTED"

    monkeypatch.setattr(
        "backend.api.routes.create_llm_client",
        lambda **kwargs: MockClient(),
    )

    payload = {
        "provider": "nvidia_nim",
        "model": "meta/llama-3.3-70b-instruct",
        "compatibility_mode": "auto",
        "api_key": "test-key-123",
    }
    res = api_client.post("/api/v1/settings/test", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["provider"] == "nvidia_nim"
    assert data["model"] == "meta/llama-3.3-70b-instruct"
    assert data["sample_output"] == "CONNECTED"
    assert data["latency_ms"] >= 0


def test_ollama_status_and_models_endpoints(api_client, monkeypatch):
    """Verify /api/v1/ollama/status and /api/v1/ollama/models endpoints."""
    monkeypatch.setattr(
        routes._ollama_service,
        "get_status",
        lambda: {"running": True, "version": "0.32.5", "installed": True, "base_url": "http://localhost:11434"}
    )
    monkeypatch.setattr(
        routes._ollama_service,
        "list_installed_models",
        lambda: [{"name": "qwen3.5:2b-q4_K_M", "size_gb": 1.81, "parameter_size": "2.3B", "family": "qwen35", "format": "gguf"}]
    )
    monkeypatch.setattr(
        routes._ollama_service,
        "list_running_models",
        lambda: [{"name": "qwen3.5:2b-q4_K_M", "size_vram_mb": 1500.0, "size_ram_mb": 0.0}]
    )

    res_stat = api_client.get("/api/v1/ollama/status")
    assert res_stat.status_code == 200
    assert res_stat.json()["running"] is True

    res_models = api_client.get("/api/v1/ollama/models")
    assert res_models.status_code == 200
    assert len(res_models.json()["installed"]) == 1
    assert len(res_models.json()["running"]) == 1


def test_ollama_load_and_unload_endpoints(api_client, monkeypatch):
    """Verify POST /api/v1/ollama/load and /api/v1/ollama/unload endpoints."""
    monkeypatch.setattr(
        routes._ollama_service,
        "load_model",
        lambda model_name, keep_alive="1h": {"success": True, "model": model_name, "keep_alive": keep_alive}
    )
    monkeypatch.setattr(
        routes._ollama_service,
        "unload_model",
        lambda model_name: {"success": True, "model": model_name}
    )

    res_load = api_client.post("/api/v1/ollama/load", json={"model": "qwen3.5:2b-q4_K_M", "keep_alive": "1h"})
    assert res_load.status_code == 200
    assert res_load.json()["success"] is True

    res_unload = api_client.post("/api/v1/ollama/unload", json={"model": "qwen3.5:2b-q4_K_M"})
    assert res_unload.status_code == 200
    assert res_unload.json()["success"] is True


