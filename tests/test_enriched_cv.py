"""
tests/test_enriched_cv.py
Unit tests verifying comprehensive CV parser and profile enrichment:
- PDF embedded hyperlinks
- Academic specifics (GPA, honors, thesis, location)
- Work experience trajectory (employment type, work model, location)
- Logistics & availability (notice period, work authorization, relocation)
- Research publications & patents
- ChromaDB indexing and audit export
"""

from uuid import uuid4
import pytest

from backend.agents.parser_agent import ParserAgent, audit_and_enrich_cv
from backend.schemas.cv import (
    ContactInfo,
    CustomSection,
    Education,
    LanguageSkill,
    LogisticalInfo,
    ParsedCV,
    Patent,
    Publication,
    WorkExperience,
)
from backend.services.audit_exporter import AuditExporter
from backend.services.pii_scrubber import PIIScrubber
from backend.services.vector_store import VectorStoreService


def test_audit_and_enrich_full_spectrum():
    """Verify deterministic enrichment across academic, experience, logistics, and research."""
    raw_text = """
Jane Doe
Work permit: EU Citizen
Date of birth: 15/05/1998 Place of birth: Cluj, Romania Gender: Female
Email: jane.doe@example.com Phone: +40 712 345 678
Notice period: 1 month notice
Relocation: Open to European Union relocation
Willingness to travel: Up to 20%
Expected salary: €75,000 / year

EDUCATION AND TRAINING
Faculty of Automation and Computers
Politehnica University [ 2017 – 2021 ]
City: Cluj-Napoca | Country: Romania
Grade: 9.90/10
Honors: Summa Cum Laude
Diploma Thesis: Distributed Consensus in Low-Latency Mesh Networks
Exchange Semester: Erasmus+ at Technical University of Munich

WORK EXPERIENCE
Apex Robotics - Cluj-Napoca, Romania
Software Engineer Summer Practice
[ 01/07/2020 – 30/09/2020 ]
• Developed control algorithms for robotic arms.

Freelance Consulting - Remote
Senior AI Contractor
[ 01/01/2022 – Current ]
• Delivered 20+ computer vision solutions remotely.

LANGUAGE SKILLS
Mother tongue(s): Romanian
Other language(s):
English German
LISTENING C2 READING C2 WRITING C1 LISTENING B2 READING B2 WRITING B1
SPOKEN PRODUCTION C2 SPOKEN INTERACTION C2 SPOKEN PRODUCTION B2 SPOKEN INTERACTION B2
Levels: A1 and A2: Basic user; B1 and B2: Independent user; C1 and C2: Proficient user

DRIVING LICENCE
Driving Licence: B

PUBLICATIONS
• J. Doe, "Efficient Low-Latency Edge Vision", IEEE Robotics and Automation Letters, 2023. DOI: 10.1109/LRA.2023.123456

PATENTS
• Fast Neural Inference on Asynchronous Microcontrollers. USPTO Patent 11223344, Granted.
"""

    parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Jane Doe", email="jane.doe@example.com"),
        education=[
            Education(
                degree_title="Bachelor of Computer Science",
                institution_name="Politehnica University",
                graduation_year=2021,
            )
        ],
        experiences=[
            WorkExperience(
                job_title="Software Engineer Summer Practice",
                company_name="Apex Robotics",
                work_description=["Developed control algorithms for robotic arms."],
            ),
            WorkExperience(
                job_title="Senior AI Contractor",
                company_name="Freelance Consulting",
                work_description=["Delivered 20+ computer vision solutions remotely."],
            ),
        ],
        custom_sections=[
            CustomSection(
                section_title="Publications",
                items=['• J. Doe, "Efficient Low-Latency Edge Vision", IEEE Robotics and Automation Letters, 2023. DOI: 10.1109/LRA.2023.123456'],
            ),
            CustomSection(
                section_title="Patents",
                items=["• Fast Neural Inference on Asynchronous Microcontrollers. USPTO Patent 11223344, Granted."],
            ),
        ],
        raw_text=raw_text,
    )

    enriched = audit_and_enrich_cv(parsed, raw_text)

    # 1. Academic specifics
    edu = enriched.education[0]
    assert edu.gpa_or_grade == "9.90/10"
    assert edu.honors == "Summa Cum Laude"
    assert "Distributed Consensus" in (edu.thesis_title or "")
    assert "Cluj-Napoca, Romania" in (edu.location or "")
    assert "Erasmus+" in (edu.exchange_program or "")

    # 2. Work Experience nuances
    exp1 = enriched.experiences[0]
    assert exp1.employment_type == "Summer Practice"
    assert "Cluj-Napoca" in (exp1.location or "")

    exp2 = enriched.experiences[1]
    assert exp2.employment_type == "Freelance"
    assert exp2.work_model == "Remote"

    # 3. Logistics
    assert enriched.logistics is not None
    assert "1 month notice" in enriched.logistics.notice_period
    assert "EU Citizen" in enriched.logistics.work_authorization
    assert "European Union" in enriched.logistics.relocation_preference

    # 4. Publications & Patents
    assert len(enriched.publications) >= 1
    assert "Edge Vision" in enriched.publications[0].title
    assert len(enriched.patents) >= 1
    assert enriched.patents[0].status == "Granted"

    # 5. Languages & Certifications
    lang_map = {l.language.lower(): l.proficiency for l in enriched.languages}
    assert lang_map.get("romanian") == "Native"
    assert lang_map.get("english") == "C2"
    assert lang_map.get("german") == "B2"
    assert any("Driving Licence: B" in c for c in enriched.certifications)


