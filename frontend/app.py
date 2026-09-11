"""
frontend/app.py
Streamlit Recruiter Dashboard for Agentic Recruitment Screening,
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
    page_title="AI Recruitment Screening & HITL Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

api_client = BackendAPIClient()


def launch_fastapi_backend() -> bool:
    """Spawns the FastAPI backend server as a background process and polls health until ready."""
    venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    flags = 0
    if os.name == "nt":
        # Detached process so it lives independently of Streamlit process reloads
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

    # Poll /health endpoint for up to 8 seconds
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
    # Default sample Job Description
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
# Sidebar: System Health & Navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🎯 Recruitment Agent")
    st.markdown("---")

    health = api_client.health_check()
    if health.get("status") == "ok":
        st.success(
            f"🟢 **Backend Online**\n\n"
            f"**Provider:** `{health.get('llm_provider', 'unknown')}`\n\n"
            f"**Model:** `{health.get('model', 'default')}`\n\n"
            f"**Mode:** `{health.get('compatibility_mode', 'auto')}`"
        )
    else:
        st.error("🔴 **Backend Offline**\n\nFastAPI is not running on port 8000.")
        if st.button("🚀 Start FastAPI Backend", use_container_width=True, key="sb_start_backend"):
            with st.spinner("Starting FastAPI backend on port 8000..."):
                if launch_fastapi_backend():
                    st.success("Backend started successfully!")
                    st.rerun()
                else:
                    st.error("Backend took too long to start. Run 'python start.py' in a terminal.")


    st.markdown("---")
    st.subheader("Screening Pipeline")
    st.markdown(
        """
        1. **Ingest & Scrub:** Upload CV, extract structure, redact PII & isolate demographics.
        2. **Job Setup:** Define atomic requirements with weights.
        3. **Semantic Match:** Asymmetric RAG with verbatim citations.
        4. **HITL Gate:** Recruiter validation, overrides, and audit log.
        5. **Interview Plan:** Rubric tailored to candidate gaps.
        """
    )
    if st.button("🔄 Reset All Session Data", use_container_width=True):
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
    "📄 1. Candidate Ingestion & PII Audit",
    "📋 2. Job Description",
    "⚖️ 3. Semantic Match & Citations",
    "🛡️ 4. Recruiter HITL Gate",
    "🎯 5. Tailored Interview Guide",
    "⚙️ 6. LLM & Provider Settings",
])


# ---------------------------------------------------------------------------
# TAB 1: Candidate Ingestion & PII Audit
# ---------------------------------------------------------------------------
with tab_cv:
    st.header("Candidate CV Ingestion & PII Scrubbing")
    st.markdown("Upload a candidate CV in PDF, DOCX, or text format. The pipeline extracts structured data and scrubs PII.")

    col_upload, col_sample = st.columns([1.5, 1])

    with col_upload:
        uploaded_file = st.file_uploader(
            "Select Candidate Resume/CV",
            type=["pdf", "docx", "txt", "md", "json"],
            help="Upload candidate PDF, Word (.docx), plain text, Markdown, or JSON resume",
        )

    with col_sample:
        st.markdown("**Or pick a pre-built candidate profile:**")
        sample_options = {
            "Strong AI Engineer (EN)": "data/mock_cvs/strong_ai_engineer.txt",
            "Borderline Junior Developer (EN)": "data/mock_cvs/borderline_junior_developer.txt",
            "Reject (Unrelated Background)": "data/mock_cvs/reject_unrelated_candidate.txt",
            "Senior Backend AI Engineer (RO)": "data/test_resumes/Inginer_Software_Senior_Alexandru_Ionescu_RO.txt",
            "Senior Cloud & DevOps Engineer (DE)": "data/test_resumes/Senior_Cloud_DevOps_Engineer_Maximilian_Weber_DE.txt",
            "Cheffe de Projet & Lead Dev (FR)": "data/test_resumes/Cheffe_de_Projet_Fullstack_Claire_Dubois_FR.txt",
            "Senior Accountant (EN)": "data/test_resumes/Real_Resume_Accountant_EN.txt",
            "Standard JSON Resume (EN)": "data/test_resumes/JSON_Resume_Standard_Schema_EN.json",
        }
        selected_sample_label = st.selectbox("Sample Candidates", list(sample_options.keys()))
        selected_sample_path = sample_options[selected_sample_label]

    ingest_button = st.button("🚀 Ingest & Scrub Candidate Profile", type="primary")

    if ingest_button:
        with st.spinner("Extracting text, running LLM structured parser, and scrubbing PII..."):
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
                st.success(f"Candidate indexed successfully! UUID: `{st.session_state.candidate_id}` ({result['chunks_indexed']} chunks in ChromaDB)")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to ingest candidate CV: {e}")

    if st.session_state.anonymized_candidate:
        st.markdown("---")
        col_raw, col_clean = st.columns(2)

        with col_raw:
            st.subheader("🔒 Raw Parsed Contact Info (Isolated)")
            contact = st.session_state.parsed_cv.contact_info if st.session_state.parsed_cv else None
            if contact:
                st.write(f"**Name:** {contact.full_name}")
                st.write(f"**Email:** {contact.email}")
                phone_display = getattr(contact, "phone_number", None) or getattr(contact, "phone", None) or "N/A"
                st.write(f"**Phone:** {phone_display}")
                st.write(f"**Location:** {contact.location or 'N/A'}")
                st.write(f"**LinkedIn:** {contact.linkedin_url or 'N/A'}")

        with col_clean:
            st.subheader("🛡️ Scrubbed Anonymized Profile (Passed to LLM)")
            st.write(f"**Candidate UUID:** `{st.session_state.anonymized_candidate.candidate_id}`")
            st.write(f"**Identified Skills:** {', '.join(st.session_state.anonymized_candidate.anonymized_skills)}")
            langs = getattr(st.session_state.anonymized_candidate, "anonymized_languages", [])
            if langs:
                lang_str = ", ".join([f"{l.language} ({l.proficiency})" if l.proficiency else l.language for l in langs])
                st.write(f"**Languages:** {lang_str}")
            st.write(f"**Demographic Audit Data:** {st.session_state.anonymized_candidate.demographic_data or 'None detected'}")

        with st.expander("View Anonymized Work Experiences", expanded=False):
            for exp in st.session_state.anonymized_candidate.anonymized_work_experiences:
                st.markdown(f"### {exp.job_title} at {exp.company_name}")
                st.caption(f"{exp.start_date or ''} - {exp.end_date or ''}")
                for bullet in exp.work_description:
                    st.markdown(f"- {bullet}")

        projects = getattr(st.session_state.anonymized_candidate, "anonymized_projects", [])
        if projects:
            with st.expander(f"View Technical & Academic Projects ({len(projects)})", expanded=False):
                for proj in projects:
                    st.markdown(f"### 🛠️ {proj.project_name}")
                    if proj.technologies:
                        st.caption(f"**Technologies:** {', '.join(proj.technologies)}")
                    if proj.project_url:
                        st.caption(f"**Repository/Link:** `{proj.project_url}`")
                    for bullet in proj.description:
                        st.markdown(f"- {bullet}")

        custom_secs = getattr(st.session_state.anonymized_candidate, "anonymized_custom_sections", [])
        if custom_secs:
            with st.expander(f"View Additional Relevant Sections ({len(custom_secs)})", expanded=False):
                for sec in custom_secs:
                    st.markdown(f"### 📌 {sec.section_title}")
                    for it in sec.items:
                        st.markdown(f"- {it}")

        # Export Tagged CV JSON
        st.markdown("---")
        col_cv_info, col_cv_btn = st.columns([2.5, 1])
        with col_cv_info:
            st.markdown("💾 **Export Annotated Candidate CV (JSON)**")
            st.caption("Downloads all extracted attributes with provenance tags: `anonymised`, `visible`, `unused`, and `extra`.")
        with col_cv_btn:
            try:
                cv_export_payload = api_client.export_candidate_cv(st.session_state.candidate_id)
                st.download_button(
                    label="📥 Download Tagged CV JSON",
                    data=json.dumps(cv_export_payload, indent=2),
                    file_name=f"candidate_{st.session_state.candidate_id}_tagged.json",
                    mime="application/json",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Export error: {e}")


# ---------------------------------------------------------------------------
# TAB 2: Job Description Setup
# ---------------------------------------------------------------------------
with tab_jd:
    st.header("Job Description & Atomic Criteria")
    st.markdown("Import a posting via web URL or manually configure requirements and scoring weights.")

    # 1. Job Ingestion Mode Tabs
    import_tab_url, import_tab_text = st.tabs(["🌐 Web URL Import", "📝 Paste Raw Job Description"])

    with import_tab_url:
        col_url, col_fetch = st.columns([3, 1])
        with col_url:
            job_url_input = st.text_input(
                "Job Posting URL",
                placeholder="https://example.com/careers/senior-ai-engineer",
                label_visibility="collapsed",
            )
        with col_fetch:
            fetch_btn = st.button("🚀 Fetch & Extract", use_container_width=True)

        if fetch_btn:
            if not job_url_input or not job_url_input.strip():
                st.error("Please enter a valid job posting URL (starting with http:// or https://).")
            else:
                with st.spinner("Accessing webpage, resolving SPAs/metadata, and decomposing requirements with AI..."):
                    try:
                        res = api_client.parse_job_url(job_url_input)
                        st.session_state.job_description = JobDescription.model_validate(res["job_description"])
                        st.session_state.jd_missing_fields = res.get("missing_fields", [])
                        st.session_state.jd_warnings = res.get("warnings", [])
                        st.success(
                            f"Successfully imported job posting! Extracted {len(st.session_state.job_description.requirements)} requirements."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to extract job description from URL: {e}")
                        st.info("💡 **Fallback Tip:** If the external careers site blocks automated bots or requires dynamic interaction, copy the job posting text and paste it into the **📝 Paste Raw Job Description** tab.")

    with import_tab_text:
        raw_jd_paste = st.text_area(
            "Paste Raw Job Description Text",
            placeholder="Paste complete job description text, qualifications, and responsibilities here...",
            height=140,
        )
        if st.button("⚡ Parse & Decompose Job Text", use_container_width=True):
            if not raw_jd_paste or not raw_jd_paste.strip():
                st.error("Please paste the job description text first.")
            else:
                with st.spinner("Extracting role metadata and decomposing atomic criteria with AI..."):
                    try:
                        res = api_client.parse_job_text(raw_jd_paste)
                        st.session_state.job_description = JobDescription.model_validate(res["job_description"])
                        st.session_state.jd_missing_fields = res.get("missing_fields", [])
                        st.session_state.jd_warnings = res.get("warnings", [])
                        st.success(
                            f"Successfully parsed job text! Extracted {len(st.session_state.job_description.requirements)} requirements."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to parse job description text: {e}")

    # 2. Missing Fields / Incomplete Data Warnings
    if st.session_state.jd_warnings:
        warning_bullets = "\n".join([f"- **{w}**" for w in st.session_state.jd_warnings])
        st.warning(
            f"⚠️ **Incomplete Job Posting Details Detected:**\n\n"
            f"{warning_bullets}\n\n"
            f"👉 *The AI populated all available information. Please fill in the missing fields manually below.*"
        )

    jd = st.session_state.job_description

    # 3. Position Metadata Fields
    col_t1, col_t2, col_t3 = st.columns([2, 1, 1])
    with col_t1:
        jd.title = st.text_input("Job Title *", value=jd.title)
    with col_t2:
        jd.department = st.text_input("Department", value=jd.department or "")
    with col_t3:
        jd.seniority_level = st.text_input("Seniority Level", value=jd.seniority_level or "")

    col_m1, col_m2, col_m3 = st.columns([2, 1, 1])
    with col_m1:
        jd.location = st.text_input("Location / Cities", value=getattr(jd, "location", "") or "", placeholder="e.g. Timisoara or Sibiu, Romania")
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

    st.subheader("Granular Requirements & Weights")

    # 4. Atomic Requirements Editor
    reqs_to_remove = []
    for idx, req in enumerate(jd.requirements):
        badge_style = "🔥 MUST-HAVE" if req.category == RequirementCategory.MUST_HAVE else ("✨ NICE-TO-HAVE" if req.category == RequirementCategory.NICE_TO_HAVE else "🤝 SOFT-SKILL")
        with st.expander(f"Requirement {idx + 1}: {req.title} [{badge_style}]", expanded=True):
            cols = st.columns([2.5, 1.2, 1, 0.5])
            with cols[0]:
                req.title = st.text_input(f"Title ({req.id})", value=req.title)
                req.description = st.text_area(f"Description ({req.id})", value=req.description, height=70)
            with cols[1]:
                req.category = RequirementCategory(
                    st.selectbox(
                        f"Category ({req.id})",
                        [c.value for c in RequirementCategory],
                        index=[c.value for c in RequirementCategory].index(req.category.value),
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
                    f"Min Years ({req.id})",
                    min_value=0,
                    max_value=20,
                    value=req.minimum_years_experience or 0,
                )
            with cols[3]:
                st.write("")
                st.write("")
                if st.button("🗑️", key=f"del_{req.id}_{idx}", help="Remove requirement"):
                    reqs_to_remove.append(idx)

    if reqs_to_remove:
        for r_idx in sorted(reqs_to_remove, reverse=True):
            jd.requirements.pop(r_idx)
        st.rerun()

    # 5. Add Custom Requirement Button
    col_add, col_audit = st.columns([1, 1])
    with col_add:
        if st.button("➕ Add Requirement Manually", use_container_width=True):
            new_num = len(jd.requirements) + 1
            jd.requirements.append(
                JobRequirement(
                    id=f"req_manual_{new_num}",
                    title=f"Custom Requirement {new_num}",
                    category=RequirementCategory.MUST_HAVE,
                    weight=1.0,
                    description="Enter required skill, experience, or credential details.",
                    minimum_years_experience=0,
                )
            )
            st.rerun()

    with col_audit:
        if st.session_state.jd_warnings:
            if st.button("✅ Clear Warnings & Validate", use_container_width=True):
                must_haves = [r for r in jd.requirements if r.category == RequirementCategory.MUST_HAVE]
                if not jd.title or jd.title.strip() in {"", "Untitled Position"}:
                    st.error("Please provide a specific Job Title before proceeding.")
                elif not must_haves:
                    st.error("At least one requirement must be categorized as 'MUST-HAVE'.")
                else:
                    st.session_state.jd_warnings = []
                    st.session_state.jd_missing_fields = []
                    st.success("Job Description validated!")
                    st.rerun()

    # Export Tagged JD JSON
    st.markdown("---")
    col_jd_info, col_jd_btn = st.columns([2.5, 1])
    with col_jd_info:
        st.markdown("💾 **Export Annotated Job Description (JSON)**")
        st.caption("Downloads all criteria and scoring weights tagged as `visible`, `extra`, `unused`, or `anonymised`.")
    with col_jd_btn:
        try:
            jd_export_payload = api_client.export_job_description(jd)
            st.download_button(
                label="📥 Download Tagged JD JSON",
                data=json.dumps(jd_export_payload, indent=2),
                file_name="job_description_tagged.json",
                mime="application/json",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Export error: {e}")


# ---------------------------------------------------------------------------
# TAB 3: Semantic Match & Verbatim Citations
# ---------------------------------------------------------------------------
with tab_match:
    st.header("Semantic Matching & Verbatim Grounding")

    if not st.session_state.candidate_id:
        st.warning("Please upload and ingest a candidate CV in Tab 1 first.")
    else:
        if st.button("⚡ Run Asymmetric Semantic Matching", type="primary"):
            with st.spinner("Retrieving candidate chunks from ChromaDB and evaluating with LLM..."):
                try:
                    eval_result = api_client.evaluate_match(
                        candidate_id=st.session_state.candidate_id,
                        job_description=st.session_state.job_description,
                    )
                    st.session_state.evaluation_result = eval_result
                    st.success("Semantic evaluation completed!")
                except Exception as e:
                    st.error(f"Matching failed: {e}")

        if st.session_state.evaluation_result:
            res = st.session_state.evaluation_result

            # Top KPI metrics
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Overall Score", f"{res.overall_score}%")
            m_col2.metric("Must-Have Score", f"{res.must_have_score}%")
            m_col3.metric("Nice-to-Have Score", f"{res.nice_to_have_score}%")
            cvs_pct = round(res.citation_verification_score * 100.0, 1)
            m_col4.metric("Citation Grounding (CVS)", f"{cvs_pct}%")

            # Recommendation Badge
            rec = res.recommendation.value
            if rec == "strong_match":
                st.success(f"### Recommendation: 🌟 STRONG MATCH (Score: {res.overall_score}%)")
            elif rec == "borderline":
                st.warning(f"### Recommendation: ⚠️ BORDERLINE (Must-Have Gaps: {res.must_have_gaps_count})")
            else:
                st.error(f"### Recommendation: ❌ REJECT (Score: {res.overall_score}%)")

            st.markdown("---")
            st.subheader("Requirement Evaluation & Grounded Citations")

            for match in res.requirement_matches:
                req_obj = next((r for r in st.session_state.job_description.requirements if r.id == match.requirement_id), None)
                req_title = req_obj.title if req_obj else match.requirement_id

                status_icon = "🟢" if match.status == MatchStatus.MET else ("🟡" if match.status == MatchStatus.PARTIAL else "🔴")
                with st.expander(f"{status_icon} {req_title} — Status: {match.status.value.upper()} (Score: {int(match.score * 100)}%)"):
                    st.write(f"**Reasoning:** {match.reasoning}")
                    if match.gap_analysis:
                        st.info(f"**Gap Analysis:** {match.gap_analysis}")

                    st.markdown("**Verbatim Citations from Candidate Resume:**")
                    if match.citations:
                        for cit in match.citations:
                            badge = "✅ Verified Substring" if cit.verified else "⚠️ Unverified Substring"
                            st.markdown(f"> *\"{cit.quote}\"* — `{badge}` ({cit.source_section or 'Profile'})")
                    else:
                        st.write("*(No direct evidence found in profile)*")


# ---------------------------------------------------------------------------
# TAB 4: Recruiter Human-in-the-Loop (HITL) Gate
# ---------------------------------------------------------------------------
with tab_hitl:
    st.header("Recruiter Human-in-the-Loop (HITL) Gate")
    st.markdown("Review the agent's proposed evaluation. Recruiters have final authority to confirm or override decisions.")

    if not st.session_state.evaluation_result:
        st.info("Run semantic matching in Tab 3 to review candidate evaluations.")
    else:
        eval_res = st.session_state.evaluation_result

        st.markdown(f"**Evaluation ID:** `{eval_res.id}`")
        st.markdown(f"**Current Agent Recommendation:** `{eval_res.recommendation.value.upper()}`")
        st.markdown(f"**HITL Status:** {'✅ Validated by Human' if eval_res.hitl_validated else '⏳ Pending Review'}")

        st.markdown("---")
        st.subheader("Recruiter Decision & Audit Logging")

        recruiter_override = st.selectbox(
            "Final Recruiter Decision",
            options=[r.value for r in Recommendation],
            index=[r.value for r in Recommendation].index(eval_res.recommendation.value),
            help="Confirm agent recommendation or select override",
        )

        recruiter_notes = st.text_area(
            "Recruiter Audit Justification & Notes",
            value=eval_res.recruiter_notes or "",
            placeholder="Explain why this candidate is approved, placed on hold, or rejected...",
            height=100,
        )

        if st.button("💾 Confirm HITL Decision & Update Audit Trail", type="primary"):
            try:
                updated = api_client.submit_hitl_decision(
                    evaluation_id=eval_res.id,
                    recruiter_decision=Recommendation(recruiter_override),
                    recruiter_notes=recruiter_notes,
                )
                st.session_state.evaluation_result = updated
                st.success(f"HITL Decision recorded! Final Status: `{updated.recommendation.value.upper()}`")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to record HITL decision: {e}")


# ---------------------------------------------------------------------------
# TAB 5: Tailored Interview Guide
# ---------------------------------------------------------------------------
with tab_interview:
    st.header("Tailored Interview Guide Synthesis")
    st.markdown("Generates targeted interview questions based on candidate-specific gaps, borderline areas, and strengths.")

    if not st.session_state.evaluation_result:
        st.info("Complete candidate matching and review in Tabs 3 and 4 first.")
    else:
        duration = st.slider("Target Interview Length (Minutes)", min_value=15, max_value=90, value=45, step=15)

        if st.button("📝 Synthesize Interview Guide", type="primary"):
            with st.spinner("Synthesizing tailored questions and rubrics..."):
                try:
                    plan = api_client.generate_interview_plan(
                        candidate_id=st.session_state.candidate_id,
                        evaluation_id=st.session_state.evaluation_result.id,
                        job_description=st.session_state.job_description,
                        target_minutes=duration,
                    )
                    st.session_state.interview_plan = plan
                    st.success("Interview Plan synthesized!")
                except Exception as e:
                    st.error(f"Failed to generate interview guide: {e}")

        if st.session_state.interview_plan:
            plan = st.session_state.interview_plan
            st.markdown("---")
            st.subheader(f"📋 Interview Guide ({plan.total_estimated_minutes} Minutes)")
            st.info(f"**Focus Summary:** {plan.interview_focus_summary}")

            for idx, q in enumerate(plan.questions, start=1):
                badge_color = "orange" if q.archetype == QuestionArchetype.GAP_VERIFICATION else "blue"
                with st.expander(f"Question {idx} [{q.archetype.value.upper()}] ({q.estimated_minutes} mins)"):
                    st.markdown(f"### *\"{q.question_text}\"*")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Expected Positive Signals:**")
                        for sig in q.expected_positive_signals:
                            st.markdown(f"- ✅ {sig}")
                    with col2:
                        st.markdown("**Red Flags:**")
                        for rf in q.red_flags:
                            st.markdown(f"- 🚩 {rf}")

            if plan.interviewer_tips:
                st.markdown("---")
                st.subheader("💡 Interviewer Tips")
                for tip in plan.interviewer_tips:
                    st.markdown(f"- {tip}")


# ---------------------------------------------------------------------------
# TAB 6: LLM Provider & Model Settings
# ---------------------------------------------------------------------------
with tab_settings:
    st.header("⚙️ LLM Provider & Model Settings")
    st.markdown(
        "Dynamically switch LLM backends, select from all free-tier models with verified rate limits, "
        "and configure JSON schema compatibility modes without restarting the application."
    )

    try:
        backend_settings = api_client.get_llm_settings()
        backend_offline = False
    except Exception as e:
        backend_offline = True
        backend_settings = None

    if backend_offline or not backend_settings:
        st.warning(
            "⚠️ **FastAPI Backend is Offline (WinError 10061)**\n\n"
            "The Streamlit dashboard cannot reach `http://127.0.0.1:8000`. "
            "Click **🚀 Start FastAPI Backend Server** below to start it directly, or run `python start.py` in your terminal."
        )
        c_act1, c_act2 = st.columns([1, 1])
        with c_act1:
            if st.button("🚀 Start FastAPI Backend Server", type="primary", use_container_width=True, key="tab6_start_backend"):
                with st.spinner("Starting FastAPI backend on http://127.0.0.1:8000..."):
                    if launch_fastapi_backend():
                        st.success("Backend started successfully!")
                        st.rerun()
                    else:
                        st.error("Backend started but health check timed out. Click Retry below.")
        with c_act2:
            if st.button("🔄 Retry Connection", use_container_width=True, key="tab6_retry_backend"):
                st.rerun()

        # Offline fallback catalog snapshot so user can still browse all models and rate limits
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
        st.info("📋 Displaying offline catalog snapshot below. Launch backend above to test connections or apply changes.")
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
            st.metric("Active Provider", f"{prov_info.get('icon', '🤖')} {prov_info.get('name', active_provider)}")
        with m_col2:
            st.metric("Active Model", active_model.split("/")[-1])
        with m_col3:
            st.metric("Compatibility Mode", active_compat.upper())
        with m_col4:
            has_key = keys_status.get(active_provider, False)
            st.metric("API Key Status", "🟢 Configured" if has_key else "⚠️ Missing")

        st.markdown("---")

        col_prov, col_model, col_compat = st.columns([1, 1.8, 1.2])

        provider_keys = list(catalog.keys())
        provider_display_names = {
            pid: f"{catalog[pid].get('icon', '')} {catalog[pid].get('name', pid)}"
            for pid in provider_keys
        }

        with col_prov:
            default_prov_idx = provider_keys.index(active_provider) if active_provider in provider_keys else 0
            selected_provider = st.selectbox(
                "Select Provider",
                options=provider_keys,
                index=default_prov_idx,
                format_func=lambda pid: provider_display_names.get(pid, pid),
                help="Choose LLM inference backend (Groq, OpenRouter, NVIDIA NIM, Google Gemini, Ollama)",
            )

        current_prov_data = catalog.get(selected_provider, {})
        available_models = current_prov_data.get("models", [])
        model_id_list = [m["id"] for m in available_models]

        # Determine default model index
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
                free_badge = " [FREE]" if m_info.get("free", False) else ""
                return f"{m_info['id']} — {m_info['name']}{free_badge} ({m_info['rate_limits']} | Ctx: {m_info['context_window']})"

            selected_model = st.selectbox(
                "Select Model (with Rate Limits)",
                options=model_id_list,
                index=default_model_idx,
                format_func=format_model_label,
                help="Select model. Rate limits and context window are displayed for each option.",
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
                "JSON Compatibility Mode",
                options=compat_keys,
                index=compat_idx,
                format_func=lambda k: compat_options[k],
                help="How Pydantic schema validation is enforced on LLM completions.",
            )

        # Selected Model details card
        selected_model_data = next((m for m in available_models if m["id"] == selected_model), None)
        if selected_model_data:
            with st.container():
                st.markdown(f"#### 📊 Model Specs: `{selected_model_data['name']}`")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(f"**Category:** {selected_model_data.get('category', 'General')}")
                with c2:
                    st.markdown(f"**Context Window:** `{selected_model_data.get('context_window', 'N/A')}`")
                with c3:
                    st.markdown(f"**Rate Limits:** `{selected_model_data.get('rate_limits', 'N/A')}`")
                with c4:
                    st.markdown(f"**Tier:** `{'FREE TIER' if selected_model_data.get('free') else 'PAID'}`")
                if selected_model_data.get("description"):
                    st.caption(f"ℹ️ {selected_model_data['description']}")

        # API Key & Base URL Credentials Box
        with st.expander("🔑 Provider Credentials & Endpoint Settings", expanded=not keys_status.get(selected_provider, False)):
            col_k1, col_k2 = st.columns([2, 1])
            with col_k1:
                key_configured = keys_status.get(selected_provider, False)
                key_placeholder = "•••••••••••• (Key Configured)" if key_configured else "Paste your API key here..."
                new_api_key = st.text_input(
                    f"{current_prov_data.get('name')} API Key",
                    type="password",
                    placeholder=key_placeholder,
                    help=f"Environment variable: {current_prov_data.get('env_key_var')}",
                )
                if current_prov_data.get("api_key_url"):
                    st.markdown(f"[🔗 Get free API key at {current_prov_data['name']}]({current_prov_data['api_key_url']})")

            with col_k2:
                custom_base_url = st.text_input(
                    "Custom Base URL (Optional)",
                    value=current_prov_data.get("default_base_url") or "",
                    help="Override endpoint base URL if using local gateway or custom proxy.",
                )

        # Action Buttons
        st.markdown("---")
        btn_col1, btn_col2 = st.columns([1, 1])

        with btn_col1:
            if st.button("🧪 Test Connection & Measure Latency", use_container_width=True):
                if backend_offline:
                    st.error("❌ Cannot test connection: FastAPI backend is offline. Click '🚀 Start FastAPI Backend Server' above.")
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
                                f"✅ **Connected Successfully!**\n\n"
                                f"- **Provider:** `{test_res.get('provider')}`\n"
                                f"- **Model:** `{test_res.get('model')}`\n"
                                f"- **Latency:** `{test_res.get('latency_ms')} ms`\n"
                                f"- **Echo Response:** `{test_res.get('sample_output')}`"
                            )
                        else:
                            st.error(
                                f"❌ **Connection Failed!**\n\n"
                                f"- **Error:** {test_res.get('error_message')}\n"
                                f"- **Latency:** `{test_res.get('latency_ms')} ms`"
                            )

        with btn_col2:
            if st.button("💾 Apply & Save Active Model", type="primary", use_container_width=True):
                if backend_offline:
                    st.error("❌ Cannot apply configuration: FastAPI backend is offline. Click '🚀 Start FastAPI Backend Server' above.")
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
                                f"🎉 **Active LLM Updated!** All agents now use **{save_res['active_provider']}** "
                                f"with model **`{save_res['active_model']}`** in **`{save_res['compatibility_mode']}`** mode."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update LLM configuration: {e}")

        # -------------------------------------------------------------------
        # Local Ollama Control Center (Detect, Start, Load/Unload VRAM)
        # -------------------------------------------------------------------
        st.markdown("---")
        st.subheader("🦙 Local Ollama Control Center")
        st.markdown(
            "Detect your laptop's local Ollama daemon, inspect models loaded in GPU VRAM/RAM, "
            "and load or evict model weights with 1-click."
        )

        if backend_offline:
            ollama_status = {"running": False, "installed": False, "binary_path": None, "base_url": "http://localhost:11434"}
        else:
            try:
                ollama_status = api_client.get_ollama_status()
            except Exception:
                ollama_status = {"running": False, "installed": False, "binary_path": None, "base_url": "http://localhost:11434"}
        is_ollama_up = ollama_status.get("running", False)

        c_stat1, c_stat2 = st.columns([3, 1.5])
        with c_stat1:
            if is_ollama_up:
                st.success(
                    f"🟢 **Ollama Daemon Running** (Version: `{ollama_status.get('version', 'unknown')}`) "
                    f"at `{ollama_status.get('base_url')}`"
                )
            else:
                binary_info = f"Found at `{ollama_status.get('binary_path')}`" if ollama_status.get("installed") else "Executable not found"
                st.warning(f"🔴 **Ollama Daemon Offline** — {binary_info}")

        with c_stat2:
            if not is_ollama_up:
                if st.button("🚀 Start Ollama Service", use_container_width=True, type="primary"):
                    with st.spinner("Starting Ollama background daemon..."):
                        start_res = api_client.start_ollama_service()
                        if start_res.get("success"):
                            st.success(start_res.get("message"))
                            st.rerun()
                        else:
                            st.error(start_res.get("message"))
            else:
                if st.button("🔄 Refresh Ollama State", use_container_width=True):
                    st.rerun()

        if is_ollama_up:
            ollama_models_data = api_client.get_ollama_models()
            running_models = ollama_models_data.get("running", [])
            installed_models = ollama_models_data.get("installed", [])

            # Section: Models currently resident in memory
            st.markdown("##### ⚡ Models Active in Memory (VRAM / RAM)")
            if running_models:
                for rm in running_models:
                    rc1, rc2, rc3 = st.columns([2.5, 1.5, 1])
                    with rc1:
                        st.markdown(f"**`{rm['name']}`**")
                        st.caption(f"Expires at: {rm.get('expires_at', 'idle')}")
                    with rc2:
                        st.markdown(f"🎮 **VRAM:** `{rm['size_vram_mb']} MB` | 💻 **RAM:** `{rm['size_ram_mb']} MB`")
                    with rc3:
                        if st.button("🛑 Unload", key=f"unload_vram_{rm['name']}", use_container_width=True):
                            with st.spinner(f"Evicting {rm['name']} from VRAM..."):
                                un_res = api_client.unload_ollama_model(rm["name"])
                                if un_res.get("success"):
                                    st.success(f"Unloaded {rm['name']}!")
                                    st.rerun()
                                else:
                                    st.error(un_res.get("message"))
            else:
                st.info("No models currently resident in VRAM. (Ollama memory idle)")

            st.markdown("##### 📦 Locally Installed Models on Laptop")
            if installed_models:
                for idx, im in enumerate(installed_models, start=1):
                    with st.container():
                        col_m1, col_m2, col_m3, col_m4 = st.columns([2.5, 1.2, 1.2, 1.3])
                        with col_m1:
                            st.markdown(f"**{idx}. `{im['name']}`**")
                            st.caption(f"Format: {im['format']} | Family: {im['family']} | Modified: {im['modified_at'][:10] if im.get('modified_at') else 'N/A'}")
                        with col_m2:
                            st.markdown(f"💾 **Size:** `{im['size_gb']} GB`")
                            st.caption(f"Params: {im['parameter_size']}")
                        with col_m3:
                            is_loaded = any(rm['name'] == im['name'] or rm['name'].startswith(im['name']) for rm in running_models)
                            if is_loaded:
                                if st.button("🛑 Unload", key=f"btn_un_{im['name']}", use_container_width=True):
                                    with st.spinner(f"Unloading {im['name']}..."):
                                        api_client.unload_ollama_model(im['name'])
                                        st.rerun()
                            else:
                                if st.button("⚡ Load VRAM", key=f"btn_ld_{im['name']}", use_container_width=True):
                                    with st.spinner(f"Pre-loading {im['name']} into VRAM..."):
                                        ld_res = api_client.load_ollama_model(im['name'])
                                        if ld_res.get("success"):
                                            st.success(f"Loaded {im['name']}!")
                                            st.rerun()
                                        else:
                                            st.error(ld_res.get("message"))
                        with col_m4:
                            is_active = (active_provider == "ollama" and active_model == im['name'])
                            if is_active:
                                st.success("✅ Active LLM")
                            else:
                                if st.button("🎯 Set Active", key=f"btn_act_{im['name']}", use_container_width=True):
                                    with st.spinner(f"Activating {im['name']} as active screening model..."):
                                        api_client.update_llm_settings(
                                            provider="ollama",
                                            model=im['name'],
                                            compatibility_mode="auto",
                                        )
                                        # Also warm up the model
                                        api_client.load_ollama_model(im['name'])
                                        st.success(f"Active LLM switched to Ollama ({im['name']})!")
                                        st.rerun()
            else:
                st.info("No models found locally. You can pull a model below.")

            # Model puller
            with st.expander("📥 Pull New Model from Ollama Registry"):
                col_p1, col_p2 = st.columns([3, 1])
                with col_p1:
                    pull_tag = st.text_input(
                        "Model Tag (e.g. `llama3.2:3b`, `qwen2.5-coder:7b`, `mistral:7b`)",
                        placeholder="qwen2.5-coder:7b",
                    )
                with col_p2:
                    st.write("")
                    st.write("")
                    if st.button("📥 Pull Model", use_container_width=True):
                        if pull_tag.strip():
                            with st.spinner(f"Downloading {pull_tag}... this may take a few minutes."):
                                p_res = api_client.pull_ollama_model(pull_tag.strip())
                                if p_res.get("success"):
                                    st.success(f"Model '{pull_tag}' pulled successfully!")
                                    st.rerun()
                                else:
                                    st.error(p_res.get("message"))


