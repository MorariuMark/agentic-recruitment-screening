"""
backend/schemas/cv.py
Data contracts for candidate CV parsing and de-biased anonymization.
"""

from enum import Enum
import re
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _flatten_to_string_list(val: Any) -> List[str]:
    """
    Recursively flattens lists, dicts, comma-separated strings, or mixed structures into a flat List[str].
    Handles small LLM responses that group skills into dictionary categories (e.g. {'hardwareSoftware': [...]})
    or comma-delimited strings rather than flat arrays.
    """
    if val is None:
        return []
    if isinstance(val, list):
        res: List[str] = []
        for item in val:
            if isinstance(item, str):
                item_s = item.strip()
                if item_s:
                    res.append(item_s)
            elif isinstance(item, dict):
                res.extend(_flatten_to_string_list(item))
            elif isinstance(item, (int, float, bool)):
                res.append(str(item))
        return res
    if isinstance(val, dict):
        res = []
        for k, v in val.items():
            res.extend(_flatten_to_string_list(v))
        return res
    if isinstance(val, str):
        if "," in val:
            return [s.strip() for s in val.split(",") if s.strip()]
        s = val.strip()
        return [s] if s else []
    return [str(val)]


class ContactInfo(BaseModel):
    """Raw contact details extracted from the candidate's CV."""
    model_config = ConfigDict(populate_by_name=True)

    full_name: str = Field(default="Candidate Name", description="Full legal or displayed name of candidate")
    email: Optional[str] = Field(default=None, description="Primary contact email")
    phone_number: Optional[str] = Field(default=None, alias="phone", description="Phone number if present")
    location: Optional[str] = Field(default=None, description="City, region, or country")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn profile link")
    github_url: Optional[str] = Field(default=None, description="GitHub or portfolio link")

    @model_validator(mode="before")
    @classmethod
    def normalize_contact_info(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "full_name" not in data or not data["full_name"]:
                for alias in ["name", "candidate_name", "fullname"]:
                    if data.get(alias):
                        data["full_name"] = str(data[alias])
                        break
                else:
                    data["full_name"] = data.get("full_name") or "Candidate Name"
            if "phone_number" not in data and "phone" in data:
                data["phone_number"] = data["phone"]
        return data

    @property
    def phone(self) -> Optional[str]:
        return self.phone_number


class WorkExperience(BaseModel):
    """Granular work history entry."""
    job_title: str = Field(default="Professional Role", description="Job title")
    company_name: str = Field(default="Company / Organization", description="Company name")
    start_date: Optional[str] = Field(default=None, description="Start date (e.g. 'Jan 2021')")
    end_date: Optional[str] = Field(default=None, description="End date or 'Present'")
    duration_months: Optional[int] = Field(default=None, description="Duration in months if calculable")
    work_description: List[str] = Field(default_factory=list, description="Bullet points/descriptions of work experience")
    skills_used: List[str] = Field(default_factory=list, description="Technologies and skills used in this role")
    location: Optional[str] = Field(default=None, description="Role location (e.g. 'Timisoara, Romania')")
    work_model: Optional[str] = Field(default=None, description="Work model: Remote, Hybrid, or On-site")
    employment_type: Optional[str] = Field(default=None, description="Type: Full-time, Part-time, Internship, Summer Practice, Freelance, Working Student")
    is_promotion: Optional[bool] = Field(default=False, description="Whether this role represents an internal promotion")

    @model_validator(mode="before")
    @classmethod
    def normalize_experience_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "job_title" not in data or not data["job_title"]:
                for alias in ["title", "role", "position", "designation"]:
                    if data.get(alias):
                        data["job_title"] = str(data[alias])
                        break
                else:
                    data["job_title"] = data.get("job_title") or "Professional Role"

            if "company_name" not in data or not data["company_name"]:
                for alias in ["company", "employer", "organization", "firm"]:
                    if data.get(alias):
                        data["company_name"] = str(data[alias])
                        break
                else:
                    data["company_name"] = data.get("company_name") or "Company / Organization"

            # Parse dates string into start_date / end_date
            if "dates" in data and data["dates"]:
                dates_str = str(data["dates"]).strip()
                if any(sep in dates_str for sep in [" - ", " – ", " — ", "-", "–", "—"]):
                    parts = re.split(r"\s*[-–—]\s*", dates_str, maxsplit=1)
                    if not data.get("start_date") and len(parts) > 0 and parts[0].strip():
                        data["start_date"] = parts[0].strip()
                    if not data.get("end_date") and len(parts) > 1 and parts[1].strip():
                        data["end_date"] = parts[1].strip()
                elif not data.get("start_date"):
                    data["start_date"] = dates_str

            # Flatten work_description / description / bullet_points
            for desc_key in ["work_description", "description", "bullet_points", "responsibilities", "tasks"]:
                if desc_key in data and data[desc_key]:
                    val = data[desc_key]
                    if isinstance(val, str):
                        data["work_description"] = [s.strip() for s in val.split("\n") if s.strip()] or [val.strip()]
                    elif isinstance(val, (list, dict)):
                        data["work_description"] = _flatten_to_string_list(val)
                    break

            # Flatten skills_used
            if "skills_used" in data and data["skills_used"]:
                data["skills_used"] = _flatten_to_string_list(data["skills_used"])
        return data


class Education(BaseModel):
    """Academic background entry."""
    degree_title: str = Field(default="Degree / Qualification", description="Degree title")
    field_of_study: Optional[str] = Field(default=None, description="Field of study / major")
    institution_name: str = Field(default="Educational Institution", description="Institution name")
    graduation_year: Optional[int] = Field(default=None, description="Graduation year if specified")
    gpa_or_grade: Optional[str] = Field(default=None, description="GPA or final graduation grade (e.g. '3.9/4.0', '9.85/10')")
    honors: Optional[str] = Field(default=None, description="Academic honors or distinctions (e.g. 'First Class Honours', 'Magna Cum Laude')")
    thesis_title: Optional[str] = Field(default=None, description="Title of Bachelor's, Master's, or PhD thesis/dissertation")
    start_date: Optional[str] = Field(default=None, description="Start date if specified")
    location: Optional[str] = Field(default=None, description="City, country of the institution")
    exchange_program: Optional[str] = Field(default=None, description="Exchange semester or study abroad program (e.g. 'Erasmus+')")

    @model_validator(mode="before")
    @classmethod
    def normalize_education_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Degree title aliases
            if "degree_title" not in data or not data["degree_title"]:
                for alias in ["degree", "title", "qualification", "degree_name", "program"]:
                    if data.get(alias):
                        data["degree_title"] = str(data[alias])
                        break
                else:
                    data["degree_title"] = data.get("degree_title") or "Degree / Qualification"

            # Institution name aliases
            if "institution_name" not in data or not data["institution_name"]:
                for alias in ["institution", "university", "school", "college", "academy"]:
                    if data.get(alias):
                        data["institution_name"] = str(data[alias])
                        break
                else:
                    data["institution_name"] = data.get("institution_name") or "Educational Institution"

            # Year extraction from dates string if graduation_year is missing
            if ("graduation_year" not in data or not data["graduation_year"]) and "dates" in data:
                import re
                years = re.findall(r"\b(19\d\d|20\d\d)\b", str(data["dates"]))
                if years:
                    try:
                        data["graduation_year"] = int(years[-1])
                    except Exception:
                        pass
        return data


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
    project_name: str = Field(default="Project", description="Title/name of the project")
    description: List[str] = Field(default_factory=list, description="Key bullet points or technical overview of the project")
    technologies: List[str] = Field(default_factory=list, description="Tools, frameworks, and technologies used")
    start_date: Optional[str] = Field(default=None, description="Start date if mentioned")
    end_date: Optional[str] = Field(default=None, description="End date if mentioned")
    project_url: Optional[str] = Field(default=None, description="GitHub repository or project demo URL")

    @model_validator(mode="before")
    @classmethod
    def normalize_project_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "project_name" not in data or not data["project_name"]:
                for alias in ["name", "title", "project", "project_title"]:
                    if data.get(alias):
                        data["project_name"] = str(data[alias])
                        break
                else:
                    data["project_name"] = data.get("project_name") or "Project"
        return data

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, v):
        if isinstance(v, str):
            lines = [l.strip().lstrip("•-*–+ ").strip() for l in v.splitlines() if l.strip()]
            return lines if lines else ([v.strip()] if v.strip() else [])
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    cleaned = item.strip().lstrip("•-*–+ ").strip()
                    if cleaned:
                        res.append(cleaned)
                elif item:
                    res.append(str(item).strip())
            return res
        return []

    @field_validator("technologies", mode="before")
    @classmethod
    def normalize_technologies(cls, v):
        if isinstance(v, str):
            import re
            return [t.strip() for t in re.split(r"[,;|•]", v) if t.strip()]
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()]
        return []


