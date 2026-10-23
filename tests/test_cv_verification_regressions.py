"""Offline reproductions of the FastAPI cohort's retrieval and scoring failures."""
from unittest.mock import MagicMock
import json
import sqlite3

import numpy as np
import pytest

from backend.agents.matching_agent import MatchingAgent, EvaluationSourceError
from backend.config import settings
from backend.schemas.cv import AnonymizedCandidate, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import MatchStatus, RequirementMatch, VerbatimCitation
from backend.services.hybrid_screening import HybridRankingEngine
from backend.services.scoring_engine import ScoringEngine
from backend.services.vector_store import EvidenceRetrievalError, VectorStoreService


def requirement():
    return JobRequirement(id="req_fastapi", title="FastAPI", description="FastAPI REST microservices", category="must_have")


def job():
    return JobDescription(title="AI Engineer", requirements=[requirement()])


def match(*quotes):
    return RequirementMatch(requirement_id="req_fastapi", status="met", score=1,
                            reasoning="Model claimed a full match.",
                            citations=[VerbatimCitation(quote=quote) for quote in quotes])


@pytest.mark.parametrize("index_fails", [False, True])
def test_vector_outage_uses_original_cv_without_failing_evaluation(index_fails):
    source = "Built FastAPI REST microservices for document processing."
    candidate = AnonymizedCandidate(sanitized_text=source)
    llm, vectors = MagicMock(), MagicMock()
    vectors.query_candidate_chunks.side_effect = EvidenceRetrievalError("Index temporarily unavailable")
    if index_fails:
        vectors.index_candidate.side_effect = OSError("Index locked")
    llm.generate_structured.return_value = match(source)
    agent = MatchingAgent(llm_client=llm, vector_store=vectors)
    result = agent.match_candidate(candidate, job())
    assert result.overall_score == 100
    assert result.requirement_matches[0].citations[0].verified
    assert source in llm.generate_structured.call_args.kwargs["prompt"]
    assert agent.retrieval_warnings


def test_missing_source_still_requires_reparse():
    llm, vectors = MagicMock(), MagicMock()
    with pytest.raises(EvaluationSourceError, match="Reparse"):
        MatchingAgent(llm_client=llm, vector_store=vectors).match_candidate(AnonymizedCandidate(), job())
    llm.generate_structured.assert_not_called()


def test_matching_agent_does_not_round_met_score_to_100():
    source = "Built Python services."
    req = JobRequirement(id="python", title="Python", description="Python", category="must_have")
    llm, vectors = MagicMock(), MagicMock()
    vectors.query_candidate_chunks.return_value = []
    llm.generate_structured.return_value = RequirementMatch(
        requirement_id="python", status="met", score=.9, reasoning="Direct evidence.",
        citations=[VerbatimCitation(quote=source)])
    agent = MatchingAgent(llm_client=llm, vector_store=vectors)
    result = agent.match_candidate(AnonymizedCandidate(sanitized_text=source), JobDescription(title="Developer", requirements=[req]))
    assert result.overall_score == 90


def test_storage_error_preserves_underlying_cause(caplog):
    vectors = VectorStoreService.__new__(VectorStoreService)
    vectors.candidate_collection = MagicMock()
    cause = OSError("Synthetic index lock")
    vectors.candidate_collection.query.side_effect = cause
    with pytest.raises(EvidenceRetrievalError) as failure:
        vectors.query_candidate_chunks(AnonymizedCandidate().candidate_id, "FastAPI")
    assert failure.value.__cause__ is cause
    assert "Synthetic index lock" in caplog.text


def test_pre_screen_requires_application_context_and_distinguishes_skill_lists():
    full = AnonymizedCandidate(anonymized_work_experiences=[WorkExperience(work_description=["Built FastAPI RESTful micro-services"] )])
    tool_only = AnonymizedCandidate(anonymized_work_experiences=[WorkExperience(work_description=["Built a local FastAPI server"] )])
    listed = AnonymizedCandidate(anonymized_skills=["FastAPI"], anonymized_work_experiences=[WorkExperience(work_description=["Built a REST microservice"], skills_used=["FastAPI"])])
    engine = HybridRankingEngine(lambda texts: np.ones((len(texts), 3)))
    rows = {row.candidate_id: row for row in engine.rank([listed, tool_only, full], job())}
    assert rows[full.candidate_id].pre_screen_score == 100
    assert rows[tool_only.candidate_id].pre_screen_score < 100
    assert rows[listed.candidate_id].pre_screen_score < 100
    assert rows[listed.candidate_id].essential_supported == 0


