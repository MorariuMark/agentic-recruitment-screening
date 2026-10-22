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
        sanitized_text="Built microservices in Python and FastAPI. Used Docker.",
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
            reasoning="Met", citations=[VerbatimCitation(quote="Docker")]
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
            reasoning="Partial", citations=[VerbatimCitation(quote="Python")]
        ),
        RequirementMatch(
            requirement_id="req_nice_1",
            status=MatchStatus.MET,
            score=1.0,
            reasoning="Met", citations=[VerbatimCitation(quote="Docker")]
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
        sanitized_text="Experience with Python backend systems. Docker only.",
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
            gap_analysis="Slightly shorter tenure than ideal", citations=[VerbatimCitation(quote="Python backend systems")],
        ),
        RequirementMatch(
            requirement_id="req_2",
            status=MatchStatus.PARTIAL,
            score=0.40,
            reasoning="Docker only",
            gap_analysis="No direct K8s", citations=[VerbatimCitation(quote="Docker only")],
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


def test_citation_verification_constrains_score_and_invalidates_fabricated_quotes():
    """Verify fabricated citations invalidate MET status, constrain score, and lower recommendation."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        sanitized_text="Junior developer with 1 year Python experience.",
        demographic_data={},
    )
    job = JobDescription(
        title="Senior Python Engineer",
        requirements=[
            JobRequirement(
                id="req_python",
                title="Python Experience",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="10+ years enterprise Python experience",
            )
        ],
    )
    # LLM claimed MET with 1.0 score but fabricated the quote (not in CV)
    matches = [
        RequirementMatch(
            requirement_id="req_python",
            status=MatchStatus.MET,
            score=1.0,
            reasoning="Candidate claims 10 years Python at Google.",
            citations=[
                VerbatimCitation(
                    quote="10 years leading Python distributed backend systems at Google",
                    verified=False,
                )
            ],
        )
    ]

    result = scoring.compute_evaluation(candidate, job, matches)

    # 1. Must NOT produce 100/100 or STRONG_MATCH
    assert result.must_have_score <= 50.0
    assert result.overall_score < 70.0
    assert result.recommendation != Recommendation.STRONG_MATCH
    assert result.recommendation == Recommendation.BORDERLINE

    # 2. Status downgraded to CLARIFICATION_NEEDED and score capped at <= 0.50
    req_match = result.requirement_matches[0]
    assert req_match.status == MatchStatus.CLARIFICATION_NEEDED
    assert req_match.score <= 0.50
    assert "Citation verification failed" in (req_match.gap_analysis or "")
    assert req_match.clarification_question is not None

    # 3. Citation verification score must be 0.0
    assert result.citation_verification_score == 0.0


def test_empty_citations_yields_zero_coverage_score():
    """Verify empty citations report 0.0 coverage rather than 1.0 perfect verification."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(
        candidate_id=uuid4(),
        sanitized_text="Software engineer.",
        demographic_data={},
    )
    cits, score = scoring.verify_citations([], candidate.sanitized_text)
    assert cits == []
    assert score == 0.0

    job = JobDescription(
        title="Developer",
        requirements=[
            JobRequirement(
                id="req_1",
                title="Coding",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Coding skills",
            )
        ],
    )
    matches = [
        RequirementMatch(
            requirement_id="req_1",
            status=MatchStatus.MET,
            score=0.90,
            reasoning="Looks good",
            citations=[],
        )
    ]
    result = scoring.compute_evaluation(candidate, job, matches)
    assert result.citation_verification_score == 0.0


