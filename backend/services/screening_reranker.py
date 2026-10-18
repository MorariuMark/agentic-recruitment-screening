"""Bounded, process-cached local cross-encoder inference for screening.

The caller handles unavailable models by retaining hybrid ranking. Downloads are
disabled by default, and this adapter never substitutes scores after a failure.
"""
from __future__ import annotations

from threading import Lock
from typing import Any

import numpy as np

from backend.config import settings

MAX_PAIRS = 6000
MAX_PAIR_CHARACTERS = 4000
_cache: dict[tuple[str, bool], "ScreeningReranker"] = {}
_load_lock = Lock()


def _load_cross_encoder(model_name: str, local_only: bool) -> Any:
    # Import lazily so screening without reranking does not load torch.
    from sentence_transformers import CrossEncoder

    return CrossEncoder(
        model_name,
        local_files_only=local_only,
        trust_remote_code=False,
        max_length=512,
    )


class ScreeningReranker:
    """Serialize inference on one model while preserving pair order."""

    def __init__(self, model_name: str, model: Any):
        self.model_name = model_name
        self._model = model
        self._prediction_lock = Lock()

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        if len(pairs) > MAX_PAIRS:
            raise ValueError(f"Reranking accepts at most {MAX_PAIRS} pairs")
        if not pairs:
            return []
        bounded = []
        for pair in pairs:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2 or not all(isinstance(text, str) for text in pair):
                raise ValueError("Reranking requires pairs of text strings")
            requirement = pair[0][: MAX_PAIR_CHARACTERS // 2]
            evidence = pair[1][: MAX_PAIR_CHARACTERS - len(requirement)]
            bounded.append((requirement, evidence))

        batch_size = max(1, min(64, int(getattr(settings, "screening_reranker_batch_size", 16))))
        scores: list[float] = []
        if not self._prediction_lock.acquire(timeout=1):
            raise RuntimeError("Reranker is busy with another inference")
        try:
            for offset in range(0, len(bounded), batch_size):
                batch = bounded[offset : offset + batch_size]
                output = np.asarray(self._model.predict(
                    batch,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                ), dtype=float)
                if output.shape not in ((len(batch),), (len(batch), 1)) or not np.isfinite(output).all():
                    raise ValueError("Reranker returned invalid scores")
                scores.extend(float(score) for score in output.reshape(-1))
        finally:
            self._prediction_lock.release()
        return scores


def get_reranker() -> ScreeningReranker:
    """Load each configured model once; missing local files fail without download."""
    model_name = getattr(settings, "screening_reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    local_only = bool(getattr(settings, "screening_reranker_local_only", True))
    key = (model_name, local_only)
    if not _load_lock.acquire(timeout=1):
        raise RuntimeError("Reranker is already loading")
    try:
        if key not in _cache:
            _cache[key] = ScreeningReranker(model_name, _load_cross_encoder(model_name, local_only))
        return _cache[key]
    finally:
        _load_lock.release()
