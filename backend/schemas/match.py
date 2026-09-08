"""
backend/schemas/match.py
Data contracts for semantic matching, citations, and evaluation results.
"""

from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class MatchStatus(str, Enum):
    """Evaluation status for a single requirement."""
    MET = "met"
    PARTIAL = "partial"
    NOT_MET = "not_met"


class Recommendation(str, Enum):
    """Algorithmic recommendation tier based on decision matrix."""
    STRONG_MATCH = "strong_match"  # Score >= 70% and 0 must-have gaps
    BORDERLINE = "borderline"      # 50% <= Score < 70% or 1 must-have gap
    REJECT = "reject"              # Score < 50% or >= 2 must-have gaps


class VerbatimCitation(BaseModel):
    """Exact text quote from candidate's CV grounding a claim."""
    quote: str = Field(description="Exact verbatim excerpt from candidate's CV")
    source_section: Optional[str] = Field(default=None, description="Section where excerpt was found (e.g. 'Experience', 'Projects')")
    verified: bool = Field(default=False, description="True if verified as exact substring by deterministic checker")


class RequirementMatch(BaseModel):
    """Evaluation result for a single atomic requirement."""
    requirement_id: str = Field(description="Referenced requirement ID")
    status: MatchStatus = Field(description="Evaluation: met, partial, or not_met")
    score: float = Field(ge=0.0, le=1.0, description="Score for this requirement (0.0 to 1.0)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Agent confidence score")
    reasoning: str = Field(description="Brief explanation of why this status was assigned")
    citations: List[VerbatimCitation] = Field(default_factory=list, description="Verbatim citations supporting this match")
    gap_analysis: Optional[str] = Field(default=None, description="Missing skills or partial shortcomings")


class MatchEvaluationResult(BaseModel):
    """Complete evaluation report for a candidate against a job description."""
    id: UUID = Field(default_factory=uuid4, description="Evaluation run ID")
    candidate_id: UUID = Field(description="Candidate identifier")
    job_id: UUID = Field(description="Job description identifier")
    overall_score: float = Field(ge=0.0, le=100.0, description="Overall weighted score for this evaluation")
    must_have_score: float = Field(ge=0.0, le=100.0, description="Must-have score for this evaluation")
    nice_to_have_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Nice-to-have score for this evaluation")
    recommendation: Recommendation = Field(description="Algorithmic recommendation tier based on decision matrix")
    requirement_matches: List[RequirementMatch] = Field(default_factory=list, description="Per-requirement evaluation breakdowns")
    must_have_gaps_count: int = Field(default=0, ge=0, description="Total count of unmet must-have requirements")
    citation_verification_score: float = Field(default=1.0, ge=0.0, le=1.0, description="CVS metric (valid citations / total citations)")
    hitl_validated: bool = Field(default=False, description="Whether a recruiter has reviewed and validated this result")
    recruiter_notes: Optional[str] = Field(default=None, description="Recruiter audit comments from the HITL gate")
