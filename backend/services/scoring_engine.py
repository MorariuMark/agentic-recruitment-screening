"""
backend/services/scoring_engine.py
Deterministic weighted scoring and verbatim citation grounding validation engine.
"""

from typing import Dict, List, Tuple
from uuid import UUID

from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    Recommendation,
    RequirementMatch,
    VerbatimCitation,
)


class ScoringEngine:
    """Service responsible for deterministic scoring and citation verification."""

    def __init__(self) -> None:
        pass

    def verify_citations(
        self,
        citations: List[VerbatimCitation],
        source_text: str
    ) -> Tuple[List[VerbatimCitation], float]:
        """
        Validates whether each citation quote exists verbatim in source_text.

        Returns:
            Tuple of (verified_citations_list, citation_verification_score_0_to_1)
        """
        if not citations:
            return [], 1.0

        normalized_source = " ".join(source_text.lower().split())

        verified_citations: List[VerbatimCitation] = []
        valid_count = 0

        for cit in citations:
            norm_quote = " ".join(cit.quote.lower().split())
            is_valid = bool(norm_quote and norm_quote in normalized_source)
            if is_valid:
                valid_count += 1

            verified_citations.append(
                VerbatimCitation(
                    quote=cit.quote,
                    source_section=cit.source_section,
                    verified=is_valid,
                )
            )

        score = valid_count / len(citations)
        return verified_citations, score

    def compute_evaluation(
        self,
        candidate: AnonymizedCandidate,
        job: JobDescription,
        matches: List[RequirementMatch]
    ) -> MatchEvaluationResult:
        """
        Computes deterministic weighted scores and applies the decision matrix.
        """
        req_lookup: Dict[str, JobRequirement] = {r.id: r for r in job.requirements}

        must_have_weighted_score = 0.0
        must_have_total_weight = 0.0
        must_have_gaps_count = 0
        clarification_count = 0

        nice_to_have_weighted_score = 0.0
        nice_to_have_total_weight = 0.0

        all_citations: List[VerbatimCitation] = []
        updated_matches: List[RequirementMatch] = []

        for match in matches:
            req = req_lookup.get(match.requirement_id)
            weight = req.weight if req else 1.0
            category = req.category if req else RequirementCategory.MUST_HAVE

            verified_cits, _ = self.verify_citations(match.citations, candidate.sanitized_text)
            all_citations.extend(verified_cits)

            updated_matches.append(
                RequirementMatch(
                    requirement_id=match.requirement_id,
                    status=match.status,
                    score=match.score,
                    confidence=match.confidence,
                    reasoning=match.reasoning,
                    citations=verified_cits,
                    gap_analysis=match.gap_analysis,
                    is_objective=getattr(match, "is_objective", True),
                    clarification_question=getattr(match, "clarification_question", None),
                    transferable_skill=getattr(match, "transferable_skill", None),
                    benefit_of_doubt=getattr(match, "benefit_of_doubt", False),
                )
            )

            if match.status == MatchStatus.CLARIFICATION_NEEDED:
                clarification_count += 1

            if category == RequirementCategory.MUST_HAVE:
                must_have_total_weight += weight
                must_have_weighted_score += match.score * weight
                # Non-met and partial must-have requirements count as gaps; clarification_needed does NOT disqualify.
                if match.status in (MatchStatus.NOT_MET, MatchStatus.PARTIAL):
                    must_have_gaps_count += 1
            else:
                nice_to_have_total_weight += weight
                nice_to_have_weighted_score += match.score * weight

        must_have_score = (
            (must_have_weighted_score / must_have_total_weight) * 100.0
            if must_have_total_weight > 0
            else 100.0
        )
        nice_to_have_score = (
            (nice_to_have_weighted_score / nice_to_have_total_weight) * 100.0
            if nice_to_have_total_weight > 0
            else 100.0
        )

        overall_score = round(0.75 * must_have_score + 0.25 * nice_to_have_score, 2)
        must_have_score = round(must_have_score, 2)
        nice_to_have_score = round(nice_to_have_score, 2)

        # Count hard objective NOT_MET must-have gaps (excluding transferable skills or benefit-of-the-doubt)
        hard_not_met_count = sum(
            1
            for m in updated_matches
            if req_lookup.get(m.requirement_id)
            and req_lookup[m.requirement_id].category == RequirementCategory.MUST_HAVE
            and m.status == MatchStatus.NOT_MET
            and getattr(m, "is_objective", True)
        )

        # Decision Matrix:
        # A candidate is REJECTED only for hard objective shortcomings:
        # - >= 2 hard objective must-have requirements NOT MET (complete lack of qualification/experience), or
        # - >= 1 must-have gap and overall_score < 50.0, or
        # - >= 2 must-have gaps where overall_score < 55.0 and at least 1 hard NOT_MET
        # If candidate has transferable skills or partial competencies with overall_score >= 55.0
        # and < 2 hard NOT_MET gaps:
        # - Advanced to BORDERLINE (or STRONG_MATCH if high-scoring and 0 hard gaps). Under no circumstances falsely REJECTED!
        has_multiple_hard_rejections = hard_not_met_count >= 2
        is_failing_score = overall_score < 50.0
        is_subpar_with_hard_gap = must_have_gaps_count >= 2 and overall_score < 55.0 and hard_not_met_count >= 1

        if has_multiple_hard_rejections or (must_have_gaps_count >= 1 and is_failing_score) or is_subpar_with_hard_gap:
            recommendation = Recommendation.REJECT
        elif must_have_gaps_count >= 1 or clarification_count > 0 or (50.0 <= overall_score < 70.0):
            recommendation = Recommendation.BORDERLINE
        else:
            recommendation = Recommendation.STRONG_MATCH

        total_valid = sum(1 for c in all_citations if c.verified)
        global_cvs = (total_valid / len(all_citations)) if all_citations else 1.0

        return MatchEvaluationResult(
            candidate_id=candidate.candidate_id,
            job_id=job.id,
            overall_score=overall_score,
            must_have_score=must_have_score,
            nice_to_have_score=nice_to_have_score,
            recommendation=recommendation,
            requirement_matches=updated_matches,
            must_have_gaps_count=must_have_gaps_count,
            clarification_count=clarification_count,
            citation_verification_score=round(global_cvs, 4),
            hitl_validated=False,
        )
