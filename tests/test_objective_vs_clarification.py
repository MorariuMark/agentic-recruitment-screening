import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from backend.agents.matching_agent import MatchingAgent, is_interpretive_requirement
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobRequirement, RequirementCategory
from backend.schemas.match import MatchStatus, RequirementMatch, VerbatimCitation


def test_objective_skills_not_in_cv_return_not_met_never_clarification_needed():
    """
    Verify that objective skills (e.g. Apache Spark, Delta Lake) not found in the CV
    are marked as NOT MET (score: 0.0) and NEVER as clarification_needed.
    Clarification needed is strictly reserved for subjective / interpretive matters.
    """
    llm = MagicMock()
    vectors = MagicMock()
    vectors.query_candidate_chunks.return_value = []

    agent = MatchingAgent(llm_client=llm, vector_store=vectors)
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        sanitized_text="Senior Web Developer with JavaScript, React, and Node.js experience.",
        demographic_data={},
    )

    spark_req = JobRequirement(
        id="spark_req",
        title="Apache Spark Proficiency",
        category=RequirementCategory.MUST_HAVE,
        description="Experience developing large-scale distributed data pipelines using Apache Spark.",
    )
    delta_req = JobRequirement(
        id="delta_req",
        title="Delta Lake Architecture",
        category=RequirementCategory.MUST_HAVE,
        description="Deep architectural knowledge of Delta Lake ACID transactions and lakehouse paradigms.",
    )

    assert is_interpretive_requirement(spark_req) is False
    assert is_interpretive_requirement(delta_req) is False

    spark_result = agent.evaluate_requirement(candidate.candidate_id, spark_req, candidate=candidate)
    assert spark_result.status == MatchStatus.NOT_MET
    assert spark_result.score == 0.0
    assert spark_result.is_objective is True
    assert spark_result.clarification_question is None
    assert "No documented evidence" in spark_result.reasoning
    assert "Apache Spark Proficiency" in spark_result.reasoning
    assert "unknown, not a negative finding" not in spark_result.reasoning

    delta_result = agent.evaluate_requirement(candidate.candidate_id, delta_req, candidate=candidate)
    assert delta_result.status == MatchStatus.NOT_MET
    assert delta_result.score == 0.0
    assert delta_result.is_objective is True
    assert delta_result.clarification_question is None
    assert "No documented evidence" in delta_result.reasoning
    assert "Delta Lake Architecture" in delta_result.reasoning
    assert "unknown, not a negative finding" not in delta_result.reasoning


def test_llm_clarification_needed_override_for_objective_skills():
    """
    Verify that even if an LLM returns clarification_needed for an objective skill,
    the deterministic guardrail coerces it to NOT_MET (when unevidenced).
    """
    llm = MagicMock()
    # Mock LLM returning clarification_needed on an objective skill
    llm.generate_structured.return_value = RequirementMatch(
        requirement_id="spark_req",
        status=MatchStatus.CLARIFICATION_NEEDED,
        score=0.5,
        confidence=0.9,
        reasoning="No evidence of Apache Spark was found in the candidate profile.",
        citations=[],
        clarification_question="Do you have Spark experience? [Yes / No]",
    )

    vectors = MagicMock()
    vectors.query_candidate_chunks.return_value = [{"text": "Handled large database queries.", "metadata": {}}]

    agent = MatchingAgent(llm_client=llm, vector_store=vectors)
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        sanitized_text="Handled large database queries in SQL.",
        demographic_data={},
    )

    spark_req = JobRequirement(
        id="spark_req",
        title="Apache Spark Proficiency",
        category=RequirementCategory.MUST_HAVE,
        description="Experience developing large-scale distributed data pipelines using Apache Spark.",
    )

    result = agent.evaluate_requirement(candidate.candidate_id, spark_req, candidate=candidate)
    assert result.status == MatchStatus.NOT_MET
    assert result.score == 0.0
    assert result.is_objective is True
    assert result.clarification_question is None


def test_subjective_interpretive_matters_still_use_clarification_needed():
    """
    Verify that subjective / logistical requirements (e.g. Willingness to travel, Shifts)
    when absent from the CV still correctly trigger clarification_needed with score 0.5.
    """
    llm = MagicMock()
    vectors = MagicMock()
    vectors.query_candidate_chunks.return_value = []

    agent = MatchingAgent(llm_client=llm, vector_store=vectors)
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        sanitized_text="Software engineer working remotely from home.",
        demographic_data={},
    )

    travel_req = JobRequirement(
        id="travel_req",
        title="Willingness to Travel",
        category=RequirementCategory.MUST_HAVE,
        description="Willingness to travel internationally up to 25% for customer deployments.",
    )

    assert is_interpretive_requirement(travel_req) is True

    result = agent.evaluate_requirement(candidate.candidate_id, travel_req, candidate=candidate)
    assert result.status == MatchStatus.CLARIFICATION_NEEDED
    assert result.score == 0.5
    assert result.is_objective is False
    assert result.clarification_question is not None
    assert "travel" in result.clarification_question.lower()
