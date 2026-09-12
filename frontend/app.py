"""
frontend/app.py
Recruiter Dashboard for Agentic Recruitment Screening,
Semantic Matching, Human-in-the-Loop (HITL) Validation, and Interview Guide Synthesis.
"""

import json
import os
import subprocess
import sys
import time
from uuid import UUID, uuid4

import streamlit as st

from backend.schemas.cv import AnonymizedCandidate, ParsedCV
from backend.schemas.interview import InterviewPlan, QuestionArchetype
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import MatchEvaluationResult, MatchStatus, Recommendation
from frontend.api_client import BackendAPIClient

# Configure page layout
st.set_page_config(
    page_title="Recruitment Screening Agent",
    page_icon="none",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Enterprise CSS Design System
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Header styling */
    .page-header {
        margin-bottom: 1.75rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid rgba(140, 150, 170, 0.2);
    }
    .page-title {
        font-size: 1.65rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        margin-bottom: 0.25rem;
    }
    .page-subtitle {
        font-size: 0.9rem;
        color: #64748b;
        margin-bottom: 0;
    }

    /* Card containers */
    .app-card {
        background: rgba(140, 150, 170, 0.05);
        border: 1px solid rgba(140, 150, 170, 0.18);
        border-radius: 8px;
        padding: 1.15rem;
        margin-bottom: 1rem;
    }
    .app-card-title {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #64748b;
        margin-bottom: 0.6rem;
    }

    /* Refined Status Badges & Pills */
    .badge {
        display: inline-flex;
        align-items: center;
        padding: 0.2rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.025em;
        line-height: 1.4;
        transition: all 0.2s ease;
    }
    .badge-must {
        background: rgba(99, 102, 241, 0.15);
        color: #a5b4fc;
        border: 1px solid rgba(99, 102, 241, 0.35);
    }
    .badge-nice {
        background: rgba(148, 163, 184, 0.12);
        color: #94a3b8;
        border: 1px solid rgba(148, 163, 184, 0.22);
    }
    .badge-soft {
        background: rgba(168, 85, 247, 0.12);
        color: #c084fc;
        border: 1px solid rgba(168, 85, 247, 0.25);
    }
    .badge-met {
        background: rgba(16, 185, 129, 0.12);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.28);
    }
    .badge-partial {
        background: rgba(245, 158, 11, 0.12);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.28);
    }
    .badge-gap {
        background: rgba(239, 68, 68, 0.12);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.28);
    }
    .badge-verified {
        background: rgba(16, 185, 129, 0.14);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-unverified {
        background: rgba(245, 158, 11, 0.12);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.28);
    }

    /* Workflow Tracker items */
    .wf-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.45rem 0.65rem;
        margin-bottom: 0.4rem;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        transition: all 0.2s ease;
    }
    .wf-item:hover {
        background: rgba(255, 255, 255, 0.04);
        border-color: rgba(255, 255, 255, 0.1);
    }
    .wf-left {
        display: flex;
        align-items: center;
    }
    .wf-num {
        font-family: monospace;
        font-size: 0.72rem;
        font-weight: 700;
        color: #818cf8;
        margin-right: 0.55rem;
    }
    .wf-title {
        font-size: 0.8rem;
        font-weight: 500;
        color: #e2e8f0;
    }

    /* Status dot */
    .status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
    }
    .status-dot-online {
        background: #10b981;
        box-shadow: 0 0 6px rgba(16, 185, 129, 0.7);
    }
    .status-dot-offline {
        background: #ef4444;
        box-shadow: 0 0 6px rgba(239, 68, 68, 0.7);
    }

    /* Tag pills */
    .tag-pill {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        margin: 0.15rem;
        background: rgba(140, 150, 170, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 9999px;
        font-size: 0.76rem;
        font-weight: 500;
    }

    /* Citation callout */
    .citation-block {
        border-left: 3px solid #3b82f6;
        padding: 0.6rem 1rem;
        margin: 0.5rem 0;
        background: rgba(59, 130, 246, 0.05);
        border-radius: 0 6px 6px 0;
        font-size: 0.88rem;
    }
    .citation-meta {
        font-size: 0.75rem;
        color: #64748b;
        margin-top: 0.35rem;
    }

    /* Metric clean typography */
    [data-testid="stMetricValue"] {
        font-size: 1.55rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        color: #64748b !important;
    }

    /* Modern, Sleek Buttons */
    div[data-testid="stButton"] > button,
    div[data-testid="stDownloadButton"] > button,
    div[data-testid="stFormSubmitButton"] > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        letter-spacing: 0.015em !important;
        padding: 0.42rem 0.95rem !important;
        min-height: 2.3rem !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        background: rgba(255, 255, 255, 0.04) !important;
        color: #f1f5f9 !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    div[data-testid="stButton"] > button:hover,
    div[data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {
        background: rgba(255, 255, 255, 0.09) !important;
        border-color: rgba(99, 102, 241, 0.5) !important;
        color: #ffffff !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
    }
    div[data-testid="stButton"] > button:active,
    div[data-testid="stDownloadButton"] > button:active,
    div[data-testid="stFormSubmitButton"] > button:active {
        transform: translateY(0) !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2) !important;
    }

    /* Primary Buttons */
    div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%) !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3) !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover,
    div[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%) !important;
        border-color: rgba(255, 255, 255, 0.3) !important;
        box-shadow: 0 6px 16px rgba(79, 70, 229, 0.45) !important;
        transform: translateY(-1.5px) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

api_client = BackendAPIClient()


