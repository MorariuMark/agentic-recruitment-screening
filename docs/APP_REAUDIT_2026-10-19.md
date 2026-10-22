# Application re-audit — screening trace and UI regressions

Date: 19 October 2026. Scope: current working tree after the first audit's remediation work, saved screening data, synthetic engine reproductions, and the running recruiter UI. Application code and working recruitment data were not changed. Source hashes were captured at the beginning and checked at the end: no inspected source files changed during this audit.

## Assessment

Several earlier fixes are present, but the pipeline still has inconsistent definitions of evidence, eligibility, and human approval. New UI state handling can associate one job's results with another job's heading. The action trace is not sufficiently reliable to diagnose all of this by itself.

The highest priorities are to establish one evidence contract, define job-level mandatory-criterion policy, bind every screen and operation to a job/run pair, and repair trace attribution before using its results to judge engine quality.

## What was independently verified from the supplied analysis

The latest saved German-support run is `e72f097a-9869-4371-bcaa-6a336847e507`. It used v1, ranked 401 records, and completed ten deep evaluations. All ten recommendations were `reject`. Eight of those ten profiles contain no documented German. Rank 19 has documented German C1 and English C1 and received no deep evaluation. This confirms a selection problem; the absence of German from a CV does not prove the person cannot speak it.

The first candidate's English match is saved as `clarification_needed`, score 0.5, with the quotation `English (Native)` marked unverified. Its reasoning says the candidate is a native English speaker. The same candidate's German result has one invalid formatted quotation and one valid source quotation, and receives only 0.75 credit.

There are 1,082 candidate records. **600 contain explicit synthetic tier labels in their anonymized profiles**, as well as in the raw profiles. The seed generator deliberately writes these labels into project names.

The export's `matches`/`requirement_matches` error is still present. The proposed one-line correction is incomplete: the loop also indexes `deep_eval["matches"]`, and the fallback branch uses `json.dumps` without importing `json` in that module.

**Two recommended fixes in the supplied analysis need qualification:** switching to v2 does not enforce mandatory-language eligibility, and broad punctuation normalization or trusting arbitrary parsed blocks would not establish source provenance. Both require deeper contract changes described below.

## Prioritized engine findings

### R1 — Neither ranking mode enforces the intended mandatory-criterion selection policy

**P1. Saved-data confirmation, source inspection, and synthetic reproduction.**

V1 combines similarity and criterion buckets into one number. Strong generic support similarity can compensate for an undocumented required language. Its “40/30/20/10” weights are redistributed when experience or education criteria are absent; similarity therefore has more than 40% effective weight in this job.

V2 also averages criterion scores and selects the first Top-K. It records `essential_unknown`, but does not use it as an eligibility boundary. Its reranker distinguishes explicit contradictions from other cases inside its pool; that still does not prioritize documented language support over unknown language evidence.

A controlled synthetic v2 example with required German B2 and three support criteria ranked the candidate with no documented German first at 75, ahead of a German C1 candidate at 40. This uses injected embeddings to test ordering policy, not real-model ranking quality.

**Correction:** introduce an explicit, recruiter-reviewed policy for criteria that must be verified before consuming the main Top-K budget. Keep eligible, needs-clarification, and explicitly contradicted evidence distinguishable. Rank within those groups and make any clarification budget visible. Do not silently reject candidates because evidence is missing, and do not treat every logistical or soft-skill must-have as a deterministic exclusion rule.

Sources: [v1 aggregation](<D:/Atos - Screening AI Agent Project/backend/services/pre_ranking.py:106>), [v2 sorting](<D:/Atos - Screening AI Agent Project/backend/services/hybrid_screening.py:205>), [Top-K selection](<D:/Atos - Screening AI Agent Project/backend/api/recruiter.py:249>).

### R2 — V2 gives known language proficiency zero credit when the job omits a level

**P1. Reproduced.**

