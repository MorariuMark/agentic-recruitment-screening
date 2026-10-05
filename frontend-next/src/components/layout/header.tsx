"use client";

import { useState, useEffect } from "react";
import { JobDescription } from "@/types";
import { api } from "@/lib/api";
import {
  Activity,
  Briefcase,
  ChevronDown,
  ExternalLink,
  PanelLeftClose,
  PanelLeftOpen,
  Zap,
} from "lucide-react";

interface HeaderProps {
  jobs: JobDescription[];
  selectedJobId: string | null;
  onSelectJob: (jobId: string | null) => void;
  onOpenUploadModal?: () => void;
  onNavigateToSettings?: () => void;
  isSidebarOpen?: boolean;
  onToggleSidebar?: () => void;
}

export function Header({
  jobs,
  selectedJobId,
  onSelectJob,
  onOpenUploadModal,
  onNavigateToSettings,
  isSidebarOpen = true,
  onToggleSidebar,
}: HeaderProps) {
  const [backendStatus, setBackendStatus] = useState<"online" | "offline" | "checking">("checking");
  const [isJobDropdownOpen, setIsJobDropdownOpen] = useState(false);

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

  useEffect(() => {
    let isMounted = true;
    const failsafe = setTimeout(() => {
      if (isMounted) {
        setBackendStatus((prev) => (prev === "checking" ? "offline" : prev));
      }
    }, 2500);

    refreshStatus();
    const interval = setInterval(refreshStatus, 10000);

    return () => {
      isMounted = false;
      clearTimeout(failsafe);
      clearInterval(interval);
    };
  }, []);

  const activeJob = jobs.find((j) => j.id === selectedJobId);

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md px-4 flex items-center justify-between sticky top-0 z-40">
      {/* Left: Sidebar Toggle & Requisition Scope Selector */}
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

        {/* Active Job Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => setIsJobDropdownOpen(!isJobDropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-sm font-medium text-slate-200 transition-colors cursor-pointer"
          >
            <Briefcase className="w-4 h-4 text-slate-400" />
            <span className="max-w-[220px] md:max-w-[280px] truncate">
              {activeJob ? activeJob.title : "All Requisitions"}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
          </button>

          {isJobDropdownOpen && (
            <div className="absolute left-0 mt-1 w-72 rounded-lg bg-slate-900 border border-slate-800 shadow-2xl py-1 z-50 animate-in fade-in zoom-in-95">
              <button
                onClick={() => {
                  onSelectJob(null);
                  setIsJobDropdownOpen(false);
                }}
                className={`w-full px-3 py-2 text-left text-xs font-medium flex items-center justify-between hover:bg-slate-800 transition-colors cursor-pointer ${
                  !selectedJobId ? "text-blue-400 font-semibold bg-blue-500/10" : "text-slate-300"
                }`}
              >
                <span>All Requisitions</span>
                <span className="text-[10px] text-slate-500">{jobs.length} total</span>
              </button>
              <div className="h-px bg-slate-800 my-1" />
              {jobs.map((job) => (
                <button
                  key={job.id}
                  onClick={() => {
                    onSelectJob(job.id);
                    setIsJobDropdownOpen(false);
                  }}
                  className={`w-full px-3 py-2 text-left text-xs hover:bg-slate-800 transition-colors cursor-pointer ${
                    selectedJobId === job.id ? "text-blue-400 font-semibold bg-blue-500/10" : "text-slate-300"
                  }`}
                >
                  <div className="truncate font-medium">{job.title}</div>
                  <div className="text-[10px] text-slate-500 truncate">
                    {job.seniority_level || "Standard"} • {job.department || "Engineering"}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: Phoenix Traces & Backend Health */}
      <div className="flex items-center gap-3">

        {/* Token Usage Analytics link */}
        {onNavigateToSettings && (
          <button
            onClick={onNavigateToSettings}
            className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 hover:border-amber-500/40 text-xs text-slate-300 hover:text-amber-300 transition-colors cursor-pointer group"
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
          className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          title="Open Arize Phoenix OpenTelemetry tracing dashboard"
        >
          <Activity className="w-3.5 h-3.5 text-purple-400" />
          <span>Phoenix Traces</span>
          <ExternalLink className="w-3 h-3 text-slate-500" />
        </a>

        {/* Backend health pulse */}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs">
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
