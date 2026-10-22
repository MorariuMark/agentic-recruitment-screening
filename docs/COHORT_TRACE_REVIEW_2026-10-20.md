# Cohort failure investigation — 20 October 2026

Reviewed the supplied JSON trace (exported at 11:44 UTC) and read the latest local parsing batch records without changing recruitment data.

## What actually failed

The attached screening run ranked 100 candidates, completed all 10 requested deep evaluations, and left 90 as pre-screen only. Nine recommendations were reject and one borderline. These are screening outcomes, not failed CV parses.

Separately, the latest parsing batches show:

| Files attempted | Completed | Failed |
| --- | --- | --- |
| 75 | 28 | 47 |
| 25 | 3 | 22 |

These batches overlap: 69 failed attempts involved 47 distinct documents. Three later succeeded, leaving **44 unparsed documents**. All 44 originals remain stored and available in the CV library. No automatic resubmission or paid/live provider calls were performed during this investigation.

68 failed attempts have the same signature: `All LLM models in fallback chain failed for schema ParsedCV. Attempted: . Last error: None`. Every target was in cooldown, so no new provider request was sent for those attempts. A temporary platform outage was incorrectly recorded as a sequence of bad CV files.

## Causes and fixes

1. **The earlier output cap covered evaluations, not parsing.** Groq still reserved 4,096 output tokens for `ParsedCV`, exceeding the observed free-tier output allowance. `GROQ_MAX_OUTPUT_TOKENS` now defaults to 800 for all structured schemas; requirement evaluations remain capped at 700. The limit is configurable for accounts with larger allowances. Token-limit-truncated responses are rejected and advance to fallback; partial JSON is not accepted as a complete parse.
2. **All-cooldown was indistinguishable from document failure.** The factory now raises a retryable, explicitly worded provider-unavailable error with the earliest recovery delay. It no longer emits an empty attempt list and `Last error: None` when no target was called.
3. **The batch drained its queue during an outage.** Parsing retries the same file after a bounded asynchronous wait, without holding the global parser slot. `PARSER_PROVIDER_WAIT_SECONDS` defaults to 90. If recovery cannot fit that budget, the batch is preserved as interrupted, finished profiles remain, and unprocessed files are not counted as failed. Their originals are saved before the first provider request so an unstarted queue can be recovered through the library. Legacy batch parsing also preserves originals and interrupts safely on global provider unavailability.
4. **Rate-limit retries shortened CV input unnecessarily.** A 429 no longer triggers a second parse with only 5,000 CV characters. Reduced input windows are reserved for actual context-length/413 errors. Provider cooldown exceptions propagate to the batch coordinator.
5. **Queued Groq workers could still hit an exhausted key.** Cooldown is registered immediately on 429 and checked again after pacing, before dispatch. Numeric Retry-After headers and stated retry delays are respected. A skipped queued call does not extend cooldown or get logged as another failed provider request. Dynamic Gemini clients now also leave key rotation to the outer fallback ladder, avoiding duplicate internal secondary-key retries.
6. **Unavailable source and logistical uncertainty could become misleading negatives.** Deep evaluation now refuses profiles with no original sanitized source text before calling the LLM or scoring. Ranking emits a warning for such profiles. Location/onsite presence is logistical, with an explicit confirmation question rather than an objective disqualification. Historical onsite support experience remains an objective skill.
7. **UI and statistics conflated outcomes.** The cohort explains pre-screen-only versus completed recommendations versus unavailable evaluation. Temporary parsing attempts appear as deferred timing actions, excluded from failure counts and success-rate denominators.

## Screening trace findings

The export declares 182 captured actions plus five reconstructed summaries and incomplete history. Among recorded provider attempts there are 77 errors: 67 rate limits, seven timeouts, two retired-endpoint 404s, and one JSON decoding error. The run took about 14m 57s. The longest recorded call was an OpenRouter/free success at about 440 seconds; the timeouts were Gemini/NIM, so these are separate latency problems.

The source already contained earlier fixes for remote request timeouts, disabled SDK retries, empty-response failover and retired-endpoint removal. The saved run uses the older `mandatory-language-v1` policy and still records the retired NIM target; its historical results do not establish whether newly loaded code is active. Restart the backend and create/retry work to exercise the current implementation.

No exported parsed profile mentions ServiceNow. None of the 85 available original sanitized CV texts mentions ServiceNow either; 15 records have no source text. Therefore low fit for a ServiceNow AI product role is plausible, and no scoring thresholds were weakened to manufacture positive matches. Location certainty and source availability still require the corrections above. Existing scores, trace history and failed-batch counts have not been rewritten.

## Recovery

Restart the backend, reload the app, and select the remaining unparsed CVs in the library to prepare them again. Existing completed profiles are reused. A single parsing worker and smaller batches are useful initially on the observed free-tier quotas. If all providers remain unavailable, the new behavior interrupts safely instead of failing the remaining files. Actual live throughput still depends on provider capacity.

## Validation

Offline regressions cover capped full-CV requests, truncation rejection, Retry-After parsing, cooldown skips, same-file retry, safe batch interruption, retention of all original files, deferred timing, missing-source refusal, onsite clarification and unchanged objective skill handling. Existing parsing, cancellation, ranking, scoring, authentication, interview and timing tests were also run. The Webpack production build and 14 frontend Node tests passed.
