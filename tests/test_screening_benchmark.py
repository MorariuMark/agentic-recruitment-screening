"""Offline metrics and explicit-fixture benchmark regression contracts."""
import json
from types import SimpleNamespace

import pytest

from scripts.benchmark_screening import evaluate_ranking, main, run_benchmark, smoke_dataset, smoke_embeddings


def test_metrics_match_hand_computed_values():
    labels = {"a": 2, "b": 1, "c": 0}
    result = evaluate_ranking(["b", "c", "a"], labels, k=2, pool_size=2)
    assert result["recall_at_pool"] == .5
    assert result["precision_at_k"] == .5
    assert result["ndcg_at_k"] == pytest.approx(1 / (3 + 1 / 1.584962500721156))
    perfect = evaluate_ranking(["a", "b", "c"], labels, k=2, pool_size=3)
    assert perfect == {"recall_at_pool": 1., "precision_at_k": 1., "ndcg_at_k": 1.}


def test_empty_relevance_and_short_rankings_are_defined():
    assert evaluate_ranking(["a"], {"a": 0}, 5, 10) == {"recall_at_pool": 0., "precision_at_k": 0., "ndcg_at_k": 0.}
    assert evaluate_ranking(["a"], {"a": 2}, 5, 10)["precision_at_k"] == .2


@pytest.mark.parametrize("ranking,labels", [(["a", "a"], {"a": 1}), (["x"], {"a": 1}), (["a"], {"a": 3}), (["a"], {"a": True})])
def test_invalid_annotations_and_rankings_are_rejected(ranking, labels):
    with pytest.raises(ValueError):
        evaluate_ranking(ranking, labels)


def test_synthetic_smoke_is_reproducible_without_real_models():
    dataset = smoke_dataset()
    assert dataset == smoke_dataset()
    first = run_benchmark(dataset, smoke_embeddings, k=2, pool_size=4, synthetic=True)
    second = run_benchmark(dataset, smoke_embeddings, k=2, pool_size=4, synthetic=True)
    assert first["metadata"]["synthetic"] is True
    assert first["metadata"]["candidate_count"] == 12
    assert first["metadata"]["job_count"] == 3
    assert first["metadata"]["purpose"] == "synthetic regression only"
    for left, right in zip(first["jobs"], second["jobs"]):
        for pipeline in ("baseline", "hybrid"):
            assert left["pipelines"][pipeline]["ranked_ids"] == right["pipelines"][pipeline]["ranked_ids"]
            assert left["pipelines"][pipeline]["duration_ms"] >= 0
            assert len(left["pipelines"][pipeline]["ranked_ids"]) == 4


def test_incomplete_labels_fail_before_embedding():
    dataset = smoke_dataset()
    dataset["jobs"][0]["labels"].pop(next(iter(dataset["jobs"][0]["labels"])))
    def forbidden(_):
        raise AssertionError("Inference must not start")
    with pytest.raises(ValueError, match="exactly one label"):
        run_benchmark(dataset, forbidden)


def test_reranker_failure_preserves_hybrid_ranking():
    def fail(_):
        raise OSError("Unavailable")
    report = run_benchmark(smoke_dataset(), smoke_embeddings, k=2, pool_size=4,
                           reranker=SimpleNamespace(predict=fail, model_name="unavailable"))
    for job in report["jobs"]:
        assert job["pipelines"]["reranked"]["ranked_ids"] == job["pipelines"]["hybrid"]["ranked_ids"]
        assert job["pipelines"]["reranked"]["applied"] is False
        assert any("retained hybrid" in warning for warning in job["warnings"])


def test_reranker_is_optional_and_records_identity():
    reranker = SimpleNamespace(predict=lambda pairs: [.5] * len(pairs), model_name="injected-reranker")
    report = run_benchmark(smoke_dataset(), smoke_embeddings, k=2, pool_size=4, reranker=reranker)
    assert report["metadata"]["reranker_model"] == "injected-reranker"
    assert all(job["pipelines"]["reranked"]["applied"] for job in report["jobs"])


def test_cli_smoke_writes_explicit_report(tmp_path):
    output = tmp_path / "report.json"
    assert main(["--smoke", "--k", "2", "--pool-size", "4", "--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["metadata"]["embedding_model"] == "synthetic-hash-v1"
    assert report["metadata"]["reranker_requested"] is False


@pytest.mark.parametrize("k,pool", [(0, 4), (5, 4)])
def test_invalid_limits_are_rejected(k, pool):
    with pytest.raises(ValueError):
        run_benchmark(smoke_dataset(), smoke_embeddings, k=k, pool_size=pool)