@pytest.mark.parametrize("quotes", [
    ["Developed an asynchronous control system running on a local FastAPI server"],
    ["Engineering: Python, FastAPI, Docker", "Built and shipped a document-classification service"],
    ["Engineering: Python, FastAPI, Docker", "Built REST microservices using Java"],
])
def test_verbatim_quotes_do_not_prove_unstated_tool_context(quotes):
    candidate = AnonymizedCandidate(sanitized_text="\n\n".join(quotes))
    result = ScoringEngine().compute_evaluation(candidate, job(), [match(*quotes)])
    assert result.overall_score < 100
    assert result.requirement_matches[0].status == MatchStatus.PARTIAL
    assert result.requirement_matches[0].clarification_question
    assert result.citation_verification_score == 1


def test_explicit_human_review_is_preserved():
    quote = "FastAPI"
    result = ScoringEngine().compute_evaluation(AnonymizedCandidate(sanitized_text=quote), job(), [match(quote)], human_reviewed=True)
    assert result.overall_score == 100


def test_default_vector_store_honors_configured_storage(monkeypatch, tmp_path):
    client = MagicMock()
    monkeypatch.setattr("backend.services.vector_store.chromadb.PersistentClient", client)
    monkeypatch.setattr(settings, "chroma_db_dir", str(tmp_path / "isolated"))
    monkeypatch.setattr(settings, "embedding_model", "configured-model")
    store = VectorStoreService()
    client.assert_called_once_with(path=str(tmp_path / "isolated"))
    assert store.model_name == "configured-model"


def test_test_collection_does_not_open_production_index():
    from backend.api import routes
    assert settings.environment == "test"
    assert "atos-pytest-" in routes._vector_store.persist_directory
    assert "atos-pytest-" in settings.database_url


def test_fixture_quarantine_requires_full_signature_and_missing_source():
    from scripts.quarantine_screening_fixtures import is_fixture
    raw = {"contact_info": {"full_name": "Alice Smith", "email": "alice@test.com"}, "skills": ["Kubernetes", "Go"], "experiences": []}
    assert is_fixture("alice_cv.pdf", raw, {}, "")
    assert not is_fixture("alice_cv.pdf", raw, {}, "Original CV")
    assert not is_fixture("alice_cv.pdf", raw, {"sanitized_text": "Original CV"}, "")
    assert not is_fixture("different.pdf", raw, {}, "")
    raw["skills"] = ["Python"]
    assert not is_fixture("alice_cv.pdf", raw, {}, "")


def test_fixture_repair_is_backed_up_idempotent_and_preserves_evaluations(monkeypatch, tmp_path):
    from scripts.quarantine_screening_fixtures import main
    path = tmp_path / "historical.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{path.as_posix()}")
    raw = {"contact_info": {"full_name": "Bob Jones", "email": "bob@test.com"}, "skills": ["Go"], "experiences": []}
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE candidates (id TEXT, original_filename TEXT, raw_cv_json TEXT, anonymized_cv_json TEXT, sanitized_text TEXT);
            CREATE TABLE job_requisitions (id TEXT, title TEXT, raw_text TEXT);
            CREATE TABLE job_requirements (id TEXT, title TEXT, description TEXT, category TEXT, weight REAL, job_id TEXT);
            CREATE TABLE job_description_data (job_id TEXT, data TEXT);
            CREATE TABLE match_evaluations (overall_score REAL);
            INSERT INTO job_requisitions VALUES ('job', 'AI Engineer', '');
            INSERT INTO job_requirements VALUES ('req_fastapi', 'FastAPI', 'FastAPI REST microservices', 'must_have', 1, 'job');
            INSERT INTO job_description_data VALUES ('job', '{"title":"AI Engineer"}');
            INSERT INTO match_evaluations VALUES (100);
        """)
        db.execute("INSERT INTO candidates VALUES ('fixture', 'bob_cv.pdf', ?, '{}', '')", (json.dumps(raw),))
    monkeypatch.setattr("sys.argv", ["quarantine_screening_fixtures.py"])
    main()
    assert not (tmp_path / "backups").exists()
    monkeypatch.setattr("sys.argv", ["quarantine_screening_fixtures.py", "--apply"])
    main()
    main()
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(path) as db:
        assert json.loads(db.execute("SELECT raw_cv_json FROM candidates").fetchone()[0])["dataset"] == "benchmark"
        assert db.execute("SELECT title FROM job_requisitions").fetchone()[0] == "AI Engineer [test fixture]"
        assert db.execute("SELECT overall_score FROM match_evaluations").fetchone()[0] == 100
    with sqlite3.connect(backups[0]) as db:
        assert "dataset" not in json.loads(db.execute("SELECT raw_cv_json FROM candidates").fetchone()[0])
