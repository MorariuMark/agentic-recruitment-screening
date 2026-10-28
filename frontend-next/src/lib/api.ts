import { workspaceId, registerWorkspaceRequest } from "./workspace-session";
import { trackProcess } from "./processes";
/**
 * Unified API Client for FastAPI Backend Services
 */

import {
  WorkspaceStatistics,
  CohortStatistics,
  OperationStatistics,
  ScreeningRun,
  BatchJobStatus,
  CandidateComparisonReport,
  CandidateDetail,
  CandidateSummary,
  ComplianceDossier,
  CVUploadResponse,
  InterviewPlan,
  JobDescription,
  JobRecommendationResponse,
  JobRequirement,
  LLMSettings,
  LocalModelScanResult,
  MatchEvaluationResult,
  RequirementMatch,
  TokenUsageAnalytics,
  ActionTraceResponse,
} from "@/types";

export interface ActiveProgressState {
  task_key: string;
  active: boolean;
  label: string;
  phase: string;
  completed_steps: number;
  total_steps: number;
  percentage: number;
  completed_items: string[];
  token_usage?: any;
}

const getApiBase = (): string => {
  if (typeof window !== "undefined") return "";
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, "");
  }
  if (typeof window !== "undefined") {
    // In the browser, always use relative base ("") so requests go to the same origin (Next.js server),
    // which reliably proxies /api/* and /health to FastAPI via next.config.ts rewrites with ZERO CORS/PNA issues.
    return "";
  }
  // Server-side (SSR / Node.js) default to direct local backend
  return "http://127.0.0.1:8000";
};

const API_BASE = getApiBase();

export class AuthenticationError extends Error {
  name = "AuthenticationError";
}

let _savedAuthToken: string | null = null;
if (typeof window !== "undefined") {
  try {
    _savedAuthToken = sessionStorage.getItem("atos_token");
  } catch {}
}

class ApiClient {
  private base: string;

