"use client";

import {useEffect, useRef, useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {Download, RefreshCw, X} from "lucide-react";
import {api} from "@/lib/api";
import {OperationTiming} from "@/types";
import {message} from "./common";

const names: Record<string, string> = {
  cv_parse: "CV parsing", batch_parse: "CV batch parsing", batch_screening: "Batch parsing and screening",
  screening_run: "Job screening", candidate_screening: "Candidate evaluation", ranking: "Candidate ranking",
  job_extraction: "Job description extraction", interview_generation: "Interview generation",
  candidate_comparison: "Candidate comparison", cv_import: "CV library import",
  shortlist_creation: "Comparison shortlist", recruiter_review: "Recruiter decision",
  cv_processing: "CV parsing and evaluation",
};
const number = (value: number) => value.toLocaleString(undefined, {maximumFractionDigits: 1});
function duration(ms: number | null | undefined) {
  if (ms == null) return "Not measured";
  if (ms < 1000) return `${Math.round(Math.max(0, ms))} ms`;
  const seconds = Math.max(0, ms / 1000);
  if (seconds < 60) return `${number(seconds)} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m`;
}
function exportPage(rows: OperationTiming[]) {
  const fields: Array<keyof OperationTiming> = ["id", "operation", "label", "status", "started_at", "finished_at", "duration_ms", "item_count", "completed_count", "failed_count", "cached", "batch_id", "job_id", "run_id", "candidate_id", "parent_id"];
  const cell = (value: unknown) => {
    const text = value == null ? "" : String(value);
    return `"${(/^[=+@-]/.test(text.trimStart()) ? "'" + text : text).replaceAll('"', '""')}"`;
  };
  const csv = [fields.join(","), ...rows.map(row => fields.map(key => cell(row[key])).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob(["\ufeff", csv], {type: "text/csv;charset=utf-8"}));
  const link = document.createElement("a"); link.href = url; link.download = "action-statistics-page.csv"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function StatisticsDialog({onClose}: {onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [days, setDays] = useState(0);
  const [operation, setOperation] = useState("");
  const [jobId, setJobId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [runId, setRunId] = useState("");
  const [offset, setOffset] = useState(0);
  const [cohortOffset, setCohortOffset] = useState(0);
  const cohorts = useQuery({queryKey: ["cohort-statistics", jobId, days, cohortOffset], queryFn: () => api.cohortStatistics(jobId, days, cohortOffset), refetchInterval: 5000});
  const [now, setNow] = useState(Date.now);
  const stats = useQuery({queryKey: ["recruiter-statistics"], queryFn: () => api.recruiterStatistics(), refetchInterval: 10000});
  const jobs = useQuery({queryKey: ["recruiter-jobs"], queryFn: () => api.getJobs(1000)});
  const actions = useQuery({queryKey: ["operation-statistics", days, operation, jobId, batchId, runId, offset],
    queryFn: () => api.operationStatistics({days, operation, job_id: jobId, batch_id: batchId, run_id: runId, offset}), refetchInterval: 5000});
  useEffect(() => {
    const element = dialog.current; element?.showModal();
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => {element?.close(); clearInterval(interval);};
  }, []);
  const summary = actions.data?.summary || [];
  const history = actions.data?.history || [];
  const data = stats.data;
  const refresh = () => {void actions.refetch(); void stats.refetch(); void cohorts.refetch();};
  const clearScope = () => {setBatchId(""); setRunId(""); setOperation(""); setOffset(0);};
  const focus = (row: OperationTiming) => {
    setOffset(0);
    if (row.batch_id) {setBatchId(row.batch_id); setRunId(""); setOperation(row.operation === "batch_screening" ? "cv_processing" : "cv_parse");}
    else if (row.run_id) {setRunId(row.run_id); setBatchId(""); setOperation("candidate_screening");}
  };

  return <dialog ref={dialog} className="recruiter r-profile-dialog r-statistics-dialog" aria-labelledby="statistics-title" onClose={() => {if (!dialog.current?.open) onClose();}}>
    <header><div><span className="r-muted">Saved performance history</span><h2 id="statistics-title">Statistics</h2></div><div className="r-statistics-actions">
      <button className="r-icon-button" aria-label="Refresh statistics" disabled={actions.isFetching || stats.isFetching} onClick={refresh}><RefreshCw size={17}/></button>
      <button className="r-icon-button" aria-label="Close statistics" onClick={onClose}><X size={20}/></button>
    </div></header>
    <div className="r-profile-content">
      <section aria-labelledby="performance-title">
        <div className="r-statistics-heading"><h3 id="performance-title">Action performance</h3><small>Saved across sessions · refreshes every 5 seconds</small></div>
        <div className="r-statistics-filters">
          <label className="r-field">Time period<select value={days} onChange={e => {setDays(Number(e.target.value)); setCohortOffset(0); setOffset(0);}}><option value={0}>All time</option><option value={1}>Last 24 hours</option><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select></label>
          <label className="r-field">Action<select value={operation} onChange={e => {setOperation(e.target.value); setOffset(0);}}><option value="">All actions</option>{Object.entries(names).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label className="r-field">Job<select value={jobId} onChange={e => {setJobId(e.target.value); setCohortOffset(0); setBatchId(""); setRunId(""); setOffset(0);}}><option value="">All jobs</option>{jobs.data?.map(job => <option key={job.id} value={job.id}>{job.title}</option>)}</select></label>
        </div>
        {(batchId || runId) && <p className="r-statistics-scope">{batchId ? `Batch ${batchId}` : `Screening run ${runId}`}<button className="r-button subtle" onClick={clearScope}>Clear batch/run filter</button></p>}
        {actions.isPending && <p role="status">Loading saved timings...</p>}
        {actions.error && <p className="r-alert" role="alert">{message(actions.error)} <button onClick={() => void actions.refetch()}>Retry</button></p>}
        <div className="r-statistics-grid">{[["CV parsing", "cv_parse"], ["CV batch", "batch_parse"], ["Job screening", "screening_run"], ["Candidate evaluation", "candidate_screening"]].map(([label, key]) => {
          const item = summary.find(row => row.operation === key);
          return <div key={key}><small>{label} · average</small><strong>{duration(item?.average_ms)}</strong><small>{item ? `${number(item.completed - item.cached)} successful actions · ${number(item.failed + item.partial)} with errors` : "No samples in this view"}</small></div>;
        })}</div>
        <p className="r-statistics-footnote">Averages and throughput use successful, uncached actions. Failed, cancelled and reused CVs stay in history. Batch and screening durations are actual elapsed time, including queue waits; per-CV duration begins when a worker starts processing. Parent and child times overlap and must not be added together.</p>
        {!!summary.length && <div className="r-statistics-history r-statistics-wide"><table><caption className="r-sr-only">Action duration and reliability KPIs</caption><thead><tr><th>Action</th><th>Attempts</th><th>Success</th><th>Average</th><th>Total elapsed</th><th>Items completed</th><th>Fastest / slowest</th><th>Items / minute</th><th>Errors / cancelled</th></tr></thead><tbody>{summary.map(item => <tr key={item.operation}><td>{item.label}<small>{item.running} running · {item.cached} reused · {item.deferred} deferred · {item.interrupted} interrupted</small></td><td>{number(item.count)}</td><td>{item.success_rate == null ? "—" : `${number(item.success_rate)}%`}</td><td>{duration(item.average_ms)}</td><td>{duration(item.total_ms)}</td><td>{number(item.items)}</td><td>{duration(item.min_ms)} / {duration(item.max_ms)}</td><td>{item.items_per_minute == null ? "—" : number(item.items_per_minute)}</td><td>{item.failed + item.partial} / {item.cancelled}</td></tr>)}</tbody></table></div>}
      </section>

      <section aria-labelledby="cohort-statistics-title">
        <div className="r-statistics-heading"><h3 id="cohort-statistics-title">Cohort screening statistics</h3><small>Filtered by job and time period above � includes retries</small></div>
        <p className="r-statistics-footnote">Each row tracks one job screening. Total elapsed includes pre-screening, deep evaluation and queue waits across attempts. Deep evaluation covers the selected candidates; compare evaluated and cohort counts. Tokens include recorded model calls across retries. Unavailable historical measurements are shown explicitly.</p>
        {cohorts.isPending && <p role="status">Loading cohort statistics...</p>}
        {cohorts.error && <p role="alert" className="r-alert">{message(cohorts.error)} <button onClick={() => void cohorts.refetch()}>Retry</button></p>}
        {cohorts.data && !cohorts.data.history.length && <p className="r-inline-empty">No screening runs match this job and time period.</p>}
        {!!cohorts.data?.history.length && <div className="r-statistics-history r-statistics-wide"><table><caption className="r-sr-only">Screening time and token usage per cohort</caption><thead><tr><th>Job / screening run</th><th>Status</th><th>Candidates</th><th>Pre-screening</th><th>Deep evaluation</th><th>Total elapsed</th><th>Input tokens</th><th>Output tokens</th><th>Total tokens</th></tr></thead><tbody>{cohorts.data.history.map(row => <tr key={row.run_id}>
          <td>{row.job_title}<small>{row.run_id}</small><small>{row.started_at ? new Date(row.started_at).toLocaleString() : "Start unavailable"}</small><button className="r-button subtle" onClick={() => {setRunId(row.run_id); setBatchId(""); setOperation(""); setOffset(0);}}>View run actions</button></td>
          <td>{row.status}</td><td>{number(row.candidate_count)} screened<small>{number(row.evaluated_count)} deep evaluated</small></td>
          <td>{duration(row.pre_screening_ms)}</td><td>{duration(row.deep_evaluation_ms)}</td><td>{duration(row.total_ms)}</td>
          <td>{row.tokens ? number(row.tokens.input) : "Not recorded"}</td><td>{row.tokens ? number(row.tokens.output) : "Not recorded"}</td><td>{row.tokens ? number(row.tokens.total) : "Not recorded"}<small>{row.model_calls} recorded calls</small></td>
        </tr>)}</tbody></table></div>}
        <div className="r-table-footer"><span>{number(cohorts.data?.total || 0)} screening runs</span><div><button className="r-button subtle" disabled={!cohortOffset || cohorts.isFetching} onClick={() => setCohortOffset(value => Math.max(0, value - 25))}>Previous</button><button className="r-button subtle" disabled={!cohorts.data?.has_more || cohorts.isFetching} onClick={() => setCohortOffset(value => value + 25)}>Next</button></div></div>
      </section>

      <section aria-labelledby="action-history-title">
        <div className="r-statistics-heading"><h3 id="action-history-title">Saved action history</h3><button className="r-button subtle" disabled={!history.length} onClick={() => exportPage(history)}><Download size={14}/>Export this page</button></div>
        {!actions.isPending && !actions.error && !history.length && <p className="r-inline-empty">No measured actions match these filters. Parse CVs, screen a job, extract a job description or generate an interview to start collecting timings. Historical actions without reliable timings are not estimated.</p>}
        {!!history.length && <div className="r-statistics-history r-statistics-wide"><table><caption className="r-sr-only">Per-action, per-CV and per-batch durations</caption><thead><tr><th>Action / CV</th><th>Status</th><th>Elapsed</th><th>Items</th><th>Started</th><th>Details</th></tr></thead><tbody>{history.map(row => <tr key={row.id}>
          <td>{row.label}<small>{names[row.operation] || row.operation}{row.cached ? " · Reused profile" : ""}</small>{row.job_id && <small>{jobs.data?.find(job => job.id === row.job_id)?.title || `Job ${row.job_id.slice(0, 8)}`}</small>}</td>
          <td><span className={`r-pill ${row.status === "completed" ? "success" : row.status === "failed" || row.status === "partial" ? "warning" : ""}`}>{row.status}</span></td>
          <td>{duration(row.status === "running" ? now - Date.parse(row.started_at) : row.duration_ms)}</td>
          <td>{row.completed_count}/{row.item_count}<small>{row.failed_count ? `${row.failed_count} failed` : "completed"}</small></td>
          <td>{new Date(row.started_at).toLocaleString()}</td>
          <td>{["batch_parse", "batch_screening", "screening_run"].includes(row.operation) && <button className="r-button subtle" onClick={() => focus(row)}>{row.batch_id ? "View CV timings" : "View candidate timings"}</button>}<details><summary>Identifiers</summary><small>Action: {row.id}</small>{row.batch_id && <small>Batch: {row.batch_id}</small>}{row.run_id && <small>Run: {row.run_id}</small>}{row.candidate_id && <small>Candidate: {row.candidate_id}</small>}</details></td>
        </tr>)}</tbody></table></div>}
        <div className="r-table-footer"><span>{actions.data?.total ? `${offset + 1}–${offset + history.length} of ${number(actions.data.total)} actions` : "0 actions"}</span><div><button className="r-button subtle" disabled={offset === 0 || actions.isFetching} onClick={() => setOffset(value => Math.max(0, value - 25))}>Previous</button><button className="r-button subtle" disabled={!actions.data?.has_more || actions.isFetching} onClick={() => setOffset(value => value + 25)}>Next</button></div></div>
      </section>

      <section aria-labelledby="data-statistics-title"><div className="r-statistics-heading"><h3 id="data-statistics-title">Platform totals</h3><small>All time · independent of filters above</small></div>
        {stats.error && <p role="alert">{message(stats.error)}</p>}
        {data && <><div className="r-statistics-grid">{[["CVs stored", data.candidates], ["Jobs", data.jobs], ["Screening runs", data.screening_runs], ["Deep evaluations", data.evaluations], ["Interview plans", data.interview_plans], ["Batch files processed", data.batch_processed], ["Batch files failed", data.batch_failed]].map(([label, value]) => <div key={label}><small>{label}</small><strong>{number(Number(value))}</strong></div>)}</div>
          {!!data.cv_parsing?.sample_count && <p className="r-statistics-footnote">Historical batch file measurements: {duration(data.cv_parsing.average_ms)} average across {number(data.cv_parsing.sample_count)} successful, uncached CVs. These older measurements remain available; new actions appear in the history above.</p>}
          <details className="r-profile-section"><summary>Model usage · current backend session</summary><p>{number(data.model_calls)} calls · {number(data.tokens)} tokens · {duration(data.model_duration_ms)} model time · {duration(data.model_average_ms)} average per call. Model calls are components of actions; these times overlap the action history.</p></details>
        </>}
      </section>
    </div>
  </dialog>;
}
