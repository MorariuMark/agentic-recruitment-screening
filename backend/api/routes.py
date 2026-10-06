"""
backend/api/routes.py
FastAPI REST routes for CV ingestion, JD evaluation, semantic matching,
Human-in-the-Loop (HITL) recruiter validation, and tailored interview guide generation.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.services.compliance_service import ComplianceService

from backend.agents.interview_agent import InterviewAgent
from backend.agents.job_parser_agent import JobParserAgent
from backend.agents.llm_factory import create_llm_client
from backend.agents.matching_agent import MatchingAgent
from backend.agents.parser_agent import ParserAgent, ScannedPDFException
from backend.config import settings
from backend.services.batch_processor import BatchProcessorService
from backend.services.event_stream import event_broadcaster
from backend.db.models import (
    CandidateModel,
    InterviewPlanModel,
    JobRequisitionModel,
    MatchEvaluationModel,
)
from backend.db.repository import DatabaseRepository
from backend.schemas.cv import AnonymizedCandidate, CVTaggedExport, ParsedCV
from backend.schemas.interview import InterviewPlan, InterviewQuestion
from backend.schemas.job import JobDescription, JobExtractionResult, JDTaggedExport, JobRequirement, RequirementCategory
from backend.schemas.match import MatchEvaluationResult, MatchStatus, Recommendation, RequirementMatch
from backend.schemas.token_usage import TokenUsageAnalytics, TokenUsageInfo
from backend.schemas.models_catalog import CATALOG_PROVIDERS, get_model_info, get_providers_catalog
from backend.services.audit_exporter import AuditExporter
from backend.services.ollama_service import OllamaService
from backend.services.scoring_engine import ScoringEngine
from backend.services.vector_store import VectorStoreService

logger = logging.getLogger("recruitment_screening.api")

router = APIRouter(prefix="/api/v1", tags=["Recruitment Screening"])

# ---------------------------------------------------------------------------
# In-Memory Datastores (State cache for candidate sessions and evaluations)
# ---------------------------------------------------------------------------
_CANDIDATE_RAW_STORE: Dict[UUID, ParsedCV] = {}
_CANDIDATE_ANONYMIZED_STORE: Dict[UUID, AnonymizedCandidate] = {}
_CANDIDATE_CHUNKS_STORE: Dict[UUID, int] = {}
_EVALUATION_STORE: Dict[UUID, MatchEvaluationResult] = {}
_INTERVIEW_PLAN_STORE: Dict[UUID, InterviewPlan] = {}

# Reusable service instances
_parser_agent = ParserAgent()
_job_parser_agent = JobParserAgent()
_vector_store = VectorStoreService()
_scoring_engine = ScoringEngine()
_matching_agent = MatchingAgent(vector_store=_vector_store, scoring_engine=_scoring_engine)
_interview_agent = InterviewAgent()
_ollama_service = OllamaService()
_batch_processor = BatchProcessorService(
    parser_agent=_parser_agent,
    vector_store=_vector_store,
    scoring_engine=_scoring_engine,
    matching_agent=_matching_agent,
)


# ---------------------------------------------------------------------------
# Database Object Reconstruction Helpers
# ---------------------------------------------------------------------------
def _reconstruct_candidate_from_db(cand_model: CandidateModel) -> Tuple[ParsedCV, AnonymizedCandidate, int]:
    parsed = ParsedCV.model_validate(cand_model.raw_cv_json or {})
    anonymized = AnonymizedCandidate.model_validate(cand_model.anonymized_cv_json or {})
    chunks_count = cand_model.chunks_indexed or 0
    return parsed, anonymized, chunks_count


def _reconstruct_evaluation_from_db(eval_model: MatchEvaluationModel) -> MatchEvaluationResult:
    matches: List[RequirementMatch] = []
    for m in (eval_model.matches_json or []):
        rm = RequirementMatch.model_validate(m)
        req_id_lower = rm.requirement_id.lower()
        reasoning_lower = rm.reasoning.lower()

        # Retroactive normalizer: if an existing evaluation marked interpretive items as NOT_MET
        if rm.status == MatchStatus.NOT_MET and (
            any(kw in req_id_lower for kw in ["night", "shift", "shifts", "attention", "detail", "learning", "growth", "fast_paced", "relocat", "travel"])
            or any(kw in reasoning_lower for kw in ["night shift", "attention to detail", "eagerness to learn", "learn and grow"])
        ):
            rm.status = MatchStatus.CLARIFICATION_NEEDED
            rm.is_objective = False
            rm.score = 0.5
            if not rm.clarification_question:
                if "shift" in req_id_lower:
                    rm.clarification_question = "Are you available and willing to work rotating or night shifts as required? [Yes / No]"
                elif "detail" in req_id_lower:
                    rm.clarification_question = "Can you confirm your ability to uphold strict attention to detail in procedural execution? [Yes / No]"
                elif "learn" in req_id_lower or "growth" in req_id_lower:
                    rm.clarification_question = "Are you committed to continuous learning and eager to develop new technical skills in a fast-paced environment? [Yes / No]"
                else:
                    rm.clarification_question = f"Can you confirm your readiness for '{rm.requirement_id}'? [Yes / No]"
            rm.gap_analysis = f"Interpretive / logistical detail requiring confirmation on application form or screening call: {rm.clarification_question}"

        matches.append(rm)

    clarification_count = sum(1 for m in matches if m.status == MatchStatus.CLARIFICATION_NEEDED)
    objective_must_have_gaps = sum(
        1 for m in matches if m.status == MatchStatus.NOT_MET and getattr(m, "is_objective", True)
    )

    rec = Recommendation(eval_model.recommendation)
    if rec == Recommendation.REJECT and objective_must_have_gaps == 0 and eval_model.overall_score >= 45.0:
        rec = Recommendation.BORDERLINE

    return MatchEvaluationResult(
        id=UUID(eval_model.id),
        candidate_id=UUID(eval_model.candidate_id),
        job_id=UUID(eval_model.job_id),
        overall_score=eval_model.overall_score,
        must_have_score=eval_model.must_have_score,
        nice_to_have_score=eval_model.nice_to_have_score,
        must_have_gaps_count=objective_must_have_gaps,
        clarification_count=clarification_count,
        recommendation=rec,
        hitl_validated=eval_model.hitl_validated,
        recruiter_notes=eval_model.recruiter_notes,
        citation_verification_score=eval_model.citation_verification_score,
        requirement_matches=matches,
    )


def _reconstruct_job_from_db(job_model: JobRequisitionModel) -> JobDescription:
    reqs = [
        JobRequirement(
            id=r.id,
            title=r.title,
            category=RequirementCategory(r.category),
            weight=r.weight,
            description=r.description,
            minimum_years_experience=r.minimum_years_experience,
        )
        for r in (job_model.requirements or [])
    ]
    return JobDescription(
        id=UUID(job_model.id),
        title=job_model.title,
        department=job_model.department,
        seniority_level=job_model.seniority_level,
        location=job_model.location,
        work_model=job_model.work_model,
        employment_type=job_model.employment_type,
        requirements=reqs,
        custom_sections=job_model.custom_sections_json or [],
        unused_details=job_model.unused_details_json or [],
        raw_text=job_model.raw_text or "",
    )


def _reconstruct_interview_plan_from_db(plan_model: InterviewPlanModel) -> InterviewPlan:
    questions = [InterviewQuestion.model_validate(q) for q in (plan_model.questions_json or [])]
    return InterviewPlan(
        id=UUID(plan_model.id),
        candidate_id=UUID(plan_model.candidate_id),
        job_id=UUID(plan_model.job_id),
        total_estimated_minutes=plan_model.total_estimated_minutes,
        questions=questions,
    )


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------
class CandidateListItem(BaseModel):
    """Summary item for candidate pipeline listing."""
    id: UUID = Field(description="Candidate identifier")
    masked_name: Optional[str] = Field(default=None, description="Anonymized name or alias")
    original_filename: Optional[str] = Field(default=None, description="Original uploaded filename")
    skills: List[str] = Field(default_factory=list, description="Extracted skills")
    total_years_experience: Optional[float] = Field(default=None, description="Total detected years of experience")
    chunks_indexed: int = Field(default=0, description="Vector chunks count")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of upload")
    latest_evaluation: Optional[Dict[str, Any]] = Field(default=None, description="Latest match evaluation summary if available")


class CandidateDetailResponse(BaseModel):
    """Detailed candidate profile including sanitized CV text for document inspection."""
    id: UUID = Field(description="Candidate identifier")
    masked_name: Optional[str] = Field(default=None, description="Anonymized name or alias")
    original_filename: Optional[str] = Field(default=None, description="Original uploaded filename")
    sanitized_text: Optional[str] = Field(default=None, description="Complete sanitized text representation of the CV")
    skills: List[str] = Field(default_factory=list, description="Extracted skills")
    experiences: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted work experience records")
    educations: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted academic credentials")
    total_years_experience: Optional[float] = Field(default=None, description="Total detected years of experience")
    chunks_indexed: int = Field(default=0, description="Vector chunks count")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of upload")
    latest_evaluation: Optional[Dict[str, Any]] = Field(default=None, description="Latest match evaluation summary if available")
    parsed_cv: Optional[Dict[str, Any]] = Field(default=None, description="Raw structured CV data")
    anonymized_candidate: Optional[Dict[str, Any]] = Field(default=None, description="Sanitized candidate profile")



class CVUploadResponse(BaseModel):
    """Response returned upon parsing and anonymizing a candidate CV."""
    candidate_id: UUID = Field(description="Unique anonymized candidate ID")
    parsed_cv: ParsedCV = Field(description="Structured CV representation")
    anonymized_candidate: AnonymizedCandidate = Field(description="PII-scrubbed candidate profile")
    chunks_indexed: int = Field(description="Count of semantic chunks stored in ChromaDB")
    token_usage: Optional[TokenUsageInfo] = Field(default=None, description="Inference token usage for CV extraction")


class BatchUploadResponse(BaseModel):
    """Response returned upon dispatching asynchronous batch screening."""
    batch_id: UUID = Field(description="Unique batch task identifier")
    total_files: int = Field(description="Number of CV documents received")
    status: str = Field(default="PROCESSING", description="Current status of the batch job")
    message: str = Field(description="Confirmation message")


class BatchJobStatusResponse(BaseModel):
    """Current progress and results of a batch screening job."""
    batch_id: UUID = Field(description="Unique batch task identifier")
    job_id: Optional[UUID] = Field(default=None, description="Associated job requisition ID if specified")
    status: str = Field(description="Batch status: QUEUED, PROCESSING, COMPLETED, PARTIAL, or FAILED")
    total_files: int = Field(description="Total files in batch")
    processed_files: int = Field(description="Count of successfully processed files")
    failed_files: int = Field(description="Count of failed files")
    progress_percentage: float = Field(description="Calculated progress from 0.0 to 100.0")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Array of per-candidate processing results")
    created_at: Optional[str] = Field(default=None)
    updated_at: Optional[str] = Field(default=None)


class MatchEvaluateRequest(BaseModel):
    """Request payload to evaluate an indexed candidate against a job description."""
    candidate_id: UUID = Field(description="UUID of previously uploaded candidate")
    job_description: JobDescription = Field(description="Job description and atomic criteria")


class CandidateCompareRequest(BaseModel):
    """Request payload to compare multiple candidates side-by-side for a job requisition."""
    candidate_ids: List[UUID] = Field(min_length=2, max_length=4, description="2 to 4 candidates to compare")
    job_id: UUID = Field(description="Job requisition UUID to compare against")


class RequirementComparisonCell(BaseModel):
    """Evaluation result of a single candidate on a single requirement."""
    status: MatchStatus
    score: float
    reasoning: str
    citation_quote: Optional[str] = None


class RequirementComparisonRow(BaseModel):
    """Matrix row for an atomic requirement comparing all evaluated candidates."""
    requirement_id: str
    title: str
    category: RequirementCategory
    weight: float
    candidate_cells: Dict[str, RequirementComparisonCell]  # candidate_id (str) -> RequirementComparisonCell


class CandidateComparisonSummaryItem(BaseModel):
    """Candidate high-level metrics for comparison banner."""
    candidate_id: UUID
    masked_name: str
    original_filename: Optional[str] = None
    overall_score: float
    must_have_score: float
    nice_to_have_score: float
    recommendation: Recommendation
    must_have_gaps_count: int
    citation_verification_score: float
    hitl_validated: bool


class CandidateComparisonReport(BaseModel):
    """Comprehensive comparison report across multiple candidates."""
    job_id: UUID
    job_title: str
    candidates: List[CandidateComparisonSummaryItem]
    matrix: List[RequirementComparisonRow]
    top_recommended_id: Optional[UUID] = None
    comparative_analysis: str


class HITLValidationRequest(BaseModel):
    """Request payload for the recruiter Human-in-the-Loop decision gate."""
    evaluation_id: UUID = Field(description="UUID of the MatchEvaluationResult")
    recruiter_decision: Recommendation = Field(description="Final recruiter decision tier")
    recruiter_notes: str = Field(description="Auditable justification for the decision or override")
    updated_matches: Optional[List[RequirementMatch]] = Field(default=None, description="Optional updated requirement matches if clarifications were resolved")


class InterviewGenerateRequest(BaseModel):
    """Request payload to synthesize a tailored interview plan."""
    candidate_id: UUID = Field(description="UUID of candidate")
    evaluation_id: UUID = Field(description="UUID of evaluation report")
    job_description: JobDescription = Field(description="Job description being interviewed for")
    target_duration_minutes: int = Field(default=45, ge=15, le=120, description="Target interview length")


class JobUrlParseRequest(BaseModel):
    """Request payload to extract a Job Description from a URL."""
    url: str = Field(description="Web URL of the job description posting")


class JobTextParseRequest(BaseModel):
    """Request payload to parse a Job Description from raw pasted text."""
    text: str = Field(description="Raw text content of the job description posting")


class FallbackHierarchyRequest(BaseModel):
    """Request payload to customize the sequence of LLM fallback candidates."""
    chain: List[Dict[str, Any]] = Field(description="Ordered list of {'provider': str, 'model': str} fallback targets")


class LLMSettingsResponse(BaseModel):
    """Response payload containing active LLM configuration and complete provider/model catalog."""
    active_provider: str = Field(description="Currently active LLM provider")
    active_model: str = Field(description="Currently active model for the active provider")
    compatibility_mode: str = Field(description="Structured JSON compatibility mode ('auto', 'json_object', 'schema_prompt')")
    providers_catalog: Dict[str, Any] = Field(description="Complete provider and model definitions with rate limits")
    api_keys_configured: Dict[str, bool] = Field(description="Status of configured API keys per provider")
    fallback_enabled: bool = Field(default=True, description="Whether multi-tier automatic failover is active")
    fallback_chain: List[str] = Field(default_factory=list, description="Sequence of fallback (provider:model) candidates")
    custom_fallback_chain: Optional[List[Dict[str, Any]]] = Field(default=None, description="User-customized fallback sequence")
    last_fallback_event: Optional[Dict[str, Any]] = Field(default=None, description="Metadata of most recent failover event")


class LLMUpdateRequest(BaseModel):
    """Request payload to dynamically update the active LLM provider and model."""
    provider: str = Field(description="Provider identifier (agnes, groq, openrouter, nvidia_nim, gemini, ollama)")
    model: str = Field(description="Target model identifier")
    compatibility_mode: str = Field(default="auto", description="Structured output compatibility mode")
    api_key: Optional[str] = Field(default=None, description="Optional new API key for the target provider")
    base_url: Optional[str] = Field(default=None, description="Optional custom base URL")


class LLMTestRequest(BaseModel):
    """Request payload to test connectivity and measure latency with specific LLM settings."""
    provider: str = Field(description="Provider identifier")
    model: str = Field(description="Model identifier")
    compatibility_mode: str = Field(default="auto", description="Compatibility mode")
    api_key: Optional[str] = Field(default=None, description="Optional API key for testing")
    base_url: Optional[str] = Field(default=None, description="Optional custom base URL")


class LLMTestResponse(BaseModel):
    """Result of LLM connection ping."""
    status: str = Field(description="'ok' or 'error'")
    provider: str = Field(description="Tested provider")
    model: str = Field(description="Tested model")
    latency_ms: float = Field(description="Latency in milliseconds")
    sample_output: Optional[str] = Field(default=None, description="Echo response if successful")
    error_message: Optional[str] = Field(default=None, description="Error details if failed")


class OllamaModelActionRequest(BaseModel):
    """Request payload to load or unload a local Ollama model in memory."""
    model: str = Field(description="Ollama model tag/name (e.g. 'qwen3.5:2b-q4_K_M')")
    keep_alive: str = Field(default="1h", description="Memory duration ('1h', '-1', '0')")


class OllamaPullRequest(BaseModel):
    """Request payload to pull/download an Ollama model."""
    model: str = Field(description="Model identifier to pull from the Ollama library")



# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/job/parse-url",
    response_model=JobExtractionResult,
    summary="Fetch, parse, and decompose a Job Description from a web URL",
)
async def parse_job_url(request: JobUrlParseRequest) -> JobExtractionResult:
    """
    Retrieves the HTML content of the job posting URL, extracts structured metadata
    and atomic requirement criteria using LLM, and audits for missing required elements.
    """
    try:
        result = await asyncio.to_thread(_job_parser_agent.parse_job_url, request.url)
        try:
            await DatabaseRepository.save_job(
                job=result.job_description,
                source_url=request.url,
            )
        except Exception as db_err:
            logger.warning(f"Failed to persist job to database: {db_err}")
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error extracting job description from URL: {str(e)}",
        )


@router.post(
    "/job/parse-text",
    response_model=JobExtractionResult,
    summary="Parse and decompose raw pasted Job Description text",
)
async def parse_job_text(request: JobTextParseRequest) -> JobExtractionResult:
    """
    Parses raw pasted job posting text, extracts structured metadata
    and atomic requirement criteria using LLM, and audits for missing required elements.
    """
    try:
        result = await asyncio.to_thread(_job_parser_agent.parse_job_text, request.text)
        try:
            await DatabaseRepository.save_job(
                job=result.job_description,
                raw_text=request.text,
            )
        except Exception as db_err:
            logger.warning(f"Failed to persist job to database: {db_err}")
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error parsing job description text: {str(e)}",
        )


@router.post(
    "/cv/upload",
    response_model=CVUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload, parse, scrub PII, and index a candidate CV",
)
async def upload_cv(file: UploadFile = File(...)) -> CVUploadResponse:
    """
    Accepts a CV file (PDF or text), extracts textual contents, invokes the Parser Agent
    for structured extraction, scrubs all PII, indexes chunks in ChromaDB, and returns
    the structured candidate profile.
    """
    try:
        content_bytes = await file.read()
        if not content_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        # 1. Parse structured CV and generate anonymized candidate profile
        parsed_cv, anonymized_candidate = await asyncio.to_thread(
            _parser_agent.parse_and_anonymize,
            source=content_bytes,
            filename=file.filename,
        )

        # 2. Index candidate chunks into ChromaDB for asymmetric RAG matching
        chunks_indexed = await asyncio.to_thread(
            _vector_store.index_candidate,
            anonymized_candidate,
        )

        # 3. Persist to relational database
        try:
            await DatabaseRepository.save_candidate(
                parsed_cv=parsed_cv,
                anonymized_candidate=anonymized_candidate,
                chunks_indexed=chunks_indexed,
                filename=file.filename,
            )
        except Exception as db_err:
            logger.warning(f"Failed to persist candidate to database: {db_err}")

        # 4. Cache instances in memory for fast lookup
        cid = anonymized_candidate.candidate_id
        _CANDIDATE_RAW_STORE[cid] = parsed_cv
        _CANDIDATE_ANONYMIZED_STORE[cid] = anonymized_candidate
        _CANDIDATE_CHUNKS_STORE[cid] = chunks_indexed

        token_usage_record = None
        if hasattr(_parser_agent.llm_client, "get_last_usage"):
            token_usage_record = _parser_agent.llm_client.get_last_usage()

        return CVUploadResponse(
            candidate_id=cid,
            parsed_cv=parsed_cv,
            anonymized_candidate=anonymized_candidate,
            chunks_indexed=chunks_indexed,
            token_usage=token_usage_record,
        )
    except ScannedPDFException as e:
        logger.warning(f"Single CV upload scanned PDF rejected '{getattr(file, 'filename', 'unknown')}': {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Single CV upload invalid input '{getattr(file, 'filename', 'unknown')}': {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error processing single CV '{getattr(file, 'filename', 'unknown')}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing candidate CV: {str(e)}",
        )


@router.post(
    "/cv/batch-upload",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload multiple candidate CVs for asynchronous batch parsing and screening",
)
async def batch_upload_cvs(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    job_id: Optional[UUID] = Form(None),
) -> BatchUploadResponse:
    """
    Accepts multiple CV files, stores their payloads, initializes a tracked
    batch job in the database, and dispatches background processing and semantic evaluation.
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded.")

    file_payloads: List[Tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        if content and f.filename:
            file_payloads.append((f.filename, content))

    if not file_payloads:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All uploaded files were empty.")

    batch_id = uuid4()

    # Initialize batch record in database
    await DatabaseRepository.create_batch_job(
        total_files=len(file_payloads),
        job_id=job_id,
        batch_id=batch_id,
    )

    # Dispatch asynchronous background task
    background_tasks.add_task(
        _batch_processor.execute_batch,
        batch_id=batch_id,
        file_payloads=file_payloads,
        job_id=job_id,
    )

    return BatchUploadResponse(
        batch_id=batch_id,
        total_files=len(file_payloads),
        status="PROCESSING",
        message=f"Batch of {len(file_payloads)} resumes accepted and queued for processing.",
    )


@router.get(
    "/cv/batch/{batch_id}",
    response_model=BatchJobStatusResponse,
    summary="Poll status and results of an asynchronous batch screening job",
)
async def get_batch_job_status(batch_id: UUID) -> BatchJobStatusResponse:
    """
    Fetches live progress, completion percentage, and individual candidate evaluation
    results for the specified batch job.
    """
    record = await DatabaseRepository.get_batch_job(batch_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job {batch_id} not found.",
        )

    processed_or_failed = record.processed_files + record.failed_files
    progress = round((processed_or_failed / max(record.total_files, 1)) * 100.0, 1)

    return BatchJobStatusResponse(
        batch_id=UUID(record.id),
        job_id=UUID(record.job_id) if record.job_id else None,
        status=record.status,
        total_files=record.total_files,
        processed_files=record.processed_files,
        failed_files=record.failed_files,
        progress_percentage=min(progress, 100.0),
        results=record.results_json or [],
        created_at=record.created_at.isoformat() if record.created_at else None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    )


@router.get(
    "/cv/batch/{batch_id}/stream",
    summary="Real-time Server-Sent Events (SSE) stream for batch screening progress",
    response_class=StreamingResponse,
)
async def stream_batch_events(batch_id: UUID) -> StreamingResponse:
    """
    Subscribes to live Server-Sent Events (SSE) for the specified batch job.
    Streams batch start, per-file processing, per-file completion, and batch completion.
    """
    record = await DatabaseRepository.get_batch_job(batch_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job {batch_id} not found.",
        )

    return StreamingResponse(
        event_broadcaster.subscribe_batch_events(batch_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/cv/{candidate_id}/export",
    response_model=CVTaggedExport,
    summary="Export candidate CV with tagged details (anonymised, visible, unused, extra)",
)
async def export_cv(candidate_id: UUID) -> CVTaggedExport:
    """
    Returns full structured audit export of candidate profile with every detail tagged
    by its extraction, redaction, or usage status.
    """
    anonymized = _CANDIDATE_ANONYMIZED_STORE.get(candidate_id)
    parsed = _CANDIDATE_RAW_STORE.get(candidate_id)
    chunks_count = _CANDIDATE_CHUNKS_STORE.get(candidate_id, 0)

    # Fallback to database if not resident in memory
    if not anonymized or not parsed:
        cand_record = await DatabaseRepository.get_candidate(candidate_id)
        if cand_record:
            parsed, anonymized, chunks_count = _reconstruct_candidate_from_db(cand_record)
            _CANDIDATE_RAW_STORE[candidate_id] = parsed
            _CANDIDATE_ANONYMIZED_STORE[candidate_id] = anonymized
            _CANDIDATE_CHUNKS_STORE[candidate_id] = chunks_count

    if not anonymized or not parsed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found in database or session cache.",
        )
    return AuditExporter.build_cv_tagged_export(
        parsed_cv=parsed,
        anonymized_candidate=anonymized,
        chunks_count=chunks_count,
    )


@router.post(
    "/job/export",
    response_model=JDTaggedExport,
    summary="Export Job Description with tagged details (visible, unused, extra, anonymised)",
)
async def export_job(job_description: JobDescription) -> JDTaggedExport:
    """
    Returns full structured audit export of the target Job Description with every
    criterion, scoring weight, and unmapped content item tagged with its status.
    """
    return AuditExporter.build_jd_tagged_export(job_description=job_description)


@router.post(
    "/match/evaluate",
    response_model=MatchEvaluationResult,
    summary="Evaluate candidate against job criteria with grounded RAG reasoning",
)
async def evaluate_match(request: MatchEvaluateRequest) -> MatchEvaluationResult:
    """
    Retrieves candidate chunks from ChromaDB for each job requirement, executes
    grounded LLM matching, deterministically verifies citation quotes, calculates
    the weighted score (75% must-have / 25% nice-to-have), and assigns a recommendation tier.
    """
    candidate = _CANDIDATE_ANONYMIZED_STORE.get(request.candidate_id)

    # Fallback to database if not in memory
    if not candidate:
        cand_record = await DatabaseRepository.get_candidate(request.candidate_id)
        if cand_record:
            parsed, candidate, chunks_count = _reconstruct_candidate_from_db(cand_record)
            _CANDIDATE_RAW_STORE[request.candidate_id] = parsed
            _CANDIDATE_ANONYMIZED_STORE[request.candidate_id] = candidate
            _CANDIDATE_CHUNKS_STORE[request.candidate_id] = chunks_count

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {request.candidate_id} not found. Please upload the CV first.",
        )

    try:
        # Run matching agent pipeline in worker thread to prevent event loop blocking
        result = await asyncio.to_thread(
            _matching_agent.match_candidate,
            candidate=candidate,
            job_description=request.job_description,
        )

        # Persist job and evaluation report to database
        try:
            await DatabaseRepository.save_job(request.job_description)
            await DatabaseRepository.save_evaluation(
                eval_result=result,
                candidate_id=request.candidate_id,
                job_id=request.job_description.id,
            )
        except Exception as db_err:
            logger.warning(f"Failed to persist evaluation to database: {db_err}")

        # Cache evaluation result
        _EVALUATION_STORE[result.id] = result
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing semantic matching: {str(e)}",
        )


