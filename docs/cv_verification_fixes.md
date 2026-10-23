# CV verification evidence and storage repair

The supplied FastAPI run used an empty job description with one test requirement,
not a complete AI Engineer requisition. Its two completed evaluations awarded full
credit for tool mentions without establishing the required REST microservice context.
Five selected evaluations failed in vector retrieval before a provider call, and
three selected profiles lacked original CV text. The local reranker was unavailable.

## Changes

- Deep evaluation can use relevant original CV passages when semantic retrieval or
  indexing is unavailable. The underlying storage exception is logged, and the run
  records the source fallback. Missing original text still requires reparsing.
- Automatic Top-K selection skips profiles without original CV text, retaining them
  in the pre-screen list and explaining their unavailability in run diagnostics.
- Hybrid evidence policy `evidence-v2.4` distinguishes skill listings from work
  descriptions and checks explicit REST, microservice, production, and async context
  when requested. Earlier feature caches are invalidated by the policy version.
- Full deep scores require citations connecting the tool to required application
  context. Quotes existing in a CV alone do not prove that connection. Recruiter
  confirmations remain authoritative.
- Neither the agent nor the scoring engine rounds a met score of 0.8–0.9 to 1.0.
  Lenient settings do not promote partial evidence to complete proof.
- Sparse job criteria and missing job source produce warnings. Saved evaluations
  retain their audit history; the verification screen prompts reranking old runs.
- Vector storage uses configured paths and embedding models. Tests set isolated
  database and vector paths before application imports construct shared services.

## Local reranker setup

From the repository root:

```powershell
.venv\Scripts\python.exe scripts/cache_screening_reranker.py
```

This downloads the configured model explicitly and verifies local inference. The
script disables Hugging Face symlinks on Windows to support accounts without that
privilege. Routine screening still loads local files only.

## Historical test data

```powershell
.venv\Scripts\python.exe scripts/quarantine_screening_fixtures.py
.venv\Scripts\python.exe scripts/quarantine_screening_fixtures.py --apply
```

The first command is a dry run. Applying takes a full SQLite backup, moves only
profiles matching the repository's exact fixture signatures into the existing demo
category, and labels exact matches for the one-requirement AI Engineer test job.
It preserves original CV records, requirements, and historical evaluations. Repeated
application makes no further changes. The repair supports SQLite only.

Select or supply the intended job description before reranking the real cohort.
Missing criteria cannot be recovered from the empty test job or inferred from its title.

## Provider capacity and retries

Rate limits, timeouts and missing OpenRouter completion envelopes defer unfinished
evaluations instead of producing candidate findings. A run waits at most
`SCREENING_PROVIDER_WAIT_SECONDS` in total for short cooldowns (30 seconds by
default). Longer outages show a retryable provider-busy status. Provider-supplied
retry delays, including Gemini's structured quota-reset duration, are respected.

Successful requirement results are saved when an evaluation attempt is interrupted
by a provider failure. **Retry unfinished screening** reuses those results and
retains completed candidate evaluations. Source/profile snapshot checks still apply.
Dynamic Groq evaluation runs one requirement worker at a time to reduce quota bursts.
