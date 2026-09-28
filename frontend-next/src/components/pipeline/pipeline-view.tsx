"use client";

import { useState, useEffect, useRef } from "react";
import { CandidateSummary, JobDescription, BatchJobStatus } from "@/types";
import { api } from "@/lib/api";
import { formatPercent, getRecommendationBadge } from "@/lib/utils";
import {
  AlertTriangle,
  ArrowUpDown,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileCheck,
  FileText,
  FileUp,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Upload,
  UserCheck,
  XCircle,
} from "lucide-react";

interface PipelineViewProps {
  selectedJobId: string | null;
  jobs: JobDescription[];
  onSelectCandidate: (candidateId: string) => void;
  onOpenEvaluation: (candidateId: string) => void;
  onOpenInterview: (candidateId: string) => void;
}

export function PipelineView({
  selectedJobId,
  jobs,
  onSelectCandidate,
  onOpenEvaluation,
  onOpenInterview,
}: PipelineViewProps) {
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterRecommendation, setFilterRecommendation] = useState<string>("ALL");
  const [isUploading, setIsUploading] = useState(false);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<{
    status: string;
    percentage: number;
    processed: number;
    total: number;
    lastEvent: string;
  } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchCandidates = async () => {
    try {
      setLoading(true);
      const data = await api.getCandidates();
      setCandidates(data);
    } catch (err) {
      console.error("Failed fetching candidates:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, []);

  // Listen for SSE events if activeBatchId changes
  useEffect(() => {
    if (!activeBatchId) return;

    const cleanup = api.createBatchSSEStream(
      activeBatchId,
      (eventName, data) => {
        if (eventName === "initial_state" || eventName === "file_completed") {
          setBatchProgress({
            status: data.status || "PROCESSING",
            percentage: data.progress_percentage || 0,
            processed: data.processed_count || data.processed_files || 0,
            total: data.total_files || 0,
            lastEvent: `Processed ${data.filename || "file"}`,
          });
        } else if (eventName === "file_processing") {
          setBatchProgress((prev) => ({
            status: "PROCESSING",
            percentage: prev?.percentage || 0,
            processed: prev?.processed || 0,
            total: data.total_files || 0,
            lastEvent: `Analyzing ${data.filename}...`,
          }));
        } else if (eventName === "batch_completed" || eventName === "complete") {
          setBatchProgress({
            status: "COMPLETED",
            percentage: 100,
            processed: data.total_files || 0,
            total: data.total_files || 0,
            lastEvent: "Batch screening complete!",
          });
          fetchCandidates();
          setTimeout(() => {
            setActiveBatchId(null);
            setBatchProgress(null);
          }, 4000);
        }
      },
      (err) => {
        console.error("SSE stream error:", err);
      }
    );

    return () => cleanup();
  }, [activeBatchId]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    try {
      setIsUploading(true);
      const fileArray = Array.from(files);
      const res = await api.uploadBatchCVs(fileArray, selectedJobId || undefined);
      setActiveBatchId(res.batch_id);
      setBatchProgress({
        status: "PROCESSING",
        percentage: 0,
        processed: 0,
        total: fileArray.length,
        lastEvent: `Enqueued ${fileArray.length} resumes...`,
      });
    } catch (err: any) {
      alert(`Batch upload failed: ${err.message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const filteredCandidates = candidates.filter((c) => {
    const matchesSearch =
      c.masked_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.skills.some((s) => s.toLowerCase().includes(searchQuery.toLowerCase()));

    if (!matchesSearch) return false;
    if (filterRecommendation === "ALL") return true;

    return c.latest_evaluation?.recommendation === filterRecommendation.toLowerCase();
  });

  return (
    <div className="space-y-6">
      {/* Top Banner & Batch Dropzone */}
      <div className="flex flex-col lg:flex-row gap-4 items-stretch justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>Candidate Screening Pipeline</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-normal">
              {candidates.length} Profiles
            </span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Asymmetric RAG candidate retrieval, automated PII redaction, and deterministic scoring.
          </p>
        </div>

        {/* Upload Action */}
        <div className="flex items-center gap-2">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            multiple
            accept=".pdf,.docx,.txt"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-all cursor-pointer disabled:opacity-50"
          >
            {isUploading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <FileUp className="w-3.5 h-3.5" />
            )}
            <span>Batch Upload Resumes</span>
          </button>

          <button
            onClick={fetchCandidates}
            className="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-400 hover:text-white transition-colors"
            title="Refresh candidate data"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Live SSE Progress Ticker */}
      {batchProgress && (
        <div className="p-4 rounded-xl bg-blue-950/40 border border-blue-500/30 backdrop-blur-md space-y-2 animate-in fade-in duration-200">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 text-blue-300 font-medium">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
              <span>Real-Time Batch Evaluation</span>
              <span className="text-[10px] text-blue-400/80 font-mono">
                ({batchProgress.processed}/{batchProgress.total})
              </span>
            </div>
            <div className="font-mono text-xs text-blue-300 font-bold">
              {formatPercent(batchProgress.percentage)}
            </div>
          </div>

          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300 rounded-full"
              style={{ width: `${batchProgress.percentage}%` }}
            />
          </div>

          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>{batchProgress.lastEvent}</span>
            <span className="uppercase text-[9px] font-semibold tracking-wider text-blue-400">
              SSE Stream Active
            </span>
          </div>
        </div>
      )}

      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between bg-slate-900/60 p-3 rounded-xl border border-slate-800">
        <div className="relative w-full sm:w-80">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search by alias, skills (e.g. Python, Docker)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="w-3.5 h-3.5 text-slate-500" />
          <div className="flex rounded-lg bg-slate-950 p-0.5 border border-slate-800 text-[11px]">
            {["ALL", "STRONG_MATCH", "BORDERLINE", "REJECT"].map((filter) => (
              <button
                key={filter}
                onClick={() => setFilterRecommendation(filter)}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterRecommendation === filter
                    ? "bg-slate-800 text-white font-medium"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {filter === "ALL" ? "All" : filter === "STRONG_MATCH" ? "Strong" : filter === "BORDERLINE" ? "Borderline" : "Reject"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Candidates Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-12 flex flex-col items-center justify-center gap-3 text-slate-500 text-xs">
            <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            <span>Retrieving indexed talent records...</span>
          </div>
        ) : filteredCandidates.length === 0 ? (
          <div className="p-12 flex flex-col items-center justify-center gap-2 text-center text-slate-500 text-xs">
            <FileText className="w-8 h-8 text-slate-600 stroke-1" />
            <span className="font-medium text-slate-400">No candidates match your criteria</span>
            <span className="text-[11px]">Upload new resumes or modify the active filter.</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/80 border-b border-slate-800 text-slate-400 font-medium">
                <tr>
                  <th className="py-3 px-4">Candidate Profile</th>
                  <th className="py-3 px-4">Experience</th>
                  <th className="py-3 px-4">Core Skills</th>
                  <th className="py-3 px-4 text-center">Score Breakdown</th>
                  <th className="py-3 px-4 text-center">Decision Tier</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredCandidates.map((candidate) => {
                  const evalData = candidate.latest_evaluation;
                  const badge = evalData
                    ? getRecommendationBadge(evalData.recommendation)
                    : { label: "Unevaluated", className: "bg-slate-800 text-slate-400" };

                  const displayName =
                    candidate.masked_name && candidate.masked_name !== "[CANDIDATE_NAME]"
                      ? candidate.masked_name
                      : `Candidate-${candidate.id.slice(0, 6).toUpperCase()}${
                          candidate.original_filename ? ` (${candidate.original_filename})` : ""
                        }`;

                  return (
                    <tr
                      key={candidate.id}
                      className="hover:bg-slate-800/30 transition-colors group cursor-pointer"
                      onClick={() => onSelectCandidate(candidate.id)}
                    >
                      {/* Masked Profile */}
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-slate-200 group-hover:text-blue-400 transition-colors">
                          {displayName}
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                          ID: {candidate.id.slice(0, 8)}... • {candidate.chunks_indexed} vectors
                        </div>
                      </td>

                      {/* Experience */}
                      <td className="py-3.5 px-4 text-slate-300">
                        {candidate.total_years_experience !== null && candidate.total_years_experience !== undefined ? (
                          <div className="flex items-center gap-1.5">
                            <Clock className="w-3.5 h-3.5 text-slate-500" />
                            <span>{candidate.total_years_experience} yrs</span>
                          </div>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>

                      {/* Top Skills Tags */}
                      <td className="py-3.5 px-4 max-w-[240px]">
                        <div className="flex flex-wrap gap-1">
                          {candidate.skills.slice(0, 3).map((skill, idx) => (
                            <span
                              key={idx}
                              className="px-1.5 py-0.5 rounded bg-slate-800/80 text-slate-300 text-[10px] font-mono border border-slate-700/50"
                            >
                              {skill}
                            </span>
                          ))}
                          {candidate.skills.length > 3 && (
                            <span className="px-1.5 py-0.5 rounded bg-slate-800/40 text-slate-500 text-[10px] font-mono">
                              +{candidate.skills.length - 3}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Score Breakdown */}
                      <td className="py-3.5 px-4 text-center">
                        {evalData ? (
                          <div className="inline-flex flex-col items-center">
                            <div className="text-sm font-bold text-slate-100 tabular-nums">
                              {evalData.overall_score.toFixed(0)}%
                            </div>
                            <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
                              <span title="Must Have Score">MH: {evalData.must_have_score.toFixed(0)}%</span>
                              {evalData.must_have_gaps_count > 0 && (
                                <span className="text-rose-400 font-bold" title="Must-Have Gaps">
                                  ({evalData.must_have_gaps_count} gap)
                                </span>
                              )}
                            </div>
                          </div>
                        ) : (
                          <span className="text-slate-600 font-mono text-[11px]">—</span>
                        )}
                      </td>

                      {/* Decision Tier */}
                      <td className="py-3.5 px-4 text-center">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${badge.className}`}
                        >
                          {badge.label}
                        </span>
                        {evalData?.hitl_validated && (
                          <div className="text-[9px] text-emerald-400 flex items-center justify-center gap-0.5 mt-0.5">
                            <UserCheck className="w-2.5 h-2.5" />
                            <span>Recruiter Validated</span>
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right">
                        <div
                          className="flex items-center justify-end gap-1.5"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={() => onOpenEvaluation(candidate.id)}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] font-medium transition-colors"
                            title="Audit verbatim citations and submit HITL decision"
                          >
                            Citations
                          </button>
                          <button
                            onClick={() => onOpenInterview(candidate.id)}
                            className="px-2.5 py-1 rounded bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 text-[11px] font-medium border border-blue-500/20 transition-colors"
                            title="Generate role-tailored STAR interview guide"
                          >
                            Interview
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
