"""
backend/schemas/interview.py
Data contracts for post-HITL tailored interview guides and evaluation rubrics.
"""

from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator


class QuestionArchetype(str, Enum):
    """Pedagogical / evaluative archetype of an interview question."""
    TECHNICAL_DEEP_DIVE = "technical_deep_dive"
    GAP_VERIFICATION = "gap_verification"
    BEHAVIORAL = "behavioral"
    BEHAVIORAL_STAR = "behavioral_star"  # Kept for backward compatibility


class InterviewQuestion(BaseModel):
    """A single targeted interview question tailored to candidate gaps and strengths."""
    id: str = Field(default_factory=lambda: f"q_{uuid4().hex[:8]}", description="Unique question identifier, e.g. 'q_asyncio_scaling'")
    target_requirement_id: str = Field(description="Referenced JobRequirement ID that this question investigates")
    archetype: QuestionArchetype = Field(default=QuestionArchetype.TECHNICAL_DEEP_DIVE, description="Category of question: technical, gap verification, or behavioral")
    question_text: str = Field(description="Verbatim question prompt for the interviewer")

    # Expected answers / positive signals
    expected_answer: str = Field(default="", description="Detailed model/expected good answer showing candidate depth and competence")
    expected_answers: List[str] = Field(default_factory=list, description="Key concepts or bullet points of an ideal response")
    expected_positive_signals: List[str] = Field(default_factory=list, description="Key concepts or signals indicating strong mastery")

    # Bad answers / red flags
    bad_answer: str = Field(default="", description="Detailed example of a poor/bad answer displaying red flags, superficial knowledge, or misconceptions")
    bad_answers: List[str] = Field(default_factory=list, description="Signs or warning indicators of a poor response")
    red_flags: List[str] = Field(default_factory=list, description="Signs of superficial knowledge or fabricated experience")

    # Timing, difficulty, and rationale
    estimated_minutes: int = Field(default=10, ge=1, le=120, description="Suggested time allocation for this topic in minutes")
    difficulty: str = Field(default="mid", description="Difficulty tier: junior, mid, senior, or principal")
    rationale_for_asking: str = Field(default="", description="Interviewer rationale explaining why this question is probed")

    # Compatibility aliases
    question_id: Optional[str] = Field(default=None, description="Alias for id")
    target_duration_minutes: Optional[int] = Field(default=None, description="Alias for estimated_minutes")
    expected_answer_rubric: Optional[str] = Field(default=None, description="Alias for expected_answer")

    @model_validator(mode="after")
    def sync_question_fields(self) -> "InterviewQuestion":
        # Question ID sync
        if not self.question_id:
            self.question_id = self.id
        elif not self.id:
            self.id = self.question_id

        # Target duration sync
        if self.target_duration_minutes and not self.estimated_minutes:
            self.estimated_minutes = self.target_duration_minutes
        elif not self.target_duration_minutes:
            self.target_duration_minutes = self.estimated_minutes

        # Expected answers sync
        if not self.expected_answer and self.expected_answers:
            self.expected_answer = "\n".join(self.expected_answers)
        elif self.expected_answer and not self.expected_answers:
            self.expected_answers = [self.expected_answer]

        if not self.expected_positive_signals and self.expected_answers:
            self.expected_positive_signals = list(self.expected_answers)
        elif not self.expected_answers and self.expected_positive_signals:
            self.expected_answers = list(self.expected_positive_signals)
            if not self.expected_answer:
                self.expected_answer = "\n".join(self.expected_positive_signals)

        if not self.expected_answer_rubric:
            self.expected_answer_rubric = self.expected_answer

        # Bad answers sync
        if not self.bad_answer and self.bad_answers:
            self.bad_answer = "\n".join(self.bad_answers)
        elif self.bad_answer and not self.bad_answers:
            self.bad_answers = [self.bad_answer]

        if not self.red_flags and self.bad_answers:
            self.red_flags = list(self.bad_answers)
        elif not self.bad_answers and self.red_flags:
            self.bad_answers = list(self.red_flags)
            if not self.bad_answer:
                self.bad_answer = "\n".join(self.red_flags)

        return self


class InterviewPlan(BaseModel):
    """Complete synthesized interview guide for an approved candidate."""
    id: UUID = Field(default_factory=uuid4, description="Interview guide ID")
    candidate_id: UUID = Field(description="Candidate identifier")
    job_id: UUID = Field(description="Job description identifier")
    questions: List[InterviewQuestion] = Field(default_factory=list, description="Ordered sequence of tailored questions")
    total_estimated_minutes: int = Field(default=45, ge=5, le=240, description="Suggested time allocation for this interview in minutes")
    total_duration_minutes: Optional[int] = Field(default=None, description="Alias for total_estimated_minutes")
    interview_focus_summary: str = Field(default="", description="Executive summary of what the interviewers should probe")
    executive_summary: Optional[str] = Field(default=None, description="Alias for interview_focus_summary")
    interviewer_tips: Optional[List[str]] = Field(default_factory=list, description="Practical advice and follow-up probes for interviewers")

    @model_validator(mode="after")
    def sync_duration_and_summary(self) -> "InterviewPlan":
        if self.total_duration_minutes and not self.total_estimated_minutes:
            self.total_estimated_minutes = self.total_duration_minutes
        elif not self.total_duration_minutes:
            self.total_duration_minutes = self.total_estimated_minutes

        if not self.executive_summary and self.interview_focus_summary:
            self.executive_summary = self.interview_focus_summary
        elif not self.interview_focus_summary and self.executive_summary:
            self.interview_focus_summary = self.executive_summary
        return self

    @property
    def target_duration_minutes(self) -> int:
        """Alias property for total_estimated_minutes to guarantee compatibility."""
        return self.total_estimated_minutes
