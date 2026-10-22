"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLiveParsingUpdates } from "@/lib/parsing-batch";
import { api } from "@/lib/api";
import { emptyProcesses, processSnapshot, subscribeProcesses } from "@/lib/processes";
import { ProcessIndicator } from "./process-indicator";
import { message } from "./common";

export function ActiveProcesses() {
  useLiveParsingUpdates();
  const requests = useSyncExternalStore(subscribeProcesses, processSnapshot, emptyProcesses);
  const cache = useQueryClient();
  const jobs = useQuery({queryKey: ["active-processes"], queryFn: () => api.activeProcesses(), refetchInterval: 2000});
  const previous = useRef<string[]>([]);
  useEffect(() => {
    if (!jobs.data) return;
    const current = jobs.data.map(job => job.id);
    if (previous.current.some(id => !current.includes(id))) {
      for (const queryKey of [["recruiter-candidates"], ["cv-library"], ["recruiter-run"], ["recruiter-run-history"]]) void cache.invalidateQueries({queryKey});
    }
    previous.current = current;
  }, [jobs.data, cache]);
  const [cancelling, setCancelling] = useState<string[]>([]);
  const [error, setError] = useState("");
  const processes = [...requests, ...(jobs.data || []).map(job => ({...job, cancel: async () => {await api.cancelBackgroundProcess(job.id);}}))];
  if (!processes.length && !error) return null;
  return <section className="r-active-processes" aria-label="Active processes">
    {error && <div className="r-alert" role="alert">{error}<button onClick={() => setError("")}>Dismiss</button></div>}
    {processes.map(process => <div key={process.id} className="r-active-process">
      <span><ProcessIndicator active timer={false} label={process.label}/>{process.label}</span>
      <button type="button" className="r-button" disabled={cancelling.includes(process.id)} onClick={async () => {
        setCancelling(current => [...current, process.id]); setError("");
        try {await process.cancel(); await cache.invalidateQueries();}
        catch (e) {setError(message(e));}
        finally {setCancelling(current => current.filter(id => id !== process.id));}
      }}>{cancelling.includes(process.id) ? "Cancelling…" : "Cancel"}</button>
    </div>)}
    <small>Completed steps are kept. A model call already running may finish before its resources are released.</small>
  </section>;
}
