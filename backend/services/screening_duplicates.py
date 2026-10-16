"""Exact duplicate keys for screening; original CVs and evaluations stay stored."""
import json
import unicodedata

from backend.schemas.match import MatchEvaluationResult


def candidate_name_key(raw_cv: dict) -> str | None:
    name = (raw_cv.get("contact_info") or {}).get("full_name")
    if not isinstance(name, str):
        return None
    key = " ".join(unicodedata.normalize("NFC", name).split()).casefold()
    if key in {"", "candidate name", "candidate", "unknown", "not specified", "not stated", "n/a", "anonymous", "[redacted]"}:
        return None
    return key


def evaluation_key(result: MatchEvaluationResult) -> str:
    """Compare the complete semantic report, excluding identity and run telemetry.

    Equal aggregate scores alone are not duplicates: reasoning, evidence, gaps,
    requirement statuses, confidence and every other evaluation field must match.
    """
    content = result.model_dump(mode="json", exclude={
        "id", "candidate_id", "job_id", "token_usage", "audit_metadata",
        "hitl_validated", "recruiter_notes",
    })
    return json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
