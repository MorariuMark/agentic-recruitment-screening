"""
tests/test_compliance_dossier.py
Tests for EU AI Act Annex III Compliance Dossier generation, SHA-256 seal integrity,
and API endpoint output in JSON and Markdown formats.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend.db.repository import DatabaseRepository
from backend.main import app
from backend.schemas.cv import ContactInfo, ParsedCV, WorkExperience
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    Recommendation,
    RequirementMatch,
    VerbatimCitation,
)
from backend.services.compliance_service import ComplianceService
from backend.services.pii_scrubber import PIIScrubber


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_compliance_service_sha256_hash_deterministic():
    """Verify SHA-256 integrity hash is deterministic and tamper-sensitive."""
    payload_a = {"eval_id": "123", "score": 90.0, "recommendation": "STRONG_MATCH"}
    payload_b = {"recommendation": "STRONG_MATCH", "score": 90.0, "eval_id": "123"}
    payload_c = {"eval_id": "123", "score": 90.1, "recommendation": "STRONG_MATCH"}

    hash_a = ComplianceService.compute_sha256_hash(payload_a)
    hash_b = ComplianceService.compute_sha256_hash(payload_b)
    hash_c = ComplianceService.compute_sha256_hash(payload_c)

    assert len(hash_a) == 64
    assert hash_a == hash_b  # Canonicalized JSON key sorting guarantee
    assert hash_a != hash_c  # Sensitive to score modification


@pytest.mark.asyncio
async def test_compliance_dossier_generation_and_api(client):
    """Seed DB and test GET /api/v1/compliance/dossier/{id} in JSON and Markdown formats."""
    scrubber = PIIScrubber()

    # 1. Seed Job
    jid = uuid4()
    job = JobDescription(
        id=jid,
        title="Senior Security Operations Engineer",
        department="Information Security",
        requirements=[
            JobRequirement(
                id="req_incident_resp",
                title="Incident Response",
                category=RequirementCategory.MUST_HAVE,
                weight=1.5,
                description="Lead incident response for critical enterprise breaches",
            ),
        ],
    )
    await DatabaseRepository.save_job(job)

    # 2. Seed Candidate
    cid = uuid4()
    raw = ParsedCV(
        candidate_id=cid,
        contact_info=ContactInfo(
            full_name="Elena Rostova",
            email="elena.rostova@example.com",
            phone="+44 20 7946 0991",
            location="London, UK",
        ),
        skills=["SIEM", "Splunk", "Incident Handling", "Forensics"],
        experiences=[
            WorkExperience(
                job_title="SecOps Lead",
                company_name="CyberDefend Ltd",
                start_date="2020",
                end_date="Present",
                work_description=["Orchestrated enterprise SOC incident response drills across 500+ endpoints"],
            )
        ],
    )
    anon = scrubber.anonymize_cv(raw)
    anon.candidate_id = cid
    await DatabaseRepository.save_candidate(
        parsed_cv=raw,
        anonymized_candidate=anon,
        chunks_indexed=4,
        filename="elena_rostova_cv.pdf",
    )

    # 3. Seed Evaluation
    eid = uuid4()
    eval_result = MatchEvaluationResult(
        id=eid,
        candidate_id=cid,
        job_id=jid,
        overall_score=88.5,
        must_have_score=90.0,
        nice_to_have_score=85.0,
        must_have_gaps_count=0,
        recommendation=Recommendation.STRONG_MATCH,
        hitl_validated=True,
        recruiter_notes="Candidate demonstrates stellar incident containment track record.",
        citation_verification_score=1.0,
        requirement_matches=[
            RequirementMatch(
                requirement_id="req_incident_resp",
                category=RequirementCategory.MUST_HAVE,
                status=MatchStatus.MET,
                score=0.90,
                citations=[
                    VerbatimCitation(
                        source_id="c1",
                        chunk_index=0,
                        quote="Orchestrated enterprise SOC incident response drills across 500+ endpoints",
                        verified=True,
                    )
                ],
                reasoning="Exceeded incident response leadership requirement with verified metrics.",
            )
        ],
    )
    await DatabaseRepository.save_evaluation(
        eval_result=eval_result,
        candidate_id=cid,
        job_id=jid,
    )
    await DatabaseRepository.update_hitl_validation(
        evaluation_id=eid,
        decision="STRONG_MATCH",
        notes="Candidate demonstrates stellar incident containment track record.",
    )

    # 4. Test API JSON Format
    resp_json = client.get(f"/api/v1/compliance/dossier/{eid}?format=json")
    assert resp_json.status_code == 200
    data = resp_json.json()

    assert data["compliance_standard"] == "Regulation (EU) 2024/1689 (EU AI Act)"
    assert "Annex III, Point 4(a)" in data["risk_classification"]
    assert data["record_metadata"]["evaluation_id"] == str(eid)
    assert len(data["record_metadata"]["cryptographic_sha256_seal"]) == 64

    # Articles 9 through 15
    assert data["article_9_risk_management"]["status"] == "COMPLIANT"
    assert data["article_10_data_governance"]["pii_redaction_enforced"] is True
    assert data["article_11_technical_documentation"]["status"] == "COMPLIANT"
    assert data["article_12_record_keeping"]["status"] == "COMPLIANT"
    assert data["article_13_transparency_and_explainability"]["citation_verification_score"] == 1.0
    assert data["article_14_human_oversight"]["is_decision_finalized_by_human"] is True
    assert data["article_14_human_oversight"]["human_override_exercised"] is True
    assert data["article_15_accuracy_and_cybersecurity"]["status"] == "COMPLIANT"

    # 5. Test API Markdown Format
    resp_md = client.get(f"/api/v1/compliance/dossier/{eid}?format=markdown")
    assert resp_md.status_code == 200
    assert "text/markdown" in resp_md.headers["content-type"]
    md_text = resp_md.text

    assert "# EU AI Act Compliance & Governance Dossier" in md_text
    assert "CERTIFIED - HUMAN OVERSIGHT COMPLETED" in md_text
    assert data["record_metadata"]["cryptographic_sha256_seal"] in md_text
    assert "Senior Security Operations Engineer" in md_text
    assert "Candidate demonstrates stellar incident containment track record." in md_text


@pytest.mark.asyncio
async def test_compliance_dossier_not_found(client):
    """Verify 404 response for nonexistent evaluation ID."""
    ghost_id = uuid4()
    resp = client.get(f"/api/v1/compliance/dossier/{ghost_id}")
    assert resp.status_code == 404
    assert f"Evaluation {ghost_id} not found" in resp.json()["detail"]
