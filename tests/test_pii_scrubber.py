"""
tests/test_pii_scrubber.py
Unit tests verifying deterministic PII and demographic scrubbing.
"""

from uuid import UUID
import pytest

from backend.schemas.cv import ContactInfo, ParsedCV, WorkExperience
from backend.services.pii_scrubber import PIIScrubber


def test_scrub_emails_and_phones():
    """Verify regex patterns redact email addresses and telephone numbers."""
    scrubber = PIIScrubber()
    sample = "Reach me at test.user@gmail.com or call +1 (555) 234-5678 today."
    sanitized, audit = scrubber.scrub_text(sample)

    assert "test.user@gmail.com" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized
    assert "+1 (555) 234-5678" not in sanitized
    assert "[REDACTED_PHONE]" in sanitized


def test_scrub_urls_and_social():
    """Verify URLs and LinkedIn/GitHub handles are sanitized."""
    scrubber = PIIScrubber()
    sample = "Portfolio: https://myportfolio.dev and GitHub: github.com/johndoe-coder"
    sanitized, audit = scrubber.scrub_text(sample)

    assert "https://myportfolio.dev" not in sanitized
    assert "github.com/johndoe-coder" not in sanitized


def test_scrub_candidate_name():
    """Verify candidate name is redacted using word boundary case-insensitive regex."""
    scrubber = PIIScrubber()
    sample = "Alexander Wright led the machine learning infrastructure team."
    sanitized, audit = scrubber.scrub_text(sample, candidate_name="Alexander Wright")

    assert "Alexander Wright" not in sanitized
    assert "[CANDIDATE_NAME]" in sanitized


def test_anonymize_cv_full_pipeline():
    """Verify complete ParsedCV anonymization into AnonymizedCandidate."""
    scrubber = PIIScrubber()
    parsed = ParsedCV(
        contact_info=ContactInfo(
            full_name="Sarah Connor",
            email="s.connor@cyberdyne.org",
            phone_number="555-123-4567"
        ),
        skills=["Python", "Defense Systems"],
        experiences=[
            WorkExperience(
                job_title="Security Lead",
                company_name="Resistance Ops",
                work_description=["Sarah Connor secured communications and prevented breach."],
                skills_used=["Python"]
            )
        ],
        raw_text="Sarah Connor resume: Contact s.connor@cyberdyne.org"
    )

    anonymized = scrubber.anonymize_cv(parsed)
    assert isinstance(anonymized.candidate_id, UUID)
    assert "Sarah Connor" not in anonymized.anonymized_work_experiences[0].work_description[0]
    assert "[CANDIDATE_NAME]" in anonymized.anonymized_work_experiences[0].work_description[0]
    assert "s.connor@cyberdyne.org" not in anonymized.sanitized_text
