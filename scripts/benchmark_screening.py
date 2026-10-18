"""Compare screening pipelines on explicitly supplied, independently labelled data.

Input: {"split": "held_out", "jobs": [{"job": <JobDescription>,
"candidates": [<AnonymizedCandidate>], "labels": {"candidate UUID": 0|1|2}}]}.
Labels mean unsuitable, plausible, and strong match. Every candidate must have a
label. Have reviewers annotate independently of pipeline scores; reserve held-out
jobs and candidates for validation after tuning. Synthetic smoke results are only
regression checks, never evidence of real-world screening quality.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from uuid import NAMESPACE_URL, uuid5

# Also support ``python scripts/benchmark_screening.py`` from any directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription
from backend.services.hybrid_screening import HybridRankingEngine, VERSION
from backend.services.pre_ranking import PreRankingEngine


def evaluate_ranking(ranked_ids, labels, k=10, pool_size=100):
    """Use relevance > 0 for recall/precision and graded gains for nDCG.

    Precision's denominator is k, even when fewer candidates are returned. A
    cohort with no relevant candidates receives zero recall and zero nDCG.
    """
    if k < 1 or pool_size < 1:
        raise ValueError("k and pool_size must be positive")
    ranked_ids = [str(value) for value in ranked_ids]
    labels = {str(key): value for key, value in labels.items()}
    if any(type(value) is not int or value not in (0, 1, 2) for value in labels.values()):
        raise ValueError("Labels must be integer relevance grades 0, 1, or 2")
    if len(ranked_ids) != len(set(ranked_ids)) or not set(ranked_ids).issubset(labels):
        raise ValueError("Ranking must contain unique labelled candidate IDs")
    relevant = sum(value > 0 for value in labels.values())
    found = sum(labels[candidate_id] > 0 for candidate_id in ranked_ids[:pool_size])
    precision = sum(labels[candidate_id] > 0 for candidate_id in ranked_ids[:k]) / k
    gains = [labels[candidate_id] for candidate_id in ranked_ids[:k]]
    ideal = sorted(labels.values(), reverse=True)[:k]
    dcg = lambda grades: sum((2 ** grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))
    denominator = dcg(ideal)
    return {"recall_at_pool": found / relevant if relevant else 0.,
            "precision_at_k": precision, "ndcg_at_k": dcg(gains) / denominator if denominator else 0.}


def run_benchmark(dataset, embedding_fn, *, k=10, pool_size=100, reranker=None, synthetic=False, embedding_model="injected"):
    """Run without database access, deep LLM calls, or implicit private data loading."""
    if k < 1 or pool_size < k:
        raise ValueError("Require 1 <= k <= pool_size")
    entries = dataset.get("jobs", []) if isinstance(dataset, dict) else dataset
    if not isinstance(entries, list) or not entries:
        raise ValueError("Dataset must contain a nonempty jobs list")
    reports = []
    for entry in entries:
        job = JobDescription.model_validate(entry["job"])
        candidates = [AnonymizedCandidate.model_validate(value) for value in entry["candidates"]]
        labels = {str(key): value for key, value in entry["labels"].items()}
        candidate_ids = [str(candidate.candidate_id) for candidate in candidates]
        if not candidates or len(set(candidate_ids)) != len(candidate_ids) or set(labels) != set(candidate_ids):
            raise ValueError("Each cohort needs unique candidates and exactly one label per candidate")
        evaluate_ranking(candidate_ids, labels, k, pool_size)  # Validate before inference.
        report = {"job_id": str(job.id), "candidate_count": len(candidates),
                  "relevant_count": sum(value > 0 for value in labels.values()), "pipelines": {}, "warnings": []}
        engine = HybridRankingEngine(embedding_fn, model_key=embedding_model)
        hybrid_rows = None
        for name, rank in (("baseline", PreRankingEngine(embedding_fn).rank), ("hybrid", engine.rank)):
            started = time.perf_counter()
            rows = rank(candidates, job)
            elapsed = (time.perf_counter() - started) * 1000
            ids = [str(row.candidate_id) for row in rows]
            report["pipelines"][name] = {**evaluate_ranking(ids, labels, k, pool_size), "duration_ms": round(elapsed, 3), "ranked_ids": ids}
            if name == "hybrid":
                hybrid_rows = rows
        if reranker is not None:
            started = time.perf_counter()
            try:
                rows = engine.rerank(deepcopy(hybrid_rows), job, reranker, pool_size)
                applied = any(row.reranked for row in rows)
            except Exception as exc:
                rows, applied = hybrid_rows, False
                report["warnings"].append(f"Reranker unavailable; retained hybrid ranking ({type(exc).__name__}).")
            elapsed = (time.perf_counter() - started) * 1000
            ids = [str(row.candidate_id) for row in rows]
            report["pipelines"]["reranked"] = {**evaluate_ranking(ids, labels, k, pool_size),
                "duration_ms": round(elapsed, 3), "total_duration_ms": round(elapsed + report["pipelines"]["hybrid"]["duration_ms"], 3),
                "applied": applied, "ranked_ids": ids}
        report["warnings"].extend(engine.diagnostics["warnings"])
        reports.append(report)
    names = reports[0]["pipelines"]
    macro = {name: {metric: sum(report["pipelines"][name][metric] for report in reports) / len(reports)
                    for metric in ("recall_at_pool", "precision_at_k", "ndcg_at_k", "duration_ms")} for name in names}
    return {"metadata": {"synthetic": synthetic, "purpose": "synthetic regression only" if synthetic else "offline labelled evaluation; quality requires independent held-out annotations",
            "split": dataset.get("split", "unspecified") if isinstance(dataset, dict) else "unspecified",
            "pipeline_version": VERSION, "embedding_model": embedding_model,
            "reranker_model": getattr(reranker, "model_name", None), "k": k, "pool_size": pool_size,
            "job_count": len(reports), "candidate_count": sum(report["candidate_count"] for report in reports),
            "timing_note": "Sequential baseline then hybrid; model/cache warmup can affect timings."},
            "macro_average": macro, "jobs": reports}


def smoke_embeddings(texts):
    """Deterministic hash vectors for plumbing checks, not semantic evaluation."""
    vectors = []
    for text in texts:
        vector = [0.] * 64
        for term in re.findall(r"[\w+#]+", text.casefold()):
            digest = hashlib.sha256(term.encode()).digest()
            vector[int.from_bytes(digest[:2], "big") % 64] += 1
        vectors.append(vector)
    return vectors


def smoke_dataset():
    jobs = []
    cases = [
        ("Python developer", "Python", [
            {"anonymized_work_experiences": [{"job_title": "Python developer", "skills_used": ["Python"], "duration_months": 48}]},
            {"anonymized_skills": ["Python"]}, {"anonymized_skills": ["Excel"]}, {}]),
        ("German support", "German language B2", [
            {"anonymized_languages": [{"language": "German", "proficiency": "C1"}]},
            {"anonymized_languages": [{"language": "German", "proficiency": "B2"}]},
            {"anonymized_languages": [{"language": "German", "proficiency": "A1"}]}, {}]),
        ("Computer science graduate", "Bachelor degree in Computer Science", [
            {"anonymized_education": [{"degree_title": "Master in Computer Science", "field_of_study": "Computer Science"}]},
            {"anonymized_education": [{"degree_title": "Bachelor in Computer Science", "field_of_study": "Computer Science"}]},
            {"anonymized_education": [{"degree_title": "Bachelor in Economics", "field_of_study": "Economics"}]}, {}]),
    ]
    for title, requirement, profiles in cases:
        candidates = [{"candidate_id": str(uuid5(NAMESPACE_URL, f"screening-smoke:{title}:{index}")), **profile} for index, profile in enumerate(profiles)]
        jobs.append({"job": {"id": str(uuid5(NAMESPACE_URL, f"screening-smoke:{title}")), "title": title,
                     "requirements": [{"id": "essential", "category": "must_have", "title": requirement, "description": requirement}]},
                     "candidates": candidates, "labels": {candidate["candidate_id"]: grade for candidate, grade in zip(candidates, [2, 1, 0, 0])}})
    return {"split": "synthetic_smoke", "jobs": jobs}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Explicit annotated JSON; no production data is loaded automatically")
    source.add_argument("--smoke", action="store_true", help="Synthetic 3-role plumbing check using offline hash vectors; NOT a quality benchmark")
    parser.add_argument("--rerank", action="store_true", help="Use configured CrossEncoder; default local-cache policy applies")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--pool-size", type=int, default=100)
    parser.add_argument("--output", type=Path, help="Write JSON report here; otherwise print JSON")
    args = parser.parse_args(argv)
    dataset = smoke_dataset() if args.smoke else json.loads(args.input.read_text(encoding="utf-8"))
    if args.smoke:
        embedding_fn, model = smoke_embeddings, "synthetic-hash-v1"
    else:
        from backend.services.vector_store import VectorStoreService
        service = VectorStoreService()
        embedding_fn, model = service.embedding_fn, service.model_name
    reranker, warning = None, None
    if args.rerank:
        try:
            from backend.services.screening_reranker import get_reranker
            reranker = get_reranker()
        except Exception as exc:
            warning = f"Reranker unavailable; hybrid only ({type(exc).__name__})."
            print(warning, file=sys.stderr)
    report = run_benchmark(dataset, embedding_fn, k=args.k, pool_size=args.pool_size,
                           reranker=reranker, synthetic=args.smoke, embedding_model=model)
    report["metadata"]["reranker_requested"] = args.rerank
    if warning:
        report["metadata"]["warning"] = warning
    payload = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
