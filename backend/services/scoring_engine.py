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

        source_str = source_text or ""
        normalized_source = " ".join(source_str.lower().split())

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
        matches: List[RequirementMatch],
        strictness: int = 50,
    ) -> MatchEvaluationResult:
        """
        Computes deterministic weighted scores and applies the decision matrix
        calibrated by the requested strictness level (0 = lenient, 100 = ultra-strict).
        """
        strictness_clamped = max(0, min(100, int(strictness if strictness is not None else 50)))
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

            calibrated_score = float(match.score)
            calibrated_status = match.status

            # Ensure a requirement marked MET without gaps receives full 100% (1.0) credit
            # unless strictness is set to ultra-strict (>85) with lower confidence.
            if calibrated_status == MatchStatus.MET:
                has_explicit_gap = bool(match.gap_analysis and match.gap_analysis.strip())
                if strictness_clamped <= 80 and not has_explicit_gap and calibrated_score >= 0.80:
                    calibrated_score = 1.0
                elif strictness_clamped <= 90 and not has_explicit_gap and calibrated_score >= 0.88:
                    calibrated_score = 1.0

            updated_matches.append(
                RequirementMatch(
                    requirement_id=match.requirement_id,
                    title=getattr(match, "title", None) or (req.title if req else None),
                    jd_summary=getattr(match, "jd_summary", None) or (req.title if req else None),
                    jd_citation=getattr(match, "jd_citation", None) or (req.description if req else None),
                    status=calibrated_status,
                    score=round(min(1.0, max(0.0, calibrated_score)), 4),
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

            if calibrated_status == MatchStatus.CLARIFICATION_NEEDED:
                clarification_count += 1

            if category == RequirementCategory.MUST_HAVE:
                must_have_total_weight += weight
                must_have_weighted_score += calibrated_score * weight
                # Non-met and partial must-have requirements count as gaps;
                # under very lenient strictness (<= 25), a high-scoring PARTIAL (>= 0.75) does not count as a hard gap.
                if calibrated_status == MatchStatus.NOT_MET:
                    must_have_gaps_count += 1
                elif calibrated_status == MatchStatus.PARTIAL:
                    if not (strictness_clamped <= 25 and calibrated_score >= 0.75):
                        must_have_gaps_count += 1
            else:
                nice_to_have_total_weight += weight
                nice_to_have_weighted_score += calibrated_score * weight

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

        # Strictness-calibrated thresholds:
        # At strictness=0 (Lenient): strong_min = 55%, reject_min = 35%, max_hard_gaps_before_reject = 3
        # At strictness=50 (Balanced): strong_min = 67.5%, reject_min = 47.5%, max_hard_gaps_before_reject = 2
        # At strictness=70 (Strict): strong_min = 72.5%, reject_min = 52.5%, max_hard_gaps_before_reject = 2
        # At strictness=100 (Ultra-Strict): strong_min = 80%, reject_min = 60%, max_hard_gaps_before_reject = 1
        strong_min_score = 55.0 + (strictness_clamped / 100.0) * 25.0
        reject_min_score = 35.0 + (strictness_clamped / 100.0) * 25.0
        hard_reject_gap_threshold = 3 if strictness_clamped <= 25 else (1 if strictness_clamped >= 90 else 2)

        has_multiple_hard_rejections = hard_not_met_count >= hard_reject_gap_threshold
        is_failing_score = overall_score < reject_min_score
        is_subpar_with_hard_gap = (
            must_have_gaps_count >= 2
            and overall_score < (reject_min_score + 5.0)
            and hard_not_met_count >= 1
        )

        if has_multiple_hard_rejections or (must_have_gaps_count >= 1 and is_failing_score) or is_subpar_with_hard_gap:
            recommendation = Recommendation.REJECT
        elif must_have_gaps_count >= 1 or clarification_count > 0 or (reject_min_score <= overall_score < strong_min_score):
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
            strictness=strictness_clamped,
        )
