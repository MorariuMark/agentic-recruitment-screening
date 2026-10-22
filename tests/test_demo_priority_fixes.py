"""Demo regressions: non-blocking model controls and durable human score edits."""
import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api import routes
from backend.config import Settings
from backend.db.models import AuditLogModel
from backend.db.repository import DatabaseRepository
from backend.main import app
from backend.schemas.cv import AnonymizedCandidate, ParsedCV
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import MatchStatus, RequirementMatch
from backend.services.scoring_engine import ScoringEngine


def test_reranker_timeout_is_configurable_and_validated():
    assert Settings(_env_file=None).screening_reranker_timeout_seconds == 30
    assert Settings(_env_file=None, screening_reranker_timeout_seconds=12).screening_reranker_timeout_seconds == 12
    for invalid in (0, -1, 301):
        with pytest.raises(ValueError):
            Settings(_env_file=None, screening_reranker_timeout_seconds=invalid)


@pytest.mark.parametrize("endpoint, method, payload", [
    ("/ollama/status", "get_status", None),
    ("/ollama/start", "start_service", {}),
    ("/ollama/load", "load_model", {"model": "demo"}),
    ("/ollama/unload", "unload_model", {"model": "demo"}),
    ("/ollama/pull", "pull_model", {"model": "demo"}),
    ("/settings/local-models/import", "auto_import_gguf_to_ollama", {"full_path": "demo.gguf", "model_tag": "demo"}),
])
async def test_model_management_keeps_api_responsive(monkeypatch, endpoint, method, payload):
    entered, release = threading.Event(), threading.Event()
    thread_ids = []
    loop_thread = threading.get_ident()

    def slow_operation(*args, **kwargs):
        thread_ids.append(threading.get_ident())
        entered.set()
        release.wait(timeout=2)
        return {"success": True, "model": "demo"}

    monkeypatch.setattr(routes._ollama_service, method, slow_operation)
    import backend.services.local_model_scanner as scanner
    monkeypatch.setattr(scanner, "get_local_model_scanner", lambda: SimpleNamespace(scan_all=lambda **kwargs: {}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit") as client:
        operation = asyncio.create_task(client.get("/api/v1" + endpoint) if payload is None
                                        else client.post("/api/v1" + endpoint, json=payload))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert thread_ids == [thread_ids[0]] and thread_ids[0] != loop_thread
            assert not operation.done()
            response = await asyncio.wait_for(client.get("/"), timeout=0.5)
            assert response.status_code == 200
        finally:
            release.set()
            response = await operation
        assert response.status_code == 200, response.text
        assert response.json() == {"success": True, "model": "demo"}


@pytest.fixture
async def review_case():
    job = JobDescription(title="Demo role", requirements=[
        JobRequirement(id="required", title="Python", description="Python", category="must_have", weight=2),
        JobRequirement(id="preferred", title="Cloud", description="Cloud", category="nice_to_have", weight=1),
        JobRequirement(id="disabled", title="Disabled", description="Disabled", category="must_have", weight=0),
    ])
    candidate = AnonymizedCandidate(sanitized_text="Python developer")
    await DatabaseRepository.save_job(job)
    await DatabaseRepository.save_candidate(ParsedCV(raw_text=candidate.sanitized_text), candidate)
    matches = [RequirementMatch(requirement_id="required", status="not_met", score=0, reasoning="Unconfirmed"),
               RequirementMatch(requirement_id="preferred", status="not_met", score=0, reasoning="Not required"),
               RequirementMatch(requirement_id="disabled", status="not_met", score=0, reasoning="Disabled")]
    evaluation = ScoringEngine().compute_evaluation(candidate, job, matches, strictness=95)
    await DatabaseRepository.save_evaluation(evaluation, candidate.candidate_id, job.id)
    routes._EVALUATION_STORE.pop(evaluation.id, None)
    routes._CANDIDATE_ANONYMIZED_STORE.pop(candidate.candidate_id, None)
    corrected = [match.model_copy(deep=True) for match in matches]
    corrected[0].status = MatchStatus.MET
    corrected[0].score = 1
    corrected[0].reasoning = "Recruiter confirmed experience on a call"
    yield evaluation, job, candidate, corrected
    routes._EVALUATION_STORE.pop(evaluation.id, None)
    routes._CANDIDATE_ANONYMIZED_STORE.pop(candidate.candidate_id, None)


async def test_correction_preview_and_save_use_original_weights_after_reload(review_case):
    evaluation, job, candidate, corrected = review_case
    # A subsequent role edit must not change this evaluation's denominator.
    changed_job = job.model_copy(deep=True)
    changed_job.requirements[0].weight = 0
    await DatabaseRepository.save_job(changed_job)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit") as client:
        preview = await client.post("/api/v1/hitl/preview", json={
            "evaluation_id": str(evaluation.id), "updated_matches": [m.model_dump(mode="json") for m in corrected]})
        assert preview.status_code == 200, preview.text
        data = preview.json()
        assert data["overall_score"] == 75 and data["must_have_score"] == 100
        assert data["must_have_gaps_count"] == 0 and data["clarification_count"] == 0
        assert data["citation_verification_score"] == 0  # Call confirmation is not a CV citation.
        assert data["strictness"] == 95 and data["hitl_validated"] is False
        assert data["id"] == str(evaluation.id)
        before = await DatabaseRepository.get_evaluation(evaluation.id)
        assert before.overall_score == 0 and before.hitl_validated is False
        assert evaluation.id not in routes._EVALUATION_STORE
        saved = await client.post("/api/v1/hitl/validate", json={
            "evaluation_id": str(evaluation.id), "updated_matches": [m.model_dump(mode="json") for m in corrected],
            "recruiter_decision": "strong_match", "recruiter_notes": "Confirmed during the demo call"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["overall_score"] == data["overall_score"]
        assert saved.json()["recruiter_decision"] == "strong_match"
        routes._EVALUATION_STORE.pop(evaluation.id, None)
        reloaded = await client.get(f"/api/v1/evaluation/{evaluation.id}")
        assert reloaded.json()["overall_score"] == 75
        assert reloaded.json()["strictness"] == 95
        assert reloaded.json()["job_snapshot"]["requirements"][0]["weight"] == 2
        assert reloaded.json()["requirement_matches"][0]["status"] == "met"


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "unknown", "empty"])
async def test_invalid_corrections_never_change_saved_results(review_case, invalid):
    evaluation, _, _, matches = review_case
    if invalid == "missing":
        matches = matches[1:]
    elif invalid == "duplicate":
        matches = [*matches, matches[0]]
    elif invalid == "unknown":
        matches[0].requirement_id = "foreign-requirement"
    else:
        matches = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit") as client:
        response = await client.post("/api/v1/hitl/validate", json={
            "evaluation_id": str(evaluation.id), "updated_matches": [m.model_dump(mode="json") for m in matches],
            "recruiter_decision": "strong_match", "recruiter_notes": "Invalid correction"})
    assert response.status_code == 422
    stored = await DatabaseRepository.get_evaluation(evaluation.id)
    assert stored.overall_score == 0 and stored.hitl_validated is False
    assert routes._EVALUATION_STORE[evaluation.id].overall_score == 0


async def test_correction_commit_failure_rolls_back_scores_matches_and_approval(review_case, monkeypatch):
    evaluation, _, _, matches = review_case
    commit = AsyncSession.commit

    async def fail_decision(session):
        if any(isinstance(row, AuditLogModel) and row.action == "HITL_VALIDATE" for row in session.new):
            raise RuntimeError("Simulated decision commit failure")
        await commit(session)

    monkeypatch.setattr(AsyncSession, "commit", fail_decision)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit") as client:
        response = await client.post("/api/v1/hitl/validate", json={
            "evaluation_id": str(evaluation.id), "updated_matches": [m.model_dump(mode="json") for m in matches],
            "recruiter_decision": "strong_match", "recruiter_notes": "Must commit atomically"})
    assert response.status_code == 500
    stored = await DatabaseRepository.get_evaluation(evaluation.id)
    assert stored.overall_score == 0 and stored.hitl_validated is False
    assert stored.matches_json[0]["status"] == "not_met"
    assert routes._EVALUATION_STORE[evaluation.id].overall_score == 0


async def test_legacy_evaluation_without_snapshot_can_still_be_corrected(review_case):
    evaluation, _, _, matches = review_case
    legacy = evaluation.model_copy(deep=True)
    legacy.job_snapshot = None
    routes._EVALUATION_STORE[evaluation.id] = legacy
    preview = await routes.preview_hitl(routes.HITLPreviewRequest(evaluation_id=evaluation.id, updated_matches=matches))
    assert preview.overall_score == 75
    assert preview.job_snapshot is not None


async def test_disabled_clarifications_stay_excluded_after_reload(review_case):
    evaluation, _, _, matches = review_case
    matches[2].status = MatchStatus.CLARIFICATION_NEEDED
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit") as client:
        response = await client.post("/api/v1/hitl/validate", json={
            "evaluation_id": str(evaluation.id), "updated_matches": [m.model_dump(mode="json") for m in matches],
            "recruiter_decision": "strong_match", "recruiter_notes": "Inactive criteria stay excluded"})
        assert response.status_code == 200, response.text
        assert response.json()["clarification_count"] == 0
        routes._EVALUATION_STORE.pop(evaluation.id, None)
        reloaded = await client.get(f"/api/v1/evaluation/{evaluation.id}")
        assert reloaded.json()["clarification_count"] == 0


def test_scoring_context_migration_preserves_existing_evaluations(tmp_path):
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    source = Path(__file__).resolve().parents[1] / "migrations/versions/h8211021_scoring_context.py"
    spec = importlib.util.spec_from_file_location("scoring_context_migration", source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy-evaluations.db'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE match_evaluations (id VARCHAR(36) PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO match_evaluations (id) VALUES ('existing')")
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()  # Also accepts a column created by local startup.
                assert "scoring_context_json" in {col["name"] for col in sa.inspect(connection).get_columns("match_evaluations")}
                assert connection.exec_driver_sql("SELECT id, scoring_context_json FROM match_evaluations").one() == ("existing", None)
                migration.downgrade()
                assert connection.exec_driver_sql("SELECT id FROM match_evaluations").scalar_one() == "existing"
    finally:
        engine.dispose()
