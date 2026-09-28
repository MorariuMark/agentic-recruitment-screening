"""
backend/db/repository.py
Asynchronous persistence repository providing CRUD operations for Candidates,
Job Requisitions, Semantic Evaluations, Interview Plans, and Audit Logs.
"""

from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import (
    AuditLogModel,
    CandidateModel,
    InterviewPlanModel,
    JobRequirementModel,
    JobRequisitionModel,
    MatchEvaluationModel,
)
from backend.db.session import async_session_scope
from backend.schemas.cv import AnonymizedCandidate, ParsedCV
from backend.schemas.interview import InterviewPlan
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import MatchEvaluationResult


class DatabaseRepository:
    """Async repository layer abstracting database queries and mutations."""

    @staticmethod
    async def save_candidate(
        parsed_cv: ParsedCV,
        anonymized_candidate: AnonymizedCandidate,
        chunks_indexed: int = 0,
        filename: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> CandidateModel:
        """Persists or updates candidate extraction and anonymization records."""
        async def _op(s: AsyncSession) -> CandidateModel:
            cid_str = str(anonymized_candidate.candidate_id)
            existing = await s.get(CandidateModel, cid_str)
            
            raw_dict = parsed_cv.model_dump(mode="json")
            anon_dict = anonymized_candidate.model_dump(mode="json")

            if existing:
                existing.original_filename = filename or existing.original_filename
                existing.raw_cv_json = raw_dict
                existing.anonymized_cv_json = anon_dict
                existing.sanitized_text = anonymized_candidate.sanitized_text
                existing.demographics_json = anonymized_candidate.demographic_data
                existing.chunks_indexed = chunks_indexed
                record = existing
            else:
                record = CandidateModel(
                    id=cid_str,
                    original_filename=filename,
                    full_name_redacted="[CANDIDATE_NAME]",
                    raw_cv_json=raw_dict,
                    anonymized_cv_json=anon_dict,
                    sanitized_text=anonymized_candidate.sanitized_text,
                    demographics_json=anonymized_candidate.demographic_data,
                    chunks_indexed=chunks_indexed,
                )
                s.add(record)

            await s.commit()
            await s.refresh(record)
            return record

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def get_candidate(
        candidate_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> Optional[CandidateModel]:
        """Retrieves a candidate profile by primary UUID string."""
        cid_str = str(candidate_id)

        async def _op(s: AsyncSession) -> Optional[CandidateModel]:
            return await s.get(CandidateModel, cid_str)

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def list_candidates(
        limit: int = 100,
        offset: int = 0,
        session: Optional[AsyncSession] = None,
    ) -> List[CandidateModel]:
        """Lists candidates ordered by most recently updated."""
        async def _op(s: AsyncSession) -> List[CandidateModel]:
            stmt = select(CandidateModel).order_by(desc(CandidateModel.updated_at)).offset(offset).limit(limit)
            result = await s.execute(stmt)
            return list(result.scalars().all())

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def save_job(
        job: JobDescription,
        source_url: Optional[str] = None,
        raw_text: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> JobRequisitionModel:
        """Persists or updates a job description with atomic requirement decomposition."""
        async def _op(s: AsyncSession) -> JobRequisitionModel:
            jid_str = str(job.id)
            existing = await s.get(JobRequisitionModel, jid_str)

            custom_sec = [c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in (job.custom_sections or [])]

            if existing:
                existing.title = job.title
                existing.department = job.department
                existing.seniority_level = job.seniority_level
                existing.location = getattr(job, "location", existing.location)
                existing.work_model = getattr(job, "work_model", existing.work_model)
                existing.employment_type = getattr(job, "employment_type", existing.employment_type)
                existing.source_url = source_url or existing.source_url
                existing.raw_text = raw_text or existing.raw_text
                existing.custom_sections_json = custom_sec
                existing.unused_details_json = getattr(job, "unused_details", [])
                record = existing
                # Clear and re-populate requirements
                existing.requirements.clear()
            else:
                record = JobRequisitionModel(
                    id=jid_str,
                    title=job.title,
                    department=job.department,
                    seniority_level=job.seniority_level,
                    location=getattr(job, "location", None),
                    work_model=getattr(job, "work_model", None),
                    employment_type=getattr(job, "employment_type", None),
                    source_url=source_url,
                    raw_text=raw_text,
                    custom_sections_json=custom_sec,
                    unused_details_json=getattr(job, "unused_details", []),
                )
                s.add(record)

            for req in job.requirements:
                req_model = JobRequirementModel(
                    id=req.id,
                    job_id=jid_str,
                    title=req.title,
                    category=req.category.value if hasattr(req.category, "value") else str(req.category),
                    weight=req.weight,
                    description=req.description,
                    minimum_years_experience=req.minimum_years_experience,
                )
                record.requirements.append(req_model)

            await s.commit()
            await s.refresh(record)
            return record

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def get_job(
        job_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> Optional[JobRequisitionModel]:
        """Retrieves a job description by primary UUID string."""
        jid_str = str(job_id)

        async def _op(s: AsyncSession) -> Optional[JobRequisitionModel]:
            stmt = select(JobRequisitionModel).options(selectinload(JobRequisitionModel.requirements)).where(JobRequisitionModel.id == jid_str)
            res = await s.execute(stmt)
            return res.scalar_one_or_none()

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def list_jobs(
        limit: int = 100,
        session: Optional[AsyncSession] = None,
    ) -> List[JobRequisitionModel]:
        """Lists all job requisitions ordered by creation time."""
        async def _op(s: AsyncSession) -> List[JobRequisitionModel]:
            stmt = select(JobRequisitionModel).options(selectinload(JobRequisitionModel.requirements)).order_by(desc(JobRequisitionModel.created_at)).limit(limit)
            result = await s.execute(stmt)
            return list(result.scalars().all())

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def save_evaluation(
        eval_result: MatchEvaluationResult,
        candidate_id: Union[UUID, str],
        job_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> MatchEvaluationModel:
        """Persists or updates a match evaluation result."""
        async def _op(s: AsyncSession) -> MatchEvaluationModel:
            eid_str = str(eval_result.id)
            existing = await s.get(MatchEvaluationModel, eid_str)

            matches_dump = [m.model_dump(mode="json") for m in eval_result.requirement_matches]
            rec_val = eval_result.recommendation.value if hasattr(eval_result.recommendation, "value") else str(eval_result.recommendation)

            if existing:
                existing.overall_score = eval_result.overall_score
                existing.must_have_score = eval_result.must_have_score
                existing.nice_to_have_score = eval_result.nice_to_have_score
                existing.must_have_gaps_count = eval_result.must_have_gaps_count
                existing.recommendation = rec_val
                existing.hitl_validated = eval_result.hitl_validated
                existing.recruiter_notes = eval_result.recruiter_notes
                existing.citation_verification_score = eval_result.citation_verification_score
                existing.matches_json = matches_dump
                record = existing
            else:
                record = MatchEvaluationModel(
                    id=eid_str,
                    candidate_id=str(candidate_id),
                    job_id=str(job_id),
                    overall_score=eval_result.overall_score,
                    must_have_score=eval_result.must_have_score,
                    nice_to_have_score=eval_result.nice_to_have_score,
                    must_have_gaps_count=eval_result.must_have_gaps_count,
                    recommendation=rec_val,
                    hitl_validated=eval_result.hitl_validated,
                    recruiter_notes=eval_result.recruiter_notes,
                    citation_verification_score=eval_result.citation_verification_score,
                    matches_json=matches_dump,
                )
                s.add(record)

            await s.commit()
            await s.refresh(record)
            return record

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def get_evaluation(
        evaluation_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> Optional[MatchEvaluationModel]:
        """Retrieves a match evaluation report by UUID string."""
        eid_str = str(evaluation_id)

        async def _op(s: AsyncSession) -> Optional[MatchEvaluationModel]:
            return await s.get(MatchEvaluationModel, eid_str)

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def list_evaluations_for_job(
        job_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> List[MatchEvaluationModel]:
        """Lists all candidate evaluations for a specific job requisition."""
        jid_str = str(job_id)

        async def _op(s: AsyncSession) -> List[MatchEvaluationModel]:
            stmt = select(MatchEvaluationModel).where(MatchEvaluationModel.job_id == jid_str).order_by(desc(MatchEvaluationModel.overall_score))
            res = await s.execute(stmt)
            return list(res.scalars().all())

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def update_hitl_validation(
        evaluation_id: Union[UUID, str],
        decision: str,
        notes: str,
        session: Optional[AsyncSession] = None,
    ) -> Optional[MatchEvaluationModel]:
        """Applies Human-in-the-Loop decision override and audit justification."""
        eid_str = str(evaluation_id)

        async def _op(s: AsyncSession) -> Optional[MatchEvaluationModel]:
            eval_record = await s.get(MatchEvaluationModel, eid_str)
            if not eval_record:
                return None

            eval_record.recommendation = decision
            eval_record.recruiter_notes = notes
            eval_record.hitl_validated = True

            # Also create an audit log entry for this human decision
            audit = AuditLogModel(
                entity_type="evaluation",
                entity_id=eid_str,
                action="HITL_VALIDATE",
                details_json={
                    "recruiter_decision": decision,
                    "recruiter_notes": notes,
                },
            )
            s.add(audit)

            await s.commit()
            await s.refresh(eval_record)
            return eval_record

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def save_interview_plan(
        plan: InterviewPlan,
        evaluation_id: Optional[Union[UUID, str]] = None,
        session: Optional[AsyncSession] = None,
    ) -> InterviewPlanModel:
        """Persists or updates an interview guide."""
        async def _op(s: AsyncSession) -> InterviewPlanModel:
            pid_str = str(plan.id)
            existing = await s.get(InterviewPlanModel, pid_str)

            questions_dump = [q.model_dump(mode="json") for q in plan.questions]

            if existing:
                existing.target_duration_minutes = plan.total_estimated_minutes
                existing.total_estimated_minutes = plan.total_estimated_minutes
                existing.questions_json = questions_dump
                record = existing
            else:
                record = InterviewPlanModel(
                    id=pid_str,
                    candidate_id=str(plan.candidate_id),
                    job_id=str(plan.job_id),
                    evaluation_id=str(evaluation_id) if evaluation_id else None,
                    target_duration_minutes=plan.total_estimated_minutes,
                    total_estimated_minutes=plan.total_estimated_minutes,
                    questions_json=questions_dump,
                )
                s.add(record)

            await s.commit()
            await s.refresh(record)
            return record

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def get_interview_plan(
        plan_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> Optional[InterviewPlanModel]:
        """Retrieves an interview plan by UUID string."""
        pid_str = str(plan_id)

        async def _op(s: AsyncSession) -> Optional[InterviewPlanModel]:
            return await s.get(InterviewPlanModel, pid_str)

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def record_audit_log(
        entity_type: str,
        entity_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> AuditLogModel:
        """Appends an immutable audit event entry."""
        async def _op(s: AsyncSession) -> AuditLogModel:
            log_entry = AuditLogModel(
                entity_type=entity_type,
                entity_id=str(entity_id),
                action=action,
                details_json=details or {},
            )
            s.add(log_entry)
            await s.commit()
            await s.refresh(log_entry)
            return log_entry

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)
