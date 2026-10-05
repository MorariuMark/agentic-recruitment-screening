"use client";

import { useState, useEffect } from "react";
import { CandidateComparisonReport, CandidateSummary, JobDescription } from "@/types";
import { api } from "@/lib/api";
import { getRecommendationBadge } from "@/lib/utils";
import {
  AlertCircle,
  ArrowLeft,
  Award,
  Briefcase,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileCheck2,
  FileText,
  HelpCircle,
  Loader2,
  Plus,
  Printer,
  Quote,
  RotateCw,
  Search,
  Sparkles,
  Trophy,
  UserCheck,
  Users2,
  X,
  XCircle,
} from "lucide-react";
import { LiveProcessTimer, DurationBadge, useProcessTimer } from "@/components/ui/live-process-timer";

interface ComparisonViewProps {
  candidateIds: string[];
  selectedJobId: string | null;
  jobs: JobDescription[];
  onBackToPipeline: () => void;
  onOpenEvaluation: (candidateId: string) => void;
  onOpenInterview: (candidateId: string) => void;
  onSelectCandidateIds?: (ids: string[]) => void;
  onSelectJob?: (jobId: string) => void;
}

export function ComparisonView({
  candidateIds,
  selectedJobId,
  jobs,
  onBackToPipeline,
  onOpenEvaluation,
  onOpenInterview,
  onSelectCandidateIds,
  onSelectJob,
}: ComparisonViewProps) {
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>(candidateIds || []);
  const [activeJobId, setActiveJobId] = useState<string | null>(selectedJobId || (jobs[0]?.id ?? null));
  const [report, setReport] = useState<CandidateComparisonReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const compareTimer = useProcessTimer();
  const [lastCompareDuration, setLastCompareDuration] = useState<number | null>(null);

  useEffect(() => {
    if (candidateIds && candidateIds.length > 0) {
      setSelectedIds(candidateIds);
    }
  }, [candidateIds]);

  useEffect(() => {
    if (selectedJobId && selectedJobId !== activeJobId) {
      setActiveJobId(selectedJobId);
    }
  }, [selectedJobId]);

  // Fetch candidate cohort list
  useEffect(() => {
    api.getCandidates()
      .then((data) => {
        if (Array.isArray(data)) setCandidates(data);
      })
      .catch((err) => console.warn("Failed fetching candidates in ComparisonView:", err));
  }, []);

  const activeJob = jobs.find((j) => j.id === activeJobId) || jobs[0];

  const fetchComparison = async () => {
    if (!selectedIds || selectedIds.length < 2 || !activeJob) {
      setReport(null);
      setLoading(false);
      return;
    }

    const controller = compareTimer.startTimer();
    try {
      setLoading(true);
      setError(null);
      const data = await api.compareCandidates(selectedIds, activeJob.id, controller.signal);
      const duration = compareTimer.stopTimer(true);
      if (duration !== null) {
        setLastCompareDuration(duration);
      }
      setReport(data);
    } catch (err: any) {
      if (err.name === "AbortError" || controller.signal.aborted) {
        compareTimer.stopTimer(false);
        return;
      }
      compareTimer.stopTimer(false);
      setError(err.message || "Failed to generate comparison matrix");
    } finally {
      setLoading(false);
    }
  };

  const handleCancelComparison = () => {
    compareTimer.cancelTimer();
    setLoading(false);
  };

  useEffect(() => {
    fetchComparison();
  }, [selectedIds, activeJob?.id]);

  const handleToggleCandidate = (id: string) => {
    let next: string[];
    if (selectedIds.includes(id)) {
      next = selectedIds.filter((item) => item !== id);
    } else {
      if (selectedIds.length >= 4) {
        alert("You can compare up to 4 candidates simultaneously.");
        return;
      }
      next = [...selectedIds, id];
    }
    setSelectedIds(next);
    onSelectCandidateIds?.(next);
  };

  const handleSelectJobChange = (newJobId: string) => {
    setActiveJobId(newJobId);
    onSelectJob?.(newJobId);
  };

  const handleCopySummary = () => {
    if (!report) return;
    const text = `# Multi-Candidate Benchmarking Report
Position: ${report.job_title}
Top Candidate: ${report.top_recommended_id || "N/A"}

## Executive Synthesis
${report.comparative_analysis}

## Candidates Compared
${report.candidates
  .map(
    (c) =>
      `- ${c.masked_name}: ${c.overall_score.toFixed(0)}% Overall | ${c.must_have_score.toFixed(0)}% Must-Have (${c.must_have_gaps_count} gaps) | Tier: ${c.recommendation}`
  )
  .join("\n")}
`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filteredPickerCandidates = candidates.filter((c) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const name = (c.masked_name || "").toLowerCase();
    const file = (c.original_filename || "").toLowerCase();
    const skills = (c.skills || []).map((s) => s.toLowerCase());
    return name.includes(q) || file.includes(q) || skills.some((s) => s.includes(q));
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ========================================================================= */}
      {/* 1. TOP HEADER & COMPARISON CONTROLS                                       */}
      {/* ========================================================================= */}
      <div className="p-4 rounded-2xl border border-slate-800 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBackToPipeline}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-medium transition-colors cursor-pointer border border-slate-700/60"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Pipeline</span>
            </button>
            <div>
              <h1 className="text-base md:text-lg font-bold text-white tracking-tight flex items-center gap-2">
                <span>Multi-Candidate Comparison Matrix</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-normal">
                  {selectedIds.length} Selected
                </span>
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Side-by-side criteria benchmarking, gap contrast, and algorithmic candidate selection.
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setShowAddModal(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold transition-all cursor-pointer shadow-sm"
            >
              <Plus className="w-3.5 h-3.5 text-blue-400" />
              <span>Manage Candidates ({selectedIds.length}/4)</span>
            </button>

            {report && (
              <>
                <button
                  onClick={handleCopySummary}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-colors cursor-pointer shadow-sm"
                  title="Copy formatted markdown report"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>{copied ? "Copied!" : "Copy Report"}</span>
                </button>
                <button
                  onClick={() => window.print()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-colors cursor-pointer shadow-sm"
                  title="Print comparison matrix dossier"
                >
                  <Printer className="w-3.5 h-3.5" />
                  <span>Print Dossier</span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Dual Context Bar: Active Job Selector & Selected Candidate Chips */}
        <div className="pt-3 border-t border-slate-800/80 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
          {/* Target Job Requisition Dropdown */}
          <div className="flex items-center gap-2 max-w-md">
            <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 shrink-0">
              <Briefcase className="w-4 h-4" />
            </div>
            <span className="text-slate-400 font-medium shrink-0">Benchmarking Against:</span>
            <select
              value={activeJobId || ""}
              onChange={(e) => handleSelectJobChange(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 text-xs font-semibold text-white focus:outline-none focus:border-blue-500 cursor-pointer truncate"
            >
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title} ({job.department || "General"} • {job.requirements?.length || 0} criteria)
                </option>
              ))}
            </select>
          </div>

          {/* Active Candidate Chips */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-slate-400 font-medium">Selected ({selectedIds.length}):</span>
            {selectedIds.map((id) => {
              const cand = candidates.find((c) => c.id === id);
              return (
                <span
                  key={id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-500/15 border border-blue-500/30 text-blue-200 text-xs font-medium"
                >
                  <span>{cand?.masked_name || `Candidate-${id.slice(0, 6)}`}</span>
                  <button
                    onClick={() => handleToggleCandidate(id)}
                    className="hover:text-rose-400 transition-colors cursor-pointer"
                    title="Remove from comparison"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              );
            })}
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. CANDIDATE SELECTION PICKER (Shown when fewer than 2 candidates chosen) */}
      {/* ========================================================================= */}
      {selectedIds.length < 2 ? (
        <div className="p-8 rounded-2xl border border-slate-800 bg-slate-900/40 text-center space-y-6">
          <div className="max-w-md mx-auto space-y-2">
            <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400 mx-auto shadow-inner">
              <Users2 className="w-6 h-6" />
            </div>
            <h2 className="text-base font-bold text-white">Select Candidates to Compare</h2>
            <p className="text-sm text-slate-300 leading-relaxed">
              Select between <strong>2 and 4 candidates</strong> from your registered cohort to perform a multi-dimensional benchmarking against <strong>{activeJob?.title}</strong>.
            </p>
          </div>

          {/* Search Bar */}
          <div className="max-w-md mx-auto relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by candidate name or skills..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Candidate Grid with Checkboxes */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5 text-left max-h-[480px] overflow-y-auto pr-1">
            {filteredPickerCandidates.map((cand) => {
              const isSelected = selectedIds.includes(cand.id);
              return (
                <div
                  key={cand.id}
                  onClick={() => handleToggleCandidate(cand.id)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer space-y-2.5 ${
                    isSelected
                      ? "bg-blue-600/15 border-blue-500/60 shadow-md ring-1 ring-blue-500/40"
                      : "bg-slate-950/60 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                          isSelected
                            ? "bg-blue-600 border-blue-500 text-white"
                            : "border-slate-700 bg-slate-900"
                        }`}
                      >
                        {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                      </div>
                      <span className="font-semibold text-sm text-white">
                        {cand.masked_name || `Candidate-${cand.id.slice(0, 6)}`}
                      </span>
                    </div>

                    {cand.latest_evaluation?.recommendation && (
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                          cand.latest_evaluation.recommendation === "strong_match"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : cand.latest_evaluation.recommendation === "borderline"
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-rose-500/20 text-rose-300"
                        }`}
                      >
                        {cand.latest_evaluation.recommendation.replace("_", " ").toUpperCase()}
                      </span>
                    )}
                  </div>

                  <div className="text-xs text-slate-400 truncate pl-6">
                    {cand.original_filename || "Uploaded CV document"}
                  </div>

                  <div className="flex flex-wrap gap-1 pl-6 pt-1">
                    {cand.skills.slice(0, 4).map((skill, idx) => (
                      <span
                        key={idx}
                        className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300 font-mono"
                      >
                        {skill}
                      </span>
                    ))}
                    {cand.skills.length > 4 && (
                      <span className="text-[10px] text-slate-500 font-mono">
                        +{cand.skills.length - 4}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="pt-2">
            <button
              onClick={() => fetchComparison()}
              disabled={selectedIds.length < 2}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all cursor-pointer disabled:opacity-40"
            >
              <Sparkles className="w-4 h-4 text-amber-300" />
              <span>Benchmark {selectedIds.length} Selected Candidates &rarr;</span>
            </button>
          </div>
        </div>
      ) : loading ? (
        <LiveProcessTimer
          timer={compareTimer}
          title="Synthesizing Multi-Candidate Comparison Matrix"
          description={`Benchmarking ${selectedIds.length} candidate profiles side-by-side against ${activeJob?.title || "requisition"} criteria.`}
          estimatedTimeText="Estimated time: ~10 - 25s"
          onCancel={handleCancelComparison}
        />
      ) : error ? (
        <div className="p-6 rounded-2xl border border-rose-500/30 bg-rose-950/20 text-rose-300 text-sm space-y-3 max-w-xl mx-auto text-center">
          <AlertCircle className="w-8 h-8 text-rose-400 mx-auto" />
          <div className="font-semibold">{error}</div>
          <p className="text-xs text-slate-400">
            Ensure the selected candidates have parsed qualifications and try benchmarking again.
          </p>
          <button
            onClick={() => fetchComparison()}
            className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold cursor-pointer shadow-md"
          >
            Retry Benchmarking
          </button>
        </div>
      ) : report ? (
        /* ========================================================================= */
        /* 3. ACTIVE COMPARISON MATRIX REPORT                                        */
        /* ========================================================================= */
        <div className="space-y-6 animate-in fade-in duration-200">
          {/* Executive Comparative Synthesis Banner */}
          <div className="p-5 rounded-2xl border border-blue-500/40 bg-gradient-to-r from-blue-950/40 via-slate-900/70 to-indigo-950/40 shadow-lg space-y-3 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <Trophy className="w-5 h-5 text-amber-400" />
                  <span className="text-xs font-bold uppercase tracking-wider text-blue-300">
                    Algorithmic Candidate Ranking &amp; Comparative Synthesis
                  </span>
                </div>
                {lastCompareDuration !== null && (
                  <DurationBadge duration={lastCompareDuration} label="Benchmarked in" />
                )}
              </div>
              <span className="text-xs text-slate-400 font-mono">
                Position: {report.job_title}
              </span>
            </div>

            <p className="text-sm text-slate-100 leading-relaxed font-sans max-w-5xl">
              {report.comparative_analysis}
            </p>
          </div>

          {/* Head-to-Head Candidate Summary Cards */}
          <div
            className="grid gap-4"
            style={{
              gridTemplateColumns: `repeat(${report.candidates.length}, minmax(0, 1fr))`,
            }}
          >
            {report.candidates.map((cand) => {
              const isTop = cand.candidate_id === report.top_recommended_id;
              const badge = getRecommendationBadge(cand.recommendation);

              return (
                <div
                  key={cand.candidate_id}
                  className={`p-5 rounded-2xl border transition-all space-y-3.5 relative ${
                    isTop
                      ? "bg-slate-900/90 border-blue-500/60 shadow-xl shadow-blue-500/10 ring-1 ring-blue-500/40"
                      : "bg-slate-900/50 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  {isTop && (
                    <div className="absolute top-3 right-3 flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs font-bold shadow-sm">
                      <Award className="w-3.5 h-3.5 text-amber-400" />
                      <span>Top Match</span>
                    </div>
                  )}

                  <div>
                    <div className="font-bold text-base text-white truncate pr-24">
                      {cand.masked_name}
                    </div>
                    <div className="text-xs text-slate-400 font-mono mt-0.5 truncate">
                      {cand.original_filename || `Candidate ID: ${cand.candidate_id.slice(0, 8)}`}
                    </div>
                  </div>

                  {/* Overall Match Score */}
                  <div className="space-y-1.5 pt-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400 font-medium">Overall Fit</span>
                      <span className="font-extrabold text-lg text-white tabular-nums">
                        {cand.overall_score.toFixed(0)}%
                      </span>
                    </div>
                    <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          cand.overall_score >= 70
                            ? "bg-emerald-500"
                            : cand.overall_score >= 50
                            ? "bg-amber-500"
                            : "bg-rose-500"
                        }`}
                        style={{ width: `${cand.overall_score}%` }}
                      />
                    </div>
                  </div>

                  {/* Sub-Scores */}
                  <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-slate-800/80">
                    <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800/70">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">
                        Must-Have Fit
                      </div>
                      <div className="font-bold text-sm text-slate-100 tabular-nums mt-0.5">
                        {cand.must_have_score.toFixed(0)}%
                      </div>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800/70">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">
                        Nice-to-Have
                      </div>
                      <div className="font-bold text-sm text-slate-100 tabular-nums mt-0.5">
                        {cand.nice_to_have_score.toFixed(0)}%
                      </div>
                    </div>
                  </div>

                  {/* Gaps & Verification Metric Badges */}
                  <div className="space-y-2 text-xs pt-1">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Must-Have Gaps:</span>
                      {cand.must_have_gaps_count === 0 ? (
                        <span className="text-emerald-400 font-semibold flex items-center gap-1">
                          <Check className="w-3.5 h-3.5" /> 0 Gaps
                        </span>
                      ) : (
                        <span className="text-rose-400 font-bold">
                          {cand.must_have_gaps_count} Unmet Gap{cand.must_have_gaps_count > 1 ? "s" : ""}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Citation Grounding:</span>
                      <span className="text-slate-200 font-mono font-medium">
                        {(cand.citation_verification_score * 100).toFixed(0)}%
                      </span>
                    </div>

                    <div className="flex items-center justify-between pt-1">
                      <span className="text-slate-400">Recommendation:</span>
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase ${badge.className}`}>
                        {badge.label}
                      </span>
                    </div>
                  </div>

                  {/* Quick Action Navigation Buttons */}
                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/80">
                    <button
                      onClick={() => onOpenEvaluation(cand.candidate_id)}
                      className="py-1.5 px-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold text-center transition-colors cursor-pointer"
                    >
                      Audit Citations
                    </button>
                    <button
                      onClick={() => onOpenInterview(cand.candidate_id)}
                      className="py-1.5 px-2 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 text-xs font-semibold text-center border border-blue-500/30 transition-colors cursor-pointer"
                    >
                      STAR Guide
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ========================================================================= */}
          {/* Detailed Requirement-by-Requirement Comparison Table                      */}
          {/* ========================================================================= */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-lg space-y-0">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div>
                <h2 className="text-sm md:text-base font-bold text-white">
                  Detailed Criteria Matrix ({report.matrix.length} Requirements)
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Audited against verbatim candidate CV citations and structured qualifications.
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-950/80 border-b border-slate-800 text-slate-400">
                  <tr>
                    <th className="py-3.5 px-5 w-80 text-xs font-bold uppercase tracking-wider text-slate-300">
                      Requirement Criterion
                    </th>
                    {report.candidates.map((cand) => (
                      <th key={cand.candidate_id} className="py-3.5 px-5 font-bold text-sm text-white">
                        {cand.masked_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {report.matrix.map((row) => (
                    <tr key={row.requirement_id} className="hover:bg-slate-800/25 transition-colors">
                      {/* Left Column: Requirement Title, Category & Weight */}
                      <td className="py-4 px-5 align-top">
                        <div className="space-y-1.5">
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                                row.category === "must_have"
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                              }`}
                            >
                              {row.category === "must_have" ? "Must Have" : "Nice To Have"}
                            </span>
                            <span className="text-xs text-slate-400 font-mono font-medium">
                              ({row.weight}x)
                            </span>
                          </div>
                          <div className="font-semibold text-sm text-white leading-snug">
                            {row.title}
                          </div>
                        </div>
                      </td>

                      {/* Candidate Comparison Cells */}
                      {report.candidates.map((cand) => {
                        const cell = row.candidate_cells[cand.candidate_id];
                        if (!cell) {
                          return (
                            <td key={cand.candidate_id} className="py-4 px-5 align-top text-slate-500">
                              —
                            </td>
                          );
                        }

                        const isMet = cell.status === "met";
                        const isPartial = cell.status === "partial";
                        const isClarification = cell.status === "clarification_needed";

                        return (
                          <td key={cand.candidate_id} className="py-4 px-5 align-top space-y-2.5">
                            <div className="flex items-center justify-between">
                              <span
                                className={`inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full ${
                                  isMet
                                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                    : isPartial
                                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                    : isClarification
                                    ? "bg-violet-500/20 text-violet-300 border border-violet-500/30"
                                    : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                }`}
                              >
                                {isMet ? (
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                ) : isPartial ? (
                                  <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
                                ) : isClarification ? (
                                  <HelpCircle className="w-3.5 h-3.5 text-violet-400" />
                                ) : (
                                  <XCircle className="w-3.5 h-3.5 text-rose-400" />
                                )}
                                <span>{isClarification ? "Clarification" : cell.status.replace("_", " ")}</span>
                              </span>

                              <span className="text-xs font-mono font-bold text-slate-300 tabular-nums">
                                {(cell.score * 100).toFixed(0)}%
                              </span>
                            </div>

                            {/* Reasoning in clean readable 14px font */}
                            <p className="text-sm text-slate-200 leading-relaxed font-sans">
                              {cell.reasoning}
                            </p>

                            {/* Verbatim Citation Quote */}
                            {cell.citation_quote && (
                              <div className="p-3 rounded-xl bg-slate-950/90 border-l-2 border-amber-400 border-r border-t border-b border-slate-800/80 text-xs text-amber-100/90 font-sans italic leading-relaxed space-y-1">
                                <div className="text-[10px] text-amber-400 uppercase font-semibold not-italic flex items-center gap-1 font-mono">
                                  <Quote className="w-3 h-3" />
                                  <span>Verbatim CV Citation</span>
                                </div>
                                <div>&ldquo;{cell.citation_quote}&rdquo;</div>
                              </div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}

      {/* Candidate Selection Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-xl w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Users2 className="w-5 h-5 text-blue-400" />
                <span>Manage Comparison Candidates</span>
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-400">
              Check between 2 and 4 candidates to benchmark side-by-side:
            </p>

            <div className="max-h-80 overflow-y-auto space-y-2 pr-1">
              {candidates.map((cand) => {
                const isChecked = selectedIds.includes(cand.id);
                return (
                  <div
                    key={cand.id}
                    onClick={() => handleToggleCandidate(cand.id)}
                    className={`p-3 rounded-xl border flex items-center justify-between gap-3 cursor-pointer transition-colors ${
                      isChecked
                        ? "bg-blue-600/15 border-blue-500/50 text-white"
                        : "bg-slate-950/60 border-slate-800 hover:border-slate-700 text-slate-300"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-4 h-4 rounded border flex items-center justify-center ${
                          isChecked
                            ? "bg-blue-600 border-blue-500 text-white"
                            : "border-slate-700 bg-slate-900"
                        }`}
                      >
                        {isChecked && <Check className="w-3 h-3 stroke-[3]" />}
                      </div>
                      <div>
                        <div className="font-semibold text-xs text-white">
                          {cand.masked_name || `Candidate-${cand.id.slice(0, 6)}`}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {cand.original_filename} ({cand.skills.length} skills)
                        </div>
                      </div>
                    </div>

                    {cand.latest_evaluation?.recommendation && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 font-mono text-slate-300">
                        {cand.latest_evaluation.recommendation}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              <span className="text-xs text-slate-400">
                Selected: <strong>{selectedIds.length}</strong> of 4 max
              </span>
              <button
                onClick={() => {
                  setShowAddModal(false);
                  fetchComparison();
                }}
                disabled={selectedIds.length < 2}
                className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md transition-all cursor-pointer disabled:opacity-40"
              >
                Apply &amp; Benchmark
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
