"""
backend/agents/job_parser_agent.py
Agent responsible for fetching job description content from URLs across web platforms,
extracting structured atomic requirements via LLM, and detecting missing critical criteria.
"""

import json
import re
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
4. Location & Work Model: Extract target city, region, or country (e.g. 'Timisoara or Sibiu, Romania') into location. Classify work_model as 'On-site', 'Hybrid', or 'Remote'. If on-site presence or a specific location is mandatory, also generate an atomic MUST_HAVE requirement for it.
5. Employment Type: Extract 'Full-time', 'Part-time', 'Contract', or 'Internship'.
6. Languages: Extract required or preferred languages (e.g. 'English (fluent)', 'German'). If a language is required, also include it as an atomic requirement.
7. Requirements: Decompose the qualifications into atomic criteria:
   - Carefully inspect BOTH 'Profile/Requirements' AND 'Tasks/Responsibilities' for specific named vendor platforms, enterprise tools, and systems (e.g. Corporater, SAP, Power BI, Jira, Salesforce, etc.) and include them as requirements.
   - MUST_HAVE (category: 'must_have', weight: 1.0): Core mandatory technical prerequisites, languages, frameworks, on-site/location mandates, or required years of experience.
   - NICE_TO_HAVE (category: 'nice_to_have', weight: 0.8): Preferred qualifications, secondary tech stacks, bonus certifications.
   - SOFT_SKILL (category: 'soft_skill', weight: 0.5): Collaboration, communication, mentorship, leadership, agile workflows.
