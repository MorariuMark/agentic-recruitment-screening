"""
backend/services/action_logger.py
High-fidelity action and LLM execution logger designed for deep AI-agent inspection,
traceability, and provenance auditing. Captures full prompt context, raw model strings,
parsed JSON structures, token metrics, latency, and candidate/requirement metadata.
"""

from collections import deque
from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional
import uuid
import copy

logger = logging.getLogger("recruitment_screening.action_logger")

_LOCK = threading.RLock()


class ActionLogger:
    """
    Singleton action logger maintaining a thread-safe ring buffer of every LLM and workflow action.
    Exposes complete payloads (prompts, raw outputs, and parsed JSON) formatted for machine consumption.
    Also tracks currently in-flight requests in real-time.
    """

    _instance: Optional["ActionLogger"] = None

    def __new__(cls) -> "ActionLogger":
        if cls._instance is None:
            cls._instance = super(ActionLogger, cls).__new__(cls)
            cls._instance._buffer = deque(maxlen=500)
            cls._instance._in_flight = {}
        return cls._instance

    def record_start(
        self,
        action_type: str,
        provider: str,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Records an active/in-flight LLM call before generation starts."""
        call_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        start_mono = time.monotonic()
        with _LOCK:
            if not hasattr(self, "_in_flight"):
                self._in_flight = {}
            # Clean up stale entries (> 30 mins)
            stale = [cid for cid, item in self._in_flight.items() if (start_mono - item.get("start_mono", start_mono)) > 1800]
            for cid in stale:
                self._in_flight.pop(cid, None)
            est_tokens = max(1, len(prompt or "") // 4)
            self._in_flight[call_id] = {
                "id": call_id,
                "timestamp": ts,
                "start_mono": start_mono,
                "action_type": action_type or "general",
                "provider": provider.lower() if provider else "unknown",
                "model": model or "unknown",
                "prompt": prompt or "",
                "system_prompt": system_prompt,
                "prompt_tokens": est_tokens,
                "metadata": copy.deepcopy(metadata or {}),
                "status": "running",
            }
        return call_id

    def record_finish(
        self,
        call_id: Optional[str],
        action_type: str,
        provider: str,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        raw_response: str = "",
        parsed_json: Optional[Any] = None,
        latency_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        status: str = "success",
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Removes the in-flight entry and permanently records completed action."""
        with _LOCK:
            if call_id and hasattr(self, "_in_flight"):
                self._in_flight.pop(call_id, None)
        return self.record_action(
            action_type=action_type,
            provider=provider,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            raw_response=raw_response,
            parsed_json=parsed_json,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            status=status,
            error=error,
            metadata=metadata,
            entry_id=call_id,
        )

    def get_live_state(self, limit: int = 50) -> Dict[str, Any]:
        """Returns in-flight requests and most recent completed actions."""
        now_mono = time.monotonic()
        with _LOCK:
            in_flight = []
            if hasattr(self, "_in_flight"):
                for item in self._in_flight.values():
                    entry = dict(item)
                    elapsed = round(max(0.0, now_mono - entry.pop("start_mono", now_mono)), 1)
                    entry["elapsed_seconds"] = elapsed
                    in_flight.append(entry)
            recent = list(self._buffer)

        recent.reverse()
        if limit > 0 and len(recent) > limit:
            recent = recent[:limit]

        return {
            "in_flight": in_flight,
            "recent": recent,
            "total_logged": len(self._buffer),
        }

    def record_action(
        self,
        action_type: str,
        provider: str,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        raw_response: str = "",
        parsed_json: Optional[Any] = None,
        latency_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        status: str = "success",
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        entry_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records a single LLM or agent action with its input prompt, raw response,
        and structured JSON payload.
        """
        ts = datetime.now(timezone.utc).isoformat()
        final_id = entry_id or str(uuid.uuid4())

        # If parsed_json was not passed, attempt to parse raw_response if it resembles JSON
        parsed_data = parsed_json
        if parsed_data is None and raw_response:
            trimmed = raw_response.strip()
            if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
                try:
                    parsed_data = json.loads(trimmed)
                except Exception:
                    parsed_data = None

        tps = round(completion_tokens / (latency_ms / 1000.0), 2) if (latency_ms > 0 and completion_tokens > 0) else 0.0
        entry: Dict[str, Any] = {
            "id": final_id,
            "timestamp": ts,
            "action_type": action_type or "general",
            "provider": provider.lower() if provider else "unknown",
            "model": model or "unknown",
            "status": status,
            "latency_ms": round(max(0.0, float(latency_ms)), 2),
            "tokens_per_second": tps,
            "tokens": {
                "prompt": max(0, int(prompt_tokens)),
                "completion": max(0, int(completion_tokens)),
                "total": max(0, int(total_tokens or (prompt_tokens + completion_tokens))),
                "tokens_per_second": tps,
            },
            "prompt": prompt or "",
            "system_prompt": system_prompt,
            "raw_response": raw_response or "",
            "parsed_json": parsed_data,
            "error": error,
            "metadata": copy.deepcopy(metadata or {}),
        }

        with _LOCK:
            self._buffer.append(entry)

        return entry

    def get_logs(
        self,
        limit: int = 200,
        action_type: Optional[str] = None,
        candidate_id: Optional[str] = None,
        job_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves recent action entries, optionally filtered by action_type, candidate_id, or job_id.
        Returns chronological order (earliest first).
        """
        with _LOCK:
            entries = list(self._buffer)

        filtered = []
        for entry in entries:
            if action_type and entry.get("action_type") != action_type:
                continue
            meta = entry.get("metadata", {})
            if candidate_id and meta.get("candidate_id") != str(candidate_id):
                continue
            if job_id and meta.get("job_id") != str(job_id):
                continue
            if run_id and meta.get("run_id") != str(run_id):
                continue
            filtered.append(entry)

        if limit > 0 and len(filtered) > limit:
            filtered = filtered[-limit:]

        return filtered

    async def persist_run(self, run_id: str) -> None:
        """Persist captured calls at candidate checkpoints, retaining original timestamps."""
        from backend.db.models import AuditLogModel
        from backend.db.session import async_session_scope
        from sqlalchemy import select
        entries = self.get_logs(limit=0, run_id=run_id)
        if not entries:
            return
        async with async_session_scope() as db:
            known = set((await db.scalars(select(AuditLogModel.id).where(
                AuditLogModel.id.in_([entry["id"] for entry in entries])))).all())
            for entry in entries:
                if entry["id"] not in known:
                    db.add(AuditLogModel(id=entry["id"], entity_type="screening_run",
                        entity_id=run_id, action="model_call", details_json=entry,
                        created_at=datetime.fromisoformat(entry["timestamp"])))
            await db.commit()

    def get_all_logs(self) -> List[Dict[str, Any]]:
        """Returns all recorded logs currently in memory."""
        with _LOCK:
            return list(self._buffer)

    def remove_candidate(self, candidate_id: str) -> None:
        """Erase retained prompts/results associated with a permanently deleted CV."""
        with _LOCK:
            self._buffer = deque((entry for entry in self._buffer if candidate_id not in str(entry)), maxlen=500)

    def clear(self) -> None:
        """Flushes the in-memory action buffer and in-flight tracking."""
        with _LOCK:
            self._buffer.clear()
            if hasattr(self, "_in_flight"):
                self._in_flight.clear()


action_logger = ActionLogger()