  constructor(base: string = API_BASE) {
    this.base = base.replace(/\/+$/, "");
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit & { timeoutMs?: number; preferDirectBackend?: boolean; sameOrigin?: boolean; responseType?: "json" | "text" } = {}
  ): Promise<T> {
    const { timeoutMs = 60000, preferDirectBackend = false, sameOrigin = false, responseType = "json", ...fetchOptions } = options;
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    // Determine primary URL and fallback URL:
    // If preferDirectBackend is set (e.g. for multi-second LLM workflows like match/evaluate),
    // start directly with loopback http://127.0.0.1:8000 to avoid Next.js dev server rewrite proxy socket timeouts.
    let primaryUrl = `${this.base}${endpoint}`;
    let fallbackUrl = this.base ? endpoint : `http://127.0.0.1:8000${endpoint}`;
    // Workspace cookies must belong to the frontend host even when the configured
    // API URL uses 127.0.0.1 and the user opened the frontend through localhost.
    if (sameOrigin && typeof window !== "undefined") {
      primaryUrl = endpoint;
      fallbackUrl = endpoint;
    }
    if (preferDirectBackend && !sameOrigin) {
      primaryUrl = `http://127.0.0.1:8000${endpoint}`;
      fallbackUrl = endpoint;
    }

    const executeFetch = async (targetUrl: string): Promise<T> => {
      const controller = new AbortController();
      const unregister = registerWorkspaceRequest(controller, endpoint);
      const tabId = workspaceId();
      const processId = crypto.randomUUID();
      const method = (fetchOptions.method || "GET").toUpperCase();
      const longRead = /recommended-jobs|compliance\/dossier|settings\/local-models|ollama\/(models|hardware)/.test(endpoint);
      const tracked = (method !== "GET" || longRead) && !endpoint.includes("/auth/") && !endpoint.includes("/cancel") && !endpoint.includes("/processes/");
      const finishProcess = tracked ? trackProcess(processId, endpoint, async () => {
        const response = await fetch(`${this.base}/api/v1/processes/${processId}/cancel`, {method: "POST", credentials: "include", headers: {"X-Workspace-ID": tabId}});
        if (!response.ok) throw new Error("Cancellation failed. Try again.");
        controller.abort(new DOMException("Process cancelled. Completed steps are retained.", "AbortError"));
      }) : () => {};
      let timedOut = false;
      const timeoutId = setTimeout(() => {
        timedOut = true;
        controller.abort(
          typeof DOMException !== "undefined"
            ? new DOMException(`Request to ${targetUrl} timed out after ${timeoutMs}ms`, "TimeoutError")
            : new Error(`Request to ${targetUrl} timed out after ${timeoutMs}ms`)
        );
      }, timeoutMs);

      // Propagate caller signal to timeout controller if supplied
      if (fetchOptions.signal) {
        if (fetchOptions.signal.aborted) {
          const reason =
            fetchOptions.signal.reason ||
            (typeof DOMException !== "undefined"
              ? new DOMException("Request cancelled by caller", "AbortError")
              : new Error("Request cancelled by caller"));
          controller.abort(reason);
        } else {
          fetchOptions.signal.addEventListener(
            "abort",
            () => {
              const reason =
                fetchOptions.signal?.reason ||
                (typeof DOMException !== "undefined"
                  ? new DOMException("Request cancelled by caller", "AbortError")
                  : new Error("Request cancelled by caller"));
              controller.abort(reason);
            },
            { once: true }
          );
        }
      }

      try {
        const res = await fetch(targetUrl, {
          credentials: "include",
          ...fetchOptions,
          signal: controller.signal,
          headers: (() => {
            const requestHeaders = new Headers(headers);
            if (tabId) requestHeaders.set("X-Workspace-ID", tabId);
            if (tracked) requestHeaders.set("X-Process-ID", processId);
            if (_savedAuthToken && !requestHeaders.has("Authorization")) {
              requestHeaders.set("Authorization", `Bearer ${_savedAuthToken}`);
            }
            return requestHeaders;
          })(),
        });

        if (!res.ok) {
          let errorDetail = `HTTP ${res.status} ${res.statusText}`;
          try {
            const contentType = res.headers.get("content-type") || "";
            if (contentType.includes("application/json")) {
              const errorJson = await res.json();
              if (Array.isArray(errorJson.detail)) {
                errorDetail = errorJson.detail
                  .map((d: any) => (typeof d === "string" ? d : d.msg || d.message || JSON.stringify(d)))
                  .join("; ");
              } else if (typeof errorJson.detail === "object" && errorJson.detail !== null) {
                errorDetail = JSON.stringify(errorJson.detail);
              } else {
                errorDetail = errorJson.detail || errorJson.message || errorDetail;
              }
            } else {
              const errorText = await res.text();
              if (errorText) {
                const snippet = errorText.replace(/<[^>]+>/g, " ").trim().slice(0, 160);
                if (snippet) errorDetail = `${errorDetail}: ${snippet}`;
              }
            }
          } catch {
            // fallback to status text
          }
          if (res.status === 401 && !endpoint.includes("/auth/")) {
            if (typeof window !== "undefined") window.dispatchEvent(new Event("atos-session-expired"));
            throw new AuthenticationError(errorDetail);
          }
          throw new Error(errorDetail);
        }

        return responseType === "text" ? await res.text() as T : res.json();
      } catch (err: any) {
        if (timedOut) {
          const timeoutErr = new Error(`Request to ${targetUrl} timed out after ${timeoutMs}ms`);
          timeoutErr.name = "TimeoutError";
          throw timeoutErr;
        }
        throw err;
      } finally {
        clearTimeout(timeoutId);
        finishProcess();
        unregister();
      }
    };

    try {
      return await executeFetch(primaryUrl);
    } catch (primaryErr: any) {
      if (fetchOptions.signal?.aborted || primaryErr?.name === "AbortError" || primaryErr?.name === "TimeoutError") {
        throw primaryErr;
      }

      const isNetworkError =
        primaryErr instanceof TypeError ||
        primaryErr?.name === "TypeError" ||
        (typeof primaryErr?.message === "string" &&
          (primaryErr.message.includes("Failed to fetch") ||
            primaryErr.message.includes("NetworkError") ||
            primaryErr.message.includes("fetch failed") ||
            primaryErr.message.includes("network")));

      const isProxyOrGatewayError =
        typeof primaryErr?.message === "string" &&
        (primaryErr.message.includes("500 Internal Server Error: Internal Server Error") ||
          primaryErr.message.includes("HTTP 502") ||
          primaryErr.message.includes("HTTP 504") ||
          primaryErr.message.includes("socket hang up") ||
          primaryErr.message.includes("ECONNRESET") ||
          primaryErr.message.includes("Failed to proxy"));

      if ((isNetworkError || isProxyOrGatewayError) && primaryUrl !== fallbackUrl && typeof window !== "undefined") {
        console.warn(`[ApiClient] Request to ${primaryUrl} encountered proxy/network failure (${primaryErr.message}); seamlessly retrying via fallback ${fallbackUrl}...`);
        return await executeFetch(fallbackUrl);
      }
      throw primaryErr;
    }
  }

