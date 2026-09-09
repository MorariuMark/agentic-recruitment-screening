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
                )
            )

            if category == RequirementCategory.MUST_HAVE:
                must_have_total_weight += weight
                must_have_weighted_score += match.score * weight
                if match.status != MatchStatus.MET:
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

        if must_have_gaps_count >= 2 or overall_score < 50.0:
            recommendation = Recommendation.REJECT
        elif must_have_gaps_count == 1 or (50.0 <= overall_score < 70.0):
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
            citation_verification_score=round(global_cvs, 4),
            hitl_validated=False,
        )