@router.post(
    "/hitl/validate",
    response_model=MatchEvaluationResult,
    summary="Record recruiter Human-in-the-Loop decision and audit notes",
)
async def validate_hitl(request: HITLValidationRequest) -> MatchEvaluationResult:
    """
    Allows a human recruiter to review the agent's proposed match evaluation,
    override or confirm the recommendation tier, and attach audit notes before
    proceeding to interview generation.
    """
    evaluation = _EVALUATION_STORE.get(request.evaluation_id)

    # Fallback to database
    if not evaluation:
        eval_record = await DatabaseRepository.get_evaluation(request.evaluation_id)
        if eval_record:
            evaluation = _reconstruct_evaluation_from_db(eval_record)
            _EVALUATION_STORE[request.evaluation_id] = evaluation

    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {request.evaluation_id} not found.",
        )

    # Apply recruiter decision and audit log
    evaluation.recommendation = request.recruiter_decision
    evaluation.recruiter_notes = request.recruiter_notes
    evaluation.hitl_validated = True

    if request.updated_matches:
        evaluation.requirement_matches = request.updated_matches
        evaluation.clarification_count = sum(1 for m in request.updated_matches if m.status == MatchStatus.CLARIFICATION_NEEDED)
        evaluation.must_have_gaps_count = sum(1 for m in request.updated_matches if m.status == MatchStatus.NOT_MET and getattr(m, "is_objective", True))

    try:
        if request.updated_matches:
            await DatabaseRepository.save_evaluation(
                eval_result=evaluation,
                candidate_id=evaluation.candidate_id,
                job_id=evaluation.job_id,
            )
        await DatabaseRepository.update_hitl_validation(
            evaluation_id=request.evaluation_id,
            decision=request.recruiter_decision.value if hasattr(request.recruiter_decision, "value") else str(request.recruiter_decision),
            notes=request.recruiter_notes,
        )
    except Exception as db_err:
        logger.warning(f"Failed to persist HITL validation to database: {db_err}")

    _EVALUATION_STORE[request.evaluation_id] = evaluation
    return evaluation


