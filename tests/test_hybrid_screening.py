"""Deterministic evidence-ranking regressions. No model download or LLM calls."""
from uuid import UUID
import numpy as np
import pytest

from backend.schemas.cv import AnonymizedCandidate, Education, LanguageSkill, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement
from backend.services.hybrid_screening import HybridRankingEngine, evidence_units, feature_key, relevant_years


def requirement(title="Python", **kwargs):
    return JobRequirement(id="req", title=title, description=title, category="must_have", **kwargs)


def embed(texts):
    words = ["python", "java", "javascript", "german", "degree", "sql"]
    return [[float(word in text.lower().split()) for word in words] for text in texts]


def rank(candidates, req=None, engine=None):
    return (engine or HybridRankingEngine(embed)).rank(candidates, JobDescription(title="Role", requirements=[req or requirement()]))


def test_demonstrated_work_beats_listed_keywords_and_preserves_evidence():
    listed = AnonymizedCandidate(anonymized_skills=["Python"])
    work = AnonymizedCandidate(anonymized_work_experiences=[WorkExperience(job_title="Developer", work_description=["Built Python APIs"])])
    rows = rank([listed, work])
    assert rows[0].candidate_id == work.candidate_id
    assert rows[0].essential_supported == 1 and rows[1].essential_supported == 0
    assert rows[0].requirement_assessments[0].evidence[0].section == "experience[0]"


def test_unknown_is_not_contradiction_and_java_is_not_javascript():
    candidate = AnonymizedCandidate(anonymized_skills=["JavaScript"])
    row = rank([candidate], requirement("Java"))[0]
    assert row.essential_unknown == 1 and row.essential_contradicted == 0
    assert row.pre_screen_score == 0


@pytest.mark.parametrize("level,status", [(None,"unknown"), ("unknown","unknown"), ("some knowledge","unknown"), ("A2","contradicted"), ("B2","supported"), ("C1","supported")])
def test_languages_require_recognized_documented_levels(level, status):
    candidate = AnonymizedCandidate(anonymized_languages=[LanguageSkill(language="German", proficiency=level)])
    row = rank([candidate], requirement("German language B2"))[0]
    assert row.requirement_assessments[0].status == status


def test_explicit_low_cefr_requirement_is_not_promoted_to_b1():
    candidate = AnonymizedCandidate(anonymized_languages=[LanguageSkill(language="Deutsch", proficiency="A2")])
    assert rank([candidate], requirement("German language A1"))[0].essential_supported == 1


def test_missing_degree_is_unknown_and_wrong_discipline_never_passes():
    candidate = AnonymizedCandidate(anonymized_education=[Education(degree_title="Master in Economics", field_of_study="Economics")])
    assert rank([candidate], requirement("Bachelor degree Computer Science"))[0].essential_unknown == 1


def test_alias_has_consistent_evidence_and_tenure():
    candidate = AnonymizedCandidate(anonymized_work_experiences=[WorkExperience(job_title="Database developer", work_description=["Maintained Postgres databases"], skills_used=["Postgres"], start_date="2020-01", end_date="2023-12")])
    result = rank([candidate], requirement("PostgreSQL", minimum_years_experience=3))[0].requirement_assessments[0]
    assert result.status == "supported" and result.documented_years == 4
    assert result.evidence and "Postgres" in result.evidence[0].text


def test_overlapping_dates_and_undated_roles_do_not_invent_extra_tenure():
    candidate = AnonymizedCandidate(anonymized_work_experiences=[
        WorkExperience(skills_used=["Python"], start_date="2020-01", end_date="2022-12"),
        WorkExperience(skills_used=["Python"], start_date="2021-01", end_date="2023-12"),
        WorkExperience(skills_used=["Python"], duration_months=36)])
    assert relevant_years(candidate, ["python"]) == (4, False)
    assert rank([candidate], requirement(minimum_years_experience=5))[0].requirement_assessments[0].status == "partial"


@pytest.mark.parametrize("start,end,status,score", [
    ("2015-01", "2024-12", "supported", 100),
    ("2023-01", "2024-12", "partial", 40),
    (None, None, "unknown", 0),
])
def test_generic_tenure_counts_all_professional_roles(start, end, status, score):
    candidate = AnonymizedCandidate(anonymized_work_experiences=[
        WorkExperience(job_title="Engineer", start_date=start, end_date=end)])
    req = requirement("Experience", minimum_years_experience=5)
    req.description = "Minimum 5 years of experience"
    assessment = rank([candidate], req)[0].requirement_assessments[0]
    assert assessment.status == status and assessment.score == score
    assert assessment.evidence and assessment.evidence[0].section == "experience[0]"


