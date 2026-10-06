"use client";

import { useState, useEffect, useRef } from "react";
import {
  CandidateSummary,
  JobDescription,
  CVUploadResponse,
} from "@/types";
import { api } from "@/lib/api";
import { formatPercent, getRecommendationBadge } from "@/lib/utils";
import {
  AlertTriangle,
  ArrowUpDown,
  Award,
  BarChart3,
  Bookmark,
  Briefcase,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  Eye,
  FileCheck,
  FileText,
  FileUp,
  Filter,
  FolderGit2,
  Globe,
  GraduationCap,
  Languages,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Trash2,
  Upload,
  UserCheck,
  Users2,
  X,
  XCircle,
} from "lucide-react";
import { LiveProcessTimer, DurationBadge, useProcessTimer } from "@/components/ui/live-process-timer";
import { TokenUsageBadge } from "@/components/ui/token-counter";

interface PipelineViewProps {
  selectedJobId: string | null;
  jobs: JobDescription[];
  onSelectCandidate: (candidateId: string) => void;
  onSelectJob?: (jobId: string) => void;
  onOpenEvaluation: (candidateId: string, targetJobId?: string, autoRun?: boolean) => void;
  onOpenInterview: (candidateId: string) => void;
  onOpenComparison?: (candidateIds: string[]) => void;
  onRefreshCandidates?: () => Promise<void> | void;
  onOpenSettings?: () => void;
}

