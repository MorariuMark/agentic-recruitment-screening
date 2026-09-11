"""
backend/schemas/job.py
Data contracts for Job Descriptions and granular atomic requirement criteria.
"""

from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class RequirementCategory(str, Enum):
    """Classification of requirement importance."""
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"
    SOFT_SKILL = "soft_skill"


class JobRequirement(BaseModel):
    """A single atomic requirement extracted from a Job Description."""
    id: str = Field(description="Unique requirement slug, e.g. 'req_python_fastapi'")
    category: RequirementCategory = Field(description="Classification: must_have, nice_to_have, or soft_skill")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Relative scoring weight between 0.0 and 1.0")
    title: str = Field(description="Short summary of the requirement")
    description: str = Field(description="Full granular expectation for this requirement")
    minimum_years_experience: Optional[int] = Field(default=None, description="Minimum years of experience required")


class JobDescription(BaseModel):
    """Complete Job Description with atomic requirement decomposition."""
    id: UUID = Field(default_factory=uuid4, description="Unique job posting ID")
    title: str = Field(description="Job posting title, e.g. 'Senior Backend Engineer'")
    department: Optional[str] = Field(default=None, description="Department")
    seniority_level: Optional[str] = Field(default=None, description="Seniority level")
    location: Optional[str] = Field(default=None, description="Target city/region or location")
    work_model: Optional[str] = Field(default=None, description="Work model: On-site, Hybrid, or Remote")
    employment_type: Optional[str] = Field(default=None, description="Employment type: Full-time, Part-time, Contract, Internship")
    languages: List[str] = Field(default_factory=list, description="Required or preferred languages")
    custom_sections: List[dict] = Field(default_factory=list, description="Fallback unmapped job sections (Travel, Security Clearance, etc.)")
    requirements: List[JobRequirement] = Field(default_factory=list, description="List of job requirements")
    unused_details: List[str] = Field(default_factory=list, description="Extracted non-requirement JD sections (perks, company intro, EEO)")
    raw_text: str = Field(default="", description="Original job description text")


class JobExtractionResult(BaseModel):
    """Result of parsing and extracting a Job Description from URL or unstructured text."""
    job_description: JobDescription = Field(description="Extracted structured Job Description")
    missing_fields: List[str] = Field(default_factory=list, description="Fields that could not be confidently identified")
    warnings: List[str] = Field(default_factory=list, description="Actionable warnings prompting manual completion")


class JDTaggedExport(BaseModel):
    """Complete exported JSON structure for a Job Description with tagged details."""
    export_type: str = Field(default="job_description", description="Type of export")
    job_id: UUID = Field(description="UUID of job posting")
    tag_counts: dict = Field(default_factory=dict, description="Summary counts of details by tag")
    items: list = Field(default_factory=list, description="All tagged items (TaggedDetailItem)")
    job_description: JobDescription = Field(description="Underlying structured Job Description")
