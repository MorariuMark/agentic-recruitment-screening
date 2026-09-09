"""
tests/test_scoring.py
Unit tests verifying deterministic scoring engine, verbatim citation verification, and decision matrix.
"""

from uuid import uuid4
import pytest

from backend.schemas.cv import AnonymizedCandidate, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import MatchStatus, Recommendation, RequirementMatch, VerbatimCitation
from backend.services.scoring_engine import ScoringEngine


def test_citation_verbatim_grounding():
    """Verify verify_citations checks exact substrings normalized for whitespace."""
    scoring = ScoringEngine()
    source_text = "Engineered scalable REST APIs with FastAPI and PostgreSQL on AWS."

    cits = [
        VerbatimCitation(quote="REST APIs with FastAPI and PostgreSQL", source_section="Experience"),
        VerbatimCitation(quote="Engineered React frontends with Redux", source_section="Experience"),
    ]

    verified, cvs = scoring.verify_citations(cits, source_text)
    assert len(verified) == 2
    assert verified[0].verified is True
    assert verified[1].verified is False
    assert cvs == 0.5


def test_scoring_weights_and_decision_matrix():
    """Verify 75% Must-Have + 25% Nice-to-Have weighting and decision tiers."""
    scoring = ScoringEngine()

    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_work_experiences=[],
        anonymized_education=[],
        anonymized_skills=["Python", "FastAPI"],
        sanitized_text="Built microservices in Python and FastAPI.",
        demographic_data={}
    )

    job = JobDescription(
        title="Software Engineer",
        requirements=[
            JobRequirement(
                id="req_must_1",
                title="Python",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Python experience"
            ),
            JobRequirement(
                id="req_nice_1",
                title="Docker",
                category=RequirementCategory.NICE_TO_HAVE,
                weight=1.0,
                description="Docker experience"
            ),
        ]
    )

    # 1. Strong Match Case: Both requirements met
    matches_strong = [
        RequirementMatch(
            requirement_id="req_must_1",
            status=MatchStatus.MET,
            score=1.0,
            reasoning="Met",
            citations=[VerbatimCitation(quote="Python and FastAPI", verified=True)]
        ),
        RequirementMatch(
            requirement_id="req_nice_1",
            status=MatchStatus.MET,
            score=1.0,
            reasoning="Met"
        ),
    ]
    res_strong = scoring.compute_evaluation(candidate, job, matches_strong)
    assert res_strong.overall_score == 100.0
    assert res_strong.recommendation == Recommendation.STRONG_MATCH
    assert res_strong.must_have_gaps_count == 0

    # 2. Borderline Case: 1 Must-Have gap (status = PARTIAL)
    matches_borderline = [
        RequirementMatch(
            requirement_id="req_must_1",
            status=MatchStatus.PARTIAL,
            score=0.6,
            reasoning="Partial"
        ),
        RequirementMatch(
            requirement_id="req_nice_1",
            status=MatchStatus.MET,
            score=1.0,
            reasoning="Met"
        ),
    ]
    res_borderline = scoring.compute_evaluation(candidate, job, matches_borderline)
    assert res_borderline.must_have_gaps_count == 1
    assert res_borderline.recommendation == Recommendation.BORDERLINE

    # 3. Reject Case: Score < 50%
    matches_reject = [
        RequirementMatch(
            requirement_id="req_must_1",
            status=MatchStatus.NOT_MET,
            score=0.1,
            reasoning="Unmet"
        ),
        RequirementMatch(
            requirement_id="req_nice_1",
            status=MatchStatus.NOT_MET,
            score=0.1,
            reasoning="Unmet"
        ),
    ]
    res_reject = scoring.compute_evaluation(candidate, job, matches_reject)
    assert res_reject.overall_score < 50.0
    assert res_reject.recommendation == Recommendation.REJECT
