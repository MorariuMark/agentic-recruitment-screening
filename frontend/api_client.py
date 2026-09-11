"""
frontend/api_client.py
HTTP API client for communication between Streamlit frontend and FastAPI backend.
"""

import os
import time
from typing import Any, Dict, Optional
from uuid import UUID

import httpx

from backend.schemas.interview import InterviewPlan
from backend.schemas.job import JobDescription
from backend.schemas.match import MatchEvaluationResult, Recommendation


class BackendAPIClient:
    """Client for invoking FastAPI backend endpoints from Streamlit."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        # Default to 127.0.0.1 to avoid Windows IPv6 (::1) resolution connection refusals
        self.base_url = (base_url or os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout = 300.0  # Allow up to 5 minutes for multi-requirement LLM evaluations

    def _post_with_retry(
        self,
        endpoint: str,
        files: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Executes a POST request with automatic retry on socket errors or timeouts."""
        req_timeout = timeout or self.timeout
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                with httpx.Client(base_url=self.base_url, timeout=req_timeout) as client:
                    if files:
                        res = client.post(endpoint, files=files)
                    elif json_data is not None:
                        res = client.post(endpoint, json=json_data)
                    else:
                        res = client.post(endpoint)
                    res.raise_for_status()
                    return res
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < max_retries - 1:
                    time.sleep(backoff_seconds * (attempt + 1))
                else:
                    if isinstance(e, httpx.TimeoutException):
                        raise TimeoutError(
                            f"Request to {endpoint} timed out after {req_timeout:.0f}s. "
                            f"The LLM provider took longer than expected to process all requirements."
                        ) from e
                    raise ConnectionError(
                        f"Unable to connect to FastAPI backend at {self.base_url}. "
                        f"Ensure 'start.bat' or 'python start.py' is running. Error: {e}"
                    ) from e
            except Exception as e:
                raise e
        if last_exc:
            raise last_exc
        raise RuntimeError("Unexpected retry loop exit")

    def _get_with_retry(
        self,
        endpoint: str,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Executes a GET request with automatic retry on socket errors or timeouts."""
        req_timeout = timeout or self.timeout
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                with httpx.Client(base_url=self.base_url, timeout=req_timeout) as client:
                    res = client.get(endpoint)
                    res.raise_for_status()
                    return res
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < max_retries - 1:
                    time.sleep(backoff_seconds * (attempt + 1))
                else:
                    if isinstance(e, httpx.TimeoutException):
                        raise TimeoutError(
                            f"Request to {endpoint} timed out after {req_timeout:.0f}s."
                        ) from e
                    raise ConnectionError(
                        f"Unable to connect to FastAPI backend at {self.base_url}. "
                        f"Ensure backend is running. Error: {e}"
                    ) from e
            except Exception as e:
                raise e
        if last_exc:
            raise last_exc
        raise RuntimeError("Unexpected retry loop exit")

    def health_check(self) -> Dict[str, Any]:
        """Checks if the backend API is reachable."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=3.0) as client:
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
        files = {"file": (filename, file_bytes, "application/octet-stream")}
        res = self._post_with_retry("/api/v1/cv/upload", files=files)
        return res.json()

    def parse_job_url(self, url: str) -> Dict[str, Any]:
        """
        Invokes /api/v1/job/parse-url to fetch, extract, and audit a job posting URL.
        Returns dict with job_description, missing_fields, and warnings.
        """
        payload = {"url": url.strip()}
        res = self._post_with_retry("/api/v1/job/parse-url", json_data=payload)
        return res.json()

    def parse_job_text(self, text: str) -> Dict[str, Any]:
        """
        Invokes /api/v1/job/parse-text to extract and audit raw job description text.
        Returns dict with job_description, missing_fields, and warnings.
        """
        payload = {"text": text.strip()}
        res = self._post_with_retry("/api/v1/job/parse-text", json_data=payload)
        return res.json()

    def export_candidate_cv(self, candidate_id: UUID) -> Dict[str, Any]:
        """
        Fetches the complete tagged audit JSON for a candidate via /api/v1/cv/{candidate_id}/export.
        """
        res = self._get_with_retry(f"/api/v1/cv/{str(candidate_id)}/export")
        return res.json()

    def export_job_description(self, job_description: JobDescription) -> Dict[str, Any]:
        """
        Fetches the complete tagged audit JSON for a job description via /api/v1/job/export.
        """
        payload = job_description.model_dump(mode="json")
        res = self._post_with_retry("/api/v1/job/export", json_data=payload)
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
        res = self._post_with_retry("/api/v1/match/evaluate", json_data=payload)
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
        res = self._post_with_retry("/api/v1/hitl/validate", json_data=payload)
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
        res = self._post_with_retry("/api/v1/interview/generate", json_data=payload)
        return InterviewPlan.model_validate(res.json())

    def get_llm_settings(self) -> Dict[str, Any]:
        """Fetches active LLM provider, current model, and models catalog from backend."""
        res = self._get_with_retry("/api/v1/settings/llm")
        return res.json()

    def update_llm_settings(
        self,
        provider: str,
        model: str,
        compatibility_mode: str = "auto",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Hot-swaps active LLM provider and model in backend runtime."""
        payload: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "compatibility_mode": compatibility_mode,
        }
        if api_key:
            payload["api_key"] = api_key
        if base_url:
            payload["base_url"] = base_url
        res = self._post_with_retry("/api/v1/settings/llm", json_data=payload)
        return res.json()

    def test_llm_connection(
        self,
        provider: str,
        model: str,
        compatibility_mode: str = "auto",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs a ping test against the specified provider and model."""
        payload: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "compatibility_mode": compatibility_mode,
        }
        if api_key:
            payload["api_key"] = api_key
        if base_url:
            payload["base_url"] = base_url
        res = self._post_with_retry("/api/v1/settings/test", json_data=payload, timeout=60.0)
        return res.json()

    def get_ollama_status(self) -> Dict[str, Any]:
        """Checks if local Ollama daemon is running."""
        res = self._get_with_retry("/api/v1/ollama/status")
        return res.json()

    def start_ollama_service(self) -> Dict[str, Any]:
        """Requests backend to start the local Ollama daemon process."""
        res = self._post_with_retry("/api/v1/ollama/start", timeout=15.0)
        return res.json()

    def get_ollama_models(self) -> Dict[str, Any]:
        """Fetches installed local models and models currently loaded in RAM/VRAM."""
        res = self._get_with_retry("/api/v1/ollama/models")
        return res.json()

    def load_ollama_model(self, model: str, keep_alive: str = "1h") -> Dict[str, Any]:
        """Pre-loads local Ollama model into memory (GPU VRAM / RAM)."""
        payload = {"model": model, "keep_alive": keep_alive}
        res = self._post_with_retry("/api/v1/ollama/load", json_data=payload, timeout=60.0)
        return res.json()

    def unload_ollama_model(self, model: str) -> Dict[str, Any]:
        """Unloads model weights from memory immediately."""
        payload = {"model": model}
        res = self._post_with_retry("/api/v1/ollama/unload", json_data=payload, timeout=15.0)
        return res.json()

    def pull_ollama_model(self, model: str) -> Dict[str, Any]:
        """Downloads/pulls a new model tag from the Ollama library."""
        payload = {"model": model}
        res = self._post_with_retry("/api/v1/ollama/pull", json_data=payload, timeout=300.0)
        return res.json()


