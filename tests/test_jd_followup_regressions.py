"""Regressions from the follow-up job import and screening trace."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.agents.matching_agent import MatchingAgent
from backend.agents.llm_factory import DynamicLLMClient, GroqClient
from backend.schemas.cv import AnonymizedCandidate, LanguageSkill
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import RequirementMatch
from backend.services.evidence import relevant_source_passages
from backend.services.scoring_engine import ScoringEngine
from backend.main import app


def req(description="English proficiency", title="English language"):
    return JobRequirement(id="english", title=title, description=description, category="must_have")


@pytest.mark.parametrize("text, proficiency", [
    ("PERSONAL SKILLS\nMother tongue(s)\nOther language(s)\nGerman\nFrench\nANNEXES\nEnglish Language - Grade A\nEnglish\nUNDERSTANDING SPEAKING WRITING\nB1 B2 B1", "Native"),
    ("Languages: English, German", None),
    ("LANGUAGES\nEnglish\nGerman", "Native"),
    ("LANGUAGE SKILLS\nMother tongue(s): Romanian\nOther language(s):\nEnglish German\nLISTENING C1 READING C1 WRITING C1", "C1"),
])
def test_language_presence_has_source_support_without_an_invented_cefr_minimum(text, proficiency):
    candidate = AnonymizedCandidate(sanitized_text=text, anonymized_languages=[LanguageSkill(language="English", proficiency=proficiency)])
    agent = MatchingAgent(llm_client=SimpleNamespace(), vector_store=SimpleNamespace())
    requirement = req()
    match = agent.evaluate_requirement(candidate.candidate_id, requirement, candidate=candidate)
    result = ScoringEngine().compute_evaluation(candidate, JobDescription(title="Support", requirements=[requirement]), [match])
    assert result.requirement_matches[0].status == "met"
    assert result.overall_score == 100
    assert result.requirement_matches[0].citations[0].verified
    assert "Native" not in result.requirement_matches[0].citations[0].quote


def test_language_name_alone_does_not_establish_required_cefr_or_arbitrary_academic_proficiency():
    candidate = AnonymizedCandidate(sanitized_text="Languages: English, German", anonymized_languages=[LanguageSkill(language="English", proficiency="Native")])
    agent = MatchingAgent(llm_client=SimpleNamespace(), vector_store=SimpleNamespace())
    assert agent.evaluate_requirement(candidate.candidate_id, req("English C1"), candidate=candidate).status == "clarification_needed"
    candidate.sanitized_text = "Studied English literature at university."
    assert agent.evaluate_requirement(candidate.candidate_id, req(), candidate=candidate).status == "clarification_needed"


@pytest.mark.parametrize("tool", ["Service Now", "Service-Now", "Freshdesk", "Freshservice", "BMC Remedy", "OTRS", "Jira Service Management", "help-desk"])
def test_ticket_tool_context_reaches_the_model_even_without_the_word_ticket(tool):
    source = f"Handled support cases and resolved service requests using {tool}."
    assert relevant_source_passages(source, "Ticket Management - track and manage queues") == [source]
    calls = []
    class Model:
        def generate_structured(self, prompt, **kwargs):
            calls.append(prompt)
            return RequirementMatch(requirement_id="ticket", status="met", score=1, reasoning="Documented service workflow", citations=[{"quote": source}])
    candidate = AnonymizedCandidate(sanitized_text=source)
    requirement = req("Track and manage service tickets", "Ticket Management")
    agent = MatchingAgent(llm_client=Model(), vector_store=SimpleNamespace(query_candidate_chunks=lambda **kw: []))
    match = agent.evaluate_requirement(candidate.candidate_id, requirement, candidate=candidate)
    assert match.status == "met" and source in calls[0]


def test_missing_ticket_evidence_stays_unknown_and_long_source_context_is_bounded():
    assert relevant_source_passages("Studied queueing theory and academic queue management.", "Ticket Management") == []
    source = "Academic information. " * 1000 + "\n\nResolved service requests using Freshservice."
    passages = relevant_source_passages(source, "Ticket Management")
    assert passages == ["Resolved service requests using Freshservice."]
    assert all(len(passage) <= 1400 for passage in relevant_source_passages(source, "Academic information"))


def test_composite_latency_is_elapsed_time_with_model_work_reported_separately(monkeypatch):
    import backend.services.token_tracker as tracking
    clock = [100.0]
    monkeypatch.setattr(tracking, "time", SimpleNamespace(perf_counter=lambda: clock[0]))
    tracker = tracking.TokenTracker()
    tracker.start_action_session("candidate_evaluation")
    tracker.record_usage("test", "first", 10, 5, latency_ms=2000)
    tracker.record_usage("test", "second", 20, 10, latency_ms=3000)
    clock[0] = 101.0
    info = tracker.end_action_session("candidate_evaluation")
    assert info.latency_ms == 1000
    assert info.model_call_duration_ms == 5000
    assert info.model_calls == 2 and info.total_tokens == 45
    assert info.model == "mixed" and info.models_used == ["test/first", "test/second"]


def test_frozen_fallback_skips_a_target_that_hit_quota(monkeypatch):
    import backend.agents.llm_factory as factory
    from backend.config import settings
    monkeypatch.setattr(factory, "_MODEL_COOLDOWNS", {})
    monkeypatch.setattr(settings, "fallback_enabled", True)
    calls = []
    class Provider:
        api_key = "synthetic-test-key"
        last_usage = {}
        def __init__(self, name, fail=False): self.name, self.fail = name, fail
        def generate_text(self, *args, **kwargs):
            calls.append(self.name)
            if self.fail: raise RuntimeError("429 rate_limit")
            return "ok"
    primary, fallback = Provider("primary", True), Provider("fallback")
    client = DynamicLLMClient()
    client._snapshot_fallback_enabled = True
    client._snapshot_chain = [("test", "primary", primary), ("test", "fallback", fallback)]
    assert client.generate_text("First") == "ok"
    assert client.generate_text("Second") == "ok"
    assert calls == ["primary", "fallback", "fallback"]


def test_dynamic_factory_owns_key_rotation_once(monkeypatch):
    import backend.agents.llm_factory as factory
    provider = GroqClient.__new__(GroqClient)
    provider.secondary_client, provider.tertiary_client = object(), object()
    monkeypatch.setattr(factory, "create_llm_client", lambda **kwargs: provider)
    assert DynamicLLMClient()._get_or_create_client("groq", "synthetic", api_key="test-key") is provider
    assert provider.secondary_client is None and provider.tertiary_client is None


def test_imported_decimal_weights_and_reused_requirement_names_save_durably():
    client = TestClient(app)
    for title in ["Synthetic imported role A", "Synthetic imported role B"]:
        job = JobDescription(title=title, requirements=[req().model_copy(update={"weight": .7})])
        response = client.post("/api/v1/jobs", json=job.model_dump(mode="json"))
        assert response.status_code == 201
        job.title += " updated"
        assert client.post("/api/v1/jobs", json=job.model_dump(mode="json")).status_code == 201
        saved = next(item for item in client.get("/api/v1/jobs?limit=1000").json() if item["id"] == str(job.id))
        assert saved["requirements"][0]["weight"] == .7 and saved["title"] == job.title
