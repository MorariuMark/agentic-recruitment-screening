# Recruiter workspace

Open the Next.js frontend and choose **User** for the recruiter workspace or **Admin** for the original interface. Both use the requested local demo password, `1234`. The workspace chooser uses an HTTP-only session cookie with a 12-hour lifetime. It is a demo sign-in, not a production identity or API authorization system.

## Shared engines and data

Both workspaces use the same database, configured providers, API keys, fallback chain, compatibility mode, local model configuration, and `DynamicLLMClient` factory. Changing the model in the recruiter sidebar updates the same runtime settings that Admin uses. There is no separate recruiter inference configuration.

The subtle control on the sidebar itself minimizes it to an icon rail. Model selection and the shared automatic failover switch remain available from its model popover. Active model operations show a small spinner without a timer; CV parsing, job extraction, ranking and interview generation show a spinner and elapsed time beside their action.

- Single CV uploads use the original `/api/v1/cv/upload` endpoint and `ParserAgent`.
- Cohort uploads use the same `ParserAgent`, enrichment, anonymization, vector indexing, and candidate repository, with up to four concurrent workers. Each worker owns its parser/client to isolate mutable inference state.
- Job text and URL imports use the original `JobParserAgent` methods. They return editable drafts without silently creating another job.
- Deep evaluation uses the original `MatchingAgent`, `ScoringEngine`, vector store and LLM factory. It keeps the original requirement scores, reasoning, confidence, citations and gap analysis.
- Recruiter decisions use the existing HITL repository operation and audit log. Interview generation calls the original interview workflow with the saved evaluation and job snapshot.

Every CV extraction field remains available in the structured profile, behind collapsible sections. Job metadata, including languages, additional sections and audit information, is stored losslessly in `job_description_data`; existing relational requirements remain authoritative. Older jobs continue to load from their existing fields.

## Recruiter workflow

1. **Job descriptions:** browse roles; import text or a posting URL; edit the role and its criteria; save.
2. **CV verification:** cohort upload is the default. The separate single-CV parser adds its result to the same cohort. Select candidates manually or select all search matches, choose the job and screening mode, then rank.
3. **Comparison matrix:** choose how many of the top candidates to compare. Completed deep evaluations are required for that subset. Review up to four columns at once, expand profiles and CV quotes on demand, and save an interview, hold or reject decision with notes.
4. **Interview:** only candidates explicitly approved by the recruiter appear. Generate a tailored question guide with a configurable duration. Plans and decisions survive navigation and reloads.

Visited workflow pages and job drafts stay mounted for the signed-in workspace session. Switching pages or jobs does not abort an in-flight request or discard its result, and its elapsed timer continues. The cohort screening panel scrolls normally, with the comparison count and comparison button in the same panel. Four candidate columns fit across the desktop comparison matrix without horizontal scrolling. Completed process durations remain beside their actions until the next action or the top-bar Reset timers control clears them. Candidate and role lists have bounded scroll areas with clear headers and footers.

## Fast batch ranking

Before ranking, exact extracted full-name duplicates (ignoring case and whitespace) keep the first selected copy; missing or placeholder names are never merged. The engine embeds the job and the remaining structured candidate profiles in one batch. A single normalized matrix product computes cosine similarities. No generative LLM evaluation runs during pre-ranking.

The composite pre-screen score uses similarity (40%), required skill evidence (30%), documented experience (20%) and degree evidence (10%). Components not requested by the job are omitted and remaining weights are normalized. Requirement weights apply within deterministic components. Language levels and degree hierarchy use the existing equivalence service. Documented dated work history merges overlapping periods; missing tenure is not invented. Scores never include contact information or the isolated demographic audit data.

The ranked list is available before deep evaluation finishes. Only the first `top_k` candidates receive the full existing semantic evaluation. Deep scores do not reorder the pre-screen list. Failures retain all pre-screen scores and show the affected candidate's error. A pre-screen score is an evidence signal, not an automatic hiring decision or external credential verification.

