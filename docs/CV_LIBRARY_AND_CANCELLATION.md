# CV library and process cancellation

Both workspaces now include a CV library. Imports store the original PDF, DOCX or TXT file without calling a parser, verification agent, matching agent or embedding service. Choose **Prepare selected for verification** to parse imported files; choose screening separately in CV verification.

The library supports search, pagination, selection across every page, an explicit select-all action, bulk and individual deletion, and restore. **Move to Trash** retains the CV for 30 days and excludes its profile from candidate lists and new screening. Permanent deletion requires confirmation in the interface and removes the original, profile, evaluations, interviews, vectors, cached evidence and candidate content in run traces. Completed deletions remain completed if a bulk operation is cancelled.

Trash cleanup runs every minute while the backend is running and before listing the library. Expired CVs cannot be restored. Stop active parsing or screening before changing CVs involved in those processes.

Exact duplicates are identified using SHA-256 followed by byte-for-byte comparison. Duplicate imports of active CVs are discarded; a repeat upload for parsing reuses the existing active profile. If the identical CV is in Trash, reupload permanently erases the trashed original and its linked profile/results, then stores the new upload under a fresh ID without reusing that old profile. CVs with different bytes are retained even when their filenames or contact details match. Pre-existing profiles without stored originals are listed and remain manageable, but their original byte identity cannot be reconstructed or compared safely.

The **Active processes** panel provides Cancel for uploads, extraction, parsing batches, screening, interviews, saving, model operations and longer reports. The panel remains available across navigation. Cancellation stops the server workflow and preserves completed steps. Synchronous model calls already running in a thread may finish; cancellation prevents the workflow from continuing after that call. Cancelled screening runs remain visible and can retry unfinished evaluations.

Process coordination follows the application's existing single-worker deployment. Multiple backend workers require a shared task queue/cancellation registry.

The new `cv_documents` table is created by the normal database initializer, with Alembic revision `e5211020` also provided. Restart the backend and frontend after updating. Existing CVs are not deleted as part of installing this change.


The recruiter sidebar keeps its collapse control beside the brand. **Reset workspace**, above the recruiter profile, cancels requests and background jobs belonging to this browser tab, clears drafts, selections, current results, timers and upload progress, and returns to Job descriptions with no role selected. Saved CVs, jobs and historical runs remain available; historical results are shown only when explicitly selected after a reset. Tab identity and upload progress use session storage. Reset does not stop another tab's work or sign the recruiter out.


## Live parsing batches

In CV library, select CVs and choose **CVs in this batch** (1-1000; default 25) and **Process simultaneously** (1-4). **Parse next** queues only that many unparsed originals, in selection order, skipping already prepared profiles. Remaining selections stay available for the next batch. Each batch loads at most 200 MB of originals.

The shared progress panel refreshes once per second and shows the current filenames and phase, per-file parsed/queued/failed status, parsed/failed/remaining counts, and the worker limit. Completed profiles and the library are refreshed after every saved CV, so CV verification receives new candidates while the rest of the batch continues. Imported files still never start parsing automatically, and parsing never starts job screening. Profiles can be browsed in CV verification before choosing a job; a job is required to start screening.

Per-file progress survives navigation and page reload through the tab's batch ID and persisted `batch_jobs.progress_json` (Alembic revision `f6211020`). Cancelled or interrupted batches retain completed profiles and mark unfinished files accordingly. The workspace reset clears the current tab's batch display and cancels its active batch.


### Parsing timers and averages

The shared live parsing panel shows a persisted batch elapsed timer in HH:MM:SS. It continues across navigation and freezes on completion, failure, cancellation, or interruption. Statistics records the average successful per-file parsing duration (including indexing and saving, excluding queue time and cached duplicate profiles). The 1/10/25/50/100 CV table explicitly labels sequential estimates based on this measured average; parallel wall-clock batch duration may be shorter. Timings persist in batch progress JSON and require no schema migration.