The actual job says German proficiency is required but specifies no CEFR threshold. `language_assessment` requires both a candidate level and an extractable required level. A German C1 candidate returns `unknown, 0` for this exact wording. A candidate without German also returns unknown/zero. V1 uses an invented default of B1, so the modes disagree about the same job.

**Correction:** represent “language documented” separately from “minimum proficiency satisfied.” Request job clarification when the threshold is genuinely necessary. Never convert an unspecified job threshold into missing candidate proficiency or silently invent a CEFR threshold. Share language parsing and policy between pre-screening and deep evaluation.

Sources: [v2 language assessment](<D:/Atos - Screening AI Agent Project/backend/services/hybrid_screening.py:46>), [legacy language policy](<D:/Atos - Screening AI Agent Project/backend/services/skill_equivalence.py:456>).

### R3 — Retrieval and citation verification use different source representations

**P1. Reproduced and observed in saved results.**

The vector store constructs strings such as `Candidate Languages & Communication: English (Native)` and adds explanatory boilerplate. Matching explicitly tells the LLM to quote those chunks verbatim. Scoring verifies the quotation only against `candidate.sanitized_text`, where that generated sentence may never have existed.

The engine consequently penalizes a quotation that follows its own prompt. A synthetic source containing `German C1` gave 50/100 and clarification-needed when cited as `German (C1)`.

**Correction:** give evidence a stable source ID, field path, original span, and permitted display form. Use deterministic structured language checks backed by source evidence. Render generated headings separately from quotable source text. Normalize harmless extraction differences consistently, with offsets back to the original. Do not certify a parsed claim as a raw quotation merely because it appears in parser output.

Sources: [generated language chunk](<D:/Atos - Screening AI Agent Project/backend/services/vector_store.py:164>), [matching prompt](<D:/Atos - Screening AI Agent Project/backend/agents/matching_agent.py:237>), [verification](<D:/Atos - Screening AI Agent Project/backend/services/scoring_engine.py:109>).

### R4 — Omitting citations bypasses the new grounding safeguard

**P1. Reproduced.**

The downgrade executes only inside `if match.citations`. A positive match without citations still receives 100/100 and `strong_match`; adding a formatted but unverifiable citation reduces the same positive claim to 50/100. This rewards weaker evidence and makes the fix internally inconsistent.

**Correction:** require appropriate support for positive findings, whether supplied as a quotation or a source-backed deterministic fact. Missing evidence must not bypass checks. Distinguish evidence availability from the validity rate of quotations that happen to be present.

Source: [scoring_engine.py](<D:/Atos - Screening AI Agent Project/backend/services/scoring_engine.py:121>).

### R5 — Retrieval still supplies unrelated evidence and hides storage failures

**P1. Source inspection; storage-failure path reproduced.**

Deep evaluation retrieves the nearest N chunks without a relevance threshold or criterion-specific section restrictions. Miscellaneous information and explicitly out-of-scope custom sections are indexed. The reported queueing-theory/ticketing collision is consistent with this design, though its exact historical retrieval response was not independently recovered.

More seriously, if both vector queries raise an exception, the service returns an empty list. A storage outage then looks like a candidate with no supporting evidence. Provider errors now propagate, but retrieval errors can still lead to negative candidate findings.

**Correction:** propagate retrieval failures as unavailable evaluation. Use section-aware retrieval and evidence sufficiency checks, allowing a valid empty retrieval result. Evaluate retrieval quality on labeled ticket-management, language, and long-CV cases; do not assume nearest means relevant.

Sources: [indexing miscellaneous content](<D:/Atos - Screening AI Agent Project/backend/services/vector_store.py:193>), [query error handling](<D:/Atos - Screening AI Agent Project/backend/services/vector_store.py:341>).

### R6 — Benchmark target labels are model inputs in the ordinary candidate library

**P1. Confirmed in database and generator.**

