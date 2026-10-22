/** Per-tab task ownership and request cancellation; saved recruiting data is untouched. */
let fallbackId = "";
let resetting = false;
const controllers = new Set<AbortController>();

export function workspaceId(): string {
  if (typeof window === "undefined") return "";
  try {
    let id = sessionStorage.getItem("atos_workspace_id");
    if (!id) {id = crypto.randomUUID(); sessionStorage.setItem("atos_workspace_id", id);}
    return id;
  } catch {
    if (!fallbackId) fallbackId = crypto.randomUUID();
    return fallbackId;
  }
}

export function registerWorkspaceRequest(controller: AbortController, endpoint: string) {
  if (resetting && endpoint !== "/api/v1/processes/reset") throw new DOMException("Process cancelled by workspace reset", "AbortError");
  controllers.add(controller);
  return () => {controllers.delete(controller);};
}

export function beginWorkspaceReset() {resetting = true;}
export function finishWorkspaceReset(success: boolean) {
  if (success) for (const controller of controllers) controller.abort(new DOMException("Process cancelled by workspace reset", "AbortError"));
  resetting = false;
}

export function freshWorkspaceAfter(): number {
  try {return Number(sessionStorage.getItem("atos_recruiter_reset_at")) || 0;} catch {return 0;}
}

export function clearWorkspaceSession() {
  try {
    sessionStorage.removeItem("atos_recruiter_batch");
    sessionStorage.setItem("atos_recruiter_reset_at", String(Date.now()));
  } catch { /* The current mounted workspace will still be reset. */ }
  window.history.replaceState(null, "", `${window.location.pathname}?step=jobs`);
}