  resetWorkspace(): Promise<{status: string}> {return this.request("/api/v1/processes/reset", {method: "POST", timeoutMs: 180000});}
  cvLibrary(): Promise<CVDocument[]> {return this.request("/api/v1/cv-library");}
  cvDocumentText(id: string): Promise<{id: string; filename: string; text: string}> {
    return this.request(`/api/v1/cv-library/${encodeURIComponent(id)}/text`);
  }
  importCVs(files: File[]): Promise<{imported: number; duplicates_removed: number}> {
    const body = new FormData(); files.forEach(file => body.append("files", file));
    return this.request("/api/v1/cv-library/import", {method: "POST", body, timeoutMs: 180000});
  }
  libraryAction(ids: string[], action: "trash" | "restore" | "delete"): Promise<{changed: number}> {
    return this.request("/api/v1/cv-library/actions", {method: "POST", body: JSON.stringify({ids, action}), timeoutMs: 180000});
  }
  prepareCVs(ids: string[], limit = 25, concurrency = 4): Promise<{batch_id: string; total_files: number; remaining_unparsed: number}> {
    return this.request("/api/v1/cv-library/prepare", {method: "POST", body: JSON.stringify({ids, limit, concurrency})});
  }
  activeProcesses(): Promise<{id: string; label: string}[]> {return this.request("/api/v1/processes");}
  cancelBackgroundProcess(id: string): Promise<unknown> {
    const [kind, key] = id.split(":");
    return this.request(`/api/v1/screening/${kind === "run" ? "runs" : "batches"}/${key}/cancel`, {method: "POST"});
  }

  // Health
  async login(role: "admin" | "user", password: string): Promise<{role: "admin" | "user"; token?: string}> {
    const res = await this.request<{role: "admin" | "user"; token?: string}>("/api/v1/auth/login", {method: "POST", body: JSON.stringify({role, password}), sameOrigin: true});
    if (res?.token) {
      _savedAuthToken = res.token;
      try { sessionStorage.setItem("atos_token", res.token); } catch {}
    }
    return res;
  }
  async parseRecruiterJob(text: string): Promise<{job_description: JobDescription}> {
    return this.request("/api/v1/screening/jobs/parse", {method: "POST", body: JSON.stringify({text}), timeoutMs: 180000});
  }
  async parseRecruiterJobUrl(url: string): Promise<{job_description: JobDescription}> {
    return this.request("/api/v1/screening/jobs/parse-url", {method: "POST", body: JSON.stringify({url}), timeoutMs: 180000});
  }
  async recruiterStatistics(): Promise<WorkspaceStatistics> {
    return this.request("/api/v1/screening/statistics");
  }

  async operationStatistics(options: {days?: number; operation?: string; job_id?: string; batch_id?: string; run_id?: string; offset?: number} = {}): Promise<OperationStatistics> {
    const params = new URLSearchParams({limit: "25"});
    Object.entries(options).forEach(([key, value]) => {if (value !== undefined && value !== "") params.set(key, String(value));});
    return this.request(`/api/v1/screening/statistics/actions?${params}`);
  }

  async cohortStatistics(jobId: string, days: number, offset: number): Promise<CohortStatistics> {
    const params = new URLSearchParams({days: String(days), offset: String(offset)});
    if (jobId) params.set("job_id", jobId);
    return this.request(`/api/v1/screening/statistics/cohorts?${params}`);
  }