def test_enriched_vector_store_indexing(tmp_path):
    """Verify that enriched education, logistics, publications, and patents are indexed into ChromaDB."""
    vstore = VectorStoreService(persist_directory=str(tmp_path / "chroma_enriched"))
    scrubber = PIIScrubber()

    parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Alex Smith", email="alex@example.com"),
        education=[
            Education(
                degree_title="Master of AI",
                institution_name="Stanford University",
                graduation_year=2024,
                gpa_or_grade="3.95/4.0",
                honors="With Distinction",
                thesis_title="Transformers on Edge Devices",
            )
        ],
        experiences=[
            WorkExperience(
                job_title="Lead ML Engineer",
                company_name="TechCorp",
                work_description=["Deployed transformer models on microcontrollers."],
                location="San Francisco, CA",
                work_model="Hybrid",
                employment_type="Full-time",
            )
        ],
        publications=[
            Publication(
                title="Ultra-light Transformers",
                journal_or_conference="NeurIPS",
                year=2024,
                doi_or_url="https://doi.org/10.1234/5678",
            )
        ],
        patents=[
            Patent(
                title="Asynchronous Quantization Method",
                patent_number="US9988776",
                patent_office="USPTO",
                status="Granted",
            )
        ],
        logistics=LogisticalInfo(
            notice_period="Immediate availability",
            work_authorization="US Citizen",
            relocation_preference="No Relocation",
        ),
        certifications=["AWS Certified Machine Learning - Specialty"],
        languages=[LanguageSkill(language="English", proficiency="Native")],
    )

    anonymized = scrubber.anonymize_cv(parsed)
    chunks_count = vstore.index_candidate(anonymized)
    assert chunks_count >= 6

    # Verify retrieval for GPA / thesis query
    edu_chunks = vstore.query_candidate_chunks(anonymized.candidate_id, "Master degree with high GPA", n_results=3)
    assert any("3.95/4.0" in c["text"] for c in edu_chunks)

    # Verify retrieval for publication query
    pub_chunks = vstore.query_candidate_chunks(anonymized.candidate_id, "NeurIPS paper research", n_results=3)
    assert any("Ultra-light Transformers" in c["text"] for c in pub_chunks)

    # Verify retrieval for availability query
    log_chunks = vstore.query_candidate_chunks(anonymized.candidate_id, "Immediate availability notice period", n_results=3)
    assert any("Immediate availability" in c["text"] for c in log_chunks)


def test_enriched_audit_export():
    """Verify that AuditExporter includes tagged items for logistics, publications, and patents."""
    cid = uuid4()
    parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Morgan Reed", email="morgan@example.com"),
        publications=[Publication(title="Novel Graph Neural Networks", year=2023)],
        patents=[Patent(title="Neuromorphic Circuit Design", patent_number="EP123456")],
        logistics=LogisticalInfo(notice_period="2 weeks", work_authorization="EU Passport"),
    )
    scrubber = PIIScrubber()
    anonymized = scrubber.anonymize_cv(parsed)
    anonymized.candidate_id = cid

    export = AuditExporter.build_cv_tagged_export(parsed, anonymized, chunks_count=10)
    field_names = [it.field_name for it in export.items]

    assert "publications" in field_names
    assert "patents" in field_names
    assert "logistics" in field_names

    pub_item = next(it for it in export.items if it.field_name == "publications")
    assert pub_item.status.value == "visible"
    assert len(pub_item.value) == 1
    assert pub_item.value[0]["title"] == "Novel Graph Neural Networks"