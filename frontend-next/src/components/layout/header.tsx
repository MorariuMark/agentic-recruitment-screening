"use client";

import { useState, useEffect } from "react";
import { JobDescription } from "@/types";
import { api } from "@/lib/api";
import {
  Activity,
  ExternalLink,
  PanelLeftClose,
  PanelLeftOpen,
  Terminal,
  Cpu,
  Zap,
} from "lucide-react";

interface HeaderProps {
  jobs?: JobDescription[];
  selectedJobId?: string | null;
  onSelectJob?: (jobId: string | null) => void;
  onOpenUploadModal?: () => void;
  onNavigateToSettings?: () => void;
  onOpenDebugModal?: () => void;
  onOpenLocalModelModal?: () => void;
  isSidebarOpen?: boolean;
  onToggleSidebar?: () => void;
}

export function Header({
  jobs = [],
  selectedJobId,
  onSelectJob,
  onOpenUploadModal,
  onNavigateToSettings,
  onOpenDebugModal,
  onOpenLocalModelModal,
  isSidebarOpen = true,
  onToggleSidebar,
}: HeaderProps) {
  const [backendStatus, setBackendStatus] = useState<"online" | "offline" | "checking">("checking");
  const [inFlightCount, setInFlightCount] = useState<number>(0);

  const refreshStatus = async () => {
    try {
      const health = await api.getHealth();
      if (health && health.status === "ok") {
        setBackendStatus("online");
      }
    } catch {
      setBackendStatus("offline");
    }
  };

  const checkInFlight = async () => {
    try {
      const state = await api.getLiveLLMLogs(1);
      setInFlightCount(state?.in_flight?.length || 0);
    } catch {
      // ignore background poll errors
    }
  };

  useEffect(() => {
    let isMounted = true;
    const failsafe = setTimeout(() => {
      if (isMounted) {
        setBackendStatus((prev) => (prev === "checking" ? "offline" : prev));
      }
    }, 2500);

    refreshStatus();
    checkInFlight();

    const healthInterval = setInterval(refreshStatus, 10000);
    const flightInterval = setInterval(checkInFlight, 2500);

    return () => {
      isMounted = false;
      clearTimeout(failsafe);
      clearInterval(healthInterval);
      clearInterval(flightInterval);
    };
  }, []);

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md px-4 flex items-center justify-between sticky top-0 z-40">
      {/* Left: Sidebar Toggle */}
      <div className="flex items-center gap-3">
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 hover:bg-slate-850 text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
            title={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
            aria-label={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
          >
            {isSidebarOpen ? (
              <PanelLeftClose className="w-4 h-4 text-slate-300" />
            ) : (
              <PanelLeftOpen className="w-4 h-4 text-blue-400" />
            )}
          </button>
        )}
      </div>

      {/* Right: LLM Live Debug Console, Telemetry & Backend Health */}
      <div className="flex items-center gap-2.5">
        {/* Local GPU Engine Controls */}
        {onOpenLocalModelModal && (
          <button
            onClick={onOpenLocalModelModal}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-purple-500/40 text-xs text-slate-300 hover:text-purple-300 transition-colors cursor-pointer group"
            title="Open Local GPU & Model Controls (RTX 4060 Ti, Load / Unload Models, 16k Rolling Context)"
          >
            <Cpu className="w-3.5 h-3.5 text-purple-400 group-hover:scale-110 transition-transform" />
            <span className="font-mono text-[11px]">Local GPU</span>
          </button>
        )}

        {/* Dedicated In-App LLM Console Button */}
        {onOpenDebugModal && (
          <button
            onClick={onOpenDebugModal}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer shadow-sm select-none ${
              inFlightCount > 0
                ? "bg-amber-500/15 border border-amber-500/40 text-amber-200 shadow-amber-500/20 hover:bg-amber-500/25 animate-pulse"
                : "bg-slate-900/90 border border-slate-700/80 hover:border-cyan-500/50 hover:bg-slate-850 text-slate-200 hover:text-white"
            }`}
            title="Open In-App LLM Console: inspect models, providers, prompts, outputs, latency, tokens, and errors in real-time."
          >
            <div className="p-0.5 rounded bg-cyan-500/10 text-cyan-400">
              <Terminal className="w-3.5 h-3.5" />
            </div>
            <div className="flex items-center gap-1.5 font-mono text-[11px]">
              <span className="font-semibold text-slate-100">LLM Console</span>
              {inFlightCount > 0 ? (
                <span className="px-1.5 py-0.2 rounded-full bg-amber-500/20 text-amber-300 text-[10px] border border-amber-500/40 font-bold">
                  {inFlightCount} In-Flight
                </span>
              ) : (
                <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/10 text-emerald-400 text-[10px] border border-emerald-500/20">
                  Live
                </span>
              )}
            </div>
          </button>
        )}

        {/* Token Usage Analytics link */}
        {onNavigateToSettings && (
          <button
            onClick={onNavigateToSettings}
            className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-amber-500/40 text-xs text-slate-300 hover:text-amber-300 transition-colors cursor-pointer group"
            title="Open Token Usage & Model Analytics Dashboard"
          >
            <Zap className="w-3.5 h-3.5 text-amber-400 group-hover:scale-110 transition-transform fill-amber-400/20" />
            <span className="font-mono text-[11px]">Tokens &amp; Telemetry</span>
          </button>
        )}

        {/* Arize Phoenix Observability link */}
        <a
          href="http://localhost:6006"
          target="_blank"
          rel="noopener noreferrer"
          className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          title="Open Arize Phoenix OpenTelemetry tracing dashboard"
        >
          <Activity className="w-3.5 h-3.5 text-purple-400" />
          <span>Phoenix Traces</span>
          <ExternalLink className="w-3 h-3 text-slate-500" />
        </a>

        {/* Backend health pulse */}
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-xs">
          <span className="relative flex h-2 w-2">
            {backendStatus === "online" ? (
              <>
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </>
            ) : backendStatus === "offline" ? (
              <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
            ) : (
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
            )}
          </span>
          <span className="text-[11px] font-medium text-slate-300 capitalize">
            {backendStatus}
          </span>
        </div>
      </div>
    </header>
  );
}
