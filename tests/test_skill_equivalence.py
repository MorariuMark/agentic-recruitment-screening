"""
tests/test_skill_equivalence.py
Unit tests verifying transferable skill detection, CEFR language hierarchy,
academic degree hierarchy, cumulative tenure calculation, and benefit-of-the-doubt guardrails.
"""

from uuid import uuid4
import pytest

from backend.schemas.cv import AnonymizedCandidate, Education, LanguageSkill, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import MatchStatus, Recommendation, RequirementMatch, VerbatimCitation
from backend.services.scoring_engine import ScoringEngine
from backend.services.skill_equivalence import SkillEquivalenceService, format_tech_name


def test_language_hierarchy():
    """Verify higher CEFR levels (C1, Native) satisfy lower requirements (B2, B1)."""
    # 1. Candidate has C1, requirement asks for B2 -> satisfied
    langs = [LanguageSkill(language="German", proficiency="C1 Advanced")]
    res = SkillEquivalenceService.evaluate_language_hierarchy(
        languages=langs,
        requirement_title="German Language Skills",
        requirement_description="Minimum B2 level German required for client interaction."
    )
    assert res is not None
    is_satisfied, cand_level, req_level = res
    assert is_satisfied is True

    # 2. Candidate has A2, requirement asks for B2 -> NOT satisfied
    langs_basic = [LanguageSkill(language="German", proficiency="A2 Elementary")]
    res_basic = SkillEquivalenceService.evaluate_language_hierarchy(
        languages=langs_basic,
        requirement_title="German Language Skills",
        requirement_description="Minimum B2 level German required for client interaction."
    )
    assert res_basic is not None
    is_satisfied_basic, _, _ = res_basic
    assert is_satisfied_basic is False


def test_degree_hierarchy():
    """Verify higher academic degrees (MSc, PhD) satisfy lower requirements (BSc)."""
    # 1. Candidate has Master's, requirement asks for Bachelor's -> satisfied
    edu_master = [
        Education(
            degree_title="Master of Science in Computer Science",
            institution_name="Technical University",
            graduation_year=2022
        )
    ]
    res = SkillEquivalenceService.evaluate_degree_hierarchy(
        education_list=edu_master,
        requirement_title="Education",
        requirement_description="Bachelor's degree in Computer Science, Software Engineering or related field."
    )
    assert res is not None
    is_satisfied, cand_degree, req_degree = res
    assert is_satisfied is True

    # 2. Candidate has Bachelor's, requirement asks for Master's -> NOT satisfied
    edu_bachelor = [
        Education(
            degree_title="Bachelor of Science in Informatics",
            institution_name="State University",
            graduation_year=2020
        )
    ]
    res_bachelor = SkillEquivalenceService.evaluate_degree_hierarchy(
        education_list=edu_bachelor,
        requirement_title="Education",
        requirement_description="Master's degree or PhD in Artificial Intelligence or Data Science."
    )
    assert res_bachelor is not None
    is_satisfied_bachelor, _, _ = res_bachelor
    assert is_satisfied_bachelor is False


def test_transferable_skills_detection():
    """Verify adjacent technologies across cloud, database, frontend clusters are detected."""
    # 1. Candidate has GCP and Docker, job requires AWS
    skills = ["Python", "FastAPI", "GCP", "Docker"]
    experiences = [
        WorkExperience(
            job_title="Cloud Engineer",
            company_name="CloudCo",
            work_description=["Deployed microservices on Google Cloud Platform using Cloud Run."],
            skills_used=["GCP", "Python"],
            duration_months=24
        )
    ]

    res = SkillEquivalenceService.find_transferable_skill(
        candidate_skills=skills,
        candidate_experiences=experiences,
        requirement_title="AWS Cloud Infrastructure",
        requirement_description="Experience managing infrastructure on AWS (Amazon Web Services), EC2, and S3."
    )
    assert res is not None
    cand_tech, req_tech, category = res
    assert "GCP" in cand_tech or "Google Cloud" in cand_tech
    assert "AWS" in req_tech
    assert category == "Cloud Infrastructure"

    # 2. Candidate already has AWS -> should NOT trigger transferable skill (exact match)
    skills_with_aws = ["Python", "AWS", "GCP"]
    res_exact = SkillEquivalenceService.find_transferable_skill(
        candidate_skills=skills_with_aws,
        candidate_experiences=experiences,
        requirement_title="AWS Cloud Infrastructure",
        requirement_description="Experience managing infrastructure on AWS."
    )
    assert res_exact is None


