"""
backend/schemas/cv.py
Data contracts for candidate CV parsing and de-biased anonymization.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactInfo(BaseModel):
    """Raw contact details extracted from the candidate's CV."""
    model_config = ConfigDict(populate_by_name=True)

    full_name: str = Field(description="Full legal or displayed name of candidate")
    email: Optional[EmailStr] = Field(default=None, description="Primary contact email")
    phone_number: Optional[str] = Field(default=None, alias="phone", description="Phone number if present")
    location: Optional[str] = Field(default=None, description="City, region, or country")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn profile link")
    github_url: Optional[str] = Field(default=None, description="GitHub or portfolio link")

    @property
    def phone(self) -> Optional[str]:
        return self.phone_number


class WorkExperience(BaseModel):
    """Granular work history entry."""
    job_title: str = Field(description="Job title")
    company_name: str = Field(description="Company name")
    start_date: Optional[str] = Field(default=None, description="Start date (e.g. 'Jan 2021')")
    end_date: Optional[str] = Field(default=None, description="End date or 'Present'")
    duration_months: Optional[int] = Field(default=None, description="Duration in months if calculable")
    work_description: List[str] = Field(default_factory=list, description="Bullet points/descriptions of work experience")
    skills_used: List[str] = Field(default_factory=list, description="Technologies and skills used in this role")
    location: Optional[str] = Field(default=None, description="Role location (e.g. 'Timisoara, Romania')")
    work_model: Optional[str] = Field(default=None, description="Work model: Remote, Hybrid, or On-site")
    employment_type: Optional[str] = Field(default=None, description="Type: Full-time, Part-time, Internship, Summer Practice, Freelance, Working Student")
    is_promotion: Optional[bool] = Field(default=False, description="Whether this role represents an internal promotion")


class Education(BaseModel):
    """Academic background entry."""
    degree_title: str = Field(description="Degree title")
    field_of_study: Optional[str] = Field(default=None, description="Field of study / major")
    institution_name: str = Field(description="Institution name")
    graduation_year: Optional[int] = Field(default=None, description="Graduation year if specified")
    gpa_or_grade: Optional[str] = Field(default=None, description="GPA or final graduation grade (e.g. '3.9/4.0', '9.85/10')")
    honors: Optional[str] = Field(default=None, description="Academic honors or distinctions (e.g. 'First Class Honours', 'Magna Cum Laude')")
    thesis_title: Optional[str] = Field(default=None, description="Title of Bachelor's, Master's, or PhD thesis/dissertation")
    start_date: Optional[str] = Field(default=None, description="Start date if specified")
    location: Optional[str] = Field(default=None, description="City, country of the institution")
    exchange_program: Optional[str] = Field(default=None, description="Exchange semester or study abroad program (e.g. 'Erasmus+')")


class Publication(BaseModel):
    """Structured academic or industry publication."""
    title: str = Field(description="Publication title")
    authors: List[str] = Field(default_factory=list, description="Co-authors")
    journal_or_conference: Optional[str] = Field(default=None, description="Journal, conference, or publisher name")
    year: Optional[int] = Field(default=None, description="Publication year")
    doi_or_url: Optional[str] = Field(default=None, description="DOI or publication link")


class Patent(BaseModel):
    """Structured intellectual property / patent entry."""
    title: str = Field(description="Patent title")
    patent_number: Optional[str] = Field(default=None, description="Patent or application number")
    patent_office: Optional[str] = Field(default=None, description="Jurisdiction/office (e.g. USPTO, EPO)")
    status: Optional[str] = Field(default=None, description="Status: e.g. 'Granted', 'Pending', 'Application'")
    issue_date: Optional[str] = Field(default=None, description="Issue or filing date")


class LogisticalInfo(BaseModel):
    """Practical candidate logistics and availability constraints."""
    notice_period: Optional[str] = Field(default=None, description="Notice period (e.g. 'Immediate', '1 month', '3 months')")
    earliest_start_date: Optional[str] = Field(default=None, description="Earliest date candidate can start")
    relocation_preference: Optional[str] = Field(default=None, description="Relocation willingness (e.g. 'EU Relocation', 'No Relocation')")
    travel_willingness: Optional[str] = Field(default=None, description="Travel percentage (e.g. 'Up to 25%', 'None')")
    salary_expectation: Optional[str] = Field(default=None, description="Target salary or hourly rate if specified")
    work_authorization: Optional[str] = Field(default=None, description="Work permit, visa status, or citizenship entitlement")
    security_clearance: Optional[str] = Field(default=None, description="Active security clearance level if mentioned")


class Project(BaseModel):
    """Structured candidate project entry."""
    project_name: str = Field(description="Title/name of the project")
    description: List[str] = Field(default_factory=list, description="Key bullet points or technical overview of the project")
    technologies: List[str] = Field(default_factory=list, description="Tools, frameworks, and technologies used")
    start_date: Optional[str] = Field(default=None, description="Start date if mentioned")
    end_date: Optional[str] = Field(default=None, description="End date if mentioned")
    project_url: Optional[str] = Field(default=None, description="GitHub repository or project demo URL")


