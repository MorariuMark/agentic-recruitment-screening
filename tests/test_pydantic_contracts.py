"""
tests/test_pydantic_contracts.py
Unit tests verifying strict Pydantic v2 data contracts across CV, Job, Match, and Interview schemas.
"""

from uuid import UUID, uuid4
import pytest

from backend.schemas.cv import (
    AnonymizedCandidate,
    ContactInfo,
    Education,
    ParsedCV,
    WorkExperience,
)
from backend.schemas.job import (
    JobDescription,
    JobRequirement,
    RequirementCategory,
)
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    Recommendation,
    RequirementMatch,
    VerbatimCitation,
)
from backend.schemas.interview import (
    InterviewPlan,
    InterviewQuestion,
    QuestionArchetype,
)


def test_cv_schemas_validation():
    """Verify CV schema serialization and constraint validation."""
    contact = ContactInfo(
        full_name="Jane Doe",
        email="jane.doe@example.com",
        phone_number="+1 555-0199",
        linkedin_url="https://linkedin.com/in/janedoe"
    )
    exp = WorkExperience(
        job_title="AI Engineer",
        company_name="Tech Solutions",
        work_description=["Developed LLM evaluation pipelines."],
        skills_used=["Python", "FastAPI"]
    )
    edu = Education(
        degree_title="B.S. Computer Science",
        institution_name="MIT",
        graduation_year=2020
    )
    cv = ParsedCV(
        contact_info=contact,
        skills=["Python", "PyTorch"],
        experiences=[exp],
        education=[edu]
    )

    assert cv.contact_info.full_name == "Jane Doe"
    assert len(cv.experiences) == 1
    assert cv.experiences[0].skills_used == ["Python", "FastAPI"]

    anonymized = AnonymizedCandidate(
        anonymized_work_experiences=[exp],
        anonymized_education=[edu],
        anonymized_skills=["Python", "PyTorch"],
        demographic_data={"name_redacted": "Jane Doe"}
    )
    assert isinstance(anonymized.candidate_id, UUID)
    assert anonymized.demographic_data["name_redacted"] == "Jane Doe"


def test_job_description_schemas_validation():
    """Verify JobDescription and JobRequirement constraints."""
    req = JobRequirement(
        id="req_python_rag",
        title="Python RAG Systems",
        category=RequirementCategory.MUST_HAVE,
        weight=1.0,
        description="Must have 3+ years experience with vector embeddings in Python.",
        minimum_years_experience=3
    )
    jd = JobDescription(
        title="Senior AI Engineer",
        requirements=[req]
    )
    assert jd.requirements[0].id == "req_python_rag"
    assert jd.requirements[0].category == RequirementCategory.MUST_HAVE


def test_match_evaluation_schemas_validation():
    """Verify MatchEvaluationResult decision matrix constraints."""
    cit = VerbatimCitation(
        quote="Developed LLM evaluation pipelines.",
        source_section="Work Experience",
        verified=True
    )
    match = RequirementMatch(
        requirement_id="req_python_rag",
        status=MatchStatus.MET,
        score=0.95,
        reasoning="Candidate built production LLM pipelines.",
        citations=[cit]
    )
    eval_res = MatchEvaluationResult(
        candidate_id=uuid4(),
        job_id=uuid4(),
        overall_score=95.0,
        must_have_score=95.0,
        nice_to_have_score=90.0,
        recommendation=Recommendation.STRONG_MATCH,
        requirement_matches=[match],
        must_have_gaps_count=0,
        citation_verification_score=1.0,
        hitl_validated=False
    )
    assert eval_res.recommendation == Recommendation.STRONG_MATCH
    assert eval_res.requirement_matches[0].citations[0].verified is True


def test_interview_plan_schemas_validation():
    """Verify InterviewPlan and archetype constraints."""
    q = InterviewQuestion(
        id="q_rag_indexing",
        target_requirement_id="req_python_rag",
        archetype=QuestionArchetype.TECHNICAL_DEEP_DIVE,
        question_text="How did you structure chunk overlap in your vector database?",
        expected_positive_signals=["Mentions chunk size and token limits", "Discusses boundary preservation"],
        red_flags=["Vague responses about embeddings"],
        estimated_minutes=15
    )
    plan = InterviewPlan(
        candidate_id=uuid4(),
        job_id=uuid4(),
        questions=[q],
        total_estimated_minutes=45,
        interview_focus_summary="Probe vector indexing mechanics."
    )
    assert len(plan.questions) == 1
    assert plan.questions[0].archetype == QuestionArchetype.TECHNICAL_DEEP_DIVE
