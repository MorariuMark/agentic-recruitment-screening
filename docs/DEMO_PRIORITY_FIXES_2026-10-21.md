# Demo priority fixes — 21 October 2026

The first three issues in the demo priority list have been addressed.

## Reranking

- Declared and validated the missing prediction timeout (`SCREENING_RERANKER_TIMEOUT_SECONDS`, default 30 seconds).
- Added a separate cold-load budget (`SCREENING_RERANKER_LOAD_TIMEOUT_SECONDS`, default 180 seconds).
- Added background startup prewarming through the same serialized executor used for ranking. The API remains available during loading; startup logs `Local screening reranker is ready.` when finished.
- Retained the existing hybrid fallback and isolation of partially modified rows when prediction fails or times out.
- Verified the laptop's cached cross-encoder offline on synthetic evidence: relevant Python experience scored above unrelated catering text. The cold load plus prediction took 120.26 seconds during the first verification, which motivated prewarming and the separate load budget. No model download was needed.

## Local-model controls

Status, service start, load, unload, pull, and GGUF import now run their synchronous operations in worker threads. Their routes and response contracts remain the same. Tests keep each operation blocked while making an independent API request, proving that the API event loop remains responsive.

## Human corrections and scores

- Score preview and final sign-off now use the same backend scoring engine. Removed the duplicate frontend weighting/recommendation calculation.
- Recalculate weighted overall/category scores, gaps, clarifications, and citation coverage.
- Preserve explicit human-confirmed scores/statuses even when confirmation came from a call rather than the CV. Citation verification still reports only evidence actually present in the source.
- Validate complete, unique criterion coverage before persisting edits. Unknown, duplicate, missing, or empty active criterion lists return a validation error.
- Save corrected scores, matches, approval, and the audit event in one transaction. A failed commit leaves the previous database result and cache intact.
- Persist the evaluation's original job criteria, strictness, and clarification count in a new nullable `scoring_context_json` column. Fresh evaluations remain consistent after job edits or a backend restart. Older evaluations without this context use the currently saved job, because their original weights were not recorded.
- Added Alembic revision `h8211021`; local startup also recognizes the nullable column through the existing schema reconciliation. Migration tests preserve existing evaluation rows and cover an already-reconciled column. No data reset is required.
- Disable clarification/sign-off actions during recalculation and ignore preview responses if the user switched to a different case.

## Validation

- Final full backend run: **354 passed, 1 failed**, in 98.41 seconds.
- The one failure is the pre-existing `test_location_not_confused_with_language_hierarchy` assertion: it expects `not_met` for unknown location/work authorization while the current policy returns `clarification_needed`. It is the same failure observed before these changes; that unrelated policy/test was not modified.
- **18 new backend regression checks** cover positive reranking, timeout fallback, configurable timeout validation, six model-control routes, preview/save consistency, criterion validation, transaction rollback, reloads, legacy context fallback, inactive clarifications, and migration preservation.
- Frontend utility tests: **16 passed**, including two new preview API contract/error checks.
- Standalone TypeScript check: **passed**.
- Production frontend build: **passed**, including TypeScript and static page generation. An initial attempt failed to fetch Google Fonts; the retry completed successfully.
- Actual cached reranker offline inference: **passed**.
- Diff whitespace check on the touched application files: **passed**. The repository's existing broader lint backlog remains separate from these fixes.

Backend execution used an isolated scratch working directory and test database/vector paths, required asyncio/anyio pytest plugins, and offline model settings. Model-control regressions use simulated slow operations; no actual local model was pulled, unloaded, or replaced during tests.

Before presenting, restart the backend so the new schema/settings are loaded and background reranker prewarming can complete. For the strongest repeatability, run a fresh evaluation of the presentation cases after restarting; it records the new scoring context.

Backend test output: [demo-fixes-2026-10-21-tests.txt](./demo-fixes-2026-10-21-tests.txt).
