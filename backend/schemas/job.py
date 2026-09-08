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
    requirements: List[JobRequirement] = Field(default_factory=list, description="List of job requirements")
    raw_text: str = Field(default="", description="Original job description text")
