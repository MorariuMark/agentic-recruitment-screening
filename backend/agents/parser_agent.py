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


def extract_text_from_pdf(pdf_source: Union[str, Path, bytes], max_pages: int = 8) -> str:
    """
    Extracts text from a PDF file path or raw PDF bytes using pdfplumber with pypdf fallback.
    Limits to first max_pages (default 8) to guard against oversized books/handbooks.
    """
    text_content = []

    try:
        import pdfplumber

        if isinstance(pdf_source, (str, Path)):
            with pdfplumber.open(str(pdf_source)) as pdf:
                for page in pdf.pages[:max_pages]:
                    extracted = page.extract_text()
                    if extracted:
                        text_content.append(extracted)
        else:
            with pdfplumber.open(io.BytesIO(pdf_source)) as pdf:
                for page in pdf.pages[:max_pages]:
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
        for page in reader.pages[:max_pages]:
            extracted = page.extract_text()
            if extracted:
                text_content.append(extracted)
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF document: {e}")

    return "\n\n".join(text_content).strip()


def extract_text_from_docx(docx_source: Union[str, Path, bytes]) -> str:
    """
    Extracts text from a DOCX file using python-docx if installed,
    or standard library zipfile + xml.etree.ElementTree as a robust zero-dependency fallback.
    """
    try:
        import docx

        doc_stream = io.BytesIO(docx_source) if isinstance(docx_source, bytes) else docx_source
        doc = docx.Document(doc_stream)
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    paragraphs.append(row_text)
        if paragraphs:
            return "\n".join(paragraphs).strip()
    except Exception:
        pass

    try:
        import xml.etree.ElementTree as ET
        import zipfile

        file_obj = io.BytesIO(docx_source) if isinstance(docx_source, bytes) else open(docx_source, "rb")
        with zipfile.ZipFile(file_obj) as z:
            xml_content = z.read("word/document.xml")
        tree = ET.fromstring(xml_content)
        texts = []
        for elem in tree.iter():
            if elem.tag.endswith("}p"):
                p_text = "".join(node.text for node in elem.iter() if node.text)
                if p_text.strip():
                    texts.append(p_text.strip())
        if not texts:
            texts = [node.text.strip() for node in tree.iter() if node.text and node.text.strip()]
        return "\n".join(texts).strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from DOCX document: {e}")



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
        Applies safe character limits to avoid provider rate/TPM limit errors on oversized inputs.
        """
        if not raw_text or not raw_text.strip():
            raise ValueError("Cannot parse empty CV text.")

        # Cap text at 12,000 characters (~2,800 tokens) to guarantee headroom for the ~1,500 token JSON schema
        trimmed = raw_text.strip()
        max_chars = 12000
        if len(trimmed) > max_chars:
            trimmed = trimmed[:max_chars]

        prompt = f"Extract the structured candidate profile from the following CV text:\n\n{trimmed}"

        try:
            parsed = self.llm_client.generate_structured(
                prompt=prompt,
                response_model=ParsedCV,
                system_prompt=PARSER_SYSTEM_PROMPT,
                temperature=0.0,
            )
        except Exception as err:
            err_str = str(err).lower()
            if "rate_limit" in err_str or "too large" in err_str or "413" in str(err) or "429" in str(err):
                # Fallback: further truncate text and retry
                fallback_prompt = f"Extract the structured candidate profile from the following CV text:\n\n{trimmed[:6000]}"
                parsed = self.llm_client.generate_structured(
                    prompt=fallback_prompt,
                    response_model=ParsedCV,
                    system_prompt=PARSER_SYSTEM_PROMPT,
                    temperature=0.0,
                )
            else:
                raise err

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
        is_docx = False

        if filename:
            fn_lower = filename.lower()
            if fn_lower.endswith(".pdf"):
                is_pdf = True
            elif fn_lower.endswith(".docx"):
                is_docx = True

        if not is_pdf and not is_docx:
            if isinstance(source, (str, Path)):
                src_lower = str(source).lower()
                if src_lower.endswith(".pdf"):
                    is_pdf = True
                elif src_lower.endswith(".docx"):
                    is_docx = True
            elif isinstance(source, bytes):
                if source.startswith(b"%PDF-"):
                    is_pdf = True
                elif source.startswith(b"PK\x03\x04"):
                    is_docx = True

        if is_pdf:
            raw_text = extract_text_from_pdf(source)
        elif is_docx:
            raw_text = extract_text_from_docx(source)
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
