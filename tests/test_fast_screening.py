"""Fast funnel contracts: no model/network access, real isolated database persistence."""
import asyncio
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.api import recruiter, routes
from backend.agents.matching_agent import MatchingAgent
from backend.db.repository import DatabaseRepository
from backend.schemas.cv import AnonymizedCandidate, ContactInfo, Education, ParsedCV, WorkExperience
from backend.schemas.interview import InterviewPlan
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import MatchEvaluationResult, RequirementMatch
from backend.services.screening_duplicates import candidate_name_key, evaluation_key
from backend.services.batch_processor import BatchProcessorService
from backend.services.pre_ranking import PreRankingEngine, experience_years


def test_statistics_aggregate_stored_data_and_recorded_usage(funnel, monkeypatch):
    from backend.db.models import BatchJobModel
    from backend.db.session import async_session_scope
    import backend.services.token_tracker as tracking
    monkeypatch.setattr(tracking, "_IN_MEMORY_LOGS", [{"synthetic": True, "total_tokens": 99999, "latency_ms": 99999}])
    client, _, _, _, _, start = funnel
    response = client.get("/api/v1/screening/statistics")
    assert response.status_code == 200
    before = response.json()
    assert before["candidates"] >= 4 and before["jobs"] >= 1
    assert before["model_calls"] == 0 and before["tokens"] == 0
    assert all(value >= 0 for value in before.values() if isinstance(value, (int, float)))
    async def seed_usage():
        async with async_session_scope() as db:
            db.add(BatchJobModel(total_files=5, processed_files=3, failed_files=1))
            await db.commit()
    asyncio.run(seed_usage())
    tracking.token_tracker.record_usage(provider="test", model="test", prompt_tokens=100, completion_tokens=50, total_tokens=150, latency_ms=2500)
    start(deep_evaluation=False)
    after = client.get("/api/v1/screening/statistics").json()
    for key, increment in {"batch_files": 5, "batch_processed": 3, "batch_failed": 1,
                           "tokens": 150, "model_calls": 1, "model_duration_ms": 2500, "screening_runs": 1}.items():
        assert after[key] == before[key] + increment
    assert after["model_average_ms"] == pytest.approx(after["model_duration_ms"] / after["model_calls"])
    assert after["candidates"] == before["candidates"]


def requirement(title="Python", **kwargs):
    return JobRequirement(id=str(uuid4()), title=title, description=title, category="must_have", **kwargs)


def test_composite_single_embedding_batch_and_no_demographics():
    calls = []
    def embed(texts):
        calls.append(texts)
        return [[1, 0], [1, 0], [0, 1]]
    strong = AnonymizedCandidate(anonymized_skills=["Python"], anonymized_work_experiences=[WorkExperience(skills_used=["Python"], duration_months=60)], anonymized_education=[Education(degree_title="Bachelor of Computer Science", field_of_study="Computer Science")], demographic_data={"age": "SECRET_DEMOGRAPHIC"}, sanitized_text="SECRET_CONTACT")
    weak = AnonymizedCandidate(anonymized_skills=["Excel"])
    job = JobDescription(title="Developer", requirements=[requirement(minimum_years_experience=5), requirement("Bachelor degree in Computer Science")])
    rows = PreRankingEngine(embed).rank([strong, weak], job)
    assert len(calls) == 1 and len(calls[0]) == 3
    assert "SECRET" not in " ".join(calls[0])
    assert rows[0].candidate_id == strong.candidate_id
    assert rows[0].pre_screen_score == 100
    assert rows[1].pre_screen_score == 0
    assert rows[1].degree_score == 0


def test_absent_requirements_redistribute_weights_and_zero_vectors_are_finite():
    candidates = [AnonymizedCandidate(), AnonymizedCandidate()]
    rows = PreRankingEngine(lambda _: np.zeros((3, 4))).rank(candidates, JobDescription(title="Role"))
    assert all(r.pre_screen_score == 0 and r.skills_score is None and r.degree_score is None for r in rows)
    assert [str(r.candidate_id) for r in rows] == sorted(str(c.candidate_id) for c in candidates)


