"""
backend/agents/matching_agent.py
Semantic matching agent for evaluating candidate-JD alignment and gap proposals.
Retrieves candidate evidence chunks via ChromaDB and performs grounded LLM reasoning.
"""

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import List, Optional
from uuid import UUID

from backend.agents.llm_factory import BaseLLMClient, get_llm_client
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    RequirementMatch,
    VerbatimCitation,
)
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
Your responsibility is to determine if a candidate's background satisfies a specific Job Requirement.

CRITICAL DISTINCTION: OBJECTIVE QUALIFICATIONS vs. INTERPRETIVE / SUBJECTIVE / LOGISTICAL CRITERIA

1. Objective Criteria:
   - Verifiable skills and credentials: years of experience, specific programming languages/frameworks, degrees, diplomas, certifications/licenses, spoken languages.
   - If evidence is genuinely absent for an objective criterion, assign status: "not_met" (score: 0.0 - 0.39), set is_objective: true, clarification_question: null.

2. Interpretive / Subjective / Logistical Criteria:
   - Items rarely stated as verifiable factual achievements in a CV, including:
     * Shift availability (night shifts, rotating shifts, weekend work, on-call duty)
     * Logistics & willingness (willingness to travel, relocation readiness, schedule flexibility)
     * Soft skills & behavioral traits (attention to detail, eagerness to learn, growth mindset, work under pressure, team player)
   - RULES FOR INTERPRETIVE / SUBJECTIVE ITEMS:
     * If the CV has explicit positive evidence (e.g. prior experience working night shifts or projects demonstrating rapid learning), assign "met" (score 0.8-1.0) or "partial" (score 0.5-0.79).
     * If the CV is SILENT or does not explicitly state it, DO NOT disqualify the candidate with "not_met"!
     * Instead, assign status: "clarification_needed", set is_objective: false, score: 0.5, and provide a clear Yes/No screening question in clarification_question (e.g., "Are you available and willing to work rotating night shifts? [Yes / No]").
     * Candidate must NOT be penalized with an objective rejection for silent logistical or soft-skill criteria.

Evaluation Status Principles:
- "met": Demonstrated positive evidence meeting the requirement (Score: 0.8 - 1.0).
- "partial": Adjacent, related, or partial evidence (Score: 0.4 - 0.79).
- "clarification_needed": Interpretive/logistical/soft-skill requirement where CV is silent. Requires applicant/recruiter Yes/No confirmation (Score: 0.5, confidence: 0.9 - 1.0).
- "not_met": Objective requirement (degree, years of experience, tech qualification, language) is genuinely absent or inadequate (Score: 0.0 - 0.39).