600 anonymized profiles include STRONG/BORDERLINE/REJECT tier labels in project names. The same global candidate collection is used for normal screening. These labels can affect both embeddings and LLM reasoning. The audit did not measure how much they influenced this particular rejection outcome.

**Correction:** isolate demonstration and benchmark data from ordinary recruiting data. Keep ground-truth labels in benchmark annotations, outside all model-visible fields, filenames used as evidence, and retrieval text. For affected fixtures, rebuild derived profiles, embeddings, and evidence caches from clean inputs before benchmarking again. Preserve original audit records and identify superseded results rather than silently rewriting history.

Source: [seed generator](<D:/Atos - Screening AI Agent Project/scripts/generate_and_seed_cohort.py:274>).

### R7 — The trace exporter omits historical requirement actions and mixes sessions

**P1 for diagnostic correctness. Source inspection.**

There are four separate faults:

1. The fallback guard checks `matches`, while saved results use `requirement_matches`.
2. The loop also reads `deep_eval["matches"]`; correcting only the guard is insufficient.
3. That branch calls `json.dumps`, but `json` is not imported. Restoring the branch without fixing this exposes another failure.
4. The exporter takes the last 300 global actions without filtering by job or run. Its duplicate key does not include run/attempt identity. A trace can therefore contain unrelated work or suppress a later attempt's action.

The action buffer is process memory with a 500-entry cap. It does not support an assertion of complete historical raw prompts/responses after restart or across workers. Reconstructed entries also use the export time when no original timestamp exists.

**Correction:** version the trace schema; use one result-field accessor for guard and iteration; persist run/attempt/job/candidate/criterion IDs with each action. Filter before export. Distinguish actual captured actions from reconstructed evaluation summaries, and do not fabricate historical timestamps or raw-output provenance.

Source: [recruiter.py](<D:/Atos - Screening AI Agent Project/backend/api/recruiter.py:601>).

### R8 — Concurrent requirement calls can be logged under the wrong requirement

**P1 for diagnostic correctness. Reproduced.**

One `DynamicLLMClient` is shared by up to four requirement threads. Its action and metadata are mutable instance fields. A synchronized two-thread reproduction recorded both requirement A and requirement B under metadata `requirement_id: B`.

**Correction:** pass execution context explicitly with each call, or use correctly propagated request/task-local state. Snapshot context before dispatch; do not read shared mutable metadata when a call completes. Apply the same isolation to raw response and token-usage capture.

Sources: [shared requirement execution](<D:/Atos - Screening AI Agent Project/backend/agents/matching_agent.py:542>), [mutable context](<D:/Atos - Screening AI Agent Project/backend/agents/llm_factory.py:1748>).

### R9 — Authentication helpers exist but are not connected to application endpoints

**P1 before shared use. Reproduced.**

Neither router nor application mounting applies the new authentication/role dependencies. With strict authentication enabled and demo mode disabled in an isolated test process, an unauthenticated candidate-list request still returned HTTP 200. Token/login tests do not exercise protected resource access.

**Correction:** apply API dependencies to the protected routes and explicit admin operations. Test candidate access, exports, deletion, model configuration, and trace access without a token and with the wrong role. Sensitive full traces need the same protection as their underlying candidate records.

Sources: [router mounting](<D:/Atos - Screening AI Agent Project/backend/main.py:140>), [auth dependencies](<D:/Atos - Screening AI Agent Project/backend/api/auth.py:77>).

### R10 — A validated rejection is treated as interview approval

**P1. Reproduced at the shared service boundary.**

The new shared approval helper checks only `hitl_validated`. A reviewed evaluation with recommendation `reject` returns `(is_draft=False, hitl_approved=True)`, even when approval is explicitly required. The recruiter-specific endpoint adds a decision check, but other consumers of the shared service remain inconsistent.

**Correction:** distinguish reviewed from approved-for-interview. Require an explicit progression decision matching the candidate, job, evaluation, and current decision version. A hold or rejection must never satisfy that predicate.

