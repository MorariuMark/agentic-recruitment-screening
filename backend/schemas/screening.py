"""Contracts for the recruiter fast funnel. Scores are evidence signals, not decisions."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.schemas.match import MatchEvaluationResult, RequirementMatch


class FastRankRequest(BaseModel):
    job_id: UUID
    candidate_ids: list[UUID] = Field(min_length=1, max_length=50000)
    top_k: int = Field(default=10, ge=1, le=100)
    deep_evaluation: bool = True
    include_benchmark: bool = False
    pipeline_version: Literal["v1", "v2"] = "v1"
    rerank_enabled: bool = True
    rerank_pool_size: int = Field(default=100, ge=1, le=200)
    evidence_per_requirement: int = Field(default=3, ge=1, le=3)

    @field_validator("candidate_ids")
    @classmethod
    def unique_candidates(cls, value):
        return list(dict.fromkeys(value))


class DeepEvaluationRequest(BaseModel):
    candidate_ids: list[UUID] = Field(min_length=1, max_length=100)


class EvidencePassage(BaseModel):
    id: str
    section: str
    text: str
    strength: Literal["demonstrated", "listed"]


class RequirementAssessment(BaseModel):
    requirement_id: str
    title: str
    category: str
    weight: float
    status: Literal["supported", "partial", "contradicted", "unknown"]
    score: float
    reasoning: str
    evidence: list[EvidencePassage] = Field(default_factory=list)
    documented_years: float | None = None
    rerank_score: float | None = None


class PreScreenRow(BaseModel):
    candidate_id: UUID
    rank: int = 0
    pre_screen_score: float
    similarity_score: float
    skills_score: float | None = None
    experience_score: float | None = None
    degree_score: float | None = None
    checks: list[str] = Field(default_factory=list)
    deep_status: Literal["not_selected", "pending", "completed", "failed", "deferred"] = "not_selected"
    deep_requirement_matches: list[RequirementMatch] = Field(default_factory=list)
    retry_after: float | None = None
    deep_evaluation: MatchEvaluationResult | None = None
    error: str | None = None
    pipeline_version: Literal["v1", "v2"] = "v1"
    requirement_assessments: list[RequirementAssessment] = Field(default_factory=list)
    essential_supported: int = 0
    essential_total: int = 0
    essential_unknown: int = 0
    essential_contradicted: int = 0
    rerank_score: float | None = None
    reranked: bool = False
    initial_rank: int | None = None
    language_priority: int = 0


class ReviewDecision(BaseModel):
    decision: Literal["interview", "hold", "reject"]
    notes: str = Field(default="", max_length=5000)


class ShortlistRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=100)
    candidate_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
