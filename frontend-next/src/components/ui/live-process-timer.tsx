"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { Timer, Clock, XCircle, CheckCircle2, Square, Loader2, Zap, Sparkles } from "lucide-react";

export interface UseProcessTimerReturn {
  isRunning: boolean;
  elapsedSeconds: number;
  completedDuration: number | null;
  startTimer: () => AbortController;
  stopTimer: (success?: boolean) => number | null;
  cancelTimer: () => void;
  resetTimer: () => void;
  getAbortSignal: () => AbortSignal | undefined;
  abortController: AbortController | null;
  formattedElapsed: string;
  formattedDuration: string | null;
}

export function useProcessTimer(): UseProcessTimerReturn {
  const [isRunning, setIsRunning] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [completedDuration, setCompletedDuration] = useState<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const startTimer = useCallback(() => {
    // Clear any previous interval
    if (intervalRef.current) clearInterval(intervalRef.current);
    
    // Create fresh AbortController
    const controller = new AbortController();
    abortControllerRef.current = controller;

    startTimeRef.current = performance.now();
    setElapsedSeconds(0);
    setCompletedDuration(null);
    setIsRunning(true);

    intervalRef.current = setInterval(() => {
      if (startTimeRef.current !== null) {
        const diff = (performance.now() - startTimeRef.current) / 1000;
        setElapsedSeconds(parseFloat(diff.toFixed(1)));
      }
    }, 100);

    return controller;
  }, []);

  const stopTimer = useCallback((success: boolean = true): number | null => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsRunning(false);

    let finalDuration: number | null = null;
    if (startTimeRef.current !== null) {
      finalDuration = parseFloat(((performance.now() - startTimeRef.current) / 1000).toFixed(1));
      if (success) {
        setCompletedDuration(finalDuration);
      }
    }
    startTimeRef.current = null;
    abortControllerRef.current = null;
    return finalDuration;
  }, []);

  const cancelTimer = useCallback(() => {
    if (abortControllerRef.current) {
      try {
        abortControllerRef.current.abort();
      } catch (e) {
        console.warn("Error aborting task controller:", e);
      }
    }
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsRunning(false);
    startTimeRef.current = null;
    abortControllerRef.current = null;
  }, []);

  const resetTimer = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsRunning(false);
    setElapsedSeconds(0);
    setCompletedDuration(null);
    startTimeRef.current = null;
    abortControllerRef.current = null;
  }, []);

  const getAbortSignal = useCallback(() => {
    return abortControllerRef.current?.signal;
  }, []);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const formatSecs = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const remainder = Math.floor(sec % 60);
    const tenths = Math.floor((sec % 1) * 10);
    return `${mins.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}.${tenths}`;
  };

  return {
    isRunning,
    elapsedSeconds,
    completedDuration,
    startTimer,
    stopTimer,
    cancelTimer,
    resetTimer,
    getAbortSignal,
    abortController: abortControllerRef.current,
    formattedElapsed: formatSecs(elapsedSeconds),
    formattedDuration: completedDuration !== null ? `${completedDuration.toFixed(1)}s` : null,
  };
}

// ---------------------------------------------------------------------------
// Visual Components
// ---------------------------------------------------------------------------

interface LiveProcessTimerProps {
  timer?: UseProcessTimerReturn;
  isRunning?: boolean;
  elapsedSeconds?: number;
  completedDuration?: number | null;
  onCancel?: () => void;
  label?: string;
  title?: string;
  description?: string;
  estimateText?: string;
  estimatedTimeText?: string;
  cancelLabel?: string;
  className?: string;
  modelName?: string;
  tokenUsage?: any;
  variant?: "default" | "expanded";
}