  async recruiterModels(): Promise<Pick<LLMSettings, "active_provider" | "active_model" | "providers_catalog" | "fallback_enabled"> & { parallel_screening_enabled?: boolean; cooldown_statuses?: Record<string, any> }> {
    return this.request("/api/v1/screening/models");
  }
  async refreshRecruiterLocalModels(): Promise<Awaited<ReturnType<ApiClient["recruiterModels"]>> & { local_discovery: { ollama: {running: boolean; models_count: number}; lmstudio: {running: boolean; live_models_count: number; disk_models_count: number} } }> {
    return this.request("/api/v1/screening/models/refresh-local", {method: "POST"});
  }
  async selectRecruiterModel(provider: string, model: string): Promise<Pick<LLMSettings, "active_provider" | "active_model" | "providers_catalog" | "fallback_enabled"> & { parallel_screening_enabled?: boolean; cooldown_statuses?: Record<string, any> }> {
    return this.request("/api/v1/screening/models", {method: "POST", body: JSON.stringify({provider, model})});
  }
  async toggleRecruiterFailover(enabled: boolean): Promise<Pick<LLMSettings, "active_provider" | "active_model" | "providers_catalog" | "fallback_enabled"> & { parallel_screening_enabled?: boolean; cooldown_statuses?: Record<string, any> }> {
    return this.request("/api/v1/screening/failover", {method: "POST", body: JSON.stringify({enabled})});
  }
  async toggleRecruiterParallel(enabled: boolean): Promise<Pick<LLMSettings, "active_provider" | "active_model" | "providers_catalog" | "fallback_enabled"> & { parallel_screening_enabled?: boolean; cooldown_statuses?: Record<string, any> }> {
    return this.request("/api/v1/screening/parallel-toggle", {method: "POST", body: JSON.stringify({enabled})});
  }
  async session(): Promise<{role: "admin" | "user" | null; token?: string}> {
    const res = await this.request<{role: "admin" | "user" | null; token?: string}>("/api/v1/auth/session", {sameOrigin: true});
    if (res?.token) {
      _savedAuthToken = res.token;
      try { sessionStorage.setItem("atos_token", res.token); } catch {}
    }
    return res;
  }
  async logout(): Promise<void> {
    _savedAuthToken = null;
    try { sessionStorage.removeItem("atos_token"); } catch {}
    await this.request("/api/v1/auth/logout", {method: "POST", sameOrigin: true});
  }
  async uploadCohort(files: File[]): Promise<{batch_id: string}> {
    const body = new FormData(); files.forEach(file => body.append("files", file));
    return this.request("/api/v1/screening/cohort/upload", {method: "POST", body, timeoutMs: 600000});
  }
  async fastRank(jobId: string, candidateIds: string[], topK: number, deepEvaluation: boolean, options: {pipeline_version?: "v1" | "v2"; rerank_enabled?: boolean; rerank_pool_size?: number; include_benchmark?: boolean} = {}): Promise<ScreeningRun> {
    return this.request("/api/v1/screening/rank", {method: "POST", body: JSON.stringify({job_id: jobId, candidate_ids: candidateIds, top_k: topK, deep_evaluation: deepEvaluation, ...options})});
  }
  async deepEvaluateSelected(id: string, candidateIds: string[]): Promise<ScreeningRun> {return this.request(`/api/v1/screening/runs/${id}/evaluate`, {method: "POST", body: JSON.stringify({candidate_ids: candidateIds})});}
  async retryScreeningRun(id: string): Promise<ScreeningRun> {return this.request(`/api/v1/screening/runs/${id}/retry`, {method: "POST"});}
  async screeningRun(id: string, jobId?: string): Promise<ScreeningRun> {
    const run = await this.request<ScreeningRun>(`/api/v1/screening/runs/${id}${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`);
    if (jobId && run.job_id !== jobId) throw new Error("This run belongs to another job. Load the latest run for this role.");
    return run;
  }
  async latestScreeningRun(jobId: string): Promise<ScreeningRun | null> { return this.request(`/api/v1/screening/jobs/${jobId}/latest`); }
  async jobScreeningRuns(jobId: string): Promise<Array<{id: string; job_id: string; status: string; created_at: string; pipeline_version?: string; total_candidates: number; ranked_candidates: number; deep_completed: number}>> {
    return this.request(`/api/v1/screening/jobs/${jobId}/runs`);
  }
  async shortlist(id: string, count: number, candidateIds?: string[]): Promise<ScreeningRun> {
    return this.request(`/api/v1/screening/runs/${id}/shortlist`, {method: "POST", body: JSON.stringify({count, candidate_ids: candidateIds})});
  }
  async reviewCandidate(id: string, candidateId: string, decision: "interview" | "hold" | "reject", notes: string): Promise<ScreeningRun> {
    return this.request(`/api/v1/screening/runs/${id}/decisions/${candidateId}`, {method: "POST", body: JSON.stringify({decision, notes})});
  }
  async recruiterInterview(id: string, candidateId: string, duration: number): Promise<InterviewPlan> {
    return this.request(`/api/v1/screening/runs/${id}/interview`, {
      method: "POST",
      body: JSON.stringify({candidate_id: candidateId, duration_minutes: duration}),
      timeoutMs: 600000,
      preferDirectBackend: true,
    });
  }

