# Runtime and screening policy audit — 20 October 2026

The three 19 October audits were checked against the existing, modified working tree. Several remedies were already implemented: language-based eligibility ordering in both ranking engines, automatic Top-K limited to documented mandatory languages, original-source citation checks, benchmark exclusion from ordinary recruiting, job/run query validation, scoped traces, and separate recruiter interview decisions. Existing work was preserved.

## Changes in this pass

- Groq criterion evaluations (`RequirementMatch`) reserve 700 output tokens. Larger parsing and interview schemas retain their existing budgets. Requests sharing a key are spaced by 350 ms; HTTP 429 adds a one-second delay for subsequent calls. This is burst smoothing, not a guarantee against a 1,000 OTPM quota; failover remains necessary.
- Removed the retired Nemotron endpoint from the automatic ladder, including when stale saved settings name it. No replacement model availability is assumed.
- Remote OpenAI-compatible clients disable SDK retries; request timeouts are at most 30 seconds (Groq 20, Gemini 15, NIM 25, Agnes/OpenRouter 30). A second JSON-mode compatibility call is allowed only for HTTP 400/422 errors mentioning the response format. Timeouts, rate limits, empty bodies, and invalid JSON advance to fallback.
- Empty structured responses raise an explicit error before JSON decoding. Empty text results are rejected by the dynamic fallback client before success telemetry.
- Scored requirement matches inherit their category from the job, overriding model-supplied categories. New results and exports now serialize the correct category.
- Mandatory criteria can carry a recruiter-defined `eligibility_evidence` source phrase. The job editor exposes this optional setting. A phrase such as `Available onsite in Bucharest` must occur in the candidate source before an automatic Top-K slot is awarded. It persists in the job's structured JSON, requires no migration, and is applied in both ranking engines. Unknown evidence is deferred, never treated as a rejection; manual deep evaluation remains available. Merely having worked in a city does not prove current on-site availability.
- Expanded benchmark input scrubbing to bracketed labels such as `[tier_1]`, alongside the existing `(STRONG Tier)` variants. Seed ground-truth tier/profile are stored only in raw database metadata (`benchmark_annotations`), and generated filenames no longer expose the tier. Original records remain available for audit; source hashes trigger vector reindexing when candidates are evaluated.
- Source verification uses the same NFKC/lowercase token normalization as frontend highlighting, retaining original offsets and distinguishing C, C++, and C#.
- The shared interview gate now requires a stored affirmative recruiter decision as well as reviewed status and a matching recommendation. A reviewed model recommendation alone does not approve progression. Both review routes propagate the explicit decision; database reconstruction restores it.
- Candidate API defaults to 100 records, caps requests at 500, rejects negative offsets, and uses a stable ID tie-breaker. The recruiter workspace requests 100-record pages with page controls, loading/error feedback, page-specific cache keys, and no retention of unused candidate pages. Search and cohort selection are explicitly scoped to the loaded library page.
- Background completion checks both the originating job and selected run before changing run selection; latest-run cache aliases are revalidated against the server. Background workspace navigation now checks the originating job before changing the visible workflow step. Existing job/run validation and cache scoping remain in place.

## Operational scope

Historical evaluations and audit records were not rewritten. New screening runs are required to obtain corrected categories and current eligibility policy. Local presence gates need recruiter wording that matches an explicit availability statement; they are not inferred from demographic data. The API response remains an array for client compatibility. Offset pagination uses an extra empty page when the final page is exactly full; it does not promise a transaction snapshot during concurrent uploads.

No paid provider calls, cohort regeneration, deployment, or live 15-minute screening run was performed. The supplied 77/187 failure count was treated as reported trace evidence, not independently remeasured. Provider latency and error-rate improvement still need measurement in a subsequent live run.

## Validation

- Combined backend suite: 149 passed before the final seed-metadata addition; 32 schema, seed-metadata, evidence, and persistence tests also passed after that addition.
- Frontend Node tests: 14 passed, including source normalization/offset fixtures.
- TypeScript: `tsc --noEmit` passed.
- Tests used the isolated pytest SQLite database. Windows event-loop socket creation required running the backend suite outside the filesystem sandbox.