@router.post(
    "/match/compare",
    response_model=CandidateComparisonReport,
    summary="Compare 2 to 4 candidates side-by-side against a job requisition",
)
async def compare_candidates(payload: CandidateCompareRequest) -> CandidateComparisonReport:
    """
    Executes a side-by-side comparative analysis of 2 to 4 candidates evaluated against
    the same job requisition. Yields head-to-head metrics, requirement fulfillment matrix,
    and algorithmic ranking.
    """
    job_record = await DatabaseRepository.get_job(payload.job_id)
    if not job_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job requisition {payload.job_id} not found.",
        )
    job_desc = _reconstruct_job_from_db(job_record)

    candidates_summary_items: List[CandidateComparisonSummaryItem] = []
    evaluations_by_candidate: Dict[str, MatchEvaluationResult] = {}

    existing_eval_records = await DatabaseRepository.list_evaluations_for_job(payload.job_id)
    existing_eval_map: Dict[str, MatchEvaluationResult] = {}
    for e in existing_eval_records:
        cid_key = str(e.candidate_id)
        reconstructed = _reconstruct_evaluation_from_db(e)
        existing_eval_map[cid_key] = reconstructed

    async def _resolve_candidate_evaluation(cid: UUID):
        cid_str = str(cid)
        cand_record = await DatabaseRepository.get_candidate(cid)
        if not cand_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate {cid} not found in database.",
            )

        anon_name = (
            cand_record.full_name_redacted
            or (cand_record.anonymized_cv_json or {}).get("masked_name")
            or f"Candidate-{cid_str[:6].upper()}"
        )
        if anon_name == "[CANDIDATE_NAME]":
            anon_name = f"Candidate-{cid_str[:6].upper()}"

        eval_result = existing_eval_map.get(cid_str)
        if not eval_result:
            _, anon_cand, _ = _reconstruct_candidate_from_db(cand_record)
            eval_result = await asyncio.to_thread(
                _matching_agent.match_candidate,
                candidate=anon_cand,
                job_description=job_desc,
            )
            try:
                await DatabaseRepository.save_evaluation(
                    eval_result=eval_result,
                    candidate_id=cid,
                    job_id=job_desc.id,
                )
            except Exception as db_err:
                logger.warning(f"Failed to save comparison evaluation: {db_err}")

        return cid, cid_str, cand_record, anon_name, eval_result

    resolved_candidates = await asyncio.gather(
        *(_resolve_candidate_evaluation(cid) for cid in payload.candidate_ids)
    )

    for cid, cid_str, cand_record, anon_name, eval_result in resolved_candidates:
        evaluations_by_candidate[cid_str] = eval_result

        cvs_score = eval_result.citation_verification_score if eval_result.citation_verification_score is not None else 1.0
        candidates_summary_items.append(
            CandidateComparisonSummaryItem(
                candidate_id=cid,
                masked_name=anon_name,
                original_filename=cand_record.original_filename,
                overall_score=eval_result.overall_score,
                must_have_score=eval_result.must_have_score,
                nice_to_have_score=eval_result.nice_to_have_score,
                recommendation=eval_result.recommendation,
                must_have_gaps_count=eval_result.must_have_gaps_count,
                citation_verification_score=cvs_score,
                hitl_validated=eval_result.hitl_validated,
            )
        )

    # Build Requirement Matrix
    matrix_rows: List[RequirementComparisonRow] = []
    for req in job_desc.requirements:
        cell_map: Dict[str, RequirementComparisonCell] = {}
        for cid in payload.candidate_ids:
            cid_str = str(cid)
            cand_eval = evaluations_by_candidate.get(cid_str)
            match = next((m for m in (cand_eval.requirement_matches if cand_eval else []) if m.requirement_id == req.id), None)
            if match:
                quote = match.citations[0].quote if match.citations else None
                cell_map[cid_str] = RequirementComparisonCell(
                    status=match.status,
                    score=match.score,
                    reasoning=match.reasoning,
                    citation_quote=quote,
                )
            else:
                cell_map[cid_str] = RequirementComparisonCell(
                    status=MatchStatus.NOT_MET,
                    score=0.0,
                    reasoning="Requirement not evaluated",
                    citation_quote=None,
                )

        matrix_rows.append(
            RequirementComparisonRow(
                requirement_id=req.id,
                title=req.title,
                category=req.category,
                weight=req.weight,
                candidate_cells=cell_map,
            )
        )

    # Rank candidates: 0 must-have gaps first, then highest must-have score, then overall score
    sorted_candidates = sorted(
        candidates_summary_items,
        key=lambda c: (
            -c.must_have_gaps_count,
            c.must_have_score,
            c.overall_score,
        ),
        reverse=True,
    )

    top_cand = sorted_candidates[0] if sorted_candidates else None
    top_id = top_cand.candidate_id if top_cand else None

    if top_cand and len(sorted_candidates) > 1:
        runner_up = sorted_candidates[1]
        cvs_pct = (top_cand.citation_verification_score if top_cand.citation_verification_score is not None else 1.0) * 100
        analysis = (
            f"Candidate {top_cand.masked_name} leads the cohort with an overall match score of "
            f"{top_cand.overall_score:.1f}% and {top_cand.must_have_gaps_count} must-have gaps, "
            f"outperforming {runner_up.masked_name} ({runner_up.overall_score:.1f}% overall, "
            f"{runner_up.must_have_gaps_count} gaps). Verified citation coverage stands at "
            f"{cvs_pct:.0f}%."
        )
    elif top_cand:
        analysis = f"Candidate {top_cand.masked_name} achieved an overall match of {top_cand.overall_score:.1f}%."
    else:
        analysis = "No candidates compared."

    return CandidateComparisonReport(
        job_id=payload.job_id,
        job_title=job_desc.title,
        candidates=candidates_summary_items,
        matrix=matrix_rows,
        top_recommended_id=top_id,
        comparative_analysis=analysis,
    )


