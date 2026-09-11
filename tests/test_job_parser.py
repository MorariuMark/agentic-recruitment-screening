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


def test_api_parse_job_text_endpoint(monkeypatch):
    """Verify POST /api/v1/job/parse-text endpoint integration."""
    mock_jd = JobDescription(
        id=uuid4(),
        title="Senior Backend Go Developer",
        department="Core Infrastructure",
        seniority_level="Senior",
        requirements=[
            JobRequirement(
                id="req_go",
                title="Go & Concurrency",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Deep experience with Go concurrency patterns and gRPC.",
                minimum_years_experience=4,
            )
        ],
        raw_text="Senior Backend Go Developer text",
    )
    mock_result = JobExtractionResult(
        job_description=mock_jd,
        missing_fields=[],
        warnings=[],
    )

    monkeypatch.setattr(
        routes._job_parser_agent,
        "parse_job_text",
        lambda text: mock_result,
    )

    client = TestClient(app)
    res = client.post("/api/v1/job/parse-text", json={"text": "Senior Backend Go Developer text"})
    assert res.status_code == 200
    data = res.json()
    assert data["job_description"]["title"] == "Senior Backend Go Developer"
    assert len(data["job_description"]["requirements"]) == 1


def test_oracle_hcm_extraction_logic(monkeypatch):
    """Verify Oracle HCM Candidate Experience REST API detection and extraction."""
    mock_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <base data-fahosturl="https://fa-test.fa.ocs.oraclecloud.com" data-sitenumber="CX_1">
        <script src="https://static.oracle.com/cdn/fa/oj-hcm-ce/main.js"></script>
    </head>
    <body>
        <div class="app" data-bind="view: 'layout'"></div>
    </body>
    </html>
    """

    mock_oracle_json = {
        "items": [
            {
                "Id": "12345",
                "Title": "Principal Telecom Engineer",
                "Category": "Hardware R&D",
                "PrimaryLocation": "Munich, Germany",
                "WorkplaceType": "Hybrid",
                "ContractType": "Full-time",
                "ExternalDescriptionStr": "<p>Design optical networks and high-speed transceivers.</p>",
                "ExternalResponsibilitiesStr": "<ul><li>Architect optical transceivers</li><li>Lead hardware testing</li></ul>",
                "ExternalQualificationsStr": "<p>10+ years optical telecom experience with Python automation.</p>",
                "skills": [{"SkillName": "OTN"}, {"SkillName": "Python"}],
            }
        ]
    }

    class MockOracleResponse:
        def __init__(self, url, text="", json_data=None, status_code=200):
            self.url = url
            self.text = text
            self._json = json_data
            self.status_code = status_code
        def raise_for_status(self):
            pass
        def json(self):
            return self._json

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            if "fa-test.fa.ocs.oraclecloud.com" in url:
                return MockOracleResponse(url, json_data=mock_oracle_json)
            return MockOracleResponse(url, text=mock_html)

    monkeypatch.setattr("httpx.Client", MockHttpClient)

    extracted = fetch_url_content("https://jobs.test.com/en/sites/CX_1/jobs/preview/12345")
    assert "Job Title: Principal Telecom Engineer" in extracted
    assert "Location: Munich, Germany" in extracted
    assert "Work Model: Hybrid" in extracted
    assert "Design optical networks" in extracted
    assert "Architect optical transceivers" in extracted
    assert "10+ years optical telecom" in extracted
    assert "Tagged Skills:\nOTN, Python" in extracted


def test_json_ld_extraction_fallback(monkeypatch):
    """Verify JSON-LD JobPosting schema extraction when body is empty or client-rendered."""
    mock_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Careers Portal</title>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": "Staff AI Infrastructure Engineer",
            "description": "<p>Build high-throughput vector indexing and LLM inference clusters.</p>",
            "hiringOrganization": {"@type": "Organization", "name": "Atos Synthetics"},
            "jobLocation": {"address": {"addressLocality": "Paris", "addressCountry": "France"}},
            "employmentType": "FULL_TIME",
            "skills": "PyTorch, CUDA, Kubernetes"
        }
        </script>
    </head>
    <body>
        <div id="root"></div>
    </body>
    </html>
    """

    class MockResponse:
        text = mock_html
        status_code = 200
        def raise_for_status(self):
            pass

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockHttpClient)

    extracted = fetch_url_content("https://jobs.example.com/posting/ai-infra")
    assert "Job Title: Staff AI Infrastructure Engineer" in extracted
    assert "Company: Atos Synthetics" in extracted
    assert "Location: Paris, France" in extracted
    assert "Build high-throughput vector indexing" in extracted
    assert "Skills:\nPyTorch, CUDA, Kubernetes" in extracted


