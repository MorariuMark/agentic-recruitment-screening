"""
backend/agents/matching_agent.py
Semantic matching agent for evaluating candidate-JD alignment and gap proposals.
Retrieves candidate evidence chunks via ChromaDB and performs grounded LLM reasoning.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import re
import time
from typing import List, Optional
from uuid import UUID

from backend.agents.llm_factory import BaseLLMClient, get_llm_client
from backend.config import settings
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    RequirementMatch,
    VerbatimCitation,
)
from backend.schemas.token_usage import ActionAuditInfo
from backend.services.scoring_engine import ScoringEngine
from backend.services.skill_equivalence import SkillEquivalenceService
from backend.services.vector_store import VectorStoreService


HEDGE_PHRASES = [
    "does not explicitly detail",
    "does not explicitly mention",
    "does not explicitly state",
    "not explicitly mentioned",
    "not explicitly stated",
    "not clearly stated",
    "not explicitly specified",
    "unclear if",
    "unclear whether",
    "cannot confirm",
    "cannot be confirmed",
    "cannot be verified",
    "insufficient evidence",
    "limited information",
    "difficult to ascertain",
    "no direct mention",
]


INTERPRETIVE_KEYWORDS = [
    # Shifts & Schedule
    "night shift", "night shifts", "shift work", "rotating shift", "rotating shifts",
    "on-call", "on call", "weekend", "weekends", "overtime", "flexible hours",
    "schedule flexibility", "odd hours", "work schedule", "shifts",
    # Logistics, Travel, Relocation
    "willingness to travel", "travel willingness", "relocation", "relocate",
    "willing to relocate", "business trips", "travel requirement",
    # Soft skills, behavioral traits & subjective dispositions
    "attention to detail", "attention to details", "detail-oriented", "detail oriented",
    "eagerness to learn", "eager to learn", "willingness to learn", "willing to learn",
    "learning and growth", "fast-paced environment", "fast paced environment", "continuous learning",
    "growth mindset", "passion", "passionate", "self-motivated", "self motivated", "motivation",
    "team player", "interpersonal skills", "adaptability", "adaptable", "stress tolerance",
    "work under pressure", "positive attitude", "enthusiastic", "enthusiasm", "initiative",
    "proactive", "proactiveness", "work ethic", "problem-solving mindset"
]


def is_interpretive_requirement(requirement: JobRequirement) -> bool:
    """
    Determines whether a requirement is interpretive, subjective, or logistical
    (cannot be objectively disqualified from standard CV text alone).
    """
    cat_str = str(getattr(requirement, "category", "")).lower()
    if "soft" in cat_str:
        return True
    text = f"{requirement.title} {requirement.description}".lower()
    return any(kw in text for kw in INTERPRETIVE_KEYWORDS)


def generate_clarification_question(requirement: JobRequirement) -> str:
    """
    Synthesizes a concrete Yes/No screening question for application forms or recruiter calls.
    """
    text = f"{requirement.title} {requirement.description}".lower()
    if any(k in text for k in ["night shift", "night shifts", "shift", "shifts"]):
        return "Are you available and willing to work rotating or night shifts as required by this position? [Yes / No]"
    if any(k in text for k in ["relocat", "relocation"]):
        return "Are you willing and able to relocate for this position if required? [Yes / No]"
    if any(k in text for k in ["travel"]):
        return "Are you comfortable and willing to travel for business as required by this role? [Yes / No]"
    if any(k in text for k in ["attention to detail", "detail-oriented"]):
        return "Can you confirm your ability to uphold strict attention to detail in procedural execution and documentation? [Yes / No]"
    if any(k in text for k in ["eager", "learn", "growth", "continuous learning"]):
        return "Are you committed to continuous learning and eager to develop new technical skills in a fast-paced environment? [Yes / No]"
    if any(k in text for k in ["pressure", "stress"]):
        return "Are you comfortable working in a fast-paced environment under deadline pressure? [Yes / No]"
    if any(k in text for k in ["team player", "interpersonal", "collaborat"]):
        return "Do you consider yourself a collaborative team player with strong interpersonal communication skills? [Yes / No]"

    return f"Can you confirm your readiness and availability regarding '{requirement.title}'? [Yes / No]"


MATCHING_SYSTEM_PROMPT = """You are an objective, evidence-driven HR Technical Evaluator.
Determine if candidate evidence chunks satisfy the specified Job Requirement.

