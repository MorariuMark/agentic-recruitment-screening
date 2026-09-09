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
   - "behavioral_star": Probe collaboration, handling production incidents, or resolving technical disagreements.
2. Structure & Quality:
   - Formulate clear, open-ended question prompts (not simple yes/no questions).
   - Detail concrete "expected_positive_signals" (architectural concepts, metrics, best practices).
   - Detail concrete "red_flags" (hand-waving, superficial buzzwords, lack of depth, unverified assertions).
   - Allocate realistic minutes per question (sum should fit within total_estimated_minutes).
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
            category = req.category.value if req else "unknown"

            citations_text = "; ".join([f'"{c.quote}"' for c in match.citations]) or "No citations"
            breakdown_lines.append(
                f"- Requirement '{title}' [{category}] (ID: {match.requirement_id}):\n"
                f"  Status: {match.status.value.upper()} (Score: {match.score})\n"
                f"  Reasoning: {match.reasoning}\n"
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
        if not plan.total_estimated_minutes:
            plan.total_estimated_minutes = target_minutes

        return plan