class LanguageSkill(BaseModel):
    """Language proficiency entry."""
    language: str = Field(description="Language name (e.g. English, German, Romanian)")
    proficiency: Optional[str] = Field(default=None, description="Proficiency level (e.g. C1, Native, Fluent, Intermediate)")


class CustomSection(BaseModel):
    """Fallback container for arbitrary relevant sections (e.g. Publications, Awards, Volunteering, Patents, Workshops)."""
    section_title: str = Field(description="Original section name from CV")
    items: List[str] = Field(default_factory=list, description="Extracted relevant content, achievements, or bullet points")
    is_relevant: bool = Field(default=True, description="Whether this section contains relevant professional/technical signals")


class ParsedCV(BaseModel):
    """Complete, raw parsed CV before PII scrubbing."""
    contact_info: ContactInfo
    summary: Optional[str] = Field(default=None, description="Candidate summary or objective")
    skills: List[str] = Field(default_factory=list, description="List of identified skills")
    experiences: List[WorkExperience] = Field(default_factory=list, description="List of work experiences")
    education: List[Education] = Field(default_factory=list, description="List of educational qualifications")
    certifications: List[str] = Field(default_factory=list, description="List of certifications")
    projects: List[Project] = Field(default_factory=list, description="List of technical, open-source, or academic projects")
    languages: List[LanguageSkill] = Field(default_factory=list, description="List of language proficiencies")
    publications: List[Publication] = Field(default_factory=list, description="List of research publications")
    patents: List[Patent] = Field(default_factory=list, description="List of patents")
    logistics: Optional[LogisticalInfo] = Field(default=None, description="Availability and logistical information")
    custom_sections: List[CustomSection] = Field(default_factory=list, description="Fallback extracted relevant sections (Awards, Publications, Volunteer, etc.)")
    unused_details: List[str] = Field(default_factory=list, description="Extracted non-technical details not used in matching (demographics, personal info, administrative items)")
    raw_text: str = Field(default="", description="Original extracted text")


class AnonymizedCandidate(BaseModel):
    """Sanitized candidate profile used for de-biased semantic matching."""
    candidate_id: UUID = Field(default_factory=uuid4, description="Deterministic or random UUID for anonymity")
    anonymized_work_experiences: List[WorkExperience] = Field(default_factory=list, description="Anonymized work experiences")
    anonymized_education: List[Education] = Field(default_factory=list, description="Anonymized education")
    anonymized_skills: List[str] = Field(default_factory=list, description="Anonymized skills")
    anonymized_certifications: List[str] = Field(default_factory=list, description="Anonymized certifications")
    anonymized_projects: List[Project] = Field(default_factory=list, description="Anonymized technical projects")
    anonymized_languages: List[LanguageSkill] = Field(default_factory=list, description="Language competencies")
    anonymized_publications: List[Publication] = Field(default_factory=list, description="Anonymized publications")
    anonymized_patents: List[Patent] = Field(default_factory=list, description="Anonymized patents")
    logistics: Optional[LogisticalInfo] = Field(default=None, description="Sanitized candidate logistics")
    anonymized_custom_sections: List[CustomSection] = Field(default_factory=list, description="Fallback custom relevant sections scrubbed of PII")
    sanitized_text: str = Field(default="", description="Sanitized text")
    demographic_data: dict = Field(default_factory=dict, description="Isolated demographic factors kept strictly for fairness audit, never passed to the LLM")


class DetailStatus(str, Enum):
    """Categorization status for extracted details."""
    ANONYMISED = "anonymised"
    VISIBLE = "visible"
    UNUSED = "unused"
    EXTRA = "extra"


class TaggedDetailItem(BaseModel):
    """An individual extracted or synthetic detail with its audit status."""
    field_name: str = Field(description="Name of the field or attribute")
    category: str = Field(description="Logical grouping (e.g. contact, experience, skills, metadata)")
    status: DetailStatus = Field(description="Audit status: anonymised, visible, unused, or extra")
    value: Any = Field(description="Exported value")
    raw_value: Optional[Any] = Field(default=None, description="Original raw value before scrubbing, if applicable")
    notes: Optional[str] = Field(default=None, description="Explanation of why this tag was assigned")


class CVTaggedExport(BaseModel):
    """Complete exported JSON structure for a candidate CV with tagged details."""
    export_type: str = Field(default="candidate_cv", description="Type of export")
    candidate_id: UUID = Field(description="UUID of candidate")
    tag_counts: dict = Field(default_factory=dict, description="Summary counts of details by tag")
    items: List[TaggedDetailItem] = Field(default_factory=list, description="All tagged items")
    parsed_cv: ParsedCV = Field(description="Underlying raw parsed CV structure")
    anonymized_candidate: AnonymizedCandidate = Field(description="Sanitized representation passed to matching")