def test_cumulative_tenure_calculation():
    """Verify calendar months/years aggregate across multiple work experiences."""
    experiences = [
        WorkExperience(
            job_title="Senior Developer",
            company_name="Company A",
            work_description=["Developed microservices using Python."],
            skills_used=["Python", "FastAPI"],
            duration_months=24
        ),
        WorkExperience(
            job_title="Junior Developer",
            company_name="Company B",
            work_description=["Maintained legacy Python backend."],
            skills_used=["Python", "Django"],
            duration_months=18
        ),
    ]

    tenure = SkillEquivalenceService.calculate_tenure_for_skill(experiences, "Python")
    assert tenure == 3.5  # (24 + 18) / 12 = 3.5 years


def test_transferable_skills_prevent_false_rejection():
    """Verify candidates with transferable competencies are not falsely rejected."""
    scoring = ScoringEngine()

    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_work_experiences=[],
        anonymized_education=[],
        anonymized_skills=["GCP", "PostgreSQL"],
        sanitized_text="Built systems with GCP and PostgreSQL.",
        demographic_data={}
    )

    job = JobDescription(
        title="Backend Engineer",
        requirements=[
            JobRequirement(
                id="req_aws",
                title="AWS Experience",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Experience with AWS"
            ),
            JobRequirement(
                id="req_mysql",
                title="MySQL Experience",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Experience with MySQL"
            ),
        ]
    )

    # Candidate has transferable skills for both requirements (GCP for AWS, PostgreSQL for MySQL)
    matches = [
        RequirementMatch(
            requirement_id="req_aws",
            status=MatchStatus.PARTIAL,
            score=0.70,
            reasoning="Candidate has GCP experience.",
            transferable_skill="GCP → AWS",
            is_objective=True,
        ),
        RequirementMatch(
            requirement_id="req_mysql",
            status=MatchStatus.PARTIAL,
            score=0.70,
            reasoning="Candidate has PostgreSQL experience.",
            transferable_skill="PostgreSQL → MySQL",
            is_objective=True,
        ),
    ]

    eval_result = scoring.compute_evaluation(candidate, job, matches)
    assert eval_result.must_have_score == 70.0
    assert eval_result.overall_score == 77.5
    # Candidate must be BORDERLINE, NOT REJECTED!
    assert eval_result.recommendation == Recommendation.BORDERLINE
    assert eval_result.requirement_matches[0].transferable_skill == "GCP → AWS"
    assert eval_result.requirement_matches[1].transferable_skill == "PostgreSQL → MySQL"


def test_matching_agent_language_guardrail_upgrades_status():
    """Verify MatchingAgent upgrades language requirement to MET if CEFR scale satisfies requirement."""
    from backend.agents.matching_agent import MatchingAgent
    from tests.test_agents import MockTestLLM

    mock_llm = MockTestLLM()
    # Mock LLM returns MET by default, let's create a subclass that returns NOT_MET for test
    class MockUnmetLLM(MockTestLLM):
        def generate_structured(self, prompt, response_model, system_prompt=None, temperature=0.0):
            if response_model == RequirementMatch:
                return RequirementMatch(
                    requirement_id="req_german",
                    status=MatchStatus.NOT_MET,
                    score=0.2,
                    reasoning="Candidate does not explicitly mention B2 certification.",
                    citations=[],
                )
            return super().generate_structured(prompt, response_model, system_prompt, temperature)

    agent = MatchingAgent(llm_client=MockUnmetLLM())

    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_languages=[LanguageSkill(language="German", proficiency="C1 Fluent")],
        sanitized_text="Fluent German speaker.",
        demographic_data={}
    )

    req = JobRequirement(
        id="req_german",
        title="German Language Skills",
        category=RequirementCategory.MUST_HAVE,
        description="Minimum B2 German required."
    )

    match = agent.evaluate_requirement(
        candidate_id=candidate.candidate_id,
        requirement=req,
        candidate=candidate,
    )

    # Hierarchical scale must have upgraded to MET with score 1.0!
    assert match.status == MatchStatus.MET
    assert match.score == 1.0
    assert "Language Hierarchy" in match.reasoning