Evaluation Principles:
- "met": Positive evidence meeting requirement. Assign score: 1.0 (100%) whenever the requirement is clearly satisfied by the candidate's evidence. Only assign 0.85-0.95 if the requirement is met with a minor caveat. Extract exact verbatim citation quotes.
- "partial": Related or adjacent evidence (score: 0.4-0.79). Extract exact verbatim citation quotes.
- "clarification_needed": Interpretive, logistical, or soft-skill requirement (e.g. shifts, travel, relocation, willingness to learn, teamwork) where the CV is silent. DO NOT mark as not_met; set score: 0.5, is_objective: false, and provide a clear Yes/No screening question in clarification_question.
- "not_met": Objective credential or skill (degree, years of experience, programming language, tool) is genuinely absent (score: 0.0-0.39, citations: []).

Grounding Rule:
- All citation quotes MUST be exact, verbatim substrings from candidate chunks. Do not paraphrase."""


def _build_strictness_instruction(strictness: int) -> str:
    """Returns prompt calibration guidance based on user-configured strictness (0-100)."""
    s = max(0, min(100, int(strictness)))
    if s <= 30:
        return (
            f"Evaluation Strictness: {s}/100 (LENIENT / INCLUSIVE). "
            "Be generous and potential-focused: give full 1.0 (100%) credit whenever the candidate has direct or closely equivalent experience. "
            "Treat adjacent tools, related coursework, or transferable project experience as strong positive evidence."
        )
    elif s <= 65:
        return (
            f"Evaluation Strictness: {s}/100 (BALANCED / STANDARD). "
            "Award a full 1.0 (100%) score whenever the candidate satisfies the requirement without gaps. "
            "Do not artificially cap met requirements at 0.90."
        )
    elif s <= 85:
        return (
            f"Evaluation Strictness: {s}/100 (STRICT). "
            "Require clear verbatim evidence in the CV chunks. Award 1.0 (100%) when evidence directly confirms the requirement, "
            "and use 'partial' (0.45-0.75) when only adjacent or partial proof is present."
        )
    else:
        return (
            f"Evaluation Strictness: {s}/100 (ULTRA-STRICT / AUDIT-GRADE). "
            "Enforce rigorous verification of exact skills, domain context, and minimum years of experience. "
            "Penalize unverified claims or partial tenure conservatively."
        )


class MatchingAgent:
    """Agent orchestrating retrieval, grounded LLM evaluation, and deterministic scoring."""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        vector_store: Optional[VectorStoreService] = None,
        scoring_engine: Optional[ScoringEngine] = None,
    ) -> None:
        self.llm_client = llm_client or get_llm_client()
        self.vector_store = vector_store or VectorStoreService()
        self.scoring_engine = scoring_engine or ScoringEngine()

    def evaluate_requirement(
        self,
        candidate_id: UUID,
        requirement: JobRequirement,
        n_chunks: int = 3,
        candidate: Optional[AnonymizedCandidate] = None,
        strictness: int = 50,
    ) -> RequirementMatch:
        """
        Retrieves top relevant candidate chunks for a single requirement and prompts LLM for grounded match.
        """
        strictness_clamped = max(0, min(100, int(strictness if strictness is not None else 50)))

        # 1. Retrieve the most relevant candidate chunks from ChromaDB for this requirement
        query_text = f"{requirement.title}: {requirement.description}".strip()
        retrieved_chunks = self.vector_store.query_candidate_chunks(
            candidate_id=candidate_id,
            query_text=query_text,
            n_results=n_chunks,
        )

        # Ensure language chunks are included if requirement is genuinely about language/communication
        req_lower = f"{requirement.title} {requirement.description}".lower()
        title_lower = requirement.title.lower()
        is_loc_or_logistics = any(kw in title_lower for kw in [
            "location", "on-site", "presence", "relocat", "residen", "work permit", "visa", "office", "driving"
        ])
        is_language_req = not is_loc_or_logistics and (
            any(kw in req_lower for kw in [
                "language", "languages", "sprache", "fluent", "fluency", "fließend", "proficien",
                "mother tongue", "native speaker", "b1", "b2", "c1", "c2", "cefr", "multilingual", "bilingual"
            ]) or any(
                re.search(rf"\b{lang}\b", req_lower)
                for lang in ["english", "german", "french", "spanish", "italian", "romanian", "dutch", "deutsch", "englisch"]
            )
        )
        is_cert_req = any(kw in req_lower for kw in [
            "certification", "certifications", "license", "licence", "certified", "driver", "driving"
        ])

        chunk_types = {c.get("metadata", {}).get("type") for c in retrieved_chunks}
        if is_language_req and "languages" not in chunk_types:
            lang_chunks = self.vector_store.query_candidate_chunks(
                candidate_id=candidate_id,
                query_text="Candidate Languages & Communication English German Romanian linguistic competency",
                n_results=1,
            )
            for lc in lang_chunks:
                if lc.get("metadata", {}).get("type") == "languages":
                    retrieved_chunks.append(lc)
                    break

        if is_cert_req and "certifications" not in chunk_types:
            cert_chunks = self.vector_store.query_candidate_chunks(
                candidate_id=candidate_id,
                query_text="Certifications & Licences Driving Licence",
                n_results=1,
            )
            for cc in cert_chunks:
                if cc.get("metadata", {}).get("type") == "certifications":
                    retrieved_chunks.append(cc)
                    break

        # 2. Format the retrieved evidence chunks with provenance metadata
        evidence_lines: List[str] = []
        for idx, chunk in enumerate(retrieved_chunks, start=1):
            meta = chunk.get("metadata", {})
            source = meta.get("job_title", "")
            if meta.get("company_name"):
                source += f" at {meta.get('company_name')}"
            if not source:
                source = meta.get("type", "Candidate Profile")
            evidence_lines.append(f"[Evidence {idx}] (Source: {source})\n\"{chunk.get('text', '')}\"")

        evidence_text = "\n\n".join(evidence_lines) if evidence_lines else "No directly matching evidence found in profile."

        # 3. Formulate the evaluation prompt
        is_interpretive = is_interpretive_requirement(requirement)
        type_hint = "INTERPRETIVE / LOGISTICAL / SOFT-SKILL" if is_interpretive else "OBJECTIVE QUALIFICATION"
        strictness_guidance = _build_strictness_instruction(strictness_clamped)

        cat_val = requirement.category.value if hasattr(requirement.category, "value") else str(requirement.category)
        prompt = (
            f"Job Requirement to Evaluate:\n"
            f"- ID: {requirement.id}\n"
            f"- Title: {requirement.title}\n"
            f"- Type: {type_hint}\n"
            f"- Category: {cat_val}\n"
            f"- Description: {requirement.description}\n"
            f"- Minimum Years Required: {requirement.minimum_years_experience or 'N/A'}\n\n"
            f"{strictness_guidance}\n\n"
            f"Candidate Profile Evidence Chunks:\n{evidence_text}\n\n"
            f"Evaluate whether the candidate meets this requirement. Respond ONLY with valid JSON conforming to the RequirementMatch schema.\n"
            f"Set requirement_id to '{requirement.id}'.\n"
            f"IMPORTANT: If the requirement is clearly satisfied, set status to 'met' and score to 1.0 (100%).\n"
            f"If Type is INTERPRETIVE / LOGISTICAL / SOFT-SKILL and the candidate CV is silent on it, set status to 'clarification_needed', is_objective to false, score to 0.5, and provide an actionable Yes/No question in clarification_question."
        )

        # 4. Invoke LLM structured generation
        match_result = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=RequirementMatch,
            system_prompt=MATCHING_SYSTEM_PROMPT,
            temperature=0.0,
        )
        match_result.requirement_id = requirement.id
        match_result.title = requirement.title
        match_result.jd_summary = requirement.title
        match_result.jd_citation = requirement.description

        # 5. Deterministic Guardrail: Enforce separation between objective vs interpretive criteria
        if is_interpretive:
            match_result.is_objective = False
            # If the model marked an interpretive / logistical requirement as NOT MET
            # because the CV is silent on it, override to CLARIFICATION_NEEDED.
            if match_result.status == MatchStatus.NOT_MET:
                match_result.status = MatchStatus.CLARIFICATION_NEEDED
                match_result.score = 0.5
                q = match_result.clarification_question or generate_clarification_question(requirement)
                match_result.clarification_question = q
                match_result.gap_analysis = f"Interpretive / logistical detail requiring confirmation on application form or screening call: {q}"
                match_result.reasoning = (
                    f"{match_result.reasoning} (Interpretive/logistical criterion: flagged for applicant/recruiter "
                    f"Yes/No clarification rather than objective disqualification.)"
                )
            elif not match_result.clarification_question:
                match_result.clarification_question = generate_clarification_question(requirement)
        else:
            match_result.is_objective = True

            # 6. Edge-Case Guardrails for Objective Requirements:

            # A. Hierarchical Language Scale (e.g. C1 / Fluent satisfies or exceeds required B2)
            if candidate and candidate.anonymized_languages and is_language_req:
                lang_eval = SkillEquivalenceService.evaluate_language_hierarchy(
                    languages=candidate.anonymized_languages,
                    requirement_title=requirement.title,
                    requirement_description=requirement.description,
                )
                if lang_eval is not None:
                    is_satisfied, cand_level, req_level = lang_eval
                    if is_satisfied and match_result.status != MatchStatus.MET:
                        reason_lower = match_result.reasoning.lower()
                        # Guard: Never override if model documented that candidate lacks the language or authorization
                        rejection_markers = [
                            "no evidence", "does not speak", "does not possess", "lacks", "missing",
                            "no documented", "no indication", "cannot confirm", "unmet", "not proficient",
                            "not fluent", "does not meet", "fails to meet", "unauthorized", "authorization",
                            "location", "on-site", "permit", "visa", "no mention"
                        ]
                        if not any(rm in reason_lower for rm in rejection_markers):
                            match_result.status = MatchStatus.MET
                            match_result.score = 1.0
                            match_result.reasoning = (
                                f"{match_result.reasoning} [Language Hierarchy: Candidate demonstrates {cand_level}, "
                                f"which satisfies or exceeds required {req_level}.]"
                            )
                            match_result.gap_analysis = None

            # B. Hierarchical Academic Degree Scale (e.g. MSc / PhD satisfies required Bachelor in matching field)
            if candidate and candidate.anonymized_education:
                deg_eval = SkillEquivalenceService.evaluate_degree_hierarchy(
                    education_list=candidate.anonymized_education,
                    requirement_title=requirement.title,
                    requirement_description=requirement.description,
                )
                if deg_eval is not None:
                    is_satisfied, cand_degree, req_degree = deg_eval
                    if is_satisfied and match_result.status != MatchStatus.MET:
                        # Guard: Do not override if LLM reasoning explicitly documented a field, qualification, or enrollment mismatch
                        reasoning_lower = match_result.reasoning.lower()
                        mismatch_markers = [
                            "none of these credentials correspond",
                            "does not correspond",
                            "different field",
                            "unrelated field",
                            "unrelated discipline",
                            "wrong field",
                            "not in",
                            "no degree in",
                            "does not meet this objective qualification",
                            "does not meet",
                            "fails to meet",
                            "does not match",
                            "not match",
                            "doesn't match",
                            "fails to match",
                            "no match",
                            "mismatch",
                            "study field",
                            "field of study",
                            "discipline",
                            "not enrolled",
                            "currently enrolled",
                            "lacks",
                            "missing",
                            "no evidence",
                            "unmet",
                        ]
                        if not any(m in reasoning_lower for m in mismatch_markers):
                            match_result.status = MatchStatus.MET
                            match_result.score = 1.0
                            match_result.reasoning = (
                                f"{match_result.reasoning} [Degree Hierarchy: Candidate holds {cand_degree}, "
                                f"which satisfies or exceeds required {req_degree}.]"
                            )
                            match_result.gap_analysis = None

            # C. Cumulative Tenure Aggregation across Work History
            if candidate and candidate.anonymized_work_experiences and requirement.minimum_years_experience:
                tenure_years = SkillEquivalenceService.calculate_tenure_for_skill(
                    experiences=candidate.anonymized_work_experiences,
                    skill_or_tool=requirement.title,
                )
                if tenure_years >= requirement.minimum_years_experience:
                    reasoning_lower = match_result.reasoning.lower()
                    if match_result.status in (MatchStatus.NOT_MET, MatchStatus.PARTIAL):
                        rejection_markers = [
                            "no experience", "lacks experience", "does not have", "no mention",
                            "no evidence", "not worked", "never", "unmet"
                        ]
                        if not any(rm in reasoning_lower for rm in rejection_markers):
                            if any(kw in reasoning_lower for kw in ["year", "tenure", "duration", "explicit", "unstated", "length"]):
                                if match_result.status == MatchStatus.PARTIAL or len(match_result.citations) > 0:
                                    match_result.status = MatchStatus.MET
                                    match_result.score = 1.0
                                    match_result.reasoning += (
                                        f" [Tenure Aggregation: Calculated {tenure_years:.1f} cumulative calendar years across work history, "
                                        f"satisfying the {requirement.minimum_years_experience} year(s) requirement.]"
                                    )
                                    match_result.gap_analysis = None

            # D. Transferable Skills & Cross-Technology Equivalence
            if candidate and match_result.status == MatchStatus.NOT_MET:
                transferable = SkillEquivalenceService.find_transferable_skill(
                    candidate_skills=candidate.anonymized_skills,
                    candidate_experiences=candidate.anonymized_work_experiences,
                    requirement_title=requirement.title,
                    requirement_description=requirement.description,
                )
                if transferable:
                    cand_tech, req_tech, category = transferable
                    match_result.status = MatchStatus.PARTIAL
                    match_result.score = 0.70
                    match_result.transferable_skill = f"{cand_tech} → {req_tech}"
                    match_result.gap_analysis = (
                        f"Transferable competency: Candidate has proven experience with {cand_tech} ({category}), "
                        f"which provides strong transferable baseline for {req_tech}."
                    )
                    match_result.reasoning += (
                        f" [Transferable Competency: Candidate demonstrated proficiency in {cand_tech}, "
                        f"an equivalent technology in {category} directly transferable to {req_tech}.]"
                    )

            # E. Benefit of the Doubt Guardrail (Ambiguous phrasing or low-confidence verdicts)
            if match_result.status == MatchStatus.NOT_MET and not match_result.transferable_skill:
                reasoning_lower = match_result.reasoning.lower()
                has_hedge_phrase = any(phrase in reasoning_lower for phrase in HEDGE_PHRASES)
                conf_threshold = 0.75 + max(0.0, (50 - strictness_clamped) * 0.004)
                is_low_confidence = match_result.confidence < conf_threshold
                if is_low_confidence or has_hedge_phrase:
                    match_result.status = MatchStatus.PARTIAL
                    match_result.score = 0.50
                    match_result.benefit_of_doubt = True
                    match_result.reasoning += (
                        " [Benefit of the Doubt: Evaluated as partial due to ambiguous or unconfirmed CV phrasing; "
                        "flagged for recruiter interview probe.]"
                    )
                    if not match_result.gap_analysis:
                        match_result.gap_analysis = "Unconfirmed in CV phrasing. Verify hands-on depth during interview."
                    else:
                        match_result.gap_analysis += " (Flagged for recruiter interview probe.)"

            # F. Strictness Calibration & Perfect-Match 100% Normalization
            if match_result.status == MatchStatus.MET:
                has_explicit_gap = bool(match_result.gap_analysis and match_result.gap_analysis.strip())
                if strictness_clamped <= 80 and not has_explicit_gap and match_result.score >= 0.80:
                    match_result.score = 1.0
                elif strictness_clamped <= 90 and not has_explicit_gap and match_result.score >= 0.88:
                    match_result.score = 1.0
            elif match_result.status == MatchStatus.PARTIAL:
                if strictness_clamped < 50:
                    # Boost partial scores under lenient settings (up to +0.20 at strictness=0)
                    boost = ((50 - strictness_clamped) / 50.0) * 0.20
                    match_result.score = round(min(0.95, match_result.score + boost), 2)
                    if strictness_clamped <= 20 and match_result.score >= 0.85 and len(match_result.citations) > 0:
                        match_result.status = MatchStatus.MET
                        match_result.score = 1.0
                        match_result.gap_analysis = None
                elif strictness_clamped > 70:
                    # Apply stricter penalty under high strictness (up to -0.15 at strictness=100)
                    penalty = ((strictness_clamped - 70) / 30.0) * 0.15
                    match_result.score = round(max(0.20, match_result.score - penalty), 2)

        return match_result

    def match_candidate(
        self,
        candidate: AnonymizedCandidate,
        job_description: JobDescription,
        n_chunks_per_req: int = 3,
        strictness: int = 50,
    ) -> MatchEvaluationResult:
        """
        Full matching workflow:
        1. Indexes candidate chunks into ChromaDB (if not already indexed).
        2. Evaluates every requirement in the Job Description.
        3. Runs deterministic ScoringEngine verification and weighted calculation.
        """
        from backend.services.progress_tracker import progress_tracker
        from backend.services.token_tracker import token_tracker

        strictness_clamped = max(0, min(100, int(strictness if strictness is not None else 50)))
        req_count = len(job_description.requirements or [])
        total_steps = max(2, req_count + 2)

        progress_tracker.start_task(
            task_key="candidate_evaluation",
            label=f"Evaluating Candidate vs. {job_description.title}",
            phase=f"Step 1/{total_steps}: Indexing candidate semantic chunks in ChromaDB...",
            total_steps=total_steps,
        )

        # 1. Ensure candidate is indexed in vector store
        self.vector_store.index_candidate(candidate)
        progress_tracker.increment_step(
            task_key="candidate_evaluation",
            phase=f"Evaluating {req_count} job criteria with AI (Strictness: {strictness_clamped}%)...",
        )

        token_tracker.start_action_session("candidate_evaluation")

        # 2. Evaluate all requirements in the JD concurrently
        matches: List[RequirementMatch] = []
        if job_description.requirements:
            completed_counter = [0]

            def _evaluate_single(req: JobRequirement) -> RequirementMatch:
                try:
                    if hasattr(self.llm_client, "set_action_context"):
                        self.llm_client.set_action_context("candidate_evaluation")
                    res = self.evaluate_requirement(
                        candidate_id=candidate.candidate_id,
                        requirement=req,
                        n_chunks=n_chunks_per_req,
                        candidate=candidate,
                        strictness=strictness_clamped,
                    )
                    completed_counter[0] += 1
                    progress_tracker.increment_step(
                        task_key="candidate_evaluation",
                        phase=f"Evaluated criterion {completed_counter[0]}/{req_count}: {req.title}",
                        item_completed=req.title,
                    )
                    return res
                except Exception as e:
                    logging.warning(f"Error evaluating requirement {req.id}: {e}")
                    completed_counter[0] += 1
                    progress_tracker.increment_step(
                        task_key="candidate_evaluation",
                        phase=f"Completed criterion {completed_counter[0]}/{req_count}: {req.title}",
                    )
                    return RequirementMatch(
                        requirement_id=req.id,
                        title=req.title,
                        jd_summary=req.title,
                        jd_citation=req.description,
                        status=MatchStatus.NOT_MET,
                        score=0.0,
                        reasoning=f"Automated evaluation encountered a provider timeout or error: {str(e)}",
                        citations=[],
                    )

            max_workers = min(len(job_description.requirements), 4)
            provider_type = getattr(self.llm_client, "__class__", "").__name__.lower()
            is_rate_sensitive = "groq" in provider_type

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                if is_rate_sensitive:
                    futures = []
                    for idx, req in enumerate(job_description.requirements):
                        if 0 < idx < max_workers:
                            time.sleep(0.15)  # 150ms gentle stagger to prevent instantaneous TPM rate-limit burst
                        futures.append(executor.submit(_evaluate_single, req))
                    matches = [f.result() for f in futures]
                else:
                    matches = list(executor.map(_evaluate_single, job_description.requirements))

        progress_tracker.update_task(
            task_key="candidate_evaluation",
            phase="Verifying verbatim CV citations & computing weighted scores...",
        )

        # 3. Compute deterministic score, citation verification, and recommendation
        evaluation_result = self.scoring_engine.compute_evaluation(
            candidate=candidate,
            job=job_description,
            matches=matches,
            strictness=strictness_clamped,
        )

        # 4. Attach aggregated token usage & latency metrics
        action_usage = token_tracker.end_action_session("candidate_evaluation")
        if action_usage and action_usage.total_tokens > 0:
            evaluation_result.token_usage = action_usage
        else:
            evaluation_result.token_usage = token_tracker.get_last_usage()

        model_name = (
            getattr(self.llm_client, "get_model_name", lambda: None)()
            or getattr(self.llm_client, "model", None)
            or getattr(settings, "llm_model", "unknown")
        )
        provider = getattr(settings, "llm_provider", None)
        tokens_dict = {
            "prompt_tokens": getattr(evaluation_result.token_usage, "prompt_tokens", 0) if evaluation_result.token_usage else 0,
            "completion_tokens": getattr(evaluation_result.token_usage, "completion_tokens", 0) if evaluation_result.token_usage else 0,
            "total_tokens": getattr(evaluation_result.token_usage, "total_tokens", 0) if evaluation_result.token_usage else 0,
        }
        latency_ms = getattr(evaluation_result.token_usage, "latency_ms", 0.0) if evaluation_result.token_usage else 0.0
        doc_len = len(job_description.raw_text or "")
        evaluation_result.audit_metadata = ActionAuditInfo(
            model_name=str(model_name),
            provider=provider,
            tokens_consumed=tokens_dict,
            duration_ms=latency_ms,
            duration_seconds=round(latency_ms / 1000.0, 3),
            initial_document_text_length=doc_len,
            initial_document_word_count=len((job_description.raw_text or "").split()),
            action_timestamp=datetime.now(timezone.utc).isoformat(),
        )

        progress_tracker.finish_task(
            task_key="candidate_evaluation",
            phase=f"Evaluation complete: {evaluation_result.overall_score:.0f}% ({evaluation_result.recommendation.value})",
        )

        return evaluation_result


