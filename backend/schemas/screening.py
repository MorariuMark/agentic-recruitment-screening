"""Contracts for the recruiter fast funnel. Scores are evidence signals, not decisions."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.schemas.match import MatchEvaluationResult


class FastRankRequest(BaseModel):
    job_id: UUID
    candidate_ids: list[UUID] = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=100)
    deep_evaluation: bool = True

    @field_validator("candidate_ids")
    @classmethod
    def unique_candidates(cls, value):
        return list(dict.fromkeys(value))


class PreScreenRow(BaseModel):
    candidate_id: UUID
    rank: int = 0
    pre_screen_score: float
    similarity_score: float
    skills_score: float | None = None
    experience_score: float | None = None
    degree_score: float | None = None
    checks: list[str] = Field(default_factory=list)
    deep_status: Literal["not_selected", "pending", "completed", "failed"] = "not_selected"
    deep_evaluation: MatchEvaluationResult | None = None
    error: str | None = None


class ReviewDecision(BaseModel):
    decision: Literal["interview", "hold", "reject"]
    notes: str = Field(default="", max_length=5000)


class ShortlistRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=100)