8. Minimum Years: Extract integer minimum years if explicitly stated (e.g. '3+ years' -> 3), otherwise null.
9. Custom Sections: Capture any unmapped operational constraints into custom_sections (e.g. Travel Requirements, Relocation Support, Security Clearance).
10. Unused Details: Extract non-requirement context such as company background, perks/benefits, EEO statements, salary/compensation info, application rules into unused_details.
11. Be precise and ground requirements strictly in the provided text. Do not invent qualifications."""


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
    location: Optional[str] = Field(default=None, description="Target location / cities / country")
    work_model: Optional[str] = Field(default=None, description="On-site, Hybrid, or Remote")
    employment_type: Optional[str] = Field(default=None, description="Full-time, Part-time, Contract, Internship")
    languages: List[str] = Field(default_factory=list, description="Required or preferred languages")
    custom_sections: List[dict] = Field(default_factory=list, description="Fallback unmapped job sections")
    requirements: List[ExtractedRequirementItem] = Field(default_factory=list, description="Extracted requirements")
    unused_details: List[str] = Field(default_factory=list, description="Extracted non-requirement context (company background, perks, EEO)")


def _clean_html_string(html_str: Optional[str]) -> str:
    """Strips HTML markup and returns sanitized plain text."""
    if not html_str:
        return ""
    return BeautifulSoup(html_str, "html.parser").get_text(separator="\n", strip=True)


def _try_extract_oracle_hcm(html_content: str, url: str, timeout: float = 15.0) -> Optional[str]:
    """
    Detects and queries Oracle Cloud HCM Candidate Experience (oj-hcm-ce) REST APIs
    when the page is a client-rendered SPA (e.g. jobs.nokia.com).
    """
    soup = BeautifulSoup(html_content, "html.parser")
    base_tag = soup.find("base")
    fa_host = None
    site_num = "CX_1"

    if base_tag:
        fa_host = base_tag.get("data-fahosturl") or base_tag.get("data-apibaseurl")
        site_num = base_tag.get("data-sitenumber") or "CX_1"

    if not fa_host:
        m_host = re.search(r"https://[a-zA-Z0-9_-]+\.fa\.ocs\.oraclecloud\.com(?::443)?", html_content)
        if m_host:
            fa_host = m_host.group(0)

    m_site = re.search(r"/sites/([A-Za-z0-9_-]+)", url)
    if m_site:
        site_num = m_site.group(1)

    if not fa_host:
        return None

    req_match = re.search(r"/jobs/(?:preview/)?([0-9]+)", url)
    if not req_match:
        req_match = re.search(r"(?:reqId|requisitionId|requisitionNumber)=([0-9]+)", url)

    if not req_match:
        return None

    req_id = req_match.group(1)
    api_url = (
        f"{fa_host.rstrip('/')}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
        f'?expand=all&onlyData=true&finder=ById;Id="{req_id}",siteNumber="{site_num}"'
    )

    try:
        with httpx.Client(headers=BROWSER_HEADERS, timeout=timeout, verify=False) as client:
            res = client.get(
                api_url,
                headers={"Accept": "application/json", "Ora-Irc-Language": "en"},
            )
            if res.status_code != 200:
                return None
            data = res.json()
            items = data.get("items", [])
            if not items:
                return None
            item = items[0]

            sections = []
            title = item.get("Title") or ""
            if title:
                sections.append(f"Job Title: {title}")
            dept = item.get("Department") or item.get("Category") or ""
            if dept:
                sections.append(f"Department: {dept}")
            loc = item.get("PrimaryLocation") or ""
            if loc:
                sections.append(f"Location: {loc}")
            wm = item.get("WorkplaceType") or ""
            if wm:
                sections.append(f"Work Model: {wm}")
            ct = item.get("ContractType") or item.get("JobSchedule") or ""
            if ct:
                sections.append(f"Employment Type: {ct}")

            desc = _clean_html_string(
                item.get("ExternalDescriptionStr")
                or item.get("ShortDescriptionStr")
                or item.get("DescriptionStr")
            )
            if desc:
                sections.append(f"\nJob Description & Overview:\n{desc}")

            resp = _clean_html_string(
                item.get("ExternalResponsibilitiesStr")
                or item.get("ResponsibilitiesStr")
                or item.get("InternalResponsibilitiesStr")
            )
            if resp:
                sections.append(f"\nKey Responsibilities & Tasks:\n{resp}")

            qual = _clean_html_string(
                item.get("ExternalQualificationsStr")
                or item.get("QualificationsStr")
                or item.get("InternalQualificationsStr")
            )
            if qual:
                sections.append(f"\nQualifications & Requirements:\n{qual}")

            skills = item.get("skills")
            if isinstance(skills, list) and skills:
                skill_names = [s.get("SkillName") or str(s) for s in skills if s]
                if skill_names:
                    sections.append(f"\nTagged Skills:\n{', '.join(skill_names)}")

            text = "\n".join(sections)
            return text if len(text.strip()) >= 50 else None
    except Exception:
        return None


def _try_extract_json_ld(soup: BeautifulSoup) -> Optional[str]:
    """
    Extracts structured JobPosting schema from JSON-LD script elements.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            raw = json.loads(script.string)
            items = raw if isinstance(raw, list) else [raw]
            for item in items:
                if not isinstance(item, dict):
                    continue
                graph = item.get("@graph")
                candidates = graph if isinstance(graph, list) else [item]
                for node in candidates:
                    if not isinstance(node, dict):
                        continue
                    if node.get("@type") == "JobPosting":
                        sections = []
                        title = node.get("title")
                        if title:
                            sections.append(f"Job Title: {title}")
                        hiring_org = node.get("hiringOrganization")
                        if isinstance(hiring_org, dict) and hiring_org.get("name"):
                            sections.append(f"Company: {hiring_org['name']}")
                        job_loc = node.get("jobLocation")
                        if isinstance(job_loc, dict):
                            addr = job_loc.get("address")
                            if isinstance(addr, dict):
                                loc_parts = [
                                    addr.get("addressLocality"),
                                    addr.get("addressRegion"),
                                    addr.get("addressCountry"),
                                ]
                                sections.append(f"Location: {', '.join([p for p in loc_parts if p])}")
                            elif isinstance(addr, str):
                                sections.append(f"Location: {addr}")
                        emp_type = node.get("employmentType")
                        if emp_type:
                            sections.append(f"Employment Type: {emp_type}")
                        desc = node.get("description")
                        if desc:
                            sections.append(f"\nJob Description:\n{_clean_html_string(desc)}")
                        skills = node.get("skills")
                        if skills:
                            sections.append(
                                f"\nSkills:\n{skills if isinstance(skills, str) else ', '.join(skills)}"
                            )
                        resp = node.get("responsibilities")
                        if resp:
                            sections.append(f"\nResponsibilities:\n{_clean_html_string(resp)}")
                        qual = node.get("qualifications")
                        if qual:
                            sections.append(f"\nQualifications:\n{_clean_html_string(qual)}")
                        text = "\n".join(sections)
                        if len(text.strip()) >= 50:
                            return text
        except Exception:
            continue
    return None


