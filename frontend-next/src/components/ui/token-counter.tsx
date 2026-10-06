"use client";

import React, { useState, useEffect } from "react";
import { TokenUsageInfo } from "@/types";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Cpu,
  Flame,
  Gauge,
  Sparkles,
  Zap,
} from "lucide-react";

// Format numbers nicely (e.g., 1,420 or 1.2M)
export function formatTokens(num: number): string {
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(2)}M`;
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(1)}k`;
  }
  return num.toLocaleString();
}

interface TokenUsageBadgeProps {
  usage?: TokenUsageInfo | null;
  className?: string;
  showBreakdown?: boolean;
}

export function TokenUsageBadge({
  usage,
  className = "",
  showBreakdown = true,
}: TokenUsageBadgeProps) {
  if (!usage || usage.total_tokens <= 0) return null;

  const modelLabel = usage.display_name || usage.model || "AI Model";

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-slate-900/90 border border-slate-700/70 text-slate-200 text-xs shadow-sm ${className}`}
      title={`${modelLabel} | In: ${usage.prompt_tokens} | Out: ${usage.completion_tokens} | Total: ${usage.total_tokens} tokens`}
    >
      <div className="flex items-center gap-1.5 font-semibold text-blue-300">
        <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400/20" />
        <span className="truncate max-w-[130px]">{modelLabel}</span>
      </div>

      <div className="h-3 w-px bg-slate-700" />

      {showBreakdown ? (
        <div className="flex items-center gap-2 text-[11px] font-mono">
          <span className="text-slate-400 flex items-center gap-0.5" title="Input / Prompt Tokens">
            <ArrowDownLeft className="w-3 h-3 text-cyan-400" />
            <span>{usage.prompt_tokens.toLocaleString()} in</span>
          </span>
          <span className="text-slate-600">/</span>
          <span className="text-slate-400 flex items-center gap-0.5" title="Output / Completion Tokens">
            <ArrowUpRight className="w-3 h-3 text-emerald-400" />
            <span>{usage.completion_tokens.toLocaleString()} out</span>
          </span>
          <span className="text-slate-600">|</span>
          <span className="font-bold text-amber-300">
            {usage.total_tokens.toLocaleString()} tok
          </span>
        </div>
      ) : (
        <span className="font-mono font-bold text-amber-300 text-xs">
          {formatTokens(usage.total_tokens)} tokens
        </span>
      )}
    </div>
  );
}

interface LiveTokenCounterProps {
  isRunning: boolean;
  modelName?: string;
  provider?: string;
  completedUsage?: TokenUsageInfo | null;
  className?: string;
}

export function LiveTokenCounter({
  isRunning,
  modelName = "Active AI Model",
  provider = "default",
  completedUsage,
  className = "",
}: LiveTokenCounterProps) {
  const [estimatedTokens, setEstimatedTokens] = useState(0);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (isRunning) {
      setEstimatedTokens(120);
      interval = setInterval(() => {
        setEstimatedTokens((prev) => {
          // Incrementally stream tokens roughly corresponding to inference generation
          const step = Math.floor(Math.random() * 45) + 35;
          return prev + step;
        });
      }, 300);
    } else {
      setEstimatedTokens(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isRunning]);

  if (isRunning) {
    return (
      <div
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-blue-950/60 border border-blue-500/30 text-xs font-mono text-blue-200 animate-in fade-in ${className}`}
      >
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
        </span>
        <span className="font-sans font-medium text-slate-300">{modelName}:</span>
        <span className="font-bold text-amber-300 tabular-nums">
          ~{estimatedTokens.toLocaleString()} tokens streamed
        </span>
      </div>
    );
  }

  if (completedUsage && completedUsage.total_tokens > 0) {
    return <TokenUsageBadge usage={completedUsage} className={className} />;
  }

  return null;
}
