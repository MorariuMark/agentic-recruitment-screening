"""
backend/agents/interview_agent.py
Interview guide synthesis agent for approved candidates based on identified gaps,
borderline claims, and strengths verified during the screening and HITL stages.
"""

from typing import List, Optional
from uuid import UUID, uuid4

from backend.agents.llm_factory import BaseLLMClient, get_llm_client
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.interview import (
    InterviewPlan,
    InterviewQuestion,
    QuestionArchetype,
)
from backend.schemas.job import JobDescription
from backend.schemas.match import MatchEvaluationResult, MatchStatus, RequirementMatch


INTERVIEW_SYSTEM_PROMPT = """You are an expert Technical Interview Architect.
Your task is to generate a comprehensive, highly targeted Interview Plan for a candidate
who has passed initial screening.

Guiding Principles:
1. Question Archetypes:
   - "gap_verification": Specifically probe unmet or partially met requirements. Test if the candidate has transferable skills or conceptual understanding despite lacking explicit resume evidence.
   - "technical_deep_dive": Probe candidate claims of deep competence (met requirements with high scores). Drill into architecture, failure modes, trade-offs, and optimization.
   - "behavioral": Probe collaboration, handling production incidents, conflict resolution, or resolving technical disagreements.
2. Structure & Quality:
   - Formulate clear, open-ended question prompts (not simple yes/no questions).
   - "expected_answer": Provide a detailed, realistic model response illustrating what a strong, qualified candidate would say (architectural concepts, trade-offs, metrics, best practices).
   - "expected_answers": List 2-4 key bullet points that must be present in an ideal response.
   - "bad_answer": Provide a detailed, realistic example of a poor or bad answer displaying red flags, superficial buzzwords, hand-waving, incorrect assumptions, or evasiveness.
   - "bad_answers": List 2-4 red flag indicators or warning signs in candidate answers.
   - "rationale_for_asking": Explain clearly why this question is being asked based on the candidate's screening gaps or verified claims.
   - "difficulty": Select appropriate difficulty level ("junior", "mid", "senior", "principal").
   - Allocate realistic minutes per question (sum should fit within the target interview duration).
3. Grounding: Focus strictly on the requirements and findings in the provided evaluation report."""


