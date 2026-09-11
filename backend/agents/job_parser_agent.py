"""
backend/agents/job_parser_agent.py
Agent responsible for fetching job description content from URLs across web platforms,
extracting structured atomic requirements via LLM, and detecting missing critical criteria.
"""

from typing import List, Optional
from uuid import uuid4
from bs4 import BeautifulSoup
import httpx
from pydantic import BaseModel, Field

from backend.agents.llm_factory import BaseLLMClient, get_llm_client
from backend.schemas.job import (
    JobDescription,
    JobExtractionResult,
    JobRequirement,
    RequirementCategory,
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

JOB_PARSER_SYSTEM_PROMPT = """You are an expert HR Talent Acquisition & Job Architecture Parsing Agent.
Your task is to analyze the extracted text from a job posting or careers webpage and convert it into a structured Job Description JSON schema.

Extraction Guidelines:
1. Title: Identify the specific professional job title (e.g. 'Senior Python AI Engineer'). Do NOT use generic website header text like 'Careers' or 'Job Opening'.
2. Department: Identify the engineering team, department, or business unit if mentioned.
3. Seniority Level: Extract seniority (Junior, Mid-Level, Senior, Staff, Lead, Principal) based on responsibilities and experience.
4. Requirements: Decompose the qualifications into atomic criteria:
   - MUST_HAVE (category: 'must_have', weight: 1.0): Core mandatory technical prerequisites, languages, frameworks, or required years of experience.
   - NICE_TO_HAVE (category: 'nice_to_have', weight: 0.8): Preferred qualifications, secondary tech stacks, bonus certifications.
   - SOFT_SKILL (category: 'soft_skill', weight: 0.5): Collaboration, communication, mentorship, leadership, agile workflows.
5. Minimum Years: Extract integer minimum years if explicitly stated (e.g. '3+ years' -> 3), otherwise null.
6. Unused Details: Extract non-requirement context such as company background, perks/benefits, EEO statements, salary/compensation info into unused_details.
7. Be precise and ground requirements strictly in the provided text. Do not invent qualifications."""


class ExtractedRequirementItem(BaseModel):
    id: str = Field(description="Unique slug, e.g. 'req_python_fastapi'")
    title: str = Field(description="Short title of the requirement")
    category: RequirementCategory = Field(description="must_have, nice_to_have, or soft_skill")
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    description: str = Field(description="Detailed expectation for this requirement")
    minimum_years_experience: Optional[int] = Field(default=None)


class StructuredJobPosting(BaseModel):
    title: Optional[str] = Field(default=None, description="Job title")
    department: Optional[str] = Field(default=None, description="Department")
    seniority_level: Optional[str] = Field(default=None, description="Seniority level")
    requirements: List[ExtractedRequirementItem] = Field(default_factory=list, description="Extracted requirements")
    unused_details: List[str] = Field(default_factory=list, description="Extracted non-requirement context (company background, perks, EEO)")


def fetch_url_content(url: str, timeout_seconds: float = 15.0) -> str:
    """
    Fetches webpage content from a URL, strips boilerplate HTML (scripts, nav, footer),
    and returns sanitized text content suitable for LLM parsing.
    """
    cleaned_url = url.strip()
    if not (cleaned_url.startswith("http://") or cleaned_url.startswith("https://")):
        raise ValueError("URL must begin with http:// or https://")

    with httpx.Client(
        headers=BROWSER_HEADERS,
        follow_redirects=True,
        timeout=timeout_seconds,
        verify=False,
    ) as client:
        response = client.get(cleaned_url)
        response.raise_for_status()
        html_content = response.text

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe", "form", "aside"]):
        tag.decompose()

    # Prefer main or article containers if available
    main_container = soup.find("main") or soup.find("article") or soup.find("div", class_=lambda c: c and "job" in c.lower()) or soup.body

    raw_text = main_container.get_text(separator="\n", strip=True) if main_container else soup.get_text(separator="\n", strip=True)

    # Clean excessive newlines
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    text = "\n".join(lines)

    # Cap text length to 15,000 characters to protect LLM context
    if len(text) > 15000:
        text = text[:15000]

    return text


class JobParserAgent:
    """Agent that orchestrates URL retrieval, LLM extraction, and missing field auditing."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def parse_job_text(self, text: str) -> JobExtractionResult:
        """
        Parses raw job posting text with LLM and audits for missing required criteria.
        """
        if not text or not text.strip():
            raise ValueError("Cannot parse empty job posting text.")

        prompt = f"Extract structured job description attributes from the following job posting content:\n\n{text.strip()}"

        structured = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=StructuredJobPosting,
            system_prompt=JOB_PARSER_SYSTEM_PROMPT,
            temperature=0.0,
        )

        missing_fields: List[str] = []
        warnings: List[str] = []

        # Validate Title
        title = (structured.title or "").strip()
        generic_titles = {"job", "job opening", "careers", "apply", "position", "opportunity", "hiring"}
        if not title or title.lower() in generic_titles:
            title = title or "Untitled Position"
            missing_fields.append("Job Title")
            warnings.append("Job Title could not be identified accurately. Please specify the target position title.")

        # Validate Requirements
        job_requirements: List[JobRequirement] = []
        must_have_count = 0

        for idx, req in enumerate(structured.requirements):
            req_id = req.id.strip() if req.id else f"req_{idx+1}"
            weight = req.weight
            if req.category == RequirementCategory.MUST_HAVE:
                must_have_count += 1
                weight = max(weight, 1.0)
            elif req.category == RequirementCategory.NICE_TO_HAVE:
                weight = min(max(weight, 0.5), 0.9)
            elif req.category == RequirementCategory.SOFT_SKILL:
                weight = min(weight, 0.6)

            job_requirements.append(
                JobRequirement(
                    id=req_id,
                    title=req.title,
                    category=req.category,
                    weight=weight,
                    description=req.description,
                    minimum_years_experience=req.minimum_years_experience,
                )
            )

        if not job_requirements:
            missing_fields.append("Requirements List")
            warnings.append("No atomic job requirements were found. Please manually add requirements below.")
        elif must_have_count == 0:
            missing_fields.append("Must-Have Requirements")
            warnings.append("No 'Must-Have' requirements detected. Scoring requires at least one Must-Have criterion.")

        # Check Department & Seniority
        department = structured.department
        if not department:
            missing_fields.append("Department")

        seniority = structured.seniority_level
        if not seniority:
            missing_fields.append("Seniority Level")

        jd = JobDescription(
            id=uuid4(),
            title=title,
            department=department,
            seniority_level=seniority,
            requirements=job_requirements,
            unused_details=structured.unused_details,
            raw_text=text,
        )

        return JobExtractionResult(
            job_description=jd,
            missing_fields=missing_fields,
            warnings=warnings,
        )

    def parse_job_url(self, url: str) -> JobExtractionResult:
        """
        Full pipeline:
        1. Fetches webpage text from URL.
        2. Parses structured attributes using LLM.
        3. Audits and warns on missing necessary fields.
        """
        content_text = fetch_url_content(url)
        if not content_text or len(content_text.strip()) < 50:
            raise ValueError("Webpage content appears empty or blocked by access protection.")

        return self.parse_job_text(content_text)