def test_skill_boundaries_and_weights():
    candidate = AnonymizedCandidate(anonymized_skills=["JavaScript", "Python"])
    job = JobDescription(title="Developer", requirements=[requirement("Java", weight=3), requirement("Python", weight=1)])
    row = PreRankingEngine(lambda _: [[1,0],[1,0]]).rank([candidate], job)[0]
    assert row.skills_score == 25  # JavaScript is not Java.
    assert row.pre_screen_score == pytest.approx((40 + .3 * 25) / .7, abs=.01)


def test_degree_discipline_mismatch_does_not_pass():
    candidate = AnonymizedCandidate(anonymized_education=[Education(degree_title="Master in Economics", field_of_study="Economics")])
    job = JobDescription(title="Developer", requirements=[requirement("Bachelor degree in Computer Science")])
    row = PreRankingEngine(lambda _: [[1,0],[1,0]]).rank([candidate], job)[0]
    assert row.degree_score == 0


def test_required_languages_use_shared_proficiency_checks():
    from backend.schemas.cv import LanguageSkill
    job = JobDescription(title="Support", requirements=[requirement("German language B2")])
    candidate = AnonymizedCandidate(anonymized_languages=[LanguageSkill(language="German", proficiency="C1")])
    assert PreRankingEngine(lambda _: [[1,0],[1,0]]).rank([candidate], job)[0].skills_score == 100
    candidate.anonymized_languages[0].proficiency = "A2"
    assert PreRankingEngine(lambda _: [[1,0],[1,0]]).rank([candidate], job)[0].skills_score == 0


def test_experience_uses_documented_dates_and_merges_overlap():
    candidate = AnonymizedCandidate(anonymized_work_experiences=[
        WorkExperience(skills_used=["Python"], start_date="Jan 2020", end_date="Dec 2022"),
        WorkExperience(skills_used=["Python"], start_date="Jan 2021", end_date="Dec 2023"),
        WorkExperience(skills_used=["Python"]),
        WorkExperience(skills_used=["Java"], duration_months=120),
    ])
    assert experience_years(candidate, ["python"]) == 4
    assert experience_years(AnonymizedCandidate(anonymized_work_experiences=[WorkExperience()]), []) == 0
    assert routes._documented_years({"experiences": [{"duration_months": 48}]}, {}) == 4
    assert routes._documented_years({"experiences": [{"job_title": "Engineer"}]}, {}) is None


@pytest.mark.parametrize("vectors", [[[1, 0]], [[float("nan"), 0], [1,0]]])
def test_invalid_embedding_response_fails_explicitly(vectors):
    with pytest.raises(ValueError):
        PreRankingEngine(lambda _: vectors).rank([AnonymizedCandidate()], JobDescription(title="Role"))


@pytest.fixture
def funnel(monkeypatch):
    client = TestClient(app)
    job = JobDescription(title="Screening test role", requirements=[requirement()])
    candidates = [AnonymizedCandidate(anonymized_skills=["Python"] if i < 2 else ["Excel"]) for i in range(4)]
    async def seed():
        await DatabaseRepository.save_job(job)
        for i, candidate in enumerate(candidates):
            await DatabaseRepository.save_candidate(ParsedCV(contact_info=ContactInfo(full_name=f"Test Candidate {i}"), skills=candidate.anonymized_skills), candidate)
    asyncio.run(seed())
    calls = []
    embedding_calls = []
    def embed(texts):
        embedding_calls.append(texts)
        return [[1,0], *[[1,0] if "Python" in text else [0,1] for text in texts[1:]]]
    monkeypatch.setattr(routes._vector_store, "_embedding_fn", embed)
    def match(self, candidate, job_description):
        calls.append(candidate.candidate_id)
        return MatchEvaluationResult(candidate_id=candidate.candidate_id, job_id=job_description.id, overall_score=85, must_have_score=85, recommendation="strong_match", requirement_matches=[RequirementMatch(requirement_id=job_description.requirements[0].id, status="met", score=1, reasoning=f"Evidence for {candidate.candidate_id}")])
    monkeypatch.setattr(MatchingAgent, "match_candidate", match)
    def start(**overrides):
        data = {"job_id": str(job.id), "candidate_ids": [str(c.candidate_id) for c in candidates], "top_k": 2, **overrides}
        response = client.post("/api/v1/screening/rank", json=data)
        assert response.status_code == 202, response.text
        run = client.get(f"/api/v1/screening/runs/{response.json()['id']}")
        assert run.status_code == 200
        return run.json()
    return client, job, candidates, calls, embedding_calls, start


