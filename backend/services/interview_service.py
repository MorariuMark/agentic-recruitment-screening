"""
backend/services/interview_service.py
Shared application service enforcing case identity validation and recruiter approval policy (E9).
"""

from typing import Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status

from backend.schemas.interview import InterviewPlan
from backend.schemas.job import JobDescription
from backend.schemas.match import MatchEvaluationResult


class InterviewValidationService:
    """Shared gate enforcing case identity and progression approval policy."""

    @staticmethod
    def validate_case_identity(
        candidate_id: UUID,
        job_id: UUID,
        evaluation: MatchEvaluationResult,
    ) -> None:
        """
        Verify that evaluation belongs to the specified candidate and job.
        Prevents mismatched candidate/job/evaluation combinations.
        """
        if str(evaluation.candidate_id) != str(candidate_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Case identity mismatch: evaluation candidate {evaluation.candidate_id} does not match {candidate_id}.",
            )
        if str(evaluation.job_id) != str(job_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Case identity mismatch: evaluation job {evaluation.job_id} does not match {job_id}.",
            )

    @staticmethod
    def check_progression_approval(
        evaluation: Optional[MatchEvaluationResult],
        require_approval: bool = True,
    ) -> Tuple[bool, bool]:
        """
        Check if candidate has received human recruiter approval.
        Returns (is_draft, hitl_approved).
        If require_approval is True and candidate is not approved, raises 409.
        """
        if evaluation and evaluation.hitl_validated and getattr(evaluation, "recruiter_decision", None) == "strong_match" and evaluation.recommendation == "strong_match":
            return False, True

        if require_approval:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A recruiter must validate and approve this candidate for interview progression first.",
            )

        # Allow unapproved draft generation with explicit draft marking
        return True, False
