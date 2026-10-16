"use client";

import {useEffect, useRef, useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {RefreshCw, X} from "lucide-react";
import {api} from "@/lib/api";
import {message} from "./common";
import {ProcessIndicator, useProcessTimings} from "./process-indicator";

const number = (value: number) => value.toLocaleString();
function duration(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function StatisticsDialog({onClose}: {onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const timings = useProcessTimings();
  const [now, setNow] = useState(Date.now);
  const stats = useQuery({queryKey: ["recruiter-statistics"], queryFn: () => api.recruiterStatistics(), refetchInterval: 5000});
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => {element?.close(); clearInterval(interval);};
  }, []);
  const completed = timings.filter(item => item.endedAt !== null);
  const total = completed.reduce((sum, item) => sum + Math.max(0, item.endedAt! - item.startedAt), 0);
  const data = stats.data;
  return <dialog ref={dialog} className="recruiter r-profile-dialog r-statistics-dialog" aria-labelledby="statistics-title" onClose={() => {if (!dialog.current?.open) onClose();}}>
    <header><div><span className="r-muted">Workspace overview</span><h2 id="statistics-title">Statistics</h2></div><div className="r-statistics-actions"><button className="r-icon-button" aria-label="Refresh statistics" disabled={stats.isFetching} onClick={() => void stats.refetch()}><RefreshCw size={17} className={stats.isFetching ? "r-spinner" : ""}/></button><button className="r-icon-button" aria-label="Close statistics" onClick={onClose}><X size={20}/></button></div></header>
    <div className="r-profile-content">
      <section aria-labelledby="timer-statistics-title"><div className="r-statistics-heading"><h3 id="timer-statistics-title">Process timers</h3><small>This workspace session · latest 200 actions</small></div>
        <div className="r-statistics-grid">{[["Running", number(timings.length - completed.length)], ["Finished", number(completed.length)], ["Cumulative process time", duration(total)], ["Average duration", completed.length ? duration(total / completed.length) : "—"]].map(([label,value]) => <div key={label}><small>{label}</small><strong>{value}</strong></div>)}</div>
        {!timings.length ? <p className="r-inline-empty">Durations appear here when you extract a role, parse CVs, rank candidates or prepare questions. They remain in this session’s history when you reset the visible timers.</p> : <div className="r-statistics-history"><table><caption className="r-sr-only">Recent process durations</caption><thead><tr><th>Process</th><th>Status</th><th>Duration</th></tr></thead><tbody>{[...timings].reverse().map(item => <tr key={item.id}><td>{item.label}<small>{new Date(item.startedAt).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}</small></td><td>{item.endedAt === null ? "Running" : "Finished"}</td><td>{duration((item.endedAt ?? now) - item.startedAt)}</td></tr>)}</tbody></table></div>}
      </section>
      <section aria-labelledby="data-statistics-title"><div className="r-statistics-heading"><h3 id="data-statistics-title">Data processed</h3><small>Shared platform totals · refreshes every 5 seconds</small></div>
        {stats.isPending && <p role="status"><ProcessIndicator active timer={false} track={false}/> Loading statistics…</p>}
        {stats.error && <p className="r-alert" role="alert">{message(stats.error)} <button onClick={() => void stats.refetch()}>Retry</button></p>}
        {data && <><div className="r-statistics-grid">{[["CVs stored", data.candidates], ["Job descriptions", data.jobs], ["Screening runs", data.screening_runs], ["Deep evaluations", data.evaluations], ["Interview plans", data.interview_plans], ["CV text characters", data.cv_text_characters], ["Batch files submitted", data.batch_files], ["Batch files processed", data.batch_processed], ["Batch files failed", data.batch_failed]].map(([label,value]) => <div key={label}><small>{label}</small><strong>{number(Number(value))}</strong></div>)}</div>
          <h3 className="r-statistics-model-heading">Model usage · current backend session</h3><div className="r-statistics-grid"><div><small>Recorded model calls</small><strong>{number(data.model_calls)}</strong></div><div><small>Tokens processed</small><strong>{number(data.tokens)}</strong></div><div><small>Total model time</small><strong>{duration(data.model_duration_ms)}</strong></div><div><small>Average model time</small><strong>{duration(data.model_average_ms)}</strong></div></div><p className="r-statistics-footnote">Recorded model time: {duration(data.model_duration_ms)} total · {duration(data.model_average_ms)} average per call. CV text counts anonymized characters, not file bytes. Batch counts cover cohort uploads; CV totals also include single uploads.</p></>}
      </section>
    </div>
  </dialog>;
}
