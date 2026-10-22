export interface ActiveProcess {id: string; label: string; cancel: () => Promise<void>}
const active = new Map<string, ActiveProcess>();
const listeners = new Set<() => void>();
let snapshot: ActiveProcess[] = [];
const emit = () => {snapshot = [...active.values()]; listeners.forEach(listener => listener());};
export const subscribeProcesses = (listener: () => void) => {listeners.add(listener); return () => {listeners.delete(listener);};};
export const processSnapshot = () => snapshot;
const empty: ActiveProcess[] = [];
export const emptyProcesses = () => empty;

function processLabel(endpoint: string) {
  if (endpoint.includes("local-models")) return "Scanning local models";
  if (endpoint.includes("ollama")) return "Updating local model";
  if (endpoint.includes("recommended-jobs")) return "Finding matching roles";
  if (endpoint.includes("compliance")) return "Generating compliance dossier";
  if (endpoint.includes("cv-library/import")) return "Importing CVs";
  if (endpoint.includes("cv-library/actions")) return "Updating CV library";
  if (endpoint.includes("cv-library/prepare")) return "Starting CV parsing";
  if (endpoint.includes("parse-url")) return "Extracting job from URL";
  if (endpoint.includes("jobs/parse")) return "Extracting job criteria";
  if (endpoint.includes("interview")) return "Preparing interview";
  if (endpoint.includes("upload")) return "Uploading and parsing CVs";
  if (endpoint.includes("rank") || endpoint.includes("retry") || endpoint.includes("evaluate")) return "Starting screening";
  return "Saving changes";
}

export function trackProcess(id: string, endpoint: string, cancel: () => Promise<void>) {
  active.set(id, {id, label: processLabel(endpoint), cancel}); emit();
  return () => {active.delete(id); emit();};
}

export function clearTrackedProcesses() {active.clear(); emit();}