def launch_fastapi_backend() -> bool:
    """Spawns the FastAPI backend server as a background process and polls health until ready."""
    venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    flags = 0
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    try:
        subprocess.Popen(
            [
                venv_python,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=os.getcwd(),
            creationflags=flags,
            close_fds=(os.name != "nt"),
        )
    except Exception:
        return False

    for _ in range(16):
        time.sleep(0.5)
        h = api_client.health_check()
        if h.get("status") == "ok":
            return True
    return False


# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "candidate_id" not in st.session_state:
    st.session_state.candidate_id = None
if "parsed_cv" not in st.session_state:
    st.session_state.parsed_cv = None
if "anonymized_candidate" not in st.session_state:
    st.session_state.anonymized_candidate = None
if "evaluation_result" not in st.session_state:
    st.session_state.evaluation_result = None
if "interview_plan" not in st.session_state:
    st.session_state.interview_plan = None
if "jd_warnings" not in st.session_state:
    st.session_state.jd_warnings = []
if "jd_missing_fields" not in st.session_state:
    st.session_state.jd_missing_fields = []
if "job_description" not in st.session_state:
    st.session_state.job_description = JobDescription(
        id=uuid4(),
        title="Senior AI Platform Engineer",
        department="AI & Cloud Innovation",
        seniority_level="Senior",
        requirements=[
            JobRequirement(
                id="req_rag_python",
                title="RAG Systems & Vector Search",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Proven experience building production RAG pipelines with Python, ChromaDB, or similar vector stores.",
                minimum_years_experience=3,
            ),
            JobRequirement(
                id="req_fastapi_backend",
                title="FastAPI & Async Microservices",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Hands-on experience designing REST APIs and asynchronous microservices with FastAPI and Pydantic.",
                minimum_years_experience=3,
            ),
            JobRequirement(
                id="req_k8s_docker",
                title="Container Orchestration",
                category=RequirementCategory.NICE_TO_HAVE,
                weight=0.8,
                description="Experience containerizing applications with Docker and deploying to Kubernetes clusters.",
                minimum_years_experience=2,
            ),
            JobRequirement(
                id="req_soft_collab",
                title="Technical Mentorship & Collaboration",
                category=RequirementCategory.SOFT_SKILL,
                weight=0.5,
                description="Ability to mentor junior engineers and collaborate effectively across distributed product teams.",
                minimum_years_experience=None,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Sidebar: System Status & Workflow Navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Screening Agent")
    st.caption("Enterprise AI Recruitment Platform")
    st.markdown("---")

    health = api_client.health_check()
    is_backend_online = (health.get("status") == "ok")

    if is_backend_online:
        st.markdown(
            f"""
            <div class="app-card" style="padding: 0.85rem; margin-bottom: 0.85rem;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.55rem;">
                    <span style="font-weight: 600; font-size: 0.78rem; letter-spacing: 0.04em; color: #94a3b8; text-transform: uppercase;">System Status</span>
                    <span class="badge badge-met"><span class="status-dot status-dot-online"></span>Online</span>
                </div>
                <div style="font-size: 0.76rem; color: #94a3b8; line-height: 1.6;">
                    <div style="display: flex; justify-content: space-between;"><span>Provider</span><strong style="color: #f1f5f9;">{health.get('llm_provider', 'unknown')}</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span>Model</span><strong style="color: #f1f5f9;">{health.get('model', 'default').split('/')[-1]}</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span>Mode</span><strong style="color: #f1f5f9;">{health.get('compatibility_mode', 'auto')}</strong></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="app-card" style="padding: 0.85rem; margin-bottom: 0.85rem;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.55rem;">
                    <span style="font-weight: 600; font-size: 0.78rem; letter-spacing: 0.04em; color: #94a3b8; text-transform: uppercase;">System Status</span>
                    <span class="badge badge-gap"><span class="status-dot status-dot-offline"></span>Offline</span>
                </div>
                <div style="font-size: 0.76rem; color: #94a3b8; line-height: 1.4;">
                    Backend service unreachable on port 8000.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Start Backend Server", use_container_width=True, key="sb_start_backend"):
            with st.spinner("Starting FastAPI backend service..."):
                if launch_fastapi_backend():
                    st.success("Backend started.")
                    st.rerun()
                else:
                    st.error("Could not reach backend. Run 'python start.py' in a terminal.")

    st.markdown("---")
    st.markdown("<div class='app-card-title' style='margin-bottom: 0.5rem;'>Screening Workflow</div>", unsafe_allow_html=True)

    # Workflow tracker
    c_cand = "badge-met" if st.session_state.candidate_id else "badge-nice"
    t_cand = "Ready" if st.session_state.candidate_id else "Pending"

    c_jd = "badge-met" if st.session_state.job_description else "badge-nice"
    t_jd = f"{len(st.session_state.job_description.requirements)} Criteria" if st.session_state.job_description else "Default"

    c_eval = "badge-met" if st.session_state.evaluation_result else "badge-nice"
    t_eval = f"{st.session_state.evaluation_result.overall_score}%" if st.session_state.evaluation_result else "Pending"

    c_hitl = "badge-met" if (st.session_state.evaluation_result and st.session_state.evaluation_result.hitl_validated) else "badge-nice"
    t_hitl = "Reviewed" if (st.session_state.evaluation_result and st.session_state.evaluation_result.hitl_validated) else "Pending"

    c_plan = "badge-met" if st.session_state.interview_plan else "badge-nice"
    t_plan = f"{len(st.session_state.interview_plan.questions)} Qs" if st.session_state.interview_plan else "Pending"

    st.markdown(
        f"""
        <div style="margin-top: 0.4rem;">
            <div class="wf-item">
                <div class="wf-left">
                    <span class="wf-num">01</span>
                    <span class="wf-title">Candidate Ingestion</span>
                </div>
                <span class="badge {c_cand}">{t_cand}</span>
            </div>
            <div class="wf-item">
                <div class="wf-left">
                    <span class="wf-num">02</span>
                    <span class="wf-title">Job Specification</span>
                </div>
                <span class="badge {c_jd}">{t_jd}</span>
            </div>
            <div class="wf-item">
                <div class="wf-left">
                    <span class="wf-num">03</span>
                    <span class="wf-title">Semantic Matching</span>
                </div>
                <span class="badge {c_eval}">{t_eval}</span>
            </div>
            <div class="wf-item">
                <div class="wf-left">
                    <span class="wf-num">04</span>
                    <span class="wf-title">Recruiter Review</span>
                </div>
                <span class="badge {c_hitl}">{t_hitl}</span>
            </div>
            <div class="wf-item">
                <div class="wf-left">
                    <span class="wf-num">05</span>
                    <span class="wf-title">Interview Guide</span>
                </div>
                <span class="badge {c_plan}">{t_plan}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    if st.button("Reset Workspace", use_container_width=True):
        st.session_state.candidate_id = None
        st.session_state.parsed_cv = None
        st.session_state.anonymized_candidate = None
        st.session_state.evaluation_result = None
        st.session_state.interview_plan = None
        st.session_state.jd_warnings = []
        st.session_state.jd_missing_fields = []
        st.rerun()


# ---------------------------------------------------------------------------
# Main Application Tabs
# ---------------------------------------------------------------------------
tab_cv, tab_jd, tab_match, tab_hitl, tab_interview, tab_settings = st.tabs([
    "Candidate Profile",
    "Job Specification",
    "Semantic Evaluation",
    "Human Review",
    "Interview Guide",
    "Model Settings",
])


# ---------------------------------------------------------------------------
# TAB 1: Candidate Ingestion & Profile Anonymization
# ---------------------------------------------------------------------------
with tab_cv:
    st.markdown(
        """
        <div class="page-header">
            <div class="page-title">Candidate Profile Ingestion</div>
            <div class="page-subtitle">Extract structured candidate profile, isolate personal identifiers, and generate audit-ready embeddings.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_upload, col_sample = st.columns([1.4, 1])

    with col_upload:
        st.markdown("<div class='app-card-title'>Upload Document</div>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            "Select Resume or CV File",
            type=["pdf", "docx", "txt", "md", "json"],
            label_visibility="collapsed",
            help="Supported formats: PDF, DOCX, TXT, Markdown, JSON Resume",
        )

    with col_sample:
        st.markdown("<div class='app-card-title'>Or Select Benchmark Profile</div>", unsafe_allow_html=True)
        sample_options = {
            "Strong AI Platform Engineer (EN)": "data/mock_cvs/strong_ai_engineer.txt",
            "Borderline Junior Developer (EN)": "data/mock_cvs/borderline_junior_developer.txt",
            "Unrelated Domain - Accountant (EN)": "data/mock_cvs/reject_unrelated_candidate.txt",
            "Senior Backend AI Engineer (RO)": "data/test_resumes/Inginer_Software_Senior_Alexandru_Ionescu_RO.txt",
            "Senior Cloud & DevOps Engineer (DE)": "data/test_resumes/Senior_Cloud_DevOps_Engineer_Maximilian_Weber_DE.txt",
            "Fullstack Project Lead (FR)": "data/test_resumes/Cheffe_de_Projet_Fullstack_Claire_Dubois_FR.txt",
            "Accountant Resume (EN)": "data/test_resumes/Real_Resume_Accountant_EN.txt",
            "Standard JSON Resume (EN)": "data/test_resumes/JSON_Resume_Standard_Schema_EN.json",
        }
        selected_sample_label = st.selectbox("Sample Profiles", list(sample_options.keys()), label_visibility="collapsed")
        selected_sample_path = sample_options[selected_sample_label]

    st.write("")
    if st.button("Ingest Profile", type="primary"):
        with st.spinner("Parsing document structure and isolating personal data..."):
            try:
                if uploaded_file:
                    file_bytes = uploaded_file.getvalue()
                    filename = uploaded_file.name
                else:
                    with open(selected_sample_path, "rb") as f:
                        file_bytes = f.read()
                    filename = selected_sample_path.split("/")[-1]

                result = api_client.upload_cv(file_bytes, filename)
                st.session_state.candidate_id = UUID(result["candidate_id"])
                st.session_state.parsed_cv = ParsedCV.model_validate(result["parsed_cv"])
                st.session_state.anonymized_candidate = AnonymizedCandidate.model_validate(result["anonymized_candidate"])
                st.success(f"Candidate profile processed. ID: {st.session_state.candidate_id} ({result['chunks_indexed']} chunks indexed)")
                st.rerun()
            except Exception as e:
                st.error(f"Ingestion failed: {e}")

    if st.session_state.anonymized_candidate:
        st.markdown("---")
        col_raw, col_clean = st.columns(2)

        with col_raw:
            st.markdown("<div class='app-card-title'>Isolated Contact Information (PII)</div>", unsafe_allow_html=True)
            contact = st.session_state.parsed_cv.contact_info if st.session_state.parsed_cv else None
            if contact:
                phone_display = getattr(contact, "phone_number", None) or getattr(contact, "phone", None) or "Not provided"
                st.markdown(
                    f"""
                    <div class="app-card">
                        <div style="font-size: 0.88rem; line-height: 1.8;">
                            <div><strong>Full Name:</strong> {contact.full_name or 'N/A'}</div>
                            <div><strong>Email Address:</strong> {contact.email or 'N/A'}</div>
                            <div><strong>Phone:</strong> {phone_display}</div>
                            <div><strong>Location:</strong> {contact.location or 'N/A'}</div>
                            <div><strong>LinkedIn:</strong> {contact.linkedin_url or 'N/A'}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with col_clean:
            st.markdown("<div class='app-card-title'>Anonymized Profile (Passed to Inference)</div>", unsafe_allow_html=True)
            skills_html = "".join([f"<span class='tag-pill'>{s}</span>" for s in st.session_state.anonymized_candidate.anonymized_skills])
            langs = getattr(st.session_state.anonymized_candidate, "anonymized_languages", [])
            lang_str = ", ".join([f"{l.language} ({l.proficiency})" if l.proficiency else l.language for l in langs]) or "Not specified"
            demo_str = st.session_state.anonymized_candidate.demographic_data or "None detected"

            st.markdown(
                f"""
                <div class="app-card">
                    <div style="font-size: 0.88rem; line-height: 1.8;">
                        <div><strong>Candidate ID:</strong> <code>{st.session_state.anonymized_candidate.candidate_id}</code></div>
                        <div style="margin-top: 0.35rem; margin-bottom: 0.35rem;"><strong>Identified Skills:</strong><br/>{skills_html}</div>
                        <div><strong>Languages:</strong> {lang_str}</div>
                        <div><strong>Demographic Audit:</strong> {demo_str}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with st.expander(f"Work Experience ({len(st.session_state.anonymized_candidate.anonymized_work_experiences)} roles)", expanded=False):
            for exp in st.session_state.anonymized_candidate.anonymized_work_experiences:
                st.markdown(f"**{exp.job_title}** - {exp.company_name}")
                st.caption(f"{exp.start_date or ''} - {exp.end_date or ''}")
                for bullet in exp.work_description:
                    st.markdown(f"- {bullet}")
                st.write("")

        projects = getattr(st.session_state.anonymized_candidate, "anonymized_projects", [])
        if projects:
            with st.expander(f"Projects ({len(projects)})", expanded=False):
                for proj in projects:
                    st.markdown(f"**{proj.project_name}**")
                    if proj.technologies:
                        tech_tags = " ".join([f"`{t}`" for t in proj.technologies])
                        st.caption(f"Technologies: {tech_tags}")
                    if proj.project_url:
                        st.caption(f"Repository: `{proj.project_url}`")
                    for bullet in proj.description:
                        st.markdown(f"- {bullet}")
                    st.write("")

        custom_secs = getattr(st.session_state.anonymized_candidate, "anonymized_custom_sections", [])
        if custom_secs:
            with st.expander(f"Additional Sections ({len(custom_secs)})", expanded=False):
                for sec in custom_secs:
                    st.markdown(f"**{sec.section_title}**")
                    for it in sec.items:
                        st.markdown(f"- {it}")

        st.markdown("---")
        col_cv_info, col_cv_btn = st.columns([2.5, 1])
        with col_cv_info:
            st.markdown("**Annotated Profile JSON**")
            st.caption("Includes provenance metadata: anonymised, visible, unused, and extra tags.")
        with col_cv_btn:
            try:
                cv_export_payload = api_client.export_candidate_cv(st.session_state.candidate_id)
                st.download_button(
                    label="Download Profile JSON",
                    data=json.dumps(cv_export_payload, indent=2),
                    file_name=f"candidate_{st.session_state.candidate_id}_tagged.json",
                    mime="application/json",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Export failed: {e}")


# ---------------------------------------------------------------------------
# TAB 2: Job Specification Setup
# ---------------------------------------------------------------------------
with tab_jd:
    st.markdown(
        """
        <div class="page-header">
            <div class="page-title">Job Specification</div>
            <div class="page-subtitle">Configure role parameters, atomic evaluation requirements, and scoring weights.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    import_tab_url, import_tab_text = st.tabs(["Import from Web URL", "Paste Job Description"])

    with import_tab_url:
        col_url, col_fetch = st.columns([3, 1])
        with col_url:
            job_url_input = st.text_input(
                "Job Posting URL",
                placeholder="https://company.com/careers/senior-ai-engineer",
                label_visibility="collapsed",
            )
        with col_fetch:
            fetch_btn = st.button("Fetch & Extract", use_container_width=True)

        if fetch_btn:
            if not job_url_input or not job_url_input.strip():
                st.error("Please provide a valid URL.")
            else:
                with st.spinner("Extracting role criteria from URL..."):
                    try:
                        res = api_client.parse_job_url(job_url_input)
                        st.session_state.job_description = JobDescription.model_validate(res["job_description"])
                        st.session_state.jd_missing_fields = res.get("missing_fields", [])
                        st.session_state.jd_warnings = res.get("warnings", [])
                        st.success(f"Job posting extracted. {len(st.session_state.job_description.requirements)} requirements identified.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Extraction failed: {e}")
                        st.caption("If the site blocks automated requests, paste the description text in the adjacent tab.")

    with import_tab_text:
        raw_jd_paste = st.text_area(
            "Raw Job Description Text",
            placeholder="Paste complete job description, responsibilities, and required qualifications...",
            height=130,
            label_visibility="collapsed",
        )
        if st.button("Parse Job Text", use_container_width=True):
            if not raw_jd_paste or not raw_jd_paste.strip():
                st.error("Please paste job description text first.")
            else:
                with st.spinner("Decomposing text into atomic criteria..."):
                    try:
                        res = api_client.parse_job_text(raw_jd_paste)
                        st.session_state.job_description = JobDescription.model_validate(res["job_description"])
                        st.session_state.jd_missing_fields = res.get("missing_fields", [])
                        st.session_state.jd_warnings = res.get("warnings", [])
                        st.success(f"Job text parsed. {len(st.session_state.job_description.requirements)} requirements identified.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Parsing failed: {e}")

    if st.session_state.jd_warnings:
        bullets = " | ".join(st.session_state.jd_warnings)
        st.warning(f"Incomplete Details: {bullets}. Please verify position metadata below.")

    jd = st.session_state.job_description

    st.markdown("<div class='app-card-title' style='margin-top: 1rem;'>Position Details</div>", unsafe_allow_html=True)
    col_t1, col_t2, col_t3 = st.columns([2, 1, 1])
    with col_t1:
        jd.title = st.text_input("Job Title", value=jd.title)
    with col_t2:
        jd.department = st.text_input("Department", value=jd.department or "")
    with col_t3:
        jd.seniority_level = st.text_input("Seniority Level", value=jd.seniority_level or "")

    col_m1, col_m2, col_m3 = st.columns([2, 1, 1])
    with col_m1:
        jd.location = st.text_input("Location", value=getattr(jd, "location", "") or "", placeholder="e.g. Remote / Timisoara, Romania")
    with col_m2:
        work_models = ["Not specified", "On-site", "Hybrid", "Remote"]
        current_wm = getattr(jd, "work_model", "") or "Not specified"
        wm_idx = work_models.index(current_wm) if current_wm in work_models else 0
        chosen_wm = st.selectbox("Work Model", work_models, index=wm_idx)
        jd.work_model = None if chosen_wm == "Not specified" else chosen_wm
    with col_m3:
        emp_types = ["Full-time", "Part-time", "Contract", "Internship"]
        current_et = getattr(jd, "employment_type", "") or "Full-time"
        et_idx = emp_types.index(current_et) if current_et in emp_types else 0
        jd.employment_type = st.selectbox("Employment Type", emp_types, index=et_idx)

    st.markdown("<div class='app-card-title' style='margin-top: 1.5rem;'>Atomic Criteria & Weights</div>", unsafe_allow_html=True)

    reqs_to_remove = []
    for idx, req in enumerate(jd.requirements):
        category_label = req.category.value.replace("_", "-").upper()

        with st.expander(f"{idx + 1}. {req.title} [{category_label}]", expanded=False):
            cols = st.columns([2.6, 1.2, 1, 0.5])
            with cols[0]:
                req.title = st.text_input(f"Title", value=req.title, key=f"req_t_{req.id}_{idx}")
                req.description = st.text_area(f"Description", value=req.description, height=65, key=f"req_d_{req.id}_{idx}")
            with cols[1]:
                req.category = RequirementCategory(
                    st.selectbox(
                        f"Category",
                        [c.value for c in RequirementCategory],
                        index=[c.value for c in RequirementCategory].index(req.category.value),
                        key=f"req_c_{req.id}_{idx}",
                    )
                )
                if req.category == RequirementCategory.MUST_HAVE:
                    req.weight = 1.0
                elif req.category == RequirementCategory.NICE_TO_HAVE:
                    req.weight = 0.8
                else:
                    req.weight = 0.5
            with cols[2]:
                req.minimum_years_experience = st.number_input(
                    f"Min Experience (Years)",
                    min_value=0,
                    max_value=20,
                    value=req.minimum_years_experience or 0,
                    key=f"req_y_{req.id}_{idx}",
                )
            with cols[3]:
                st.write("")
                st.write("")
                if st.button("Delete", key=f"del_{req.id}_{idx}", use_container_width=True):
                    reqs_to_remove.append(idx)

    if reqs_to_remove:
        for r_idx in sorted(reqs_to_remove, reverse=True):
            jd.requirements.pop(r_idx)
        st.rerun()

    col_add, col_audit = st.columns([1, 1])
    with col_add:
        if st.button("Add Requirement", use_container_width=True):
            new_num = len(jd.requirements) + 1
            jd.requirements.append(
                JobRequirement(
                    id=f"req_manual_{new_num}",
                    title=f"New Requirement {new_num}",
                    category=RequirementCategory.MUST_HAVE,
                    weight=1.0,
                    description="Specify qualifications or capabilities.",
                    minimum_years_experience=0,
                )
            )
            st.rerun()

    with col_audit:
        if st.session_state.jd_warnings:
            if st.button("Clear Warnings & Validate", use_container_width=True):
                must_haves = [r for r in jd.requirements if r.category == RequirementCategory.MUST_HAVE]
                if not jd.title or jd.title.strip() in {"", "Untitled Position"}:
                    st.error("Please specify a Job Title.")
                elif not must_haves:
                    st.error("At least one requirement must be Must-Have.")
                else:
                    st.session_state.jd_warnings = []
                    st.session_state.jd_missing_fields = []
                    st.success("Job specification validated.")
                    st.rerun()

    st.markdown("---")
    col_jd_info, col_jd_btn = st.columns([2.5, 1])
    with col_jd_info:
        st.markdown("**Annotated Job Specification JSON**")
        st.caption("Downloads all criteria with assigned weights and category metadata.")
    with col_jd_btn:
        try:
            jd_export_payload = api_client.export_job_description(jd)
            st.download_button(
                label="Download Job JSON",
                data=json.dumps(jd_export_payload, indent=2),
                file_name="job_description_tagged.json",
                mime="application/json",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Export failed: {e}")


# ---------------------------------------------------------------------------
# TAB 3: Semantic Evaluation & Grounding
# ---------------------------------------------------------------------------
with tab_match:
    st.markdown(
        """
        <div class="page-header">
            <div class="page-title">Semantic Evaluation & Citations</div>
            <div class="page-subtitle">Asymmetric semantic retrieval and LLM evaluation with verbatim citation verification.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.candidate_id:
        st.info("Ingest a candidate profile in the Candidate Profile tab first.")
    else:
        if st.button("Run Semantic Evaluation", type="primary"):
            with st.spinner("Retrieving candidate chunks from vector store and evaluating criteria..."):
                try:
                    eval_result = api_client.evaluate_match(
                        candidate_id=st.session_state.candidate_id,
                        job_description=st.session_state.job_description,
                    )
                    st.session_state.evaluation_result = eval_result
                    st.success("Evaluation complete.")
                except Exception as e:
                    st.error(f"Evaluation failed: {e}")

        if st.session_state.evaluation_result:
            res = st.session_state.evaluation_result

            # Top KPI metrics
            st.markdown("<div class='app-card-title' style='margin-top: 1rem;'>Evaluation Summary</div>", unsafe_allow_html=True)
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Overall Score", f"{res.overall_score}%")
            m_col2.metric("Must-Have Score", f"{res.must_have_score}%")
            m_col3.metric("Nice-to-Have Score", f"{res.nice_to_have_score}%")
            cvs_pct = round(res.citation_verification_score * 100.0, 1)
            m_col4.metric("Citation Grounding", f"{cvs_pct}%")

            # Recommendation Banner
            rec = res.recommendation.value
            if rec == "strong_match":
                badge_style = "badge-met"
                rec_title = f"Strong Match - Candidate exceeds benchmark ({res.overall_score}%)"
            elif rec == "borderline":
                badge_style = "badge-partial"
                rec_title = f"Borderline - Review required ({res.must_have_gaps_count} Must-Have gaps)"
            else:
                badge_style = "badge-gap"
                rec_title = f"Unqualified - Score below threshold ({res.overall_score}%)"

            st.markdown(
                f"""
                <div class="app-card" style="margin-top: 0.75rem; display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <div style="font-size: 0.75rem; text-transform: uppercase; color: #64748b; font-weight: 600;">System Recommendation</div>
                        <div style="font-size: 1.05rem; font-weight: 700; margin-top: 0.2rem;">{rec_title}</div>
                    </div>
                    <span class="badge {badge_style}" style="font-size: 0.85rem; padding: 0.35rem 0.75rem;">{rec.replace('_', ' ').upper()}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("<div class='app-card-title' style='margin-top: 1.5rem;'>Requirement Breakdown & Verbatim Citations</div>", unsafe_allow_html=True)

            for match in res.requirement_matches:
                req_obj = next((r for r in st.session_state.job_description.requirements if r.id == match.requirement_id), None)
                req_title = req_obj.title if req_obj else match.requirement_id

                status_badge = "badge-met" if match.status == MatchStatus.MET else ("badge-partial" if match.status == MatchStatus.PARTIAL else "badge-gap")

                with st.expander(f"{req_title} - {match.status.value.upper()} ({int(match.score * 100)}%)"):
                    st.markdown(f"**Reasoning:** {match.reasoning}")
                    if match.gap_analysis:
                        st.markdown(
                            f"""
                            <div style="padding: 0.5rem 0.75rem; background: rgba(239, 68, 68, 0.06); border-left: 3px solid #ef4444; border-radius: 4px; margin: 0.5rem 0; font-size: 0.88rem;">
                                <strong>Gap Analysis:</strong> {match.gap_analysis}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    st.markdown("<div style='font-size: 0.8rem; font-weight: 600; text-transform: uppercase; color: #64748b; margin-top: 0.75rem;'>Verbatim Resume Citations</div>", unsafe_allow_html=True)
                    if match.citations:
                        for cit in match.citations:
                            badge_cls = "badge-verified" if cit.verified else "badge-unverified"
                            badge_txt = "Verified Substring" if cit.verified else "Unverified"
                            sec_txt = cit.source_section or "Profile"
                            st.markdown(
                                f"""
                                <div class="citation-block">
                                    "{cit.quote}"
                                    <div class="citation-meta">
                                        <span class="badge {badge_cls}">{badge_txt}</span> - Source: {sec_txt}
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("No direct evidence cited from candidate profile.")


# ---------------------------------------------------------------------------
# TAB 4: Recruiter Human-in-the-Loop (HITL) Gate
# ---------------------------------------------------------------------------
with tab_hitl:
    st.markdown(
        """
        <div class="page-header">
            <div class="page-title">Recruiter Human-in-the-Loop Review</div>
            <div class="page-subtitle">Verify AI recommendation signals, apply human overrides, and maintain an immutable audit trail.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.evaluation_result:
        st.info("Run semantic evaluation in the Semantic Evaluation tab first.")
    else:
        eval_res = st.session_state.evaluation_result

        h_status_cls = "badge-met" if eval_res.hitl_validated else "badge-partial"
        h_status_txt = "Validated by Human" if eval_res.hitl_validated else "Pending Review"

        st.markdown(
            f"""
            <div class="app-card" style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 0.88rem; line-height: 1.6;">
                    <div><strong>Evaluation ID:</strong> <code>{eval_res.id}</code></div>
                    <div><strong>Algorithm Recommendation:</strong> <strong>{eval_res.recommendation.value.replace('_', ' ').upper()}</strong></div>
                </div>
                <span class="badge {h_status_cls}" style="font-size: 0.85rem; padding: 0.35rem 0.75rem;">{h_status_txt}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='app-card-title' style='margin-top: 1.25rem;'>Final Decision & Audit Trail</div>", unsafe_allow_html=True)

        recruiter_override = st.selectbox(
            "Recruiter Determination",
            options=[r.value for r in Recommendation],
            index=[r.value for r in Recommendation].index(eval_res.recommendation.value),
            format_func=lambda v: v.replace("_", " ").title(),
            help="Select final recruiter decision (confirms or overrides AI score)",
        )

        recruiter_notes = st.text_area(
            "Audit Justification & Notes",
            value=eval_res.recruiter_notes or "",
            placeholder="Document rationale for approval, reservation, or rejection...",
            height=100,
        )

        if st.button("Record Decision", type="primary"):
            try:
                updated = api_client.submit_hitl_decision(
                    evaluation_id=eval_res.id,
                    recruiter_decision=Recommendation(recruiter_override),
                    recruiter_notes=recruiter_notes,
                )
                st.session_state.evaluation_result = updated
                st.success(f"Determination recorded: {updated.recommendation.value.replace('_', ' ').upper()}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to record determination: {e}")


# ---------------------------------------------------------------------------
# TAB 5: Tailored Interview Guide
# ---------------------------------------------------------------------------
with tab_interview:
    st.markdown(
        """
        <div class="page-header">
            <div class="page-title">Tailored Interview Guide</div>
            <div class="page-subtitle">Dynamic technical and behavioral questions synthesized specifically to probe candidate gaps.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.evaluation_result:
        st.info("Complete candidate evaluation and review first.")
    else:
        duration = st.slider("Target Interview Length (Minutes)", min_value=15, max_value=90, value=45, step=15)

        if st.button("Generate Interview Guide", type="primary"):
            with st.spinner("Synthesizing questions and rubrics based on identified gaps..."):
                try:
                    plan = api_client.generate_interview_plan(
                        candidate_id=st.session_state.candidate_id,
                        evaluation_id=st.session_state.evaluation_result.id,
                        job_description=st.session_state.job_description,
                        target_minutes=duration,
                    )
                    st.session_state.interview_plan = plan
                    st.success("Interview guide generated.")
                except Exception as e:
                    st.error(f"Generation failed: {e}")

        if st.session_state.interview_plan:
            plan = st.session_state.interview_plan
            st.markdown("---")

            col_plan_m1, col_plan_m2 = st.columns(2)
            col_plan_m1.metric("Questions Synthesized", len(plan.questions))
            plan_duration = getattr(plan, "total_estimated_minutes", getattr(plan, "target_duration_minutes", 45))
            col_plan_m2.metric("Target Interview Length", f"{plan_duration} min")

            st.markdown("<div class='app-card-title' style='margin-top: 1rem;'>Questions & Evaluation Rubric</div>", unsafe_allow_html=True)

            for idx, q in enumerate(plan.questions, start=1):
                archetype_title = q.archetype.value.replace("_", " ").upper()

                with st.expander(f"Question {idx} [{archetype_title}] - {q.estimated_minutes} min"):
                    st.markdown(f"##### *'{q.question_text}'*")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("<div style='font-size: 0.8rem; font-weight: 600; color: #166534; text-transform: uppercase;'>Expected Positive Signals</div>", unsafe_allow_html=True)
                        for sig in q.expected_positive_signals:
                            st.markdown(f"- {sig}")
                    with col2:
                        st.markdown("<div style='font-size: 0.8rem; font-weight: 600; color: #991b1b; text-transform: uppercase;'>Potential Red Flags</div>", unsafe_allow_html=True)
                        for rf in q.red_flags:
                            st.markdown(f"- {rf}")

            if plan.interviewer_tips:
                st.markdown("<div class='app-card-title' style='margin-top: 1.5rem;'>Interviewer Guidance</div>", unsafe_allow_html=True)
                for tip in plan.interviewer_tips:
                    st.markdown(f"- {tip}")


# ---------------------------------------------------------------------------
# TAB 6: Model & Provider Configuration
# ---------------------------------------------------------------------------
with tab_settings:
    st.markdown(
        """
        <div class="page-header">
            <div class="page-title">Model & Inference Configuration</div>
            <div class="page-subtitle">Configure inference providers, select verified models with real-time rate limits, and manage local engines.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        backend_settings = api_client.get_llm_settings()
        backend_offline = False
    except Exception:
        backend_offline = True
        backend_settings = None

    if backend_offline or not backend_settings:
        st.markdown(
            """
            <div class="app-card" style="border-left: 3px solid #f59e0b; padding: 1rem;">
                <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem;">FastAPI Backend is Offline</div>
                <div style="font-size: 0.85rem; color: #64748b;">
                    Cannot reach http://127.0.0.1:8000. Start the backend server below to test connections or apply configuration changes.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        c_act1, c_act2 = st.columns([1, 1])
        with c_act1:
            if st.button("Start Backend Server", type="primary", use_container_width=True, key="tab6_start_backend"):
                with st.spinner("Starting FastAPI backend service..."):
                    if launch_fastapi_backend():
                        st.success("Backend started.")
                        st.rerun()
                    else:
                        st.error("Backend started but did not respond in time.")
        with c_act2:
            if st.button("Retry Connection", use_container_width=True, key="tab6_retry_backend"):
                st.rerun()

        # Offline fallback catalog snapshot
        from backend.schemas.models_catalog import PROVIDERS_CATALOG
        catalog = {pid: p.model_dump() for pid, p in PROVIDERS_CATALOG.items()}
        active_provider = "groq"
        active_model = "openai/gpt-oss-20b"
        active_compat = "auto"
        keys_status = {
            "groq": bool(os.environ.get("GROQ_API_KEY")),
            "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
            "nvidia_nim": bool(os.environ.get("NVIDIA_NIM_API_KEY")),
            "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            "ollama": True,
        }
    else:
        catalog = backend_settings.get("providers_catalog", {})
        active_provider = backend_settings.get("active_provider", "groq")
        active_model = backend_settings.get("active_model", "")
        active_compat = backend_settings.get("compatibility_mode", "auto")
        keys_status = backend_settings.get("api_keys_configured", {})

    if catalog:
        # Top summary metrics
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        prov_info = catalog.get(active_provider, {})
        with m_col1:
            st.metric("Active Provider", prov_info.get("name", active_provider))
        with m_col2:
            st.metric("Active Model", active_model.split("/")[-1])
        with m_col3:
            st.metric("Schema Mode", active_compat.upper())
        with m_col4:
            has_key = keys_status.get(active_provider, False)
            st.metric("Credentials", "Configured" if has_key else "Missing")

        # Fallback sequence indicator
        fallback_chain = backend_settings.get("fallback_chain", []) if backend_settings else []
        last_event = backend_settings.get("last_fallback_event") if backend_settings else None
        if fallback_chain:
            chain_pills = " &rarr; ".join([f"<span class='badge badge-nice' style='font-family: monospace; font-size: 0.7rem;'>{item}</span>" for item in fallback_chain[:5]])
            st.markdown(
                f"""
                <div class="app-card" style="padding: 0.7rem 0.95rem; margin-top: 0.75rem; border-left: 3px solid #10b981;">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="badge badge-met">Multi-Tier Failover Active</span>
                            <span style="font-size: 0.78rem; color: #94a3b8;">Automatic fallback sequence if rate limit or error occurs:</span>
                        </div>
                        <div>{chain_pills}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if last_event:
            st.info(f"Recent Failover Event: Switched from {last_event.get('from_provider')} ({last_event.get('from_model')}) to {last_event.get('to_provider')} ({last_event.get('to_model')}) due to: {last_event.get('error')}")

        st.markdown("---")

        col_prov, col_model, col_compat = st.columns([1, 1.8, 1.2])

        provider_keys = list(catalog.keys())
        provider_display_names = {
            pid: catalog[pid].get("name", pid)
            for pid in provider_keys
        }

        with col_prov:
            default_prov_idx = provider_keys.index(active_provider) if active_provider in provider_keys else 0
            selected_provider = st.selectbox(
                "Provider",
                options=provider_keys,
                index=default_prov_idx,
                format_func=lambda pid: provider_display_names.get(pid, pid),
                help="Inference backend: Groq, OpenRouter, NVIDIA NIM, Google Gemini, Ollama",
            )

        current_prov_data = catalog.get(selected_provider, {})
        available_models = current_prov_data.get("models", [])
        model_id_list = [m["id"] for m in available_models]

        current_default_model = current_prov_data.get("default_model", "")
        if selected_provider == active_provider and active_model in model_id_list:
            default_model_idx = model_id_list.index(active_model)
        elif current_default_model in model_id_list:
            default_model_idx = model_id_list.index(current_default_model)
        else:
            default_model_idx = 0

        with col_model:
            def format_model_label(mid: str) -> str:
                m_info = next((m for m in available_models if m["id"] == mid), None)
                if not m_info:
                    return mid
                free_badge = " [Free]" if m_info.get("free", False) else ""
                return f"{m_info['id']} - {m_info['name']}{free_badge} ({m_info['rate_limits']} | Ctx: {m_info['context_window']})"

            selected_model = st.selectbox(
                "Model",
                options=model_id_list,
                index=default_model_idx,
                format_func=format_model_label,
            )

        compat_options = {
            "auto": "Auto Adaptive (JSON Mode + Fallback)",
            "json_object": "Native JSON Object Mode",
            "schema_prompt": "Schema Prompt Enforcement",
        }
        with col_compat:
            compat_keys = list(compat_options.keys())
            compat_idx = compat_keys.index(active_compat) if active_compat in compat_keys else 0
            selected_compat = st.selectbox(
                "Compatibility Mode",
                options=compat_keys,
                index=compat_idx,
                format_func=lambda k: compat_options[k],
            )

        # Selected Model details card
        selected_model_data = next((m for m in available_models if m["id"] == selected_model), None)
        if selected_model_data:
            st.markdown(
                f"""
                <div class="app-card" style="margin-top: 0.5rem; font-size: 0.85rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span style="font-weight: 600; font-size: 0.92rem;">{selected_model_data['name']}</span>
                        <span class="badge badge-nice">{'Free Tier' if selected_model_data.get('free') else 'Paid'}</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; color: #64748b;">
                        <div>Category: <strong style="color: inherit;">{selected_model_data.get('category', 'General')}</strong></div>
                        <div>Context Window: <strong style="color: inherit;">{selected_model_data.get('context_window', 'N/A')}</strong></div>
                        <div>Rate Limits: <strong style="color: inherit;">{selected_model_data.get('rate_limits', 'N/A')}</strong></div>
                        <div>Compatibility: <strong style="color: inherit;">{selected_model_data.get('compatibility', 'JSON Mode')}</strong></div>
                    </div>
                    {f"<div style='margin-top: 0.4rem; color: #64748b;'>{selected_model_data['description']}</div>" if selected_model_data.get('description') else ""}
                </div>
                """,
                unsafe_allow_html=True,
            )

        with st.expander("Credentials & Custom Endpoint", expanded=not keys_status.get(selected_provider, False)):
            col_k1, col_k2 = st.columns([2, 1])
            with col_k1:
                key_configured = keys_status.get(selected_provider, False)
                key_placeholder = "•••••••••••• (Configured)" if key_configured else "Paste API key..."
                new_api_key = st.text_input(
                    f"{current_prov_data.get('name')} API Key",
                    type="password",
                    placeholder=key_placeholder,
                    help=f"Environment variable: {current_prov_data.get('env_key_var')}",
                )
                if current_prov_data.get("api_key_url"):
                    st.caption(f"[Get API key at {current_prov_data['name']}]({current_prov_data['api_key_url']})")

            with col_k2:
                custom_base_url = st.text_input(
                    "Custom Base URL (Optional)",
                    value=current_prov_data.get("default_base_url") or "",
                    help="Override default endpoint base URL",
                )

        st.markdown("---")
        btn_col1, btn_col2 = st.columns([1, 1])

        with btn_col1:
            if st.button("Test Connection & Measure Latency", use_container_width=True):
                if backend_offline:
                    st.error("Backend server is offline. Start the backend server above first.")
                else:
                    with st.spinner(f"Pinging {selected_provider} with model {selected_model}..."):
                        test_res = api_client.test_llm_connection(
                            provider=selected_provider,
                            model=selected_model,
                            compatibility_mode=selected_compat,
                            api_key=new_api_key.strip() if new_api_key else None,
                            base_url=custom_base_url.strip() if custom_base_url else None,
                        )
                        if test_res.get("status") == "ok":
                            st.success(
                                f"Connected successfully. Provider: {test_res.get('provider')} | Model: {test_res.get('model')} | Latency: {test_res.get('latency_ms')} ms"
                            )
                        else:
                            st.error(f"Connection failed: {test_res.get('error_message')} ({test_res.get('latency_ms')} ms)")

        with btn_col2:
            if st.button("Apply & Save Model", type="primary", use_container_width=True):
                if backend_offline:
                    st.error("Backend server is offline. Start the backend server above first.")
                else:
                    with st.spinner("Updating active backend configuration..."):
                        try:
                            save_res = api_client.update_llm_settings(
                                provider=selected_provider,
                                model=selected_model,
                                compatibility_mode=selected_compat,
                                api_key=new_api_key.strip() if new_api_key else None,
                                base_url=custom_base_url.strip() if custom_base_url else None,
                            )
                            st.success(
                                f"Active configuration updated: {save_res['active_provider']} ({save_res['active_model']}) in {save_res['compatibility_mode']} mode."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update configuration: {e}")

        # -------------------------------------------------------------------
        # Local Ollama Control Center
        # -------------------------------------------------------------------
        st.markdown("---")
        st.markdown(
            """
            <div class="page-title" style="font-size: 1.25rem;">Local Ollama Engine</div>
            <div class="page-subtitle" style="margin-bottom: 0.75rem;">Detect and control local LLM daemon on this machine.</div>
            """,
            unsafe_allow_html=True,
        )

        if backend_offline:
            ollama_status = {"running": False, "installed": False, "binary_path": None, "base_url": "http://localhost:11434"}
        else:
            try:
                ollama_status = api_client.get_ollama_status()
            except Exception:
                ollama_status = {"running": False, "installed": False, "binary_path": None, "base_url": "http://localhost:11434"}
        is_ollama_up = ollama_status.get("running", False)

        c_stat1, c_stat2 = st.columns([3, 1.2])
        with c_stat1:
            if is_ollama_up:
                st.markdown(
                    f"""
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.4rem;">
                        <span class="badge badge-met">Service Online</span>
                        <span style="font-size: 0.85rem; color: #64748b;">Version: <code>{ollama_status.get('version', 'unknown')}</code> at <code>{ollama_status.get('base_url')}</code></span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                binary_info = f"Found at {ollama_status.get('binary_path')}" if ollama_status.get("installed") else "Executable not found"
                st.markdown(
                    f"""
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.4rem;">
                        <span class="badge badge-gap">Service Offline</span>
                        <span style="font-size: 0.85rem; color: #64748b;">{binary_info}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with c_stat2:
            if not is_ollama_up:
                if st.button("Start Ollama Service", use_container_width=True, type="primary"):
                    with st.spinner("Starting Ollama background process..."):
                        start_res = api_client.start_ollama_service()
                        if start_res.get("success"):
                            st.success(start_res.get("message"))
                            st.rerun()
                        else:
                            st.error(start_res.get("message"))
            else:
                if st.button("Refresh State", use_container_width=True):
                    st.rerun()

        if is_ollama_up:
            ollama_models_data = api_client.get_ollama_models()
            running_models = ollama_models_data.get("running", [])
            installed_models = ollama_models_data.get("installed", [])

            st.markdown("<div class='app-card-title' style='margin-top: 1rem;'>Active Memory Allocation (VRAM / RAM)</div>", unsafe_allow_html=True)
            if running_models:
                for rm in running_models:
                    rc1, rc2, rc3 = st.columns([2.5, 1.5, 1])
                    with rc1:
                        st.markdown(f"**`{rm['name']}`**")
                        st.caption(f"Expires: {rm.get('expires_at', 'idle')}")
                    with rc2:
                        st.markdown(f"VRAM: `{rm['size_vram_mb']} MB` | RAM: `{rm['size_ram_mb']} MB`")
                    with rc3:
                        if st.button("Unload", key=f"unload_vram_{rm['name']}", use_container_width=True):
                            with st.spinner(f"Unloading {rm['name']}..."):
                                un_res = api_client.unload_ollama_model(rm["name"])
                                if un_res.get("success"):
                                    st.success(f"Unloaded {rm['name']}.")
                                    st.rerun()
                                else:
                                    st.error(un_res.get("message"))
            else:
                st.caption("No models currently resident in memory. (Engine idle)")

            st.markdown("<div class='app-card-title' style='margin-top: 1rem;'>Installed Models on Host</div>", unsafe_allow_html=True)
            if installed_models:
                for idx, im in enumerate(installed_models, start=1):
                    with st.container():
                        col_m1, col_m2, col_m3, col_m4 = st.columns([2.5, 1.2, 1.2, 1.3])
                        with col_m1:
                            st.markdown(f"**{idx}. `{im['name']}`**")
                            st.caption(f"Format: {im['format']} | Family: {im['family']}")
                        with col_m2:
                            st.markdown(f"Size: `{im['size_gb']} GB`")
                            st.caption(f"Params: {im['parameter_size']}")
                        with col_m3:
                            is_loaded = any(rm['name'] == im['name'] or rm['name'].startswith(im['name']) for rm in running_models)
                            if is_loaded:
                                if st.button("Unload", key=f"btn_un_{im['name']}", use_container_width=True):
                                    with st.spinner(f"Unloading {im['name']}..."):
                                        api_client.unload_ollama_model(im['name'])
                                        st.rerun()
                            else:
                                if st.button("Load VRAM", key=f"btn_ld_{im['name']}", use_container_width=True):
                                    with st.spinner(f"Loading {im['name']} into VRAM..."):
                                        ld_res = api_client.load_ollama_model(im['name'])
                                        if ld_res.get("success"):
                                            st.success(f"Loaded {im['name']}.")
                                            st.rerun()
                                        else:
                                            st.error(ld_res.get("message"))
                        with col_m4:
                            is_active = (active_provider == "ollama" and active_model == im['name'])
                            if is_active:
                                st.markdown("<span class='badge badge-met' style='margin-top: 0.5rem;'>Active Engine</span>", unsafe_allow_html=True)
                            else:
                                if st.button("Set Active", key=f"btn_act_{im['name']}", use_container_width=True):
                                    with st.spinner(f"Activating {im['name']}..."):
                                        api_client.update_llm_settings(
                                            provider="ollama",
                                            model=im['name'],
                                            compatibility_mode="auto",
                                        )
                                        api_client.load_ollama_model(im['name'])
                                        st.success(f"Active model set to Ollama ({im['name']}).")
                                        st.rerun()
            else:
                st.caption("No local models installed.")

            with st.expander("Pull New Model"):
                col_p1, col_p2 = st.columns([3, 1])
                with col_p1:
                    pull_tag = st.text_input(
                        "Model Tag",
                        placeholder="e.g. qwen2.5-coder:7b, mistral:7b, llama3.2:3b",
                        label_visibility="collapsed",
                    )
                with col_p2:
                    if st.button("Pull Model", use_container_width=True):
                        if pull_tag.strip():
                            with st.spinner(f"Downloading {pull_tag}..."):
                                p_res = api_client.pull_ollama_model(pull_tag.strip())
                                if p_res.get("success"):
                                    st.success(f"Model '{pull_tag}' pulled.")
                                    st.rerun()
                                else:
                                    st.error(p_res.get("message"))