@router.post(
    "/interview/generate",
    response_model=InterviewPlan,
    summary="Synthesize tailored interview plan focusing on candidate gaps",
)
async def generate_interview_plan(request: InterviewGenerateRequest) -> InterviewPlan:
    """
    Synthesizes a personalized, rubric-driven interview plan based on the candidate's
    identified gaps, borderline criteria, and key technical claims.
    """
    candidate = _CANDIDATE_ANONYMIZED_STORE.get(request.candidate_id)
    if not candidate:
        cand_record = await DatabaseRepository.get_candidate(request.candidate_id)
        if cand_record:
            _, candidate, _ = _reconstruct_candidate_from_db(cand_record)
            _CANDIDATE_ANONYMIZED_STORE[request.candidate_id] = candidate

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {request.candidate_id} not found.",
        )

    evaluation = _EVALUATION_STORE.get(request.evaluation_id)
    if not evaluation:
        eval_record = await DatabaseRepository.get_evaluation(request.evaluation_id)
        if eval_record:
            evaluation = _reconstruct_evaluation_from_db(eval_record)
            _EVALUATION_STORE[request.evaluation_id] = evaluation

    if not evaluation:
        # Fallback: check if an evaluation already exists for this candidate and job
        try:
            eval_records = await DatabaseRepository.list_evaluations_for_job(request.job_description.id)
            cand_eval = next((e for e in eval_records if e.candidate_id == str(request.candidate_id)), None)
            if cand_eval:
                evaluation = _reconstruct_evaluation_from_db(cand_eval)
        except Exception as check_err:
            logger.warning(f"Could not retrieve candidate evaluations: {check_err}")

    if not evaluation:
        # Auto-evaluate candidate against job description so interview guide can always be synthesized
        try:
            evaluation = await asyncio.to_thread(
                _matching_agent.match_candidate,
                candidate=candidate,
                job_description=request.job_description,
            )
            try:
                await DatabaseRepository.save_evaluation(
                    eval_result=evaluation,
                    candidate_id=request.candidate_id,
                    job_id=request.job_description.id,
                )
            except Exception as save_err:
                logger.warning(f"Failed to persist auto-evaluation: {save_err}")
            _EVALUATION_STORE[evaluation.id] = evaluation
        except Exception as eval_err:
            logger.error(f"Auto-evaluation failed during interview generation: {eval_err}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation {request.evaluation_id} not found and auto-evaluation failed: {eval_err}",
            )

    try:
        plan = await asyncio.to_thread(
            _interview_agent.generate_interview_plan,
            candidate=candidate,
            job_description=request.job_description,
            evaluation_result=evaluation,
            target_minutes=request.target_duration_minutes,
        )

        try:
            await DatabaseRepository.save_interview_plan(
                plan=plan,
                evaluation_id=evaluation.id,
            )
        except Exception as db_err:
            logger.warning(f"Failed to persist interview plan to database: {db_err}")

        _INTERVIEW_PLAN_STORE[plan.id] = plan
        return plan
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating interview plan: {str(e)}",
        )


