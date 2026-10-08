"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { JobDescription } from "@/types";
import {
  Briefcase,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Highlighter,
  Layers,
  MapPin,
  Quote,
  Search,
  Sparkles,
  Target,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { downloadJsonFile } from "@/lib/utils";

interface ParsedJdViewerProps {
  job: JobDescription | null;
  activeRequirementId?: string | null;
  onSelectRequirement?: (reqId: string) => void;
  onClose?: () => void;
  isModal?: boolean;
}

export function ParsedJdViewer({
  job,
  activeRequirementId,
  onSelectRequirement,
  onClose,
  isModal = false,
}: ParsedJdViewerProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const [fontSize, setFontSize] = useState<"sm" | "base" | "lg">("base");
  const [viewMode, setViewMode] = useState<"structured" | "raw" | "both">("both");

  const containerRef = useRef<HTMLDivElement>(null);
  const activeReqRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to active requirement whenever activeRequirementId changes
  useEffect(() => {
    if (activeRequirementId && activeReqRef.current) {
      activeReqRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [activeRequirementId]);

  // Full raw text fallback if raw_text is missing or brief
  const rawJdText = useMemo(() => {
    if (job?.raw_text && job.raw_text.trim().length > 0) {
      return job.raw_text;
    }
    if (!job) return "No job description loaded.";

    // Fallback synthesis from structured job details
    const parts: string[] = [];
    parts.push(`# ${job.title || "Job Specification"}`);
    if (job.department || job.seniority_level || job.location) {
      const meta = [
        job.department ? `Department: ${job.department}` : null,
        job.seniority_level ? `Level: ${job.seniority_level}` : null,
        job.location ? `Location: ${job.location}` : null,
        job.work_model ? `Work Model: ${job.work_model}` : null,
        job.employment_type ? `Type: ${job.employment_type}` : null,
      ]
        .filter(Boolean)
        .join(" | ");
      parts.push(`> ${meta}`);
    }

    if (job.requirements && job.requirements.length > 0) {
      parts.push("## Key Role Requirements & Criteria");
      job.requirements.forEach((req, idx) => {
        const cat = req.category === "must_have" ? "[MUST-HAVE]" : "[NICE-TO-HAVE]";
        const exp = req.minimum_years_experience ? ` (${req.minimum_years_experience}+ yrs exp)` : "";
        parts.push(`### ${idx + 1}. ${req.title} ${cat}${exp}\n${req.description}`);
      });
    }

    return parts.join("\n\n");
  }, [job]);

  const handleCopyText = () => {
    navigator.clipboard.writeText(rawJdText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const activeReq = useMemo(() => {
    return (job?.requirements || []).find((r) => r.id === activeRequirementId);
  }, [job, activeRequirementId]);

  const fontSizeClass =
    fontSize === "base"
      ? "text-[15px] leading-relaxed"
      : fontSize === "lg"
      ? "text-base leading-relaxed"
      : "text-sm leading-relaxed";

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl backdrop-blur-md">
      {/* Header Bar */}
      <div className="px-5 py-3.5 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-9 h-9 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400 shrink-0 shadow-inner">
            <Briefcase className="w-5 h-5" />
          </div>
          <div className="overflow-hidden">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm sm:text-base font-bold text-white truncate">
                {job?.title || "Requisition Specification"}
              </h3>
              <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/30">
                Parsed JD
              </span>
            </div>
            <p className="text-xs text-slate-400 truncate mt-0.5">
              {job?.department || "Engineering"} • {job?.seniority_level || "Standard"} • {job?.location || "Remote/Hybrid"}
            </p>
          </div>
        </div>

        {/* Toolbar Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {/* View mode toggle */}
          <div className="hidden sm:flex items-center rounded-lg border border-slate-800 bg-slate-950 p-0.5 text-xs">
            <button
              onClick={() => setViewMode("both")}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === "both" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white"
              }`}
            >
              All Sections
            </button>
            <button
              onClick={() => setViewMode("structured")}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === "structured" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white"
              }`}
            >
              Criteria Breakdown
            </button>
            <button
              onClick={() => setViewMode("raw")}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === "raw" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white"
              }`}
            >
              Original Text
            </button>
          </div>

          {/* Font zoom */}
          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950 p-0.5">
            <button
              onClick={() => setFontSize(fontSize === "lg" ? "base" : "sm")}
              disabled={fontSize === "sm"}
              className="p-1.5 text-slate-400 hover:text-white disabled:opacity-30"
              title="Decrease text size"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setFontSize(fontSize === "sm" ? "base" : "lg")}
              disabled={fontSize === "lg"}
              className="p-1.5 text-slate-400 hover:text-white disabled:opacity-30"
              title="Increase text size"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Copy document */}
          <button
            onClick={handleCopyText}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
            title="Copy full JD text"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>

          {/* Download JSON */}
          <button
            onClick={() => {
              if (!job) return;
              const jobTitle = (job.title || job.id || "requisition")
                .toLowerCase()
                .replace(/[^a-z0-9]/g, "_");
              downloadJsonFile(job, `job_${jobTitle}_extracted.json`);
            }}
            disabled={!job}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-blue-400 text-xs transition-colors disabled:opacity-40"
            title="Download extracted job specification JSON"
          >
            <Download className="w-4 h-4" />
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors ml-1"
              title="Close JD Viewer"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Sub-bar: Search & Active Highlight Notification */}
      <div className="px-5 py-2.5 border-b border-slate-800/80 bg-slate-950/50 flex items-center justify-between gap-3 shrink-0 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search keywords in Job Description..."
            className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-9 pr-8 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        {activeReq ? (
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/40 text-xs text-amber-200 animate-in fade-in">
            <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
            <span className="font-semibold">Highlighting:</span>
            <span className="font-bold text-white max-w-[220px] truncate">{activeReq.title}</span>
          </div>
        ) : (
          <div className="text-xs text-slate-400">
            Click any requirement card to jump and highlight it in this JD
          </div>
        )}
      </div>

      {/* Quick Jump Requirement Pills Strip */}
      {job && job.requirements && job.requirements.length > 0 && (
        <div className="px-5 py-2.5 border-b border-slate-800/80 bg-slate-950/30 shrink-0 overflow-x-auto">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400 whitespace-nowrap">
              Jump to Criterion:
            </span>
            <div className="flex items-center gap-1.5 flex-nowrap">
              {job.requirements.map((req) => {
                const isSelected = activeRequirementId === req.id;
                const isMustHave = req.category === "must_have";
                return (
                  <button
                    key={req.id}
                    onClick={() => onSelectRequirement?.(req.id)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-all cursor-pointer flex items-center gap-1.5 ${
                      isSelected
                        ? "bg-amber-500 text-slate-950 font-bold shadow-md shadow-amber-500/30 scale-105"
                        : isMustHave
                        ? "bg-rose-500/10 text-rose-300 border border-rose-500/30 hover:bg-rose-500/20"
                        : "bg-blue-500/10 text-blue-300 border border-blue-500/30 hover:bg-blue-500/20"
                    }`}
                  >
                    <span>{req.title}</span>
                    <span className="text-[10px] opacity-75 font-mono">
                      {isMustHave ? "MUST" : "NICE"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Document Content Body */}
      <div
        ref={containerRef}
        className={`flex-1 overflow-y-auto p-6 space-y-6 select-text text-slate-200 ${fontSizeClass}`}
      >
        {/* Role Metadata Overview Card */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <span className="text-slate-400 block">Department</span>
            <span className="font-semibold text-white">{job?.department || "Engineering"}</span>
          </div>
          <div>
            <span className="text-slate-400 block">Seniority Level</span>
            <span className="font-semibold text-white">{job?.seniority_level || "Standard"}</span>
          </div>
          <div>
            <span className="text-slate-400 block">Work Model</span>
            <span className="font-semibold text-white">{job?.work_model || "Flexible"}</span>
          </div>
          <div>
            <span className="text-slate-400 block">Employment Type</span>
            <span className="font-semibold text-white">{job?.employment_type || "Full-time"}</span>
          </div>
        </div>

        {/* Section 1: Granular Atomic Requirements (Parsed Breakdown) */}
        {(viewMode === "both" || viewMode === "structured") && (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h4 className="text-sm font-bold uppercase tracking-wider text-blue-400 flex items-center gap-2">
                <Target className="w-4 h-4" />
                <span>Extracted Atomic Requirements ({job?.requirements?.length || 0})</span>
              </h4>
              <span className="text-xs text-slate-400">
                Verified criteria calibrated by the AI Agent
              </span>
            </div>

            <div className="space-y-3.5">
              {(job?.requirements || []).map((req, rIdx) => {
                const isSelected = activeRequirementId === req.id;
                const isMustHave = req.category === "must_have";

                return (
                  <div
                    key={req.id || rIdx}
                    ref={isSelected ? activeReqRef : undefined}
                    onClick={() => onSelectRequirement?.(req.id)}
                    className={`p-4 rounded-xl border transition-all cursor-pointer space-y-2.5 ${
                      isSelected
                        ? "border-2 border-amber-400 ring-2 ring-amber-400/50 shadow-[0_0_25px_rgba(251,191,36,0.25)] bg-amber-500/10 scale-[1.01]"
                        : "border-slate-800/90 bg-slate-950/70 hover:border-slate-700 hover:bg-slate-900/60"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-white text-base">
                            {rIdx + 1}. {req.title}
                          </span>
                          {isSelected && (
                            <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-400 text-slate-950 flex items-center gap-1 shadow-sm">
                              <Sparkles className="w-3 h-3 fill-current" />
                              <span>Active Highlight</span>
                            </span>
                          )}
                          <span className="text-[10px] font-mono text-slate-500 px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">
                            {req.id}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 text-xs flex-wrap">
                          <span
                            className={`font-bold px-2 py-0.5 rounded-md text-xs uppercase tracking-wide ${
                              isMustHave
                                ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                                : "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                            }`}
                          >
                            {isMustHave ? "Must-Have" : "Nice-to-Have"}
                          </span>
                          <span className="text-slate-400">• Weight: {req.weight}x</span>
                          {req.minimum_years_experience && (
                            <span className="text-slate-300">
                              • {req.minimum_years_experience}+ yrs experience
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <p className="text-sm text-slate-200 leading-relaxed font-sans pl-1">
                      {req.description}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Section 2: Complete Original / Raw Job Description Text */}
        {(viewMode === "both" || viewMode === "raw") && (
          <div className="space-y-3 pt-4 border-t border-slate-800">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-400" />
                <span>Full Original Job Description Text</span>
              </h4>
              <span className="text-xs text-slate-400 font-mono">
                {rawJdText.length.toLocaleString()} characters
              </span>
            </div>

            <div className="p-5 rounded-xl border border-slate-800/90 bg-slate-950/80 font-mono text-xs text-slate-300 leading-relaxed whitespace-pre-wrap space-y-2 select-text shadow-inner">
              {rawJdText.split("\n").map((line, lIdx) => {
                if (!line.trim()) {
                  return <div key={lIdx} className="h-2" />;
                }

                // If active requirement matches something in this line, highlight it
                const lineLower = line.toLowerCase();
                const activeKeyword = activeReq?.title?.toLowerCase();
                let isMatch = false;

                if (activeKeyword && lineLower.includes(activeKeyword)) {
                  isMatch = true;
                }

                if (isMatch) {
                  return (
                    <p key={lIdx} className="bg-amber-400/20 text-amber-100 border-l-2 border-amber-400 pl-2 py-0.5 rounded font-sans font-medium">
                      <Sparkles className="w-3 h-3 inline mr-1 text-amber-400" />
                      {line}
                    </p>
                  );
                }

                return (
                  <p key={lIdx} className="font-sans">
                    {line}
                  </p>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
