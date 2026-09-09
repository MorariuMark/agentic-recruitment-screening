"""
tests/test_agents.py
Unit and integration tests for ParserAgent, MatchingAgent, and InterviewAgent with deterministic mocks.
"""

from uuid import UUID, uuid4
import pytest

from backend.agents.interview_agent import InterviewAgent
from backend.agents.llm_factory import BaseLLMClient
from backend.agents.matching_agent import MatchingAgent
from backend.agents.parser_agent import ParserAgent
from backend.schemas.cv import AnonymizedCandidate, ContactInfo, ParsedCV, WorkExperience
from backend.schemas.interview import InterviewPlan, InterviewQuestion, QuestionArchetype
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    Recommendation,
    RequirementMatch,
    VerbatimCitation,
)
from backend.services.scoring_engine import ScoringEngine
from backend.services.vector_store import VectorStoreService


class MockTestLLM(BaseLLMClient):
    """Deterministic LLM mock returning structured responses based on the response_model."""

    def generate_text(self, prompt: str, system_prompt=None, temperature=0.1) -> str:
        return "mock text"

    def generate_structured(self, prompt: str, response_model, system_prompt=None, temperature=0.0):
        if response_model == ParsedCV:
            return ParsedCV(
                contact_info=ContactInfo(
                    full_name="Jordan Lee",
                    email="jordan.lee@example.com",
                    phone_number="+1 555-4321"
                ),
                skills=["Python", "FastAPI"],
                experiences=[
                    WorkExperience(
                        job_title="Software Developer",
                        company_name="Apex Solutions",
                        work_description=["Jordan Lee built REST APIs with Python."],
                        skills_used=["Python"]
                    )
                ]
            )
        elif response_model == RequirementMatch:
            return RequirementMatch(
                requirement_id="req_python",
                status=MatchStatus.MET,
                score=0.9,
                reasoning="Strong match grounded in work experience.",
                citations=[VerbatimCitation(quote="built REST APIs with Python", verified=True)]
            )
        elif response_model == InterviewPlan:
            return InterviewPlan(
                candidate_id=uuid4(),
                job_id=uuid4(),
                total_estimated_minutes=45,
                interview_focus_summary="Focus on backend concurrency and architectural scaling.",
                questions=[
                    InterviewQuestion(
                        id="q1",
                        target_requirement_id="req_python",
                        archetype=QuestionArchetype.TECHNICAL_DEEP_DIVE,
                        question_text="How did you structure concurrency in your REST APIs?",
                        expected_positive_signals=["Mentions asyncio event loop"],
                        red_flags=["Cannot explain async vs sync"],
                        estimated_minutes=15
                    )
                ]
            )
        return response_model()


def test_parser_agent_pipeline():
    """Verify ParserAgent extracts structured CV and sanitizes PII."""
    mock_llm = MockTestLLM()
    parser = ParserAgent(llm_client=mock_llm)

    raw_text = "Jordan Lee resume. jordan.lee@example.com. Built REST APIs with Python."
    parsed, anonymized = parser.parse_and_anonymize(raw_text)

    assert parsed.contact_info.full_name == "Jordan Lee"
    assert "Jordan Lee" not in anonymized.anonymized_work_experiences[0].work_description[0]
    assert "[CANDIDATE_NAME]" in anonymized.anonymized_work_experiences[0].work_description[0]


def test_matching_agent_pipeline(tmp_path):
    """Verify MatchingAgent evaluates candidate against JD criteria."""
    vstore = VectorStoreService(persist_directory=str(tmp_path / "chroma"))
    mock_llm = MockTestLLM()
    agent = MatchingAgent(llm_client=mock_llm, vector_store=vstore, scoring_engine=ScoringEngine())

    cid = uuid4()
    candidate = AnonymizedCandidate(
        candidate_id=cid,
        anonymized_work_experiences=[
            WorkExperience(
                job_title="Developer",
                company_name="TechCo",
                work_description=["built REST APIs with Python and async microservices."],
                skills_used=["Python"]
            )
        ],
        sanitized_text="built REST APIs with Python and async microservices.",
        demographic_data={}
    )

    jd = JobDescription(
        title="Python Engineer",
        requirements=[
            JobRequirement(
                id="req_python",
                title="Python Experience",
                category=RequirementCategory.MUST_HAVE,
                description="Experience building REST APIs with Python."
            )
        ]
    )

    eval_result = agent.match_candidate(candidate, jd)
    assert eval_result.overall_score >= 80.0
    assert eval_result.recommendation == Recommendation.STRONG_MATCH
    assert len(eval_result.requirement_matches) == 1
    assert eval_result.requirement_matches[0].citations[0].verified is True


def test_interview_agent_pipeline():
    """Verify InterviewAgent synthesizes rubric-driven interview plan."""
    mock_llm = MockTestLLM()
    agent = InterviewAgent(llm_client=mock_llm)

    cid = uuid4()
    candidate = AnonymizedCandidate(candidate_id=cid, demographic_data={})
    jid = uuid4()
    jd = JobDescription(id=jid, title="Backend Developer", requirements=[])
    eval_res = MatchEvaluationResult(
        candidate_id=cid,
        job_id=jid,
        overall_score=85.0,
        must_have_score=85.0,
        recommendation=Recommendation.STRONG_MATCH,
        citation_verification_score=1.0
    )

    plan = agent.generate_interview_plan(candidate, jd, eval_res)
    assert plan.candidate_id == cid
    assert plan.job_id == jid
    assert len(plan.questions) == 1
    assert plan.questions[0].archetype == QuestionArchetype.TECHNICAL_DEEP_DIVE