def _try_extract_meta_tags(soup: BeautifulSoup) -> Optional[str]:
    """
    Extracts OpenGraph, Twitter, and standard HTML meta tags as a fallback when body is client-rendered.
    """
    title = None
    og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    desc = None
    og_desc = (
        soup.find("meta", property="og:description")
        or soup.find("meta", attrs={"name": "twitter:description"})
        or soup.find("meta", attrs={"name": "description"})
    )
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"].strip()

    keywords = None
    kw_meta = soup.find("meta", attrs={"name": "keywords"})
    if kw_meta and kw_meta.get("content"):
        keywords = kw_meta["content"].strip()

    if desc and len(desc) >= 40:
        sections = []
        if title:
            sections.append(f"Job Title: {title}")
        sections.append(f"\nJob Overview:\n{desc}")
        if keywords:
            sections.append(f"\nKeywords & Skills:\n{keywords}")
        return "\n".join(sections)
    return None


def _try_extract_next_data(soup: BeautifulSoup) -> Optional[str]:
    """
    Extracts structured job posting payload from Next.js (__NEXT_DATA__) scripts
    commonly present on modern recruiting platforms (e.g. BestJobs).
    """
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None
    try:
        data = json.loads(script.string)
        props = data.get("props", {})
        page_props = props.get("pageProps", {})
        job = page_props.get("job")
        if not isinstance(job, dict):
            return None

        sections = []
        title = job.get("title")
        if title:
            sections.append(f"Job Title: {title}")

        emp = job.get("employer") or {}
        comp_name = emp.get("name") or job.get("companyName")
        if comp_name:
            sections.append(f"Company: {comp_name}")

        locs = job.get("locations")
        if isinstance(locs, list) and locs:
            city_names = [l.get("name") for l in locs if isinstance(l, dict) and l.get("name")]
            if city_names:
                sections.append(f"Target Locations: {', '.join(city_names)}, Romania")

        is_remote = job.get("remote")
        is_partial = job.get("partialRemote")
        if is_remote is True:
            sections.append("Work Model: Remote")
        elif is_partial is True:
            sections.append("Work Model: Hybrid")
        elif is_remote is False and is_partial is False:
            sections.append("Work Model: On-site")

        emp_types = job.get("employmentTypes")
        if isinstance(emp_types, list) and emp_types:
            type_names = [t.get("name") for t in emp_types if isinstance(t, dict) and t.get("name")]
            if type_names:
                sections.append(f"Employment Type: {', '.join(type_names)}")

        langs = job.get("spokenLanguages")
        if isinstance(langs, list) and langs:
            l_strs = [
                f"{l.get('name')} ({l.get('levelName')})"
                for l in langs
                if isinstance(l, dict) and l.get("name")
            ]
            if l_strs:
                sections.append(f"Required Languages: {', '.join(l_strs)}")

        salary = job.get("salary") or job.get("estimatedSalary")
        if salary:
            sections.append(f"Estimated Salary: {salary}")

        desc = _clean_html_string(job.get("description"))
        if desc:
            sections.append(f"\nJob Description & Overview:\n{desc}")

        text = "\n".join(sections)
        return text if len(text.strip()) >= 50 else None
    except Exception:
        return None


