import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

export function formatScore(score: number): string {
  return score.toFixed(1);
}

export function getRecommendationBadge(rec: string): { label: string; className: string } {
  switch (rec?.toLowerCase()) {
    case "strong_match":
      return {
        label: "Strong Match",
        className: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
      };
    case "borderline":
      return {
        label: "Borderline",
        className: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
      };
    case "reject":
      return {
        label: "Reject",
        className: "bg-rose-500/10 text-rose-400 border border-rose-500/20",
      };
    default:
      return {
        label: "Pending",
        className: "bg-slate-500/10 text-slate-400 border border-slate-500/20",
      };
  }
}

export function downloadJsonFile(data: any, defaultFilename: string): void {
  try {
    if (typeof window === "undefined") return;

    let exportObj = data;
    if (data && typeof data === "object") {
      // Clone object to avoid mutating internal state
      exportObj = Array.isArray(data) ? [...data] : { ...data };

      if (!Array.isArray(exportObj)) {
        const meta = exportObj.audit_metadata || exportObj.parsed_cv?.audit_metadata;
        const rawText = exportObj.raw_text || exportObj.parsed_cv?.raw_text || "";
        const tokenUsage = exportObj.token_usage;

        const modelName =
          exportObj.model_name ||
          meta?.model_name ||
          tokenUsage?.model ||
          (typeof window !== "undefined" ? localStorage.getItem("atos_active_model") : null) ||
          "unknown";

        const tokensConsumed =
          exportObj.tokens_consumed ||
          meta?.tokens_consumed ||
          (tokenUsage
            ? {
                prompt_tokens: tokenUsage.prompt_tokens || 0,
                completion_tokens: tokenUsage.completion_tokens || 0,
                total_tokens: tokenUsage.total_tokens || 0,
              }
            : { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 });

        const durationMs =
          exportObj.duration_ms ??
          meta?.duration_ms ??
          tokenUsage?.latency_ms ??
          0.0;

        const durationSec =
          exportObj.duration_seconds ??
          meta?.duration_seconds ??
          Number((durationMs / 1000).toFixed(2));

        const durationStr =
          exportObj.duration ||
          (durationSec ? `${durationSec}s` : `${durationMs}ms`);

        const initialDocLength =
          exportObj.initial_document_text_length ??
          meta?.initial_document_text_length ??
          rawText.length ??
          0;

        exportObj.model_name = modelName;
        exportObj.tokens_consumed = tokensConsumed;
        exportObj.duration = durationStr;
        exportObj.duration_ms = durationMs;
        exportObj.initial_document_text_length = initialDocLength;

        if (!exportObj.audit_metadata) {
          exportObj.audit_metadata = {
            model_name: modelName,
            tokens_consumed: tokensConsumed,
            duration_ms: durationMs,
            duration_seconds: durationSec,
            initial_document_text_length: initialDocLength,
            action_timestamp: new Date().toISOString(),
          };
        }
      }
    }

    const jsonStr = typeof exportObj === "string" ? exportObj : JSON.stringify(exportObj, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = defaultFilename.endsWith(".json") ? defaultFilename : `${defaultFilename}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("Failed to download JSON file:", err);
  }
}
