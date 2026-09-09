"""
backend/api/routes.py
FastAPI REST routes for CV ingestion, JD evaluation, semantic matching,
Human-in-the-Loop (HITL) recruiter validation, and tailored interview guide generation.
"""

from typing import Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from backend.agents.interview_agent import InterviewAgent
from backend.agents.matching_agent import MatchingAgent
from backend.agents.parser_agent import ParserAgent
from backend.schemas.cv import AnonymizedCandidate, ParsedCV
from backend.schemas.interview import InterviewPlan
from backend.schemas.job import JobDescription
from backend.schemas.match import MatchEvaluationResult, Recommendation
from backend.services.scoring_engine import ScoringEngine
from backend.services.vector_store import VectorStoreService

router = APIRouter(prefix="/api/v1", tags=["Recruitment Screening"])

# ---------------------------------------------------------------------------
# In-Memory Datastores (State cache for candidate sessions and evaluations)
# ---------------------------------------------------------------------------
_CANDIDATE_RAW_STORE: Dict[UUID, ParsedCV] = {}
_CANDIDATE_ANONYMIZED_STORE: Dict[UUID, AnonymizedCandidate] = {}
_EVALUATION_STORE: Dict[UUID, MatchEvaluationResult] = {}
_INTERVIEW_PLAN_STORE: Dict[UUID, InterviewPlan] = {}

# Reusable service instances
_parser_agent = ParserAgent()
_vector_store = VectorStoreService()
_scoring_engine = ScoringEngine()
_matching_agent = MatchingAgent(vector_store=_vector_store, scoring_engine=_scoring_engine)
_interview_agent = InterviewAgent()


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------
class CVUploadResponse(BaseModel):
    """Response returned upon parsing and anonymizing a candidate CV."""
    candidate_id: UUID = Field(description="Unique anonymized candidate ID")
    parsed_cv: ParsedCV = Field(description="Structured CV representation")
    anonymized_candidate: AnonymizedCandidate = Field(description="PII-scrubbed candidate profile")
    chunks_indexed: int = Field(description="Count of semantic chunks stored in ChromaDB")


class MatchEvaluateRequest(BaseModel):
    """Request payload to evaluate an indexed candidate against a job description."""
    candidate_id: UUID = Field(description="UUID of previously uploaded candidate")
    job_description: JobDescription = Field(description="Job description and atomic criteria")


class HITLValidationRequest(BaseModel):
    """Request payload for the recruiter Human-in-the-Loop decision gate."""
    evaluation_id: UUID = Field(description="UUID of the MatchEvaluationResult")
    recruiter_decision: Recommendation = Field(description="Final recruiter decision tier")
    recruiter_notes: str = Field(description="Auditable justification for the decision or override")


class InterviewGenerateRequest(BaseModel):
    """Request payload to synthesize a tailored interview plan."""
    candidate_id: UUID = Field(description="UUID of candidate")
    evaluation_id: UUID = Field(description="UUID of evaluation report")
    job_description: JobDescription = Field(description="Job description being interviewed for")
    target_duration_minutes: int = Field(default=45, ge=15, le=120, description="Target interview length")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
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
        parsed_cv, anonymized_candidate = _parser_agent.parse_and_anonymize(
            source=content_bytes,
            filename=file.filename,
        )

        # 2. Index candidate chunks into ChromaDB for asymmetric RAG matching
        chunks_indexed = _vector_store.index_candidate(anonymized_candidate)

        # 3. Cache instances in memory
        cid = anonymized_candidate.candidate_id
        _CANDIDATE_RAW_STORE[cid] = parsed_cv
        _CANDIDATE_ANONYMIZED_STORE[cid] = anonymized_candidate

        return CVUploadResponse(
            candidate_id=cid,
            parsed_cv=parsed_cv,
            anonymized_candidate=anonymized_candidate,
            chunks_indexed=chunks_indexed,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing candidate CV: {str(e)}",
        )


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
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {request.candidate_id} not found. Please upload the CV first.",
        )

    try:
        # Run matching agent pipeline
        result = _matching_agent.match_candidate(
            candidate=candidate,
            job_description=request.job_description,
        )

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
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {request.evaluation_id} not found.",
        )

    # Apply recruiter decision and audit log
    evaluation.recommendation = request.recruiter_decision
    evaluation.recruiter_notes = request.recruiter_notes
    evaluation.hitl_validated = True

    _EVALUATION_STORE[request.evaluation_id] = evaluation
    return evaluation


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {request.candidate_id} not found.",
        )

    evaluation = _EVALUATION_STORE.get(request.evaluation_id)
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {request.evaluation_id} not found.",
        )

    try:
        plan = _interview_agent.generate_interview_plan(
            candidate=candidate,
            job_description=request.job_description,
            evaluation_result=evaluation,
            target_minutes=request.target_duration_minutes,
        )

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
    """Fetches a cached evaluation report."""
    evaluation = _EVALUATION_STORE.get(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found.")
    return evaluation
