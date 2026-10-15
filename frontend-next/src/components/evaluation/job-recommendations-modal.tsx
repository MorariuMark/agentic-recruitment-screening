"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { JobDescription, JobRecommendationItem, JobRecommendationResponse } from "@/types";
import { getRecommendationBadge } from "@/lib/utils";
import {
  AlertCircle,
  Award,
  Briefcase,
  CheckCircle2,
  ChevronRight,
  Globe,
  Loader2,
  MapPin,
  RotateCw,
  Sparkles,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";

interface JobRecommendationsModalProps {
  isOpen: boolean;
  onClose: () => void;
  candidateId: string | null;
  candidateName?: string | null;
  activeJobId: string | null;
  jobs: JobDescription[];
  onSelectJob: (jobId: string) => void;
}

export function JobRecommendationsModal({
  isOpen,
  onClose,
  candidateId,
  candidateName,
  activeJobId,
  jobs,
  onSelectJob,
}: JobRecommendationsModalProps) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<JobRecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchRecommendations = async () => {
    if (!candidateId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getRecommendedJobs(candidateId, 10, undefined, activeJobId || undefined);
      const currentJob = jobs.find((j) => j.id === activeJobId);
      const currentTitle = (currentJob?.title || "").trim().toLowerCase();
      const seenTitles = new Set<string>();
      const filtered: JobRecommendationItem[] = [];

      for (const rec of res?.recommendations || []) {
        const normTitle = (rec.title || "").trim().toLowerCase();
        if (rec.job_id === activeJobId || (currentTitle && normTitle === currentTitle)) {
          continue;
        }
        if (seenTitles.has(normTitle)) {
          continue;
        }
        seenTitles.add(normTitle);
        filtered.push({
          ...rec,
          rank: filtered.length + 1,
        });
      }

      setData({
        ...res,
        recommendations: filtered,
      });
    } catch (err: any) {
      console.error("Failed to fetch recommended jobs:", err);
      setError(err?.message || "Failed to load job recommendations from database.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && candidateId) {
      fetchRecommendations();
    } else {
      setData(null);
      setError(null);
    }
  }, [isOpen, candidateId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-800 bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-emerald-500/20 to-blue-500/20 border border-emerald-500/30 text-emerald-300">
              <Sparkles className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white">Recommended Jobs from Database</h2>
                <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[11px] font-semibold text-emerald-300">
                  Top 10 Fits
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Algorithmic match ranking across all requisitions for{" "}
                <span className="text-slate-200 font-semibold">{data?.candidate_name || candidateName || "Candidate"}</span>
                {data?.total_database_jobs ? ` (${data.total_database_jobs} requisitions scanned)` : ""}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={fetchRecommendations}
              disabled={loading}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer border border-slate-800"
              title="Refresh recommendations"
            >
              <RotateCw className={`w-4 h-4 ${loading ? "animate-spin text-blue-400" : ""}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center gap-3 text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
              <div className="text-sm font-medium text-slate-200">Evaluating Job Fit Across Database Requisitions...</div>
              <p className="text-xs text-slate-400 max-w-sm text-center">
                Comparing candidate skills, experience citations, and requirement weights to compute top matching roles.
              </p>
            </div>
          ) : error ? (
            <div className="p-6 rounded-2xl border border-rose-800/50 bg-rose-950/20 text-rose-300 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 shrink-0 mt-0.5 text-rose-400" />
              <div className="space-y-1">
                <div className="font-semibold text-sm">Failed to generate recommendations</div>
                <div className="text-xs text-rose-300/80">{error}</div>
                <button
                  type="button"
                  onClick={fetchRecommendations}
                  className="mt-3 px-3 py-1.5 rounded-lg bg-rose-600/30 hover:bg-rose-600/50 text-xs font-semibold text-rose-200 transition-colors cursor-pointer"
                >
                  Retry Analysis
                </button>
              </div>
            </div>
          ) : !data || data.recommendations.length === 0 ? (
            <div className="py-16 text-center text-slate-400 space-y-2">
              <Briefcase className="w-10 h-10 text-slate-600 mx-auto" />
              <div className="text-sm font-semibold text-slate-300">No Job Requisitions Found</div>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                No active job requisitions are stored in the database to recommend against.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs text-slate-400 px-1">
                <span>
                  Showing {data.recommendations.length} top matching roles, ranked descending by overall fit score.
                </span>
                <span className="text-[11px] text-slate-400">Click &ldquo;Select Requisition&rdquo; to audit match</span>
              </div>

              {data.recommendations.map((rec: JobRecommendationItem) => {
                const isCurrent = activeJobId === rec.job_id;
                const recBadge = getRecommendationBadge(rec.recommendation);

                // Rank styling
                let rankBadgeClass = "bg-slate-800 border-slate-700 text-slate-300";
                if (rec.rank === 1) rankBadgeClass = "bg-amber-500/20 border-amber-500/50 text-amber-300 font-bold shadow-sm shadow-amber-500/10";
                else if (rec.rank === 2) rankBadgeClass = "bg-slate-300/20 border-slate-400/50 text-slate-200 font-bold";
                else if (rec.rank === 3) rankBadgeClass = "bg-amber-700/20 border-amber-600/50 text-amber-200 font-bold";

                // Score bar color
                let scoreColor = "bg-emerald-500";
                let scoreTextColor = "text-emerald-400";
                if (rec.overall_score < 50) {
                  scoreColor = "bg-rose-500";
                  scoreTextColor = "text-rose-400";
                } else if (rec.overall_score < 70) {
                  scoreColor = "bg-amber-500";
                  scoreTextColor = "text-amber-400";
                }

                return (
                  <div
                    key={rec.job_id}
                    className={`p-4 rounded-xl border transition-all ${
                      isCurrent
                        ? "border-blue-500/60 bg-blue-950/20 ring-1 ring-blue-500/30"
                        : "border-slate-800 bg-slate-950/50 hover:border-slate-700/80 hover:bg-slate-950/80"
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      {/* Left: Rank, Title, Department, Meta */}
                      <div className="flex items-start gap-3.5 flex-1 min-w-0">
                        <span
                          className={`w-8 h-8 rounded-xl border flex items-center justify-center text-xs shrink-0 mt-0.5 ${rankBadgeClass}`}
                        >
                          #{rec.rank}
                        </span>

                        <div className="space-y-1.5 flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="text-sm font-bold text-white hover:text-blue-300 transition-colors truncate">
                              {rec.title}
                            </h3>
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide ${recBadge.className}`}
                            >
                              {recBadge.label}
                            </span>
                            {isCurrent && (
                              <span className="px-2 py-0.5 rounded-full bg-blue-500/20 border border-blue-500/40 text-[10px] font-semibold text-blue-300">
                                Current Audit Job
                              </span>
                            )}
                            {rec.has_full_evaluation && (
                              <span className="px-2 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-[10px] font-medium text-indigo-300 flex items-center gap-1">
                                <Award className="w-3 h-3 text-indigo-400" />
                                Full Evaluation
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
                            {rec.department && (
                              <span className="flex items-center gap-1">
                                <Briefcase className="w-3 h-3 text-slate-500" />
                                {rec.department}
                              </span>
                            )}
                            {rec.location && (
                              <span className="flex items-center gap-1">
                                <MapPin className="w-3 h-3 text-slate-500" />
                                {rec.location}
                              </span>
                            )}
                            {rec.work_model && (
                              <span className="flex items-center gap-1 capitalize">
                                <Globe className="w-3 h-3 text-slate-500" />
                                {rec.work_model}
                              </span>
                            )}
                            {rec.seniority_level && (
                              <span className="capitalize px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px]">
                                {rec.seniority_level}
                              </span>
                            )}
                          </div>

                          {/* Grounded Match Justification */}
                          {rec.justification && (
                            <p className="text-xs text-slate-300 leading-relaxed bg-slate-900/70 border border-slate-800/80 rounded-lg px-2.5 py-2 mt-1">
                              {rec.justification}
                            </p>
                          )}

                          {/* Strengths / Matching Skills & Missing Requirements Tags */}
                          {(rec.matching_skills.length > 0 ||
                            rec.key_strengths.length > 0 ||
                            (rec.missing_requirements && rec.missing_requirements.length > 0)) && (
                            <div className="flex items-center gap-1.5 flex-wrap pt-1">
                              {rec.matching_skills.map((skill, sIdx) => (
                                <span
                                  key={`skill-${sIdx}`}
                                  className="px-2 py-0.5 rounded-md bg-emerald-950/50 border border-emerald-500/30 text-[10px] font-mono text-emerald-300"
                                >
                                  +{skill}
                                </span>
                              ))}
                              {rec.key_strengths.map((st, stIdx) => (
                                <span
                                  key={`str-${stIdx}`}
                                  className="px-2 py-0.5 rounded-md bg-slate-900/80 border border-slate-800 text-[10px] text-slate-300 max-w-[220px] truncate"
                                  title={st}
                                >
                                  ✓ {st}
                                </span>
                              ))}
                              {(rec.missing_requirements || []).map((gap, gIdx) => (
                                <span
                                  key={`gap-${gIdx}`}
                                  className="px-2 py-0.5 rounded-md bg-amber-950/40 border border-amber-500/30 text-[10px] text-amber-300 max-w-[220px] truncate"
                                  title={`Potential gap: ${gap}`}
                                >
                                  ⚠ Gap: {gap}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Right: Scores & Switch Button */}
                      <div className="flex items-center gap-5 sm:shrink-0 self-end sm:self-center">
                        {/* Score Metric */}
                        <div className="text-right">
                          <div className="flex items-baseline justify-end gap-1">
                            <span className={`text-xl font-extrabold font-mono tracking-tight ${scoreTextColor}`}>
                              {rec.overall_score.toFixed(1)}%
                            </span>
                            <span className="text-[10px] uppercase font-semibold text-slate-500">Fit</span>
                          </div>
                          <div className="w-24 h-1.5 rounded-full bg-slate-800 overflow-hidden mt-1 ml-auto">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${scoreColor}`}
                              style={{ width: `${Math.min(100, Math.max(0, rec.overall_score))}%` }}
                            />
                          </div>
                          <div className="text-[10px] text-slate-400 mt-1 flex items-center justify-end gap-2">
                            <span>Must: <strong className="text-slate-300">{rec.must_have_score.toFixed(0)}%</strong></span>
                            <span>Nice: <strong className="text-slate-300">{rec.nice_to_have_score.toFixed(0)}%</strong></span>
                          </div>
                        </div>

                        {/* Action Switch Button */}
                        <button
                          type="button"
                          onClick={() => {
                            onSelectJob(rec.job_id);
                            onClose();
                          }}
                          className={`px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                            isCurrent
                              ? "bg-slate-800 text-slate-300 border border-slate-700"
                              : "bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-600/20 active:scale-95"
                          }`}
                        >
                          <span>{isCurrent ? "Active Job" : "Select Job"}</span>
                          <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/60 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Scores synthesize requirement weights, semantic ChromaDB vectors &amp; skill overlap.</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
