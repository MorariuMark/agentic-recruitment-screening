"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

const listeners = new Set<() => void>();
let memoryId = "";
const readBatch = () => {
  try {return sessionStorage.getItem("atos_recruiter_batch") || "";} catch {return memoryId;}
};
const subscribe = (listener: () => void) => {listeners.add(listener); return () => {listeners.delete(listener);};};

export function setParsingBatch(id: string) {
  memoryId = id;
  try {if (id) sessionStorage.setItem("atos_recruiter_batch", id); else sessionStorage.removeItem("atos_recruiter_batch");} catch { /* In-memory progress stays available. */ }
  listeners.forEach(listener => listener());
}

export function useParsingBatch(poll = false) {
  const batchId = useSyncExternalStore(subscribe, readBatch, () => "");
  const batch = useQuery({queryKey: ["recruiter-batch", batchId], queryFn: () => api.getBatchStatus(batchId), enabled: !!batchId,
    staleTime: Infinity, refetchOnMount: false, refetchOnWindowFocus: false, refetchOnReconnect: false,
    refetchInterval: query => poll && ["PROCESSING", "QUEUED"].includes(query.state.data?.status || "PROCESSING") ? 1000 : false});
  return {batchId, batch, setBatchId: setParsingBatch};
}

/** One polling owner per workspace; every file completion refreshes both views. */
export function useLiveParsingUpdates() {
  const {batchId, batch} = useParsingBatch(true);
  const cache = useQueryClient();
  const previous = useRef("");
  useEffect(() => {
    if (!batch.data) return;
    const key = `${batchId}:${batch.data.processed_files}:${batch.data.failed_files}:${batch.data.status}`;
    if (key === previous.current) return;
    previous.current = key;
    if (batch.data.processed_files || batch.data.status !== "PROCESSING") {
      void cache.invalidateQueries({queryKey: ["recruiter-candidates"]});
      void cache.invalidateQueries({queryKey: ["cv-library"]});
    }
  }, [batchId, batch.data, cache]);
}
