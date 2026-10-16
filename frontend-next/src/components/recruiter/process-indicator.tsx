"use client";

import { createContext, useCallback, useContext, useEffect, useId, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { LoaderCircle } from "lucide-react";

export interface ProcessTiming {id: string; label: string; startedAt: number; endedAt: number | null;}
const ActivityContext = createContext<{active: boolean; update: (id: string, active: boolean) => void; resetAt: number; resetTimers: () => void; timings: ProcessTiming[]; report: (id: string, label: string, startedAt: number, active: boolean) => void}>({active: false, update: () => {}, resetAt: 0, resetTimers: () => {}, timings: [], report: () => {}});

export function ActivityProvider({children}: {children: ReactNode}) {
  const [activities, setActivities] = useState<Set<string>>(() => new Set());
  const [resetAt, setResetAt] = useState(0);
  const [timings, setTimings] = useState<ProcessTiming[]>([]);
  const report = useCallback((id: string, label: string, startedAt: number, active: boolean) => {
    setTimings(current => {
      const key = `${id}:${startedAt}`;
      const previous = current.find(item => item.id === key);
      if (previous && (active ? previous.endedAt === null : previous.endedAt !== null)) return current;
      const item = {id: key, label, startedAt, endedAt: active ? null : Date.now()};
      return [...current.filter(entry => entry.id !== key && !(entry.id.startsWith(`${id}:`) && entry.endedAt === null)), item].slice(-200);
    });
  }, []);
  const resetTimers = useCallback(() => setResetAt(Date.now()), []);
  const update = useCallback((id: string, active: boolean) => {
    setActivities(current => {
      if (current.has(id) === active) return current;
      const next = new Set(current);
      if (active) next.add(id); else next.delete(id);
      return next;
    });
  }, []);
  const value = useMemo(() => ({active: activities.size > 0, update, resetAt, resetTimers, timings, report}), [activities, update, resetAt, resetTimers, timings, report]);
  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>;
}

export function useWorkspaceActivity() {return useContext(ActivityContext).active;}
export function useResetTimers() {return useContext(ActivityContext).resetTimers;}
export function useProcessTimings() {return useContext(ActivityContext).timings;}

/** Small local feedback that stays alive with its workspace panel during navigation. */
export function useTimedActivity<T extends string | boolean>(initial: T) {
  const [busy, updateBusy] = useState(initial);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [lastActivity, setLastActivity] = useState(initial);
  const setBusy = useCallback((value: T) => {
    if (value) {setStartedAt(Date.now()); setLastActivity(value);}
    updateBusy(value);
  }, []);
  return [busy, setBusy, startedAt, lastActivity] as const;
}

export function ProcessIndicator({active, startedAt, timer = true, label = "Processing", track = true}: {
  active: boolean;
  startedAt?: number | null;
  timer?: boolean;
  label?: string;
  track?: boolean;
}) {
  const id = useId();
  const {update, resetAt, report} = useContext(ActivityContext);
  useEffect(() => {
    if (track && timer && startedAt) report(id, label, startedAt, active);
  }, [active, id, label, report, startedAt, timer, track]);
  useEffect(() => {
    if (!track || !active) return;
    update(id, true);
    return () => update(id, false);
  }, [active, id, track, update]);
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!timer || !startedAt) return;
    // Capture the final wall-clock duration once, then stop updating it.
    const finalTick = setTimeout(() => setNow(Date.now()), 0);
    const interval = active ? setInterval(() => setNow(Date.now()), 1000) : null;
    return () => {clearTimeout(finalTick); if (interval) clearInterval(interval);};
  }, [active, startedAt, timer]);
  if (!active && (!timer || !startedAt || startedAt <= resetAt)) return null;
  const elapsed = startedAt ? Math.max(0, Math.floor(((now ?? startedAt) - startedAt) / 1000)) : 0;
  const formatted = `${Math.floor(elapsed / 60).toString().padStart(2, "0")}:${(elapsed % 60).toString().padStart(2, "0")}`;
  return <span className="r-process-indicator" role="status" aria-label={active ? label : `${label} finished in ${formatted}`}>
    {active && <LoaderCircle className="r-spinner" size={15} aria-hidden="true"/>}
    {timer && startedAt != null && <span className="r-process-time" role="timer" aria-live="off" aria-label={`${active ? "Elapsed time" : "Total duration"} ${formatted}`}>{formatted}</span>}
  </span>;
}
