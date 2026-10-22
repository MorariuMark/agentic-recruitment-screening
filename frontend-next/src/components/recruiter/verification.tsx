"use client";
import { useEffect, useRef, useState } from "react";
import { useParsingBatch } from "@/lib/parsing-batch";
import { ParsingProgress } from "./parsing-progress";
import { ArrowRight, Check, ChevronLeft, ChevronRight, FileText, Search, Upload, Users, Zap } from "lucide-react";
import { CandidateSummary, CVUploadResponse, ScreeningRun } from "@/types";
import { api } from "@/lib/api";
import { cohortSelection } from "@/lib/candidate-cohort";
import { Empty, message } from "./common";
import { ProfileDialog } from "./profile";
import { ParsedProfile } from "./parsed-profile";
import { ProcessIndicator, useTimedActivity } from "./process-indicator";

interface Props { jobId: string; candidates: CandidateSummary[]; run: ScreeningRun | null; onRun: (run: ScreeningRun) => void; onRefresh: () => Promise<unknown>; onCompare: () => void; }
export function Verification({jobId, candidates, run, onRun, onRefresh, onCompare}: Props) {
  const [section, setSection] = useState<"cohort" | "single">("cohort");
  const [selected, setSelected] = useState<string[]>([]);
  const [cohortSize, setCohortSize] = useState(() => Math.min(100, candidates.length));
  const [search, setSearch] = useState("");
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
  const [profileId, setProfileId] = useState("");
  const [page, setPage] = useState(0);
  const [uploadCollapsed, setUploadCollapsed] = useState(candidates.length > 0);
  const inputRef = useRef<HTMLInputElement>(null);
  const completedBatch = useRef("");

  const refreshRef = useRef(onRefresh);
  useEffect(() => {refreshRef.current = onRefresh;}, [onRefresh]);
  useEffect(() => {
    if (batch.data && !["PROCESSING", "QUEUED"].includes(batch.data.status) && completedBatch.current !== batchId) {
      completedBatch.current = batchId; void refreshRef.current();
    }
  }, [batch.data, batchId]);
  const activeRun = run?.status === "ranking" || run?.status === "evaluating";
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
    setBusy("upload"); setUploadStartedAt(Date.now()); setError("");
    try {
      if (singleFile) {const result = await api.uploadSingleCV(files[0]); setSingle(result); await onRefresh();}
      else {const result = await api.uploadCohort(files); setBatchId(result.batch_id);}
    } catch(e) {setError(message(e));} finally {setBusy(""); if(inputRef.current) inputRef.current.value = "";}
  }

  const triggerScreening = async () => {
    if (!canScreen) {setError("Choose candidates and valid screening options before starting."); return;}
    setBusy("rank"); setError("");
    try {
      onRun(await api.fastRank(jobId, selectedIds, deep ? topK : 10, deep, {
        pipeline_version: improved ? "v2" : "v1",
        rerank_enabled: rerankEnabled,
        rerank_pool_size: rerankEnabled ? rerankPool : 100,
        include_benchmark: demoOnly,
      }));
    } catch(e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  };

  return <><div className="r-tabs" role="tablist" aria-label="CV upload mode"><button role="tab" aria-selected={section === "cohort"} className={section === "cohort" ? "active" : ""} onClick={() => setSection("cohort")}><Users size={17}/>Cohort<span>{cohortCandidates.length}</span></button><button role="tab" aria-selected={section === "single"} className={section === "single" ? "active" : ""} onClick={() => setSection("single")}><FileText size={17}/>Single CV & parser</button></div>
    <label className="r-dataset-switch"><input type="checkbox" checked={demoOnly} onChange={e => {setDemoOnly(e.target.checked); setSelected([]); setPage(0);}}/>Show demo profiles only <small>Demo profiles are screened separately from recruiting candidates.</small></label>
    {error && <div className="r-alert" role="alert">{error}</div>}
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
      <div className="r-upload-zone" aria-busy={uploading} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); if (!uploading) void upload(Array.from(e.dataTransfer.files), section === "single");}}><div className="r-upload-icon">{uploading ? <ProcessIndicator active timer={false} label="Parsing CVs"/> : <Upload size={23}/>}</div><div><h3>{section === "cohort" ? "Add CVs to your cohort" : "Parse a single CV"}</h3><p>{section === "cohort" ? "Drop multiple files here or choose from your computer." : "Review the extracted profile. The candidate is added to your cohort automatically."}<span>PDF, DOCX or TXT · up to 20 MB per file</span></p></div><div className="r-upload-actions"><button type="button" className={`r-button ${uploading ? "disabled" : ""}`} disabled={uploading} onClick={() => inputRef.current?.click()}><ProcessIndicator active={uploading} startedAt={lastActivity === "upload" ? uploadStartedAt : null} label="Parsing CVs"/>{uploading ? "Processing CVs…" : "Choose files"}</button>{cohortCandidates.length > 0 && !uploading && <button type="button" className="r-button subtle" onClick={() => setUploadCollapsed(true)}>Collapse</button>}</div></div>
    )}
    {!!run?.duplicates?.length && <p className="r-processing-note" role="status">{run.duplicates.length} duplicate {run.duplicates.length === 1 ? "CV excluded" : "CVs excluded"} from this ranking. Repeated documents or matching contact identities were grouped. Historical runs retain their original grouping.</p>}
    <ParsingProgress/>
    {section === "single" ? <section className="r-panel">{single ? <div className="r-single-result"><span className="r-pill success"><Check size={14}/>Added to cohort</span><h2>Parsed candidate profile</h2><ParsedProfile profile={single.parsed_cv}/><button className="r-button primary" onClick={() => {setSection("cohort"); setSelected([single.candidate_id]);}}>View in cohort<ArrowRight size={16}/></button></div> : <Empty title="One CV, a clear profile">Upload a CV to inspect extracted skills, experience and qualifications before ranking it with the cohort.</Empty>}</section> : <>
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
          <p className="r-scoring-explainer">{improved ? "Improved screening matches each weighted criterion to CV passages using keyword and semantic retrieval. Documented evidence has more weight than a skills-list mention. Soft skills remain for deep evaluation and human review." : "Similarity 40%, required skills 30%, experience 20%, education 10%. Missing evidence needs review. Pre-screen ranking stays fixed after deep evaluation."}</p>
        </details>
      {run && !run.evidence_policy_version && <p className="r-inline-error" role="status">This historical run predates the evidence and language-ranking fixes. Start a new screening to use the corrected engine.</p>}
      {run && <div className="r-run-status" role="status">{activeRun ? <ProcessIndicator active timer={false} label="Evaluating cohort"/> : <span className="r-status-dot"/>}<span>{run.status === "ranking" ? (run.phase || "Computing batch similarity and evidence checks…") : run.status === "evaluating" ? `${run.rows.length} candidates ranked. Deep evaluation: ${run.rows.filter(r => r.deep_status === "completed" || r.deep_status === "failed").length} of ${run.deep_candidate_ids?.length ?? Math.min(run.top_k, run.rows.length)} complete.` : run.status === "cancelled" ? "Screening cancelled. Completed evaluations are retained." : run.status === "failed" ? `Screening failed: ${run.error}` : `${run.rows.length} candidates ranked · ${run.rows.filter(r => r.deep_status === "completed").length} deep evaluations complete${run.status === "partial" ? " · Some evaluations failed; inspect the affected rows." : ""}`}</span></div>}
      {run && ["completed", "partial"].includes(run.status) && <p className="r-statistics-footnote">{run.rows.filter(row => row.deep_status === "not_selected").length} candidates remain pre-screen only. Deep evaluation uses the configured Top-K budget. A “Reject” recommendation is a completed job-fit assessment; “Evaluation unavailable” means a processing problem.</p>}
      {run?.diagnostics && <details className="r-scoring-note r-run-diagnostics"><summary>Screening details {run.pipeline_version === "v2" ? "· Improved hybrid" : "· Fast batch"}</summary><p>{run.diagnostics.cache_hits || 0} cached profiles · {run.rows.filter(row => row.reranked).length} candidates reranked</p>{run.diagnostics.warnings?.map((warning,i) => <p key={i}>{warning}</p>)}{Object.entries(run.diagnostics.timings_ms || {}).map(([stage,ms]) => <span className="r-pill" key={stage}>{stage.replaceAll("_", " ")}: {(ms / 1000).toFixed(1)}s</span>)}</details>}
      {run?.profile_hashes && ["partial", "failed", "cancelled"].includes(run.status) && <button className="r-button" disabled={!!busy} onClick={async () => {setBusy("retry"); setError(""); try {onRun(await api.retryScreeningRun(run.id));} catch(e) {setError(message(e));} finally {setBusy("");}}}><ProcessIndicator active={busy === "retry"} startedAt={lastActivity === "retry" ? startedAt : null} label="Retrying screening"/>Retry unfinished screening</button>}
      <section className="r-panel r-cohort"><div className="r-table-toolbar"><div><h2>Candidate cohort <span>{cohortCandidates.length}</span></h2><p>{selectedIds.length} of {cohortCandidates.length} selected{search ? ` · ${filtered.length} matching search` : ""}</p></div><div className="r-table-toolbar-actions">{selectedIds.length > 0 && <button className="r-button primary r-table-quick-cta" disabled={!canScreen} onClick={triggerScreening}><Zap size={14}/>Screen {selectedIds.length}</button>}<div className="r-search"><Search size={16}/><input placeholder="Search candidates or skills" aria-label="Search candidates" value={search} onChange={e => {setSearch(e.target.value); setPage(0);}}/></div></div></div>
        {!candidates.length ? <Empty title="Your cohort starts here">Upload CVs above, choose the job, then select candidates to rank.</Empty> : <div className="r-table-scroll"><table className="r-table"><thead><tr><th className="r-checkbox-cell"><input type="checkbox" aria-label="Select all matching candidates" title="Select all matching candidates across all pages" checked={allSelected} onChange={() => setSelected(allSelected ? selected.filter(id => !filtered.some(c => c.id === id)) : [...new Set([...selected, ...filtered.map(c => c.id)])])}/></th><th>Candidate</th><th>Key skills</th><th>Experience</th><th>Pre-screen</th><th>Deep evaluation</th><th><span className="r-sr-only">Profile</span></th></tr></thead><tbody>{visible.map(c => {const row = ranked.get(c.id); const rec = row?.deep_evaluation?.recommendation; const recClass = rec === "strong_match" ? "success" : rec === "borderline" ? "warning" : "alert-pill"; return <tr key={c.id} className={selected.includes(c.id) ? "selected" : ""}><td><input type="checkbox" aria-label={`Select ${c.masked_name}`} checked={selected.includes(c.id)} onChange={() => setSelected(selected.includes(c.id) ? selected.filter(id => id !== c.id) : [...selected, c.id])}/></td><td><div className="r-candidate-cell"><span className="r-avatar">{row ? String(row.rank).padStart(2,"0") : c.masked_name?.slice(0,1) || "C"}</span><div><strong>{c.masked_name || `Candidate ${c.id.slice(0,8)}`}</strong><small>{row ? `Rank ${row.rank}${row.pipeline_version === "v2" ? ` · ${row.essential_supported}/${row.essential_total} required supported${row.reranked ? " · reranked" : ""}` : ""}` : "Ready to screen"}</small></div></div></td><td><div className="r-tags">{c.skills.slice(0,2).map((s,i) => <span key={i}>{s}</span>)}{c.skills.length > 2 && <span title={c.skills.slice(2).join(", ")}>+{c.skills.length - 2}</span>}</div></td><td>{c.total_years_experience != null ? `${c.total_years_experience.toFixed(1)} years` : "Not stated"}</td><td>{row ? <span className="r-score">{row.pre_screen_score.toFixed(1)}<small>/100</small></span> : <span className="r-muted">Not ranked</span>}</td><td>{row?.deep_status === "completed" && row.deep_evaluation ? <span className={`r-pill ${recClass}`} title={`Recommendation: ${rec}`}>{row.deep_evaluation.overall_score.toFixed(1)} / 100{rec ? ` · ${rec === "strong_match" ? "Match" : rec === "borderline" ? "Borderline" : "Reject"}` : ""}</span> : <span className={`r-pill ${row?.deep_status === "failed" ? "warning" : ""}`} title={row?.error || undefined}>{row?.deep_status === "pending" ? "Evaluating…" : row?.deep_status === "failed" ? "Evaluation unavailable — open profile" : "Pre-screen only"}</span>}</td><td><button className="r-icon-button" aria-label={`View ${c.masked_name} profile and scores`} onClick={() => setProfileId(c.id)}><ChevronRight size={18}/></button></td></tr>;})}</tbody></table>{!visible.length && <Empty title="No matching candidates">Try another name or skill.</Empty>}</div>}
        <div className="r-table-footer"><span>{filtered.length ? `${currentPage * 25 + 1}–${Math.min((currentPage + 1) * 25, filtered.length)} of ${filtered.length} matching (${cohortCandidates.length} total cohort)` : `0 candidates (${cohortCandidates.length} total cohort)`}</span><div><button className="r-icon-button" aria-label="Previous page" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={17}/></button><button className="r-icon-button" aria-label="Next page" disabled={currentPage >= maxPage} onClick={() => setPage(currentPage + 1)}><ChevronRight size={17}/></button></div></div>
      </section>
    </>}
    {profileId && <ProfileDialog id={profileId} row={ranked.get(profileId)} onClose={() => setProfileId("")}/>}
  </>;
}