Source: [interview_service.py](<D:/Atos - Screening AI Agent Project/backend/services/interview_service.py:50>).

### R11 — An all-inactive job can still be labeled a strong match

**P2. Reproduced.**

A job with only zero-weight requirements and no evaluated matches yields 0/100 and `strong_match`. The low-score rejection branch requires a gap, and the borderline branch excludes scores below the rejection threshold. The final fallback therefore labels this unusable assessment strong.

**Correction:** reject screening when no active criteria remain and make the recommendation decision matrix exhaustive. Validate status/score consistency as well as coverage.

Source: [scoring_engine.py](<D:/Atos - Screening AI Agent Project/backend/services/scoring_engine.py:238>).

## UI and workflow regressions

### U1 — A job heading can display another job's results

**P1. Browser reproduced.**

Opening the application with the French Java job ID and the German-support run ID displayed “Hiring for Java Developer with French” alongside the German run's 401 ranked candidates and its scores. The UI fetches a run by ID without validating its job. The same mismatch can arise when an operation started in a now-hidden job finishes: `updateRun` globally replaces the active run ID without checking the currently selected job.

**Correction:** bind run selection and every callback to a validated job/run pair. Ignore or retain in the originating workspace results that complete after navigation. Reject mismatched job/run requests in job-scoped API operations and trace exports as well. Never enable decision actions against an unvalidated combination.

Sources: [run lookup](<D:/Atos - Screening AI Agent Project/frontend-next/src/components/recruiter/workspace.tsx:103>), [global update callback](<D:/Atos - Screening AI Agent Project/frontend-next/src/components/recruiter/workspace.tsx:123>).

### U2 — The required next action is hidden under advanced settings

**P2. Browser reproduced.**

After ten completed deep evaluations, opening Comparison shows “Build your comparison shortlist” and sends the user back. The action needed to create it is inside the collapsed “Advanced options, reranker & shortlist compare” disclosure. Ordinary progression is presented as a technical setting.

**Correction:** show a primary “Review evaluated candidates” or “Create comparison shortlist” action when screening finishes. Keep reranker options separate. Explain when the run is pre-screen-only and offer a direct action to evaluate a selected shortlist. Keep a way to inspect lower-ranked candidates without replacing the entire run.

Source: [verification.tsx](<D:/Atos - Screening AI Agent Project/frontend-next/src/components/recruiter/verification.tsx:114>).

### U3 — Two screening buttons enforce different validation

**P2. Browser reproduced without submitting screening.**

After selecting one candidate and setting Deep top to zero, the main ranking button was disabled while the quick “Screen 1” button remained enabled. The latter calls the same unguarded handler. It can submit invalid Top-K/reranker values and produce avoidable API errors.

**Correction:** share a single eligibility predicate and validate again inside the shared action handler. Both entry points need identical pending/error behavior.

Source: [quick action](<D:/Atos - Screening AI Agent Project/frontend-next/src/components/recruiter/verification.tsx:125>).

### U4 — Controls reset to legacy settings independently of the displayed run

**P2. Source confirmed.**

Mode always initializes to legacy-deep and Top-K to ten, even when a saved hybrid run or a different Top-K is displayed. Controls do not clearly distinguish historical run configuration from options for a new run. Users can believe they are repeating improved screening while submitting legacy screening.

**Correction:** display the selected run's immutable configuration separately, and explicitly initialize or label “New screening” settings. Make the supported recommended workflow the default only after its policy is corrected and benchmarked.

Source: [verification.tsx](<D:/Atos - Screening AI Agent Project/frontend-next/src/components/recruiter/verification.tsx:17>).

### U5 — Citation highlighting has a different normalizer and a loading race

**P2. Source confirmed.**

Backend verification collapses whitespace, but highlighting uses an exact case-insensitive substring. A quote can be marked verified while no text is highlighted across line breaks. Also, the initial-quote effect can run before profile data renders the source section; it does not rerun when that section becomes available. This makes quote navigation depend on whether the profile was already cached.