def fetch_url_content(url: str, timeout_seconds: float = 15.0) -> str:
    """
    Fetches webpage content from a URL across standard job boards, SPAs (Oracle HCM),
    Next.js SSR apps (__NEXT_DATA__), and structured schema/meta tag fallbacks.
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

    # 1. Check for Oracle Cloud HCM Candidate Experience SPA
    oracle_text = _try_extract_oracle_hcm(html_content, cleaned_url, timeout=timeout_seconds)
    if oracle_text:
        return oracle_text[:15000]

    soup = BeautifulSoup(html_content, "html.parser")

    # 2. Check for Next.js (__NEXT_DATA__) job object
    next_data_text = _try_extract_next_data(soup)

    # 3. Check for JSON-LD JobPosting schema before decomposing scripts
    json_ld_text = _try_extract_json_ld(soup)

    # 4. Check for OpenGraph / Twitter meta tags fallback
    meta_text = _try_extract_meta_tags(soup)

    # Extract header context (Page Title and Meta Description) before decomposing
    page_title = soup.title.string.strip() if soup.title and soup.title.string else None
    meta_desc = None
    og_desc = (
        soup.find("meta", property="og:description")
        or soup.find("meta", attrs={"name": "description"})
        or soup.find("meta", attrs={"name": "twitter:description"})
    )
    if og_desc and og_desc.get("content"):
        meta_desc = og_desc["content"].strip()

    # 5. Remove non-content tags and extract visible body text
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe", "form", "aside"]):
        tag.decompose()

    main_container = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=lambda c: c and "job" in c.lower())
        or soup.body
    )

    raw_text = main_container.get_text(separator="\n", strip=True) if main_container else soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    body_text = "\n".join(lines)

    # Prepend header context (title and meta description) to main text if available
    header_context = []
    if page_title:
        header_context.append(f"Page Title: {page_title}")
    if meta_desc:
        header_context.append(f"Meta Description: {meta_desc}")

    full_text = "\n".join(header_context) + "\n\n" + body_text if header_context else body_text

    # 6. Determine best available text source
    if next_data_text and len(next_data_text) >= 200:
        result_text = next_data_text
    elif len(body_text) >= 100:
        result_text = full_text
    elif next_data_text:
        result_text = next_data_text
    elif json_ld_text:
        result_text = json_ld_text
    elif meta_text:
        result_text = meta_text
    elif len(full_text.strip()) >= 50:
        result_text = full_text
    else:
        raise ValueError(
            f"Webpage content could not be extracted from '{url}'. "
            f"The site may be an interactive Single-Page Application (SPA) requiring JavaScript, "
            f"or protected by anti-bot verification. Please copy the job description text and paste it manually into the text input area."
        )

    if len(result_text) > 15000:
        result_text = result_text[:15000]

    return result_text


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

        # Fallback 1: Smart Location Detection from text / headers if omitted by LLM
        location = structured.location
        lower_text = text.lower()
        if not location:
            loc_match = re.search(r"(?:Target\s+)?Locations?:\s*([^\n\r]+)", text, re.IGNORECASE)
            if loc_match:
                location = loc_match.group(1).strip()
            else:
                city_patterns = [
                    "Timișoara", "Timisoara", "Arad", "Lugoj", "București", "Bucuresti",
                    "Cluj-Napoca", "Cluj", "Iași", "Iasi", "Brașov", "Brasov", "Sibiu",
                    "Oradea", "Craiova", "Constanța", "Constanta", "Ploiești", "Ploiesti", "Galați", "Galati"
                ]
                found_cities = []
                for city in city_patterns:
                    if re.search(rf"\b{re.escape(city)}\b", text, re.IGNORECASE):
                        if city not in found_cities and city.replace("ș", "s").replace("ț", "t") not in [c.replace("ș", "s").replace("ț", "t") for c in found_cities]:
                            found_cities.append(city)
                if found_cities:
                    location = ", ".join(found_cities) + ", Romania"

        # Fallback 2: Smart Work Model Detection
        work_model = structured.work_model
        if not work_model or work_model.lower() in ("not specified", "none", ""):
            if any(k in lower_text for k in ["remote", "telemunca", "telemuncă", "de acasa", "de acasă", "work from home", "wfh"]):
                work_model = "Remote"
            elif any(k in lower_text for k in ["hibrid", "hybrid"]):
                work_model = "Hybrid"
            elif any(k in lower_text for k in ["pe teren", "în teren", "in teren", "vizite in teren", "la sediu", "la birou", "pe santier", "pe șantier", "on-site", "onsite", "birou"]):
                work_model = "On-site"

        # Fallback 3: Smart Languages Detection
        languages = list(structured.languages or [])
        if not languages:
            if any(k in lower_text for k in ["cerinte", "cerințe", "responsabilitati", "responsabilități", "candidatului", "experienta", "experiență", "studii", "beneficii"]):
                languages.append("Romanian (fluent)")
            if any(k in lower_text for k in ["engleza", "engleză", "english"]):
                if not any("eng" in l.lower() for l in languages):
                    languages.append("English (advanced)")
            if any(k in lower_text for k in ["germana", "germană", "german", "deutsch"]):
                if not any("ger" in l.lower() or "deutsch" in l.lower() for l in languages):
                    languages.append("German")
            if any(k in lower_text for k in ["franceza", "franceză", "french"]):
                if not any("fran" in l.lower() for l in languages):
                    languages.append("French")

        # Fallback 4: On-site / Location requirement fallback
        has_location_req = any(
            "location" in r.id.lower() or "on-site" in r.id.lower() or "onsite" in r.id.lower()
            for r in job_requirements
        )
        if not has_location_req:
            is_onsite = (
                (work_model and work_model.lower() == "on-site")
                or "requires on-site presence" in lower_text
                or "on-site presence" in lower_text
                or "vizite in teren" in lower_text
                or "pe santier" in lower_text
            )
            if is_onsite and location:
                loc_req = JobRequirement(
                    id="req_location_onsite",
                    title=f"Location & On-Site Presence ({location})",
                    category=RequirementCategory.MUST_HAVE,
                    weight=1.0,
                    description=f"Candidate must be based in or able to work on-site at {location}.",
                    minimum_years_experience=0,
                )
                job_requirements.insert(0, loc_req)
                must_have_count += 1

        # Fallback 5: Seniority & Department Fallbacks
        seniority = structured.seniority_level
        if not seniority:
            t_lower = title.lower()
            if any(k in t_lower for k in ["lead", "coordonator", "coordinator", "manager", "head of", "director", "principal", "architect"]):
                seniority = "Senior"
            elif any(k in t_lower for k in ["senior", "sr."]):
                seniority = "Senior"
            elif any(k in t_lower for k in ["junior", "jr.", "entry", "intern", "trainee", "asistent"]):
                seniority = "Junior"
            elif "mid" in t_lower or "3-5" in lower_text:
                seniority = "Mid-Level"

        department = structured.department
        if not department:
            if "Departament Proiectare" in title or "departament proiectare" in lower_text:
                department = "Departament Proiectare"
            else:
                m_dept = re.search(r"departament(?:ul)?\s+([A-ZĂÎȘȚa-zăîșțâ\s]+)", text, re.IGNORECASE)
                if m_dept:
                    department = m_dept.group(0).strip().title()

        # Fallback 6: Must-have requirement guarantee
        if not job_requirements:
            missing_fields.append("Requirements List")
            warnings.append("No atomic job requirements were found. Please manually add requirements below.")
        elif must_have_count == 0:
            if job_requirements:
                job_requirements[0].category = RequirementCategory.MUST_HAVE
                job_requirements[0].weight = 1.0
                must_have_count = 1
            missing_fields.append("Must-Have Requirements")
            warnings.append("No 'Must-Have' requirements detected. Scoring requires at least one Must-Have criterion.")

        # Check Department, Seniority & Location
        if not department:
            missing_fields.append("Department")

        if not seniority:
            missing_fields.append("Seniority Level")

        if not location:
            missing_fields.append("Location")

        jd = JobDescription(
            id=uuid4(),
            title=title,
            department=department,
            seniority_level=seniority,
            location=location,
            work_model=work_model,
            employment_type=structured.employment_type,
            languages=languages,
            custom_sections=structured.custom_sections,
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