class LanguageSkill(BaseModel):
    """Language proficiency entry."""
    language: str = Field(description="Language name (e.g. English, German, Romanian)")
    proficiency: Optional[str] = Field(default=None, description="Proficiency level (e.g. C1, Native, Fluent, Intermediate)")

    @model_validator(mode="before")
    @classmethod
    def normalize_language_skill(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"language": data.strip()}
        if isinstance(data, dict):
            if "language" not in data:
                for k in ["name", "lang", "language_name"]:
                    if data.get(k):
                        data["language"] = str(data[k])
                        break
                else:
                    if len(data) == 1:
                        k, v = next(iter(data.items()))
                        data["language"] = str(k)
                        data["proficiency"] = str(v)
                    else:
                        data["language"] = "Language"
        return data


class CustomSection(BaseModel):
    """Fallback container for arbitrary relevant sections (e.g. Publications, Awards, Volunteering, Patents, Workshops)."""
    section_title: str = Field(description="Original section name from CV")
    items: List[str] = Field(default_factory=list, description="Extracted relevant content, achievements, or bullet points")
    is_relevant: bool = Field(default=True, description="Whether this section contains relevant professional/technical signals")

    @model_validator(mode="before")
    @classmethod
    def normalize_custom_section(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "section_title" not in data or not data["section_title"]:
                for k in ["title", "name", "heading", "category"]:
                    if data.get(k):
                        data["section_title"] = str(data[k])
                        break
                else:
                    data["section_title"] = "Additional Section"
            if "items" in data and data["items"]:
                data["items"] = _flatten_to_string_list(data["items"])
            elif "items" not in data or not data["items"]:
                for it_k in ["content", "bullet_points", "details", "values"]:
                    if data.get(it_k):
                        data["items"] = _flatten_to_string_list(data[it_k])
                        break
                else:
                    data["items"] = []
        return data


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
    custom_sections: List[CustomSection] = Field(default_factory=list, description="Dedicated custom sections extracted from CV (Awards, Publications, Volunteer, Hobbies, etc.)")
    miscellaneous: List[str] = Field(default_factory=list, description="All miscellaneous, unmapped, or out-of-scope details, facts, hobbies, interests, activities, memberships, side notes, or observations extracted so no detail is ignored or overlooked")
    unused_details: List[str] = Field(default_factory=list, description="Extracted non-technical details not used in matching (demographics, personal info, administrative items)")
    raw_text: str = Field(default="", description="Original extracted text")

    @model_validator(mode="before")
    @classmethod
    def normalize_parsed_cv(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Contact Info fallback
            if "contact_info" not in data or data.get("contact_info") is None:
                data["contact_info"] = {
                    "full_name": data.get("full_name") or data.get("name") or data.get("candidate_name") or "Candidate Name",
                    "email": data.get("email"),
                    "phone": data.get("phone") or data.get("phone_number"),
                    "location": data.get("location"),
                }

            # 2. Section aliases mapping
            if "skills" not in data or not data["skills"]:
                for alias in ["technical_skills", "skill_set", "competencies", "key_skills", "skills_list"]:
                    if data.get(alias):
                        data["skills"] = data[alias]
                        break

            if "experiences" not in data or not data["experiences"]:
                for alias in ["work_experiences", "work_experience", "experience", "work_history", "employment", "roles", "jobs"]:
                    if data.get(alias):
                        data["experiences"] = data[alias]
                        break

            if "education" not in data or not data["education"]:
                for alias in ["educations", "academic_background", "qualifications", "academics", "studies"]:
                    if data.get(alias):
                        data["education"] = data[alias]
                        break

            if "certifications" not in data or not data["certifications"]:
                for alias in ["certificates", "licenses", "accreditations"]:
                    if data.get(alias):
                        data["certifications"] = data[alias]
                        break

            if "projects" not in data or not data["projects"]:
                for alias in ["portfolio", "key_projects", "personal_projects"]:
                    if data.get(alias):
                        data["projects"] = data[alias]
                        break

            if "languages" not in data or not data["languages"]:
                for alias in ["language_skills", "spoken_languages"]:
                    if data.get(alias):
                        data["languages"] = data[alias]
                        break

            # 3. Object-to-Array transforms if LLM returned dictionary instead of list
            if "experiences" in data:
                if isinstance(data["experiences"], dict):
                    data["experiences"] = list(data["experiences"].values()) if data["experiences"] else []
                elif not isinstance(data["experiences"], list):
                    data["experiences"] = []

            if "education" in data:
                if isinstance(data["education"], dict):
                    data["education"] = list(data["education"].values()) if data["education"] else []
                elif not isinstance(data["education"], list):
                    data["education"] = []

            if "projects" in data:
                if isinstance(data["projects"], dict):
                    data["projects"] = list(data["projects"].values()) if data["projects"] else []
                elif not isinstance(data["projects"], list):
                    data["projects"] = []

            if "languages" in data:
                if isinstance(data["languages"], dict):
                    data["languages"] = [{"language": k, "proficiency": str(v)} for k, v in data["languages"].items()]
                elif isinstance(data["languages"], list):
                    norm_langs = []
                    for item in data["languages"]:
                        if isinstance(item, str) and item.strip():
                            norm_langs.append({"language": item.strip(), "proficiency": "Proficient"})
                        elif isinstance(item, (dict, LanguageSkill)):
                            norm_langs.append(item)
                    data["languages"] = norm_langs
                elif isinstance(data["languages"], str):
                    data["languages"] = [{"language": s.strip(), "proficiency": "Proficient"} for s in data["languages"].split(",") if s.strip()]
                else:
                    data["languages"] = []

            if "custom_sections" in data:
                if isinstance(data["custom_sections"], dict):
                    c_sec = data["custom_sections"]
                    if not c_sec:
                        data["custom_sections"] = []
                    elif "section_title" in c_sec:
                        data["custom_sections"] = [c_sec]
                    else:
                        norm_csec = []
                        for k, v in c_sec.items():
                            if isinstance(v, dict):
                                norm_csec.append(v)
                            elif isinstance(v, list):
                                norm_csec.append({"section_title": str(k), "items": _flatten_to_string_list(v), "is_relevant": True})
                            elif isinstance(v, str):
                                norm_csec.append({"section_title": str(k), "items": [v.strip()], "is_relevant": True})
                        data["custom_sections"] = norm_csec
                elif not isinstance(data["custom_sections"], list):
                    data["custom_sections"] = []

            if "publications" in data:
                if isinstance(data["publications"], dict):
                    p_dict = data["publications"]
                    if not p_dict:
                        data["publications"] = []
                    elif "title" in p_dict:
                        data["publications"] = [p_dict]
                    else:
                        data["publications"] = list(p_dict.values())
                elif not isinstance(data["publications"], list):
                    data["publications"] = []

            if "patents" in data:
                if isinstance(data["patents"], dict):
                    pat_dict = data["patents"]
                    if not pat_dict:
                        data["patents"] = []
                    elif "title" in pat_dict:
                        data["patents"] = [pat_dict]
                    else:
                        data["patents"] = list(pat_dict.values())
                elif not isinstance(data["patents"], list):
                    data["patents"] = []

            # 4. Logistics cleanup (local models may emit "" or null)
            if "logistics" in data:
                if isinstance(data["logistics"], str):
                    data["logistics"] = None
                elif not isinstance(data["logistics"], (dict, LogisticalInfo)):
                    data["logistics"] = None

            # 5. Flatten string lists (handles categorized dicts like {'hardwareSoftware': [...]})
            if "skills" in data and data["skills"] is not None:
                data["skills"] = _flatten_to_string_list(data["skills"])
            elif "skills" in data and data["skills"] is None:
                data["skills"] = []

            if "certifications" in data and data["certifications"] is not None:
                data["certifications"] = _flatten_to_string_list(data["certifications"])
            elif "certifications" in data and data["certifications"] is None:
                data["certifications"] = []

            if "miscellaneous" in data and data["miscellaneous"] is not None:
                data["miscellaneous"] = _flatten_to_string_list(data["miscellaneous"])
            elif "miscellaneous" in data and data["miscellaneous"] is None:
                data["miscellaneous"] = []

            if "unused_details" in data and data["unused_details"] is not None:
                data["unused_details"] = _flatten_to_string_list(data["unused_details"])
            elif "unused_details" in data and data["unused_details"] is None:
                data["unused_details"] = []

        return data


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
    anonymized_miscellaneous: List[str] = Field(default_factory=list, description="PII-scrubbed miscellaneous and out-of-scope details ready for semantic vector search")
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
