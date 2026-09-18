"""
tests/test_parser_edge_cases.py
Unit tests for CV parsing edge cases: text normalization, unicode ligatures,
soft-hyphen line unwrapping, obfuscated contacts, multi-role promotions,
multilingual dates, and scanned PDF detection.
"""

import io
import pytest
from pypdf import PdfWriter

from backend.agents.parser_agent import (
    ParserAgent,
    ScannedPDFException,
    audit_and_enrich_cv,
    normalize_extracted_text,
)
from backend.schemas.cv import ContactInfo, ParsedCV, WorkExperience, Education


def test_normalize_ligatures_and_soft_hyphens():
    """Verify that typographical ligatures, soft hyphens, and zero-width spaces are resolved."""
    raw_with_quirks = (
        "Specialized in \ufb01nance and \ufb02oating-point arithmetic. "
        "Built micro\xadcontrollers and high-e\ufb03cient systems with zero\u200bwidth bugs. "
        "Engineered reliable hardware-\nsoftware integration."
    )
    normalized = normalize_extracted_text(raw_with_quirks)
    assert "finance" in normalized
    assert "floating-point" in normalized
    assert "microcontrollers" in normalized
    assert "high-efficient" in normalized
    assert "hardwaresoftware" in normalized or "hardware-" in normalized
    assert "\xad" not in normalized
    assert "\u200b" not in normalized


def test_normalize_obfuscated_emails():
    """Verify that anti-scraping obfuscated emails are unmasked to standard mail addresses."""
    text1 = "Contact me at christian.mark [at] gmail [dot] com for opportunities."
    text2 = "Send inquiries to dev-lead (at) techcorp.org."
    
    norm1 = normalize_extracted_text(text1)
    norm2 = normalize_extracted_text(text2)
    
    assert "christian.mark@gmail.com" in norm1
    assert "dev-lead@techcorp.org" in norm2


def test_normalize_private_use_bullets():
    """Verify that private-use area and wingdings bullet symbols are converted to clean bullet points."""
    text = "\uf879Developed ESP32 drivers.\n\uf0b7Led hardware testing.\n\u25b6Implemented WebSockets."
    normalized = normalize_extracted_text(text)
    assert "• Developed ESP32 drivers." in normalized
    assert "• Led hardware testing." in normalized
    assert "• Implemented WebSockets." in normalized


def test_scanned_pdf_exception_raised_on_empty_text():
    """Verify that ScannedPDFException is raised when a PDF yields insufficient or empty text."""
    from backend.agents.parser_agent import extract_text_from_pdf

    # Generate an empty single-page PDF with no text stream
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)
    empty_pdf = pdf_bytes.getvalue()

    with pytest.raises(ScannedPDFException) as excinfo:
        extract_text_from_pdf(empty_pdf)
    assert "scanned image" in str(excinfo.value).lower()


def test_multilingual_present_and_roman_numeral_dates():
    """Verify that non-English Present tokens and Roman numeral months are normalized."""
    parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Alex Schmidt"),
        experiences=[
            WorkExperience(
                job_title="Software Entwickler",
                company_name="Siemens",
                start_date="X.2021",
                end_date="heute",
                work_description=["Entwicklung von Embedded Software."],
            ),
            WorkExperience(
                job_title="Inginer Software",
                company_name="Continental",
                start_date="03/2019",
                end_date="prezent",
                work_description=["Dezvoltare aplicatii automotive."],
            ),
        ],
        raw_text="Siemens - X.2021 - heute. Continental - 03/2019 - prezent.",
    )

    enriched = audit_and_enrich_cv(parsed, parsed.raw_text)

    # 1. Check end_date normalization
    assert enriched.experiences[0].end_date == "Present"
    assert enriched.experiences[1].end_date == "Present"

    # 2. Check Roman numeral start_date
    assert enriched.experiences[0].start_date == "10/2021"


def test_internal_promotion_detection():
    """Verify that multiple consecutive positions at the same employer are flagged as promotions."""
    parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Elena Vance"),
        experiences=[
            WorkExperience(
                job_title="Senior Platform Engineer",
                company_name="Black Mesa Tech",
                start_date="01/2022",
                end_date="Present",
                work_description=["Leading distributed computing cluster."],
            ),
            WorkExperience(
                job_title="Platform Engineer",
                company_name="Black Mesa Tech",
                start_date="06/2019",
                end_date="12/2021",
                work_description=["Maintained core backend microservices."],
            ),
            WorkExperience(
                job_title="Junior Developer",
                company_name="Aperture Labs",
                start_date="01/2018",
                end_date="05/2019",
                work_description=["Built test fixtures."],
            ),
        ],
        raw_text="Work history at Black Mesa Tech and Aperture Labs.",
    )

    enriched = audit_and_enrich_cv(parsed, parsed.raw_text)

    assert enriched.experiences[0].is_promotion is False
    assert enriched.experiences[1].is_promotion is True
    assert enriched.experiences[2].is_promotion is False


def test_contact_handles_unmasking():
    """Verify that raw social handles (e.g. GitHub: @user, LinkedIn: /in/user) are converted into valid URLs."""
    raw_text = """
    Jane Developer
    Email: jane.dev [at] engineering [dot] io
    GitHub: @janedev
    LinkedIn: /in/jane-dev-official
    """

    parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Jane Developer"),
        raw_text=raw_text,
    )

    enriched = audit_and_enrich_cv(parsed, raw_text)

    assert enriched.contact_info.email == "jane.dev@engineering.io"
    assert enriched.contact_info.github_url == "https://github.com/janedev"
    assert enriched.contact_info.linkedin_url == "https://linkedin.com/in/jane-dev-official"
