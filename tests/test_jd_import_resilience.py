"""JD document budgets and HTTP error contracts for both import surfaces."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.agents import llm_factory as factory
from backend.agents.job_parser_agent import StructuredJobPosting
from backend.api import routes
from backend.main import app
from backend.services.url_errors import URLResolutionError


def test_jd_budget_is_independent_of_short_decision_budget(monkeypatch):
    monkeypatch.setattr(factory.settings, "groq_max_output_tokens", 800)
    monkeypatch.setattr(factory.settings, "groq_jd_max_output_tokens", 8192)
    client = factory.GroqClient(api_key="synthetic-key", model="openai/gpt-oss-20b")
    client.client = MagicMock()
    client.secondary_client = client.tertiary_client = None
    client.client.chat.completions.create.return_value = SimpleNamespace(
        usage=None, choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"title":"Backend Engineer","requirements":[]}'))])
    result = client.generate_structured("Job description", StructuredJobPosting)
    assert result.title == "Backend Engineer"
    assert client.client.chat.completions.create.call_args.kwargs["max_tokens"] == 8192


@pytest.mark.parametrize("endpoint,method,payload", [
    ("/api/v1/screening/jobs/parse", "parse_job_text", {"text": "Backend engineer job"}),
    ("/api/v1/screening/jobs/parse-url", "parse_job_url", {"url": "https://example.com/jobs/backend"}),
    ("/api/v1/job/parse-text", "parse_job_text", {"text": "Backend engineer job"}),
    ("/api/v1/job/parse-url", "parse_job_url", {"url": "https://example.com/jobs/backend"}),
])
@pytest.mark.parametrize("failure,expected", [
    (factory.LLMProvidersCoolingDownError(12.2), 503),
    (URLResolutionError("jobs.atos.net"), 503),
    (factory.StructuredOutputTruncatedError("truncated"), 502),
    (RuntimeError("provider error containing synthetic-private-details"), 502),
    (ValueError("Cannot parse empty job posting text."), 400),
    (KeyError("synthetic-private-details"), 500),
])
def test_job_import_returns_actionable_json_errors(monkeypatch, endpoint, method, payload, failure, expected):
    monkeypatch.setattr(routes._job_parser_agent, method, MagicMock(side_effect=failure))
    response = TestClient(app, raise_server_exceptions=False).post(endpoint, json=payload)
    assert response.status_code == expected
    detail = response.json()["detail"]
    assert detail and detail != "Internal Server Error"
    assert "synthetic-private-details" not in detail
    if expected == 503:
        if isinstance(failure, URLResolutionError):
            assert response.headers["Retry-After"] == "2"
            assert "jobs.atos.net" in detail and "paste" in detail
        else:
            assert response.headers["Retry-After"] == "13"
            assert "13 seconds" in detail
    if expected >= 500:
        assert "Reference:" in detail
