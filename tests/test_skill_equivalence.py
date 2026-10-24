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
            reasoning="Candidate has GCP experience.", citations=[{"quote": "GCP"}],
            transferable_skill="GCP → AWS",
            is_objective=True,
        ),
        RequirementMatch(
            requirement_id="req_mysql",
            status=MatchStatus.PARTIAL,
            score=0.70,
            reasoning="Candidate has PostgreSQL experience.", citations=[{"quote": "PostgreSQL"}],
            transferable_skill="PostgreSQL → MySQL",
            is_objective=True,
        ),
    ]

    eval_result = scoring.compute_evaluation(candidate, job, matches)
    assert eval_result.must_have_score == 70.0
    assert eval_result.overall_score == 70.0  # Normalized: no absent preferred bonus
    # Candidate must be BORDERLINE, NOT REJECTED!
    assert eval_result.recommendation == Recommendation.BORDERLINE
    assert eval_result.requirement_matches[0].transferable_skill == "GCP → AWS"
    assert eval_result.requirement_matches[1].transferable_skill == "PostgreSQL → MySQL"


def test_matching_agent_language_guardrail_upgrades_status():
    """Verify MatchingAgent upgrades language requirement to MET if CEFR scale satisfies requirement."""
    from backend.agents.matching_agent import MatchingAgent
    from tests.test_agents import MockTestLLM
    from types import SimpleNamespace

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

    agent = MatchingAgent(llm_client=MockUnmetLLM(), vector_store=SimpleNamespace(query_candidate_chunks=lambda **kw: [{"text": candidate.sanitized_text, "metadata": {"type": "experience"}}]))

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
    assert "Documented" in match.reasoning
    assert match.citations[0].quote == "Fluent German"


def test_matching_agent_degree_guardrail_upgrades_status():
    """Verify MatchingAgent upgrades degree requirement to MET if candidate holds higher degree."""
    from backend.agents.matching_agent import MatchingAgent
    from tests.test_agents import MockTestLLM
    from types import SimpleNamespace

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

    agent = MatchingAgent(llm_client=MockUnmetLLM(), vector_store=SimpleNamespace(query_candidate_chunks=lambda **kw: [{"text": candidate.sanitized_text, "metadata": {"type": "experience"}}]))

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
    from types import SimpleNamespace

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

    agent = MatchingAgent(llm_client=MockHedgedLLM(), vector_store=SimpleNamespace(query_candidate_chunks=lambda **kw: [{"text": candidate.sanitized_text, "metadata": {"type": "experience"}}]))

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


def test_high_school_diploma_not_treated_as_master():
    """Verify 'High School Diploma' does not match 'ma' (Master of Arts) and does not satisfy Bachelor's Degree."""
    edus = [
        Education(degree_title="High School Diploma", field_of_study="Nature Science", institution_name="AMG")
    ]
    res = SkillEquivalenceService.evaluate_degree_hierarchy(
        education_list=edus,
        requirement_title="Academic Degree",
        requirement_description="Bachelor's Degree required.",
    )
    assert res is not None
    is_satisfied, cand_deg, req_deg = res
    assert is_satisfied is False
    assert cand_deg == "High School Diploma"


def test_degree_hierarchy_discipline_mismatch_never_satisfies():
    """Verify candidate with Engineering degree is not evaluated as meeting an Economic Studies degree requirement."""
    edus = [
        Education(degree_title="Bachelor's Degree", field_of_study="Applied Electronics", institution_name="UPT"),
        Education(degree_title="High School Diploma", field_of_study="Nature Science", institution_name="AMG"),
    ]
    res = SkillEquivalenceService.evaluate_degree_hierarchy(
        education_list=edus,
        requirement_title="University Degree in Economic Studies",
        requirement_description="University Degree in Economic Studies",
    )
    # Must be None because candidate has no degree in Economics/Business family
    assert res is None


