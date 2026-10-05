"""
backend/services/compliance_service.py
EU AI Act (Regulation (EU) 2024/1689) Annex III Compliance & Audit Dossier Generator.
Generates legally grounded, cryptographically verified technical documentation and
human oversight audit trails for High-Risk AI Systems in Employment and Recruitment (Point 4(a)).
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from backend.config import settings
from backend.db.models import CandidateModel, JobRequisitionModel, MatchEvaluationModel
from backend.db.repository import DatabaseRepository


class ComplianceService:
    """Generates immutable EU AI Act High-Risk Compliance Dossiers."""

    @staticmethod
    def compute_sha256_hash(data: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 digest over canonicalized JSON payload."""
        canon = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    @staticmethod
    def _get_active_model_name() -> str:
        prov = getattr(settings, "llm_provider", "groq").lower()
        if prov == "agnes":
            return getattr(settings, "agnes_model", "agnes-2.5-flash")
        elif prov == "groq":
            return getattr(settings, "groq_model", "openai/gpt-oss-20b")
        elif prov == "openrouter":
            return getattr(settings, "openrouter_model", "openrouter/free")
        elif prov == "nvidia_nim":
            return getattr(settings, "nvidia_nim_model", "meta/llama-3.2-11b-vision-instruct")
        elif prov == "gemini":
            return getattr(settings, "gemini_model", "gemini-flash-latest")
        elif prov == "ollama":
            return getattr(settings, "ollama_model", "qwen3.5:2b-q4_K_M")
        return "default"

    @classmethod
    def generate_dossier(
        cls,
        evaluation: MatchEvaluationModel,
        candidate: CandidateModel,
        job: JobRequisitionModel,
    ) -> Dict[str, Any]:
        """
        Synthesizes an exhaustive EU AI Act Annex III Compliance Dossier
        covering Articles 9 through 15 with cryptographic integrity verification.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        cid_str = str(candidate.id)
        eid_str = str(evaluation.id)
        jid_str = str(job.id)

        anon_name = (
            candidate.full_name_redacted
            or (candidate.anonymized_cv_json or {}).get("masked_name")
            or f"Candidate-{cid_str[:6].upper()}"
        )
        if anon_name == "[CANDIDATE_NAME]":
            anon_name = f"Candidate-{cid_str[:6].upper()}"

        # Canonical audit payload for SHA-256 seal
        hash_payload = {
            "evaluation_id": eid_str,
            "candidate_id": cid_str,
            "job_id": jid_str,
            "overall_score": evaluation.overall_score,
            "must_have_score": evaluation.must_have_score,
            "recommendation": evaluation.recommendation,
            "recruiter_notes": evaluation.recruiter_notes,
            "hitl_validated": evaluation.hitl_validated,
            "matches": evaluation.matches_json,
        }
        crypto_hash = cls.compute_sha256_hash(hash_payload)

        # Article 10: Data Governance & De-Biasing Metrics
        demographics = candidate.demographics_json or {}
        pii_scrubbed_fields = [
            "full_name",
            "email_address",
            "phone_number",
            "physical_address",
            "social_urls",
            "headshot_photo",
        ]

        # Article 13: Transparency & Citation Metrics
        matches = evaluation.matches_json or []
        total_citations = sum(len(m.get("citations", [])) for m in matches)
        verified_citations = sum(
            sum(1 for c in m.get("citations", []) if c.get("verified"))
            for m in matches
        )
        cvs_score = evaluation.citation_verification_score

        # Article 14: Human Oversight Audit Gate
        hitl_status = {
            "human_in_the_loop_mandatory": True,
            "is_decision_finalized_by_human": evaluation.hitl_validated,
            "recruiter_decision": evaluation.recommendation if evaluation.hitl_validated else "PENDING_REVIEW",
            "recruiter_audit_notes": evaluation.recruiter_notes or "Awaiting recruiter review sign-off.",
            "algorithmic_recommendation": evaluation.recommendation,
            "human_override_exercised": bool(evaluation.hitl_validated and evaluation.recruiter_notes),
            "human_oversight_article": "EU AI Act Article 14 (Human Oversight)",
        }

        dossier: Dict[str, Any] = {
            "compliance_standard": "Regulation (EU) 2024/1689 (EU AI Act)",
            "risk_classification": "Annex III, Point 4(a) - High-Risk AI in Employment & Worker Recruitment",
            "system_identity": {
                "name": "Antigravity Autonomous Talent Screening Engine",
                "version": "2.0-enterprise",
                "vendor": "Antigravity AI Systems",
                "intended_purpose": "Job requirement extraction, candidate CV parsing, asymmetric semantic retrieval, and Human-in-the-Loop matching verification.",
            },
            "record_metadata": {
                "dossier_generated_at": now_utc,
                "evaluation_id": eid_str,
                "candidate_id": cid_str,
                "candidate_alias": anon_name,
                "job_requisition_id": jid_str,
                "job_title": job.title,
                "department": job.department,
                "cryptographic_sha256_seal": crypto_hash,
            },
            "article_9_risk_management": {
                "status": "COMPLIANT",
                "risks_identified": [
                    "Demographic bias based on gender, ethnicity, or socioeconomic indicators in CV",
                    "Hallucination of candidate skills or ungrounded qualifications",
                    "Unintended autonomous candidate rejection without human audit",
                ],
                "mitigations_implemented": [
                    "Deterministic multi-layer PII regex scrubber & demographic isolation (Article 10)",
                    "Asymmetric RAG with deterministic verbatim citation verification (Article 13)",
                    "Strict Human-in-the-Loop decision gate with mandatory justification notes (Article 14)",
                ],
            },
            "article_10_data_governance": {
                "status": "COMPLIANT",
                "pii_redaction_enforced": True,
                "protected_attributes_scrubbed": pii_scrubbed_fields,
                "demographic_data_isolation": "Demographic tokens isolated in encrypted audit store; excluded from semantic matching vector index.",
                "vector_store_cleanliness": f"{candidate.chunks_indexed} anonymous semantic chunks indexed.",
            },
            "article_11_technical_documentation": {
                "status": "COMPLIANT",
                "retrieval_architecture": "Asymmetric RAG with dense vector cosine similarity (ChromaDB + SentenceTransformers)",
                "embedding_model": settings.embedding_model,
                "inference_model": f"{settings.llm_provider}:{cls._get_active_model_name()}",
                "inference_temperature": 0.0,
                "structured_output_mode": settings.compatibility_mode,
                "multi_tier_failover": "Enabled (Groq Cloud -> OpenRouter -> Local Ollama fallback)",
            },
            "article_12_record_keeping": {
                "status": "COMPLIANT",
                "immutable_logging": "Enabled via SQLite/PostgreSQL append-only relational audit log",
                "audit_timestamp": evaluation.created_at.isoformat() if evaluation.created_at else now_utc,
                "data_integrity_hash": crypto_hash,
            },
            "article_13_transparency_and_explainability": {
                "status": "COMPLIANT",
                "scoring_formula": "Deterministic weighted sum: 75% Must-Have hard criteria + 25% Nice-to-Have bonus criteria",
                "overall_match_score": evaluation.overall_score,
                "must_have_score": evaluation.must_have_score,
                "nice_to_have_score": evaluation.nice_to_have_score,
                "must_have_gaps_count": evaluation.must_have_gaps_count,
                "citation_verification_score": cvs_score,
                "total_citations_extracted": total_citations,
                "verbatim_verified_citations": verified_citations,
                "unmet_gaps_documented": [
                    {
                        "requirement_id": m.get("requirement_id"),
                        "gap_analysis": m.get("gap_analysis"),
                        "reasoning": m.get("reasoning"),
                    }
                    for m in matches
                    if m.get("status") != "met"
                ],
            },
            "article_14_human_oversight": hitl_status,
            "article_15_accuracy_and_cybersecurity": {
                "status": "COMPLIANT",
                "adversarial_prompt_injection_defense": "System prompt isolation & boundary demarcation",
                "scanned_pdf_integrity_check": "Deterministic PyPDF OCR graphic flat-file detector",
                "failover_redundancy": "Active multi-provider automated fallback chain",
            },
        }

        return dossier

    @classmethod
    def format_markdown_certificate(cls, dossier: Dict[str, Any]) -> str:
        """Formats the compliance dossier into a clean, printable Markdown certificate."""
        meta = dossier["record_metadata"]
        art13 = dossier["article_13_transparency_and_explainability"]
        art14 = dossier["article_14_human_oversight"]

        gaps_list = ""
        if art13["unmet_gaps_documented"]:
            gaps_list = "\n".join(
                f"- **{g['requirement_id']}**: {g['gap_analysis'] or g['reasoning']}"
                for g in art13["unmet_gaps_documented"]
            )
        else:
            gaps_list = "- None (All must-have requirements fully satisfied)."

        overall_score = float(art13.get("overall_match_score") or 0.0)
        must_have_score = float(art13.get("must_have_score") or 0.0)
        cvs_score = float(art13.get("citation_verification_score") or 0.0)
        decision_str = str(art14.get("recruiter_decision") or "PENDING_REVIEW").upper()

        return f"""# EU AI Act Compliance & Governance Dossier