def test_top_k_only_complete_ranked_list_and_durable_latest(funnel):
    client, job, candidates, calls, embeddings, start = funnel
    run = start(candidate_ids=[str(c.candidate_id) for c in candidates] * 2)
    assert run["status"] == "completed"
    assert len(run["rows"]) == 4 and len(calls) == 2 and len(embeddings) == 1
    assert [str(cid) for cid in calls] == [r["candidate_id"] for r in run["rows"][:2]]
    assert all(r["deep_evaluation"] is None for r in run["rows"][2:])
    assert client.get(f"/api/v1/screening/jobs/{job.id}/latest").json()["id"] == run["id"]
    assert len(client.get(f"/api/v1/jobs/{job.id}/evaluations").json()) == 2


def test_pre_screen_only_never_calls_llm(funnel):
    *_, calls, embeddings, start = funnel
    run = start(deep_evaluation=False)
    assert len(run["rows"]) == 4 and not calls and len(embeddings) == 1
    assert all(r["deep_status"] == "not_selected" for r in run["rows"])


def test_improved_pipeline_cache_and_legacy_api_compatibility(funnel):
    client, _, _, calls, _, start = funnel
    first = start(pipeline_version="v2", deep_evaluation=False, rerank_enabled=False)
    assert first["status"] == "completed" and first["pipeline_version"] == "v2" and not calls
    assert len(first["rows"]) == 4 and first["job_hash"] and first["profile_hashes"]
    assert first["rows"][0]["requirement_assessments"]
    again = start(pipeline_version="v2", deep_evaluation=False, rerank_enabled=False)
    assert again["diagnostics"]["cache_hits"] == 4
    assert start(deep_evaluation=False)["pipeline_version"] == "v1"


def test_improved_reranker_failure_retains_hybrid_order_and_top_k(funnel, monkeypatch):
    def unavailable():
        raise OSError("No local model")
    monkeypatch.setattr(recruiter, "get_reranker", unavailable)
    client, _, _, calls, _, start = funnel
    result = start(pipeline_version="v2", top_k=2)
    assert result["status"] == "completed" and len(calls) == 2
    assert result["diagnostics"]["reranker_fallback"] is True
    assert result["diagnostics"]["warnings"]
    assert client.post(f"/api/v1/screening/runs/{result['id']}/shortlist", json={"count": 2}).status_code == 200


def test_retry_reuses_completed_evaluations_and_detects_changed_profiles(funnel, monkeypatch):
    client, job, candidates, calls, _, start = funnel
    original = MatchingAgent.match_candidate
    def one_failure(self, candidate, job_description):
        if calls:
            raise RuntimeError("Temporary failure")
        return original(self, candidate, job_description)
    monkeypatch.setattr(MatchingAgent, "match_candidate", one_failure)
    run = start()
    assert run["status"] == "partial" and len(calls) == 1
    completed_id = run["rows"][0]["deep_evaluation"]["id"]
    monkeypatch.setattr(MatchingAgent, "match_candidate", original)
    response = client.post(f"/api/v1/screening/runs/{run['id']}/retry")
    assert response.status_code == 202
    final = client.get(f"/api/v1/screening/runs/{run['id']}").json()
    assert final["status"] == "completed" and len(calls) == 2
    assert final["rows"][0]["deep_evaluation"]["id"] == completed_id
    assert client.post(f"/api/v1/screening/runs/{run['id']}/retry").status_code == 409


