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
    const jsonStr = typeof data === "string" ? data : JSON.stringify(data, null, 2);
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