def test_missing_and_empty_matches_rejected():
    """Verify missing, empty, or partial requirement matches raise ValueError."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(candidate_id=uuid4(), sanitized_text="Dev", demographic_data={})
    job = JobDescription(
        title="Engineer",
        requirements=[
            JobRequirement(id="req_1", title="Req 1", category=RequirementCategory.MUST_HAVE, weight=1.0, description="D1"),
            JobRequirement(id="req_2", title="Req 2", category=RequirementCategory.MUST_HAVE, weight=1.0, description="D2"),
        ],
    )

    # 1. Empty matches must raise ValueError (cannot produce 100/100 STRONG_MATCH)
    with pytest.raises(ValueError) as exc:
        scoring.compute_evaluation(candidate, job, [])
    assert "Missing evaluation match for requirement" in str(exc.value)

    # 2. Incomplete matches (covering only req_1) must raise ValueError
    partial_match = [RequirementMatch(requirement_id="req_1", status=MatchStatus.MET, score=1.0, reasoning="Met")]
    with pytest.raises(ValueError) as exc:
        scoring.compute_evaluation(candidate, job, partial_match)
    assert "Missing evaluation match for requirement 'Req 2'" in str(exc.value)


def test_duplicate_and_unknown_matches_rejected():
    """Verify duplicate and unknown requirement IDs in matches raise ValueError."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(candidate_id=uuid4(), sanitized_text="Dev", demographic_data={})
    job = JobDescription(
        title="Engineer",
        requirements=[
            JobRequirement(id="req_1", title="Req 1", category=RequirementCategory.MUST_HAVE, weight=1.0, description="D1")
        ],
    )

    # Duplicate match ID
    dups = [
        RequirementMatch(requirement_id="req_1", status=MatchStatus.MET, score=1.0, reasoning="Met"),
        RequirementMatch(requirement_id="req_1", status=MatchStatus.MET, score=1.0, reasoning="Met duplicate"),
    ]
    with pytest.raises(ValueError) as exc:
        scoring.compute_evaluation(candidate, job, dups)
    assert "Duplicate evaluation match for requirement ID 'req_1'" in str(exc.value)

    # Unknown match ID
    unknown = [
        RequirementMatch(requirement_id="req_unknown", status=MatchStatus.MET, score=1.0, reasoning="Met")
    ]
    with pytest.raises(ValueError) as exc:
        scoring.compute_evaluation(candidate, job, unknown)
    assert "Unknown requirement ID 'req_unknown'" in str(exc.value)


def test_empty_job_requirements_rejected():
    """Verify evaluating against a job with no requirements raises ValueError."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(candidate_id=uuid4(), sanitized_text="Dev", demographic_data={})
    job = JobDescription(title="Empty Job", requirements=[])

    with pytest.raises(ValueError) as exc:
        scoring.compute_evaluation(candidate, job, [])
    assert "contains no requirements" in str(exc.value)


def test_category_weights_normalized_without_absent_bonus():
    """Verify absent preferred criteria do not give an automatic 25-point bonus."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(candidate_id=uuid4(), sanitized_text="Dev", demographic_data={})
    # Job with ONLY must-have requirements
    job = JobDescription(
        title="Engineer",
        requirements=[
            JobRequirement(id="req_1", title="Req 1", category=RequirementCategory.MUST_HAVE, weight=1.0, description="D1")
        ],
    )
    matches = [
        RequirementMatch(requirement_id="req_1", status=MatchStatus.PARTIAL, score=0.60, reasoning="Partial", citations=[VerbatimCitation(quote="Dev")])
    ]
    result = scoring.compute_evaluation(candidate, job, matches)
    assert result.must_have_score == 60.0
    # Must be 60.0, NOT 0.75 * 60 + 0.25 * 100 = 70.0
    assert result.overall_score == 60.0
    assert result.nice_to_have_score == 0.0
def test_zero_weight_criteria_does_not_cause_gap_or_rejection():
    """Verify zero-weight must-have criterion does not produce gaps or cause rejection (E7)."""
    scoring = ScoringEngine()
    candidate = AnonymizedCandidate(candidate_id=uuid4(), sanitized_text="Python expert", demographic_data={})
    job = JobDescription(
        title="Python Dev",
        requirements=[
            JobRequirement(
                id="req_active",
                title="Python",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Core Python",
            ),
            JobRequirement(
                id="req_inactive",
                title="Legacy Tool",
                category=RequirementCategory.MUST_HAVE,
                weight=0.0,
                description="Optional legacy tool with zero weight",
            ),
        ],
    )
    # The active requirement is MET; inactive is NOT_MET
    matches = [
        RequirementMatch(
            requirement_id="req_active",
            status=MatchStatus.MET,
            score=1.0,
            reasoning="Strong Python skills",
            citations=[VerbatimCitation(quote="Python expert", source_section="Summary", verified=True)],
        ),
        RequirementMatch(
            requirement_id="req_inactive",
            status=MatchStatus.NOT_MET,
            score=0.0,
            reasoning="No legacy tool experience",
        ),
    ]

    result = scoring.compute_evaluation(candidate, job, matches)
    assert result.overall_score == 100.0
    assert result.must_have_score == 100.0
    assert result.recommendation == Recommendation.STRONG_MATCH
    assert result.must_have_gaps_count == 0

