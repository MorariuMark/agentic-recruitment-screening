"""
backend/db/repository.py
Asynchronous persistence repository providing CRUD operations for Candidates,
Job Requisitions, Semantic Evaluations, Interview Plans, and Audit Logs.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from sqlalchemy import desc, select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import (
    AuditLogModel,
    CandidateModel,
    CVDocumentModel,
    InterviewPlanModel,
    JobRequirementModel,
    JobRequisitionModel,
    JobDescriptionDataModel,
    MatchEvaluationModel,
    BatchJobModel,
    ScreeningRunModel,
    ScreeningFeatureCacheModel,
)
from backend.db.session import async_session_scope
from backend.config import settings
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

            raw_contact = raw_dict.get("contact_info") or {}
            c_name = raw_contact.get("full_name")
            if not c_name and filename:
                c_name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
            name_to_save = c_name or f"Candidate-{cid_str[:8].upper()}"

            now = datetime.now(timezone.utc)
            if existing:
                existing.original_filename = filename or existing.original_filename
                existing.full_name_redacted = name_to_save
                existing.raw_cv_json = raw_dict
                existing.anonymized_cv_json = anon_dict
                existing.sanitized_text = anonymized_candidate.sanitized_text
                existing.demographics_json = anonymized_candidate.demographic_data
                existing.chunks_indexed = chunks_indexed
                existing.updated_at = now
                record = existing
            else:
                record = CandidateModel(
                    id=cid_str,
                    original_filename=filename,
                    full_name_redacted=name_to_save,
                    raw_cv_json=raw_dict,
                    anonymized_cv_json=anon_dict,
                    sanitized_text=anonymized_candidate.sanitized_text,
                    demographics_json=anonymized_candidate.demographic_data,
                    chunks_indexed=chunks_indexed,
                    created_at=now,
                    updated_at=now,
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
            hidden = await s.scalar(select(CVDocumentModel.id).where(CVDocumentModel.candidate_id == cid_str, CVDocumentModel.deleted_at.is_not(None)))
            return None if hidden else await s.get(CandidateModel, cid_str)

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
            hidden = select(CVDocumentModel.candidate_id).where(CVDocumentModel.deleted_at.is_not(None), CVDocumentModel.candidate_id.is_not(None))
            stmt = select(CandidateModel).where(CandidateModel.id.not_in(hidden)).order_by(desc(CandidateModel.updated_at), CandidateModel.id).offset(offset).limit(limit)
            result = await s.execute(stmt)
            return list(result.scalars().all())

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def delete_candidate(
        candidate_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """
        Deletes a candidate by primary UUID, cascading across:
        - CandidateModel
        - MatchEvaluationModel
        - InterviewPlanModel
        - Redacts candidate references from ScreeningRunModel payloads (E15)
        """
        cid_str = str(candidate_id)

        async def _op(s: AsyncSession) -> bool:
            record = await s.get(CandidateModel, cid_str)
            if not record:
                return False

            # Cascade delete associated evaluations
            await s.execute(
                delete(MatchEvaluationModel).where(MatchEvaluationModel.candidate_id == cid_str)
            )

            # Cascade delete associated interview plans
            await s.execute(
                delete(InterviewPlanModel).where(InterviewPlanModel.candidate_id == cid_str)
            )
            s.expire(record, ["evaluations", "interview_plans"])

            # Redact candidate from ScreeningRunModel payloads (E15)
            runs_result = await s.execute(select(ScreeningRunModel))
            runs = runs_result.scalars().all()
            for run in runs:
                if cid_str not in str(run.payload or {}):
                    continue
                payload = dict(run.payload or {})
                modified = False

                if "candidate_ids" in payload and isinstance(payload["candidate_ids"], list):
                    orig_len = len(payload["candidate_ids"])
                    payload["candidate_ids"] = [c for c in payload["candidate_ids"] if str(c) != cid_str]
                    if len(payload["candidate_ids"]) != orig_len:
                        modified = True

                if "rows" in payload and isinstance(payload["rows"], list):
                    orig_len = len(payload["rows"])
                    payload["rows"] = [
                        row for row in payload["rows"]
                        if not (isinstance(row, dict) and (str(row.get("candidate_id")) == cid_str or str(row.get("id")) == cid_str))
                    ]
                    if len(payload["rows"]) != orig_len:
                        modified = True

                if "decisions" in payload and isinstance(payload["decisions"], dict):
                    if cid_str in payload["decisions"]:
                        payload["decisions"].pop(cid_str, None)
                        modified = True

                if "interviews" in payload and isinstance(payload["interviews"], dict):
                    if cid_str in payload["interviews"]:
                        payload["interviews"].pop(cid_str, None)
                        modified = True

                if "evaluations" in payload and isinstance(payload["evaluations"], dict):
                    if cid_str in payload["evaluations"]:
                        payload["evaluations"].pop(cid_str, None)
                        modified = True

                for key in ("shortlist_ids", "deep_candidate_ids", "evaluation_candidate_ids"):
                    if isinstance(payload.get(key), list):
                        updated = [value for value in payload[key] if str(value) != cid_str]
                        modified = modified or updated != payload[key]
                        payload[key] = updated
                for key in ("profile_hashes",):
                    if cid_str in payload.get(key, {}):
                        payload[key] = {k: v for k, v in payload[key].items() if k != cid_str}
                        modified = True
                if payload.get("duplicates"):
                    updated = [entry for entry in payload["duplicates"] if cid_str not in str(entry)]
                    modified = modified or updated != payload["duplicates"]
                    payload["duplicates"] = updated
                if modified:
                    run.payload = payload
                    s.add(run)

            # Cached embeddings contain passages; invalidate them on permanent erasure.
            await s.execute(delete(ScreeningFeatureCacheModel))
            # Original files follow the same permanent deletion path in both workspaces.
            await s.execute(delete(CVDocumentModel).where(CVDocumentModel.candidate_id == cid_str))
            logs = (await s.scalars(select(AuditLogModel))).all()
            for log in logs:
                details = log.details_json or {}
                if cid_str in str(details):
                    log.details_json = {"redacted": True, "reason": "Candidate permanently deleted"}
            await s.delete(record)
            await s.commit()
            return True

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
            existing = await s.get(
                JobRequisitionModel,
                jid_str,
                options=[selectinload(JobRequisitionModel.requirements)],
            )

            custom_sec = [c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in (job.custom_sections or [])]
            original_text = raw_text if raw_text is not None else job.raw_text

            if existing:
                existing.title = job.title
                existing.department = job.department
                existing.seniority_level = job.seniority_level
                existing.location = getattr(job, "location", existing.location)
                existing.work_model = getattr(job, "work_model", existing.work_model)
                existing.employment_type = getattr(job, "employment_type", existing.employment_type)
                existing.source_url = source_url or existing.source_url
                existing.raw_text = original_text or existing.raw_text
                existing.custom_sections_json = custom_sec
                existing.unused_details_json = getattr(job, "unused_details", [])
                existing.updated_at = datetime.now(timezone.utc)
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
                    raw_text=original_text,
                    custom_sections_json=custom_sec,
                    unused_details_json=getattr(job, "unused_details", []),
                )
                s.add(record)

            complete_data = job.model_dump(mode="json")
            if record.structured_data:
                record.structured_data.data = complete_data
            else:
                record.structured_data = JobDescriptionDataModel(job_id=jid_str, data=complete_data)

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
            stmt = (
                select(JobRequisitionModel)
                .options(selectinload(JobRequisitionModel.requirements))
                .order_by(desc(func.coalesce(JobRequisitionModel.updated_at, JobRequisitionModel.created_at)))
                .limit(limit)
            )
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
            scoring_context = {
                "job": eval_result.job_snapshot.model_dump(mode="json"),
                "strictness": eval_result.strictness,
                "clarification_count": eval_result.clarification_count,
            } if eval_result.job_snapshot else None
            rec_val = eval_result.recommendation.value if hasattr(eval_result.recommendation, "value") else str(eval_result.recommendation)

            prov_str = getattr(settings, "llm_provider", "unknown")
            model_attr = f"{prov_str}_model"
            mod_str = getattr(settings, model_attr, None) or prov_str

            if existing:
                existing.overall_score = eval_result.overall_score
                existing.must_have_score = eval_result.must_have_score
                existing.nice_to_have_score = eval_result.nice_to_have_score
                existing.must_have_gaps_count = eval_result.must_have_gaps_count
                existing.recommendation = rec_val
                if not getattr(existing, "llm_recommendation", None):
                    existing.llm_recommendation = rec_val
                existing.evaluated_with_provider = prov_str
                existing.evaluated_with_model = mod_str
                existing.hitl_validated = eval_result.hitl_validated
                existing.recruiter_notes = eval_result.recruiter_notes
                existing.citation_verification_score = eval_result.citation_verification_score
                existing.matches_json = matches_dump
                if scoring_context is not None:
                    existing.scoring_context_json = scoring_context
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
                    llm_recommendation=rec_val,
                    evaluated_with_provider=prov_str,
                    evaluated_with_model=mod_str,
                    hitl_validated=eval_result.hitl_validated,
                    recruiter_notes=eval_result.recruiter_notes,
                    citation_verification_score=eval_result.citation_verification_score,
                    matches_json=matches_dump,
                    scoring_context_json=scoring_context,
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
    async def list_evaluations_for_candidate(
        candidate_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> List[MatchEvaluationModel]:
        """Lists all evaluations for a specific candidate across all job requisitions."""
        cid_str = str(candidate_id)

        async def _op(s: AsyncSession) -> List[MatchEvaluationModel]:
            stmt = select(MatchEvaluationModel).where(MatchEvaluationModel.candidate_id == cid_str).order_by(desc(MatchEvaluationModel.overall_score))
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
        updated_evaluation: Optional[MatchEvaluationResult] = None,
    ) -> Optional[MatchEvaluationModel]:
        """Applies Human-in-the-Loop decision override and audit justification."""
        eid_str = str(evaluation_id)

        async def _op(s: AsyncSession) -> Optional[MatchEvaluationModel]:
            eval_record = await s.get(MatchEvaluationModel, eid_str)
            if not eval_record:
                return None

            if not getattr(eval_record, "llm_recommendation", None):
                eval_record.llm_recommendation = eval_record.recommendation
            if updated_evaluation is not None:
                # Scores, corrected matches and the human decision commit together.
                eval_record.overall_score = updated_evaluation.overall_score
                eval_record.must_have_score = updated_evaluation.must_have_score
                eval_record.nice_to_have_score = updated_evaluation.nice_to_have_score
                eval_record.must_have_gaps_count = updated_evaluation.must_have_gaps_count
                eval_record.citation_verification_score = updated_evaluation.citation_verification_score
                eval_record.matches_json = [match.model_dump(mode="json") for match in updated_evaluation.requirement_matches]
                if updated_evaluation.job_snapshot:
                    eval_record.scoring_context_json = {
                        "job": updated_evaluation.job_snapshot.model_dump(mode="json"),
                        "strictness": updated_evaluation.strictness,
                        "clarification_count": updated_evaluation.clarification_count,
                    }
            eval_record.recruiter_decision = decision
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

    @staticmethod
    async def create_batch_job(
        total_files: int,
        job_id: Optional[Union[UUID, str]] = None,
        batch_id: Optional[Union[UUID, str]] = None,
        session: Optional[AsyncSession] = None,
    ) -> BatchJobModel:
        """Initializes a new batch screening job record."""
        async def _op(s: AsyncSession) -> BatchJobModel:
            bid_str = str(batch_id) if batch_id else str(uuid4())
            record = BatchJobModel(
                id=bid_str,
                job_id=str(job_id) if job_id else None,
                status="PROCESSING",
                total_files=total_files,
                processed_files=0,
                failed_files=0,
                results_json=[],
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
    async def get_batch_job(
        batch_id: Union[UUID, str],
        session: Optional[AsyncSession] = None,
    ) -> Optional[BatchJobModel]:
        """Retrieves a batch screening job by ID."""
        bid_str = str(batch_id)

        async def _op(s: AsyncSession) -> Optional[BatchJobModel]:
            return await s.get(BatchJobModel, bid_str)

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def update_batch_progress(
        batch_id: Union[UUID, str],
        candidate_result: Dict[str, Any],
        is_success: bool = True,
        is_completed: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> Optional[BatchJobModel]:
        """Appends candidate result and updates processed count on the batch job."""
        bid_str = str(batch_id)

        async def _op(s: AsyncSession) -> Optional[BatchJobModel]:
            record = await s.get(BatchJobModel, bid_str)
            if not record:
                return None
            if record.status in {"CANCELLED", "INTERRUPTED"}:
                return record
            file_id = candidate_result.get("file_id")
            if file_id is not None and any(r.get("file_id") == file_id for r in (record.results_json or [])):
                return record

            curr_results = list(record.results_json or [])
            curr_results.append(candidate_result)
            record.results_json = curr_results
            if file_id is not None and record.progress_json:
                import copy
                progress = copy.deepcopy(record.progress_json)
                for item in progress.get("files", []):
                    if item["id"] == file_id:
                        item.update(status=candidate_result["status"], phase="Ready for verification" if is_success else "Parsing failed",
                                    candidate_id=candidate_result.get("candidate_id"), error=candidate_result.get("error"),
                                    duplicate_removed=bool(candidate_result.get("duplicate_removed")),
                                    finished_at=datetime.now(timezone.utc).isoformat())
                record.progress_json = progress

            if is_success:
                record.processed_files += 1
            else:
                record.failed_files += 1

            if is_completed or (record.processed_files + record.failed_files >= record.total_files):
                record.status = "COMPLETED" if record.failed_files == 0 else ("PARTIAL" if record.processed_files > 0 else "FAILED")
                record.progress_json = {**(record.progress_json or {}), "finished_at": datetime.now(timezone.utc).isoformat()}

            await s.commit()
            await s.refresh(record)
            return record

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)

    @staticmethod
    async def initialize_batch_files(batch_id, filenames, concurrency=4, document_ids=None):
        async with async_session_scope() as db:
            record = await db.get(BatchJobModel, str(batch_id))
            if record and not record.progress_json:
                record.progress_json = {"started_at": datetime.now(timezone.utc).isoformat(), "concurrency_limit": concurrency, "files": [
                    {"id": str(index), "document_id": document_ids[index] if document_ids else None,
                     "filename": name, "status": "QUEUED", "phase": "Waiting to parse"}
                    for index, name in enumerate(filenames)]}
                await db.commit()

    @staticmethod
    async def update_batch_file(batch_id, file_id, phase):
        import copy
        async with async_session_scope() as db:
            record = await db.get(BatchJobModel, str(batch_id))
            if not record or record.status != "PROCESSING":
                return
            progress = copy.deepcopy(record.progress_json or {})
            for item in progress.get("files", []):
                if item["id"] == file_id:
                    item.update(status="PROCESSING", phase=phase)
                    item.setdefault("started_at", datetime.now(timezone.utc).isoformat())
            record.progress_json = progress
            await db.commit()

    @staticmethod
    async def finish_batch_files(batch_id, status, error=None):
        import copy
        async with async_session_scope() as db:
            record = await db.get(BatchJobModel, str(batch_id))
            if not record:
                return
            progress = copy.deepcopy(record.progress_json or {})
            progress.setdefault("finished_at", datetime.now(timezone.utc).isoformat())
            for item in progress.get("files", []):
                if item["status"] in {"QUEUED", "PROCESSING"}:
                    item.update(status=status, phase=error or status.capitalize(), error=error)
                    if status == "FAILED":
                        record.failed_files += 1
                        record.results_json = [*(record.results_json or []),
                            {"file_id": item["id"], "filename": item["filename"], "status": "FAILED", "error": error}]
            record.progress_json = progress
            record.status = status
            await db.commit()

    @staticmethod
    async def recover_interrupted_batches(session: Optional[AsyncSession] = None) -> int:
        """Transitions any batch jobs stuck in PROCESSING state from a previous crash/restart to INTERRUPTED (E10)."""
        async def _op(s: AsyncSession) -> int:
            stmt = select(BatchJobModel).where(BatchJobModel.status == "PROCESSING")
            res = await s.execute(stmt)
            stuck_batches = res.scalars().all()
            recovered = 0
            for batch in stuck_batches:
                batch.status = "INTERRUPTED"
                import copy
                progress = copy.deepcopy(batch.progress_json or {})
                progress.setdefault("finished_at", batch.updated_at.replace(tzinfo=timezone.utc).isoformat())
                for item in progress.get("files", []):
                    if item["status"] in {"QUEUED", "PROCESSING"}:
                        item.update(status="INTERRUPTED", phase="Interrupted by server restart")
                batch.progress_json = progress
                curr_results = list(batch.results_json or [])
                curr_results.append({
                    "status": "INTERRUPTED",
                    "error": "Batch parsing interrupted by server restart. Unfinished files require re-upload.",
                })
                batch.results_json = curr_results
                s.add(batch)
                recovered += 1
            if recovered > 0:
                await s.commit()
            return recovered

        if session:
            return await _op(session)
        async with async_session_scope() as s:
            return await _op(s)
