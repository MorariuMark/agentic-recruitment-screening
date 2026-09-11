"""
frontend/app.py
Streamlit Recruiter Dashboard for Agentic Recruitment Screening,
Semantic Matching, Human-in-the-Loop (HITL) Validation, and Interview Guide Synthesis.
"""

import json
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
        st.success(f"🟢 Backend Online\nProvider: `{health.get('llm_provider', 'unknown')}`")
    else:
        st.error(f"🔴 Backend Offline\nEnsure FastAPI is running on port 8000.")

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
tab_cv, tab_jd, tab_match, tab_hitl, tab_interview = st.tabs([
    "📄 1. Candidate Ingestion & PII Audit",
    "📋 2. Job Description",
    "⚖️ 3. Semantic Match & Citations",
    "🛡️ 4. Recruiter HITL Gate",
    "🎯 5. Tailored Interview Guide",
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
            type=["pdf", "txt"],
            help="Upload candidate PDF or plain text resume",
        )

    with col_sample:
        st.markdown("**Or pick a pre-built mock candidate:**")
        sample_options = {
            "Strong AI Engineer": "data/mock_cvs/strong_ai_engineer.txt",
            "Borderline Junior Developer": "data/mock_cvs/borderline_junior_developer.txt",
            "Reject (Unrelated Background)": "data/mock_cvs/reject_unrelated_candidate.txt",
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

    # 1. URL Import Section
    with st.expander("🌐 Import Job Description from Web URL (LinkedIn, Indeed, Company Site, etc.)", expanded=True):
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
                with st.spinner("Accessing webpage, parsing role metadata, and decomposing requirements with AI..."):
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
