# Improved cohort screening

## Using the new mode

In CV verification, select **Improved hybrid rank (Top-K Deep Eval)**, choose candidates and Top-K, then rank. **Improved hybrid pre-screen only** performs the evidence funnel without generative LLM evaluations. Existing Fast Batch modes and requests remain version 1; version 2 is optional until recruiter-labelled benchmarks establish its quality.

Advanced options control whether the local cross-encoder runs and its pool size (1–200, expanded to at least Top-K). Top-K remains the full LLM evaluation budget. Names and identical-report deduplication retain the requested existing policy; original records are not deleted. Deduplication can leave fewer than K evaluated candidates.

## Execution

1. Snapshot the job, candidate content hashes, request configuration and selected shared model settings.
2. Prepare bounded anonymized evidence from work, projects, qualifications, languages, certifications and relevant additional sections. Evidence retains stable section references. At most 40 excerpts per profile and four 1,000-character excerpts per source section enter this funnel; full extracted profiles remain available.
3. Embed job criteria and missing evidence in batches of up to 128. Persist job-independent candidate evidence vectors in `screening_feature_cache`, keyed by evidence content, representation version and embedding model/cache version.
4. Retrieve evidence with BM25 and cosine similarity; reciprocal-rank fusion selects up to three passages per criterion. Deterministic checks distinguish supported, partial, contradicted and unknown. Semantic relevance alone cannot validate credentials or language proficiency. Missing information is not an automatic rejection. Soft skills are reserved for deep evaluation and recruiter review.
5. Aggregate positive requirement weights. Where both categories exist, essential criteria receive 80% and preferred criteria 20%; weights apply within each group. Evidence documented in work or qualifications receives more support than a skills-list mention. Overlapping dated experience is merged; undated roles are not summed over dated intervals.
6. Optionally rerank a bounded pool using requirement/evidence pairs. Scores remain on the model's native scale and do not replace the separate 0–100 pre-screen score. Reranking refines ordering within ten-point pre-screen bands, with explicit essential contradictions sorted after candidates without contradictions in the pool. Other candidates retain hybrid order. Pool inference is capped at 6,000 pairs; unavailable models, timeout or budget overflow retain hybrid order with a visible notice.
7. Use the existing MatchingAgent, vector retrieval, scoring engine and factory for Top-K. The version-2 run freezes its factory target chain and failover flag without changing Admin settings. Deep evaluation remains independent of the fast evidence shortlist.
8. Persist reports, progress, timings and diagnostics. Existing comparison/HITL and interview generation consume the retained evaluations.

The single-process runner bounds concurrent screening runs to two. Switching frontend pages does not cancel requests. Server interruption marks a run retryable rather than silently restarting expensive work. Retry retains completed evaluations, reuses the original job snapshot and rejects changed/missing candidate profiles. A retry uses current shared model settings and records the previous attempt configuration. Conditional writes reject stale earlier-attempt payloads. Multi-worker distributed execution is not supported by this local runner.

## API

`POST /api/v1/screening/rank` accepts the existing fields plus:

```json
{
  "pipeline_version": "v2",
  "rerank_enabled": true,
  "rerank_pool_size": 100,
  "evidence_per_requirement": 3
}
```

Defaults remain backward compatible (`pipeline_version: v1`). Improved screening requires 1–100 positive-weight criteria. Run rows add requirement assessments, evidence, coverage, initial rank, reranking status and score. Run metadata includes phase, snapshots, attempt, warnings, cache counters and stage timings. `POST /api/v1/screening/runs/{id}/retry` retries partial/failed versioned runs only. Recent run diagnostics also appear in Statistics.

Existing databases receive the additive cache table through normal `init_db` startup. Migration-managed deployments can use Alembic revision `d4171027` after `c93f1026`; do not run create-table migrations on a database already initialized with those same tables without aligning its migration stamp.

## Local model configuration

The existing sentence-transformers dependency supplies the cross-encoder. Defaults:

```dotenv
SCREENING_RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
SCREENING_RERANKER_LOCAL_ONLY=true
SCREENING_RERANKER_BATCH_SIZE=16
SCREENING_RERANKER_TIMEOUT_SECONDS=30
SCREENING_EMBEDDING_CACHE_VERSION=1
```

The default compact reranker is English-focused. A multilingual deployment should benchmark an appropriate multilingual model and configure its identifier or local path before promotion. No private candidate data is sent to a reranking service. Default operation loads cached local weights only, disables remote model code, serializes inference and bounds contention. Model initialization/prediction has a time limit; a timed-out background load may finish and warm the next run, but cannot change the current fallback results.

After replacing embedding weights under the same model name/path, increment `SCREENING_EMBEDDING_CACHE_VERSION`. Changing the model name or evidence representation version naturally invalidates cache entries. Invalid vectors are rebuilt, and cache write contention does not fail ranking.

## Benchmarks and rollout

Run the reproducible synthetic regression benchmark:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_screening.py --smoke --k 2 --pool-size 4 --output scratch/screening-benchmark-smoke.json
.\.venv\Scripts\python.exe scripts/benchmark_screening.py --smoke --rerank --k 2 --pool-size 4 --output scratch/screening-benchmark-reranked.json
```

For recruiter-labelled held-out data, use the input schema documented by `--help` and `--input PATH`. The tool reports recall at pool size, precision at K, graded nDCG at K, timings, model identity and ordered IDs for baseline/hybrid/optional reranking. Synthetic smoke results test mechanics, not hiring accuracy. Promotion requires a representative labelled dataset, measurement of missed suitable candidates, cold/warm hardware profiling and comparison of language groups. No learned weights or claimed accuracy improvement are derived from synthetic labels.