@router.get(
    "/evaluation/{evaluation_id}",
    response_model=MatchEvaluationResult,
    summary="Retrieve an existing evaluation report by ID",
)
async def get_evaluation(evaluation_id: UUID) -> MatchEvaluationResult:
    """Fetches a cached or persisted evaluation report."""
    evaluation = _EVALUATION_STORE.get(evaluation_id)
    if not evaluation:
        eval_record = await DatabaseRepository.get_evaluation(evaluation_id)
        if eval_record:
            evaluation = _reconstruct_evaluation_from_db(eval_record)
            _EVALUATION_STORE[evaluation_id] = evaluation

    if not evaluation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found.")
    return evaluation


# ---------------------------------------------------------------------------
# Database Listing & Query Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/candidates",
    response_model=List[CandidateListItem],
    summary="List all stored candidates in database",
)
async def list_candidates(
    job_id: Optional[UUID] = None,
    limit: int = 1000,
    offset: int = 0,
) -> List[CandidateListItem]:
    """Returns candidate records stored in the persistent database with scoring breakdown."""
    records = await DatabaseRepository.list_candidates(limit=limit, offset=offset)
    items = []
    for r in records:
        raw = r.raw_cv_json or {}
        anon = r.anonymized_cv_json or {}
        skills = raw.get("skills", [])

        # Demographics / alias
        raw_contact = raw.get("contact_info") or {}
        real_name = raw_contact.get("full_name")
        if r.full_name_redacted and r.full_name_redacted != "[CANDIDATE_NAME]":
            masked_name = r.full_name_redacted
        elif real_name and real_name != "[CANDIDATE_NAME]":
            masked_name = real_name
        elif r.original_filename:
            fn_alias = r.original_filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
            masked_name = f"{fn_alias} (Candidate-{r.id[:6].upper()})"
        else:
            masked_name = f"Candidate-{r.id[:8].upper()}"

        # Total experience
        total_yrs = raw.get("total_years_experience") or anon.get("total_years_experience")
        if total_yrs is None and raw.get("experiences"):
            total_yrs = float(len(raw["experiences"]))

        # Latest evaluation
        latest_eval = None
        target_evals = [e for e in (r.evaluations or []) if not job_id or e.job_id == str(job_id)]
        if target_evals:
            sorted_evals = sorted(
                target_evals,
                key=lambda x: str(getattr(x, "created_at", "")) or "",
                reverse=True,
            )
            ev = sorted_evals[0]
            latest_eval = {
                "evaluation_id": ev.id,
                "overall_score": ev.overall_score,
                "must_have_score": ev.must_have_score,
                "nice_to_have_score": ev.nice_to_have_score,
                "recommendation": ev.recommendation,
                "must_have_gaps_count": ev.must_have_gaps_count,
                "citation_verification_score": ev.citation_verification_score,
                "hitl_validated": ev.hitl_validated,
            }

        items.append(
            CandidateListItem(
                id=UUID(r.id),
                masked_name=masked_name,
                original_filename=r.original_filename,
                skills=skills,
                total_years_experience=float(total_yrs) if total_yrs is not None else None,
                chunks_indexed=r.chunks_indexed,
                created_at=r.created_at.isoformat() if r.created_at else None,
                latest_evaluation=latest_eval,
            )
        )
    return items