export function PipelineView({
  selectedJobId,
  jobs,
  onSelectCandidate,
  onSelectJob,
  onOpenEvaluation,
  onOpenInterview,
  onOpenComparison,
  onRefreshCandidates,
  onOpenSettings,
}: PipelineViewProps) {
  // Navigation Mode: "single" is the default section
  const [activeSection, setActiveSection] = useState<"single" | "batch">("single");

  // Single CV Ingestion & Extraction State
  const [singleExtraction, setSingleExtraction] = useState<CVUploadResponse | null>(null);
  const [isUploadingSingle, setIsUploadingSingle] = useState(false);
  const [singleUploadError, setSingleUploadError] = useState<string | null>(null);
  const singleFileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [activeModelName, setActiveModelName] = useState<string>("Active AI Model");

  // Live Timer and Cancellation Hooks for AI Processing
  const singleTimer = useProcessTimer();
  const batchTimer = useProcessTimer();
  const [lastUploadDuration, setLastUploadDuration] = useState<number | null>(null);
  const [lastBatchDuration, setLastBatchDuration] = useState<number | null>(null);

  // Target job selection for Phase 2 evaluation
  const [targetJobId, setTargetJobId] = useState<string>(selectedJobId || (jobs[0]?.id || ""));

  useEffect(() => {
    const fetchActiveModel = async () => {
      try {
        const s = await api.getLLMSettings();
        const prov = s.active_provider;
        const mod = s.active_model;
        const catalogInfo = s.providers_catalog?.[prov]?.models?.find((m: any) => m.id === mod);
        setActiveModelName(catalogInfo?.name || mod || `${prov.toUpperCase()} AI`);
      } catch {
        // preserve current fallback
      }
    };
    fetchActiveModel();
    const interval = setInterval(fetchActiveModel, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedJobId) {
      setTargetJobId(selectedJobId);
    } else if (jobs.length > 0 && !targetJobId) {
      setTargetJobId(jobs[0].id);
    }
  }, [selectedJobId, jobs]);

  // Restore singleExtraction and activeSection from localStorage on mount
  useEffect(() => {
    try {
      const savedExtraction = localStorage.getItem("atos_pipeline_single_extraction");
      if (savedExtraction) {
        const parsed = JSON.parse(savedExtraction);
        setSingleExtraction(parsed);
        if (parsed?.candidate_id) {
          onSelectCandidate(parsed.candidate_id);
        }
      }
      const savedSection = localStorage.getItem("atos_pipeline_active_section");
      if (savedSection === "single" || savedSection === "batch") {
        setActiveSection(savedSection);
      }
    } catch (err) {
      console.warn("Failed restoring pipeline state from localStorage:", err);
    }
  }, []);

  // Listen to global reset-session events to return workspace to completely fresh state
  useEffect(() => {
    const handleReset = () => {
      setSingleExtraction(null);
      setActiveSection("single");
      setSelectedForComparison([]);
      setSearchQuery("");
      setFilterRecommendation("ALL");
      setSingleUploadError(null);
      if (singleFileInputRef.current) singleFileInputRef.current.value = "";
      if (batchFileInputRef.current) batchFileInputRef.current.value = "";
    };
    window.addEventListener("atos:reset-session", handleReset);
    return () => window.removeEventListener("atos:reset-session", handleReset);
  }, []);

  const updateSingleExtraction = (data: CVUploadResponse | null) => {
    setSingleExtraction(data);
    try {
      if (data) {
        localStorage.setItem("atos_pipeline_single_extraction", JSON.stringify(data));
        if (data.candidate_id) {
          onSelectCandidate(data.candidate_id);
        }
      } else {
        localStorage.removeItem("atos_pipeline_single_extraction");
        localStorage.removeItem("atos_session_selected_candidate_id");
        onSelectCandidate("");
        setSingleUploadError(null);
        if (singleFileInputRef.current) singleFileInputRef.current.value = "";
      }
    } catch (err) {
      console.warn("Failed saving extraction to localStorage:", err);
    }
  };

  const updateActiveSection = (section: "single" | "batch") => {
    setActiveSection(section);
    try {
      localStorage.setItem("atos_pipeline_active_section", section);
    } catch (err) {
      console.warn("Failed saving active section to localStorage:", err);
    }
  };

  // Accordion Expand States in Single View
  const [expandedSections, setExpandedSections] = useState({
    experience: true,
    education: true,
    projects: true,
    custom: true,
    miscellaneous: true,
    publications: true,
    logistics: true,
  });

  const toggleSection = (key: keyof typeof expandedSections) => {
    setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Cohort & Batch State
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterRecommendation, setFilterRecommendation] = useState<string>("ALL");
  const [isUploadingBatch, setIsUploadingBatch] = useState(false);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<{
    status: string;
    percentage: number;
    processed: number;
    total: number;
    lastEvent: string;
  } | null>(null);

  const [selectedForComparison, setSelectedForComparison] = useState<string[]>([]);
  const batchFileInputRef = useRef<HTMLInputElement>(null);

  const activeJob = jobs.find((j) => j.id === selectedJobId) || jobs[0];

  const toggleCandidateSelect = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedForComparison((prev) => {
      if (prev.includes(id)) {
        return prev.filter((item) => item !== id);
      }
      if (prev.length >= 4) {
        alert("You can compare up to 4 candidates simultaneously.");
        return prev;
      }
      return [...prev, id];
    });
  };

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
          if (eventName === "file_completed") {
            fetchCandidates();
            if (onRefreshCandidates) onRefreshCandidates();
          }
        } else if (eventName === "file_processing") {
          setBatchProgress((prev) => ({
            status: "PROCESSING",
            percentage: prev?.percentage || 0,
            processed: prev?.processed || 0,
            total: data.total_files || 0,
            lastEvent: `Analyzing ${data.filename}...`,
          }));
        } else if (eventName === "batch_completed" || eventName === "complete") {
          const duration = batchTimer.stopTimer(true);
          if (duration !== null) {
            setLastBatchDuration(duration);
          }
          setBatchProgress({
            status: "COMPLETED",
            percentage: 100,
            processed: data.total_files || 0,
            total: data.total_files || 0,
            lastEvent: `Batch screening complete${duration ? ` in ${duration.toFixed(1)}s` : ""}!`,
          });
          fetchCandidates();
          if (onRefreshCandidates) onRefreshCandidates();
          setTimeout(() => {
            setActiveBatchId(null);
            setBatchProgress(null);
          }, 5000);
        }
      },
      (err) => {
        console.error("SSE stream error:", err);
      }
    );

    return () => cleanup();
  }, [activeBatchId]);

  // Handle single candidate CV upload
  const handleSingleFileUpload = async (file: File) => {
    if (!file) return;

    const controller = singleTimer.startTimer();
    try {
      setIsUploadingSingle(true);
      setSingleUploadError(null);
      const result = await api.uploadSingleCV(file, controller.signal);
      const duration = singleTimer.stopTimer(true);
      if (duration !== null) {
        setLastUploadDuration(duration);
      }
      if (result?.parsed_cv) {
        const fallbackName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
        if (!result.parsed_cv.contact_info) {
          result.parsed_cv.contact_info = { full_name: fallbackName, email: null, phone_number: null, location: null, linkedin_url: null, github_url: null };
        } else if (!result.parsed_cv.contact_info.full_name || result.parsed_cv.contact_info.full_name.includes("[CANDIDATE_NAME]")) {
          result.parsed_cv.contact_info.full_name = fallbackName;
        }
      }
      updateSingleExtraction(result);
      onSelectCandidate(result.candidate_id);
      const effectiveJobId = targetJobId || selectedJobId || (jobs[0]?.id ?? "");
      if (effectiveJobId) {
        setTargetJobId(effectiveJobId);
        onSelectJob?.(effectiveJobId);
      }
      await fetchCandidates();
      if (onRefreshCandidates) {
        await onRefreshCandidates();
      }
      setTimeout(() => {
        const el = document.getElementById("candidate-extracted-profile");
        el?.scrollIntoView({ behavior: "smooth" });
      }, 250);
    } catch (err: any) {
      if (err.name === "AbortError" || controller.signal.aborted) {
        singleTimer.stopTimer(false);
        setSingleUploadError("CV upload and parsing was cancelled by user.");
        return;
      }
      singleTimer.stopTimer(false);
      console.error("Single CV upload failed:", err);
      const msg = err.message || "Failed to process candidate CV.";
      if (
        msg.toLowerCase().includes("scanned") ||
        msg.toLowerCase().includes("flat graphic") ||
        msg.toLowerCase().includes("image-only")
      ) {
        setSingleUploadError(
          "Scanned or Image-only Document: The uploaded file has no digital text layer. Please upload a searchable PDF or a Word (.docx) document."
        );
      } else if (msg.includes("500") || msg.toLowerCase().includes("socket") || msg.toLowerCase().includes("hang up")) {
        setSingleUploadError(
          `${msg}. (Tip: If processing timed out or backend was rate-limited, candidate may already be ingested—check Cohort Directory below.)`
        );
        fetchCandidates();
      } else {
        setSingleUploadError(msg);
      }
    } finally {
      setIsUploadingSingle(false);
      if (singleFileInputRef.current) singleFileInputRef.current.value = "";
    }
  };

  const handleCancelSingleUpload = () => {
    singleTimer.cancelTimer();
    setIsUploadingSingle(false);
    setSingleUploadError("CV parsing cancelled immediately.");
  };

  // Inspect existing candidate in single extraction view
  const handleInspectCandidate = async (candidateId: string) => {
    try {
      setLoading(true);
      const detail = await api.getCandidate(candidateId);
      onSelectCandidate(candidateId);

      const raw = detail.parsed_cv;
      const anon = detail.anonymized_candidate;

      const reconstructed: CVUploadResponse = {
        candidate_id: detail.id,
        parsed_cv: {
          contact_info: raw?.contact_info || {
            full_name: detail.masked_name || `Candidate-${detail.id.slice(0, 6).toUpperCase()}`,
            email: raw?.contact_info?.email || null,
            phone_number: raw?.contact_info?.phone_number || null,
            location: raw?.contact_info?.location || null,
            linkedin_url: raw?.contact_info?.linkedin_url || null,
            github_url: raw?.contact_info?.github_url || null,
          },
          summary: raw?.summary || null,
          skills: detail.skills || [],
          experiences: (raw?.experiences || detail.experiences || []) as any,
          education: (raw?.education || detail.educations || []) as any,
          certifications: raw?.certifications || anon?.anonymized_certifications || [],
          projects: (raw?.projects || anon?.anonymized_projects || []) as any,
          languages: raw?.languages || anon?.anonymized_languages || [],
          publications: (raw?.publications || anon?.anonymized_publications || []) as any,
          patents: (raw?.patents || anon?.anonymized_patents || []) as any,
          logistics: raw?.logistics || anon?.logistics || null,
          custom_sections: raw?.custom_sections || anon?.anonymized_custom_sections || [],
          miscellaneous: raw?.miscellaneous || anon?.anonymized_miscellaneous || [],
          unused_details: raw?.unused_details || [],
        },
        anonymized_candidate: {
          candidate_id: detail.id,
          anonymized_work_experiences: (anon?.anonymized_work_experiences || detail.experiences || []) as any,
          anonymized_education: (anon?.anonymized_education || detail.educations || []) as any,
          anonymized_skills: anon?.anonymized_skills || detail.skills || [],
          anonymized_certifications: anon?.anonymized_certifications || raw?.certifications || [],
          anonymized_projects: (anon?.anonymized_projects || raw?.projects || []) as any,
          anonymized_languages: anon?.anonymized_languages || raw?.languages || [],
          anonymized_publications: (anon?.anonymized_publications || raw?.publications || []) as any,
          anonymized_patents: (anon?.anonymized_patents || raw?.patents || []) as any,
          logistics: anon?.logistics || raw?.logistics || null,
          anonymized_custom_sections: anon?.anonymized_custom_sections || raw?.custom_sections || [],
          anonymized_miscellaneous: anon?.anonymized_miscellaneous || raw?.miscellaneous || [],
          sanitized_text: detail.sanitized_text || "",
          demographic_data: anon?.demographic_data || {},
        },
        chunks_indexed: detail.chunks_indexed || 0,
      };

      updateSingleExtraction(reconstructed);
      updateActiveSection("single");
    } catch (err) {
      console.error("Failed inspecting candidate:", err);
    } finally {
      setLoading(false);
    }
  };

  // Delete candidate CV and records from cohort directory
  const handleDeleteCandidate = async (candidateId: string, candidateName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Are you sure you want to permanently delete "${candidateName}" and all associated evaluations?`)) {
      return;
    }
    try {
      await api.deleteCandidate(candidateId);
      if (singleExtraction?.candidate_id === candidateId) {
        updateSingleExtraction(null);
      }
      setSelectedForComparison((prev) => prev.filter((id) => id !== candidateId));
      await fetchCandidates();
    } catch (err: any) {
      alert(`Failed to delete candidate: ${err?.message || err}`);
    }
  };

  // Batch upload handler
  const handleBatchFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const controller = batchTimer.startTimer();
    try {
      setIsUploadingBatch(true);
      const fileArray = Array.from(files);
      const res = await api.uploadBatchCVs(fileArray, selectedJobId || undefined, controller.signal);
      setActiveBatchId(res.batch_id);
      setBatchProgress({
        status: "PROCESSING",
        percentage: 0,
        processed: 0,
        total: fileArray.length,
        lastEvent: `Enqueued ${fileArray.length} resumes...`,
      });
    } catch (err: any) {
      if (err.name === "AbortError" || controller.signal.aborted) {
        batchTimer.stopTimer(false);
        return;
      }
      batchTimer.stopTimer(false);
      alert(`Batch upload failed: ${err.message}`);
    } finally {
      setIsUploadingBatch(false);
      if (batchFileInputRef.current) batchFileInputRef.current.value = "";
    }
  };

  const handleCancelBatch = () => {
    batchTimer.cancelTimer();
    setActiveBatchId(null);
    setBatchProgress(null);
    setIsUploadingBatch(false);
  };

  const candidateList = Array.isArray(candidates) ? candidates : [];
  const filteredCandidates = candidateList.filter((c) => {
    const name = (c.masked_name || "").toLowerCase();
    const filename = (c.original_filename || "").toLowerCase();
    const id = (c.id || "").toLowerCase();
    const skills = Array.isArray(c.skills) ? c.skills : [];
    const query = searchQuery.toLowerCase().trim();

    if (!query) {
      if (filterRecommendation === "ALL") return true;
      const rec = (c.latest_evaluation?.recommendation || "").toLowerCase();
      return rec === filterRecommendation.toLowerCase();
    }

    const matchesSearch =
      name.includes(query) ||
      filename.includes(query) ||
      id.includes(query) ||
      skills.some((s) => typeof s === "string" && s.toLowerCase().includes(query));

    if (!matchesSearch) return false;
    if (filterRecommendation === "ALL") return true;

    const rec = (c.latest_evaluation?.recommendation || "").toLowerCase();
    return rec === filterRecommendation.toLowerCase();
  });

  return (
    <div className="space-y-6">
      {/* Top Header & Section Switcher */}
      <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>Candidate Screening Pipeline</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-normal">
              {candidates.length} Registered
            </span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Asymmetric RAG candidate retrieval, automated PII redaction, and deterministic scoring.
          </p>
        </div>

        {/* Section Navigation Tabs (Single CV is Default) */}
        <div className="flex items-center rounded-xl bg-slate-900/90 p-1 border border-slate-800 text-xs shadow-inner">
          <button
            onClick={() => updateActiveSection("single")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
              activeSection === "single"
                ? "bg-blue-600 text-white font-semibold shadow-md shadow-blue-600/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Single CV Ingestion & Extraction</span>
          </button>
          <button
            onClick={() => updateActiveSection("batch")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
              activeSection === "batch"
                ? "bg-blue-600 text-white font-semibold shadow-md shadow-blue-600/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Users2 className="w-3.5 h-3.5" />
            <span>Cohort Directory ({candidates.length})</span>
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 1: SINGLE CANDIDATE INGESTION & EXTRACTION (DEFAULT SECTION)     */}
      {/* ========================================================================= */}
      {activeSection === "single" && (
        <div className="space-y-6">
          {/* Upload Dropzone Card */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Upload className="w-4 h-4 text-blue-400" />
                  <span>Upload Document</span>
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Select a resume or CV file to extract structured qualifications and isolate contact details.
                </p>
              </div>

              {singleExtraction && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => updateSingleExtraction(null)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Clear & Upload Another</span>
                  </button>
                </div>
              )}
            </div>



            {/* Error banner */}
            {singleUploadError && (
              <div className="p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
                <div className="space-y-1">
                  <div className="font-semibold">Document Ingestion Notice</div>
                  <div>{singleUploadError}</div>
                </div>
              </div>
            )}

            {/* Accessible Hidden File Input */}
            <input
              id="single-cv-upload-input"
              type="file"
              ref={singleFileInputRef}
              accept=".pdf,.docx,.txt,.md,.json"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleSingleFileUpload(file);
                e.target.value = "";
              }}
            />

            {/* Interactive Dropzone */}
            <label
              htmlFor={isUploadingSingle ? undefined : "single-cv-upload-input"}
              onDragOver={(e) => {
                e.preventDefault();
                if (!isUploadingSingle) setIsDragOver(true);
              }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragOver(false);
                if (!isUploadingSingle) {
                  const file = e.dataTransfer.files?.[0];
                  if (file) handleSingleFileUpload(file);
                }
              }}
              className={`transition-all select-none ${
                isUploadingSingle
                  ? "p-5 sm:p-6 rounded-xl border-2 border-dashed border-blue-500/40 bg-slate-950/80 flex flex-col items-stretch w-full cursor-default shadow-inner"
                  : isDragOver
                  ? "p-8 rounded-xl border-2 border-dashed border-blue-500 bg-blue-500/10 flex flex-col items-center justify-center gap-3 text-center cursor-pointer"
                  : "p-8 rounded-xl border-2 border-dashed border-slate-800 bg-slate-950/60 hover:border-slate-700 hover:bg-slate-900/50 flex flex-col items-center justify-center gap-3 text-center cursor-pointer"
              }`}
            >
              {isUploadingSingle ? (
                <div className="w-full py-1" onClick={(e) => e.stopPropagation()}>
                  <LiveProcessTimer
                    variant="expanded"
                    isRunning={singleTimer.isRunning}
                    elapsedSeconds={singleTimer.elapsedSeconds}
                    onCancel={handleCancelSingleUpload}
                    label={`Extracting CV with ${activeModelName} & Scrubbing PII...`}
                    estimateText="AI parsing active (typically 8-25s)"
                    cancelLabel="Cancel Extraction"
                    modelName={activeModelName}
                  />
                </div>
              ) : (
                <>
                  <div className="p-3 rounded-full bg-blue-600/10 border border-blue-500/20 text-blue-400 shadow-inner">
                    <FileUp className="w-6 h-6" />
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-slate-200">
                      Click anywhere or drag & drop candidate CV
                    </span>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Supported formats: PDF, DOCX, TXT, Markdown, JSON
                    </p>
                  </div>
                  <span className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition-all pointer-events-none mt-1">
                    <Upload className="w-3.5 h-3.5" />
                    <span>Browse & Upload CV</span>
                  </span>
                </>
              )}
            </label>

            {/* Quick Pick Previously Ingested Candidate */}
            {!singleExtraction && candidates.length > 0 && (
              <div className="pt-2 border-t border-slate-800/80">
                <span className="text-xs text-slate-400 font-medium">
                  Or inspect an indexed candidate profile:
                </span>
                <div className="flex flex-wrap gap-2 mt-2">
                  {candidates.slice(0, 5).map((cand) => (
                    <button
                      key={cand.id}
                      onClick={() => handleInspectCandidate(cand.id)}
                      className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 hover:border-blue-500/50 hover:bg-slate-900 text-slate-200 text-xs flex items-center gap-1.5 transition-all cursor-pointer"
                    >
                      <Eye className="w-3.5 h-3.5 text-slate-400" />
                      <span>{cand.masked_name || `Candidate-${cand.id.slice(0, 6)}`}</span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        ({cand.skills.length} skills)
                      </span>
                    </button>
                  ))}
                  {candidates.length > 5 && (
                    <button
                      onClick={() => updateActiveSection("batch")}
                      className="px-2.5 py-1.5 text-xs text-blue-400 hover:underline cursor-pointer font-medium"
                    >
                      View all {candidates.length} in cohort &rarr;
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ========================================================================= */}
          {/* EXTRACTED CANDIDATE DATA DISPLAY (LIKE ORIGINAL APP VERSION)              */}
          {/* ========================================================================= */}
          {singleExtraction && (
            <div id="candidate-extracted-profile" className="space-y-6 animate-in fade-in duration-300">
              {/* Unified Extraction Header Toolbar */}
              <div className="p-5 rounded-xl border border-emerald-500/30 bg-gradient-to-r from-emerald-950/30 via-slate-900/95 to-slate-900/95 backdrop-blur-md shadow-xl shadow-emerald-950/20 space-y-4">
                {/* Top Tier: Candidate Identity & Primary Actions */}
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  <div className="flex items-center gap-3.5 min-w-0">
                    <div className="p-2.5 rounded-xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 shrink-0 shadow-inner">
                      <CheckCircle2 className="w-6 h-6" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight whitespace-nowrap">
                          {singleExtraction.parsed_cv?.contact_info?.full_name ||
                            singleExtraction.anonymized_candidate?.candidate_id ||
                            singleExtraction.candidate_id}
                        </h2>
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shrink-0">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          <span>Extracted &amp; Indexed</span>
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 mt-1">
                        Candidate CV extracted, PII isolated, and semantic vectors ready for evaluation.
                      </p>
                    </div>
                  </div>

                  {/* Actions Toolbar */}
                  <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap shrink-0">
                    <button
                      onClick={() => {
                        const effectiveJobId = targetJobId || selectedJobId || (jobs[0]?.id ?? undefined);
                        onOpenEvaluation(singleExtraction.candidate_id, effectiveJobId, true);
                      }}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/30 transition-all cursor-pointer whitespace-nowrap active:scale-[0.98]"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                      <span>Run Match Evaluation</span>
                    </button>
                    <button
                      onClick={() => onOpenInterview(singleExtraction.candidate_id)}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700/60 transition-colors cursor-pointer whitespace-nowrap"
                    >
                      <FileText className="w-3.5 h-3.5 text-slate-400" />
                      <span>Interview Guide</span>
                    </button>
                    <button
                      onClick={() => updateActiveSection("batch")}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700/60 transition-colors cursor-pointer whitespace-nowrap"
                    >
                      <Users2 className="w-3.5 h-3.5 text-slate-400" />
                      <span>Cohort ({candidates.length}) &rarr;</span>
                    </button>
                    <button
                      onClick={() => updateSingleExtraction(null)}
                      className="flex items-center gap-1 px-2.5 py-2 rounded-lg bg-slate-800/80 hover:bg-rose-950/40 text-slate-400 hover:text-rose-300 border border-slate-700/60 hover:border-rose-900/50 text-xs transition-colors cursor-pointer whitespace-nowrap"
                      title="Close extracted candidate and reset workspace"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Close</span>
                    </button>
                  </div>
                </div>

                {/* Bottom Tier: Metrics & Candidate ID Strip */}
                <div className="pt-3 border-t border-emerald-500/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 font-mono text-[11px] font-medium">
                      <Layers className="w-3.5 h-3.5 text-emerald-400" />
                      <span>{singleExtraction.chunks_indexed || 0} chunks indexed</span>
                    </span>

                    {lastUploadDuration && (
                      <DurationBadge
                        duration={lastUploadDuration}
                        label="CV Extraction Time"
                        className="bg-slate-800/80 text-emerald-300 border-slate-700/60"
                      />
                    )}

                    {singleExtraction.token_usage && (
                      <TokenUsageBadge usage={singleExtraction.token_usage} />
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 text-slate-400 font-mono text-[11px]">
                    <span>Candidate ID:</span>
                    <code className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300 select-all font-mono">
                      {singleExtraction.candidate_id}
                    </code>
                  </div>
                </div>
              </div>

              {/* Dedicated Phase 2: Execute Semantic Evaluation on Specific Job Banner */}
              <div className="p-4 rounded-xl border border-blue-500/40 bg-gradient-to-r from-blue-950/50 via-slate-900/90 to-indigo-950/50 shadow-md flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 font-mono text-[10px] uppercase font-bold tracking-wider border border-blue-500/30">
                      Phase 2 Action
                    </span>
                    <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-amber-400" />
                      <span>Execute Semantic Evaluation</span>
                    </h3>
                  </div>
                  <p className="text-xs text-slate-300">
                    Evaluate this candidate against atomic requirements for a specific target job with verbatim citations.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto">
                  <div className="flex items-center gap-2 flex-1 lg:flex-none">
                    <span className="text-[11px] text-slate-400 font-medium whitespace-nowrap">Target Job:</span>
                    <select
                      value={targetJobId}
                      onChange={(e) => {
                        setTargetJobId(e.target.value);
                        onSelectJob?.(e.target.value);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-slate-100 focus:outline-none focus:border-blue-500 max-w-[260px] truncate"
                    >
                      {jobs.map((job) => (
                        <option key={job.id} value={job.id}>
                          {job.title} ({job.department || "General"})
                        </option>
                      ))}
                    </select>
                  </div>

                  <button
                    onClick={() => {
                      const effectiveJobId = targetJobId || selectedJobId || (jobs[0]?.id ?? undefined);
                      onOpenEvaluation(singleExtraction.candidate_id, effectiveJobId, true);
                    }}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all cursor-pointer whitespace-nowrap"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                    <span>Proceed to Phase 2: Semantic Evaluation &rarr;</span>
                  </button>
                </div>
              </div>

              {/* Two-Column Grid: Isolated PII vs Anonymized Profile */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* Column 1: Isolated Contact Information (PII) */}
                <div className="space-y-4">
                  <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm space-y-3.5">
                    <div className="flex items-center gap-2 text-xs font-semibold text-rose-400 uppercase tracking-wider">
                      <ShieldAlert className="w-4 h-4" />
                      <span>Isolated Contact Information (PII)</span>
                    </div>

                    <div className="text-sm text-slate-300 space-y-2.5 divide-y divide-slate-800/80">
                      <div className="pt-1 flex justify-between items-baseline gap-2">
                        <span className="text-slate-400 font-medium">Full Name:</span>
                        <span className="font-semibold text-white">
                          {singleExtraction.parsed_cv?.contact_info?.full_name || "N/A"}
                        </span>
                      </div>
                      <div className="pt-2.5 flex justify-between items-baseline gap-2">
                        <span className="text-slate-400 font-medium">Email Address:</span>
                        <span className="font-mono text-slate-200">
                          {singleExtraction.parsed_cv?.contact_info?.email || "N/A"}
                        </span>
                      </div>
                      <div className="pt-2.5 flex justify-between items-baseline gap-2">
                        <span className="text-slate-400 font-medium">Phone:</span>
                        <span className="font-mono text-slate-200">
                          {singleExtraction.parsed_cv?.contact_info?.phone_number ||
                            singleExtraction.parsed_cv?.contact_info?.phone ||
                            "Not provided"}
                        </span>
                      </div>
                      <div className="pt-2.5 flex justify-between items-baseline gap-2">
                        <span className="text-slate-400 font-medium">Location:</span>
                        <span className="text-slate-200">
                          {singleExtraction.parsed_cv?.contact_info?.location || "Not specified"}
                        </span>
                      </div>
                      <div className="pt-2.5 flex justify-between items-baseline gap-2">
                        <span className="text-slate-400 font-medium">LinkedIn:</span>
                        <span className="text-blue-400 truncate max-w-[260px]">
                          {singleExtraction.parsed_cv?.contact_info?.linkedin_url || "None"}
                        </span>
                      </div>
                      {singleExtraction.parsed_cv?.contact_info?.github_url && (
                        <div className="pt-2.5 flex justify-between items-baseline gap-2">
                          <span className="text-slate-400 font-medium">GitHub / Portfolio:</span>
                          <span className="text-blue-400 truncate max-w-[260px]">
                            {singleExtraction.parsed_cv?.contact_info?.github_url}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Demographic Audit Card (Redacted) */}
                  {singleExtraction.anonymized_candidate?.demographic_data &&
                    Object.keys(singleExtraction.anonymized_candidate.demographic_data).length > 0 && (
                      <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-950/20 shadow-sm space-y-2.5">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-amber-400 flex items-center gap-1.5 uppercase tracking-wider text-xs">
                            <ShieldAlert className="w-3.5 h-3.5" />
                            <span>Protected Demographic Audit (Redacted)</span>
                          </span>
                          <span className="text-xs text-amber-300/80 font-mono font-medium">
                            EU AI Act Art. 10
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed">
                          These demographic tokens are isolated from the semantic matching vector store to prevent algorithmic bias:
                        </p>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          {Object.entries(singleExtraction.anonymized_candidate.demographic_data).map(
                            ([k, v]) => (
                              <div
                                key={k}
                                className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 space-y-0.5"
                              >
                                <span className="text-slate-400 block uppercase text-[10px] font-mono">
                                   {k.replace(/_/g, " ")}
                                </span>
                                <span className="text-slate-100 font-medium text-sm">{String(v)}</span>
                              </div>
                            )
                          )}
                        </div>
                      </div>
                    )}
                </div>

                {/* Column 2: Anonymized Profile (Passed to Inference) */}
                <div className="space-y-4">
                  <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm space-y-4">
                    <div className="flex items-center gap-2 text-xs font-semibold text-blue-400 uppercase tracking-wider">
                      <UserCheck className="w-4 h-4" />
                      <span>Anonymized Profile (Passed to Inference)</span>
                    </div>

                    <div className="space-y-4">
                      <div>
                        <span className="text-sm font-medium text-slate-300 block mb-2">
                          Identified Core Skills ({(singleExtraction.anonymized_candidate?.anonymized_skills || singleExtraction.parsed_cv?.skills || []).length}):
                        </span>
                        <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto pr-1">
                          {(singleExtraction.anonymized_candidate?.anonymized_skills || singleExtraction.parsed_cv?.skills || []).map((skill, idx) => (
                            <span
                              key={idx}
                              className="px-2.5 py-1 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-300 text-xs font-mono"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                      </div>

                      {(singleExtraction.anonymized_candidate?.anonymized_languages || singleExtraction.parsed_cv?.languages || []).length > 0 && (
                          <div className="pt-3 border-t border-slate-800">
                            <span className="text-sm font-medium text-slate-300 block mb-2">
                              Language Proficiencies:
                            </span>
                            <div className="flex flex-wrap gap-2">
                              {(singleExtraction.anonymized_candidate?.anonymized_languages || singleExtraction.parsed_cv?.languages || []).map(
                                (lang, idx) => (
                                  <span
                                    key={idx}
                                    className="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 text-xs"
                                  >
                                    <strong className="text-white">{lang.language}</strong>
                                    {lang.proficiency ? ` (${lang.proficiency})` : ""}
                                  </span>
                                )
                              )}
                            </div>
                          </div>
                        )}

                      {(singleExtraction.anonymized_candidate?.anonymized_certifications || singleExtraction.parsed_cv?.certifications || []).length > 0 && (
                          <div className="pt-3 border-t border-slate-800">
                            <span className="text-sm font-medium text-slate-300 block mb-2">
                              Certifications & Licences ({(singleExtraction.anonymized_candidate?.anonymized_certifications || singleExtraction.parsed_cv?.certifications || []).length}):
                            </span>
                            <ul className="list-disc list-inside text-slate-200 space-y-1.5 text-sm leading-relaxed pl-1">
                              {(singleExtraction.anonymized_candidate?.anonymized_certifications || singleExtraction.parsed_cv?.certifications || []).map(
                                (cert, idx) => (
                                  <li key={idx} className="truncate">
                                    {cert}
                                  </li>
                                )
                              )}
                            </ul>
                          </div>
                        )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Expandable Section 1: Work Experience */}
              {(singleExtraction.anonymized_candidate?.anonymized_work_experiences || singleExtraction.parsed_cv?.experiences || []).length > 0 && (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("experience")}
                      className="w-full p-4 flex items-center justify-between text-left text-xs font-semibold text-slate-200 hover:bg-slate-800/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Briefcase className="w-4 h-4 text-blue-400" />
                        <span>
                          Work Experience ({(singleExtraction.anonymized_candidate?.anonymized_work_experiences || singleExtraction.parsed_cv?.experiences || []).length} roles)
                        </span>
                      </div>
                      <ChevronDown
                        className={`w-4 h-4 text-slate-500 transition-transform ${
                          expandedSections.experience ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {expandedSections.experience && (
                      <div className="p-4 pt-0 space-y-4 divide-y divide-slate-800/80">
                        {(singleExtraction.anonymized_candidate?.anonymized_work_experiences || singleExtraction.parsed_cv?.experiences || []).map(
                          (exp, idx) => (
                            <div key={idx} className="pt-3 space-y-2 text-sm">
                              <div className="flex flex-wrap items-baseline justify-between gap-2">
                                <div className="font-semibold text-base text-white">
                                  <span>{exp.job_title}</span>
                                  <span className="text-slate-300 font-normal">
                                    {" "}
                                    at {exp.company_name}
                                  </span>
                                </div>
                                <span className="text-xs text-slate-400 font-mono">
                                  {exp.start_date || ""} &ndash; {exp.end_date || "Present"}
                                </span>
                              </div>

                              <div className="flex flex-wrap gap-2 text-xs text-slate-400">
                                {exp.employment_type && (
                                  <span className="px-2 py-0.5 rounded bg-slate-800 font-mono">
                                    {exp.employment_type}
                                  </span>
                                )}
                                {exp.work_model && (
                                  <span className="px-2 py-0.5 rounded bg-slate-800 font-mono">
                                    {exp.work_model}
                                  </span>
                                )}
                                {exp.location && <span>{exp.location}</span>}
                              </div>

                              <ul className="list-disc list-inside space-y-1.5 text-slate-200 text-sm leading-relaxed pl-1">
                                {(Array.isArray(exp.work_description) ? exp.work_description : exp.work_description ? [String(exp.work_description)] : []).map((b, bIdx) => (
                                  <li key={bIdx} className="leading-relaxed">
                                    {b}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </div>
                )}

              {/* Expandable Section 2: Education & Academic Credentials */}
              {(singleExtraction.anonymized_candidate?.anonymized_education || singleExtraction.parsed_cv?.education || []).length > 0 && (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("education")}
                      className="w-full p-4 flex items-center justify-between text-left text-xs font-semibold text-slate-200 hover:bg-slate-800/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <GraduationCap className="w-4 h-4 text-emerald-400" />
                        <span>
                          Education & Academic Credentials ({(singleExtraction.anonymized_candidate?.anonymized_education || singleExtraction.parsed_cv?.education || []).length} degrees)
                        </span>
                      </div>
                      <ChevronDown
                        className={`w-4 h-4 text-slate-500 transition-transform ${
                          expandedSections.education ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {expandedSections.education && (
                      <div className="p-4 pt-0 space-y-3 divide-y divide-slate-800/80">
                        {(singleExtraction.anonymized_candidate?.anonymized_education || singleExtraction.parsed_cv?.education || []).map(
                          (edu, idx) => (
                            <div key={idx} className="pt-3 text-sm space-y-1.5">
                              <div className="flex justify-between items-baseline">
                                <span className="font-semibold text-base text-white">
                                  {edu.degree_title}
                                </span>
                                {edu.graduation_year && (
                                  <span className="text-xs font-mono text-slate-400">
                                    {edu.graduation_year}
                                  </span>
                                )}
                              </div>
                              <div className="text-slate-300 text-xs">
                                {edu.institution_name}
                                {edu.field_of_study ? ` • Major: ${edu.field_of_study}` : ""}
                                {edu.location ? ` • ${edu.location}` : ""}
                              </div>
                              {edu.gpa_or_grade && (
                                <div className="text-slate-300 text-xs">
                                  Final Grade / GPA: <span className="font-mono text-white font-semibold">{edu.gpa_or_grade}</span>
                                </div>
                              )}
                              {edu.thesis_title && (
                                <div className="text-slate-400 text-xs italic">
                                  Thesis: {edu.thesis_title}
                                </div>
                              )}
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </div>
                )}

              {/* Expandable Section 3: Projects & Portfolios */}
              {(singleExtraction.anonymized_candidate?.anonymized_projects || singleExtraction.parsed_cv?.projects || []).length > 0 && (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("projects")}
                      className="w-full p-4 flex items-center justify-between text-left text-xs font-semibold text-slate-200 hover:bg-slate-800/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <FolderGit2 className="w-4 h-4 text-purple-400" />
                        <span>
                          Technical Projects & Portfolios ({(singleExtraction.anonymized_candidate?.anonymized_projects || singleExtraction.parsed_cv?.projects || []).length})
                        </span>
                      </div>
                      <ChevronDown
                        className={`w-4 h-4 text-slate-500 transition-transform ${
                          expandedSections.projects ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {expandedSections.projects && (
                      <div className="p-4 pt-0 space-y-4 divide-y divide-slate-800/80">
                        {(singleExtraction.anonymized_candidate?.anonymized_projects || singleExtraction.parsed_cv?.projects || []).map(
                          (proj, idx) => (
                            <div key={idx} className="pt-3.5 space-y-3">
                              <div className="flex flex-wrap items-baseline justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold text-base text-white">
                                    {proj.project_name}
                                  </span>
                                  {(proj.start_date || proj.end_date) && (
                                    <span className="text-xs text-slate-400 font-mono bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/50">
                                      {proj.start_date || ""} {proj.start_date && proj.end_date ? "–" : ""} {proj.end_date || ""}
                                    </span>
                                  )}
                                </div>
                                {proj.project_url && (
                                  <a
                                    href={proj.project_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-blue-400 hover:text-blue-300 hover:underline flex items-center gap-1.5 text-xs font-medium"
                                  >
                                    <span>Repository / Live URL</span>
                                    <ExternalLink className="w-3.5 h-3.5" />
                                  </a>
                                )}
                              </div>

                              {Array.isArray(proj.technologies) && proj.technologies.length > 0 && (
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <span className="text-[11px] font-medium text-slate-400 mr-1">Stack:</span>
                                  {proj.technologies.map((t, tIdx) => (
                                    <span
                                      key={tIdx}
                                      className="px-2 py-0.5 rounded bg-purple-950/40 text-xs font-mono text-purple-300 border border-purple-800/40"
                                    >
                                      {t}
                                    </span>
                                  ))}
                                </div>
                              )}

                              {/* Project Description & Technical Scope */}
                              <div className="rounded-lg bg-slate-950/60 border border-slate-800/70 p-3 space-y-2">
                                <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                                  <FileText className="w-3 h-3 text-purple-400" />
                                  <span>Project Description & Scope</span>
                                </div>
                                {(() => {
                                  const descItems = Array.isArray(proj.description)
                                    ? proj.description
                                    : proj.description
                                    ? [String(proj.description)]
                                    : [];
                                  if (descItems.length === 0) {
                                    return (
                                      <p className="text-xs text-slate-500 italic">
                                        No explicit scope or architecture notes listed for this project.
                                      </p>
                                    );
                                  }
                                  return (
                                    <ul className="list-disc list-inside text-slate-200 text-xs sm:text-sm leading-relaxed space-y-1.5 pl-1">
                                      {descItems.map((d, dIdx) => (
                                        <li key={dIdx} className="leading-relaxed">
                                          {d}
                                        </li>
                                      ))}
                                    </ul>
                                  );
                                })()}
                              </div>
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </div>
                )}

              {/* Expandable Section 4: Specialized & Community Sections */}
              {(() => {
                const specializedSections = (
                  singleExtraction.anonymized_candidate?.anonymized_custom_sections || []
                ).filter(
                  (s) =>
                    s.items &&
                    s.items.length > 0 &&
                    !s.section_title.toLowerCase().includes("miscellaneous") &&
                    !s.section_title.toLowerCase().includes("other information")
                );

                if (specializedSections.length === 0) return null;

                return (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("custom")}
                      className="w-full p-4 flex items-center justify-between text-left text-xs font-semibold text-slate-200 hover:bg-slate-800/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Award className="w-4 h-4 text-amber-400" />
                        <span>
                          Specialized & Community Sections ({specializedSections.length})
                        </span>
                      </div>
                      <ChevronDown
                        className={`w-4 h-4 text-slate-500 transition-transform ${
                          expandedSections.custom ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {expandedSections.custom && (
                      <div className="p-4 pt-0 space-y-4 divide-y divide-slate-800/80">
                        {specializedSections.map((sec, idx) => (
                          <div key={idx} className="pt-3 text-sm space-y-2">
                            <div className="font-semibold text-base text-amber-300 flex items-center gap-1.5">
                              <span>{sec.section_title}</span>
                            </div>
                            <ul className="list-disc list-inside text-slate-200 text-sm space-y-1.5 leading-relaxed pl-1">
                              {(Array.isArray(sec.items) ? sec.items : sec.items ? [String(sec.items)] : []).map((item, iIdx) => (
                                <li key={iIdx} className="leading-relaxed">
                                  {item}
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Expandable Section 5: Miscellaneous & Other Information (No Detail Overlooked) */}
              {(() => {
                const directMisc = singleExtraction.anonymized_candidate?.anonymized_miscellaneous || singleExtraction.parsed_cv?.miscellaneous || [];
                const miscCustomSections = (singleExtraction.anonymized_candidate?.anonymized_custom_sections || []).filter(
                  (s) =>
                    s.section_title.toLowerCase().includes("miscellaneous") ||
                    s.section_title.toLowerCase().includes("other") ||
                    s.section_title.toLowerCase().includes("additional")
                );
                const customItems = miscCustomSections.flatMap((s) => s.items || []);
                const combinedMisc = Array.from(new Set([...directMisc, ...customItems])).filter(Boolean);

                return (
                  <div className="rounded-xl border border-indigo-900/40 bg-indigo-950/20 overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("miscellaneous")}
                      className="w-full p-4 flex items-center justify-between text-left text-xs font-semibold text-slate-200 hover:bg-indigo-950/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Layers className="w-4 h-4 text-indigo-400" />
                        <span className="text-indigo-200 font-semibold text-sm">
                          Miscellaneous / Other Information ({combinedMisc.length})
                        </span>
                        <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-mono font-medium">
                          Indexed for Semantic Search
                        </span>
                      </div>
                      <ChevronDown
                        className={`w-4 h-4 text-indigo-400 transition-transform ${
                          expandedSections.miscellaneous ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {expandedSections.miscellaneous && (
                      <div className="p-4 pt-0 space-y-3">
                        <p className="text-xs text-slate-300 leading-relaxed">
                          All peripheral details, hobbies, extracurriculars, unusual achievements, or unmapped notes extracted from the candidate document. Preserved and fully indexed in ChromaDB so no detail is ignored or overlooked during candidate matching.
                        </p>

                        {combinedMisc.length > 0 ? (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
                            {combinedMisc.map((item, idx) => (
                              <div
                                key={idx}
                                className="p-3 rounded-lg bg-slate-900/90 border border-indigo-900/50 text-sm text-slate-200 flex items-start gap-2.5 shadow-sm"
                              >
                                <span className="text-indigo-400 mt-0.5 font-bold">•</span>
                                <span className="leading-relaxed text-sm">{item}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-400 italic">
                            All extracted candidate details were mapped into primary qualification sections. Zero details omitted.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Expandable Section 6: Publications & Patents */}
              {(() => {
                const pubs = singleExtraction.anonymized_candidate?.anonymized_publications || singleExtraction.parsed_cv?.publications || [];
                const pats = singleExtraction.anonymized_candidate?.anonymized_patents || singleExtraction.parsed_cv?.patents || [];
                if (pubs.length === 0 && pats.length === 0) return null;

                return (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("publications")}
                      className="w-full p-4 flex items-center justify-between text-left text-xs font-semibold text-slate-200 hover:bg-slate-800/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Bookmark className="w-4 h-4 text-cyan-400" />
                        <span className="text-sm font-semibold">
                          Publications & Intellectual Property ({pubs.length + pats.length})
                        </span>
                      </div>
                      <ChevronDown
                        className={`w-4 h-4 text-slate-500 transition-transform ${
                          expandedSections.publications ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {expandedSections.publications && (
                      <div className="p-4 pt-0 space-y-3 divide-y divide-slate-800/80">
                        {pubs.map((pub, idx) => (
                          <div key={idx} className="pt-2 text-sm space-y-1">
                            <div className="font-semibold text-white flex items-center justify-between">
                              <span className="text-base">{pub.title}</span>
                              {pub.year && <span className="text-slate-400 font-mono text-xs">{pub.year}</span>}
                            </div>
                            {pub.journal_or_conference && (
                              <div className="text-xs text-slate-300">
                                {pub.journal_or_conference}
                              </div>
                            )}
                            {pub.doi_or_url && (
                              <a
                                href={pub.doi_or_url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-blue-400 hover:underline flex items-center gap-1 text-xs"
                              >
                                <span>{pub.doi_or_url}</span>
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            )}
                          </div>
                        ))}
                        {pats.map((pat, idx) => (
                          <div key={`pat-${idx}`} className="pt-2 text-sm space-y-1">
                            <div className="font-semibold text-white flex items-center justify-between">
                              <span className="text-base">Patent: {pat.title}</span>
                              {pat.status && (
                                <span className="text-emerald-400 font-mono text-xs uppercase font-medium">
                                  {pat.status}
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-slate-300">
                              {pat.patent_office} {pat.patent_number ? `• ${pat.patent_number}` : ""}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Expandable Section 7: Logistics & Candidate Availability */}
              {(() => {
                const log = (singleExtraction.anonymized_candidate?.logistics || singleExtraction.parsed_cv?.logistics) as any;
                if (!log || Object.keys(log).length === 0 || !Object.values(log).some(Boolean)) return null;

                return (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("logistics")}
                      className="w-full p-4 flex items-center justify-between text-left text-xs font-semibold text-slate-200 hover:bg-slate-800/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4 text-orange-400" />
                        <span className="text-sm font-semibold">Logistics & Candidate Availability</span>
                      </div>
                      <ChevronDown
                        className={`w-4 h-4 text-slate-500 transition-transform ${
                          expandedSections.logistics ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {expandedSections.logistics && (
                      <div className="p-4 pt-0 grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                        {log.notice_period && (
                          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
                            <span className="text-slate-400 text-xs block uppercase font-mono font-medium">Notice Period</span>
                            <span className="text-slate-100 font-medium text-sm">{log.notice_period}</span>
                          </div>
                        )}
                        {log.earliest_start_date && (
                          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
                            <span className="text-slate-400 text-xs block uppercase font-mono font-medium">Earliest Start</span>
                            <span className="text-slate-100 font-medium text-sm">{log.earliest_start_date}</span>
                          </div>
                        )}
                        {log.work_authorization && (
                          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
                            <span className="text-slate-400 text-xs block uppercase font-mono font-medium">Work Authorization</span>
                            <span className="text-slate-100 font-medium text-sm">{log.work_authorization}</span>
                          </div>
                        )}
                        {log.relocation_preference && (
                          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
                            <span className="text-slate-400 text-xs block uppercase font-mono font-medium">Relocation</span>
                            <span className="text-slate-100 font-medium text-sm">{log.relocation_preference}</span>
                          </div>
                        )}
                        {log.travel_willingness && (
                          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
                            <span className="text-slate-400 text-xs block uppercase font-mono font-medium">Travel Willingness</span>
                            <span className="text-slate-100 font-medium text-sm">{log.travel_willingness}</span>
                          </div>
                        )}
                        {log.salary_expectation && (
                          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
                            <span className="text-slate-400 text-xs block uppercase font-mono font-medium">Target Salary / Rate</span>
                            <span className="text-emerald-300 font-semibold text-sm">{log.salary_expectation}</span>
                          </div>
                        )}
                        {log.security_clearance && (
                          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
                            <span className="text-slate-400 text-xs block uppercase font-mono font-medium">Security Clearance</span>
                            <span className="text-purple-300 font-medium text-sm">{log.security_clearance}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION 2: COHORT DIRECTORY & BATCH SCREENING                             */}
      {/* ========================================================================= */}
      {activeSection === "batch" && (
        <div className="space-y-6">
          {/* Top Cohort Action Bar */}
          <div className="flex flex-col sm:flex-row gap-3 items-stretch justify-between">
            <div className="flex items-center gap-2">
              <input
                id="batch-cv-upload-input"
                type="file"
                ref={batchFileInputRef}
                onChange={(e) => {
                  handleBatchFileUpload(e);
                  e.target.value = "";
                }}
                multiple
                accept=".pdf,.docx,.txt,.md,.json"
                className="sr-only"
              />
              <label
                htmlFor="batch-cv-upload-input"
                className={`flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-all cursor-pointer ${
                  isUploadingBatch ? "opacity-50 pointer-events-none" : ""
                }`}
              >
                {isUploadingBatch ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <FileUp className="w-3.5 h-3.5" />
                )}
                <span>Batch Upload Resumes</span>
              </label>

              <button
                onClick={fetchCandidates}
                className="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-400 hover:text-white transition-colors cursor-pointer"
                title="Refresh candidate records"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Filter Pills */}
            <div className="flex items-center gap-2">
              <Filter className="w-3.5 h-3.5 text-slate-500" />
              <div className="flex rounded-lg bg-slate-950 p-0.5 border border-slate-800 text-[11px]">
                {["ALL", "STRONG_MATCH", "BORDERLINE", "REJECT"].map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setFilterRecommendation(filter)}
                    className={`px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                      filterRecommendation === filter
                        ? "bg-slate-800 text-white font-medium"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {filter === "ALL"
                      ? "All"
                      : filter === "STRONG_MATCH"
                      ? "Strong"
                      : filter === "BORDERLINE"
                      ? "Borderline"
                      : "Reject"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Live SSE Progress Ticker */}
          {batchProgress && (
            <div className="p-4 rounded-xl bg-blue-950/40 border border-blue-500/30 backdrop-blur-md space-y-3 animate-in fade-in duration-200">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 text-blue-300 font-medium">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
                  <span>Real-Time Batch Evaluation</span>
                  <span className="text-[10px] text-blue-400/80 font-mono">
                    ({batchProgress.processed}/{batchProgress.total})
                  </span>
                  {batchTimer.isRunning && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                      ⏱ {batchTimer.formattedElapsed}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <div className="font-mono text-xs text-blue-300 font-bold">
                    {formatPercent(batchProgress.percentage)}
                  </div>
                  {batchProgress.status !== "COMPLETED" && (
                    <button
                      type="button"
                      onClick={handleCancelBatch}
                      className="px-2.5 py-1 rounded-md bg-rose-950/80 hover:bg-rose-900 border border-rose-500/40 text-rose-200 text-[11px] font-medium transition-colors cursor-pointer"
                    >
                      Cancel Batch
                    </button>
                  )}
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
                <div className="flex items-center gap-2">
                  {lastBatchDuration && (
                    <DurationBadge duration={lastBatchDuration} label="Total batch time" />
                  )}
                  <span className="uppercase text-[9px] font-semibold tracking-wider text-blue-400">
                    SSE Stream Active
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Search Bar */}
          <div className="relative w-full">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search cohort by alias, skills (e.g. Python, Docker, PyTorch)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          {/* Candidates Table */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/30 overflow-hidden shadow-sm">
            {loading ? (
              <div className="p-12 flex flex-col items-center justify-center gap-3 text-slate-400 text-sm">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                <span>Retrieving indexed talent records...</span>
              </div>
            ) : filteredCandidates.length === 0 ? (
              <div className="p-12 flex flex-col items-center justify-center gap-3 text-center text-slate-400 text-sm">
                <FileText className="w-8 h-8 text-slate-500 stroke-1" />
                <span className="font-semibold text-slate-200">No candidates match your criteria</span>
                <span className="text-xs text-slate-400">Upload new resumes or switch back to Single Ingestion tab.</span>
                <div className="flex items-center gap-2 mt-2">
                  <label
                    htmlFor="batch-cv-upload-input"
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/25 transition-all cursor-pointer"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    <span>Upload Resumes</span>
                  </label>
                  <button
                    onClick={() => updateActiveSection("single")}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors cursor-pointer"
                  >
                    <span>Single Ingestion Tab</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-900/90 border-b border-slate-800 text-slate-300 font-semibold text-xs uppercase tracking-wider">
                    <tr>
                      <th className="py-3.5 px-3 w-8 text-center">
                        <span className="sr-only">Compare Select</span>
                      </th>
                      <th className="py-3.5 px-4">Candidate Profile</th>
                      <th className="py-3.5 px-4">Experience</th>
                      <th className="py-3.5 px-4">Core Skills</th>
                      <th className="py-3.5 px-4 text-center">Score Breakdown</th>
                      <th className="py-3.5 px-4 text-center">Decision Tier</th>
                      <th className="py-3.5 px-4 text-right">Actions</th>
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

                      const isChecked = selectedForComparison.includes(candidate.id);

                      return (
                        <tr
                          key={candidate.id}
                          className={`hover:bg-slate-800/30 transition-colors group cursor-pointer ${
                            isChecked ? "bg-blue-600/10" : ""
                          }`}
                          onClick={() => handleInspectCandidate(candidate.id)}
                        >
                          {/* Comparison Checkbox */}
                          <td
                            className="py-3.5 px-3 text-center"
                            onClick={(e) => toggleCandidateSelect(candidate.id, e)}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {}}
                              className="rounded border-slate-700 bg-slate-900 text-blue-600 cursor-pointer"
                            />
                          </td>

                          {/* Masked Profile */}
                          <td className="py-3.5 px-4">
                            <div className="font-semibold text-base text-slate-100 group-hover:text-blue-400 transition-colors flex items-center gap-1.5">
                              <span>{displayName}</span>
                            </div>
                            <div className="text-xs text-slate-400 font-mono mt-0.5">
                              ID: {candidate.id.slice(0, 8)}... &bull; {candidate.chunks_indexed} vectors
                            </div>
                          </td>

                          {/* Experience */}
                          <td className="py-3.5 px-4 text-slate-200 font-medium">
                            {candidate.total_years_experience !== null &&
                            candidate.total_years_experience !== undefined ? (
                              <div className="flex items-center gap-1.5">
                                <Clock className="w-3.5 h-3.5 text-slate-400" />
                                <span>{candidate.total_years_experience} yrs</span>
                              </div>
                            ) : (
                              <span className="text-slate-500">&mdash;</span>
                            )}
                          </td>

                          {/* Core Skills */}
                          <td className="py-3.5 px-4 max-w-[260px]">
                            <div className="flex flex-wrap gap-1">
                              {candidate.skills.slice(0, 3).map((skill, idx) => (
                                <span
                                  key={idx}
                                  className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-200 text-xs font-mono border border-slate-700/60"
                                >
                                  {skill}
                                </span>
                              ))}
                              {candidate.skills.length > 3 && (
                                <span className="px-1.5 py-0.5 rounded-md bg-slate-800/50 text-slate-400 text-xs font-mono">
                                  +{candidate.skills.length - 3}
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Score Breakdown */}
                          <td className="py-3.5 px-4 text-center">
                            {evalData ? (
                              <div className="inline-flex flex-col items-center">
                                <div className="text-base font-bold text-white tabular-nums">
                                  {evalData.overall_score.toFixed(0)}%
                                </div>
                                <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
                                  <span title="Must Have Score">
                                    MH: {evalData.must_have_score.toFixed(0)}%
                                  </span>
                                  {evalData.must_have_gaps_count > 0 && (
                                    <span
                                      className="text-rose-400 font-bold"
                                      title="Must-Have Gaps"
                                    >
                                      ({evalData.must_have_gaps_count} gap)
                                    </span>
                                  )}
                                </div>
                              </div>
                            ) : (
                              <span className="text-slate-500 font-mono text-xs">&mdash;</span>
                            )}
                          </td>

                          {/* Decision Tier */}
                          <td className="py-3.5 px-4 text-center">
                            <span
                              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${badge.className}`}
                            >
                              {badge.label}
                            </span>
                            {evalData?.hitl_validated && (
                              <div className="text-[10px] text-emerald-400 flex items-center justify-center gap-0.5 mt-1 font-medium">
                                <UserCheck className="w-3 h-3" />
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
                                onClick={() => handleInspectCandidate(candidate.id)}
                                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors cursor-pointer"
                                title="Inspect extracted structured credentials"
                              >
                                Inspect
                              </button>
                              <button
                                onClick={() => onOpenEvaluation(candidate.id, targetJobId || selectedJobId || (jobs[0]?.id ?? undefined))}
                                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors cursor-pointer"
                                title="Audit verbatim citations and submit HITL decision"
                              >
                                Citations
                              </button>
                              <button
                                onClick={() => onOpenInterview(candidate.id)}
                                className="px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 text-xs font-medium border border-blue-500/20 transition-colors cursor-pointer"
                                title="Generate role-tailored STAR interview guide"
                              >
                                Interview
                              </button>
                              <button
                                onClick={(e) => handleDeleteCandidate(candidate.id, displayName, e)}
                                className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/25 text-rose-400 hover:text-rose-300 border border-rose-500/20 transition-colors cursor-pointer"
                                title="Delete candidate CV and all associated evaluations"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
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
      )}

      {/* Floating Comparison Action Bar */}
      {selectedForComparison.length >= 2 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-5 py-3 rounded-2xl bg-slate-900/95 border border-blue-500/40 shadow-2xl backdrop-blur-md animate-in slide-in-from-bottom duration-200">
          <div className="flex items-center gap-2 text-xs font-semibold text-white">
            <Users2 className="w-4 h-4 text-blue-400" />
            <span>{selectedForComparison.length} Candidates Selected</span>
          </div>
          <div className="h-4 w-px bg-slate-800" />
          <button
            onClick={() => onOpenComparison && onOpenComparison(selectedForComparison)}
            className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all cursor-pointer"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span>Compare Head-to-Head</span>
          </button>
          <button
            onClick={() => setSelectedForComparison([])}
            className="text-xs text-slate-400 hover:text-white transition-colors cursor-pointer"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
