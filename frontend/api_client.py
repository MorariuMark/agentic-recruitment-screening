"""
frontend/api_client.py
HTTP API client for communication between Streamlit frontend and FastAPI backend.
"""

from typing import Any, Dict, Optional
from uuid import UUID

import httpx

from backend.schemas.interview import InterviewPlan
from backend.schemas.job import JobDescription
from backend.schemas.match import MatchEvaluationResult, Recommendation


class BackendAPIClient:
    """Client for invoking FastAPI backend endpoints from Streamlit."""

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = 120.0  # LLM inferences and embeddings may take time

    def health_check(self) -> Dict[str, Any]:
        """Checks if the backend API is reachable."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=5.0) as client:
                res = client.get("/health")
                res.raise_for_status()
                return res.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    def upload_cv(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Uploads a candidate CV file to /api/v1/cv/upload.
        Returns parsed CV, anonymized candidate profile, and chunk count.
        """
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            files = {"file": (filename, file_bytes, "application/octet-stream")}
            res = client.post("/api/v1/cv/upload", files=files)
            res.raise_for_status()
            return res.json()

    def evaluate_match(
        self,
        candidate_id: UUID,
        job_description: JobDescription,
    ) -> MatchEvaluationResult:
        """
        Evaluates an indexed candidate against job criteria via /api/v1/match/evaluate.
        """
        payload = {
            "candidate_id": str(candidate_id),
            "job_description": job_description.model_dump(mode="json"),
        }
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            res = client.post("/api/v1/match/evaluate", json=payload)
            res.raise_for_status()
            return MatchEvaluationResult.model_validate(res.json())

    def submit_hitl_decision(
        self,
        evaluation_id: UUID,
        recruiter_decision: Recommendation,
        recruiter_notes: str,
    ) -> MatchEvaluationResult:
        """
        Submits human recruiter validation / override to /api/v1/hitl/validate.
        """
        payload = {
            "evaluation_id": str(evaluation_id),
            "recruiter_decision": recruiter_decision.value,
            "recruiter_notes": recruiter_notes,
        }
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            res = client.post("/api/v1/hitl/validate", json=payload)
            res.raise_for_status()
            return MatchEvaluationResult.model_validate(res.json())

    def generate_interview_plan(
        self,
        candidate_id: UUID,
        evaluation_id: UUID,
        job_description: JobDescription,
        target_minutes: int = 45,
    ) -> InterviewPlan:
        """
        Synthesizes a tailored interview guide via /api/v1/interview/generate.
        """
        payload = {
            "candidate_id": str(candidate_id),
            "evaluation_id": str(evaluation_id),
            "job_description": job_description.model_dump(mode="json"),
            "target_duration_minutes": target_minutes,
        }
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            res = client.post("/api/v1/interview/generate", json=payload)
            res.raise_for_status()
            return InterviewPlan.model_validate(res.json())
