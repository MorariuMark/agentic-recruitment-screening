/**
 * Unified API Client for FastAPI Backend Services
 */

import {
  BatchJobStatus,
  CandidateComparisonReport,
  CandidateDetail,
  CandidateSummary,
  ComplianceDossier,
  CVUploadResponse,
  InterviewPlan,
  JobDescription,
  JobRequirement,
  LLMSettings,
  MatchEvaluationResult,
  RequirementMatch,
  TokenUsageAnalytics,
} from "@/types";

const getApiBase = (): string => {
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

class ApiClient {
  private base: string;

  constructor(base: string = API_BASE) {
    this.base = base.replace(/\/+$/, "");
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit & { timeoutMs?: number } = {}
  ): Promise<T> {
    const { timeoutMs = 60000, ...fetchOptions } = options;
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    // Determine primary URL and fallback URL:
    // Primary: relative path in browser ("") or configured base
    // Fallback: direct loopback http://127.0.0.1:8000 if primary is relative, or relative if primary was direct
    const primaryUrl = `${this.base}${endpoint}`;
    const fallbackUrl = this.base ? endpoint : `http://127.0.0.1:8000${endpoint}`;

    const executeFetch = async (targetUrl: string): Promise<T> => {
      const controller = new AbortController();
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
          ...fetchOptions,
          signal: controller.signal,
          headers,
        });

        if (!res.ok) {
          let errorDetail = `HTTP ${res.status} ${res.statusText}`;
          try {
            const contentType = res.headers.get("content-type") || "";
            if (contentType.includes("application/json")) {
              const errorJson = await res.json();
              errorDetail = errorJson.detail || errorJson.message || errorDetail;
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
          throw new Error(errorDetail);
        }

        return res.json();
      } catch (err: any) {
        if (timedOut) {
          const timeoutErr = new Error(`Request to ${targetUrl} timed out after ${timeoutMs}ms`);
          timeoutErr.name = "TimeoutError";
          throw timeoutErr;
        }
        throw err;
      } finally {
        clearTimeout(timeoutId);
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

      if (isNetworkError && primaryUrl !== fallbackUrl && typeof window !== "undefined") {
        console.warn(`[ApiClient] Request to ${primaryUrl} failed with network error; seamlessly retrying via fallback ${fallbackUrl}...`);
        return await executeFetch(fallbackUrl);
      }
      throw primaryErr;
    }
  }

  // Health
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
  async getJobs(): Promise<JobDescription[]> {
    return this.request("/api/v1/jobs");
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
  async getCandidates(limit: number = 1000): Promise<CandidateSummary[]> {
    return this.request(`/api/v1/candidates?limit=${limit}`);
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

  // Matching & Citations
  async evaluateCandidate(candidateId: string, jobDescription: JobDescription, signal?: AbortSignal): Promise<MatchEvaluationResult> {
    return this.request("/api/v1/match/evaluate", {
      method: "POST",
      body: JSON.stringify({
        candidate_id: candidateId,
        job_description: jobDescription,
      }),
      timeoutMs: 180000,
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
    const endpoint = `/api/v1/compliance/dossier/${evaluationId}?format=markdown`;
    const primaryUrl = `${this.base}${endpoint}`;
    const fallbackUrl = this.base ? endpoint : `http://127.0.0.1:8000${endpoint}`;

    try {
      const res = await fetch(primaryUrl);
      if (!res.ok) {
        throw new Error(`Failed to fetch compliance markdown: ${res.statusText}`);
      }
      return res.text();
    } catch (err) {
      if (primaryUrl !== fallbackUrl && typeof window !== "undefined") {
        const res = await fetch(fallbackUrl);
        if (!res.ok) {
          throw new Error(`Failed to fetch compliance markdown: ${res.statusText}`);
        }
        return res.text();
      }
      throw err;
    }
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
}


export const api = new ApiClient();
