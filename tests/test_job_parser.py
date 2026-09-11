"""
tests/test_job_parser.py
Unit and integration tests for JobParserAgent URL extraction, LLM structuring, and missing field auditing.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend.agents.job_parser_agent import (
    JobParserAgent,
    StructuredJobPosting,
    ExtractedRequirementItem,
    fetch_url_content,
)
from backend.agents.llm_factory import BaseLLMClient
from backend.main import app
import backend.api.routes as routes
from backend.schemas.job import (
    JobDescription,
    JobExtractionResult,
    JobRequirement,
    RequirementCategory,
)


class MockJobLLM(BaseLLMClient):
    """Mock LLM returning predefined StructuredJobPosting objects."""

    def __init__(self, structured_response: StructuredJobPosting) -> None:
        self.structured_response = structured_response

    def generate_text(self, prompt: str, system_prompt=None, temperature=0.1) -> str:
        return "mock job text"

    def generate_structured(self, prompt: str, response_model, system_prompt=None, temperature=0.0):
        return self.structured_response


def test_html_cleaning_logic(monkeypatch):
    """Verify fetch_url_content strips non-content tags (scripts, nav, styles)."""
    raw_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Careers Page</title><style>.hidden { display: none; }</style></head>
    <body>
        <nav><a href="/">Home</a><a href="/jobs">Jobs</a></nav>
        <main>
            <h1>Lead AI Platform Architect</h1>
            <p>We are seeking a senior architect to lead our RAG systems.</p>
            <ul>
                <li>5+ years experience in Python and distributed databases.</li>
            </ul>
        </main>
        <footer><p>Copyright 2026</p></footer>
        <script>console.log("tracking script");</script>
    </body>
    </html>
    """

    class MockResponse:
        text = raw_html
        def raise_for_status(self):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockClient)

    extracted = fetch_url_content("https://example.com/jobs/architect")
    assert "Lead AI Platform Architect" in extracted
    assert "5+ years experience" in extracted
    assert "tracking script" not in extracted
    assert "Copyright 2026" not in extracted
    assert "Home" not in extracted


def test_job_parser_agent_complete_posting():
    """Verify complete job posting extraction without missing critical criteria."""
    complete_posting = StructuredJobPosting(
        title="Senior Python Engineer",
        department="Core AI Systems",
        seniority_level="Senior",
        requirements=[
            ExtractedRequirementItem(
                id="req_python_rag",
                title="Python & RAG Systems",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Experience architecting RAG pipelines using Python and vector stores.",
                minimum_years_experience=4,
            ),
            ExtractedRequirementItem(
                id="req_docker",
                title="Docker & Kubernetes",
                category=RequirementCategory.NICE_TO_HAVE,
                weight=0.8,
                description="Containerized deployments in cloud environments.",
                minimum_years_experience=2,
            ),
        ],
    )

    agent = JobParserAgent(llm_client=MockJobLLM(complete_posting))
    result = agent.parse_job_text("Sample raw job description")

    assert result.job_description.title == "Senior Python Engineer"
    assert result.job_description.department == "Core AI Systems"
    assert len(result.job_description.requirements) == 2
    assert "Job Title" not in result.missing_fields
    assert "Must-Have Requirements" not in result.missing_fields
    assert len(result.warnings) == 0


def test_job_parser_agent_incomplete_posting_warnings():
    """Verify incomplete job posting triggers missing field flags and recruiter warnings."""
    incomplete_posting = StructuredJobPosting(
        title="Careers",  # Generic title
        department=None,
        seniority_level=None,
        requirements=[
            # Only nice to have, zero must-haves
            ExtractedRequirementItem(
                id="req_nice",
                title="Knowledge of GraphQL",
                category=RequirementCategory.NICE_TO_HAVE,
                weight=0.7,
                description="Nice to have GraphQL exposure.",
                minimum_years_experience=None,
            )
        ],
    )

    agent = JobParserAgent(llm_client=MockJobLLM(incomplete_posting))
    result = agent.parse_job_text("Sample incomplete posting")

    # Missing critical fields detected
    assert "Job Title" in result.missing_fields
    assert "Must-Have Requirements" in result.missing_fields
    assert "Department" in result.missing_fields
    assert "Seniority Level" in result.missing_fields

    # User warnings populated
    assert any("Job Title" in w for w in result.warnings)
    assert any("Must-Have" in w for w in result.warnings)


def test_api_parse_job_url_endpoint(monkeypatch):
    """Verify POST /api/v1/job/parse-url endpoint integration."""
    mock_jd = JobDescription(
        id=uuid4(),
        title="Staff ML Engineer",
        department="Platform",
        seniority_level="Staff",
        requirements=[
            JobRequirement(
                id="req_1",
                title="PyTorch & Transformers",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Hands-on model fine-tuning.",
                minimum_years_experience=5,
            )
        ],
        raw_text="Staff ML Engineer job description.",
    )
    mock_result = JobExtractionResult(
        job_description=mock_jd,
        missing_fields=[],
        warnings=[],
    )

    monkeypatch.setattr(
        routes._job_parser_agent,
        "parse_job_url",
        lambda url: mock_result,
    )

    client = TestClient(app)
    res = client.post("/api/v1/job/parse-url", json={"url": "https://example.com/job/123"})
    assert res.status_code == 200
    data = res.json()
    assert data["job_description"]["title"] == "Staff ML Engineer"
    assert len(data["job_description"]["requirements"]) == 1
    assert data["missing_fields"] == []
    assert data["warnings"] == []