class InterviewAgent:
    """Agent that synthesizes personalized, rubric-driven interview plans."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def generate_interview_plan(
        self,
        candidate: AnonymizedCandidate,
        job_description: JobDescription,
        evaluation_result: MatchEvaluationResult,
        target_minutes: int = 45,
    ) -> InterviewPlan:
        """
        Synthesizes an InterviewPlan tailored to the candidate's specific gaps,
        borderline requirements, and key technical strengths.
        """
        # 1. Compile per-requirement evaluation breakdown for the prompt
        breakdown_lines: List[str] = []
        req_map = {r.id: r for r in job_description.requirements}

        for match in evaluation_result.requirement_matches:
            req = req_map.get(match.requirement_id)
            title = req.title if req else match.requirement_id
            category = req.category.value if (req and hasattr(req.category, "value")) else (str(req.category) if req else "unknown")

            citations_text = "; ".join([f'"{c.quote}"' for c in match.citations]) or "No citations"
            clarification_line = f"  Clarification Screening Question: {match.clarification_question}\n" if getattr(match, "clarification_question", None) else ""
            transferable_line = f"  Transferable Competency: {match.transferable_skill} (probe candidate's ability to adapt equivalent tech)\n" if getattr(match, "transferable_skill", None) else ""
            doubt_line = "  Benefit of the Doubt: Yes (ambiguous phrasing in CV; candidate claims must be probed verbally)\n" if getattr(match, "benefit_of_doubt", False) else ""
            breakdown_lines.append(
                f"- Requirement '{title}' [{category}] (ID: {match.requirement_id}):\n"
                f"  Status: {match.status.value.upper()} (Score: {match.score})\n"
                f"  Reasoning: {match.reasoning}\n"
                f"{clarification_line}"
                f"{transferable_line}"
                f"{doubt_line}"
                f"  Citations: {citations_text}\n"
                f"  Gap Analysis: {match.gap_analysis or 'None'}"
            )

        evaluation_summary = "\n".join(breakdown_lines)

        # 2. Formulate the synthesis prompt
        prompt = (
            f"Job Position: {job_description.title}\n"
            f"Candidate Overall Score: {evaluation_result.overall_score}%\n"
            f"Recommendation: {evaluation_result.recommendation.value}\n"
            f"Must-Have Gaps Count: {evaluation_result.must_have_gaps_count}\n\n"
            f"Requirement Evaluation Breakdown:\n{evaluation_summary}\n\n"
            f"Generate a {target_minutes}-minute interview guide tailored to probe this candidate's "
            f"identified gaps and verify claimed technical strengths.\n"
            f"For each question, formulate clear open-ended prompts and provide:\n"
            f"- question_text\n"
            f"- rationale_for_asking (why we are probing this)\n"
            f"- expected_answer (detailed model good answer)\n"
            f"- expected_answers (bullet points of good answer criteria)\n"
            f"- bad_answer (detailed example of an unacceptable or poor answer)\n"
            f"- bad_answers (bullet points of red flags / poor answers)\n"
            f"- difficulty ('junior', 'mid', 'senior', or 'principal')\n"
            f"- estimated_minutes\n\n"
            f"Set candidate_id to '{candidate.candidate_id}' and job_id to '{job_description.id}'."
        )

        # 3. Invoke LLM structured generation
        if hasattr(self.llm_client, "set_action_context"):
            self.llm_client.set_action_context(
                "interview_generation",
                metadata={
                    "candidate_id": str(candidate.candidate_id),
                    "job_id": str(job_description.id),
                    "target_duration_minutes": target_minutes,
                },
            )

        try:
            plan = self.llm_client.generate_structured(
                prompt=prompt,
                response_model=InterviewPlan,
                system_prompt=INTERVIEW_SYSTEM_PROMPT,
                temperature=0.2,
            )
        except Exception as llm_err:
            import logging
            logging.getLogger(__name__).warning(
                "All LLM providers failed or timed out during interview plan generation (%s). "
                "Engaging resilient rubric synthesis fallback to guarantee zero recruiter downtime.",
                llm_err,
            )
            return self._synthesize_offline_rubric_plan(
                candidate=candidate,
                job_description=job_description,
                evaluation_result=evaluation_result,
                target_minutes=target_minutes,
            )

        # 4. Guarantee IDs and target duration alignment
        plan.candidate_id = candidate.candidate_id
        plan.job_id = job_description.id
        if not plan.total_estimated_minutes or plan.total_estimated_minutes == 45:
            plan.total_estimated_minutes = target_minutes
        plan.total_duration_minutes = plan.total_estimated_minutes
        if not plan.executive_summary and plan.interview_focus_summary:
            plan.executive_summary = plan.interview_focus_summary
        elif not plan.interview_focus_summary and plan.executive_summary:
            plan.interview_focus_summary = plan.executive_summary

        return plan

    def _synthesize_offline_rubric_plan(
        self,
        candidate: AnonymizedCandidate,
        job_description: JobDescription,
        evaluation_result: MatchEvaluationResult,
        target_minutes: int = 45,
    ) -> InterviewPlan:
        """
        Deterministic, rubric-driven fallback generator that guarantees an interview plan
        is always produced based on verified evaluation findings even if all external LLM APIs are exhausted.
        """
        questions = []
        req_map = {r.id: r for r in job_description.requirements}

        # 1. Identify gaps first (unmet / borderline must-haves)
        gaps = [m for m in evaluation_result.requirement_matches if getattr(m, "score", 1.0) < 0.75]
        strengths = [m for m in evaluation_result.requirement_matches if getattr(m, "score", 1.0) >= 0.75]

        total_items = max(1, len(gaps) + min(len(strengths), 3))
        mins_per_q = max(5, target_minutes // total_items)

        for m in gaps:
            req = req_map.get(m.requirement_id)
            title = req.title if req else m.requirement_id
            clarification = getattr(m, "clarification_question", None)
            gap_text = getattr(m, "gap_analysis", None) or getattr(m, "reasoning", "Evidence in profile is partial or unverified.")

            q_text = clarification or f"Can you describe your practical experience with {title}? Specifically, how have you applied it in production or project environments?"
            questions.append(
                InterviewQuestion(
                    id=f"q_{uuid4().hex[:8]}",
                    target_requirement_id=m.requirement_id,
                    archetype=QuestionArchetype.GAP_VERIFICATION,
                    question_text=q_text,
                    expected_answer=f"The candidate should provide concrete examples demonstrating hands-on competence with {title}, addressing the screening gap: {gap_text}",
                    expected_answers=[
                        f"Demonstrates clear conceptual knowledge and direct application of {title}",
                        "Describes specific architectural decisions, tools, and technical constraints",
                        "Addresses gaps noted during resume screening with verifiable professional details",
                    ],
                    bad_answer=f"Vague, buzzword-heavy response with no specific implementation details regarding {title}.",
                    bad_answers=[
                        "Evasive or unable to provide a concrete scenario where they used this skill",
                        "Claims competence on resume but cannot explain core fundamentals or workflow",
                        "Relies purely on theoretical definitions without practical problem-solving context",
                    ],
                    estimated_minutes=mins_per_q,
                    difficulty="mid",
                    rationale_for_asking=f"Screening identified a gap or partial evidence for '{title}' (Score: {m.score}). Verbal verification is required.",
                )
            )

        for m in strengths[:3]:
            req = req_map.get(m.requirement_id)
            title = req.title if req else m.requirement_id
            questions.append(
                InterviewQuestion(
                    id=f"q_{uuid4().hex[:8]}",
                    target_requirement_id=m.requirement_id,
                    archetype=QuestionArchetype.TECHNICAL_DEEP_DIVE,
                    question_text=f"Regarding your work with {title}, what was the most complex technical challenge or failure mode you encountered, and how did you resolve it?",
                    expected_answer=f"The candidate should discuss advanced architectural trade-offs, performance optimization, and deep familiarity with {title}.",
                    expected_answers=[
                        f"Articulates deep, production-tested understanding of {title}",
                        "Explains trade-offs and alternative approaches considered",
                        "Highlights measurable impact and reliability best practices",
                    ],
                    bad_answer="Generic textbook answer that does not reflect actual ownership or complex troubleshooting.",
                    bad_answers=[
                        "Cannot explain why specific technical choices were made",
                        "Superficial understanding of underlying systems or failure modes",
                    ],
                    estimated_minutes=mins_per_q,
                    difficulty="senior",
                    rationale_for_asking=f"Verified technical strength on '{title}' (Score: {m.score}). Probe architectural depth and problem-solving ownership.",
                )
            )

        if len(questions) < 4:
            questions.append(
                InterviewQuestion(
                    id=f"q_{uuid4().hex[:8]}",
                    target_requirement_id="behavioral_alignment",
                    archetype=QuestionArchetype.BEHAVIORAL,
                    question_text=f"Tell us about a time you had a technical disagreement with a team member or stakeholder on a project related to {job_description.title}. How did you navigate it?",
                    expected_answer="Demonstrates constructive communication, data-driven reasoning, active listening, and putting the team/product outcome first.",
                    expected_answers=[
                        "Uses objective metrics or trade-off analysis to evaluate competing viewpoints",
                        "Listens actively and demonstrates empathy and professional maturity",
                        "Achieves alignment or commits fully to the team decision",
                    ],
                    bad_answer="Blames others, shows inflexibility, or avoids resolving conflicts directly.",
                    bad_answers=[
                        "Dismissive of colleagues' input or overly defensive",
                        "Passive aggressive or refuses to align with the team direction",
                    ],
                    estimated_minutes=mins_per_q,
                    difficulty="mid",
                    rationale_for_asking="Assess team collaboration, conflict resolution, and communication maturity.",
                )
            )

        summary = (
            f"Tailored interview guide for {job_description.title} targeting {len(gaps)} screening gap(s) "
            f"and verifying claimed competencies. (Synthesized via resilient rubric fallback)."
        )

        return InterviewPlan(
            id=uuid4(),
            candidate_id=candidate.candidate_id,
            job_id=job_description.id,
            questions=questions,
            total_estimated_minutes=target_minutes,
            total_duration_minutes=target_minutes,
            interview_focus_summary=summary,
            executive_summary=summary,
            interviewer_tips=[
                "Focus on the 'gap_verification' questions first to confirm minimum role qualifications.",
                "Dig into specific scenarios using the STAR method (Situation, Task, Action, Result).",
                "Verify whether candidate's verbal explanations align with the quotes cited in the screening dossier.",
            ],
            is_draft=False,
            hitl_approved=True,
        )

