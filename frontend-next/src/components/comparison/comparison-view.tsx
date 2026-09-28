"use client";

import { useState, useEffect } from "react";
import { CandidateComparisonReport, JobDescription } from "@/types";
import { api } from "@/lib/api";
import { formatPercent, getRecommendationBadge } from "@/lib/utils";
import {
  AlertCircle,
  Award,
  BarChart3,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock,
  Copy,
  ExternalLink,
  FileCheck2,
  FileText,
  Loader2,
  Printer,
  Quote,
  ShieldCheck,
  Sparkles,
  Trophy,
  User,
  Users2,
  XCircle,
} from "lucide-react";

interface ComparisonViewProps {
  candidateIds: string[];
  selectedJobId: string | null;
  jobs: JobDescription[];
  onBackToPipeline: () => void;
  onOpenEvaluation: (candidateId: string) => void;
  onOpenInterview: (candidateId: string) => void;
}

export function ComparisonView({
  candidateIds,
  selectedJobId,
  jobs,
  onBackToPipeline,
  onOpenEvaluation,
  onOpenInterview,
}: ComparisonViewProps) {
  const [report, setReport] = useState<CandidateComparisonReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const activeJob = jobs.find((j) => j.id === selectedJobId) || jobs[0];

  useEffect(() => {
    async function fetchComparison() {
      if (!candidateIds || candidateIds.length < 2 || !activeJob) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        const data = await api.compareCandidates(candidateIds, activeJob.id);
        setReport(data);
      } catch (err: any) {
        setError(err.message || "Failed to generate comparison matrix");
      } finally {
        setLoading(false);
      }
    }

    fetchComparison();
  }, [candidateIds, activeJob?.id]);

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

  if (!candidateIds || candidateIds.length < 2) {
    return (
      <div className="p-12 text-center text-slate-500 text-xs space-y-3">
        <Users2 className="w-8 h-8 text-slate-600 mx-auto stroke-1" />
        <div className="font-semibold text-slate-400">Select at least 2 candidates to compare</div>
        <p className="text-[11px] max-w-sm mx-auto">
          Return to the Candidate Pipeline and select between 2 and 4 candidates using the checkboxes.
        </p>
        <button
          onClick={onBackToPipeline}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white text-xs font-semibold cursor-pointer"
        >
          Go to Pipeline
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Navigation & Actions */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <button
              onClick={onBackToPipeline}
              className="text-xs text-blue-400 hover:text-blue-300 font-medium cursor-pointer"
            >
              ← Back to Pipeline
            </button>
            <span className="text-slate-600">•</span>
            <span className="text-xs text-slate-400">
              Comparing {candidateIds.length} Candidates
            </span>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-white mt-1 flex items-center gap-2">
            <span>Multi-Candidate Comparison Matrix</span>
          </h1>
          <p className="text-xs text-slate-400">
            Side-by-side criteria benchmarking, gap contrast, and algorithmic candidate selection.
          </p>
        </div>

        {report && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopySummary}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-colors cursor-pointer"
            >
              <Copy className="w-3.5 h-3.5" />
              <span>{copied ? "Copied Report!" : "Copy Report"}</span>
            </button>
            <button
              onClick={() => window.print()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-colors cursor-pointer"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print Dossier</span>
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="p-16 flex flex-col items-center justify-center gap-3 text-slate-500 text-xs">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          <span>Generating multi-candidate comparison matrix...</span>
        </div>
      ) : error ? (
        <div className="p-6 rounded-xl border border-rose-500/30 bg-rose-950/20 text-rose-300 text-xs">
          Error loading comparison: {error}
        </div>
      ) : report ? (
        <div className="space-y-6">
          {/* Executive Comparative Synthesis Banner */}
          <div className="p-5 rounded-xl border border-blue-500/30 bg-blue-950/20 space-y-3 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Trophy className="w-5 h-5 text-amber-400" />
                <span className="text-xs font-bold uppercase tracking-wider text-blue-400">
                  Algorithmic Candidate Ranking
                </span>
              </div>
              <span className="text-xs text-slate-400 font-mono">
                Requisition: {report.job_title}
              </span>
            </div>
            <p className="text-xs text-slate-200 leading-relaxed max-w-4xl">
              {report.comparative_analysis}
            </p>
          </div>

          {/* Head-to-Head Candidate Cards */}
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
                  className={`p-4 rounded-xl border transition-all space-y-3 relative ${
                    isTop
                      ? "bg-slate-900/80 border-blue-500/50 shadow-lg shadow-blue-500/5"
                      : "bg-slate-900/40 border-slate-800"
                  }`}
                >
                  {isTop && (
                    <div className="absolute top-2.5 right-2.5 flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-bold">
                      <Award className="w-3 h-3" />
                      <span>Top Choice</span>
                    </div>
                  )}

                  <div>
                    <div className="font-bold text-sm text-white truncate pr-20">
                      {cand.masked_name}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono mt-0.5 truncate">
                      {cand.original_filename || `ID: ${cand.candidate_id.slice(0, 8)}`}
                    </div>
                  </div>

                  {/* Overall Score */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">Overall Match</span>
                      <span className="font-bold text-white tabular-nums">
                        {cand.overall_score.toFixed(0)}%
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
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
                  <div className="grid grid-cols-2 gap-2 text-[11px] pt-1 border-t border-slate-800/80">
                    <div className="p-2 rounded bg-slate-950 border border-slate-800/60">
                      <div className="text-[9px] text-slate-500 uppercase font-semibold">
                        Must-Have
                      </div>
                      <div className="font-bold text-slate-200 tabular-nums">
                        {cand.must_have_score.toFixed(0)}%
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800/60">
                      <div className="text-[9px] text-slate-500 uppercase font-semibold">
                        Nice-to-Have
                      </div>
                      <div className="font-bold text-slate-200 tabular-nums">
                        {cand.nice_to_have_score.toFixed(0)}%
                      </div>
                    </div>
                  </div>

                  {/* Metrics Badges */}
                  <div className="space-y-1.5 text-[10px]">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Must-Have Gaps:</span>
                      {cand.must_have_gaps_count === 0 ? (
                        <span className="text-emerald-400 font-semibold flex items-center gap-1">
                          <Check className="w-3 h-3" /> 0 Gaps
                        </span>
                      ) : (
                        <span className="text-rose-400 font-bold">
                          {cand.must_have_gaps_count} Unmet Gap{cand.must_have_gaps_count > 1 ? "s" : ""}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Citation CVS:</span>
                      <span className="text-slate-200 font-mono">
                        {(cand.citation_verification_score * 100).toFixed(0)}%
                      </span>
                    </div>

                    <div className="flex items-center justify-between pt-1">
                      <span className="text-slate-400">Recommendation:</span>
                      <span className={`px-2 py-0.5 rounded-full font-medium ${badge.className}`}>
                        {badge.label}
                      </span>
                    </div>
                  </div>

                  {/* Quick Jump Buttons */}
                  <div className="flex items-center gap-2 pt-2 border-t border-slate-800/80">
                    <button
                      onClick={() => onOpenEvaluation(cand.candidate_id)}
                      className="flex-1 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] font-medium text-center transition-colors cursor-pointer"
                    >
                      Audit Citations
                    </button>
                    <button
                      onClick={() => onOpenInterview(cand.candidate_id)}
                      className="flex-1 py-1 rounded bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 text-[10px] font-medium text-center border border-blue-500/20 transition-colors cursor-pointer"
                    >
                      Interview Plan
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Criteria-by-Criteria Requirement Comparison Grid */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/30 overflow-hidden shadow-sm space-y-0">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">
                Detailed Requirement-by-Requirement Comparison ({report.matrix.length} Rules)
              </h2>
              <span className="text-xs text-slate-400">
                Ground truth verified with verbatim CV citations
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400">
                  <tr>
                    <th className="py-3 px-4 w-72">Requirement Criterion</th>
                    {report.candidates.map((cand) => (
                      <th key={cand.candidate_id} className="py-3 px-4 font-semibold text-white">
                        {cand.masked_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {report.matrix.map((row) => (
                    <tr key={row.requirement_id} className="hover:bg-slate-800/20 transition-colors">
                      {/* Left: Requirement Details */}
                      <td className="py-4 px-4 align-top">
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                                row.category === "must_have"
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                              }`}
                            >
                              {row.category === "must_have" ? "Must Have" : "Nice To Have"}
                            </span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              ({row.weight}x)
                            </span>
                          </div>
                          <div className="font-semibold text-xs text-slate-200">
                            {row.title}
                          </div>
                        </div>
                      </td>

                      {/* Candidate Comparison Cells */}
                      {report.candidates.map((cand) => {
                        const cell = row.candidate_cells[cand.candidate_id];
                        if (!cell) {
                          return (
                            <td key={cand.candidate_id} className="py-4 px-4 align-top text-slate-500">
                              —
                            </td>
                          );
                        }

                        const isMet = cell.status === "met";
                        const isPartial = cell.status === "partial";
                        const isNotMet = cell.status === "not_met";

                        return (
                          <td key={cand.candidate_id} className="py-4 px-4 align-top space-y-2">
                            <div className="flex items-center justify-between">
                              <span
                                className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                                  isMet
                                    ? "bg-emerald-500/20 text-emerald-300"
                                    : isPartial
                                    ? "bg-amber-500/20 text-amber-300"
                                    : "bg-rose-500/20 text-rose-300"
                                }`}
                              >
                                {isMet ? (
                                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                                ) : isPartial ? (
                                  <AlertCircle className="w-3 h-3 text-amber-400" />
                                ) : (
                                  <XCircle className="w-3 h-3 text-rose-400" />
                                )}
                                <span>{cell.status}</span>
                              </span>

                              <span className="text-xs font-mono font-bold text-slate-300 tabular-nums">
                                {(cell.score * 100).toFixed(0)}%
                              </span>
                            </div>

                            <p className="text-[11px] text-slate-400 leading-snug">
                              {cell.reasoning}
                            </p>

                            {cell.citation_quote && (
                              <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[10px] text-slate-300 font-mono italic">
                                &ldquo;{cell.citation_quote}&rdquo;
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
    </div>
  );
}