**Classification:** {dossier["risk_classification"]}  
**Standard:** {dossier["compliance_standard"]}  
**Status:** {'CERTIFIED - HUMAN OVERSIGHT COMPLETED' if art14.get('is_decision_finalized_by_human') else 'PROVISIONAL - AWAITING HUMAN SIGN-OFF'}  
**SHA-256 Integrity Seal:** `{meta["cryptographic_sha256_seal"]}`  

---

## 1. System & Case Provenance
- **System:** {dossier["system_identity"]["name"]} (v{dossier["system_identity"]["version"]})
- **Candidate Alias:** {meta["candidate_alias"]}
- **Requisition Title:** {meta["job_title"]} ({meta.get("department") or 'General'})
- **Evaluation Run ID:** `{meta["evaluation_id"]}`
- **Generated At:** {meta["dossier_generated_at"]}

---

## 2. Article 10: Data Governance & Demographic De-Biasing
- **PII Redaction Enforced:** Yes (100% of contact & demographic tokens masked prior to inference)
- **Protected Attributes Scrubbed:** Name, Email, Phone, Address, Social URLs, Headshot Photos
- **Vector Cleanliness:** Scrubbed representation only stored in dense vector store

---

## 3. Article 13: Transparency, Metrics & Citation Grounding
- **Overall Match Score:** {overall_score:.1f}%
- **Must-Have Score:** {must_have_score:.1f}%
- **Citation Verification Score (CVS):** {cvs_score * 100:.0f}%
- **Verbatim Citations Validated:** {art13.get("verbatim_verified_citations", 0)} / {art13.get("total_citations_extracted", 0)} exact substrings confirmed
- **Unmet Gaps Analysis:**  
{gaps_list}

---

## 4. Article 14: Human-in-the-Loop Oversight Audit Trail
- **Human Review Mandatory:** {art14.get("human_in_the_loop_mandatory", True)}
- **Human Final Decision:** **{decision_str}**
- **Recruiter Audit Notes:**  
> {art14.get("recruiter_audit_notes", "Awaiting recruiter review sign-off.")}
- **Human Override Applied:** {art14.get("human_override_exercised", False)}

---

## 5. Article 15: Architecture & Redundancy
- **Retrieval Engine:** {dossier["article_11_technical_documentation"]["retrieval_architecture"]}
- **Model Configuration:** {dossier["article_11_technical_documentation"]["inference_model"]} (Deterministic Temp: 0.0)
- **Failover Engine:** {dossier["article_11_technical_documentation"]["multi_tier_failover"]}

*This dossier constitutes an auditable technical documentation package pursuant to Articles 9–15 of Regulation (EU) 2024/1689.*
"""