Verbatim Grounding (STRICT):
- Extract direct, exact verbatim substrings from candidate chunks for positive claims.
- For "clarification_needed" or "not_met", citations should be empty []."""


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
    ) -> RequirementMatch:
        """
        Retrieves top relevant candidate chunks for a single requirement and prompts LLM for grounded match.
        """
        # 1. Retrieve the most relevant candidate chunks from ChromaDB for this requirement
        query_text = f"{requirement.title}: {requirement.description}".strip()
        retrieved_chunks = self.vector_store.query_candidate_chunks(
            candidate_id=candidate_id,
            query_text=query_text,
            n_results=n_chunks,
        )

        # Ensure language chunks are included if requirement is about language/communication
        req_lower = f"{requirement.title} {requirement.description}".lower()
        is_language_req = any(kw in req_lower for kw in [
            "language", "languages", "english", "german", "french", "spanish", "italian", "romanian",
            "communication", "multilingual", "bilingual", "conversational", "cefr", "spoken", "written"
        ])
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

        cat_val = requirement.category.value if hasattr(requirement.category, "value") else str(requirement.category)
        prompt = (
            f"Job Requirement to Evaluate:\n"
            f"- ID: {requirement.id}\n"
            f"- Title: {requirement.title}\n"
            f"- Type: {type_hint}\n"
            f"- Category: {cat_val}\n"
            f"- Description: {requirement.description}\n"
            f"- Minimum Years Required: {requirement.minimum_years_experience or 'N/A'}\n\n"
            f"Candidate Profile Evidence Chunks:\n{evidence_text}\n\n"
            f"Evaluate whether the candidate meets this requirement. Respond ONLY with valid JSON conforming to the RequirementMatch schema.\n"
            f"Set requirement_id to '{requirement.id}'.\n"
            f"IMPORTANT: If Type is INTERPRETIVE / LOGISTICAL / SOFT-SKILL and the candidate CV is silent on it, set status to 'clarification_needed', is_objective to false, score to 0.5, and provide an actionable Yes/No question in clarification_question."
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
            if candidate and candidate.anonymized_languages:
                lang_eval = SkillEquivalenceService.evaluate_language_hierarchy(
                    languages=candidate.anonymized_languages,
                    requirement_title=requirement.title,
                    requirement_description=requirement.description,
                )
                if lang_eval is not None:
                    is_satisfied, cand_level, req_level = lang_eval
                    if is_satisfied and match_result.status != MatchStatus.MET:
                        match_result.status = MatchStatus.MET
                        match_result.score = 1.0
                        match_result.reasoning = (
                            f"{match_result.reasoning} [Language Hierarchy: Candidate demonstrates {cand_level}, "
                            f"which satisfies or exceeds required {req_level}.]"
                        )
                        match_result.gap_analysis = None

            # B. Hierarchical Academic Degree Scale (e.g. MSc / PhD satisfies required Bachelor)
            if candidate and candidate.anonymized_education:
                deg_eval = SkillEquivalenceService.evaluate_degree_hierarchy(
                    education_list=candidate.anonymized_education,
                    requirement_title=requirement.title,
                    requirement_description=requirement.description,
                )
                if deg_eval is not None:
                    is_satisfied, cand_degree, req_degree = deg_eval
                    if is_satisfied and match_result.status != MatchStatus.MET:
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
                        if any(kw in reasoning_lower for kw in ["year", "tenure", "duration", "explicit", "unstated", "length", "experience"]):
                            if match_result.status == MatchStatus.PARTIAL or len(match_result.citations) > 0 or tenure_years > 0:
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
                is_low_confidence = match_result.confidence < 0.75
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

        return match_result

    def match_candidate(
        self,
        candidate: AnonymizedCandidate,
        job_description: JobDescription,
        n_chunks_per_req: int = 3,
    ) -> MatchEvaluationResult:
        """
        Full matching workflow:
        1. Indexes candidate chunks into ChromaDB (if not already indexed).
        2. Evaluates every requirement in the Job Description.
        3. Runs deterministic ScoringEngine verification and weighted calculation.
        """
        # 1. Ensure candidate is indexed in vector store
        self.vector_store.index_candidate(candidate)

        from backend.services.token_tracker import token_tracker
        token_tracker.start_action_session("candidate_evaluation")

        # 2. Evaluate all requirements in the JD concurrently
        matches: List[RequirementMatch] = []
        if job_description.requirements:
            def _evaluate_single(req: JobRequirement) -> RequirementMatch:
                try:
                    if hasattr(self.llm_client, "set_action_context"):
                        self.llm_client.set_action_context("candidate_evaluation")
                    return self.evaluate_requirement(
                        candidate_id=candidate.candidate_id,
                        requirement=req,
                        n_chunks=n_chunks_per_req,
                        candidate=candidate,
                    )
                except Exception as e:
                    logging.warning(f"Error evaluating requirement {req.id}: {e}")
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
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                matches = list(executor.map(_evaluate_single, job_description.requirements))

        # 3. Compute deterministic score, citation verification, and recommendation
        evaluation_result = self.scoring_engine.compute_evaluation(
            candidate=candidate,
            job=job_description,
            matches=matches,
        )

        # 4. Attach aggregated token usage & latency metrics
        action_usage = token_tracker.end_action_session("candidate_evaluation")
        if action_usage and action_usage.total_tokens > 0:
            evaluation_result.token_usage = action_usage
        else:
            evaluation_result.token_usage = token_tracker.get_last_usage()

        return evaluation_result

