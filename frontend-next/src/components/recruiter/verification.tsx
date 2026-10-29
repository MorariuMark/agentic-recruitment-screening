"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParsingBatch } from "@/lib/parsing-batch";
import { ParsingProgress } from "./parsing-progress";
import { ArrowRight, Check, ChevronLeft, ChevronRight, FileText, RotateCcw, Search, Upload, Users, X, Zap } from "lucide-react";
import { CandidateSummary, CVUploadResponse, ScreeningRun, JobDescription } from "@/types";
import { api } from "@/lib/api";
import { cohortSelection } from "@/lib/candidate-cohort";
import { Empty, message } from "./common";
import { ProfileDialog } from "./profile";
import { ParsedProfile } from "./parsed-profile";
import { ProcessIndicator, useTimedActivity } from "./process-indicator";

interface Props { jobId: string; candidates: CandidateSummary[]; run: ScreeningRun | null; onRun: (run: ScreeningRun) => void; onRefresh: () => Promise<unknown>; onCompare: () => void; jobs?: JobDescription[]; onSelectJob?: (id: string) => void; }
export function Verification({jobId, candidates, run, onRun, onRefresh, onCompare, jobs = [], onSelectJob}: Props) {
  const [section, setSection] = useState<"cohort" | "single">("cohort");
  const [selected, setSelected] = useState<string[]>([]);
  const [cohortSize, setCohortSize] = useState(() => Math.min(100, candidates.length));
  const [search, setSearch] = useState("");
  const [jobSearchQuery, setJobSearchQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [shortlistCount, setShortlistCount] = useState(10);
  const [mode, setMode] = useState("hybrid-deep");
  const [demoOnly, setDemoOnly] = useState(false);
  const deep = mode.endsWith("deep");
  const improved = mode.startsWith("hybrid");
  const [rerankEnabled, setRerankEnabled] = useState(true);
  const [rerankPool, setRerankPool] = useState(100);
  const [busy, setBusy, startedAt, lastActivity] = useTimedActivity<string>("");
  const [uploadStartedAt, setUploadStartedAt] = useState<number | null>(null);
  const [error, setError] = useState("");
  const {batchId, batch, setBatchId} = useParsingBatch();
  const [single, setSingle] = useState<CVUploadResponse | null>(null);
  const [singleRunId, setSingleRunId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [page, setPage] = useState(0);
  const [uploadCollapsed, setUploadCollapsed] = useState(candidates.length > 0);
  const [singleSearch, setSingleSearch] = useState("");
  const [singleSearchOpen, setSingleSearchOpen] = useState(false);
  const singleCandidateSearchRef = useRef<HTMLDivElement>(null);
  const [cohortSearchOpen, setCohortSearchOpen] = useState(false);
  const cohortSearchRef = useRef<HTMLDivElement>(null);
  const [uploadDuration, setUploadDuration] = useState<number | null>(null);
  const [singleEvalDuration, setSingleEvalDuration] = useState<number | null>(null);
  const [screeningDuration, setScreeningDuration] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const completedBatch = useRef("");

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (singleCandidateSearchRef.current && !singleCandidateSearchRef.current.contains(e.target as Node)) {
        setSingleSearchOpen(false);
      }
      if (cohortSearchRef.current && !cohortSearchRef.current.contains(e.target as Node)) {
        setCohortSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const refreshRef = useRef(onRefresh);
  useEffect(() => {refreshRef.current = onRefresh;}, [onRefresh]);
  useEffect(() => {
    if (batch.data && !["PROCESSING", "QUEUED"].includes(batch.data.status) && completedBatch.current !== batchId) {
      completedBatch.current = batchId; void refreshRef.current();
    }
  }, [batch.data, batchId]);
  const activeRun = run?.status === "ranking" || run?.status === "evaluating";
  const activeRequirementCount = run?.job.requirements.filter(requirement => requirement.weight > 0).length;
  const screening = busy === "rank" || activeRun;
  const rankStartedAt = activeRun && run?.started_at ? run.started_at : lastActivity === "rank" ? startedAt : null;
  const uploading = busy === "upload" || ["PROCESSING", "QUEUED"].includes(batch.data?.status || "");
  useEffect(() => {
    if (uploading) setUploadCollapsed(false);
  }, [uploading]);
  const ranked = new Map(run?.rows.map(row => [row.candidate_id, row]) || []);
  const duplicateIds = new Set(run?.duplicates?.map(item => item.candidate_id) || []);
  const cohortCandidates = candidates.filter(candidate => !!candidate.is_benchmark === demoOnly && !duplicateIds.has(candidate.id));
  const filtered = cohortCandidates.filter(c => `${c.masked_name} ${c.skills.join(" ")}`.toLowerCase().includes(search.toLowerCase())).sort((a,b) => (ranked.get(a.id)?.rank ?? Infinity) - (ranked.get(b.id)?.rank ?? Infinity));
  const maxPage = Math.max(0, Math.ceil(filtered.length / 25) - 1);
  const currentPage = Math.min(page, maxPage);
  const visible = filtered.slice(currentPage * 25, currentPage * 25 + 25);
  const selectedIds = [...new Set(selected.filter(id => cohortCandidates.some(c => c.id === id)))];
  const singleRow = single ? run?.rows.find(row => row.candidate_id === single.candidate_id) : undefined;
  const singleRun = (run?.id === singleRunId && run.job_id === jobId) ? run : singleRow ? run : null;
  const matchingCohortCandidates = useMemo(() => {
    if (!singleSearch.trim()) return cohortCandidates;
    const q = singleSearch.toLowerCase().trim();
    return cohortCandidates.filter(c =>
      c.masked_name.toLowerCase().includes(q) ||
      c.skills.some(s => s.toLowerCase().includes(q))
    );
  }, [cohortCandidates, singleSearch]);

  const selectCohortCandidate = async (candId: string) => {
    setBusy("load-candidate");
    setError("");
    try {
      const detail = await api.getCandidate(candId);
      const fallbackParsed: any = {
        contact_info: { full_name: detail.masked_name || `Candidate ${detail.id.slice(0, 8)}`, email: null, phone: null, location: null },
        skills: detail.skills || [],
        experiences: detail.experiences || [],
        education: detail.educations || [],
        certifications: [],
        projects: [],
        languages: [],
        raw_text: detail.sanitized_text || "",
      };
      const fallbackAnonymized: any = {
        candidate_id: detail.id,
        anonymized_work_experiences: detail.experiences || [],
        anonymized_education: detail.educations || [],
        anonymized_skills: detail.skills || [],
        anonymized_certifications: [],
        anonymized_projects: [],
        anonymized_languages: [],
        sanitized_text: detail.sanitized_text || "",
      };
      setSingle({
        candidate_id: detail.id,
        parsed_cv: detail.parsed_cv || fallbackParsed,
        anonymized_candidate: detail.anonymized_candidate || fallbackAnonymized,
        chunks_indexed: detail.chunks_indexed || 0,
      });
      setSingleRunId(run?.id || "");
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  };

  const runTotalMs = useMemo(() => {
    if (!run) return null;
    if (run.diagnostics?.timings_ms) {
      const sum = Object.values(run.diagnostics.timings_ms).reduce((a, b) => a + b, 0);
      if (sum > 0) return sum;
    }
    if (run.ended_at && run.started_at) {
      const diff = typeof run.ended_at === "number" && typeof run.started_at === "number"
        ? (run.ended_at > 1e11 ? run.ended_at - run.started_at : (run.ended_at - run.started_at) * 1000)
        : null;
      if (diff && diff > 0) return diff;
    }
    return screeningDuration ? screeningDuration * 1000 : null;
  }, [run, screeningDuration]);

  const allSelected = filtered.length > 0 && filtered.every(c => selected.includes(c.id));
  const topRows = run?.rows.filter(row => row.deep_status === "completed").slice(0, shortlistCount) || [];
  const selectedForDeep = selectedIds.filter(id => ranked.has(id) && ranked.get(id)?.deep_status !== "completed");
  const canCompare = !!topRows.length && !activeRun;
  const validSettings = (!deep || (Number.isInteger(topK) && topK >= 1 && topK <= 100)) &&
    (!improved || !rerankEnabled || (Number.isInteger(rerankPool) && rerankPool >= 1 && rerankPool <= 200));
  const canScreen = !!jobId && selectedIds.length > 0 && !busy && !activeRun && validSettings;
  useEffect(() => {
    if (!run) return;
    setMode(`${run.pipeline_version === "v2" ? "hybrid" : "legacy"}-${run.deep_enabled ? "deep" : "fast"}`);
    setTopK(run.top_k);
  }, [run?.id]);

  async function upload(files: File[], singleFile = false) {
    if (!files.length) return;
    const startTime = Date.now();
    setBusy("upload"); setUploadStartedAt(startTime); setError("");
    if (singleFile) {setSingle(null); setSingleRunId("");}
    try {
      if (singleFile) {const result = await api.uploadSingleCV(files[0]); setSingle(result); await onRefresh();}
      else {const result = await api.uploadCohort(files); setBatchId(result.batch_id);}
      setUploadDuration(Math.round((Date.now() - startTime) / 100) / 10);
    } catch(e) {setError(message(e));} finally {setBusy(""); if(inputRef.current) inputRef.current.value = "";}
  }

  const triggerScreening = async () => {
    if (!canScreen) {setError("Choose candidates and valid screening options before starting."); return;}
    const startTime = Date.now();
    setBusy("rank"); setError("");
    try {
      const res = await api.fastRank(jobId, selectedIds, deep ? topK : 10, deep, {
        pipeline_version: improved ? "v2" : "v1",
        rerank_enabled: rerankEnabled,
        rerank_pool_size: rerankEnabled ? rerankPool : 100,
        include_benchmark: demoOnly,
      });
      setScreeningDuration(Math.round((Date.now() - startTime) / 100) / 10);
      onRun(res);
    } catch(e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  };

  const evaluateSingle = async () => {
    if (!single || !jobId || busy || activeRun) return;
    const startTime = Date.now();
    setBusy("rank"); setError(""); setSingleRunId("");
    try {
      const result = await api.fastRank(jobId, [single.candidate_id], 1, true, {
        pipeline_version: "v2", rerank_enabled: rerankEnabled,
        rerank_pool_size: rerankEnabled && Number.isInteger(rerankPool) && rerankPool >= 1 && rerankPool <= 200 ? rerankPool : 100,
        include_benchmark: false,
      });
      setSingleRunId(result.id);
      setSingleEvalDuration(Math.round((Date.now() - startTime) / 100) / 10);
      onRun(result);
    } catch(e) {setError(message(e));} finally {setBusy("");}
  };

  return <><div className="r-tabs" role="tablist" aria-label="CV upload mode"><button role="tab" aria-selected={section === "cohort"} className={section === "cohort" ? "active" : ""} onClick={() => setSection("cohort")}><Users size={17}/>Cohort<span>{cohortCandidates.length}</span></button><button role="tab" aria-selected={section === "single"} className={section === "single" ? "active" : ""} onClick={() => setSection("single")}><FileText size={17}/>Single CV & parser</button></div>
        {error && <div className="r-alert" role="alert">{error}</div>}
    {run && activeRequirementCount != null && activeRequirementCount < 3 && <div className="r-alert" role="status">This run used only {activeRequirementCount} active {activeRequirementCount === 1 ? "requirement" : "requirements"}. Scores reflect those criteria only. Review the job requirements before using these results to shortlist candidates.</div>}
    {run?.pipeline_version === "v2" && run.diagnostics?.version !== "evidence-v2.4" && !activeRun && <p className="r-processing-note" role="status">These saved results use an earlier scoring policy. Rank the cohort again to apply the updated evidence checks.</p>}
    <input ref={inputRef} type="file" style={{ display: "none" }} aria-label={section === "cohort" ? "Upload cohort CVs" : "Upload a single CV"} accept=".pdf,.docx,.txt" multiple={section === "cohort"} disabled={uploading} onChange={e => void upload(Array.from(e.target.files || []), section === "single")}/>
    {section === "cohort" && uploadCollapsed && !uploading && cohortCandidates.length > 0 ? (
      <div className="r-upload-collapsed" onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); void upload(Array.from(e.dataTransfer.files), false);}}>
        <div className="r-upload-summary">
          <Upload size={16}/>
          <span><strong>{cohortCandidates.length} CVs in cohort</strong> · Drag more files here or choose from computer</span>
        </div>
        <div className="r-upload-collapsed-actions">
          <button type="button" className="r-button subtle" onClick={() => setUploadCollapsed(false)}>Expand upload dropzone</button>
          <button type="button" className="r-button" onClick={() => inputRef.current?.click()}>Choose files</button>
        </div>
      </div>
    ) : (
      <div className="r-upload-zone" aria-busy={uploading} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); if (!uploading) void upload(Array.from(e.dataTransfer.files), section === "single");}}><div className="r-upload-icon">{uploading ? <ProcessIndicator active timer={false} label="Parsing CVs"/> : <Upload size={23}/>}</div><div><h3>{section === "cohort" ? "Add CVs to your cohort" : "Parse a single CV"}</h3><p>{section === "cohort" ? "Drop multiple files here or choose from your computer." : "Review the extracted profile. The candidate is added to your cohort automatically."}<span>PDF, DOCX or TXT · up to 20 MB per file</span></p></div><div className="r-upload-actions"><button type="button" className={`r-button ${uploading ? "disabled" : ""}`} disabled={uploading} onClick={() => inputRef.current?.click()}><ProcessIndicator active={uploading} startedAt={lastActivity === "upload" ? uploadStartedAt : null} label="Parsing CVs"/>{uploading ? "Processing CVs…" : "Choose files"}</button>{section === "cohort" && cohortCandidates.length > 0 && !uploading && <button type="button" className="r-button subtle" onClick={() => setUploadCollapsed(true)}>Collapse</button>}</div></div>
    )}
    {!!run?.duplicates?.length && <p className="r-processing-note" role="status">{run.duplicates.length} duplicate {run.duplicates.length === 1 ? "CV excluded" : "CVs excluded"} from this ranking. Repeated documents or matching contact identities were grouped. Historical runs retain their original grouping.</p>}
    <ParsingProgress/>
    {section === "single" ? <section className="r-panel">
      <div className="r-single-cohort-picker">
        <div className="r-single-cohort-header">
          <div>
            <h3>Choose candidate from cohort</h3>
            <p>Select any of the {cohortCandidates.length} parsed profiles in your cohort to inspect or evaluate against this role.</p>
          </div>
          {single && (
            <button
              type="button"
              className="r-button subtle"
              onClick={() => {
                setSingle(null);
                setSingleRunId("");
              }}
            >
              Clear selection
            </button>
          )}
        </div>
        <div className="r-single-cohort-controls">
          <div className="r-search" style={{ position: "relative", width: "100%", maxWidth: 440 }} ref={singleCandidateSearchRef}>
            <Search size={16} />
            <input
              placeholder="Search cohort by candidate name or skill…"
              aria-label="Search cohort candidates"
              value={singleSearch}
              onChange={e => {
                setSingleSearch(e.target.value);
                setSingleSearchOpen(true);
              }}
              onFocus={() => setSingleSearchOpen(true)}
              onKeyDown={e => {
                if (e.key === "Escape") setSingleSearchOpen(false);
              }}
            />
            {singleSearch && (
              <button
                type="button"
                className="r-job-search-clear"
                onClick={() => {
                  setSingleSearch("");
                  setSingleSearchOpen(false);
                }}
                aria-label="Clear search"
              >
                <X size={14} />
              </button>
            )}
            {singleSearchOpen && (
              <div className="r-search-autocomplete r-search-autocomplete-wide" role="listbox">
                {matchingCohortCandidates.length === 0 ? (
                  <div className="r-search-empty">No matching candidates in cohort</div>
                ) : (
                  matchingCohortCandidates.slice(0, 10).map(c => {
                    const row = ranked.get(c.id);
                    const isSelected = single?.candidate_id === c.id;
                    return (
                      <button
                        key={c.id}
                        type="button"
                        className={`r-search-item ${isSelected ? "active" : ""}`}
                        onClick={async () => {
                          setSingleSearch(c.masked_name);
                          setSingleSearchOpen(false);
                          await selectCohortCandidate(c.id);
                        }}
                        role="option"
                        aria-selected={isSelected}
                      >
                        <div className="r-search-item-title">
                          <span>{c.masked_name || `Candidate ${c.id.slice(0, 8)}`}</span>
                          {row?.deep_evaluation ? (
                            <span className={`r-pill ${row.deep_evaluation.overall_score >= 75 ? "success" : row.deep_evaluation.overall_score < 50 ? "alert-pill" : "warning"}`}>
                              {row.deep_evaluation.overall_score.toFixed(0)}/100 · {row.deep_evaluation.overall_score >= 75 ? "Match" : row.deep_evaluation.overall_score < 50 ? "Reject" : "Borderline"}
                            </span>
                          ) : row ? (
                            <span className="r-pill">Pre-screen: {row.pre_screen_score.toFixed(0)}</span>
                          ) : (
                            <span className="r-muted" style={{ fontSize: 10 }}>Not yet screened</span>
                          )}
                        </div>
                        <div className="r-search-item-meta">
                          <span>{c.total_years_experience != null ? `${c.total_years_experience.toFixed(1)} yrs exp` : "Exp not stated"}</span>
                          <span>·</span>
                          <span>Skills: {c.skills.slice(0, 4).join(", ") || "General"}</span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>
          <span style={{ fontSize: 12, color: "var(--r-muted)" }}>or choose/drop a fresh file above</span>
        </div>
      </div>
      {single ? <div className="r-single-result">
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
          <span className="r-pill success"><Check size={14}/>Profile loaded</span>
          {uploadDuration != null && <span className="r-duration-badge success"><Check size={12}/>Parsed in {uploadDuration.toFixed(1)}s</span>}
          {singleEvalDuration != null && <span className="r-duration-badge success"><Zap size={12}/>Evaluated in {singleEvalDuration.toFixed(1)}s</span>}
        </div>
        <h2>Parsed candidate profile</h2><ParsedProfile profile={single.parsed_cv}/>
      <div className="r-review-ready" aria-busy={screening}>
        <div><h3>Evaluate against the selected job</h3><p>{jobId ? "Run the same evidence-based screening and deep evaluation used for the cohort." : "Select a job to evaluate this CV."}</p></div>
        <button className="r-button primary" disabled={!jobId || !!busy || activeRun} onClick={() => void evaluateSingle()}><Zap size={16}/><ProcessIndicator active={screening} startedAt={rankStartedAt} timer={screening} label="Evaluating CV"/>{screening ? "Evaluating…" : singleRow ? "Re-evaluate CV" : "Evaluate CV"}</button>
        <button className="r-button" onClick={() => {setSection("cohort"); setSelected([single.candidate_id]);}}>View in cohort<ArrowRight size={16}/></button>
      </div>
      {(singleRun || singleRow) && (
        <div className="r-run-status" role="status">
          {activeRun && <ProcessIndicator active timer={false} label="Evaluating CV"/>}
          <span>
            {activeRun
              ? (singleRun?.phase || "Evaluating CV against the selected job…")
              : singleRun?.status === "failed"
              ? `Screening failed: ${singleRun.error || "Please try again."}`
              : singleRun?.status === "cancelled"
              ? "Screening cancelled."
              : singleRow && singleRow.deep_status === "completed" && singleRow.deep_evaluation
              ? `Evaluation complete · ${singleRow.deep_evaluation.overall_score.toFixed(1)} / 100 · ${singleRow.deep_evaluation.overall_score >= 75 ? "Match" : singleRow.deep_evaluation.overall_score < 50 ? "Reject" : "Borderline"}`
              : singleRow
              ? `Pre-screen score: ${singleRow.pre_screen_score.toFixed(1)} / 100${singleRow.deep_status === "deferred" ? " · Deep eval deferred (providers busy)" : ""}`
              : "Evaluation pending."}
          </span>
        </div>
      )}
      {singleRow && <button type="button" className="r-button" onClick={() => setProfileId(single.candidate_id)}>View evaluation and evidence<ArrowRight size={16}/></button>}
      {singleRun?.profile_hashes && ["partial", "failed", "cancelled"].includes(singleRun.status) && <button className="r-retry-button" disabled={!!busy || !!activeRun} onClick={async () => {setBusy("retry"); setError(""); try {onRun(await api.retryScreeningRun(singleRun.id));} catch(e) {setError(message(e));} finally {setBusy("");}}}><RotateCcw size={15}/>Retry unfinished screening</button>}
      </div> : <Empty title="One CV, a clear profile">Upload a CV above or select an existing candidate from the cohort above to inspect and evaluate against the selected role.</Empty>}</section> : <>
      <section className="r-rank-controls r-rank-controls-compact" aria-label="Screen your cohort" aria-busy={screening}>
        <div className="r-rank-main-row">
          <div className="r-rank-title"><Zap size={19}/><div><h3>Screen cohort</h3><p>New screening options. Required languages and recruiter-defined evidence gates take priority; unknown evidence needs clarification.</p></div></div>
          <div className="r-rank-fields">
            <label className="r-field r-small-field">Cohort size<input aria-label="Cohort size" type="number" min={1} max={cohortCandidates.length || 1} value={cohortSize} disabled={screening || !!busy} onChange={e => setCohortSize(Number(e.target.value))}/></label>
            <button className="r-button" disabled={screening || !!busy || !cohortSelection(cohortCandidates, cohortSize)} onClick={() => {
              const next = cohortSelection(cohortCandidates, cohortSize);
              if (next) {setSelected(next); setPage(0);}
            }}>Apply</button>
            <label className="r-cohort-select-all"><input type="checkbox" aria-label="Select all parsed CVs" disabled={screening || !!busy || !cohortCandidates.length}
              checked={cohortCandidates.length > 0 && selectedIds.length === cohortCandidates.length}
              onChange={e => {setSelected(e.target.checked ? cohortCandidates.map(candidate => candidate.id) : []); setCohortSize(e.target.checked ? cohortCandidates.length : Math.min(100, cohortCandidates.length));}}/>Select all {cohortCandidates.length} parsed CVs</label>
            <label className="r-field">Screening mode<select value={mode} onChange={e => setMode(e.target.value)} disabled={!!busy || activeRun}><option value="legacy-deep">Fast Batch Rank (Top-K Deep Eval)</option><option value="hybrid-deep">Improved hybrid rank (Top-K Deep Eval)</option><option value="hybrid-fast">Improved hybrid pre-screen only</option><option value="legacy-fast">Fast pre-screen only</option></select></label>
            <label className="r-field r-small-field">Deep top<input type="number" min={1} max={100} value={topK} disabled={!deep || !!busy || activeRun} onChange={e => setTopK(Number(e.target.value))}/></label>
                        <button className="r-button primary" disabled={!canScreen} onClick={triggerScreening}><Zap size={16}/><ProcessIndicator active={screening} startedAt={rankStartedAt} timer={screening} label="Screening candidates"/> {screening ? "Screening…" : `Rank ${selectedIds.length || "selected"} candidates`}</button>
          </div>
        </div>
        </section>
        {run && <p className="r-muted">Displayed run: {run.pipeline_version === "v2" ? "Improved hybrid" : "Fast batch"} · {run.deep_enabled ? `Deep evaluation of up to ${run.top_k}` : "Pre-screen only"}{run.dataset === "benchmark" ? " · Demo data" : ""}. Documented required languages are prioritized in new runs; missing evidence remains for review.</p>}
        <section className="r-panel r-review-ready" aria-label="Continue to comparison">
          <div><h3>Review evaluated candidates</h3><p>{topRows.length ? `${topRows.length} completed evaluations ready for comparison.` : run?.deep_enabled ? "No completed evaluations yet. Review language evidence or select ranked profiles for deep evaluation." : "Run screening with deep evaluation, or select ranked profiles to evaluate, before comparison."}</p></div>
          <label className="r-field r-small-field">Compare up to<input type="number" min={1} max={100} value={shortlistCount} onChange={e => setShortlistCount(Number(e.target.value))}/></label>
          <button className="r-button primary" disabled={!run || !canCompare || !!busy || !Number.isInteger(shortlistCount) || shortlistCount < 1 || shortlistCount > 100} onClick={async () => {setBusy("shortlist"); setError(""); try {onRun(await api.shortlist(run!.id, shortlistCount)); onCompare();} catch(e) {setError(message(e));} finally {setBusy("");}}}>Review {topRows.length || "evaluated"} candidates<ArrowRight size={16}/></button>
        </section>
        {run?.evidence_policy_version === "source-v2" && <button className="r-button" disabled={!!busy || activeRun || !selectedForDeep.length || selectedForDeep.length > 100} onClick={async () => {setBusy("evaluate-selected"); setError(""); try {onRun(await api.deepEvaluateSelected(run.id, selectedForDeep));} catch(e) {setError(message(e));} finally {setBusy("");}}}>Deep evaluate selected ({selectedForDeep.length})</button>}
        <details className="r-scoring-note r-screening-advanced"><summary>Advanced screening options</summary>
          <div className="r-advanced-grid">
            {improved && <div className="r-advanced-options"><label><input type="checkbox" checked={rerankEnabled} disabled={screening} onChange={e => setRerankEnabled(e.target.checked)}/> Rerank evidence with local cross-encoder</label><label className="r-field">Reranking pool<input type="number" min={1} max={200} value={rerankPool} disabled={screening || !rerankEnabled} onChange={e => setRerankPool(Number(e.target.value))}/></label></div>}
          </div>
                  </details>
      {run && !run.evidence_policy_version && <p className="r-inline-error" role="status">This historical run predates the evidence and language-ranking fixes. Start a new screening to use the corrected engine.</p>}
      {run && <div className="r-run-status" role="status">
        {activeRun ? <ProcessIndicator active timer={false} label="Evaluating cohort"/> : <span className="r-status-dot"/>}
        <span>{run.status === "ranking" ? (run.phase || "Computing batch similarity and evidence checks…") : run.status === "evaluating" ? (run.phase || `${run.rows.length} candidates ranked. Deep evaluation: ${run.rows.filter(r => r.deep_status === "completed" || r.deep_status === "failed").length} of ${run.deep_candidate_ids?.length ?? Math.min(run.top_k, run.rows.length)} complete.`) : run.status === "cancelled" ? "Screening cancelled. Completed evaluations are retained." : run.status === "failed" ? `Screening failed: ${run.error}` : `${run.rows.length} candidates ranked · ${run.rows.filter(r => r.deep_status === "completed").length} deep evaluations complete${run.status === "partial" ? " · Some evaluations are unavailable; use Retry unfinished screening." : ""}`}</span>
        {runTotalMs != null && !activeRun && (
          <span className="r-duration-badge success" style={{ marginLeft: "auto" }}>
            <Zap size={13}/>
            Screening completed in {(runTotalMs / 1000).toFixed(1)}s
            {run.diagnostics?.timings_ms?.fast_screen ? ` (${(run.diagnostics.timings_ms.fast_screen / 1000).toFixed(1)}s pre-screen, ${((run.diagnostics.timings_ms.deep_evaluation || 0) / 1000).toFixed(1)}s deep)` : ""}
          </span>
        )}
      </div>}
      {run && ["completed", "partial"].includes(run.status) && <p className="r-statistics-footnote">{run.rows.filter(row => row.deep_status === "not_selected").length} candidates remain pre-screen only. Deep evaluation uses the configured Top-K budget. A “Reject” recommendation is a completed job-fit assessment; “Evaluation unavailable” means a processing problem.</p>}
      {run?.diagnostics && <details className="r-scoring-note r-run-diagnostics"><summary>Screening details {run.pipeline_version === "v2" ? "· Improved hybrid" : "· Fast batch"}</summary><p>{run.diagnostics.cache_hits || 0} cached profiles · {run.rows.filter(row => row.reranked).length} candidates reranked</p>{run.diagnostics.warnings?.map((warning,i) => <p key={i}>{warning}</p>)}{Object.entries(run.diagnostics.timings_ms || {}).map(([stage,ms]) => <span className="r-pill" key={stage}>{stage.replaceAll("_", " ")}: {(ms / 1000).toFixed(1)}s</span>)}</details>}
      {run?.profile_hashes && ["partial", "failed", "cancelled"].includes(run.status) && <button className="r-retry-button" disabled={!!busy} onClick={async () => {setBusy("retry"); setError(""); try {onRun(await api.retryScreeningRun(run.id));} catch(e) {setError(message(e));} finally {setBusy("");}}}><RotateCcw size={15}/><ProcessIndicator active={busy === "retry"} startedAt={lastActivity === "retry" ? startedAt : null} label="Retrying screening"/>Retry unfinished screening</button>}
      <section className="r-panel r-cohort">
        <div className="r-table-toolbar">
          <div>
            <h2>Candidate cohort <span>{cohortCandidates.length}</span></h2>
            <p>{selectedIds.length} of {cohortCandidates.length} selected{search ? ` · ${filtered.length} matching search` : ""}</p>
          </div>
          <div className="r-table-toolbar-actions">
            {selectedIds.length > 0 && <button className="r-button primary r-table-quick-cta" disabled={!canScreen} onClick={triggerScreening}><Zap size={14}/>Screen {selectedIds.length}</button>}
            <div className="r-search" style={{ position: "relative" }} ref={cohortSearchRef}>
              <Search size={16}/>
              <input
                placeholder="Search candidates or skills"
                aria-label="Search candidates"
                value={search}
                onChange={e => {
                  setSearch(e.target.value);
                  setPage(0);
                  setCohortSearchOpen(true);
                }}
                onFocus={() => { if (search.trim()) setCohortSearchOpen(true); }}
                onKeyDown={e => { if (e.key === "Escape") setCohortSearchOpen(false); }}
              />
              {search && (
                <button
                  type="button"
                  className="r-job-search-clear"
                  onClick={() => { setSearch(""); setCohortSearchOpen(false); }}
                  aria-label="Clear candidate search"
                >
                  <X size={14}/>
                </button>
              )}
              {cohortSearchOpen && search.trim() && (
                <div className="r-search-autocomplete r-search-autocomplete-wide" role="listbox">
                  {filtered.length === 0 ? (
                    <div className="r-search-empty">No matching candidates found</div>
                  ) : (
                    filtered.slice(0, 8).map(c => {
                      const row = ranked.get(c.id);
                      return (
                        <button
                          key={c.id}
                          type="button"
                          className="r-search-item"
                          onClick={() => {
                            setSearch(c.masked_name);
                            setCohortSearchOpen(false);
                            if (!selected.includes(c.id)) setSelected([...selected, c.id]);
                          }}
                          role="option"
                        >
                          <div className="r-search-item-title">
                            <span>{c.masked_name}</span>
                            {row?.deep_evaluation ? (
                              <span className={`r-pill ${row.deep_evaluation.overall_score >= 75 ? "success" : row.deep_evaluation.overall_score < 50 ? "alert-pill" : "warning"}`}>
                                {row.deep_evaluation.overall_score.toFixed(0)}/100
                              </span>
                            ) : row ? (
                              <span className="r-pill">Pre: {row.pre_screen_score.toFixed(0)}</span>
                            ) : null}
                          </div>
                          <div className="r-search-item-meta">
                            <span>{c.total_years_experience != null ? `${c.total_years_experience.toFixed(1)} yrs exp` : "Exp not stated"}</span>
                            <span>·</span>
                            <span>Skills: {c.skills.slice(0, 3).join(", ")}</span>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
        {!jobId && (jobs?.length || 0) > 0 && (
          <div className="r-verification-job-card">
            <div className="r-verification-job-header">
              <div>
                <strong>Select a job description to screen against</strong>
                <p>Search or choose from your active job requisitions:</p>
              </div>
              <div className="r-search" style={{ maxWidth: 260 }}>
                <Search size={15} />
                <input
                  placeholder="Search jobs…"
                  value={jobSearchQuery}
                  onChange={e => setJobSearchQuery(e.target.value)}
                  aria-label="Search jobs"
                />
              </div>
            </div>
            <div className="r-verification-job-list">
              {(jobs || [])
                .filter(j => !jobSearchQuery.trim() || `${j.title} ${j.department || ""} ${j.location || ""}`.toLowerCase().includes(jobSearchQuery.toLowerCase()))
                .slice(0, 8)
                .map(j => (
                  <button key={j.id} type="button" className="r-verification-job-btn" onClick={() => onSelectJob?.(j.id)}>
                    <span>{j.title}</span>
                    <small>{j.department || "General"}</small>
                  </button>
                ))}
            </div>
          </div>
        )}
        {!candidates.length ? <Empty title="Your cohort starts here">Upload CVs above, choose the job, then select candidates to rank.</Empty> : <div className="r-table-scroll"><table className="r-table"><thead><tr><th className="r-checkbox-cell"><input type="checkbox" aria-label="Select all matching candidates" title="Select all matching candidates across all pages" checked={allSelected} onChange={() => setSelected(allSelected ? selected.filter(id => !filtered.some(c => c.id === id)) : [...new Set([...selected, ...filtered.map(c => c.id)])])}/></th><th>Candidate</th><th>Key skills</th><th>Experience</th><th>Pre-screen</th><th>Deep evaluation</th><th><span className="r-sr-only">Profile</span></th></tr></thead><tbody>{visible.map(c => {const row = ranked.get(c.id); const deepScore = row?.deep_evaluation?.overall_score; let rec = row?.deep_evaluation?.recommendation; let recClass: "success" | "warning" | "alert-pill" = "alert-pill"; if (deepScore != null) { if (deepScore >= 75) { rec = "strong_match"; recClass = "success"; } else if (deepScore < 50) { rec = "reject"; recClass = "alert-pill"; } else { rec = "borderline"; recClass = "warning"; } } else if (rec) { recClass = rec === "strong_match" ? "success" : rec === "borderline" ? "warning" : "alert-pill"; } const preScoreClass = row ? (row.pre_screen_score >= 75 ? "r-score-high" : row.pre_screen_score < 50 ? "r-score-low" : "") : ""; const isCurrentlyEvaluating = run?.status === "evaluating" && run?.active_candidate_id === c.id; return <tr key={c.id} className={`${selected.includes(c.id) ? "selected" : ""} ${isCurrentlyEvaluating ? "r-evaluating-row" : ""}`.trim()}><td><input type="checkbox" aria-label={`Select ${c.masked_name}`} checked={selected.includes(c.id)} onChange={() => setSelected(selected.includes(c.id) ? selected.filter(id => id !== c.id) : [...selected, c.id])}/></td><td><div className="r-candidate-cell"><span className="r-avatar">{row ? String(row.rank).padStart(2,"0") : c.masked_name?.slice(0,1) || "C"}</span><div><strong>{c.masked_name || `Candidate ${c.id.slice(0,8)}`}</strong><small>{row ? `Rank ${row.rank}${row.pipeline_version === "v2" ? ` · ${row.essential_supported}/${row.essential_total} required supported${row.reranked ? " · reranked" : ""}` : ""}` : "Ready to screen"}</small></div></div></td><td><div className="r-tags">{c.skills.slice(0,2).map((s,i) => <span key={i}>{s}</span>)}{c.skills.length > 2 && <span title={c.skills.slice(2).join(", ")}>+{c.skills.length - 2}</span>}</div></td><td>{c.total_years_experience != null ? `${c.total_years_experience.toFixed(1)} years` : "Not stated"}</td><td>{row ? <span className={`r-score ${preScoreClass}`}>{row.pre_screen_score.toFixed(1)}<small>/100</small></span> : <span className="r-muted">Not ranked</span>}</td><td>{row?.deep_status === "completed" && row.deep_evaluation ? <span className={`r-pill ${recClass}`} title={`Recommendation: ${rec}`}>{row.deep_evaluation.overall_score.toFixed(1)} / 100{rec ? ` · ${rec === "strong_match" ? "Match" : rec === "borderline" ? "Borderline" : "Reject"}` : ""}</span> : isCurrentlyEvaluating ? <span className="r-active-eval-badge"><ProcessIndicator active timer={false} label="Evaluating candidate"/>Evaluating CV now…</span> : <span className={`r-pill ${(row?.deep_status === "failed" || row?.deep_status === "deferred") ? "warning" : ""}`} title={row?.error || undefined}>{row?.deep_status === "pending" ? "Queued for evaluation…" : row?.deep_status === "deferred" ? "Providers busy — retry later" : row?.deep_status === "failed" ? "Evaluation unavailable — open profile" : "Pre-screen only"}</span>}</td><td><button type="button" className="r-icon-button" aria-label={`View ${c.masked_name} profile and scores`} onClick={() => setProfileId(c.id)}><ChevronRight size={18}/></button></td></tr>;})}</tbody></table>{!visible.length && <Empty title="No matching candidates">Try another name or skill.</Empty>}</div>}
        <div className="r-table-footer"><span>{filtered.length ? `${currentPage * 25 + 1}–${Math.min((currentPage + 1) * 25, filtered.length)} of ${filtered.length} matching (${cohortCandidates.length} total cohort)` : `0 candidates (${cohortCandidates.length} total cohort)`}</span><div><button className="r-icon-button" aria-label="Previous page" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={17}/></button><button className="r-icon-button" aria-label="Next page" disabled={currentPage >= maxPage} onClick={() => setPage(currentPage + 1)}><ChevronRight size={17}/></button></div></div>
      </section>
    </>}
    {profileId && <ProfileDialog id={profileId} row={ranked.get(profileId)} onClose={() => setProfileId("")}/>}
  </>;
}
