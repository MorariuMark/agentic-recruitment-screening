"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, ChevronLeft, ChevronRight, FileText, Search, Upload, Users, Zap } from "lucide-react";
import { CandidateSummary, CVUploadResponse, ScreeningRun } from "@/types";
import { api } from "@/lib/api";
import { Empty, message } from "./common";
import { ProfileDialog } from "./profile";
import { ParsedProfile } from "./parsed-profile";
import { ProcessIndicator, useTimedActivity } from "./process-indicator";

interface Props { jobId: string; candidates: CandidateSummary[]; run: ScreeningRun | null; onRun: (run: ScreeningRun) => void; onRefresh: () => Promise<unknown>; onCompare: () => void; }
export function Verification({jobId, candidates, run, onRun, onRefresh, onCompare}: Props) {
  const [section, setSection] = useState<"cohort" | "single">("cohort");
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [topK, setTopK] = useState(10);
  const [shortlistCount, setShortlistCount] = useState(10);
  const [mode, setMode] = useState("legacy-deep");
  const deep = mode.endsWith("deep");
  const improved = mode.startsWith("hybrid");
  const [rerankEnabled, setRerankEnabled] = useState(true);
  const [rerankPool, setRerankPool] = useState(100);
  const [busy, setBusy, startedAt, lastActivity] = useTimedActivity<string>("");
  const [uploadStartedAt, setUploadStartedAt] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [batchId, setBatchId] = useState(() => typeof window !== "undefined" ? localStorage.getItem("atos_recruiter_batch") || "" : "");
  const [single, setSingle] = useState<CVUploadResponse | null>(null);
  const [profileId, setProfileId] = useState("");
  const [page, setPage] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const completedBatch = useRef("");
  const batch = useQuery({queryKey: ["recruiter-batch", batchId], queryFn: () => api.getBatchStatus(batchId), enabled: !!batchId, refetchInterval: q => q.state.data && q.state.data.status !== "PROCESSING" ? false : 2000});
  const refreshRef = useRef(onRefresh);
  useEffect(() => {refreshRef.current = onRefresh;}, [onRefresh]);
  useEffect(() => {
    if (batch.data && batch.data.status !== "PROCESSING" && completedBatch.current !== batchId) {
      completedBatch.current = batchId; localStorage.removeItem("atos_recruiter_batch"); void refreshRef.current();
    }
  }, [batch.data, batchId]);
  const activeRun = run?.status === "ranking" || run?.status === "evaluating";
  const screening = busy === "rank" || activeRun;
  const rankStartedAt = activeRun && run?.started_at ? run.started_at : lastActivity === "rank" ? startedAt : null;
  const uploading = busy === "upload" || batch.data?.status === "PROCESSING";
  const ranked = new Map(run?.rows.map(row => [row.candidate_id, row]) || []);
  const duplicateIds = new Set(run?.duplicates?.map(item => item.candidate_id) || []);
  const cohortCandidates = candidates.filter(candidate => !duplicateIds.has(candidate.id));
  const filtered = cohortCandidates.filter(c => `${c.masked_name} ${c.skills.join(" ")}`.toLowerCase().includes(search.toLowerCase())).sort((a,b) => (ranked.get(a.id)?.rank ?? Infinity) - (ranked.get(b.id)?.rank ?? Infinity));
  const maxPage = Math.max(0, Math.ceil(filtered.length / 25) - 1);
  const currentPage = Math.min(page, maxPage);
  const visible = filtered.slice(currentPage * 25, currentPage * 25 + 25);
  const selectedIds = selected.filter(id => cohortCandidates.some(c => c.id === id));
  const allSelected = filtered.length > 0 && filtered.every(c => selected.includes(c.id));
  const topRows = run?.rows.slice(0, shortlistCount) || [];
  const canCompare = !!topRows.length && topRows.every(r => r.deep_status === "completed") && !activeRun;

  async function upload(files: File[], singleFile = false) {
    if (!files.length) return;
    setBusy("upload"); setUploadStartedAt(Date.now()); setError("");
    try {
      if (singleFile) {const result = await api.uploadSingleCV(files[0]); setSingle(result); await onRefresh();}
      else {const result = await api.uploadCohort(files); setBatchId(result.batch_id); localStorage.setItem("atos_recruiter_batch", result.batch_id);}
    } catch(e) {setError(message(e));} finally {setBusy(""); if(inputRef.current) inputRef.current.value = "";}
  }

  return <><div className="r-tabs" role="tablist" aria-label="CV upload mode"><button role="tab" aria-selected={section === "cohort"} className={section === "cohort" ? "active" : ""} onClick={() => setSection("cohort")}><Users size={17}/>Cohort<span>{cohortCandidates.length}</span></button><button role="tab" aria-selected={section === "single"} className={section === "single" ? "active" : ""} onClick={() => setSection("single")}><FileText size={17}/>Single CV & parser</button></div>
    {error && <div className="r-alert" role="alert">{error}</div>}
    <div className="r-upload-zone" aria-busy={uploading} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); if (!uploading) void upload(Array.from(e.dataTransfer.files), section === "single");}}><div className="r-upload-icon">{uploading ? <ProcessIndicator active timer={false} label="Parsing CVs"/> : <Upload size={23}/>}</div><div><h3>{section === "cohort" ? "Add CVs to your cohort" : "Parse a single CV"}</h3><p>{section === "cohort" ? "Drop multiple files here or choose from your computer." : "Review the extracted profile. The candidate is added to your cohort automatically."}<span>PDF, DOCX or TXT · up to 20 MB per file</span></p></div><label className={`r-button ${uploading ? "disabled" : ""}`}><ProcessIndicator active={uploading} startedAt={lastActivity === "upload" ? uploadStartedAt : null} label="Parsing CVs"/>{uploading ? "Processing CVs…" : "Choose files"}<input ref={inputRef} type="file" className="r-file-input" aria-label={section === "cohort" ? "Upload cohort CVs" : "Upload a single CV"} accept=".pdf,.docx,.txt" multiple={section === "cohort"} disabled={uploading} onChange={e => void upload(Array.from(e.target.files || []), section === "single")}/></label></div>
    {!!run?.duplicates?.length && <p className="r-processing-note" role="status">{run.duplicates.length} duplicate {run.duplicates.length === 1 ? "CV excluded" : "CVs excluded"} from this ranking. One copy per matching name or identical evaluation is shown.</p>}
    {batchId && <div className="r-batch-status" role="status">{batch.error ? <span className="r-alert">Progress unavailable: {message(batch.error)} <button onClick={() => batch.refetch()}>Retry</button></span> : batch.data ? <><div><span>{batch.data.status === "PROCESSING" ? "Parsing your cohort" : "Cohort upload finished"}</span><strong>{batch.data.processed_files} parsed · {batch.data.failed_files} failed · {batch.data.total_files} files</strong></div><progress max={100} value={batch.data.progress_percentage}/>{batch.data.failed_files > 0 && <details><summary>Review upload errors</summary>{batch.data.results.filter(r => r.status === "FAILED").map((r,i) => <p key={i}>{r.filename}: {r.error}</p>)}</details>}</> : "Loading upload progress…"}</div>}
    {section === "single" ? <section className="r-panel">{single ? <div className="r-single-result"><span className="r-pill success"><Check size={14}/>Added to cohort</span><h2>Parsed candidate profile</h2><ParsedProfile profile={single.parsed_cv}/><button className="r-button primary" onClick={() => {setSection("cohort"); setSelected([single.candidate_id]);}}>View in cohort<ArrowRight size={16}/></button></div> : <Empty title="One CV, a clear profile">Upload a CV to inspect extracted skills, experience and qualifications before ranking it with the cohort.</Empty>}</section> : <>
      <section className="r-rank-controls" aria-label="Screen your cohort" aria-busy={screening}><div className="r-rank-title"><Zap size={19}/><div><h3>Screen your cohort</h3><p>Rank every selected CV. Take a closer look at the strongest matches.</p></div></div><div className="r-rank-fields"><label className="r-field">Screening mode<select value={mode} onChange={e => setMode(e.target.value)} disabled={!!busy || activeRun}><option value="legacy-deep">Fast Batch Rank (Top-K Deep Eval)</option><option value="hybrid-deep">Improved hybrid rank (Top-K Deep Eval)</option><option value="hybrid-fast">Improved hybrid pre-screen only</option><option value="legacy-fast">Fast pre-screen only</option></select></label><label className="r-field r-small-field">Deep evaluate top<input type="number" min={1} max={100} value={topK} disabled={!deep || !!busy || activeRun} onChange={e => setTopK(Number(e.target.value))}/></label><button className="r-button primary" disabled={!jobId || !selectedIds.length || !!busy || activeRun || !Number.isInteger(topK) || topK < 1 || topK > 100 || (improved && (!Number.isInteger(rerankPool) || rerankPool < 1 || rerankPool > 200))} onClick={async () => {setBusy("rank"); setError(""); try {onRun(await api.fastRank(jobId, selectedIds, topK, deep, {pipeline_version: improved ? "v2" : "v1", rerank_enabled: rerankEnabled, rerank_pool_size: rerankPool}));} catch(e) {setError(message(e));} finally {setBusy("");}}}><Zap size={16}/><ProcessIndicator active={screening} startedAt={rankStartedAt} label="Screening candidates"/> {screening ? "Screening…" : `Rank ${selectedIds.length || "selected"} candidates`}</button></div>
        {improved && <details className="r-scoring-note r-screening-advanced"><summary>Advanced screening options</summary><label><input type="checkbox" checked={rerankEnabled} disabled={screening} onChange={e => setRerankEnabled(e.target.checked)}/> Rerank evidence with the local cross-encoder</label><label className="r-field">Reranking pool<input type="number" min={1} max={200} value={rerankPool} disabled={screening || !rerankEnabled} onChange={e => setRerankPool(Number(e.target.value))}/></label><p>The pool expands to at least Top-K. If the configured local reranker is unavailable, hybrid ranking continues with a visible notice.</p></details>}
      <details className="r-scoring-note"><summary>How pre-screen scores work</summary><p>{improved ? "Improved screening matches each weighted criterion to CV passages using keyword and semantic retrieval. Documented evidence has more weight than a skills-list mention. Unknown is separate from contradicted. Reranking refines evidence relevance; scores are not probabilities. Soft skills remain for deep evaluation and human review." : "Similarity 40%, required skills 30%, experience 20%, education 10%. Criteria not requested by the job are excluded and weights are redistributed. Skills use documented terms; education checks CV claims, not external credentials. Missing evidence needs review. Pre-screen ranking stays fixed after deep evaluation."}</p></details>
        <div className="r-compare-controls"><div><h3>Compare your top candidates</h3><p>Completed deep evaluations are ready for human review.</p></div><label className="r-field r-small-field">Compare top<input type="number" min={1} max={100} value={shortlistCount} onChange={e => setShortlistCount(Number(e.target.value))}/></label><button className="r-button" disabled={!run || !canCompare || !!busy || !Number.isInteger(shortlistCount) || shortlistCount < 1 || shortlistCount > 100} onClick={async () => {setBusy("shortlist"); setError(""); try {onRun(await api.shortlist(run!.id, shortlistCount)); onCompare();} catch(e) {setError(message(e));} finally {setBusy("");}}}><ProcessIndicator active={busy === "shortlist"} startedAt={lastActivity === "shortlist" ? startedAt : null} label="Preparing comparison"/>Comparison matrix<ArrowRight size={16}/></button></div>
        {run && !canCompare && <small className="r-compare-hint">Complete deep evaluations for the selected top candidates to compare.</small>}
      </section>
      {run && <div className="r-run-status" role="status">{activeRun ? <ProcessIndicator active timer={false} label="Evaluating cohort"/> : <span className="r-status-dot"/>}<span>{run.status === "ranking" ? (run.phase || "Computing batch similarity and evidence checks…") : run.status === "evaluating" ? `${run.rows.length} candidates ranked. Deep evaluation: ${run.rows.filter(r => r.deep_status === "completed" || r.deep_status === "failed").length} of ${Math.min(run.top_k, run.rows.length)} complete.` : run.status === "failed" ? `Screening failed: ${run.error}` : `${run.rows.length} candidates ranked · ${run.rows.filter(r => r.deep_status === "completed").length} deep evaluations complete${run.status === "partial" ? " · Some evaluations failed; inspect the affected rows." : ""}`}</span></div>}
      {run?.diagnostics && <details className="r-scoring-note r-run-diagnostics"><summary>Screening details {run.pipeline_version === "v2" ? "· Improved hybrid" : "· Fast batch"}</summary><p>{run.diagnostics.cache_hits || 0} cached profiles · {run.rows.filter(row => row.reranked).length} candidates reranked</p>{run.diagnostics.warnings?.map((warning,i) => <p key={i}>{warning}</p>)}{Object.entries(run.diagnostics.timings_ms || {}).map(([stage,ms]) => <span className="r-pill" key={stage}>{stage.replaceAll("_", " ")}: {(ms / 1000).toFixed(1)}s</span>)}</details>}
      {run?.profile_hashes && ["partial", "failed"].includes(run.status) && <button className="r-button" disabled={!!busy} onClick={async () => {setBusy("retry"); setError(""); try {onRun(await api.retryScreeningRun(run.id));} catch(e) {setError(message(e));} finally {setBusy("");}}}><ProcessIndicator active={busy === "retry"} startedAt={lastActivity === "retry" ? startedAt : null} label="Retrying screening"/>Retry unfinished screening</button>}
      <section className="r-panel r-cohort"><div className="r-table-toolbar"><div><h2>Candidate cohort <span>{cohortCandidates.length}</span></h2><p>{selectedIds.length} selected{search ? ` · ${filtered.length} match your search` : ""}</p></div><div className="r-search"><Search size={16}/><input placeholder="Search candidates or skills" aria-label="Search candidates" value={search} onChange={e => {setSearch(e.target.value); setPage(0);}}/></div></div>
        {!candidates.length ? <Empty title="Your cohort starts here">Upload CVs above, choose the job, then select candidates to rank.</Empty> : <div className="r-table-scroll"><table className="r-table"><thead><tr><th className="r-checkbox-cell"><input type="checkbox" aria-label="Select all matching candidates" checked={allSelected} onChange={() => setSelected(allSelected ? selected.filter(id => !filtered.some(c => c.id === id)) : [...new Set([...selected, ...filtered.map(c => c.id)])])}/></th><th>Candidate</th><th>Key skills</th><th>Experience</th><th>Pre-screen</th><th>Deep evaluation</th><th><span className="r-sr-only">Profile</span></th></tr></thead><tbody>{visible.map(c => {const row = ranked.get(c.id); return <tr key={c.id} className={selected.includes(c.id) ? "selected" : ""}><td><input type="checkbox" aria-label={`Select ${c.masked_name}`} checked={selected.includes(c.id)} onChange={() => setSelected(selected.includes(c.id) ? selected.filter(id => id !== c.id) : [...selected, c.id])}/></td><td><div className="r-candidate-cell"><span className="r-avatar">{row ? String(row.rank).padStart(2,"0") : c.masked_name?.slice(0,1) || "C"}</span><div><strong>{c.masked_name || `Candidate ${c.id.slice(0,8)}`}</strong><small>{row ? `Rank ${row.rank}${row.pipeline_version === "v2" ? ` · ${row.essential_supported}/${row.essential_total} required supported${row.reranked ? " · reranked" : ""}` : ""}` : "Ready to screen"}</small></div></div></td><td><div className="r-tags">{c.skills.slice(0,2).map((s,i) => <span key={i}>{s}</span>)}{c.skills.length > 2 && <span title={c.skills.slice(2).join(", ")}>+{c.skills.length - 2}</span>}</div></td><td>{c.total_years_experience != null ? `${c.total_years_experience.toFixed(1)} years` : "Not stated"}</td><td>{row ? <span className="r-score">{row.pre_screen_score.toFixed(1)}<small>/100</small></span> : <span className="r-muted">Not ranked</span>}</td><td>{row?.deep_status === "completed" ? <span className="r-pill success">{row.deep_evaluation!.overall_score.toFixed(1)} / 100</span> : <span className={`r-pill ${row?.deep_status === "failed" ? "warning" : ""}`} title={row?.error || undefined}>{row?.deep_status === "pending" ? "Evaluating…" : row?.deep_status === "failed" ? "Failed — open profile" : "Pre-screen only"}</span>}</td><td><button className="r-icon-button" aria-label={`View ${c.masked_name} profile and scores`} onClick={() => setProfileId(c.id)}><ChevronRight size={18}/></button></td></tr>;})}</tbody></table>{!visible.length && <Empty title="No matching candidates">Try another name or skill.</Empty>}</div>}
        <div className="r-table-footer"><span>{filtered.length ? `${currentPage * 25 + 1}–${Math.min((currentPage + 1) * 25, filtered.length)} of ${filtered.length} candidates` : "0 candidates"}</span><div><button className="r-icon-button" aria-label="Previous page" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={17}/></button><button className="r-icon-button" aria-label="Next page" disabled={currentPage >= maxPage} onClick={() => setPage(currentPage + 1)}><ChevronRight size={17}/></button></div></div>
      </section>
    </>}
    {profileId && <ProfileDialog id={profileId} row={ranked.get(profileId)} onClose={() => setProfileId("")}/>}
  </>;
}