@router.get(
    "/candidates/{candidate_id}",
    response_model=CandidateDetailResponse,
    summary="Get single candidate detail with sanitized CV text and structured profile",
)
async def get_candidate(candidate_id: UUID) -> CandidateDetailResponse:
    """Returns granular candidate profile including full sanitized text for document viewer."""
    record = await DatabaseRepository.get_candidate(candidate_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found.",
        )

    raw = record.raw_cv_json or {}
    anon = record.anonymized_cv_json or {}
    skills = raw.get("skills") or anon.get("skills") or []
    experiences = raw.get("experiences") or anon.get("experiences") or []
    educations = raw.get("educations") or anon.get("educations") or []

    total_yrs = raw.get("total_years_experience") or anon.get("total_years_experience")
    if total_yrs is None and experiences:
        total_yrs = float(len(experiences))

    raw_contact = raw.get("contact_info") or {}
    real_name = raw_contact.get("full_name")
    if record.full_name_redacted and record.full_name_redacted != "[CANDIDATE_NAME]":
        masked_name = record.full_name_redacted
    elif real_name and real_name != "[CANDIDATE_NAME]":
        masked_name = real_name
    elif record.original_filename:
        fn_alias = record.original_filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
        masked_name = f"{fn_alias} (Candidate-{str(candidate_id)[:6].upper()})"
    else:
        masked_name = f"Candidate-{str(candidate_id)[:8].upper()}"

    latest_eval = None
    if record.evaluations:
        sorted_evals = sorted(
            record.evaluations,
            key=lambda x: str(getattr(x, "created_at", "")) or "",
            reverse=True,
        )
        ev = sorted_evals[0]
        latest_eval = {
            "evaluation_id": ev.id,
            "overall_score": ev.overall_score,
            "must_have_score": ev.must_have_score,
            "nice_to_have_score": ev.nice_to_have_score,
            "recommendation": ev.recommendation,
            "must_have_gaps_count": ev.must_have_gaps_count,
            "citation_verification_score": ev.citation_verification_score,
            "hitl_validated": ev.hitl_validated,
        }

    sanitized_text = record.sanitized_text or ""
    if not sanitized_text.strip():
        parts = []
        if masked_name:
            parts.append(f"# {masked_name}")
        if raw.get("summary"):
            parts.append(f"## Professional Summary\n{raw['summary']}")
        if skills:
            parts.append("## Technical Skills\n" + ", ".join(skills))
        if experiences:
            parts.append("## Professional Experience")
            for exp in experiences:
                title = exp.get("job_title", "Role")
                company = exp.get("company_name", "Company")
                parts.append(f"### {title} at {company}")
                for desc in exp.get("work_description", []):
                    parts.append(f"- {desc}")
                skills_used = exp.get("skills_used") or []
                if skills_used:
                    parts.append(f"Technologies: {', '.join(skills_used)}")
        if educations:
            parts.append("## Education")
            for edu in educations:
                deg = edu.get("degree_title") or edu.get("degree_name", "Degree")
                inst = edu.get("institution_name", "Institution")
                parts.append(f"- {deg}, {inst}")
        sanitized_text = "\n\n".join(parts)

    return CandidateDetailResponse(
        id=UUID(record.id),
        masked_name=masked_name,
        original_filename=record.original_filename,
        sanitized_text=sanitized_text,
        skills=skills,
        experiences=experiences,
        educations=educations,
        chunks_indexed=record.chunks_indexed,
        total_years_experience=float(total_yrs) if total_yrs is not None else None,
        created_at=record.created_at.isoformat() if record.created_at else None,
        latest_evaluation=latest_eval,
        parsed_cv=raw,
        anonymized_candidate=anon,
    )


@router.delete(
    "/candidates/{candidate_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a candidate and all associated data",
)
async def delete_candidate(candidate_id: UUID) -> Dict[str, Any]:
    """
    Deletes candidate profile, relational evaluations/interview plans,
    and removes vector chunks from ChromaDB and memory caches.
    """
    cid_str = str(candidate_id)
    deleted = await DatabaseRepository.delete_candidate(candidate_id)
    in_memory = (
        candidate_id in _CANDIDATE_RAW_STORE
        or candidate_id in _CANDIDATE_ANONYMIZED_STORE
    )
    if not deleted and not in_memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found.",
        )

    # Remove from ChromaDB vector store
    await asyncio.to_thread(_vector_store.delete_candidate, candidate_id)

    # Clear memory caches
    _CANDIDATE_RAW_STORE.pop(candidate_id, None)
    _CANDIDATE_ANONYMIZED_STORE.pop(candidate_id, None)
    _CANDIDATE_CHUNKS_STORE.pop(candidate_id, None)

    return {
        "status": "deleted",
        "candidate_id": cid_str,
        "message": f"Candidate {cid_str} successfully deleted.",
    }


@router.get(
    "/jobs",
    response_model=List[JobDescription],
    summary="List all stored job requisitions in database",
)
async def list_jobs(limit: int = 50) -> List[JobDescription]:
    """Returns all job requisitions stored in the database."""
    job_records = await DatabaseRepository.list_jobs(limit=limit)
    return [_reconstruct_job_from_db(j) for j in job_records]


@router.post(
    "/jobs",
    response_model=JobDescription,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a job requisition with atomic requirement decomposition",
)
async def create_or_update_job(job: JobDescription) -> JobDescription:
    """Persists a job requisition and its atomic criteria directly."""
    await DatabaseRepository.save_job(job)
    return job


class RequirementUpdateRequest(BaseModel):
    requirements: List[JobRequirement]