def test_matching_agent_degree_guardrail_upgrades_status():
    """Verify MatchingAgent upgrades degree requirement to MET if candidate holds higher degree."""
    from backend.agents.matching_agent import MatchingAgent
    from tests.test_agents import MockTestLLM

    class MockUnmetLLM(MockTestLLM):
        def generate_structured(self, prompt, response_model, system_prompt=None, temperature=0.0):
            if response_model == RequirementMatch:
                return RequirementMatch(
                    requirement_id="req_edu",
                    status=MatchStatus.NOT_MET,
                    score=0.3,
                    reasoning="Bachelor's degree not found in text.",
                    citations=[],
                )
            return super().generate_structured(prompt, response_model, system_prompt, temperature)

    agent = MatchingAgent(llm_client=MockUnmetLLM())

    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_education=[
            Education(degree_title="Master of Science in Computer Science", institution_name="TU Munich")
        ],
        sanitized_text="Holds MSc in Computer Science.",
        demographic_data={}
    )

    req = JobRequirement(
        id="req_edu",
        title="Academic Degree",
        category=RequirementCategory.MUST_HAVE,
        description="Bachelor's degree in Computer Science or Software Engineering."
    )

    match = agent.evaluate_requirement(
        candidate_id=candidate.candidate_id,
        requirement=req,
        candidate=candidate,
    )

    # Degree scale must have upgraded to MET with score 1.0!
    assert match.status == MatchStatus.MET
    assert match.score == 1.0
    assert "Degree Hierarchy" in match.reasoning


def test_matching_agent_benefit_of_doubt_guardrail():
    """Verify low-confidence or hedged NOT_MET verdicts upgrade to PARTIAL with interview probe."""
    from backend.agents.matching_agent import MatchingAgent
    from tests.test_agents import MockTestLLM

    class MockHedgedLLM(MockTestLLM):
        def generate_structured(self, prompt, response_model, system_prompt=None, temperature=0.0):
            if response_model == RequirementMatch:
                return RequirementMatch(
                    requirement_id="req_api",
                    status=MatchStatus.NOT_MET,
                    score=0.2,
                    confidence=0.60,  # low confidence (< 0.75)
                    reasoning="It is unclear whether the candidate has built distributed architectures, as it is not explicitly detailed.",
                    citations=[],
                )
            return super().generate_structured(prompt, response_model, system_prompt, temperature)

    agent = MatchingAgent(llm_client=MockHedgedLLM())

    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_skills=["Python", "FastAPI"],
        sanitized_text="Built microservices.",
        demographic_data={}
    )

    req = JobRequirement(
        id="req_api",
        title="Distributed Architecture",
        category=RequirementCategory.MUST_HAVE,
        description="Experience architecting distributed distributed high-load systems."
    )

    match = agent.evaluate_requirement(
        candidate_id=candidate.candidate_id,
        requirement=req,
        candidate=candidate,
    )

    # Guardrail must convert to PARTIAL with benefit of doubt flag
    assert match.status == MatchStatus.PARTIAL
    assert match.score == 0.50
    assert match.benefit_of_doubt is True
    assert "Benefit of the Doubt" in match.reasoning

