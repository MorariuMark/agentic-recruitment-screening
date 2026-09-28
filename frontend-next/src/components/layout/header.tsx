"use client";

import { useState, useEffect } from "react";
import { JobDescription } from "@/types";
import { api } from "@/lib/api";
import {
  Activity,
  Briefcase,
  ChevronDown,
  ExternalLink,
  Layers,
  Sparkles,
  Zap,
} from "lucide-react";

interface HeaderProps {
  jobs: JobDescription[];
  selectedJobId: string | null;
  onSelectJob: (jobId: string | null) => void;
  onOpenUploadModal?: () => void;
}

export function Header({
  jobs,
  selectedJobId,
  onSelectJob,
  onOpenUploadModal,
}: HeaderProps) {
  const [backendStatus, setBackendStatus] = useState<"online" | "offline" | "checking">("checking");
  const [activeModel, setActiveModel] = useState<string>("Detecting...");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  useEffect(() => {
    let isMounted = true;

    // Failsafe timer: transition out of 'checking' state within 4s if network hangs
    const failsafe = setTimeout(() => {
      if (isMounted) {
        setBackendStatus((prev) => (prev === "checking" ? "offline" : prev));
        setActiveModel((prev) => (prev === "Detecting..." ? "Offline" : prev));
      }
    }, 4000);

    async function checkHealth() {
      try {
        const health = await api.getHealth();
        if (isMounted) {
          setBackendStatus(health.status === "ok" ? "online" : "offline");
          const provider = health.active_llm_provider || "llm";
          const model = health.active_model || "ready";
          setActiveModel(`${provider}:${model}`);
        }
      } catch {
        if (isMounted) {
          setBackendStatus("offline");
          setActiveModel("Unavailable");
        }
      }
    }

    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => {
      isMounted = false;
      clearTimeout(failsafe);
      clearInterval(interval);
    };
  }, []);

  const activeJob = jobs.find((j) => j.id === selectedJobId);

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md px-4 flex items-center justify-between sticky top-0 z-40">
      {/* Left: Requisition Scope Selector */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold uppercase tracking-wider">
          <Sparkles className="w-3.5 h-3.5 text-blue-400" />
          <span>Enterprise Screening</span>
        </div>

        <div className="h-4 w-px bg-slate-800" />

        {/* Active Job Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-sm font-medium text-slate-200 transition-colors"
          >
            <Briefcase className="w-4 h-4 text-slate-400" />
            <span className="max-w-[200px] truncate">
              {activeJob ? activeJob.title : "All Requisitions"}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
          </button>

          {isDropdownOpen && (
            <div className="absolute left-0 mt-1 w-64 rounded-lg bg-slate-900 border border-slate-800 shadow-2xl py-1 z-50">
              <button
                onClick={() => {
                  onSelectJob(null);
                  setIsDropdownOpen(false);
                }}
                className={`w-full px-3 py-2 text-left text-xs font-medium flex items-center justify-between hover:bg-slate-800 transition-colors ${
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
                    setIsDropdownOpen(false);
                  }}
                  className={`w-full px-3 py-2 text-left text-xs hover:bg-slate-800 transition-colors ${
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

      {/* Right: Diagnostics, Phoenix Trace, & Status */}
      <div className="flex items-center gap-3">
        {/* Arize Phoenix Observability link */}
        <a
          href="http://localhost:6006"
          target="_blank"
          rel="noopener noreferrer"
          className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <Activity className="w-3.5 h-3.5 text-purple-400" />
          <span>Phoenix Traces</span>
          <ExternalLink className="w-3 h-3 text-slate-500" />
        </a>

        {/* Active LLM Model tag */}
        <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-xs text-slate-300">
          <Zap className="w-3.5 h-3.5 text-amber-400" />
          <span className="font-mono text-[11px] text-slate-400">{activeModel}</span>
        </div>

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