def test_retry_does_not_use_modified_candidate_data(funnel, monkeypatch):
    client, _, candidates, _, _, start = funnel
    monkeypatch.setattr(MatchingAgent, "match_candidate", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Retry later")))
    run = start()
    candidates[0].anonymized_skills.append("Changed content")
    asyncio.run(DatabaseRepository.save_candidate(ParsedCV(contact_info=ContactInfo(full_name="Test Candidate 0")), candidates[0]))
    assert client.post(f"/api/v1/screening/runs/{run['id']}/retry").status_code == 409


@pytest.mark.parametrize("options", [{"pipeline_version": "v3"}, {"rerank_pool_size": 0}, {"rerank_pool_size": 201}, {"evidence_per_requirement": 4}])
def test_improved_options_are_validated(funnel, options):
    client, job, candidates, *_ = funnel
    assert client.post("/api/v1/screening/rank", json={"job_id": str(job.id), "candidate_ids": [str(candidates[0].candidate_id)], **options}).status_code == 422


def test_same_name_excluded_before_embedding_and_first_selected_copy_kept(funnel):
    client, job, candidates, calls, embeddings, start = funnel
    asyncio.run(DatabaseRepository.save_candidate(
        ParsedCV(contact_info=ContactInfo(full_name="Test Candidate 0")), candidates[1]))
    ordered = [candidates[1], candidates[0], *candidates[2:]]
    run = start(candidate_ids=[str(c.candidate_id) for c in ordered], deep_evaluation=False)
    assert len(run["rows"]) == 3 and len(embeddings[0]) == 4 and not calls
    assert run["duplicates"] == [{"candidate_id": str(candidates[0].candidate_id), "kept_candidate_id": str(candidates[1].candidate_id), "reason": "same_name"}]
    assert str(candidates[0].candidate_id) not in [r["candidate_id"] for r in run["rows"]]
    # Exclusion affects this ranking only, not the stored CV.
    assert asyncio.run(DatabaseRepository.get_candidate(candidates[0].candidate_id)) is not None
    assert client.get(f"/api/v1/screening/jobs/{job.id}/latest").json()["duplicates"] == run["duplicates"]


def test_identical_full_evaluations_keep_highest_rank_without_extra_llm_calls(funnel, monkeypatch):
    client, job, candidates, calls, _, start = funnel
    def match(self, candidate, job_description):
        calls.append(candidate.candidate_id)
        return MatchEvaluationResult(candidate_id=candidate.candidate_id, job_id=job_description.id,
            overall_score=85, must_have_score=85, recommendation="strong_match",
            requirement_matches=[RequirementMatch(requirement_id=job_description.requirements[0].id, status="met", score=1, reasoning="Identical documented Python evidence")])
    monkeypatch.setattr(MatchingAgent, "match_candidate", match)
    run = start()
    assert run["status"] == "completed" and len(calls) == 2 and len(run["rows"]) == 3
    assert [row["rank"] for row in run["rows"]] == [1, 2, 3]
    assert sum(row["deep_status"] == "completed" for row in run["rows"]) == 1
    assert run["duplicates"] == [{"candidate_id": str(calls[1]), "kept_candidate_id": str(calls[0]), "reason": "identical_evaluation"}]
    assert len(client.get(f"/api/v1/jobs/{job.id}/evaluations").json()) == 2
    response = client.post(f"/api/v1/screening/runs/{run['id']}/shortlist", json={"count": 1})
    assert response.status_code == 200 and response.json()["shortlist_ids"] == [str(calls[0])]


def test_equal_scores_with_different_reasoning_are_not_duplicates(funnel):
    *_, start = funnel
    run = start()
    assert len(run["rows"]) == 4 and run["duplicates"] == []
    assert run["rows"][0]["deep_evaluation"]["overall_score"] == run["rows"][1]["deep_evaluation"]["overall_score"]


@pytest.mark.parametrize("name", ["", "Candidate Name", "Unknown", "[redacted]", None])
def test_placeholder_names_never_merge_unrelated_candidates(name):
    assert candidate_name_key({"contact_info": {"full_name": name}}) is None


def test_exact_name_normalization_preserves_real_name_differences():
    assert candidate_name_key({"contact_info": {"full_name": "  Ana   POPESCU "}}) == "ana popescu"
    assert candidate_name_key({"contact_info": {"full_name": "Ana Popescu-Ionescu"}}) != "ana popescu"


def test_evaluation_key_ignores_identity_telemetry_but_compares_all_evidence():
    first = MatchEvaluationResult(candidate_id=uuid4(), job_id=uuid4(), overall_score=85,
        must_have_score=85, recommendation="strong_match", requirement_matches=[RequirementMatch(
            requirement_id="python", status="met", score=1, reasoning="Python is documented",
            citations=[{"quote": "Built Python APIs", "verified": True}])])
    second = first.model_copy(deep=True, update={"id": uuid4(), "candidate_id": uuid4(),
        "token_usage": {"latency_ms": 900}, "audit_metadata": {"action_timestamp": "later"}})
    assert evaluation_key(first) == evaluation_key(second)
    second.requirement_matches[0].citations[0].quote = "Different evidence"
    assert evaluation_key(first) != evaluation_key(second)


def test_top_k_larger_than_cohort_is_capped(funnel):
    *_, calls, embeddings, start = funnel
    run = start(top_k=10)
    assert len(calls) == 4 and len(run["rows"]) == 4


@pytest.mark.parametrize("top_k", [0, -1, 101, 1.5])
def test_top_k_validation(funnel, top_k):
    client, job, candidates, *_ = funnel
    assert client.post("/api/v1/screening/rank", json={"job_id": str(job.id), "candidate_ids": [str(candidates[0].candidate_id)], "top_k": top_k}).status_code == 422


def test_empty_unknown_job_and_missing_candidates(funnel):
    client, job, candidates, *_ = funnel
    base = {"job_id": str(job.id), "candidate_ids": [str(candidates[0].candidate_id)]}
    assert client.post("/api/v1/screening/rank", json={**base, "candidate_ids": []}).status_code == 422
    assert client.post("/api/v1/screening/rank", json={**base, "job_id": str(uuid4())}).status_code == 404
    assert client.post("/api/v1/screening/rank", json={**base, "candidate_ids": [str(uuid4())]}).status_code == 404


def test_deep_failure_keeps_all_pre_screen_scores(funnel, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Provider unavailable")
    monkeypatch.setattr(MatchingAgent, "match_candidate", fail)
    client, *_, start = funnel
    run = start()
    assert run["status"] == "partial" and len(run["rows"]) == 4
    assert all(r["pre_screen_score"] >= 0 for r in run["rows"])
    assert sum(r["deep_status"] == "failed" for r in run["rows"]) == 2
    assert client.post(f"/api/v1/screening/runs/{run['id']}/shortlist", json={"count": 2}).status_code == 409


def test_human_gate_persistence_and_interview(funnel, monkeypatch):
    client, job, *_, start = funnel
    run = start()
    base = f"/api/v1/screening/runs/{run['id']}"
    cid = run["rows"][0]["candidate_id"]
    assert client.post(base + "/interview", json={"candidate_id": cid}).status_code == 409
    assert client.post(base + f"/decisions/{cid}", json={"decision": "interview"}).status_code == 409
    assert client.post(base + "/shortlist", json={"count": 3}).status_code == 409
    assert client.post(base + "/shortlist", json={"count": 2}).status_code == 200
    approved = client.post(base + f"/decisions/{cid}", json={"decision": "interview", "notes": "Verified relevant evidence."})
    assert approved.status_code == 200
    persisted = client.get(base).json()
    assert persisted["decisions"][cid]["notes"] == "Verified relevant evidence."
    evaluation = client.get(f"/api/v1/evaluation/{run['rows'][0]['deep_evaluation']['id']}").json()
    assert evaluation["hitl_validated"] is True
    plan = InterviewPlan(candidate_id=UUID(cid), job_id=job.id, questions=[], total_estimated_minutes=45)
    mock = AsyncMock(return_value=plan)
    monkeypatch.setattr(routes, "generate_interview_plan", mock)
    assert client.post(base + "/interview", json={"candidate_id": cid}).status_code == 200
    assert mock.await_count == 1
    assert client.get(base).json()["interviews"][cid]["id"] == str(plan.id)
    for decision in ["hold", "reject"]:
        assert client.post(base + f"/decisions/{cid}", json={"decision": decision}).status_code == 200
        assert client.post(base + "/interview", json={"candidate_id": cid}).status_code == 409


def test_demo_login_both_roles_password_logout():
    client = TestClient(app)
    assert client.get("/api/v1/auth/session").json()["role"] is None
    assert client.post("/api/v1/auth/login", json={"role":"user", "password":"wrong"}).status_code == 401
    for role in ["admin", "user"]:
        response = client.post("/api/v1/auth/login", json={"role": role, "password":"1234"})
        assert response.status_code == 200 and "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/v1/auth/session").json()["role"] == role
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.get("/api/v1/auth/session").json()["role"] is None


def test_compact_model_selector_reuses_shared_factory_settings(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(recruiter.settings, "llm_provider", "groq")
    monkeypatch.setattr(recruiter.settings, "groq_model", "test-model")
    response = client.get("/api/v1/screening/models")
    assert response.status_code == 200 and response.json()["active_model"] == "test-model"
    model = response.json()["providers_catalog"]["groq"]["models"][0]["id"]
    response = client.post("/api/v1/screening/models", json={"provider":"groq", "model":model})
    assert response.status_code == 200
    assert recruiter.settings.groq_model == model
    assert client.post("/api/v1/screening/models", json={"provider":"groq", "model":"not-in-catalog"}).status_code == 400


def test_recruiter_failover_toggle_updates_shared_admin_setting(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(recruiter.settings, "fallback_enabled", True)
    original_provider = recruiter.settings.llm_provider
    original_compatibility = recruiter.settings.compatibility_mode
    for enabled in [False, True]:
        response = client.post("/api/v1/screening/failover", json={"enabled": enabled})
        assert response.status_code == 200
        assert response.json()["fallback_enabled"] is enabled
        assert recruiter.settings.fallback_enabled is enabled
        assert client.get("/api/v1/screening/models").json()["fallback_enabled"] is enabled
        assert recruiter.settings.llm_provider == original_provider
        assert recruiter.settings.compatibility_mode == original_compatibility


def test_job_extraction_parity_and_lossless_save(monkeypatch):
    from backend.schemas.job import JobExtractionResult
    job = JobDescription(title="Complete extraction parity role", department="Engineering", raw_text="Full original job description", languages=["English", "German"], seniority_level="Senior", work_model="Hybrid", employment_type="Full-time", custom_sections=[{"section_title":"Travel", "items":["Occasional travel"]}], unused_details=["Company benefits"], requirements=[requirement()])
    extraction = JobExtractionResult(job_description=job)
    calls = []
    def parse(text):
        calls.append(text)
        return extraction
    monkeypatch.setattr(routes._job_parser_agent, "parse_job_text", parse)
    monkeypatch.setattr(routes._job_parser_agent, "parse_job_url", parse)
    client = TestClient(app)
    recruiter_result = client.post("/api/v1/screening/jobs/parse", json={"text":"Shared engine input"})
    assert recruiter_result.status_code == 200
    assert recruiter_result.json()["job_description"] == job.model_dump(mode="json")
    assert not any(item["id"] == str(job.id) for item in client.get("/api/v1/jobs").json())
    admin_result = client.post("/api/v1/job/parse-text", json={"text":"Shared engine input"})
    assert admin_result.json() == recruiter_result.json() and calls == ["Shared engine input"] * 2
    url_result = client.post("/api/v1/screening/jobs/parse-url", json={"url":"https://example.org/job"})
    assert url_result.status_code == 200 and url_result.json()["job_description"] == job.model_dump(mode="json")
    assert client.post("/api/v1/jobs", json=job.model_dump(mode="json")).status_code == 201
    restored = next(item for item in client.get("/api/v1/jobs").json() if item["id"] == str(job.id))
    for field in ["languages", "custom_sections", "unused_details", "raw_text", "seniority_level", "work_model", "employment_type", "requirements"]:
        assert restored[field] == job.model_dump(mode="json")[field]


def test_single_and_cohort_cv_extraction_use_same_complete_contract(monkeypatch):
    from backend.agents.parser_agent import ParserAgent
    from backend.schemas.cv import Project, LanguageSkill, Publication, Patent, LogisticalInfo, CustomSection
    parsed = ParsedCV(contact_info=ContactInfo(full_name="Synthetic Parity Candidate"), summary="A complete synthetic profile.", skills=["Python"], experiences=[WorkExperience(job_title="Engineer", duration_months=48)], education=[Education(degree_title="Bachelor of Science", field_of_study="Computer Science")], projects=[Project(project_name="ETL platform", technologies=["Python"])], languages=[LanguageSkill(language="English", proficiency="C1")], certifications=["Example certificate"], publications=[Publication(title="Example paper")], patents=[Patent(title="Example invention")], logistics=LogisticalInfo(notice_period="One month"), custom_sections=[CustomSection(section_title="Volunteering", items=["STEM mentoring"])], miscellaneous=["Other evidence"], unused_details=["Source footer"], raw_text="Complete synthetic CV text")
    calls = []
    def parse(self, source, filename=None):
        calls.append(filename)
        return parsed, self.pii_scrubber.anonymize_cv(parsed)
    monkeypatch.setattr(ParserAgent, "parse_and_anonymize", parse)
    # Existing tests can restore a bound method directly on the shared Admin instance.
    monkeypatch.setattr(routes._parser_agent, "parse_and_anonymize", lambda source, filename=None: parse(routes._parser_agent, source, filename))
    monkeypatch.setattr(routes._vector_store, "index_candidate", lambda candidate: 2)
    client = TestClient(app)
    single = client.post("/api/v1/cv/upload", files={"file": ("single.txt", b"CV")})
    assert single.status_code == 201
    batch = client.post("/api/v1/screening/cohort/upload", files=[("files", ("cohort.txt", b"CV"))])
    assert batch.status_code == 202
    status = client.get(f"/api/v1/cv/batch/{batch.json()['batch_id']}").json()
    assert status["status"] == "COMPLETED"
    cid = status["results"][0]["candidate_id"]
    detail = client.get(f"/api/v1/candidates/{cid}").json()
    # FastAPI serializes ContactInfo.phone by alias; the database uses phone_number.
    assert ParsedCV.model_validate(single.json()["parsed_cv"]) == ParsedCV.model_validate(detail["parsed_cv"]) == parsed
    assert sorted(calls) == ["cohort.txt", "single.txt"]


def test_interrupted_runs_preserve_finished_results(funnel):
    client, *_, start = funnel
    run = start()
    run["status"] = "evaluating"
    run["rows"][1]["deep_status"] = "pending"
    asyncio.run(recruiter.save_run(run))
    asyncio.run(recruiter.recover_interrupted_runs())
    restored = client.get(f"/api/v1/screening/runs/{run['id']}").json()
    assert restored["status"] == "partial"
    assert restored["rows"][0]["deep_status"] == "completed"
    assert restored["rows"][1]["deep_status"] == "failed"


@pytest.mark.asyncio
async def test_concurrent_parsing_bounded_and_progress_serialized(monkeypatch):
    active = peak = 0
    results = []
    async def process(self, content_bytes, filename, job_description=None):
        nonlocal active, peak
        assert job_description is None
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.02)
        active -= 1
        return {"filename": filename, "status": "FAILED" if filename == "bad.txt" else "COMPLETED"}
    async def save(batch_id, result, is_success):
        results.append((result, is_success))
    monkeypatch.setattr(BatchProcessorService, "process_single_candidate", process)
    monkeypatch.setattr(DatabaseRepository, "update_batch_progress", save)
    await routes._batch_processor.execute_parse_batch(uuid4(), [(name, b"cv") for name in ["bad.txt", *[f"{i}.txt" for i in range(8)]]])
    assert 1 < peak <= 4 and len(results) == 9
    assert sum(success for _, success in results) == 8


@pytest.mark.parametrize("filename,content", [("cv.exe", b"data"), ("empty.txt", b"")])
def test_cohort_upload_rejects_invalid_files(filename, content):
    client = TestClient(app)
    assert client.post("/api/v1/screening/cohort/upload", files=[("files", (filename, content))]).status_code == 400