@router.put(
    "/jobs/{job_id}/requirements",
    response_model=JobDescription,
    summary="Update atomic requirement weights and categories for a job requisition",
)
async def update_job_requirements(
    job_id: UUID,
    payload: RequirementUpdateRequest,
) -> JobDescription:
    """Updates requirement criteria weights and categories, saving changes to database."""
    job_record = await DatabaseRepository.get_job(job_id)
    if not job_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job requisition {job_id} not found.",
        )
    job_desc = _reconstruct_job_from_db(job_record)
    job_desc.requirements = payload.requirements
    await DatabaseRepository.save_job(job_desc)
    return job_desc


@router.get(
    "/jobs/{job_id}/evaluations",
    response_model=List[MatchEvaluationResult],
    summary="List all candidate evaluations for a specific job",
)
async def list_job_evaluations(job_id: UUID) -> List[MatchEvaluationResult]:
    """Returns all candidate evaluations computed for the specified job requisition."""
    eval_records = await DatabaseRepository.list_evaluations_for_job(job_id)
    return [_reconstruct_evaluation_from_db(e) for e in eval_records]


@router.get(
    "/interview/{plan_id}",
    response_model=InterviewPlan,
    summary="Retrieve an interview plan by ID from database",
)
async def get_interview_plan(plan_id: UUID) -> InterviewPlan:
    """Returns an interview plan by primary ID."""
    plan = _INTERVIEW_PLAN_STORE.get(plan_id)
    if not plan:
        plan_record = await DatabaseRepository.get_interview_plan(plan_id)
        if plan_record:
            plan = _reconstruct_interview_plan_from_db(plan_record)
            _INTERVIEW_PLAN_STORE[plan_id] = plan

    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview plan not found.")
    return plan


# ---------------------------------------------------------------------------
# LLM Settings & Dynamic Switching Endpoints
# ---------------------------------------------------------------------------
def _get_active_model_for_provider(provider: str) -> str:
    prov = provider.lower()
    if prov == "agnes":
        return settings.agnes_model
    elif prov == "groq":
        return settings.groq_model
    elif prov == "openrouter":
        return settings.openrouter_model
    elif prov == "nvidia_nim":
        return settings.nvidia_nim_model
    elif prov == "gemini":
        return settings.gemini_model
    elif prov == "ollama":
        return settings.ollama_model
    return "default"


@router.get(
    "/settings/llm",
    response_model=LLMSettingsResponse,
    summary="Fetch current LLM provider, active model, and complete catalog",
)
async def get_llm_settings() -> LLMSettingsResponse:
    """Returns the full catalog of models with rate limits, active configuration, and fallback hierarchy."""
    catalog_dict = {
        pid: pinfo.model_dump() for pid, pinfo in CATALOG_PROVIDERS.items()
    }
    from backend.agents.llm_factory import (
        DynamicLLMClient,
        get_last_fallback_event,
        get_custom_fallback_chain,
    )

    dyn = DynamicLLMClient()
    chain_labels = [f"{p}:{m}" for p, m, _ in dyn.get_fallback_chain()]
    raw_custom = get_custom_fallback_chain()

    enriched_custom = None
    if raw_custom:
        enriched_custom = []
        for item in raw_custom:
            p_id = (item.get("provider") or "").lower()
            m_id = item.get("model") or ""
            p_info = CATALOG_PROVIDERS.get(p_id)
            model_info = None
            if p_info:
                for m in p_info.models:
                    if m.id == m_id:
                        model_info = m
                        break
            enriched_custom.append({
                "provider": p_id,
                "model": m_id,
                "name": model_info.name if model_info else m_id,
                "free": model_info.free if model_info else False,
                "rate_limits": model_info.rate_limits if model_info else None,
            })

    return LLMSettingsResponse(
        active_provider=settings.llm_provider,
        active_model=_get_active_model_for_provider(settings.llm_provider),
        compatibility_mode=settings.compatibility_mode,
        providers_catalog=catalog_dict,
        api_keys_configured={
            "agnes": bool(settings.agnes_api_key),
            "groq": bool(settings.groq_api_key),
            "openrouter": bool(settings.openrouter_api_key),
            "nvidia_nim": bool(settings.nvidia_nim_api_key),
            "gemini": bool(settings.gemini_api_key),
            "ollama": True,
        },
        fallback_enabled=True,
        fallback_chain=chain_labels,
        custom_fallback_chain=enriched_custom,
        last_fallback_event=get_last_fallback_event(),
    )


@router.post(
    "/settings/llm",
    response_model=LLMSettingsResponse,
    summary="Hot-swap the active LLM provider, model, and compatibility mode",
)
async def update_llm_settings(payload: LLMUpdateRequest) -> LLMSettingsResponse:
    """Dynamically applies the chosen LLM provider and model across all screening agents."""
    prov = payload.provider.lower()
    if prov not in CATALOG_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{payload.provider}'. Valid options: {list(CATALOG_PROVIDERS.keys())}",
        )

    settings.llm_provider = prov
    settings.compatibility_mode = payload.compatibility_mode

    if prov == "agnes":
        settings.agnes_model = payload.model
        if payload.api_key:
            settings.agnes_api_key = payload.api_key.strip()
        if payload.base_url:
            settings.agnes_base_url = payload.base_url.strip()
    elif prov == "groq":
        settings.groq_model = payload.model
        if payload.api_key:
            settings.groq_api_key = payload.api_key.strip()
    elif prov == "openrouter":
        settings.openrouter_model = payload.model
        if payload.api_key:
            settings.openrouter_api_key = payload.api_key.strip()
        if payload.base_url:
            settings.openrouter_base_url = payload.base_url.strip()
    elif prov == "nvidia_nim":
        settings.nvidia_nim_model = payload.model
        if payload.api_key:
            settings.nvidia_nim_api_key = payload.api_key.strip()
        if payload.base_url:
            settings.nvidia_nim_base_url = payload.base_url.strip()
    elif prov == "gemini":
        settings.gemini_model = payload.model
        if payload.api_key:
            settings.gemini_api_key = payload.api_key.strip()
        if payload.base_url:
            settings.gemini_base_url = payload.base_url.strip()
    elif prov == "ollama":
        settings.ollama_model = payload.model
        if payload.base_url:
            settings.ollama_base_url = payload.base_url.strip()

    from backend.agents.llm_factory import clear_last_fallback_event
    clear_last_fallback_event()

    return await get_llm_settings()


@router.post(
    "/settings/llm/fallback-chain",
    response_model=LLMSettingsResponse,
    summary="Save user-defined fallback failover hierarchy",
)
async def update_fallback_chain(payload: FallbackHierarchyRequest) -> LLMSettingsResponse:
    """Configures the user's custom prioritized multi-tier fallback sequence."""
    from backend.agents.llm_factory import save_custom_fallback_chain
    clean_chain = []
    for item in payload.chain:
        p = (item.get("provider") or "").lower()
        m = item.get("model") or ""
        if p in CATALOG_PROVIDERS and m:
            clean_chain.append({"provider": p, "model": m})
    save_custom_fallback_chain(clean_chain if clean_chain else None)
    return await get_llm_settings()


@router.post(
    "/settings/llm/fallback-chain/reset",
    response_model=LLMSettingsResponse,
    summary="Reset fallback hierarchy to automatic cascading failover",
)
async def reset_fallback_chain() -> LLMSettingsResponse:
    """Restores the default automatic multi-tier failover hierarchy."""
    from backend.agents.llm_factory import save_custom_fallback_chain
    save_custom_fallback_chain(None)
    return await get_llm_settings()


@router.post(
    "/settings/llm/clear-fallback",
    summary="Clear or dismiss the last failover event metadata",
)
async def clear_fallback_endpoint() -> Dict[str, str]:
    """Dismisses the active fallback/failover warning banner."""
    from backend.agents.llm_factory import clear_last_fallback_event
    clear_last_fallback_event()
    return {"status": "ok", "message": "Fallback notification cleared."}


