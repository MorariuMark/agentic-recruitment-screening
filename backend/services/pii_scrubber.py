"""
backend/services/pii_scrubber.py
Deterministic PII scrubbing, demographic de-biasing, and candidate anonymization engine.
"""

import re
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from backend.schemas.cv import AnonymizedCandidate, ParsedCV, WorkExperience, Education


# Pre-compiled high-performance regex patterns for deterministic scrubbing
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(
    r"(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(\s*([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9])\s*\)|([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9]))\s*(?:[.-]\s*)?)?([2-9]1[02-9]|[2-9][02-9]1|[2-9][02-9]{2})\s*(?:[.-]\s*)?([0-9]{4})(?:\s*(?:#|x\.?|ext\.?|extension)\s*(\d+))?"
)
URL_REGEX = re.compile(r"https?://(?:www\.)?[a-zA-Z0-9./\-_#]+")
LINKEDIN_GITHUB_REGEX = re.compile(r"(?:linkedin\.com/in/|github\.com/)[a-zA-Z0-9_\-]+", re.IGNORECASE)


class PIIScrubber:
    """Service responsible for scrubbing PII and isolating demographic factors."""

    def __init__(self) -> None:
        pass

    def scrub_text(
        self,
        text: str,
        candidate_name: Optional[str] = None
    ) -> Tuple[str, Dict[str, str]]:
        """
        Scrubs emails, phones, URLs, and the candidate name from raw text.
        Isolates demographic indicators into a dictionary for auditing.

        Returns:
            Tuple of (sanitized_text, demographic_audit_dict)
        """
        if not text:
            return "", {}

        sanitized = text
        demographic_audit: Dict[str, str] = {}

        # 1. Redact email addresses
        sanitized = EMAIL_REGEX.sub("[REDACTED_EMAIL]", sanitized)

        # 2. Redact URLs and LinkedIn/GitHub profiles
        sanitized = LINKEDIN_GITHUB_REGEX.sub("[REDACTED_URL]", sanitized)
        sanitized = URL_REGEX.sub("[REDACTED_URL]", sanitized)

        # 3. Redact phone numbers
        sanitized = PHONE_REGEX.sub("[REDACTED_PHONE]", sanitized)

        # 4. Redact candidate name (case-insensitive with word boundary)
        if candidate_name and candidate_name.strip():
            name_pattern = re.compile(rf"\b{re.escape(candidate_name.strip())}\b", re.IGNORECASE)
            sanitized = name_pattern.sub("[CANDIDATE_NAME]", sanitized)

        return sanitized, demographic_audit

    def anonymize_cv(self, parsed_cv: ParsedCV) -> AnonymizedCandidate:
        """
        Transforms a raw ParsedCV into an AnonymizedCandidate model.
        """
        candidate_name = parsed_cv.contact_info.full_name if parsed_cv.contact_info else None

        # 1. Scrub the full raw document text
        sanitized_text, demographic_audit = self.scrub_text(
            parsed_cv.raw_text, candidate_name=candidate_name
        )

        # 2. Scrub work experience descriptions
        anonymized_experiences: List[WorkExperience] = []
        for exp in parsed_cv.experiences:
            scrubbed_bullets = [
                self.scrub_text(bullet, candidate_name=candidate_name)[0]
                for bullet in exp.work_description
            ]
            anonymized_experiences.append(
                WorkExperience(
                    job_title=exp.job_title,
                    company_name=exp.company_name,
                    start_date=exp.start_date,
                    end_date=exp.end_date,
                    duration_months=exp.duration_months,
                    work_description=scrubbed_bullets,
                    skills_used=exp.skills_used,
                )
            )

        # 3. Construct and return the AnonymizedCandidate model
        return AnonymizedCandidate(
            candidate_id=uuid4(),
            anonymized_work_experiences=anonymized_experiences,
            anonymized_education=parsed_cv.education,
            anonymized_skills=parsed_cv.skills,
            anonymized_certifications=parsed_cv.certifications,
            sanitized_text=sanitized_text,
            demographic_data=demographic_audit,
        )
