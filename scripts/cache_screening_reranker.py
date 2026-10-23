r"""Download the configured reranker once and verify offline inference.

Run from the repository root: .venv\Scripts\python scripts/cache_screening_reranker.py
Screening itself continues to load local files only.
"""
import os
from pathlib import Path
import sys

if os.name == "nt":
    # Windows accounts without symlink privileges can cache ordinary copies.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from huggingface_hub import snapshot_download
from backend.config import settings
from backend.services.screening_reranker import get_reranker


def main():
    snapshot_download(
        settings.screening_reranker_model,
        allow_patterns=["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
                        "special_tokens_map.json", "vocab.txt", "modules.json", "sentence_bert_config.json",
                        "config_sentence_transformers.json", "1_Pooling/config.json"],
        max_workers=1,
    )
    reranker = get_reranker()
    scores = reranker.predict([
        ("FastAPI REST microservices", "Built FastAPI REST microservices."),
        ("FastAPI REST microservices", "Built React frontend components."),
    ])
    if scores[0] <= scores[1]:
        raise RuntimeError("Reranker validation failed: relevant evidence did not outrank unrelated text")
    print(f"Ready for offline screening: {reranker.model_name}")


if __name__ == "__main__":
    main()
