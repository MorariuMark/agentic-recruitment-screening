"""Consistent JD import errors for recruiter drafts and Admin imports."""
import logging
import math
from uuid import uuid4

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from backend.agents.llm_factory import LLMProvidersCoolingDownError, StructuredOutputTruncatedError
from backend.services.url_errors import URLResolutionError

logger = logging.getLogger("recruitment_screening.job_import")


def job_parse_http_error(error: Exception) -> HTTPException:
    if isinstance(error, HTTPException):
        return error
    reference = uuid4().hex[:12]
    logger.exception("JD extraction failed (reference %s)", reference)
    suffix = f" Reference: {reference}."
    if isinstance(error, URLResolutionError):
        return HTTPException(503, str(error) + suffix, headers={"Retry-After": "2"})
    if isinstance(error, LLMProvidersCoolingDownError):
        retry_after = math.ceil(error.retry_after)
        return HTTPException(503, f"The configured AI providers are temporarily unavailable or rate-limited. Retry in {retry_after} seconds." + suffix,
                             headers={"Retry-After": str(retry_after)})
    if isinstance(error, (StructuredOutputTruncatedError, ValidationError)):
        return HTTPException(502, "The AI provider returned an incomplete or invalid job description. Retry with a larger output budget or another configured model." + suffix)
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return HTTPException(504, "Job extraction timed out while contacting an external service. Retry, or paste the job description directly if importing a URL." + suffix)
    if isinstance(error, httpx.HTTPError):
        return HTTPException(502, "The job page could not be retrieved. Check the URL or paste the job description directly." + suffix)
    if isinstance(error, ValueError):
        return HTTPException(400, str(error))
    if isinstance(error, RuntimeError):
        return HTTPException(502, "The configured AI providers could not complete job extraction. Check model availability and output limits, then retry." + suffix)
    return HTTPException(500, "Job extraction failed unexpectedly. The server log contains the diagnostic details." + suffix)