def test_matching_agent_preserves_field_mismatch_unmet_status():
    """Verify MatchingAgent does not override LLM's NOT_MET verdict when degree field doesn't match."""
    from backend.agents.matching_agent import MatchingAgent
    from tests.test_agents import MockTestLLM
    from types import SimpleNamespace

    class MockFieldMismatchLLM(MockTestLLM):
        def generate_structured(self, prompt, response_model, system_prompt=None, temperature=0.0):
            if response_model == RequirementMatch:
                return RequirementMatch(
                    requirement_id="req_econ",
                    status=MatchStatus.NOT_MET,
                    score=0.0,
                    reasoning="Candidate holds a degree in Applied Electronics. None of these credentials correspond to a university degree in Economic Studies. Therefore the candidate does not meet this objective qualification.",
                    citations=[],
                )
            return super().generate_structured(prompt, response_model, system_prompt, temperature)

    agent = MatchingAgent(llm_client=MockFieldMismatchLLM(), vector_store=SimpleNamespace(query_candidate_chunks=lambda **kw: [{"text": candidate.sanitized_text, "metadata": {"type": "experience"}}]))
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_education=[
            Education(degree_title="Bachelor's Degree (In Progress)", field_of_study="Applied Electronics", institution_name="UPT"),
            Education(degree_title="High School Diploma", field_of_study="Nature Science", institution_name="AMG"),
        ],
        sanitized_text="4th-year Applied Electronics student.",
        demographic_data={},
    )
    req = JobRequirement(
        id="req_econ",
        title="University Degree in Economic Studies",
        category=RequirementCategory.MUST_HAVE,
        description="University Degree in Economic Studies",
    )
    match = agent.evaluate_requirement(
        candidate_id=candidate.candidate_id,
        requirement=req,
        candidate=candidate,
    )
    assert match.status in (MatchStatus.NOT_MET, MatchStatus.CLARIFICATION_NEEDED)
    assert match.score == 0.0
    assert "Degree Hierarchy" not in match.reasoning


def test_location_not_confused_with_language_hierarchy():
    """Verify that a location requirement mentioning Germany is not treated as a German language requirement."""
    langs = [LanguageSkill(language="German", proficiency="C1 (Listening, Reading, Writing)")]

    # 1. Direct service check: must return None
    res = SkillEquivalenceService.evaluate_language_hierarchy(
        languages=langs,
        requirement_title="Location & On-Site Presence (Regensburg, Germany)",
        requirement_description="Ability and authorization to work on-site at the Regensburg location in Germany.",
    )
    assert res is None

    # 2. MatchingAgent workflow check: LLM rejection on location must NOT be overridden to MET
    from backend.agents.matching_agent import MatchingAgent
    from tests.test_agents import MockTestLLM
    from types import SimpleNamespace

    class MockLocationLLM(MockTestLLM):
        def generate_structured(self, prompt, response_model, system_prompt="", temperature=0.0):
            if response_model == RequirementMatch:
                return RequirementMatch(
                    requirement_id="req_loc",
                    status=MatchStatus.NOT_MET,
                    score=0.0,
                    reasoning="Candidate does not have a valid work authorization for Germany, and there is no indication of their ability to work on-site at Regensburg, Germany.",
                    citations=[],
                )
            return super().generate_structured(prompt, response_model, system_prompt, temperature)

    agent = MatchingAgent(llm_client=MockLocationLLM(), vector_store=SimpleNamespace(query_candidate_chunks=lambda **kw: [{"text": candidate.sanitized_text, "metadata": {"type": "experience"}}]))
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_languages=langs,
        sanitized_text="Speaks German at C1 level.",
        demographic_data={},
    )
    req = JobRequirement(
        id="req_loc",
        title="Location & On-Site Presence (Regensburg, Germany)",
        category=RequirementCategory.MUST_HAVE,
        description="Ability and authorization to work on-site at the Regensburg location in Germany.",
    )
    match = agent.evaluate_requirement(
        candidate_id=candidate.candidate_id,
        requirement=req,
        candidate=candidate,
    )
    assert match.status in (MatchStatus.NOT_MET, MatchStatus.CLARIFICATION_NEEDED)
    assert "Language Hierarchy" not in match.reasoning


