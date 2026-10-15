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


def test_perfect_match_90_percent_normalized_to_100():
    """Verify MET requirements with 0.90 score and no gap_analysis normalize to 1.0 (100%)."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_work_experiences=[],
        anonymized_education=[],
        anonymized_skills=["Python", "FastAPI"],
        sanitized_text="5 years building microservices in Python and FastAPI.",
        demographic_data={},
    )
    job = JobDescription(
        title="Backend Engineer",
        requirements=[
            JobRequirement(
                id="req_python",
                title="Python & FastAPI",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Strong Python and FastAPI experience",
            )
        ],
    )
    matches = [
        RequirementMatch(
            requirement_id="req_python",
            status=MatchStatus.MET,
            score=0.90,
            reasoning="Candidate clearly meets Python and FastAPI requirement.",
            gap_analysis=None,
            citations=[VerbatimCitation(quote="microservices in Python and FastAPI", verified=True)],
        )
    ]

    result = scoring.compute_evaluation(candidate, job, matches, strictness=50)
    assert result.requirement_matches[0].score == 1.0
    assert result.overall_score == 100.0
    assert result.strictness == 50
    assert result.recommendation == Recommendation.STRONG_MATCH


def test_strictness_slider_calibration():
    """Verify strictness slider (0-100) adjusts verdict thresholds appropriately."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_work_experiences=[],
        anonymized_education=[],
        anonymized_skills=["Python"],
        sanitized_text="Experience with Python backend systems.",
        demographic_data={},
    )
    job = JobDescription(
        title="Python Developer",
        requirements=[
            JobRequirement(
                id="req_1",
                title="Python",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Python development",
            ),
            JobRequirement(
                id="req_2",
                title="Kubernetes",
                category=RequirementCategory.NICE_TO_HAVE,
                weight=1.0,
                description="Kubernetes deployment",
            ),
        ],
    )
    # Overall score = 0.75 * 85 + 0.25 * 40 = 63.75 + 10 = 73.75%
    matches = [
        RequirementMatch(
            requirement_id="req_1",
            status=MatchStatus.MET,
            score=0.85,
            reasoning="Met with minor tenure note",
            gap_analysis="Slightly shorter tenure than ideal",
        ),
        RequirementMatch(
            requirement_id="req_2",
            status=MatchStatus.PARTIAL,
            score=0.40,
            reasoning="Docker only",
            gap_analysis="No direct K8s",
        ),
    ]

    # At balanced strictness (50), 73.75% with 0 must-have gaps is STRONG_MATCH
    res_balanced = scoring.compute_evaluation(candidate, job, matches, strictness=50)
    assert res_balanced.strictness == 50
    assert res_balanced.recommendation == Recommendation.STRONG_MATCH

    # At forensic strictness (95), strong match threshold rises above 75%, making 73.75% BORDERLINE
    res_strict = scoring.compute_evaluation(candidate, job, matches, strictness=95)
    assert res_strict.strictness == 95
    assert res_strict.recommendation == Recommendation.BORDERLINE


def test_progress_tracker_lifecycle():
    """Verify thread-safe ProgressTracker tracks real step completion accurately."""
    from backend.services.progress_tracker import ProgressTracker

    tracker = ProgressTracker()
    tracker.start_task("match_evaluation", label="Evaluating candidate", total_steps=4, phase="Starting")

    state1 = tracker.get_active_progress("match_evaluation")
    assert state1["active"] is True
    assert state1["total_steps"] == 4
    assert state1["completed_steps"] == 0

    tracker.update_task("match_evaluation", completed_steps=2, phase="Evaluating requirement 2/4", item_completed="Python")
    state2 = tracker.get_active_progress("match_evaluation")
    assert state2["completed_steps"] == 2
    assert state2["percentage"] == 50.0
    assert "Python" in state2["completed_items"]

    tracker.finish_task("match_evaluation", phase="Completed")
    state3 = tracker.get_active_progress("match_evaluation")
    assert state3["active"] is False
    assert state3["percentage"] == 100.0


