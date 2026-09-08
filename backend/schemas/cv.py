"""
backend/schemas/cv.py
Data contracts for candidate CV parsing and de-biased anonymization.
"""

from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, EmailStr


class ContactInfo(BaseModel):
    """Raw contact details extracted from the candidate's CV."""
    full_name: str = Field(description="Full legal or displayed name of candidate")
    email: Optional[EmailStr] = Field(default=None, description="Primary contact email")
    phone: Optional[str] = Field(default=None, description="Phone number if present")
    location: Optional[str] = Field(default=None, description="City, region, or country")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn profile link")
    github_url: Optional[str] = Field(default=None, description="GitHub or portfolio link")


class WorkExperience(BaseModel):
    """Granular work history entry."""
    job_title: str = Field(description="Job title")
    company_name: str = Field(description="Company name")
    start_date: Optional[str] = Field(default=None, description="Start date (e.g. 'Jan 2021')")
    end_date: Optional[str] = Field(default=None, description="End date or 'Present'")
    duration_months: Optional[int] = Field(default=None, description="Duration in months if calculable")
    work_description: List[str] = Field(default_factory=list, description="Bullet points/descriptions of work experience")
    skills_used: List[str] = Field(default_factory=list, description="Technologies and skills used in this role")


class Education(BaseModel):
    """Academic background entry."""
    degree_title: str = Field(description="Degree title")
    field_of_study: Optional[str] = Field(default=None, description="Field of study / major")
    institution_name: str = Field(description="Institution name")
    graduation_year: Optional[int] = Field(default=None, description="Graduation year if specified")


class ParsedCV(BaseModel):
    """Complete, raw parsed CV before PII scrubbing."""
    contact_info: ContactInfo
    summary: Optional[str] = Field(default=None, description="Candidate summary or objective")
    skills: List[str] = Field(default_factory=list, description="List of identified skills")
    experiences: List[WorkExperience] = Field(default_factory=list, description="List of work experiences")
    education: List[Education] = Field(default_factory=list, description="List of educational qualifications")
    certifications: List[str] = Field(default_factory=list, description="List of certifications")
    raw_text: str = Field(default="", description="Original extracted text")


class AnonymizedCandidate(BaseModel):
    """Sanitized candidate profile used for de-biased semantic matching."""
    candidate_id: UUID = Field(default_factory=uuid4, description="Deterministic or random UUID for anonymity")
    anonymized_work_experiences: List[WorkExperience] = Field(default_factory=list, description="Anonymized work experiences")
    anonymized_education: List[Education] = Field(default_factory=list, description="Anonymized education")
    anonymized_skills: List[str] = Field(default_factory=list, description="Anonymized skills")
    anonymized_certifications: List[str] = Field(default_factory=list, description="Anonymized certifications")
    sanitized_text: str = Field(default="", description="Sanitized text")
    demographic_data: dict = Field(default_factory=dict, description="Isolated demographic factors kept strictly for fairness audit, never passed to the LLM")