Limits: 1–1,000 unique candidates per ranking request; `top_k` from 1–100, capped by cohort size; 20 MB per CV and 200 MB total per cohort upload. The local application runs tracked work in-process. Interrupted ranking runs are marked retryable on restart; distributed workers and automatic resume are outside this implementation.

## API

All paths below are under `/api/v1`.

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/login`, `GET /auth/session`, `POST /auth/logout` | Demo workspace session |
| `GET /screening/models`, `POST /screening/models` | Read or change the shared active model without a hardware scan |
| `POST /screening/failover` | Update the same failover setting used by Admin; accepts `enabled` |
| `POST /screening/jobs/parse`, `POST /screening/jobs/parse-url` | Full job extraction into an editable draft |
| `POST /screening/cohort/upload` | Parse-only concurrent cohort upload; returns `batch_id` |
| `GET /cv/batch/{batch_id}` | Existing upload progress and per-file results |
| `POST /screening/rank` | Start ranking; accepts `job_id`, `candidate_ids`, `top_k`, `deep_evaluation` |
| `GET /screening/runs/{run_id}` | Complete ranked list and deep evaluation progress |
| `GET /screening/jobs/{job_id}/latest` | Restore the most recent run for a job |
| `POST /screening/runs/{run_id}/shortlist` | Persist top-N comparison shortlist; accepts `count` |
| `POST /screening/runs/{run_id}/decisions/{candidate_id}` | Persist human decision and audit notes |
| `POST /screening/runs/{run_id}/interview` | Enforce approval, call the original interview engine, persist plan |

Application startup creates the additional tables. Alembic revision `c93f1026` supplies the equivalent migration for migration-managed installations.

## Verification

`tests/test_fast_screening.py` covers matrix scoring, finite vectors, skill boundaries, language and degree checks, tenure, top-K limits, no-LLM pre-screening, partial failures, validation, persisted shortlists and HITL decisions, the interview gate, demo login, shared model settings, interrupted runs, bounded concurrent parsing, and complete CV/job extraction parity.

Run the backend regression suite with `.venv/Scripts/python.exe -m pytest`. Run the frontend checks from `frontend-next` with `npx tsc --noEmit`, `npx eslint src/components/recruiter src/app/page.tsx`, and `npm run build`.

Duplicate handling is scoped to each new screening run. After Top-K evaluation, identical complete semantic reports keep only the highest pre-ranked copy. Equality includes all scores, requirement reasoning, confidence, citations and gaps; identity, telemetry and recruiter review metadata are excluded. Matching aggregate scores alone do not merge candidates. The Top-K LLM-call limit remains unchanged; deduplication can leave fewer than K evaluated candidates. Excluded IDs and retained representatives are persisted in the run's `duplicates` list and omitted from the recruiter cohort view for that run. Original CVs and evaluation records remain available in Admin.

## Statistics

The top-right Statistics button opens a read-only dialog. Process timers show running and finished actions, cumulative and average durations, and the latest 200 timed actions in the current signed-in workspace session. Reloading or signing out starts a new timer history; Reset timers only clears durations beside action buttons. Running processes continue while the dialog is open or closed.

Data totals come from `/api/v1/screening/statistics`, using database aggregates rather than paginated frontend lists: stored CVs, roles, screening runs, deep evaluations, interview plans, anonymized CV text characters, cohort batch file counts and failures, plus recorded model calls, tokens, total and average model latency from the same live token tracker used by Admin. Model usage covers the current backend session (up to its latest 20,000 retained call records), not the lifetime database totals. Built-in synthetic analytics records are excluded from these model totals. Counts refresh every five seconds while the dialog is open. Characters are not file bytes; model-call latency and frontend end-to-end process duration measure different scopes.

See [Improved cohort screening](IMPROVED_SCREENING.md) for the optional version-2 hybrid evidence and local reranking pipeline, configuration, retry semantics and benchmark workflow.
