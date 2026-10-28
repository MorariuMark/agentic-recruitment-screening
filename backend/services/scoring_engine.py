"""
backend/services/scoring_engine.py
Deterministic weighted scoring and verbatim citation grounding validation engine.
"""

from typing import Dict, List, Tuple
from uuid import UUID

from backend.schemas.cv import AnonymizedCandidate
from backend.services.evidence import source_quote
from backend.services.pre_ranking import context_terms, requirement_terms, evidence_term_matches, VOCABULARY
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
            return [], 0.0

        verified_citations: List[VerbatimCitation] = []
        valid_count = 0

        for cit in citations:
            original_span = source_quote(source_text, cit.quote)
            is_valid = original_span is not None
            if is_valid:
                valid_count += 1

            verified_citations.append(
                VerbatimCitation(
                    quote=original_span if is_valid else cit.quote,
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
        *,
        human_reviewed: bool = False,
    ) -> MatchEvaluationResult:
        """
        Computes deterministic weighted scores and applies the decision matrix
        calibrated by the requested strictness level (0 = lenient, 100 = ultra-strict).

        Human-reviewed matches retain their explicit scores/statuses, including
        confirmations obtained outside the CV. Citations are still checked and
        reported honestly; they do not overwrite the recruiter's confirmation.
        """
        strictness_clamped = max(0, min(100, int(strictness if strictness is not None else 50)))
        if not job.requirements:
            raise ValueError("Job description contains no requirements to evaluate.")

        req_lookup: Dict[str, JobRequirement] = {r.id: r for r in job.requirements}
        if len(req_lookup) != len(job.requirements):
            raise ValueError("Job requirement IDs must be unique.")
        if not any(req.weight > 0 for req in job.requirements):
            raise ValueError("Screening requires at least one active requirement.")

        # E3 Fix: Require complete, unique coverage of all active job requirements
        match_req_ids = set()
        for m in matches:
            if m.requirement_id in match_req_ids:
                raise ValueError(f"Duplicate evaluation match for requirement ID '{m.requirement_id}'.")
            if m.requirement_id not in req_lookup:
                raise ValueError(f"Unknown requirement ID '{m.requirement_id}' not found in job requirements.")
            match_req_ids.add(m.requirement_id)

        for req in job.requirements:
            if (req.weight or 0.0) > 0.0 and req.id not in match_req_ids:
                raise ValueError(f"Missing evaluation match for requirement '{req.title}' ({req.id}).")

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
            is_active = (weight or 0.0) > 0.0

            verified_cits, cit_score = self.verify_citations(match.citations, candidate.sanitized_text)
            all_citations.extend(verified_cits)

            calibrated_score = float(match.score)
            calibrated_status = match.status
            gap_analysis = match.gap_analysis
            clarification_question = getattr(match, "clarification_question", None)

            # E2 Fix: Citation verification constrains scores and invalidates unsupported positive claims
            has_unverified_cits = False
            if not human_reviewed and (match.citations or (is_active and calibrated_status in (MatchStatus.MET, MatchStatus.PARTIAL))):
                if cit_score == 0.0:
                    # Fabricated or ungrounded quotes: complete verification failure
                    has_unverified_cits = True
                    if calibrated_status in (MatchStatus.MET, MatchStatus.PARTIAL):
                        calibrated_status = MatchStatus.CLARIFICATION_NEEDED
                        calibrated_score = min(calibrated_score, 0.50)
                        cv_warning = "Citation verification failed: cited quote(s) not found verbatim in CV."
                        gap_analysis = f"{gap_analysis}; {cv_warning}" if gap_analysis else cv_warning
                        if not clarification_question:
                            req_title = req.title if req else match.requirement_id
                            clarification_question = f"Could you provide verified details for your experience with {req_title}?"
                elif cit_score < 1.0:
                    # Partial citation verification: constrain score proportionally
                    has_unverified_cits = True
                    calibrated_score = min(calibrated_score, round(0.50 + 0.50 * cit_score, 4))
                    if cit_score < 0.50 and calibrated_status == MatchStatus.MET:
                        calibrated_status = MatchStatus.PARTIAL

            # Verbatim accuracy alone does not prove the required application context.
            if not human_reviewed and req and calibrated_status in (MatchStatus.MET, MatchStatus.PARTIAL):
                contexts = context_terms(req.title, req.description)
                tools = [term for term in requirement_terms(req.title, req.description) if term in VOCABULARY]
                if contexts and tools:
                    quotes = [cit.quote for cit in verified_cits if cit.verified]
                    missing = [term for term in contexts if not any(evidence_term_matches(quote, term) for quote in quotes)]
                    linked = any(all(evidence_term_matches(quote, term) for term in [*tools, *contexts]) for quote in quotes)
                    if missing or not linked:
                        calibrated_status = MatchStatus.PARTIAL
                        calibrated_score = min(calibrated_score, 0.55 if missing else 0.79)
                        gap_analysis = f"Unverified required context: {', '.join(missing)}." if missing else "Tool usage is not explicitly linked to the required application context in the citations."
                        clarification_question = f"Can you provide a concrete example demonstrating {req.description}?"

            updated_matches.append(
                RequirementMatch(
                    requirement_id=match.requirement_id,
                    title=getattr(match, "title", None) or (req.title if req else None),
                    jd_summary=getattr(match, "jd_summary", None) or (req.title if req else None),
                    jd_citation=getattr(match, "jd_citation", None) or (req.description if req else None),
                    category=category,
                    status=calibrated_status,
                    score=round(min(1.0, max(0.0, calibrated_score)), 4),
                    confidence=match.confidence,
                    reasoning=match.reasoning,
                    citations=verified_cits,
                    gap_analysis=gap_analysis,
                    is_objective=getattr(match, "is_objective", True),
                    clarification_question=clarification_question,
                    transferable_skill=getattr(match, "transferable_skill", None),
                    benefit_of_doubt=getattr(match, "benefit_of_doubt", False),
                )
            )

            # E7 Fix: Only active criteria (weight > 0.0) trigger clarification counts or gaps
            if is_active and calibrated_status == MatchStatus.CLARIFICATION_NEEDED:
                clarification_count += 1

            if category == RequirementCategory.MUST_HAVE:
                must_have_total_weight += weight
                must_have_weighted_score += calibrated_score * weight
                # Non-met and partial must-have requirements count as gaps only if active;
                # under very lenient strictness (<= 25), a high-scoring PARTIAL (>= 0.75) does not count as a hard gap.
                if is_active:
                    if calibrated_status == MatchStatus.NOT_MET:
                        must_have_gaps_count += 1
                    elif calibrated_status == MatchStatus.PARTIAL:
                        if not (strictness_clamped <= 25 and calibrated_score >= 0.75):
                            must_have_gaps_count += 1
            else:
                nice_to_have_total_weight += weight
                nice_to_have_weighted_score += calibrated_score * weight

        # E3 Fix: Normalize category weights around categories actually present so absent preferred criteria do not provide an automatic bonus
        if must_have_total_weight > 0 and nice_to_have_total_weight > 0:
            must_have_score = (must_have_weighted_score / must_have_total_weight) * 100.0
            nice_to_have_score = (nice_to_have_weighted_score / nice_to_have_total_weight) * 100.0
            overall_score = round(0.75 * must_have_score + 0.25 * nice_to_have_score, 2)
        elif must_have_total_weight > 0:
            must_have_score = (must_have_weighted_score / must_have_total_weight) * 100.0
            nice_to_have_score = 0.0
            overall_score = round(must_have_score, 2)
        elif nice_to_have_total_weight > 0:
            must_have_score = 0.0
            nice_to_have_score = (nice_to_have_weighted_score / nice_to_have_total_weight) * 100.0
            overall_score = round(nice_to_have_score, 2)
        else:
            must_have_score = 0.0
            nice_to_have_score = 0.0
            overall_score = 0.0

        must_have_score = round(must_have_score, 2)
        nice_to_have_score = round(nice_to_have_score, 2)

        # Count hard objective NOT_MET must-have gaps (excluding transferable skills or benefit-of-the-doubt)
        # E7 Fix: Only active criteria (weight > 0) count as hard rejections
        hard_not_met_count = sum(
            1
            for m in updated_matches
            if req_lookup.get(m.requirement_id)
            and req_lookup[m.requirement_id].category == RequirementCategory.MUST_HAVE
            and (req_lookup[m.requirement_id].weight or 0.0) > 0.0
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

        if has_multiple_hard_rejections or overall_score < 50.0 or (must_have_gaps_count >= 1 and is_failing_score) or is_subpar_with_hard_gap:
            recommendation = Recommendation.REJECT
        elif overall_score >= 75.0 and not has_multiple_hard_rejections:
            recommendation = Recommendation.STRONG_MATCH
        elif overall_score >= strong_min_score and must_have_gaps_count == 0 and clarification_count == 0:
            recommendation = Recommendation.STRONG_MATCH
        else:
            recommendation = Recommendation.BORDERLINE

        total_valid = sum(1 for c in all_citations if c.verified)
        global_cvs = (total_valid / len(all_citations)) if all_citations else 0.0

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
            job_snapshot=job.model_copy(deep=True),
        )
