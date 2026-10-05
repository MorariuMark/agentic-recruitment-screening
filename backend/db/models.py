"""
backend/db/models.py
SQLAlchemy ORM models for relational persistence:
Jobs, Requirements, Candidates, Match Evaluations, Interview Plans, and Audit Logs.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


class JobRequisitionModel(Base):
    """Stores parsed job descriptions, positions, and associated requirement specifications."""
    __tablename__ = "job_requisitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    seniority_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    work_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_sections_json: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    unused_details_json: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    requirements: Mapped[List["JobRequirementModel"]] = relationship(
        "JobRequirementModel",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    evaluations: Mapped[List["MatchEvaluationModel"]] = relationship(
        "MatchEvaluationModel",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class JobRequirementModel(Base):
    """Atomic requirement decomposed from a Job Description."""
    __tablename__ = "job_requirements"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("job_requisitions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # must_have, nice_to_have, soft_skill
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    minimum_years_experience: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    job: Mapped["JobRequisitionModel"] = relationship("JobRequisitionModel", back_populates="requirements")


class CandidateModel(Base):
    """Stores candidate profiles, original parsed data, PII-scrubbed representations, and chunk stats."""
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name_redacted: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_cv_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    anonymized_cv_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    sanitized_text: Mapped[str] = mapped_column(Text, nullable=False)
    demographics_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    chunks_indexed: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    evaluations: Mapped[List["MatchEvaluationModel"]] = relationship(
        "MatchEvaluationModel",
        back_populates="candidate",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    interview_plans: Mapped[List["InterviewPlanModel"]] = relationship(
        "InterviewPlanModel",
        back_populates="candidate",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MatchEvaluationModel(Base):
    """Stores semantic evaluation results, grounded citations, scores, and recruiter HITL decisions."""
    __tablename__ = "match_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("job_requisitions.id", ondelete="CASCADE"),
        nullable=False,
    )

    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    must_have_score: Mapped[float] = mapped_column(Float, nullable=False)
    nice_to_have_score: Mapped[float] = mapped_column(Float, nullable=False)
    must_have_gaps_count: Mapped[int] = mapped_column(Integer, default=0)
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False)

    hitl_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    recruiter_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    citation_verification_score: Mapped[float] = mapped_column(Float, default=1.0)
    matches_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    candidate: Mapped["CandidateModel"] = relationship("CandidateModel", back_populates="evaluations")
    job: Mapped["JobRequisitionModel"] = relationship("JobRequisitionModel", back_populates="evaluations")
    interview_plans: Mapped[List["InterviewPlanModel"]] = relationship(
        "InterviewPlanModel",
        back_populates="evaluation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class InterviewPlanModel(Base):
    """Stores tailored interview guides and rubric questions synthesized by the InterviewAgent."""
    __tablename__ = "interview_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("job_requisitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("match_evaluations.id", ondelete="CASCADE"),
        nullable=True,
    )

    target_duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    total_estimated_minutes: Mapped[int] = mapped_column(Integer, default=45)
    questions_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    candidate: Mapped["CandidateModel"] = relationship("CandidateModel", back_populates="interview_plans")
    evaluation: Mapped[Optional["MatchEvaluationModel"]] = relationship("MatchEvaluationModel", back_populates="interview_plans")


class AuditLogModel(Base):
    """Immutable audit trail for all critical recruiter and agent events (EU AI Act compliance)."""
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BatchJobModel(Base):
    """Tracks asynchronous multi-file CV screening batches."""
    __tablename__ = "batch_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("job_requisitions.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="QUEUED")  # QUEUED, PROCESSING, COMPLETED, FAILED
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, default=0)
    results_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TokenUsageLogModel(Base):
    """Tracks token consumption, prompt/completion token distribution, latency, and model metrics."""
    __tablename__ = "token_usage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, default="general", index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="success")  # success, failover, error
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