def test_evidence_cache_reuses_cv_vectors_and_invalidates_model_or_content():
    candidate = AnonymizedCandidate(anonymized_skills=["Python"])
    first = HybridRankingEngine(embed, "embedding-v1")
    initial = rank([candidate], engine=first)
    calls = []
    def cached_embed(texts):
        calls.extend(texts)
        return embed(texts)
    second = HybridRankingEngine(cached_embed, "embedding-v1", first.cache_updates)
    repeated = rank([candidate], engine=second)
    assert len(calls) == 1 and second.diagnostics["cache_hits"] == 1
    assert repeated[0].pre_screen_score == initial[0].pre_screen_score
    assert feature_key(candidate, "embedding-v1") != feature_key(candidate, "embedding-v2")
    candidate.anonymized_skills.append("SQL")
    assert feature_key(candidate, "embedding-v1") not in first.cache_updates


def test_empty_profiles_and_zero_vectors_are_finite_and_deterministic():
    candidates = [AnonymizedCandidate(candidate_id=UUID(int=i)) for i in [2,1]]
    rows = rank(candidates, engine=HybridRankingEngine(lambda texts: np.zeros((len(texts), 3))))
    assert [row.candidate_id.int for row in rows] == [1,2]
    assert all(row.pre_screen_score == 0 and row.essential_unknown == 1 for row in rows)


def test_bounded_evidence_excludes_names_contacts_and_demographics():
    candidate = AnonymizedCandidate(sanitized_text="SECRET", demographic_data={"age": "SECRET"},
        anonymized_work_experiences=[WorkExperience(work_description=["Python evidence " * 5000])])
    units = evidence_units(candidate)
    assert len(units) <= 40 and all(len(unit.text) <= 1000 for unit in units)
    assert "SECRET" not in " ".join(unit.text for unit in units)


def test_rerank_changes_only_pool_and_keeps_scores_separate():
    candidates = [AnonymizedCandidate(candidate_id=UUID(int=i), anonymized_work_experiences=[WorkExperience(work_description=["Python"])] ) for i in [1,2,3]]
    engine = HybridRankingEngine(embed)
    job = JobDescription(title="Developer", requirements=[requirement()])
    rows = engine.rank(candidates, job)
    class Reranker:
        def predict(self, pairs):
            return [1, 10]
    result = engine.rerank(rows, job, Reranker(), 2)
    assert [row.candidate_id.int for row in result] == [2,1,3]
    assert [row.rank for row in result] == [1,2,3]
    assert result[0].pre_screen_score == 100 and result[0].rerank_score == 10
    assert not result[2].reranked


def test_invalid_reranker_output_is_rejected():
    engine = HybridRankingEngine(embed)
    job = JobDescription(title="Developer", requirements=[requirement()])
    rows = engine.rank([AnonymizedCandidate(anonymized_skills=["Python"])], job)
    class Broken:
        def predict(self, pairs):
            return [float("nan")]
    with pytest.raises(ValueError, match="invalid scores"):
        engine.rerank(rows, job, Broken(), 1)


def test_soft_skills_do_not_receive_automatic_proof_scores():
    req = requirement("Communication")
    req.category = "soft_skill"
    result = rank([AnonymizedCandidate(anonymized_skills=["Communication"])], req)[0]
    assert result.requirement_assessments[0].status == "unknown" and result.pre_screen_score == 0


def test_explicit_negative_claim_is_not_positive_keyword_proof():
    candidate = AnonymizedCandidate(anonymized_work_experiences=[WorkExperience(work_description=["No experience with Python"])])
    result = rank([candidate])[0]
    assert result.essential_supported == 0 and result.essential_unknown == 1


def test_one_relevant_passage_does_not_make_unrelated_passages_evidence():
    from backend.schemas.screening import EvidencePassage
    candidate = AnonymizedCandidate()
    relevant = EvidencePassage(id="good", section="experience[0]", text="Built REST services", strength="demonstrated")
    unrelated = EvidencePassage(id="other", section="experience[1]", text="Painted retail storefronts", strength="demonstrated")
    assessment = HybridRankingEngine.assess(candidate, requirement(), [relevant, unrelated], .8, {"good": .8, "other": .1})
    assert [item.id for item in assessment.evidence] == ["good"]
