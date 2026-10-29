"""
tests/test_asap_chat.py
Comprehensive test suite for ASAP Chat Agent, live database context,
streaming endpoint, and failover engine integration.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.auth import create_session_token
from backend.agents.asap_chat_agent import AsapChatAgent, _tokenize
from backend.db.repository import DatabaseRepository
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory


@pytest.fixture
def auth_client():
    client = TestClient(app)
    token = create_session_token("admin")
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_asap_greetings_endpoint(auth_client):
    """Verifies that greetings endpoint returns varied greeting messages."""
    response = auth_client.get("/api/v1/asap/greetings")
    assert response.status_code == 200
    greetings = response.json()
    assert isinstance(greetings, list)
    assert len(greetings) >= 4
    assert any("ASAP" in g for g in greetings)
    assert any("screening assistant" in g.lower() for g in greetings)


def test_asap_chat_unauthorized():
    """Verifies that unauthenticated requests to chat endpoint are rejected with 401 when auth_required is True."""
    client = TestClient(app)
    with patch("backend.config.settings.auth_required", True):
        response = client.post("/api/v1/asap/chat", json={
            "messages": [{"role": "user", "content": "Hello"}]
        })
        assert response.status_code == 401


def test_asap_chat_authorized_mocked(auth_client):
    """Verifies that chat endpoint correctly forwards to AsapChatAgent and returns response."""
    with patch("backend.agents.asap_chat_agent.get_llm_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.model = "qwen/qwen3.8-27b"
        mock_client.generate_text.return_value = "Hello! I am ASAP, your candidate screening assistant."
        mock_client.get_last_usage.return_value = {
            "prompt_tokens": 15,
            "completion_tokens": 12,
            "total_tokens": 27,
            "model": "qwen/qwen3.8-27b",
            "provider": "groq",
            "latency_ms": 320.0,
        }
        mock_client.get_model_name.return_value = "qwen/qwen3.8-27b"
        mock_get_client.return_value = mock_client

        response = auth_client.post("/api/v1/asap/chat", json={
            "messages": [{"role": "user", "content": "What are your core screening capabilities?"}],
            "context": {"active_step": "pipeline"}
        })

        assert response.status_code == 200
        data = response.json()
        assert "ASAP" in data["reply"]
        assert data["model"] == "qwen/qwen3.8-27b"
        assert data["provider"] == "groq"
        assert "usage" in data
        assert "sources" in data


def test_asap_chat_stream_endpoint(auth_client):
    """Verifies that the /chat/stream SSE endpoint streams events successfully."""
    response = auth_client.post(
        "/api/v1/asap/chat/stream",
        json={"messages": [{"role": "user", "content": "Say hello in 2 words"}]},
    )
    assert response.status_code == 200
    lines = [line for line in response.iter_lines() if line]
    assert len(lines) >= 2
    # Verify at least one start/chunk/done event
    events = [json.loads(line.replace("data: ", "")) for line in lines if line.startswith("data: ")]
    event_types = {e.get("type") for e in events}
    assert "start" in event_types or "chunk" in event_types or "done" in event_types


@pytest.mark.asyncio
async def test_asap_context_retrieval_job_query():
    """Verifies that AsapChatAgent retrieves live job data when asked about jobs."""
    job_id = uuid4()
    req = JobRequirement(
        id="req-cloud-1",
        title="AWS & Kubernetes Architecture",
        category=RequirementCategory.MUST_HAVE,
        weight=1.0,
        description="Design container clusters",
        minimum_years_experience=4,
    )
    job = JobDescription(
        id=job_id,
        title="Lead Cloud Infrastructure Architect",
        department="Platform Engineering",
        seniority_level="Lead",
        raw_text="Lead the multi-region cloud team.",
        requirements=[req],
    )
    await DatabaseRepository.save_job(job)

    agent = AsapChatAgent()
    context_str, sources = await agent._retrieve_live_context(
        query="What are the requirements for Lead Cloud Infrastructure Architect?",
        context={}
    )
    assert len(context_str) > 0
    assert "CURRENT APP LIVE DATABASE SNAPSHOT" in context_str
    assert any("Lead Cloud Infrastructure Architect" in s.get("title", "") for s in sources)


@pytest.mark.asyncio
async def test_asap_context_retrieval_live_runs():
    """Verifies that AsapChatAgent retrieves live screening runs from the database."""
    agent = AsapChatAgent()
    context_str, sources = await agent._retrieve_live_context(
        query="What was our latest screening run in the system?",
        context={}
    )
    assert "CURRENT APP LIVE DATABASE SNAPSHOT" in context_str


def test_tokenize_helper():
    """Verifies keyword extraction helper."""
    tokens = _tokenize("What are the key requirements for Senior Cloud & DevOps Engineer?")
    assert "senior" in tokens
    assert "cloud" in tokens
    assert "devops" in tokens
    assert "engineer" in tokens
    assert "the" not in tokens
    assert "for" not in tokens


async def _seed_java_job_and_candidate():
    from backend.db.session import async_session_scope
    from backend.db.models import CandidateModel

    job_id = uuid4()
    req = JobRequirement(
        id="req-java-test-1",
        title="Java 8+ & Spring Boot",
        category=RequirementCategory.MUST_HAVE,
        weight=1.0,
        description="Experience with Java and French",
        minimum_years_experience=3,
    )
    job = JobDescription(
        id=job_id,
        title="Java Developer with French",
        department="Software Development",
        seniority_level="Mid",
        raw_text="Java developer proficient in French and Spring Boot.",
        requirements=[req],
    )
    await DatabaseRepository.save_job(job)

    cand_id = str(uuid4())
    async with async_session_scope() as db:
        cand = CandidateModel(
            id=cand_id,
            sanitized_text="Experienced Java Developer with French fluency and Spring Boot.",
            anonymized_cv_json={
                "candidate_id": cand_id,
                "sanitized_text": "Experienced Java Developer with French fluency and Spring Boot.",
                "anonymized_text": "Experienced Java Developer with French fluency and Spring Boot.",
                "skills": ["Java", "French", "Spring Boot"]
            },
            raw_cv_json={
                "text": "Jean Dupont. Experienced Java Developer with French fluency and Spring Boot.",
                "candidate_name": "Jean Dupont"
            }
        )
        db.add(cand)
        await db.commit()
    return job_id, cand_id


@pytest.mark.asyncio
async def test_asap_action_execution_run_screening():
    """Verifies that AsapChatAgent can directly parse and execute a live screening run command."""
    from backend.db.session import async_session_scope
    from backend.db.models import ScreeningRunModel
    from sqlalchemy import delete

    await _seed_java_job_and_candidate()

    agent = AsapChatAgent()
    user_prompt = "run a java developer with french screening session with 1 candidates in the cohort size and 1 deep screening acandidates"
    result = await agent.chat(messages=[{"role": "user", "content": user_prompt}])

    assert "action" in result and result["action"] is not None
    action = result["action"]
    print("\nACTION IN TEST:", action)
    assert action["action_type"] == "run_screening"
    assert action["success"] is True
    assert action["job_title"] == "Java Developer with French"
    assert action["cohort_size"] >= 1
    assert action["deep_count"] == 1
    assert action["status"] == "ranking"
    assert "run_id" in action

    # Verify confirmation text is rendered in reply
    assert "Live Screening Run Initiated" in result["reply"]
    assert "Java Developer with French" in result["reply"]
    assert str(action["run_id"]) in result["reply"]
    assert "cannot execute" not in result["reply"].lower()

    # Clean up test run from db
    async with async_session_scope() as db:
        await db.execute(delete(ScreeningRunModel).where(ScreeningRunModel.id == action["run_id"]))


def test_asap_action_endpoint_chat(auth_client):
    """Verifies that the REST chat endpoint executes the screening action and returns action metadata."""
    from backend.db.session import async_session_scope
    from backend.db.models import ScreeningRunModel
    from sqlalchemy import delete
    import asyncio

    asyncio.run(_seed_java_job_and_candidate())

    user_prompt = "run a java developer with french screening session with 1 candidates in the cohort size and 1 deep screening acandidates"
    response = auth_client.post("/api/v1/asap/chat", json={
        "messages": [{"role": "user", "content": user_prompt}]
    })

    assert response.status_code == 200
    data = response.json()
    assert "action" in data and data["action"] is not None
    assert data["action"]["action_type"] == "run_screening"
    assert data["action"]["success"] is True
    assert data["action"]["cohort_size"] >= 1
    assert data["action"]["deep_count"] == 1
    assert data["action"]["job_title"] == "Java Developer with French"

    run_id = data["action"]["run_id"]

    # Clean up
    async def cleanup():
        async with async_session_scope() as db:
            await db.execute(delete(ScreeningRunModel).where(ScreeningRunModel.id == run_id))
    asyncio.run(cleanup())


def test_asap_action_endpoint_stream(auth_client):
    """Verifies that the SSE streaming endpoint emits action events when an action is commanded."""
    from backend.db.session import async_session_scope
    from backend.db.models import ScreeningRunModel
    from sqlalchemy import delete
    import asyncio

    asyncio.run(_seed_java_job_and_candidate())

    user_prompt = "run a java developer with french screening session with 1 candidates in the cohort size and 1 deep screening acandidates"
    response = auth_client.post(
        "/api/v1/asap/chat/stream",
        json={"messages": [{"role": "user", "content": user_prompt}]},
    )
    assert response.status_code == 200
    lines = [line for line in response.iter_lines() if line]
    events = [json.loads(line.replace("data: ", "")) for line in lines if line.startswith("data: ")]

    action_events = [e for e in events if e.get("type") == "action"]
    assert len(action_events) >= 1
    action = action_events[0]["action"]
    assert action["action_type"] == "run_screening"
    assert action["job_title"] == "Java Developer with French"
    assert action["cohort_size"] >= 1
    assert action["deep_count"] == 1

    run_id = action["run_id"]

    # Clean up
    async def cleanup():
        async with async_session_scope() as db:
            await db.execute(delete(ScreeningRunModel).where(ScreeningRunModel.id == run_id))
    asyncio.run(cleanup())
