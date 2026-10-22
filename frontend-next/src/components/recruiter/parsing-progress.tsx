"use client";

import { useEffect, useState } from "react";
import { Check, Clock3, FileText, XCircle } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useParsingBatch } from "@/lib/parsing-batch";
import { ProcessIndicator } from "./process-indicator";
import { message } from "./common";

const labels: Record<string, string> = {QUEUED: "Queued", PROCESSING: "Processing", COMPLETED: "Parsed", FAILED: "Failed", CANCELLED: "Cancelled", INTERRUPTED: "Interrupted"};

function ParsingTimer({startedAt, finishedAt, active}: {startedAt?: string | null; finishedAt?: string | null; active: boolean}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [active]);
  if (!startedAt) return null;
  const start = Date.parse(startedAt);
  const end = finishedAt ? Date.parse(finishedAt) : active ? now : start;
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  const time = `${Math.floor(seconds / 3600).toString().padStart(2, "0")}:${Math.floor(seconds / 60 % 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
  return <span className="r-pill" aria-label={`Parsing elapsed time ${time}`} style={{fontVariantNumeric: "tabular-nums"}}><Clock3 size={15} aria-hidden="true"/> Elapsed {time}</span>;
}

export function ParsingProgress() {
  const {batchId, batch} = useParsingBatch();
  const cache = useQueryClient();
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  if (!batchId) return null;
  const data = batch.data;
  const active = !!data && ["PROCESSING", "QUEUED"].includes(data.status);
  const files = data?.files?.length ? data.files : (data?.results || []).map((file, index) => ({...file, id: String(index), phase: file.error || "Ready for verification"}));
  const processing = active ? files.filter(file => file.status === "PROCESSING") : [];
  const completed = (data?.processed_files || 0) + (data?.failed_files || 0);
  const available = new Set((data?.results || []).filter(file => file.status === "COMPLETED" && file.candidate_id).map(file => file.candidate_id)).size;
  const remaining = Math.max(0, (data?.total_files || 0) - completed);
  const priority = (status: string) => status === "PROCESSING" ? 0 : status === "FAILED" ? 1 : status === "COMPLETED" ? 2 : 3;
  const ordered = [...files].sort((a, b) => priority(a.status) - priority(b.status));
  return <section className="r-panel r-parsing-progress" aria-label="Live CV parsing progress">
    <div className="r-parsing-heading"><div><h2><FileText size={18} aria-hidden="true"/>CV parsing {active && <ProcessIndicator active timer={false} label="Parsing CV batch"/>}</h2><p aria-live="polite">{data ? `${data.processed_files} parsed · ${data.failed_files} failed · ${remaining} left · ${data.total_files} total` : "Loading batch progress..."}</p></div>
      {active && <button className="r-button" disabled={cancelling} onClick={async () => {
        setCancelling(true); setError("");
        try {await api.cancelBackgroundProcess(`batch:${batchId}`); await batch.refetch(); await cache.invalidateQueries({queryKey: ["active-processes"]});}
        catch (e) {setError(message(e));} finally {setCancelling(false);}
      }}>{cancelling ? "Cancelling..." : "Cancel parsing"}</button>}
      {data && !active && <span className="r-pill">{data.status === "COMPLETED" ? "Batch complete" : data.status === "PARTIAL" ? "Finished with errors" : labels[data.status] || data.status}</span>}
    </div>
    {(error || batch.error) && <div className="r-alert" role="alert">{error || message(batch.error)}<button onClick={() => batch.refetch()}>Retry progress</button></div>}
    {data && <><progress aria-label="CV batch completion" max={data.total_files || 1} value={completed}/>
      <div className="r-parsing-counts"><ParsingTimer startedAt={data.started_at} finishedAt={data.finished_at} active={active}/><span><Check size={15} aria-hidden="true"/>{available} profile{available !== 1 ? "s" : ""} available in CV verification</span><span>{processing.length} processing</span><span>{active ? data.queued_files ?? Math.max(0, remaining - processing.length) : 0} queued</span><span>Up to {data.concurrency_limit || 4} at once</span></div>
      {active && <div className="r-parsing-current" aria-live="polite"><strong>Currently processing</strong>{processing.length ? processing.map(file => <p key={file.id}><ProcessIndicator active timer={false} track={false} label={`Processing ${file.filename}`}/><span>{file.filename}</span><small>{file.phase}</small></p>) : <p>Waiting for a parsing slot...</p>}</div>}
      {!active && remaining > 0 && <p className="r-muted">{remaining} CV(s) were not completed. Select unparsed CVs in the library to start another batch.</p>}
      <details className="r-parsing-files" open><summary>Files in this batch ({files.length})</summary><div className="r-parsing-file-list">{ordered.map(file => <div className="r-parsing-file" key={file.id}>
        <span>{file.status === "COMPLETED" ? <Check size={15} aria-hidden="true"/> : file.status === "FAILED" ? <XCircle size={15} aria-hidden="true"/> : <Clock3 size={15} aria-hidden="true"/>}<strong>{file.filename}</strong></span>
        <span className={`r-pill ${file.status === "COMPLETED" ? "success" : file.status === "FAILED" ? "warning" : ""}`}>{labels[file.status] || file.status}</span>
        <small>{file.error || file.phase}</small>
      </div>)}</div></details>
    </>}
  </section>;
}