def test_meta_tags_extraction_fallback(monkeypatch):
    """Verify OpenGraph and Twitter meta tag fallback when body and JSON-LD are absent."""
    mock_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="og:title" content="Senior Cryptography Engineer">
        <meta property="og:description" content="We are seeking an experienced Cryptography Engineer to design secure post-quantum communication protocols and algorithms.">
        <meta name="keywords" content="cryptography, algorithms, post-quantum, C++">
    </head>
    <body>
        <div class="spa-container"></div>
    </body>
    </html>
    """

    class MockResponse:
        text = mock_html
        status_code = 200
        def raise_for_status(self):
            pass

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockHttpClient)

    extracted = fetch_url_content("https://jobs.example.com/crypto")
    assert "Job Title: Senior Cryptography Engineer" in extracted
    assert "secure post-quantum communication protocols" in extracted
    assert "Keywords & Skills:\ncryptography, algorithms, post-quantum, C++" in extracted


def test_next_data_extraction_logic(monkeypatch):
    """Verify Next.js (__NEXT_DATA__) structured script parsing."""
    mock_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Job Portal</title>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "job": {
                        "title": "Lead DevOps Engineer",
                        "companyName": "CloudScale Inc",
                        "locations": [{"name": "Cluj-Napoca"}, {"name": "Oradea"}],
                        "remote": false,
                        "partialRemote": true,
                        "spokenLanguages": [{"name": "English", "levelName": "Fluent"}],
                        "estimatedSalary": "4000 - 5000 EUR",
                        "description": "<p>Manage Kubernetes clusters and Terraform infrastructure.</p>"
                    }
                }
            }
        }
        </script>
    </head>
    <body><div>Container</div></body>
    </html>
    """

    class MockResponse:
        text = mock_html
        status_code = 200
        def raise_for_status(self):
            pass

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockHttpClient)

    extracted = fetch_url_content("https://jobs.example.com/devops")
    assert "Job Title: Lead DevOps Engineer" in extracted
    assert "Company: CloudScale Inc" in extracted
    assert "Target Locations: Cluj-Napoca, Oradea, Romania" in extracted
    assert "Work Model: Hybrid" in extracted
    assert "Required Languages: English (Fluent)" in extracted
    assert "Estimated Salary: 4000 - 5000 EUR" in extracted


def test_job_parser_agent_omitted_field_fallbacks():
    """Verify fallback heuristics for location, work model, and language when omitted by LLM."""
    incomplete_posting = StructuredJobPosting(
        title="Coordonator Departament Proiectare",
        department=None,  # Should fallback to Departament Proiectare
        seniority_level=None,  # Should fallback to Senior from Coordonator
        location=None,  # Should fallback to Timișoara, Arad, Romania
        work_model=None,  # Should fallback to On-site from 'vizite in teren'
        languages=[],  # Should fallback to Romanian & English
        requirements=[
            ExtractedRequirementItem(
                id="req_civil",
                title="Proiectare Drumuri",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Proiectare drumuri si platforme.",
            )
        ],
    )

    agent = JobParserAgent(llm_client=MockJobLLM(incomplete_posting))
    raw_text = """
    Page Title: Coordonator Departament Proiectare - Timișoara, Arad
    Cerinte:
    Studii superioare tehnice.
    Limba engleza avansat.
    Responsabilitati:
    Vizite in teren si asistenta tehnica.
    """

    result = agent.parse_job_text(raw_text)
    jd = result.job_description

    assert jd.seniority_level == "Senior"
    assert "Departament Proiectare" in jd.department
    assert "Timișoara" in jd.location or "Arad" in jd.location
    assert jd.work_model == "On-site"
    assert any("Romanian" in l for l in jd.languages)
    assert any("English" in l for l in jd.languages)
    # Check that on-site location requirement was generated
    assert any("location" in r.id.lower() or "on-site" in r.id.lower() for r in jd.requirements)


