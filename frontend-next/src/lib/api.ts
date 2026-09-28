/**
 * Unified API Client for FastAPI Backend Services
 */

import {
  BatchJobStatus,
  CandidateSummary,
  InterviewPlan,
  JobDescription,
  LLMSettings,
  MatchEvaluationResult,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

class ApiClient {
  private base: string;

  constructor(base: string = API_BASE) {
    this.base = base.replace(/\/+$/, "");
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.base}${endpoint}`;
    const headers = new Headers(options.headers || {});
    if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (!res.ok) {
      let errorDetail = `HTTP ${res.status} ${res.statusText}`;
      try {
        const errorJson = await res.json();
        errorDetail = errorJson.detail || errorDetail;
      } catch {
        // fallback to status text
      }
      throw new Error(errorDetail);
    }

    return res.json();
  }

  // Health
  async getHealth(): Promise<{ status: string; active_llm_provider: string; active_model: string }> {
    return this.request("/health");
  }

  // Requisitions & Jobs
  async getJobs(): Promise<JobDescription[]> {
    return this.request("/api/v1/jobs");
  }

  async parseJobText(text: string): Promise<{ job_description: JobDescription }> {
    return this.request("/api/v1/job/parse-text", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  }

  async parseJobUrl(url: string): Promise<{ job_description: JobDescription }> {
    return this.request("/api/v1/job/parse-url", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  }

  async getJobEvaluations(jobId: string): Promise<MatchEvaluationResult[]> {
    return this.request(`/api/v1/jobs/${jobId}/evaluations`);
  }

  // Candidates & Batch
  async getCandidates(): Promise<CandidateSummary[]> {
    return this.request("/api/v1/candidates");
  }

  async uploadSingleCV(file: File): Promise<any> {
    const formData = new FormData();
    formData.append("file", file);
    return this.request("/api/v1/cv/upload", {
      method: "POST",
      body: formData,
    });
  }

  async uploadBatchCVs(files: File[], jobId?: string): Promise<{ batch_id: string; total_files: number; status: string; message: string }> {
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
  async evaluateCandidate(candidateId: string, jobDescription: JobDescription): Promise<MatchEvaluationResult> {
    return this.request("/api/v1/match/evaluate", {
      method: "POST",
      body: JSON.stringify({
        candidate_id: candidateId,
        job_description: jobDescription,
      }),
    });
  }

  async getEvaluation(evaluationId: string): Promise<MatchEvaluationResult> {
    return this.request(`/api/v1/evaluation/${evaluationId}`);
  }

  async submitHITLDecision(
    evaluationId: string,
    recruiterDecision: "strong_match" | "borderline" | "reject",
    recruiterNotes: string
  ): Promise<MatchEvaluationResult> {
    return this.request("/api/v1/hitl/validate", {
      method: "POST",
      body: JSON.stringify({
        evaluation_id: evaluationId,
        recruiter_decision: recruiterDecision,
        recruiter_notes: recruiterNotes,
      }),
    });
  }

  // Interview Studio
  async generateInterviewPlan(
    candidateId: string,
    evaluationId: string,
    jobDescription: JobDescription,
    targetDurationMinutes: number = 45
  ): Promise<InterviewPlan> {
    return this.request("/api/v1/interview/generate", {
      method: "POST",
      body: JSON.stringify({
        candidate_id: candidateId,
        evaluation_id: evaluationId,
        job_description: jobDescription,
        target_duration_minutes: targetDurationMinutes,
      }),
    });
  }

  async getInterviewPlan(planId: string): Promise<InterviewPlan> {
    return this.request(`/api/v1/interview/${planId}`);
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
  }): Promise<{ status: string; active_provider: string; active_model: string }> {
    return this.request("/api/v1/settings/llm", {
      method: "POST",
      body: JSON.stringify(data),
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
}

export const api = new ApiClient();