  async getHealth(): Promise<{ status: string; active_llm_provider: string; active_model: string }> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort(
        typeof DOMException !== "undefined"
          ? new DOMException("Health check timed out after 8000ms", "TimeoutError")
          : new Error("Health check timed out after 8000ms")
      );
    }, 8000);
    try {
      return await this.request("/health", { signal: controller.signal, timeoutMs: 8000 });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // Requisitions & Jobs
  async getJobs(limit: number = 50): Promise<JobDescription[]> {
    return this.request(`/api/v1/jobs?limit=${limit}`);
  }

  async parseJobText(text: string, signal?: AbortSignal): Promise<{ job_description: JobDescription }> {
    return this.request("/api/v1/job/parse-text", {
      method: "POST",
      body: JSON.stringify({ text }),
      timeoutMs: 120000,
      signal,
    });
  }

  async parseJobUrl(url: string, signal?: AbortSignal): Promise<{ job_description: JobDescription }> {
    return this.request("/api/v1/job/parse-url", {
      method: "POST",
      body: JSON.stringify({ url }),
      timeoutMs: 120000,
      signal,
    });
  }

  async getJobEvaluations(jobId: string): Promise<MatchEvaluationResult[]> {
    return this.request(`/api/v1/jobs/${jobId}/evaluations`);
  }

  async createJob(job: JobDescription): Promise<JobDescription> {
    return this.request("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify(job),
    });
  }

  async updateJobRequirements(jobId: string, requirements: JobRequirement[]): Promise<JobDescription> {
    return this.request(`/api/v1/jobs/${jobId}/requirements`, {
      method: "PUT",
      body: JSON.stringify({ requirements }),
    });
  }

  // Candidates & Batch
  async getCandidates(limit: number = 100, offset: number = 0, signal?: AbortSignal): Promise<CandidateSummary[]> {
    return this.request(`/api/v1/candidates?limit=${limit}&offset=${offset}`, {signal});
  }

  async getCandidate(candidateId: string): Promise<CandidateDetail> {
    return this.request(`/api/v1/candidates/${candidateId}`);
  }

  async deleteCandidate(candidateId: string): Promise<{ status: string; candidate_id: string; message: string }> {
    return this.request(`/api/v1/candidates/${candidateId}`, {
      method: "DELETE",
    });
  }

  async exportCandidateCV(candidateId: string): Promise<any> {
    return this.request(`/api/v1/cv/${candidateId}/export`);
  }

  async getRecommendedJobs(
    candidateId: string,
    limit: number = 10,
    signal?: AbortSignal,
    excludeJobId?: string
  ): Promise<JobRecommendationResponse> {
    const url = excludeJobId
      ? `/api/v1/candidates/${candidateId}/recommended-jobs?limit=${limit}&exclude_job_id=${encodeURIComponent(excludeJobId)}`
      : `/api/v1/candidates/${candidateId}/recommended-jobs?limit=${limit}`;
    return this.request(url, {
      signal,
    });
  }

  async uploadSingleCV(file: File, signal?: AbortSignal): Promise<CVUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    return this.request<CVUploadResponse>("/api/v1/cv/upload", {
      method: "POST",
      body: formData,
      timeoutMs: 600000,
      signal,
    });
  }

  async uploadBatchCVs(files: File[], jobId?: string, signal?: AbortSignal): Promise<{ batch_id: string; total_files: number; status: string; message: string }> {
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }
    if (jobId) {
      formData.append("job_id", jobId);
    }
    return this.request("/api/v1/cv/batch-upload", {
      method: "POST",
      body: formData,
      timeoutMs: 600000,
      signal,
    });
  }

  async getBatchStatus(batchId: string): Promise<BatchJobStatus> {
    return this.request(`/api/v1/cv/batch/${batchId}`);
  }

  createBatchSSEStream(
    batchId: string,
    onMessage: (event: string, data: any) => void,
    onError?: (err: any) => void
  ): () => void {
    const url = `${this.base}/api/v1/cv/batch/${batchId}/stream`;
    const eventSource = new EventSource(url);

    const eventNames = [
      "initial_state",
      "batch_started",
      "file_processing",
      "file_completed",
      "batch_completed",
      "complete",
    ];

    eventNames.forEach((name) => {
      eventSource.addEventListener(name, (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          onMessage(name, parsed);
          if (name === "batch_completed" || name === "complete") {
            eventSource.close();
          }
        } catch {
          onMessage(name, e.data);
        }
      });
    });

    eventSource.onerror = (err) => {
      if (onError) onError(err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }

  // Matching & Citations & Live Progress
  async getActiveProgress(taskKey?: string): Promise<ActiveProgressState | null> {
    try {
      const q = taskKey ? `?task_key=${encodeURIComponent(taskKey)}` : "";
      return await this.request(`/api/v1/progress/active${q}`, { timeoutMs: 4000 });
    } catch {
      return null;
    }
  }

  async evaluateCandidate(
    candidateId: string,
    jobDescription: JobDescription,
    signal?: AbortSignal,
    strictness: number = 50
  ): Promise<MatchEvaluationResult> {
    return this.request("/api/v1/match/evaluate", {
      method: "POST",
      body: JSON.stringify({
        candidate_id: candidateId,
        job_description: jobDescription,
        strictness: Math.max(0, Math.min(100, Math.round(strictness))),
      }),
      timeoutMs: 180000,
      preferDirectBackend: true,
      signal,
    });
  }

  async getEvaluation(evaluationId: string): Promise<MatchEvaluationResult> {
    return this.request(`/api/v1/evaluation/${evaluationId}`);
  }

  async submitHITLDecision(
    evaluationId: string,
    recruiterDecision: "strong_match" | "borderline" | "reject",
    recruiterNotes: string,
    updatedMatches?: RequirementMatch[]
  ): Promise<MatchEvaluationResult> {
    return this.request("/api/v1/hitl/validate", {
      method: "POST",
      body: JSON.stringify({
        evaluation_id: evaluationId,
        recruiter_decision: recruiterDecision,
        recruiter_notes: recruiterNotes,
        updated_matches: updatedMatches,
      }),
    });
  }

  async previewHITLCorrections(evaluationId: string, updatedMatches: RequirementMatch[]): Promise<MatchEvaluationResult> {
    return this.request("/api/v1/hitl/preview", {
      method: "POST",
      body: JSON.stringify({evaluation_id: evaluationId, updated_matches: updatedMatches}),
    });
  }

  // Multi-Candidate Comparison Matrix
  async compareCandidates(
    candidateIds: string[],
    jobId: string,
    signal?: AbortSignal
  ): Promise<CandidateComparisonReport> {
    return this.request("/api/v1/match/compare", {
      method: "POST",
      body: JSON.stringify({
        candidate_ids: candidateIds,
        job_id: jobId,
      }),
      timeoutMs: 180000,
      preferDirectBackend: true,
      signal,
    });
  }

  async exportJobDescription(job: JobDescription): Promise<any> {
    return this.request("/api/v1/job/export", {
      method: "POST",
      body: JSON.stringify(job),
      headers: { "Content-Type": "application/json" },
    });
  }

  // Interview Studio
  async generateInterviewPlan(
    candidateId: string,
    evaluationId: string,
    jobDescription: JobDescription,
    targetDurationMinutes: number = 45,
    signal?: AbortSignal
  ): Promise<InterviewPlan> {
    return this.request("/api/v1/interview/generate", {
      method: "POST",
      body: JSON.stringify({
        candidate_id: candidateId,
        evaluation_id: evaluationId,
        job_description: jobDescription,
        target_duration_minutes: targetDurationMinutes,
      }),
      timeoutMs: 180000,
      preferDirectBackend: true,
      signal,
    });
  }

  async getInterviewPlan(planId: string): Promise<InterviewPlan> {
    return this.request(`/api/v1/interview/${planId}`);
  }

  // Compliance & Governance (EU AI Act Annex III)
  async getComplianceDossier(evaluationId: string, signal?: AbortSignal): Promise<ComplianceDossier> {
    return this.request(`/api/v1/compliance/dossier/${evaluationId}?format=json`, {
      timeoutMs: 120000,
      signal,
    });
  }

  async getComplianceDossierMarkdown(evaluationId: string): Promise<string> {
    return this.request(`/api/v1/compliance/dossier/${evaluationId}?format=markdown`, {responseType: "text", timeoutMs: 120000});
  }

  // Settings
  async getLLMSettings(): Promise<LLMSettings> {
    return this.request("/api/v1/settings/llm");
  }

  async updateLLMSettings(data: {
    provider: string;
    model: string;
    compatibility_mode?: string;
    api_key?: string;
    base_url?: string;
    local_context_window?: number;
    local_rolling_context?: boolean;
    local_thinking_enabled?: boolean;
    fallback_enabled?: boolean;
  }): Promise<LLMSettings> {
    return this.request("/api/v1/settings/llm", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async toggleFailover(enabled: boolean): Promise<LLMSettings> {
    return this.request("/api/v1/settings/llm/fallback-toggle", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  }

  async toggleParallelScreening(enabled: boolean): Promise<LLMSettings> {
    return this.request("/api/v1/settings/llm/parallel-toggle", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  }

  async loadOllamaModel(model: string, keep_alive: string = "1h"): Promise<any> {
    return this.request("/api/v1/ollama/load", {
      method: "POST",
      body: JSON.stringify({ model, keep_alive }),
    });
  }

  async unloadOllamaModel(model: string): Promise<any> {
    return this.request("/api/v1/ollama/unload", {
      method: "POST",
      body: JSON.stringify({ model, keep_alive: "0" }),
    });
  }

  async getOllamaModels(): Promise<{ installed: any[]; running: any[]; hardware?: any }> {
    return this.request("/api/v1/ollama/models");
  }

  async getHardwareProfile(): Promise<any> {
    return this.request("/api/v1/ollama/hardware");
  }

  async scanLocalModels(
    autoImportToOllama: boolean = false,
    force: boolean = true
  ): Promise<LocalModelScanResult> {
    return this.request("/api/v1/settings/local-models/scan", {
      method: "POST",
      body: JSON.stringify({
        auto_import_to_ollama: autoImportToOllama,
        force: force,
      }),
    });
  }

  async getLocalModels(force: boolean = false): Promise<LocalModelScanResult> {
    return this.request(`/api/v1/settings/local-models?force=${force}`);
  }

  async importLocalModelToOllama(fullPath: string, modelTag: string): Promise<any> {
    return this.request("/api/v1/settings/local-models/import", {
      method: "POST",
      body: JSON.stringify({
        full_path: fullPath,
        model_tag: modelTag,
      }),
    });
  }

  async saveFallbackChain(
    chain: Array<{ provider: string; model: string }>
  ): Promise<LLMSettings> {
    return this.request("/api/v1/settings/llm/fallback-chain", {
      method: "POST",
      body: JSON.stringify({ chain }),
    });
  }

  async resetFallbackChain(): Promise<LLMSettings> {
    return this.request("/api/v1/settings/llm/fallback-chain/reset", {
      method: "POST",
    });
  }

  async clearFallbackEvent(): Promise<{ status: string; message: string }> {
    return this.request("/api/v1/settings/llm/clear-fallback", {
      method: "POST",
    });
  }

  async testLLMConnectivity(data: {
    provider: string;
    model: string;
    api_key?: string;
  }): Promise<{
    status: string;
    provider: string;
    model: string;
    latency_ms: number;
    sample_output?: string;
    error_message?: string;
  }> {
    return this.request("/api/v1/settings/llm/test", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async getTokenUsageAnalytics(
    timeRange: "today" | "7d" | "30d" | "month" | "all" = "all"
  ): Promise<TokenUsageAnalytics> {
    return this.request(`/api/v1/analytics/token-usage?time_range=${timeRange}`);
  }

  async resetTokenUsage(): Promise<{ status: string; message: string }> {
    return this.request("/api/v1/analytics/token-usage/reset", {
      method: "POST",
    });
  }

  async actionTrace(jobId?: string, runId?: string): Promise<ActionTraceResponse> {
    const params = new URLSearchParams();
    if (jobId) params.append("job_id", jobId);
    if (runId) params.append("run_id", runId);
    const q = params.toString() ? `?${params.toString()}` : "";
    return this.request(`/api/v1/screening/action-trace${q}`);
  }

  async getLiveLLMLogs(limit: number = 50): Promise<LiveLLMState> {
    return this.request(`/api/v1/screening/llm/live-logs?limit=${limit}`);
  }

  async clearLiveLLMLogs(): Promise<{ status: string }> {
    return this.request("/api/v1/screening/llm/live-logs/clear", { method: "POST" });
  }

  async getLocalModelsStatus(): Promise<LocalModelFullState> {
    return this.request("/api/v1/screening/local-models/status");
  }

  async loadLocalModel(params: LocalModelLoadParams): Promise<any> {
    return this.request("/api/v1/screening/local-models/load", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  async unloadLocalModel(params: LocalModelUnloadParams): Promise<any> {
    return this.request("/api/v1/screening/local-models/unload", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  async startLocalServer(port: number = 1234): Promise<any> {
    return this.request("/api/v1/screening/local-models/start-server", {
      method: "POST",
      body: JSON.stringify({ provider: "lmstudio", port }),
    });
  }
}


export const api = new ApiClient();

export interface HardwareProfile {
  tier: "low" | "medium" | "high" | "ultra";
  tier_label: string;
  recommended_context_window: number;
  recommended_max_tokens: number;
  recommended_gpu_layers: number;
  recommended_model_size_max_gb: number;
  safe_models_description: string;
  warning?: string | null;
  is_low_end: boolean;
}

export interface GPUTelemetry {
  available: boolean;
  is_dedicated_gpu?: boolean;
  name: string;
  total_vram_mb: number;
  used_vram_mb: number;
  free_vram_mb: number;
  utilization_percent: number;
  used_vram_gb: number;
  total_vram_gb: number;
  free_vram_gb: number;
  profile?: HardwareProfile;
}

export interface LocalCatalogModel {
  id: string;
  name: string;
  size_gb?: number;
  is_4gb_friendly?: boolean;
}

export interface LocalLoadedModel {
  identifier?: string;
  model?: string;
  status?: string;
  size?: string;
  size_vram_mb?: number;
  context_length?: string;
  expires_at?: string;
}

export interface LocalEngineStatus {
  available: boolean;
  base_url: string;
  current_model: string;
  models: LocalCatalogModel[];
  loaded_models: LocalLoadedModel[];
  context_window: number;
  rolling_context: boolean;
  gpu_layers: number;
}

export interface LocalModelFullState {
  gpu: GPUTelemetry;
  hardware_profile?: HardwareProfile;
  lmstudio: LocalEngineStatus;
  ollama: LocalEngineStatus;
  active_provider: string;
  context_window: number;
  rolling_context: boolean;
  gpu_layers: number;
}

export interface LocalModelLoadParams {
  provider: "lmstudio" | "ollama";
  model: string;
  context_window?: number;
  gpu_layers?: number;
  gpu_offload_mode?: "auto" | "max" | "off";
  set_as_active?: boolean;
}

export interface LocalModelUnloadParams {
  provider: "lmstudio" | "ollama";
  model?: string;
}

export interface LiveLLMInFlightEntry {
  prompt_tokens?: number;
  id: string;
  timestamp: string;
  elapsed_seconds: number;
  action_type: string;
  provider: string;
  model: string;
  prompt: string;
  system_prompt?: string | null;
  metadata?: Record<string, any>;
  status: string;
}

export interface LiveLLMRecentEntry {
  id: string;
  timestamp: string;
  action_type: string;
  provider: string;
  model: string;
  status: "success" | "failover" | "error" | "cooling_down";
  latency_ms: number;
  tokens_per_second?: number;
  tokens: {
    prompt: number;
    completion: number;
    total: number;
    tokens_per_second?: number;
  };
  prompt: string;
  system_prompt?: string | null;
  raw_response?: string;
  parsed_json?: any;
  error?: string | null;
  metadata?: Record<string, any>;
}

export interface LiveLLMState {
  in_flight: LiveLLMInFlightEntry[];
  recent: LiveLLMRecentEntry[];
  total_logged: number;
}

export interface CVDocument {
  id: string; filename: string; candidate_id: string | null; size: number | null;
  content_hash: string | null; created_at: string; deleted_at: string | null; expires_at: string | null;
}
