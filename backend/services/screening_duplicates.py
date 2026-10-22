"""
backend/services/screening_duplicates.py
Duplicate identity detection based on document content, email, and verified contact info (E5).
Preserves distinct applications and avoids inferring duplicate identity from evaluation output.
"""

import hashlib
import json
from typing import Optional
import unicodedata

from backend.schemas.match import MatchEvaluationResult


def document_hash_key(raw_cv: dict, raw_text: Optional[str] = None) -> Optional[str]:
    """Compute exact document hash for identical file uploads."""
    text = raw_text or (raw_cv.get("raw_text") if isinstance(raw_cv, dict) else None)
    if text and text.strip():
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    return None


def candidate_identity_key(raw_cv: dict) -> Optional[str]:
    """
    Deterministic identity key for candidate deduplication.
    Requires matching email or phone alongside full name to prevent name collision exclusions.
    Distinct candidates with the same name but different emails produce distinct keys.
    """
    if not isinstance(raw_cv, dict):
        return None

    # Check for exact document hash first
    doc_hash = document_hash_key(raw_cv)

    contact = raw_cv.get("contact_info") or {}
    name = contact.get("full_name")
    email = (contact.get("email") or "").strip().lower()
    phone = (contact.get("phone_number") or contact.get("phone") or "").strip()

    norm_name = " ".join(unicodedata.normalize("NFC", name).split()).casefold() if isinstance(name, str) else None
    if norm_name in {"", "candidate name", "candidate", "unknown", "not specified", "not stated", "n/a", "anonymous", "[redacted]"}:
        norm_name = None

    if email and norm_name:
        return f"{norm_name}:{email}"
    elif email:
        return f"email:{email}"
    elif norm_name and phone:
        return f"{norm_name}:{phone}"
    elif doc_hash:
        return f"doc:{doc_hash}"

    return None


def candidate_name_key(raw_cv: dict) -> Optional[str]:
    """Compatibility alias for candidate identity key."""
    return candidate_identity_key(raw_cv)


def evaluation_key(result: MatchEvaluationResult) -> str:
    """Compare evaluation structure for diagnostics. An evaluation is NOT an identity record."""
    content = result.model_dump(mode="json", exclude={
        "id", "candidate_id", "job_id", "token_usage", "audit_metadata",
        "hitl_validated", "recruiter_notes",
    })
    return json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
