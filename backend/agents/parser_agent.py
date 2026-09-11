"""
backend/agents/parser_agent.py
Parser agent for extracting structured candidate profiles from unstructured CVs
and transforming them into anonymized representations for de-biased matching.
"""

import io
from pathlib import Path
from typing import Optional, Tuple, Union

from backend.agents.llm_factory import BaseLLMClient, get_llm_client
from backend.schemas.cv import AnonymizedCandidate, ParsedCV
from backend.services.pii_scrubber import PIIScrubber


PARSER_SYSTEM_PROMPT = """You are an expert HR Recruitment Parsing Agent.
Your task is to analyze the unstructured text of a candidate's Curriculum Vitae (CV) / Resume
and convert it into a structured JSON representation matching the target schema.

Guidelines:
1. Contact Info: Extract candidate's full name, email, phone number, location, and links (LinkedIn, GitHub, portfolio).
2. Work Experience: For each position held:
   - Identify job_title and company_name accurately.
   - Extract start_date and end_date (or 'Present').
   - Extract specific achievement / responsibility bullet points into work_description.
   - Extract technologies and tools explicitly mentioned in that role into skills_used. Do NOT assign technologies to a past role unless explicitly mentioned in that role's description.
3. Education: Extract degrees, fields of study, institutions, and graduation years.
4. Skills: Aggregate all technical, methodological, and soft skills into a flat list.
5. Certifications: List any professional licenses, certificates, driving licenses, or courses mentioned.
6. Projects: Extract all technical, academic, personal, or open-source projects into projects:
   - project_name: Title of the project.
   - description: Verbatim technical bullets describing architecture, implementation, and features.
   - technologies: Tools, libraries, and frameworks used in the project.
   - start_date, end_date: Dates if provided.
   - project_url: GitHub repository, demo, or publication link.
7. Languages: Extract all spoken and written language competencies into languages (e.g. language: "English", proficiency: "C1"; language: "Romanian", proficiency: "Native").
8. Custom Sections (Fallback for unmapped categories): Extract ANY other sections with professional, technical, or community relevance into custom_sections (e.g. "Volunteering", "Honors & Awards", "Publications", "Patents", "Hackathons", "Conferences", "Extracurriculars"). Set section_title, list of bullet items, and is_relevant=True.
9. Summary: Include the professional bio, objective, or 'about me' if present.
10. Unused Details: Identify purely personal, demographic, or administrative items (date of birth, place of birth, nationality, gender, marital status, street address, work permit/visa) and extract them into unused_details.
11. Preserve exact wording where possible for verifiable grounding. Do not hallucinate qualifications."""


def extract_text_from_pdf(pdf_source: Union[str, Path, bytes]) -> str:
    """
    Extracts text from a PDF file path or raw PDF bytes using pdfplumber with pypdf fallback.
    """
    text_content = []

    try:
        import pdfplumber

        if isinstance(pdf_source, (str, Path)):
            with pdfplumber.open(str(pdf_source)) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content.append(extracted)
        else:
            with pdfplumber.open(io.BytesIO(pdf_source)) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content.append(extracted)

        if text_content:
            return "\n\n".join(text_content).strip()
    except Exception:
        pass

    # Fallback to pypdf if pdfplumber fails or returns empty
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_source if isinstance(pdf_source, (str, Path)) else io.BytesIO(pdf_source))
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_content.append(extracted)
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF document: {e}")

    return "\n\n".join(text_content).strip()


class ParserAgent:
    """Agent that orchestrates text extraction, LLM structured parsing, and PII anonymization."""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        pii_scrubber: Optional[PIIScrubber] = None,
    ) -> None:
        self.llm_client = llm_client or get_llm_client()
        self.pii_scrubber = pii_scrubber or PIIScrubber()

    def parse_cv_text(self, raw_text: str) -> ParsedCV:
        """
        Invokes LLM structured generation to parse raw CV text into a ParsedCV object.
        """
        if not raw_text or not raw_text.strip():
            raise ValueError("Cannot parse empty CV text.")

        prompt = f"Extract the structured candidate profile from the following CV text:\n\n{raw_text.strip()}"

        parsed = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=ParsedCV,
            system_prompt=PARSER_SYSTEM_PROMPT,
            temperature=0.0,
        )
        parsed.raw_text = raw_text
        return parsed

    def parse_and_anonymize(
        self,
        source: Union[str, Path, bytes],
        filename: Optional[str] = None,
    ) -> Tuple[ParsedCV, AnonymizedCandidate]:
        """
        Full pipeline:
        1. Extract text if PDF, or read text directly.
        2. Run LLM structured extraction to produce ParsedCV.
        3. Run deterministic PII scrubber to produce AnonymizedCandidate.

        Returns:
            Tuple of (raw ParsedCV, sanitized AnonymizedCandidate).
        """
        # 1. Determine input type and extract text
        is_pdf = False
        if filename and filename.lower().endswith(".pdf"):
            is_pdf = True
        elif isinstance(source, (str, Path)) and str(source).lower().endswith(".pdf"):
            is_pdf = True
        elif isinstance(source, bytes) and source.startswith(b"%PDF-"):
            is_pdf = True

        if is_pdf:
            raw_text = extract_text_from_pdf(source)
        elif isinstance(source, bytes):
            try:
                raw_text = source.decode("utf-8")
            except UnicodeDecodeError:
                raw_text = source.decode("latin-1", errors="ignore")
        elif isinstance(source, Path) or (isinstance(source, str) and Path(source).exists()):
            with open(source, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()
        else:
            raw_text = str(source)

        # 2. Extract structured profile via LLM
        parsed_cv = self.parse_cv_text(raw_text)

        # 3. Anonymize PII and demographic markers
        anonymized_candidate = self.pii_scrubber.anonymize_cv(parsed_cv)

        return parsed_cv, anonymized_candidate
