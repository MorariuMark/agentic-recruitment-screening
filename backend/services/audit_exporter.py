"""
backend/services/audit_exporter.py
Service for exporting parsed CV and Job Description data into comprehensive,
annotated JSON files with provenance and usage tags: anonymised, visible, unused, and extra.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from backend.schemas.cv import (
    AnonymizedCandidate,
    CVTaggedExport,
    DetailStatus,
    ParsedCV,
    TaggedDetailItem,
)
from backend.schemas.job import (
    JDTaggedExport,
    JobDescription,
    RequirementCategory,
)


class AuditExporter:
    """Generates standardized, tagged JSON export structures for CVs and Job Descriptions."""

    @staticmethod
    def build_cv_tagged_export(
        parsed_cv: ParsedCV,
        anonymized_candidate: AnonymizedCandidate,
        chunks_count: int = 0,
    ) -> CVTaggedExport:
        """
        Builds a comprehensive tagged JSON representation of a parsed & scrubbed candidate CV.
        Every field is tagged as:
          - anonymised: scrubbed/redacted PII or demographic indicators
          - visible: extracted qualifications actively passed to the matching engine
          - unused: text/sections present in CV but not used for technical evaluation
          - extra: synthetic or system-generated metadata
        """
        items: List[TaggedDetailItem] = []
        contact = parsed_cv.contact_info

        # --- 1. ANONYMISED: Scrubbed PII & Demographics ---
        if contact:
            items.append(
                TaggedDetailItem(
                    field_name="full_name",
                    category="contact_info",
                    status=DetailStatus.ANONYMISED,
                    raw_value=contact.full_name,
                    value="[CANDIDATE_NAME]",
                    notes="Candidate name redacted by PII scrubber to prevent demographic bias",
                )
            )
            items.append(
                TaggedDetailItem(
                    field_name="email",
                    category="contact_info",
                    status=DetailStatus.ANONYMISED,
                    raw_value=contact.email,
                    value="[REDACTED_EMAIL]" if contact.email else None,
                    notes="Direct email address redacted",
                )
            )
            items.append(
                TaggedDetailItem(
                    field_name="phone_number",
                    category="contact_info",
                    status=DetailStatus.ANONYMISED,
                    raw_value=contact.phone_number or contact.phone,
                    value="[REDACTED_PHONE]" if (contact.phone_number or contact.phone) else None,
                    notes="Telephone contact redacted",
                )
            )
            items.append(
                TaggedDetailItem(
                    field_name="location",
                    category="contact_info",
                    status=DetailStatus.ANONYMISED,
                    raw_value=contact.location,
                    value="[REDACTED_LOCATION]" if contact.location else None,
                    notes="Geographic location isolated from screening engine",
                )
            )
            items.append(
                TaggedDetailItem(
                    field_name="linkedin_url",
                    category="contact_info",
                    status=DetailStatus.ANONYMISED,
                    raw_value=contact.linkedin_url,
                    value="[REDACTED_URL]" if contact.linkedin_url else None,
                    notes="Personal social URL redacted",
                )
            )
            items.append(
                TaggedDetailItem(
                    field_name="github_url",
                    category="contact_info",
                    status=DetailStatus.ANONYMISED,
                    raw_value=contact.github_url,
                    value="[REDACTED_URL]" if contact.github_url else None,
                    notes="Portfolio/GitHub URL redacted",
                )
            )

        items.append(
            TaggedDetailItem(
                field_name="demographic_data",
                category="demographics",
                status=DetailStatus.ANONYMISED,
                value=anonymized_candidate.demographic_data or {},
                notes="Protected demographic attributes isolated strictly for audit, never passed to matching LLM",
            )
        )

        # --- 2. VISIBLE: Extracted Qualifications Used in Matching ---
        items.append(
            TaggedDetailItem(
                field_name="skills",
                category="skills",
                status=DetailStatus.VISIBLE,
                value=anonymized_candidate.anonymized_skills,
                notes="Extracted technical and professional skills indexed in ChromaDB for dense retrieval",
            )
        )
        items.append(
            TaggedDetailItem(
                field_name="work_experiences",
                category="experience",
                status=DetailStatus.VISIBLE,
                value=[exp.model_dump() for exp in anonymized_candidate.anonymized_work_experiences],
                notes="Sanitized work history bullet points evaluated by LLM against job requirements",
            )
        )
        items.append(
            TaggedDetailItem(
                field_name="education",
                category="education",
                status=DetailStatus.VISIBLE,
                value=[edu.model_dump() for edu in anonymized_candidate.anonymized_education],
                notes="Degrees, institutions, and graduation years evaluated for minimum criteria",
            )
        )
        items.append(
            TaggedDetailItem(
                field_name="certifications",
                category="certifications",
                status=DetailStatus.VISIBLE,
                value=anonymized_candidate.anonymized_certifications,
                notes="Professional certifications and licenses evaluated for qualifications",
            )
        )
        if parsed_cv.summary:
            items.append(
                TaggedDetailItem(
                    field_name="summary",
                    category="overview",
                    status=DetailStatus.VISIBLE,
                    value=parsed_cv.summary,
                    notes="Candidate executive summary / bio evaluated for role alignment",
                )
            )

        # Projects
        items.append(
            TaggedDetailItem(
                field_name="projects",
                category="projects",
                status=DetailStatus.VISIBLE,
                value=[proj.model_dump() for proj in getattr(anonymized_candidate, "anonymized_projects", [])],
                notes="Technical, open-source, or academic projects evaluated for hands-on experience and skills",
            )
        )

        # Languages
        items.append(
            TaggedDetailItem(
                field_name="languages",
                category="languages",
                status=DetailStatus.VISIBLE,
                value=[lang.model_dump() for lang in getattr(anonymized_candidate, "anonymized_languages", [])],
                notes="Candidate language competencies evaluated against role communication requirements",
            )
        )

        # Custom Fallback Sections
        custom_items = getattr(anonymized_candidate, "anonymized_custom_sections", [])
        if custom_items:
            items.append(
                TaggedDetailItem(
                    field_name="custom_sections",
                    category="custom_sections",
                    status=DetailStatus.VISIBLE,
                    value=[sec.model_dump() for sec in custom_items],
                    notes="Fallback relevant sections (e.g. volunteering, awards, publications, hackathons) evaluated for additional qualifications",
                )
            )

        # --- 3. UNUSED: Present in CV but Not Used in Technical Evaluation ---
        unused_list = list(parsed_cv.unused_details or [])
        # Also include non-empty raw text check for hobbies or references if not in unused_list
        items.append(
            TaggedDetailItem(
                field_name="unused_details",
                category="unmapped_content",
                status=DetailStatus.UNUSED,
                value=unused_list,
                notes="Non-technical context (e.g. hobbies, personal interests, reference contacts, volunteer work) present in CV but excluded from technical scoring",
            )
        )

        # --- 4. EXTRA: System-Generated Metadata ---
        items.append(
            TaggedDetailItem(
                field_name="candidate_id",
                category="system_metadata",
                status=DetailStatus.EXTRA,
                value=str(anonymized_candidate.candidate_id),
                notes="System-assigned UUID for anonymized candidate session tracking",
            )
        )
        items.append(
            TaggedDetailItem(
                field_name="chunks_indexed",
                category="system_metadata",
                status=DetailStatus.EXTRA,
                value=chunks_count,
                notes="Count of semantic chunks embedded and stored in ChromaDB",
            )
        )
        items.append(
            TaggedDetailItem(
                field_name="export_timestamp",
                category="system_metadata",
                status=DetailStatus.EXTRA,
                value=datetime.now(timezone.utc).isoformat(),
                notes="Timestamp when this export was generated",
            )
        )

        # Compute tag breakdown
        tag_counts: Dict[str, int] = {}
        for it in items:
            tag_counts[it.status.value] = tag_counts.get(it.status.value, 0) + 1

        return CVTaggedExport(
            export_type="candidate_cv",
            candidate_id=anonymized_candidate.candidate_id,
            tag_counts=tag_counts,
            items=items,
            parsed_cv=parsed_cv,
            anonymized_candidate=anonymized_candidate,
        )

    @staticmethod
    def build_jd_tagged_export(
        job_description: JobDescription,
        missing_fields: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> JDTaggedExport:
        """
        Builds a comprehensive tagged JSON representation of a Job Description.
        Every detail is tagged as:
          - visible: target title, department, seniority, and requirements used in scoring
          - unused: perks, benefits, company overview, or EEO statements present in posting
          - extra: system-assigned weights (1.0/0.8/0.5), generated requirement IDs, job UUID
          - anonymised: marked if employer contact details are masked
        """
        items: List[TaggedDetailItem] = []

        # --- 1. VISIBLE: Criteria Evaluated Against Candidates ---
        items.append(
            TaggedDetailItem(
                field_name="title",
                category="role_metadata",
                status=DetailStatus.VISIBLE,
                value=job_description.title,
                notes="Official job title used to align candidate evaluation and calibrate interview topics",
            )
        )
        if job_description.department:
            items.append(
                TaggedDetailItem(
                    field_name="department",
                    category="role_metadata",
                    status=DetailStatus.VISIBLE,
                    value=job_description.department,
                    notes="Hiring department / division context",
                )
            )
        if job_description.seniority_level:
            items.append(
                TaggedDetailItem(
                    field_name="seniority_level",
                    category="role_metadata",
                    status=DetailStatus.VISIBLE,
                    value=job_description.seniority_level,
                    notes="Expected seniority level used to calibrate question difficulty and experience thresholds",
                )
            )
        if getattr(job_description, "location", None):
            items.append(
                TaggedDetailItem(
                    field_name="location",
                    category="role_metadata",
                    status=DetailStatus.VISIBLE,
                    value=job_description.location,
                    notes="Geographic location and on-site constraints",
                )
            )
        if getattr(job_description, "work_model", None):
            items.append(
                TaggedDetailItem(
                    field_name="work_model",
                    category="role_metadata",
                    status=DetailStatus.VISIBLE,
                    value=job_description.work_model,
                    notes="Work model (On-site, Hybrid, Remote)",
                )
            )
        if getattr(job_description, "employment_type", None):
            items.append(
                TaggedDetailItem(
                    field_name="employment_type",
                    category="role_metadata",
                    status=DetailStatus.VISIBLE,
                    value=job_description.employment_type,
                    notes="Employment type (Full-time, Part-time, Contract, Internship)",
                )
            )
        if getattr(job_description, "languages", None):
            items.append(
                TaggedDetailItem(
                    field_name="languages",
                    category="role_metadata",
                    status=DetailStatus.VISIBLE,
                    value=job_description.languages,
                    notes="Required or preferred languages",
                )
            )
        if getattr(job_description, "custom_sections", None):
            items.append(
                TaggedDetailItem(
                    field_name="custom_sections",
                    category="custom_sections",
                    status=DetailStatus.VISIBLE,
                    value=job_description.custom_sections,
                    notes="Fallback unmapped operational job constraints",
                )
            )

        for req in job_description.requirements:
            category_label = "MUST-HAVE (75% weight)" if req.category == RequirementCategory.MUST_HAVE else ("NICE-TO-HAVE (25% weight)" if req.category == RequirementCategory.NICE_TO_HAVE else "SOFT SKILL")
            items.append(
                TaggedDetailItem(
                    field_name=f"requirement:{req.id}",
                    category="atomic_requirements",
                    status=DetailStatus.VISIBLE,
                    value={
                        "id": req.id,
                        "title": req.title,
                        "category": req.category.value,
                        "description": req.description,
                        "minimum_years_experience": req.minimum_years_experience,
                    },
                    notes=f"Atomic requirement criterion evaluated via RAG citations [{category_label}]",
                )
            )

        # --- 2. UNUSED: Context Present in Job Posting but Not in Evaluation ---
        unused_list = list(job_description.unused_details or [])
        items.append(
            TaggedDetailItem(
                field_name="unused_details",
                category="unmapped_content",
                status=DetailStatus.UNUSED,
                value=unused_list,
                notes="Company overview, perks/benefits, working conditions, or EEO statements present in JD but excluded from candidate scoring criteria",
            )
        )

        # --- 3. EXTRA: System-Generated Metadata & Weights ---
        items.append(
            TaggedDetailItem(
                field_name="job_id",
                category="system_metadata",
                status=DetailStatus.EXTRA,
                value=str(job_description.id),
                notes="System-assigned UUID identifying this Job Description session",
            )
        )
        for req in job_description.requirements:
            items.append(
                TaggedDetailItem(
                    field_name=f"weight:{req.id}",
                    category="scoring_configuration",
                    status=DetailStatus.EXTRA,
                    value=req.weight,
                    notes=f"System-assigned scoring weight ({req.weight}) for requirement '{req.title}'",
                )
            )

        items.append(
            TaggedDetailItem(
                field_name="scoring_decision_matrix",
                category="scoring_configuration",
                status=DetailStatus.EXTRA,
                value={
                    "must_have_weight": 0.75,
                    "nice_to_have_weight": 0.25,
                    "strong_match_threshold": 0.70,
                    "borderline_threshold": 0.40,
                },
                notes="System decision matrix used by ScoringEngine to classify recommendations",
            )
        )
        items.append(
            TaggedDetailItem(
                field_name="export_timestamp",
                category="system_metadata",
                status=DetailStatus.EXTRA,
                value=datetime.now(timezone.utc).isoformat(),
                notes="Timestamp when this export was generated",
            )
        )

        # --- 4. ANONYMISED: Note on Employer Redaction ---
        items.append(
            TaggedDetailItem(
                field_name="employer_anonymisation",
                category="compliance",
                status=DetailStatus.ANONYMISED,
                value="N/A - Public Job Specification",
                notes="No employer redaction applied to public job criteria",
            )
        )

        # Compute tag breakdown
        tag_counts: Dict[str, int] = {}
        for it in items:
            tag_counts[it.status.value] = tag_counts.get(it.status.value, 0) + 1

        return JDTaggedExport(
            export_type="job_description",
            job_id=job_description.id,
            tag_counts=tag_counts,
            items=items,
            job_description=job_description,
        )
