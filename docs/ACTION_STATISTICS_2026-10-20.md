# Persistent action statistics

The recruiter Statistics dialog now provides saved performance KPIs and paginated action history. These measurements are independent of browser timers and remain after closing a tab, resetting the workspace view, or restarting the backend.

## What is recorded

- CV parsing: one entry per file for single uploads and batch preparation. Includes parsing/anonymization, indexing, and profile persistence. Reused profiles are recorded as reused and excluded from parsing averages.
- CV batches: one elapsed-time entry per batch, with submitted/successful/failed counts. Parallel CV durations remain individual measurements, not an estimate of the batch duration.
- Job screening: one entry per run attempt, plus ranking and individual deep-evaluation entries. Retries remain separate entries and count only the unfinished candidates processed in that attempt.
- Legacy combined CV parsing and job screening is categorized separately so its additional evaluation time cannot inflate pure parsing averages.
- Job description extraction (text/URL, recruiter/admin), interview generation, candidate comparison, library import, shortlist creation, and recruiter decisions are also recorded.

Each entry has an ID, action, status, label, UTC start/finish timestamps, measured milliseconds, item counts, and applicable job/run/batch/candidate/parent IDs. Durations use a monotonic clock. Batch and run measurements include their worker queue waits; per-file batch processing starts after a worker is admitted. Database journal writes themselves are excluded from the individual action's own measured duration.

## KPIs and filters

The dashboard shows successful-action average, fastest and slowest durations, total successful elapsed time, completed item volume, items/minute, success rate, failures, cancellations, reused profiles and active/interrupted counts.

Average and throughput calculations exclude failed, partial, cancelled, interrupted, running and reused actions. Temporary provider cooldown attempts are saved as deferred and excluded from terminal-attempt counts. Success rate is completed actions / terminal attempts; reused successful actions count as successful attempts. Throughput is completed items / sum of successful elapsed durations, converted to items/minute. Parent/child measurements overlap and must not be added together as overall system time. A screening-run item represents a ranked candidate; a candidate-evaluation item represents a deep evaluation.

Filters support all time, 24 hours, 7/30/90 days, action type and job. Batch/run drill-down filters show the corresponding file or candidate measurements. Action history is fetched in 25-row pages; KPIs cover the entire filtered history, not just that page. Export this page downloads those displayed records with millisecond durations and identifiers in CSV format.

Historical parsing averages from existing batch timestamps remain displayed separately. New journal records start when this version is enabled; missing historical timestamps are never fabricated. An interrupted action recovered on restart keeps its duration unknown instead of receiving a guessed finish time.

## Storage and startup

`operation_timings` is an independent database table, with an Alembic migration (`g7211020`) for managed migrations. The application's existing local database initialization also creates it on backend startup. Restart the backend after updating; reload the frontend to load the new dialog. Existing candidate/job records are unchanged.

Action history inherits the authenticated recruiter's access requirements. No prompts, CV body text, credentials or raw model responses are copied into the timing table. Filenames and action identifiers are retained for traceability. Recording failures are logged without changing recruitment outcomes.

## Validation

- Backend integration suite: 102 passed, covering parsing, batches, cancellation, screening, evidence and approval.
- Follow-up screening, timing, job-extraction and authentication suite: 79 passed, including retry item counts.
- Frontend: full Webpack production build, TypeScript check and all 14 Node tests passed.
- New timing tests verify persistence, milliseconds, parent/child identity, parallel work, failure/cancellation outcomes, aggregation exclusions, filtered pagination, access control, and restart handling.
