"""
tests/test_audit_exporter.py
Unit and integration tests for AuditExporter service and tagged JSON export endpoints.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend.main import app
import backend.api.routes as routes
from backend.schemas.cv import (
    AnonymizedCandidate,
    ContactInfo,
    CustomSection,
    DetailStatus,
    Education,
    LanguageSkill,
    ParsedCV,
    Project,
    WorkExperience,
)
from backend.schemas.job import (
    JobDescription,
    JobRequirement,
    RequirementCategory,
)
from backend.services.audit_exporter import AuditExporter


def test_cv_tagged_export_structure():
    """Verify CV export properly categorizes fields into anonymised, visible, unused, and extra."""
    parsed_cv = ParsedCV(
        contact_info=ContactInfo(
            full_name="Morgan Chase",
            email="morgan@example.com",
            phone_number="+1 555-9876",
            location="San Francisco, CA",
            linkedin_url="https://linkedin.com/in/morganchase",
        ),
        summary="Senior AI Engineer specializing in distributed LLM architectures.",
        skills=["Python", "FastAPI", "ChromaDB"],
        experiences=[
            WorkExperience(
                job_title="Lead ML Engineer",
                company_name="Alpha Labs",
                work_description=["Engineered RAG pipelines with dense embeddings."],
                skills_used=["Python", "ChromaDB"],
            )
        ],
        education=[
            Education(
                degree_title="M.S. Computer Science",
                institution_name="Stanford University",
                graduation_year=2021,
            )
        ],
        certifications=["AWS Certified Solutions Architect"],
        projects=[
            Project(
                project_name="DeepRL Navigator",
                description=["Implemented PPO agent for quadcopter control."],
                technologies=["PyTorch", "ROS2"],
                project_url="https://github.com/example/rl-nav",
            )
        ],
        languages=[
            LanguageSkill(language="English", proficiency="Native"),
            LanguageSkill(language="German", proficiency="C1"),
        ],
        custom_sections=[
            CustomSection(
                section_title="Volunteering",
                items=["Mentor for First Robotics team."],
            )
        ],
        unused_details=["Enjoys marathon running, chess, and landscape photography."],
        raw_text="Full raw resume text.",
    )

    anonymized = AnonymizedCandidate(
        candidate_id=uuid4(),
        anonymized_work_experiences=parsed_cv.experiences,
        anonymized_education=parsed_cv.education,
        anonymized_skills=parsed_cv.skills,
        anonymized_certifications=parsed_cv.certifications,
        anonymized_projects=parsed_cv.projects,
        anonymized_languages=parsed_cv.languages,
        anonymized_custom_sections=parsed_cv.custom_sections,
        sanitized_text="Sanitized resume text.",
        demographic_data={"name_origin": "English"},
    )

    export = AuditExporter.build_cv_tagged_export(
        parsed_cv=parsed_cv,
        anonymized_candidate=anonymized,
        chunks_count=12,
    )

    assert export.export_type == "candidate_cv"
    assert export.candidate_id == anonymized.candidate_id

    # Check status tags coverage
    statuses_present = {item.status for item in export.items}
    assert DetailStatus.ANONYMISED in statuses_present
    assert DetailStatus.VISIBLE in statuses_present
    assert DetailStatus.UNUSED in statuses_present
    assert DetailStatus.EXTRA in statuses_present

    # Check specific tag logic
    name_item = next(i for i in export.items if i.field_name == "full_name")
    assert name_item.status == DetailStatus.ANONYMISED
    assert name_item.raw_value == "Morgan Chase"
    assert name_item.value == "[CANDIDATE_NAME]"

    skills_item = next(i for i in export.items if i.field_name == "skills")
    assert skills_item.status == DetailStatus.VISIBLE
    assert "FastAPI" in skills_item.value

    proj_item = next(i for i in export.items if i.field_name == "projects")
    assert proj_item.status == DetailStatus.VISIBLE
    assert proj_item.value[0]["project_name"] == "DeepRL Navigator"

    lang_item = next(i for i in export.items if i.field_name == "languages")
    assert lang_item.status == DetailStatus.VISIBLE
    assert len(lang_item.value) == 2

    custom_item = next(i for i in export.items if i.field_name == "custom_sections")
    assert custom_item.status == DetailStatus.VISIBLE
    assert custom_item.value[0]["section_title"] == "Volunteering"

    unused_item = next(i for i in export.items if i.field_name == "unused_details")
    assert unused_item.status == DetailStatus.UNUSED
    assert any("marathon" in u for u in unused_item.value)

    extra_item = next(i for i in export.items if i.field_name == "candidate_id")
    assert extra_item.status == DetailStatus.EXTRA
    assert extra_item.value == str(anonymized.candidate_id)

    # Check summary tag counts
    assert export.tag_counts["anonymised"] > 0
    assert export.tag_counts["visible"] > 0
    assert export.tag_counts["unused"] > 0
    assert export.tag_counts["extra"] > 0


def test_jd_tagged_export_structure():
    """Verify JD export properly tags criteria, scoring weights, and unmapped content."""
    jd = JobDescription(
        id=uuid4(),
        title="Principal AI Infrastructure Engineer",
        department="AI Platform",
        seniority_level="Principal",
        requirements=[
            JobRequirement(
                id="req_k8s",
                title="Kubernetes & Ray",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Cluster orchestration for distributed training.",
                minimum_years_experience=5,
            ),
            JobRequirement(
                id="req_go",
                title="Go Programming",
                category=RequirementCategory.NICE_TO_HAVE,
                weight=0.8,
                description="Developing performant sidecars.",
                minimum_years_experience=2,
            ),
        ],
        unused_details=[
            "Comprehensive health benefits and 401(k) matching.",
            "We are an Equal Opportunity Employer.",
        ],
        raw_text="Job posting full text.",
    )

    export = AuditExporter.build_jd_tagged_export(job_description=jd)

    assert export.export_type == "job_description"
    assert export.job_id == jd.id

    statuses_present = {item.status for item in export.items}
    assert DetailStatus.VISIBLE in statuses_present
    assert DetailStatus.UNUSED in statuses_present
    assert DetailStatus.EXTRA in statuses_present

    title_item = next(i for i in export.items if i.field_name == "title")
    assert title_item.status == DetailStatus.VISIBLE
    assert title_item.value == "Principal AI Infrastructure Engineer"

    req_item = next(i for i in export.items if i.field_name == "requirement:req_k8s")
    assert req_item.status == DetailStatus.VISIBLE
    assert req_item.value["title"] == "Kubernetes & Ray"

    unused_item = next(i for i in export.items if i.field_name == "unused_details")
    assert unused_item.status == DetailStatus.UNUSED
    assert any("Equal Opportunity" in u for u in unused_item.value)

    weight_item = next(i for i in export.items if i.field_name == "weight:req_k8s")
    assert weight_item.status == DetailStatus.EXTRA
    assert weight_item.value == 1.0


def test_api_cv_and_jd_export_endpoints():
    """Verify REST endpoints /cv/{candidate_id}/export and /job/export."""
    client = TestClient(app)

    # 1. Non-existent candidate export returns 404
    fake_id = uuid4()
    res_404 = client.get(f"/api/v1/cv/{fake_id}/export")
    assert res_404.status_code == 404

    # 2. Add a mocked candidate to routes store and test 200 export
    cid = uuid4()
    mock_parsed = ParsedCV(
        contact_info=ContactInfo(full_name="Taylor Swift", email="taylor@example.com"),
        skills=["Audio Engineering", "Python"],
        raw_text="Resume",
    )
    mock_anonymized = AnonymizedCandidate(
        candidate_id=cid,
        anonymized_skills=mock_parsed.skills,
        sanitized_text="Sanitized",
    )
    routes._CANDIDATE_RAW_STORE[cid] = mock_parsed
    routes._CANDIDATE_ANONYMIZED_STORE[cid] = mock_anonymized
    routes._CANDIDATE_CHUNKS_STORE[cid] = 5

    res_cv = client.get(f"/api/v1/cv/{cid}/export")
    assert res_cv.status_code == 200
    cv_data = res_cv.json()
    assert cv_data["export_type"] == "candidate_cv"
    assert cv_data["candidate_id"] == str(cid)
    assert "tag_counts" in cv_data
    assert len(cv_data["items"]) > 0

    # 3. Test POST /api/v1/job/export
    jd_payload = {
        "id": str(uuid4()),
        "title": "Cloud Architect",
        "department": "Infrastructure",
        "requirements": [
            {
                "id": "req_aws",
                "title": "AWS Cloud",
                "category": "must_have",
                "weight": 1.0,
                "description": "AWS ECS and Terraform",
            }
        ],
        "unused_details": ["Commuter benefits included."],
    }
    res_jd = client.post("/api/v1/job/export", json=jd_payload)
    assert res_jd.status_code == 200
    jd_data = res_jd.json()
    assert jd_data["export_type"] == "job_description"
    assert jd_data["job_id"] == jd_payload["id"]
    assert "tag_counts" in jd_data
    assert len(jd_data["items"]) > 0