def test_study_field_mismatch_not_overridden_by_degree_hierarchy():
    """Verify that a study field requirement is not overridden by degree hierarchy when study field does not match."""
    edu = [
        Education(degree_title="Master of Science", field_of_study="Automotive Electronic Systems", institution_name="TU"),
        Education(degree_title="Bachelor", field_of_study="Applied Electronics", institution_name="TU"),
    ]

    # 1. Direct service check: "Relevant Study Field" requirement title must return None
    res = SkillEquivalenceService.evaluate_degree_hierarchy(
        education_list=edu,
        requirement_title="Relevant Study Field",
        requirement_description="Currently enrolled in a degree program in Industrial Engineering, Business Administration, Business Informatics, Mechanical Engineering or a comparable field.",
    )
    assert res is None

    # 2. MatchingAgent workflow check: LLM rejection with "study field does not match" must NOT be overridden to MET
    from backend.agents.matching_agent import MatchingAgent
    from tests.test_agents import MockTestLLM
    from types import SimpleNamespace

    class MockStudyFieldLLM(MockTestLLM):
        def generate_structured(self, prompt, response_model, system_prompt="", temperature=0.0):
            if response_model == RequirementMatch:
                return RequirementMatch(
                    requirement_id="req_study",
                    status=MatchStatus.NOT_MET,
                    score=0.0,
                    reasoning="The candidate's study field does not match the required fields.",
                    citations=[],
                )
            return super().generate_structured(prompt, response_model, system_prompt, temperature)

    agent = MatchingAgent(llm_client=MockStudyFieldLLM(), vector_store=SimpleNamespace(query_candidate_chunks=lambda **kw: [{"text": candidate.sanitized_text, "metadata": {"type": "experience"}}]))
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_education=edu,
        sanitized_text="Master student in Automotive Electronic Systems.",
        demographic_data={},
    )
    req = JobRequirement(
        id="req_study",
        title="Relevant Study Field",
        category=RequirementCategory.MUST_HAVE,
        description="Currently enrolled in a degree program in Industrial Engineering, Business Administration, Business Informatics, Mechanical Engineering or a comparable field.",
    )
    match = agent.evaluate_requirement(
        candidate_id=candidate.candidate_id,
        requirement=req,
        candidate=candidate,
    )
    assert match.status == MatchStatus.NOT_MET
    assert match.score == 0.0
    assert "Degree Hierarchy" not in match.reasoning


def test_e6_tenure_calculations_multi_term_and_no_invented_dates():
    """Verify E6 fixes: conjunctive multi-skill does not over-credit, no 12-month invention, and overlaps merge."""
    from backend.services.tenure_calculator import TenureCalculator

    # 1. Java-only 5-year role against multi-term "Java and Python"
    cand_java_only = AnonymizedCandidate(
        anonymized_work_experiences=[
            WorkExperience(
                job_title="Java Developer",
                skills_used=["Java"],
                start_date="Jan 2018",
                end_date="Dec 2022",  # 60 months = 5.0 years
            )
        ]
    )
    # Conjunctive: requires both Java and Python
    years, dated = TenureCalculator.calculate_requirement_tenure(
        cand_java_only,
        terms=["java", "python"],
        requirement_text="5+ years experience in Java and Python",
    )
    # Must be 0.0, NOT 5.0! Candidate has 0 Python experience.
    assert years == 0.0

    # 2. No invented 12-month tenure for undated role with unstated duration
    cand_blank_exp = AnonymizedCandidate(
        anonymized_work_experiences=[
            WorkExperience(job_title="Software Intern", skills_used=["Python"])
        ]
    )
    tenure_blank = SkillEquivalenceService.calculate_tenure_for_skill(
        cand_blank_exp.anonymized_work_experiences, "Python"
    )
    assert tenure_blank == 0.0  # Must NOT default to 12 months (1.0 year)!

    # 3. Overlapping roles merge calendar intervals
    cand_overlapping = AnonymizedCandidate(
        anonymized_work_experiences=[
            WorkExperience(
                job_title="Role 1",
                skills_used=["Python"],
                start_date="Jan 2020",
                end_date="Dec 2021",  # 24 months
            ),
            WorkExperience(
                job_title="Role 2",
                skills_used=["Python"],
                start_date="Jan 2021",
                end_date="Dec 2022",  # 24 months, 12 months overlap
            ),
        ]
    )
    tenure_overlap = SkillEquivalenceService.calculate_tenure_for_skill(
        cand_overlapping.anonymized_work_experiences, "Python"
    )
    # Jan 2020 to Dec 2022 = 36 months = 3.0 years, NOT 48 months (4.0 years)
    assert tenure_overlap == 3.0
