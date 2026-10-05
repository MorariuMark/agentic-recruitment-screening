"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { CandidateDetail, VerbatimCitation } from "@/types";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  FileText,
  Highlighter,
  Search,
  Sparkles,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

interface DocumentViewerProps {
  candidate: CandidateDetail | null;
  activeCitation?: string | null;
  allCitations?: VerbatimCitation[];
  onClose?: () => void;
}

export function DocumentViewer({
  candidate,
  activeCitation,
  allCitations = [],
  onClose,
}: DocumentViewerProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const [fontSize, setFontSize] = useState<"sm" | "base" | "lg">("sm");
  const [highlightAll, setHighlightAll] = useState(true);

  const containerRef = useRef<HTMLDivElement>(null);
  const activeQuoteRef = useRef<HTMLSpanElement>(null);

  const rawText = useMemo(() => {
    if (candidate?.sanitized_text && candidate.sanitized_text.trim().length > 0) {
      return candidate.sanitized_text;
    }
    if (!candidate) return "No candidate document loaded.";

    // Fallback synthesis from structured candidate details
    const parts: string[] = [];
    const name = candidate.masked_name || candidate.original_filename || `Candidate-${candidate.id.slice(0, 6)}`;
    parts.push(`# ${name}`);

    if (candidate.parsed_cv?.summary) {
      parts.push(`## Professional Summary\n${candidate.parsed_cv.summary}`);
    }

    if (candidate.skills && candidate.skills.length > 0) {
      parts.push(`## Technical Skills\n${candidate.skills.join(", ")}`);
    }

    if (candidate.experiences && candidate.experiences.length > 0) {
      parts.push("## Professional Experience");
      candidate.experiences.forEach((exp: any) => {
        const title = exp.job_title || "Role";
        const company = exp.company_name || "Company";
        const start = exp.start_date || "";
        const end = exp.end_date || "Present";
        const dateStr = start ? ` (${start} - ${end})` : "";
        parts.push(`### ${title} at ${company}${dateStr}`);
        const descs = Array.isArray(exp.work_description) ? exp.work_description : exp.work_description ? [exp.work_description] : [];
        descs.forEach((d: string) => parts.push(`- ${d}`));
        if (exp.skills_used && exp.skills_used.length > 0) {
          parts.push(`Technologies: ${exp.skills_used.join(", ")}`);
        }
      });
    }

    if (candidate.educations && candidate.educations.length > 0) {
      parts.push("## Education");
      candidate.educations.forEach((edu: any) => {
        const deg = edu.degree_title || edu.degree_name || "Degree";
        const inst = edu.institution_name || "Institution";
        const year = edu.graduation_year ? ` (${edu.graduation_year})` : "";
        parts.push(`- ${deg}, ${inst}${year}`);
      });
    }

    return parts.length > 1 ? parts.join("\n\n") : "No sanitized document text available.";
  }, [candidate]);

  // Auto-scroll to active citation whenever it changes
  useEffect(() => {
    if (activeQuoteRef.current && containerRef.current) {
      activeQuoteRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [activeCitation]);

  // Copy full document text
  const handleCopyText = () => {
    navigator.clipboard.writeText(rawText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Build segmented document text with highlights
  const renderedContent = useMemo(() => {
    if (!rawText) return null;

    // Normalizing citations for case-insensitive matching
    const activeNorm = activeCitation?.trim().toLowerCase();
    const otherQuotes = highlightAll
      ? allCitations
          .map((c) => c.quote?.trim())
          .filter((q): q is string => Boolean(q && q.length > 5 && q.toLowerCase() !== activeNorm))
      : [];

    // Helper to find slice matches
    type Segment = {
      text: string;
      isActiveCitation: boolean;
      isOtherCitation: boolean;
      isSearchMatch: boolean;
    };

    // If there is a search query, prioritize highlighting that
    const searchNorm = searchQuery.trim().toLowerCase();

    // Line by line parsing for clean document layout
    const lines = rawText.split("\n");

    return lines.map((line, lineIdx) => {
      if (!line.trim()) {
        return <div key={lineIdx} className="h-3" />;
      }

      // Check for active citation in line
      const lineLower = line.toLowerCase();

      let activeIndex = -1;
      let activeLength = 0;

      if (activeNorm && lineLower.includes(activeNorm)) {
        activeIndex = lineLower.indexOf(activeNorm);
        activeLength = activeNorm.length;
      } else if (activeNorm) {
        // Fallback: check 30-char prefix if quote spans formatting
        const prefix = activeNorm.slice(0, Math.min(activeNorm.length, 30));
        if (prefix.length > 10 && lineLower.includes(prefix)) {
          activeIndex = lineLower.indexOf(prefix);
          activeLength = prefix.length;
        }
      }

      // Check for search query
      let searchIndex = -1;
      if (searchNorm && lineLower.includes(searchNorm)) {
        searchIndex = lineLower.indexOf(searchNorm);
      }

      // Check for other citations
      let otherQuoteMatch: string | null = null;
      for (const oq of otherQuotes) {
        const oqNorm = oq.toLowerCase();
        if (lineLower.includes(oqNorm)) {
          otherQuoteMatch = oq;
          break;
        }
      }

      if (activeIndex !== -1) {
        const before = line.slice(0, activeIndex);
        const match = line.slice(activeIndex, activeIndex + activeLength);
        const after = line.slice(activeIndex + activeLength);

        return (
          <p key={lineIdx} className="leading-relaxed">
            <span>{before}</span>
            <mark
              ref={activeQuoteRef}
              className="bg-amber-400/25 text-amber-200 border border-amber-400/60 rounded px-1.5 py-0.5 font-semibold shadow-sm inline-block my-0.5 animate-pulse"
              title="Active citation verifying requirement"
            >
              <Sparkles className="w-3 h-3 inline mr-1 text-amber-400" />
              {match}
            </mark>
            <span>{after}</span>
          </p>
        );
      }

      if (otherQuoteMatch) {
        const idx = lineLower.indexOf(otherQuoteMatch.toLowerCase());
        const before = line.slice(0, idx);
        const match = line.slice(idx, idx + otherQuoteMatch.length);
        const after = line.slice(idx + otherQuoteMatch.length);

        return (
          <p key={lineIdx} className="leading-relaxed">
            <span>{before}</span>
            <mark
              className="bg-emerald-500/15 text-emerald-200 border-b border-emerald-500/50 px-1 rounded-sm"
              title="Verified citation from evaluation"
            >
              {match}
            </mark>
            <span>{after}</span>
          </p>
        );
      }

      if (searchIndex !== -1 && searchNorm) {
        const before = line.slice(0, searchIndex);
        const match = line.slice(searchIndex, searchIndex + searchNorm.length);
        const after = line.slice(searchIndex + searchNorm.length);

        return (
          <p key={lineIdx} className="leading-relaxed">
            <span>{before}</span>
            <mark className="bg-blue-500/30 text-blue-200 px-1 rounded-sm font-medium">
              {match}
            </mark>
            <span>{after}</span>
          </p>
        );
      }

      return (
        <p key={lineIdx} className="leading-relaxed text-slate-300">
          {line}
        </p>
      );
    });
  }, [rawText, activeCitation, allCitations, highlightAll, searchQuery]);

  // Count search query matches
  const searchMatchCount = useMemo(() => {
    if (!searchQuery.trim() || !rawText) return 0;
    const regex = new RegExp(searchQuery.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    const matches = rawText.match(regex);
    return matches ? matches.length : 0;
  }, [searchQuery, rawText]);

  const fontSizeClass =
    fontSize === "base"
      ? "text-[15px] leading-relaxed"
      : fontSize === "lg"
      ? "text-base leading-relaxed"
      : "text-sm leading-relaxed";

  return (
    <div className="flex flex-col h-full bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-2xl backdrop-blur-sm">
      {/* Header bar */}
      <div className="px-4 py-3 border-b border-slate-800 bg-slate-950/70 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shrink-0">
            <FileText className="w-4 h-4" />
          </div>
          <div className="overflow-hidden">
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-semibold text-white truncate">
                {candidate?.original_filename || "Candidate Document"}
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                PII-Scrubbed
              </span>
            </div>
            <p className="text-[11px] text-slate-400 truncate">
              {candidate?.chunks_indexed || 0} semantic vector chunks indexed
            </p>
          </div>
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Highlight toggle */}
          <button
            onClick={() => setHighlightAll(!highlightAll)}
            title={highlightAll ? "Show active highlight only" : "Highlight all verified citations"}
            className={`p-1.5 rounded-lg border text-xs font-medium transition-colors ${
              highlightAll
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                : "bg-slate-800 border-slate-700 text-slate-400 hover:text-white"
            }`}
          >
            <Highlighter className="w-3.5 h-3.5" />
          </button>

          {/* Font zoom */}
          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950 p-0.5">
            <button
              onClick={() => setFontSize(fontSize === "lg" ? "base" : "sm")}
              disabled={fontSize === "sm"}
              className="p-1 text-slate-400 hover:text-white disabled:opacity-30"
              title="Decrease text size"
            >
              <ZoomOut className="w-3 h-3" />
            </button>
            <button
              onClick={() => setFontSize(fontSize === "sm" ? "base" : "lg")}
              disabled={fontSize === "lg"}
              className="p-1 text-slate-400 hover:text-white disabled:opacity-30"
              title="Increase text size"
            >
              <ZoomIn className="w-3 h-3" />
            </button>
          </div>

          {/* Copy document */}
          <button
            onClick={handleCopyText}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
            title="Copy text representation"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors ml-1"
              title="Close Document Viewer"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Sub-bar: In-Document Search & Active Citation Notification */}
      <div className="px-4 py-2 border-b border-slate-800/80 bg-slate-950/40 flex items-center justify-between gap-3 shrink-0">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search keywords in CV text..."
            className="w-full bg-slate-900 border border-slate-800 rounded-md pl-8 pr-16 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          {searchQuery && (
            <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-mono text-slate-400">
              {searchMatchCount} found
            </span>
          )}
        </div>

        {activeCitation && (
          <div className="flex items-center gap-1.5 text-[11px] text-amber-300 truncate max-w-xs">
            <Sparkles className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <span className="truncate">Active Citation: &ldquo;{activeCitation}&rdquo;</span>
          </div>
        )}
      </div>

      {/* Document Text Body */}
      <div
        ref={containerRef}
        className={`flex-1 overflow-y-auto p-5 font-sans text-slate-200 select-text space-y-1.5 ${fontSizeClass}`}
      >
        {renderedContent}
      </div>
    </div>
  );
}