**Correction:** share a source-span mapping with verification and trigger navigation after the source has rendered. Show a clear “source passage not located” state rather than silently displaying an unhighlighted document.

Source: [profile.tsx](<D:/Atos - Screening AI Agent Project/frontend-next/src/components/recruiter/profile.tsx:20>).

## Further cleanup and integration concerns

- Duplicate evaluation-based exclusion has been removed from the execution path, but duplicate identity still falls back to name-only when contact information is absent. The precomputed document hash is not preferred in that case. Existing UI copy still says identical evaluations are excluded. Review collision behavior before describing deduplication as fixed. [Source](<D:/Atos - Screening AI Agent Project/backend/services/screening_duplicates.py:50>).
- Candidate reach improved: the browser now shows all 1,082 records. Raising the download limit to 10,000 is not server pagination, however. It retains a future cap and increases browser/filtering cost. The rank API accepts 50,000 IDs, which the ordinary list cannot fully select.
- Review and interview state is held in multiple local copies and several query-key shapes. Interview generation writes a two-part run cache key while displayed runs use a three-part key. Standardize run identity/cache updates and account for external changes without discarding unsaved drafts.
- The read path still retroactively normalizes some saved requirement statuses without recomputing every dependent score/recommendation. Historical results should be immutable or explicitly migrated/versioned.
- Partial screening can block comparison because shortlisting requires the first N rows all to have completed evaluations. A failed first row prevents selecting completed lower rows through this endpoint. Support explicit reviewed candidate IDs and explain incomplete evidence.

## Verification

The selected regression run completed with **181 passed, 1 failed, 0 skipped** across 182 tests. It covered scoring, PII, contracts, skill equivalence, hybrid screening, reranker adapters, synthetic benchmark metrics, recruiter funnel, database behavior, parser edge cases, job parsing, events, authentication helpers, phase-two/three audit checks, persistence/approval checks, and URL safety.

The failure is `test_durable_save_failure_raises_500_and_does_not_cache_dirty_evaluation`. It patches database saving but leaves matching connected to the real dynamic provider path. In the isolated offline environment it fails before reaching the intended persistence failure. The test must mock matching and vector access; its present result does not prove or disprove the durable-save safeguard. The diagnostic timer also emitted a stack dump during slow scientific-library imports; the test process subsequently completed.

TypeScript passed with `tsc --noEmit --incremental false`.

Additional synthetic checks reproduced: unspecified-language threshold handling; missing-versus-formatted citation scoring; all-inactive strong-match behavior; swallowed retrieval failures; concurrent trace metadata contamination; v2 aggregate ordering without mandatory-language eligibility; strict-auth API access without a token; and rejected-but-reviewed interview approval.

Browser checks reproduced: mismatched job/run display, hidden comparison progression, inconsistent quick-action validation, and current full-cohort reach. No ranking, approval, rejection, interview generation, model changes, or working-data deletion was submitted during UI testing. Existing user services were not stopped.

No live provider ranking benchmark or real candidate outcome assessment was run. Saved records and source findings establish the defects above; they do not establish that any named candidate should be hired or rejected.

## Recommended correction order

1. Define canonical evidence and mandatory-criterion policy; unify language handling, citation verification, and retrieval failure semantics.
2. Fix job/run binding, enforce API authorization, and correct the reviewed-versus-approved predicate.
3. Repair and persist trace attribution before using operational logs as the principal regression oracle.
4. Rebuild clean benchmark inputs and derived indexes in a separate benchmark workspace; measure Top-K recall of documented mandatory skills and irrelevant-evidence rates.
5. Restore a visible recruiter progression: select job and cohort → screen → inspect evidence and uncertainties → create comparison → record explicit human decisions → prepare interviews.
6. Standardize action validation, run cache identity, source highlighting, and deterministic integration tests. Retest complete flows after each small correction rather than introducing another broad remediation patch.
