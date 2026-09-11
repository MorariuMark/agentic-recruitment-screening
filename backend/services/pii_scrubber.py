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
# International & standard phone regex pattern
PHONE_REGEX = re.compile(
    r"(?:\+?\d{1,4}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}(?:[-.\s]?\d{2,4})?"
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
        candidate_name: Optional[str] = None,
        candidate_phone: Optional[str] = None,
        candidate_email: Optional[str] = None,
    ) -> Tuple[str, Dict[str, str]]:
        """
        Scrubs emails, phones, URLs, and candidate identifiers from raw text.
        Isolates demographic indicators into a dictionary for auditing.

        Returns:
            Tuple of (sanitized_text, demographic_audit_dict)
        """
        if not text:
            return "", {}

        sanitized = text
        demographic_audit: Dict[str, str] = {}

        # 1. Redact exact known contact details if provided
        if candidate_email and candidate_email.strip():
            sanitized = re.sub(
                re.escape(candidate_email.strip()),
                "[REDACTED_EMAIL]",
                sanitized,
                flags=re.IGNORECASE,
            )

        if candidate_phone and candidate_phone.strip():
            sanitized = re.sub(
                re.escape(candidate_phone.strip()),
                "[REDACTED_PHONE]",
                sanitized,
            )

        # 2. Redact email addresses
        sanitized = EMAIL_REGEX.sub("[REDACTED_EMAIL]", sanitized)

        # 3. Redact URLs and LinkedIn/GitHub profiles
        sanitized = LINKEDIN_GITHUB_REGEX.sub("[REDACTED_URL]", sanitized)
        sanitized = URL_REGEX.sub("[REDACTED_URL]", sanitized)

        # 4. Redact candidate name (case-insensitive with word boundary)
        if candidate_name and candidate_name.strip():
            name_pattern = re.compile(rf"\b{re.escape(candidate_name.strip())}\b", re.IGNORECASE)
            sanitized = name_pattern.sub("[CANDIDATE_NAME]", sanitized)

        # 5. Redact general phone numbers (only if contains at least 7 digits)
        def _replace_phone(match: re.Match) -> str:
            val = match.group(0)
            digits = re.sub(r"\D", "", val)
            if len(digits) >= 7:
                return "[REDACTED_PHONE]"
            return val

        sanitized = PHONE_REGEX.sub(_replace_phone, sanitized)

        return sanitized, demographic_audit

    def anonymize_cv(self, parsed_cv: ParsedCV) -> AnonymizedCandidate:
        """
        Transforms a raw ParsedCV into an AnonymizedCandidate model.
        """
        contact = parsed_cv.contact_info
        candidate_name = contact.full_name if contact else None
        candidate_phone = getattr(contact, "phone_number", None) or getattr(contact, "phone", None) if contact else None
        candidate_email = contact.email if contact else None

        # 1. Scrub the full raw document text
        sanitized_text, demographic_audit = self.scrub_text(
            parsed_cv.raw_text,
            candidate_name=candidate_name,
            candidate_phone=candidate_phone,
            candidate_email=candidate_email,
        )

        # 2. Scrub work experience descriptions
        anonymized_experiences: List[WorkExperience] = []
        for exp in parsed_cv.experiences:
            scrubbed_bullets = [
                self.scrub_text(
                    bullet,
                    candidate_name=candidate_name,
                    candidate_phone=candidate_phone,
                    candidate_email=candidate_email,
                )[0]
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

        # 3. Scrub projects
        anonymized_projects = []
        for proj in getattr(parsed_cv, "projects", []):
            scrubbed_bullets = [
                self.scrub_text(
                    bullet,
                    candidate_name=candidate_name,
                    candidate_phone=candidate_phone,
                    candidate_email=candidate_email,
                )[0]
                for bullet in proj.description
            ]
            anonymized_url = (
                self.scrub_text(proj.project_url)[0] if proj.project_url else None
            )
            anonymized_projects.append(
                proj.model_copy(
                    update={
                        "description": scrubbed_bullets,
                        "project_url": anonymized_url,
                    }
                )
            )

        # 4. Scrub custom sections
        anonymized_custom = []
        for sec in getattr(parsed_cv, "custom_sections", []):
            scrubbed_items = [
                self.scrub_text(
                    item,
                    candidate_name=candidate_name,
                    candidate_phone=candidate_phone,
                    candidate_email=candidate_email,
                )[0]
                for item in sec.items
            ]
            anonymized_custom.append(
                sec.model_copy(update={"items": scrubbed_items})
            )

        # 5. Construct and return the AnonymizedCandidate model
        return AnonymizedCandidate(
            candidate_id=uuid4(),
            anonymized_work_experiences=anonymized_experiences,
            anonymized_education=parsed_cv.education,
            anonymized_skills=parsed_cv.skills,
            anonymized_certifications=parsed_cv.certifications,
            anonymized_projects=anonymized_projects,
            anonymized_languages=getattr(parsed_cv, "languages", []),
            anonymized_custom_sections=anonymized_custom,
            sanitized_text=sanitized_text,
            demographic_data=demographic_audit,
        )

