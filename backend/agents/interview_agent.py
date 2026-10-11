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
        plan = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=InterviewPlan,
            system_prompt=INTERVIEW_SYSTEM_PROMPT,
            temperature=0.2,
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
