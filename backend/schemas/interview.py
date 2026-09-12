"""
backend/schemas/interview.py
Data contracts for post-HITL tailored interview guides and evaluation rubrics.
"""

from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class QuestionArchetype(str, Enum):
    """Pedagogical / evaluative archetype of an interview question."""
    TECHNICAL_DEEP_DIVE = "technical_deep_dive"
    GAP_VERIFICATION = "gap_verification"
    BEHAVIORAL_STAR = "behavioral_star"


class InterviewQuestion(BaseModel):
    """A single targeted interview question tailored to candidate gaps and strengths."""
    id: str = Field(description="Unique question identifier, e.g. 'q_asyncio_scaling'")
    target_requirement_id: str = Field(description="Referenced JobRequirement ID that this question investigates")
    archetype: QuestionArchetype = Field(description="Category of question: technical, gap verification, or behavioral")
    question_text: str = Field(description="Verbatim question prompt for the interviewer")
    expected_positive_signals: List[str] = Field(default_factory=list, description="Key concepts or signals indicating strong mastery")
    red_flags: List[str] = Field(default_factory=list, description="Signs of superficial knowledge or fabricated experience")
    estimated_minutes: int = Field(default=10, ge=1, le=60, description="Suggested time allocation for this topic in minutes")


class InterviewPlan(BaseModel):
    """Complete synthesized interview guide for an approved candidate."""
    id: UUID = Field(default_factory=uuid4, description="Interview guide ID")
    candidate_id: UUID = Field(description="Candidate identifier")
    job_id: UUID = Field(description="Job description identifier")
    questions: List[InterviewQuestion] = Field(default_factory=list, description="Ordered sequence of tailored questions")
    total_estimated_minutes: int = Field(default=45, ge=15, le=120, description="Suggested time allocation for this interview in minutes")
    interview_focus_summary: str = Field(default="", description="Executive summary of what the interviewers should probe")
    interviewer_tips: Optional[List[str]] = Field(default_factory=list, description="Practical advice and follow-up probes for interviewers")

    @property
    def target_duration_minutes(self) -> int:
        """Alias property for total_estimated_minutes to guarantee compatibility."""
        return self.total_estimated_minutes