@router.post(
    "/settings/llm/test",
    response_model=LLMTestResponse,
    summary="Test connection and measure latency for a given provider/model (alias)",
)
async def test_llm_connection_alias(payload: LLMTestRequest) -> LLMTestResponse:
    return await test_llm_connection(payload)


@router.post(
    "/settings/test",
    response_model=LLMTestResponse,
    summary="Test connection and measure latency for a given provider/model",
)
async def test_llm_connection(payload: LLMTestRequest) -> LLMTestResponse:
    """Runs a ping inference against the selected LLM provider and model."""
    start_time = time.perf_counter()
    prov = payload.provider.lower()
    api_key = payload.api_key

    if not api_key:
        if prov == "groq":
            api_key = settings.groq_api_key
        elif prov == "openrouter":
            api_key = settings.openrouter_api_key
        elif prov == "nvidia_nim":
            api_key = settings.nvidia_nim_api_key
        elif prov == "gemini":
            api_key = settings.gemini_api_key

    try:
        client = create_llm_client(
            provider=prov,
            model=payload.model,
            api_key=api_key,
            base_url=payload.base_url,
            compatibility_mode=payload.compatibility_mode,
        )
        output = client.generate_text(
            prompt="Respond with the single word CONNECTED and nothing else.",
            temperature=0.0,
        )
        latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
        return LLMTestResponse(
            status="ok",
            provider=prov,
            model=payload.model,
            latency_ms=latency_ms,
            sample_output=output.strip() or "CONNECTED",
        )
    except Exception as err:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
        return LLMTestResponse(
            status="error",
            provider=prov,
            model=payload.model,
            latency_ms=latency_ms,
            error_message=str(err),
        )


# ---------------------------------------------------------------------------
# Token Usage & Model Performance Analytics Endpoints (Agnes AI Inspired)
# ---------------------------------------------------------------------------
@router.get(
    "/analytics/token-usage",
    response_model=TokenUsageAnalytics,
    summary="Get aggregated token usage statistics, model comparisons, and activity heatmap",
)
async def get_token_usage_analytics(
    time_range: str = Query("all", pattern="^(today|7d|30d|month|all)$")
) -> TokenUsageAnalytics:
    """Returns platform token statistics, model consumption comparisons, activity calendar, and trends."""
    from backend.services.token_tracker import token_tracker
    return token_tracker.get_analytics(time_range=time_range)


@router.post(
    "/analytics/token-usage/reset",
    summary="Reset and clear all token usage logs",
)
async def reset_token_usage_analytics() -> Dict[str, str]:
    """Clears all historical token usage logs."""
    from backend.services.token_tracker import token_tracker
    token_tracker.reset_usage_data()
    return {"status": "ok", "message": "Token usage analytics successfully reset."}



# ---------------------------------------------------------------------------
# Ollama Local Service & Model Memory Management Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/ollama/status",
    summary="Check local Ollama daemon status, installed version, and binary path",
)
async def get_ollama_status() -> Dict[str, Any]:
    """Returns whether Ollama is installed, running on port 11434, and its active version."""
    return _ollama_service.get_status()


@router.post(
    "/ollama/start",
    summary="Start the local Ollama background server daemon",
)
async def start_ollama_service() -> Dict[str, Any]:
    """Launches 'ollama serve' in background if not already running."""
    return _ollama_service.start_service()


@router.get(
    "/ollama/models",
    summary="List all installed local models and models currently loaded in RAM/VRAM",
)
async def get_ollama_models() -> Dict[str, Any]:
    """Fetches local tags from /api/tags and active in-memory models from /api/ps."""
    return {
        "installed": _ollama_service.list_installed_models(),
        "running": _ollama_service.list_running_models(),
    }


@router.post(
    "/ollama/load",
    summary="Pre-load a local Ollama model into GPU VRAM / system RAM",
)
async def load_ollama_model(payload: OllamaModelActionRequest) -> Dict[str, Any]:
    """Loads weights into memory with specified keep_alive duration."""
    return _ollama_service.load_model(model_name=payload.model, keep_alive=payload.keep_alive)


@router.post(
    "/ollama/unload",
    summary="Evict and unload an Ollama model from memory immediately",
)
async def unload_ollama_model(payload: OllamaModelActionRequest) -> Dict[str, Any]:
    """Immediately unloads model from VRAM/RAM (keep_alive=0)."""
    return _ollama_service.unload_model(model_name=payload.model)


@router.post(
    "/ollama/pull",
    summary="Pull a model from the Ollama library",
)
async def pull_ollama_model(payload: OllamaPullRequest) -> Dict[str, Any]:
    """Downloads model weights to local storage."""
    return _ollama_service.pull_model(model_name=payload.model)


# ---------------------------------------------------------------------------
# EU AI Act Annex III Compliance & Governance Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/compliance/dossier/{evaluation_id}",
    summary="Generate EU AI Act Annex III Compliance Dossier and SHA-256 Audit Seal",
)
async def get_compliance_dossier(
    evaluation_id: UUID,
    format: str = Query("json", pattern="^(json|markdown)$"),
):
    """
    Synthesizes a legally grounded, cryptographically verified EU AI Act (Regulation (EU) 2024/1689)
    Annex III technical documentation dossier and audit trail for High-Risk recruitment AI.
    """
    eval_record = await DatabaseRepository.get_evaluation(evaluation_id)
    if not eval_record:
        # Fallback to in-memory store if present
        eval_mem = _EVALUATION_STORE.get(evaluation_id)
        if not eval_mem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation {evaluation_id} not found in database.",
            )
        # Attempt to persist memory candidate and evaluation
        cand_mem = _CANDIDATE_ANONYMIZED_STORE.get(eval_mem.candidate_id) if hasattr(eval_mem, "candidate_id") else None
        raw_mem = _CANDIDATE_RAW_STORE.get(eval_mem.candidate_id) if hasattr(eval_mem, "candidate_id") else None
        if cand_mem:
            cand_record = await DatabaseRepository.get_candidate(cand_mem.candidate_id)
            if not cand_record:
                if raw_mem:
                    await DatabaseRepository.save_candidate(
                        parsed_cv=raw_mem,
                        anonymized_candidate=cand_mem,
                    )
            try:
                await DatabaseRepository.save_evaluation(
                    eval_result=eval_mem,
                    candidate_id=eval_mem.candidate_id,
                    job_id=eval_mem.job_id,
                )
            except Exception as save_err:
                logger.warning(f"Could not persist in-memory evaluation for dossier: {save_err}")
        eval_record = await DatabaseRepository.get_evaluation(evaluation_id)

    if not eval_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {evaluation_id} not found.",
        )

    cand_record = await DatabaseRepository.get_candidate(eval_record.candidate_id)
    if not cand_record:
        raw_mem = _CANDIDATE_RAW_STORE.get(UUID(eval_record.candidate_id))
        anon_mem = _CANDIDATE_ANONYMIZED_STORE.get(UUID(eval_record.candidate_id))
        if raw_mem and anon_mem:
            cand_record = await DatabaseRepository.save_candidate(
                parsed_cv=raw_mem,
                anonymized_candidate=anon_mem,
            )
    if not cand_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {eval_record.candidate_id} associated with evaluation not found.",
        )

    job_record = await DatabaseRepository.get_job(eval_record.job_id)
    if not job_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job requisition {eval_record.job_id} associated with evaluation not found.",
        )

    dossier = ComplianceService.generate_dossier(
        evaluation=eval_record,
        candidate=cand_record,
        job=job_record,
    )

    if format == "markdown":
        md_text = ComplianceService.format_markdown_certificate(dossier)
        return PlainTextResponse(
            content=md_text,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'inline; filename="EU_AI_Act_Dossier_{evaluation_id}.md"',
            },
        )

    return dossier