export function LiveProcessTimer({
  timer,
  isRunning: directIsRunning,
  elapsedSeconds: directElapsedSeconds,
  completedDuration: directCompletedDuration,
  onCancel: directOnCancel,
  label,
  title,
  description,
  estimateText,
  estimatedTimeText,
  cancelLabel = "Cancel",
  className = "",
  modelName = "Active AI Model",
  tokenUsage,
  variant = "default",
}: LiveProcessTimerProps) {
  const isRunning = timer ? timer.isRunning : (directIsRunning ?? false);
  const elapsedSeconds = timer ? timer.elapsedSeconds : (directElapsedSeconds ?? 0);
  const completedDuration = timer ? timer.completedDuration : directCompletedDuration;
  const onCancel = directOnCancel || (timer ? timer.cancelTimer : undefined);
  const displayLabel = title || label || "Processing with AI...";
  const displayEstimate = estimatedTimeText || estimateText || "Est. 8 - 25s";

  const [streamedTokens, setStreamedTokens] = useState(0);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (isRunning) {
      setStreamedTokens(90);
      interval = setInterval(() => {
        setStreamedTokens((prev) => prev + Math.floor(Math.random() * 35) + 25);
      }, 250);
    } else {
      setStreamedTokens(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isRunning]);

  if (!isRunning && !completedDuration && !tokenUsage) {
    return null;
  }

  const formatDisplay = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    const tenths = Math.floor((sec % 1) * 10);
    return `${mins > 0 ? `${mins}m ` : ""}${secs}.${tenths}s`;
  };

  const effectiveModelName = tokenUsage?.display_name || modelName;

  if (isRunning) {
    if (variant === "expanded") {
      return (
        <div
          className={`w-full p-5 sm:p-6 rounded-xl border border-blue-500/40 bg-gradient-to-r from-blue-950/70 via-slate-900/95 to-indigo-950/60 backdrop-blur-md shadow-2xl shadow-blue-950/40 animate-in fade-in duration-200 text-left space-y-4 ${className}`}
        >
          {/* Header Row: Radar + Status & Titles + Cancel CTA */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3.5 min-w-0">
              <div className="relative flex items-center justify-center w-11 h-11 rounded-xl bg-blue-600/20 border border-blue-500/40 text-blue-400 shrink-0 shadow-inner">
                <Loader2 className="w-5 h-5 animate-spin text-blue-400" />
                <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500"></span>
                </span>
              </div>

              <div className="min-w-0">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <h3 className="text-sm sm:text-base font-bold text-white tracking-tight">
                    {displayLabel}
                  </h3>
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30 shrink-0">
                    <Sparkles className="w-3 h-3 text-cyan-300" />
                    <span>Inference Active</span>
                  </span>
                </div>
                <p className="text-xs text-slate-300 mt-1 truncate">
                  {description || "Autonomous parsing, cryptographic PII isolation, and vector chunk indexing."}
                </p>
              </div>
            </div>

            {onCancel && (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onCancel();
                }}
                className="flex items-center justify-center gap-2 px-3.5 py-2 rounded-lg bg-rose-950/80 hover:bg-rose-900 border border-rose-500/40 hover:border-rose-400 text-rose-200 hover:text-white text-xs font-semibold shadow-sm transition-all cursor-pointer w-full sm:w-auto active:scale-95 shrink-0"
                title="Immediately abort the ongoing AI task"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>{cancelLabel}</span>
              </button>
            )}
          </div>

          {/* Telemetry Chips Strip */}
          <div className="flex items-center gap-2.5 flex-wrap pt-1 border-t border-slate-800/80">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30 shadow-sm">
              <Clock className="w-3.5 h-3.5 text-blue-400" />
              <span>⏱ {formatDisplay(elapsedSeconds)}</span>
            </span>

            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 shadow-sm">
              <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400/20" />
              <span>{effectiveModelName}: ~{streamedTokens.toLocaleString()} tokens</span>
            </span>

            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-medium bg-slate-800/90 text-slate-300 border border-slate-700/60 shadow-sm">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span>{displayEstimate} • Live inference streaming</span>
            </span>
          </div>

          {/* Animated Gradient Progress & 4 Pipeline Phases */}
          <div className="space-y-2 pt-1">
            <div className="h-1.5 w-full bg-slate-800/90 rounded-full overflow-hidden border border-slate-700/50 relative">
              <div
                className="h-full bg-gradient-to-r from-blue-500 via-cyan-400 to-indigo-500 rounded-full animate-pulse transition-all duration-300"
                style={{
                  width: `${Math.min(95, Math.max(15, (elapsedSeconds / 18) * 100))}%`,
                }}
              />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] pt-1">
              <div className="flex items-center gap-1.5 text-blue-300 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                <span className="truncate">1. Document OCR</span>
              </div>
              <div className="flex items-center gap-1.5 text-cyan-300 font-medium">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping shrink-0"></span>
                <span className="truncate">2. PII Scrubbing</span>
              </div>
              <div className="flex items-center gap-1.5 text-indigo-300 font-medium">
                <span className="w-2 h-2 rounded-full bg-indigo-400 shrink-0"></span>
                <span className="truncate">3. Entity Extraction</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-400 font-medium">
                <span className="w-2 h-2 rounded-full bg-slate-600 shrink-0"></span>
                <span className="truncate">4. Vector Embedding</span>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div
        className={`flex flex-col sm:flex-row items-center justify-between gap-3 p-3.5 rounded-xl border border-blue-500/30 bg-blue-950/40 backdrop-blur-md shadow-lg shadow-blue-950/40 animate-in fade-in duration-200 ${className}`}
      >
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-400 shrink-0">
            <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
            <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
          </div>

          <div className="flex flex-col text-left">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold text-slate-100">{displayLabel}</span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                ⏱ {formatDisplay(elapsedSeconds)}
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1">
                <span>⚡</span>
                <span>{effectiveModelName}: ~{streamedTokens.toLocaleString()} tok</span>
              </span>
            </div>
            {description && (
              <span className="text-[11px] text-slate-300 mt-0.5">
                {description}
              </span>
            )}
            {displayEstimate && (
              <span className="text-[10px] text-slate-400 mt-0.5">
                {displayEstimate} • Live inference streaming...
              </span>
            )}
          </div>
        </div>

        {onCancel && (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onCancel();
            }}
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-950/80 hover:bg-rose-900 border border-rose-500/40 hover:border-rose-400 text-rose-200 hover:text-rose-100 text-xs font-medium shadow-sm transition-all cursor-pointer w-full sm:w-auto active:scale-95 shrink-0"
            title="Immediately abort the ongoing AI task"
          >
            <Square className="w-3 h-3 fill-current" />
            <span>{cancelLabel}</span>
          </button>
        )}
      </div>
    );
  }

  if (completedDuration !== undefined && completedDuration !== null) {
    return (
      <div
        className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 shadow-sm ${className}`}
      >
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
        <span>Completed in {completedDuration.toFixed(1)}s</span>
        {tokenUsage && tokenUsage.total_tokens > 0 && (
          <>
            <span className="text-emerald-700">•</span>
            <span className="font-mono text-amber-300">
              ⚡ {tokenUsage.total_tokens.toLocaleString()} tok ({tokenUsage.prompt_tokens} in / {tokenUsage.completion_tokens} out)
            </span>
          </>
        )}
      </div>
    );
  }

  return null;
}

export function DurationBadge({
  duration,
  tokenUsage,
  label = "Processing Time",
  className = "",
}: {
  duration?: number | null;
  tokenUsage?: any;
  label?: string;
  className?: string;
}) {
  if (!duration && !tokenUsage) return null;

  return (
    <div className={`inline-flex items-center gap-1.5 ${className}`}>
      {duration && duration > 0 && (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-800/80 border border-slate-700/60 text-slate-300"
          title={`${label}: ${duration.toFixed(1)}s`}
        >
          <Clock className="w-3 h-3 text-cyan-400" />
          <span>{duration.toFixed(1)}s</span>
        </span>
      )}

      {tokenUsage && tokenUsage.total_tokens > 0 && (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono font-medium bg-slate-900 border border-amber-500/30 text-amber-300"
          title={`${tokenUsage.display_name || tokenUsage.model}: ${tokenUsage.prompt_tokens} in / ${tokenUsage.completion_tokens} out`}
        >
          <span>⚡</span>
          <span>
            {tokenUsage.display_name || tokenUsage.model?.split("/")?.pop() || "AI"}: {tokenUsage.total_tokens.toLocaleString()} tok
          </span>
        </span>
      )}
    </div>
  );
}
