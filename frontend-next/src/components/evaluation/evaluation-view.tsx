"use client";

import { useState, useEffect, useMemo } from "react";
import {
  CandidateDetail,
  CandidateSummary,
  JobDescription,
  MatchEvaluationResult,
  RequirementMatch,
} from "@/types";
import { api } from "@/lib/api";
import { getRecommendationBadge } from "@/lib/utils";
import { TokenUsageBadge, LiveTokenCounter } from "@/components/ui/token-counter";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRightLeft,
  BookOpen,
  Briefcase,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Copy,
  ExternalLink,
  FileCheck2,
  FileText,
  Filter,
  HelpCircle,
  Highlighter,
  Info,
  Loader2,
  MessageSquare,
  PhoneCall,
  Quote,
  RotateCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  Users2,
  X,
  XCircle,
} from "lucide-react";
import { LiveProcessTimer, DurationBadge, useProcessTimer } from "@/components/ui/live-process-timer";
import { ComplianceDossierModal } from "@/components/compliance/compliance-dossier-modal";
import { DocumentViewer } from "@/components/evaluation/document-viewer";

export interface RequirementMeta {
  title: string;
  slug: string;
  category: "must_have" | "nice_to_have";
  weight: number;
  minYears: number | null;
  summary: string;
  citation: string;
  isCustomSlug: boolean;
}

export function getRequirementMeta(
  rm: {
    requirement_id: string;
    title?: string | null;
    jd_summary?: string | null;
    jd_citation?: string | null;
  },
  job?: JobDescription | null
): RequirementMeta {
  const matchedReq = (job?.requirements || []).find((r) => r.id === rm.requirement_id);

  // 1. Resolve human-readable title
  let title = rm.title || matchedReq?.title;
  let isCustomSlug = false;

  if (!title || title.trim() === rm.requirement_id || title.startsWith("req_")) {
    isCustomSlug = true;
    const clean = rm.requirement_id.replace(/^req_/, "").trim();
    const slugMap: Record<string, string> = {
      degree: "Academic Degree Qualification",
      education: "Educational Background & Qualifications",
      bachelor: "Bachelor's Degree in Technical Field",
      master: "Master's Degree in Engineering/CS",
      python: "Python Software Engineering",
      python_fastapi: "Python & FastAPI Microservices",
      fastapi: "FastAPI REST Microservices",
      k8s: "Kubernetes Cluster Architecture & Orchestration",
      kubernetes: "Kubernetes Container Orchestration",
      go: "Go (Golang) Systems & Concurrency",
      golang: "Go (Golang) Backend Development",
      incident_resp: "Security Incident Response & SecOps",
      rag: "Retrieval-Augmented Generation (RAG) Systems",
      location_onsite: "On-Site Physical Location Requirement",
      relocation: "Relocation Willingness",
      travel: "Business Travel Availability",
      work_auth: "Legal Work Authorization",
      clearance: "Security Clearance Requirement",
      embedded_c: "Embedded C/C++ Firmware Development",
      can_bus: "CAN Bus / CAN FD Automotive Networks",
      freertos: "FreeRTOS & Embedded RTOS Architecture",
      ble: "Bluetooth Low Energy (BLE) / RF Networking",
      mems: "MEMS Sensor Integration & Device Drivers",
      aspice: "ASPICE & ISO 26262 Functional Safety Standards",
      tensorflow: "TensorFlow & Edge Machine Learning",
      ci_cd: "Automated CI/CD & Hardware-in-the-Loop Testing",
      french: "Professional Working French Proficiency",
      bid_management: "Enterprise Bid & Tender Management",
      material_handling: "Material Handling & Logistics Operations",
      forklift: "Forklift Operation & Certification",
    };

    if (slugMap[clean]) {
      title = slugMap[clean];
    } else {
      title = clean
        .split(/[-_]+/)
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(" ");
    }
  }

  // 2. Resolve summary of the request
  let summary = matchedReq?.description || rm.jd_summary || "";
  if (!summary || summary.trim().length === 0) {
    summary = `Candidate must demonstrate documented hands-on capability, practical experience, and alignment with the requisition expectations for "${title}".`;
  }

  // 3. Resolve verbatim citation from the JD
  let citation = rm.jd_citation || matchedReq?.description || "";
  if (!citation || citation.trim().length === 0) {
    if (job?.raw_text && job.raw_text.trim()) {
      const keywords = title.toLowerCase().split(/\s+/).filter((w) => w.length > 3);
      const paragraphs = job.raw_text.split(/\n+/).map((p) => p.trim()).filter((p) => p.length > 25);
      for (const p of paragraphs) {
        const pLower = p.toLowerCase();
        if (keywords.some((kw) => pLower.includes(kw))) {
          citation = p;
          break;
        }
      }
    }
  }

  if (!citation) {
    citation = summary;
  }

  return {
    title,
    slug: rm.requirement_id,
    category: (matchedReq?.category as "must_have" | "nice_to_have") || "must_have",
    weight: matchedReq?.weight ?? 1.0,
    minYears: matchedReq?.minimum_years_experience ?? null,
    summary,
    citation,
    isCustomSlug,
  };
}

interface EvaluationViewProps {
  candidateId: string | null;
  selectedJobId: string | null;
  jobs: JobDescription[];
  autoRun?: boolean;
  onResetAutoRun?: () => void;
  onBackToPipeline: () => void;
  onSelectCandidate?: (candidateId: string) => void;
  onSelectJob?: (jobId: string) => void;
}

export function EvaluationView({
  candidateId,
  selectedJobId,
  jobs,
  autoRun,
  onResetAutoRun,
  onBackToPipeline,
  onSelectCandidate,
  onSelectJob,
}: EvaluationViewProps) {
  // Candidate & Requisition Scope State
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(selectedJobId || (jobs[0]?.id ?? null));
  const [activeCandidateId, setActiveCandidateId] = useState<string | null>(candidateId || null);

  // Evaluation & Data State
  const [evaluation, setEvaluation] = useState<MatchEvaluationResult | null>(null);
  const [candidateDetail, setCandidateDetail] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const evalTimer = useProcessTimer();
  const [evalDuration, setEvalDuration] = useState<number | null>(null);

  // HITL Decision & Notes State
  const [decision, setDecision] = useState<"strong_match" | "borderline" | "reject">("strong_match");
  const [notes, setNotes] = useState("");
  const [submittingHitl, setSubmittingHitl] = useState(false);
  const [hitlSuccess, setHitlSuccess] = useState(false);

  // UI Interactive States
  const [showComplianceModal, setShowComplianceModal] = useState(false);
  const [showDocViewer, setShowDocViewer] = useState(true);
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [rightPanelTab, setRightPanelTab] = useState<"document" | "signoff">("document");
  const [requirementFilter, setRequirementFilter] = useState<"all" | "met" | "partial" | "clarification_needed" | "not_met">("all");
  const [candidateSearchQuery, setCandidateSearchQuery] = useState("");

  // Requirement Expansion & JD Citation Modal State
  const [expandedReqIds, setExpandedReqIds] = useState<Set<string>>(new Set());
  const [activeModalReq, setActiveModalReq] = useState<RequirementMatch | null>(null);
  const [citationCopiedId, setCitationCopiedId] = useState<string | null>(null);

  const toggleRequirementExpand = (reqId: string) => {
    setExpandedReqIds((prev) => {
      const next = new Set(prev);
      if (next.has(reqId)) {
        next.delete(reqId);
      } else {
        next.add(reqId);
      }
      return next;
    });
  };

  // Sync with incoming props if they change externally
  useEffect(() => {
    if (selectedJobId && selectedJobId !== activeJobId) {
      setActiveJobId(selectedJobId);
    } else if (!activeJobId && jobs.length > 0) {
      setActiveJobId(jobs[0].id);
    }
  }, [selectedJobId, jobs]);

  useEffect(() => {
    if (candidateId && candidateId !== activeCandidateId) {
      setActiveCandidateId(candidateId);
      fetchCandidateCohort(candidateId);
    }
  }, [candidateId]);

  // Fetch available candidates cohort on mount or when requested
  const fetchCandidateCohort = async (targetCandId?: string | null) => {
    try {
      const data = await api.getCandidates(1000);
      let list = Array.isArray(data) ? [...data] : [];

      const cidToFind = targetCandId || activeCandidateId || candidateId;
      if (cidToFind && !list.some((c) => c.id === cidToFind)) {
        try {
          const singleCand = await api.getCandidate(cidToFind);
          if (singleCand) {
            list = [
              {
                id: singleCand.id,
                masked_name: singleCand.masked_name || `Candidate-${singleCand.id.slice(0, 6)}`,
                original_filename: singleCand.original_filename ?? null,
                skills: singleCand.skills || [],
                total_years_experience: singleCand.total_years_experience ?? 0,
                chunks_indexed: singleCand.chunks_indexed || 0,
                created_at: singleCand.created_at || new Date().toISOString(),
              },
              ...list,
            ];
          }
        } catch (e) {
          console.warn("Could not fetch target candidate individually:", e);
        }
      }

      setCandidates(list);

      if (!activeCandidateId && list.length > 0 && candidateId) {
        setActiveCandidateId(candidateId);
      }
    } catch (err) {
      console.warn("Failed fetching candidates list in EvaluationView:", err);
    }
  };

  useEffect(() => {
    fetchCandidateCohort(candidateId);
  }, []);

  const activeJob = jobs.find((j) => j.id === activeJobId) || jobs[0];
  const activeCandidate = candidates.find((c) => c.id === activeCandidateId);

  // Execute Semantic Evaluation on demand
  const handleRunEvaluation = async (candId?: string | null, job?: JobDescription | null) => {
    const targetCandidateId = candId || activeCandidateId;
    const targetJob = job || activeJob;
    if (!targetCandidateId || !targetJob) return;

    const controller = evalTimer.startTimer();
    try {
      setEvaluating(true);
      const [result, cand] = await Promise.all([
        api.evaluateCandidate(targetCandidateId, targetJob, controller.signal),
        api.getCandidate(targetCandidateId).catch(() => null),
      ]);
      const duration = evalTimer.stopTimer(true);
      if (duration !== null) {
        setEvalDuration(duration);
      }
      setEvaluation(result);
      setCandidateDetail(cand);
      setDecision(result.recommendation);
      const firstQuote = result.requirement_matches?.find((rm) => rm.citations?.length > 0)?.citations[0]?.quote;
      if (firstQuote) setActiveCitation(firstQuote);
      await fetchCandidateCohort(targetCandidateId);
    } catch (err: any) {
      if (err.name === "AbortError" || controller.signal.aborted) {
        evalTimer.stopTimer(false);
        return;
      }
      evalTimer.stopTimer(false);
      alert(`Evaluation failed: ${err.message}`);
    } finally {
      setEvaluating(false);
    }
  };

  const handleCancelEvaluation = () => {
    evalTimer.cancelTimer();
    setEvaluating(false);
  };

  // Load existing evaluations whenever candidate or target job changes
  const loadEvaluation = async () => {
    if (!activeCandidateId || !activeJob) {
      setEvaluation(null);
      setCandidateDetail(null);
      return;
    }

    try {
      setLoading(true);
      const [evals, cand] = await Promise.all([
        api.getJobEvaluations(activeJob.id).catch((err) => {
          console.warn("Could not fetch existing job evaluations:", err);
          return [] as MatchEvaluationResult[];
        }),
        api.getCandidate(activeCandidateId).catch(() => null),
      ]);

      setCandidateDetail(cand);
      const existing = evals.find((e) => e.candidate_id === activeCandidateId);

      if (existing) {
        setEvaluation(existing);
        setDecision(existing.recommendation);
        setNotes(existing.recruiter_notes || "");
        const firstQuote = existing.requirement_matches?.find((rm) => rm.citations?.length > 0)?.citations[0]?.quote;
        if (firstQuote) setActiveCitation(firstQuote);
        if (autoRun) {
          onResetAutoRun?.();
        }
      } else {
        setEvaluation(null);
        if (autoRun) {
          onResetAutoRun?.();
          await handleRunEvaluation(activeCandidateId, activeJob);
        }
      }
    } catch (err) {
      console.error("Failed loading candidate evaluation:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEvaluation();
  }, [activeCandidateId, activeJob?.id]);

  // Resolve an interpretive requirement clarification (Yes / No toggle by Recruiter)
  const handleResolveClarification = (requirementId: string, answer: "yes" | "no") => {
    if (!evaluation) return;

    const newMatches = evaluation.requirement_matches.map((rm) => {
      if (rm.requirement_id === requirementId) {
        const meta = getRequirementMeta(rm, activeJob);
        if (answer === "yes") {
          return {
            ...rm,
            status: "met" as const,
            score: 1.0,
            confidence: 1.0,
            reasoning: `${rm.reasoning} [Recruiter Verified: Candidate confirmed readiness/availability for ${meta.title} via screening call/form]`,
            gap_analysis: null,
          };
        } else {
          return {
            ...rm,
            status: "not_met" as const,
            score: 0.0,
            confidence: 1.0,
            reasoning: `${rm.reasoning} [Recruiter Verified: Candidate declined/unavailable for ${meta.title}]`,
            gap_analysis: `Candidate explicitly declined or unavailable for: ${meta.title}`,
          };
        }
      }
      return rm;
    });

    // Recompute score and recommendation dynamically
    const reqLookup = new Map((activeJob?.requirements || []).map((r) => [r.id, r]));
    let mustHaveWeighted = 0;
    let mustHaveWeight = 0;
    let niceWeighted = 0;
    let niceWeight = 0;
    let mustHaveGaps = 0;
    let pendingClarifications = 0;

    for (const m of newMatches) {
      const req = reqLookup.get(m.requirement_id);
      const weight = req?.weight ?? 1.0;
      const isMustHave = req?.category === "must_have";

      if (m.status === "clarification_needed") {
        pendingClarifications += 1;
      }

      if (isMustHave) {
        mustHaveWeight += weight;
        mustHaveWeighted += m.score * weight;
        if (m.status === "not_met") {
          mustHaveGaps += 1;
        }
      } else {
        niceWeight += weight;
        niceWeighted += m.score * weight;
      }
    }

    const mustScore = mustHaveWeight > 0 ? (mustHaveWeighted / mustHaveWeight) * 100 : 100;
    const niceScore = niceWeight > 0 ? (niceWeighted / niceWeight) * 100 : 100;
    const overall = Math.round((0.75 * mustScore + 0.25 * niceScore) * 100) / 100;

    let newRec: "strong_match" | "borderline" | "reject" = "strong_match";
    if (mustHaveGaps >= 2 || (mustHaveGaps >= 1 && overall < 50)) {
      newRec = "reject";
    } else if (mustHaveGaps === 1 || pendingClarifications > 0 || (overall >= 50 && overall < 70)) {
      newRec = "borderline";
    } else {
      newRec = "strong_match";
    }

    const updatedEval: MatchEvaluationResult = {
      ...evaluation,
      overall_score: overall,
      must_have_score: Math.round(mustScore * 100) / 100,
      nice_to_have_score: Math.round(niceScore * 100) / 100,
      must_have_gaps_count: mustHaveGaps,
      clarification_count: pendingClarifications,
      recommendation: newRec,
      requirement_matches: newMatches,
    };

    setEvaluation(updatedEval);
    setDecision(newRec);
  };

  // Submit Recruiter Sign-Off (Article 14 Human Gate)
  const handleSubmitHITL = async () => {
    if (!evaluation) return;
    if (!notes.trim()) {
      alert("Please provide recruiter justification notes for the audit trail.");
      return;
    }

    try {
      setSubmittingHitl(true);
      const updated = await api.submitHITLDecision(evaluation.id, decision, notes, evaluation.requirement_matches);
      setEvaluation(updated);
      setHitlSuccess(true);
      setTimeout(() => setHitlSuccess(false), 3500);
      await fetchCandidateCohort();
    } catch (err: any) {
      alert(`HITL submission failed: ${err.message}`);
    } finally {
      setSubmittingHitl(false);
    }
  };

  // Candidate index in list for next/prev quick stepping
  const currentCandidateIndex = candidates.findIndex((c) => c.id === activeCandidateId);

  const handleStepCandidate = (direction: "prev" | "next") => {
    if (candidates.length === 0) return;
    let nextIndex = currentCandidateIndex;
    if (direction === "prev") {
      nextIndex = currentCandidateIndex > 0 ? currentCandidateIndex - 1 : candidates.length - 1;
    } else {
      nextIndex = currentCandidateIndex < candidates.length - 1 ? currentCandidateIndex + 1 : 0;
    }
    const nextCand = candidates[nextIndex];
    if (nextCand) {
      setActiveCandidateId(nextCand.id);
      onSelectCandidate?.(nextCand.id);
    }
  };

  const handleSelectJobChange = (newJobId: string) => {
    setActiveJobId(newJobId);
    onSelectJob?.(newJobId);
  };

  const handleSelectCandidateChange = (newCandidateId: string) => {
    setActiveCandidateId(newCandidateId);
    onSelectCandidate?.(newCandidateId);
  };

  const allCitations = useMemo(() => {
    if (!evaluation) return [];
    return evaluation.requirement_matches.flatMap((rm) => rm.citations || []);
  }, [evaluation]);

  // Requirement status counts
  const statusCounts = useMemo(() => {
    if (!evaluation) return { met: 0, partial: 0, clarification_needed: 0, not_met: 0, total: 0 };
    return {
      met: evaluation.requirement_matches.filter((rm) => rm.status === "met").length,
      partial: evaluation.requirement_matches.filter((rm) => rm.status === "partial").length,
      clarification_needed: evaluation.requirement_matches.filter((rm) => rm.status === "clarification_needed").length,
      not_met: evaluation.requirement_matches.filter((rm) => rm.status === "not_met").length,
      total: evaluation.requirement_matches.length,
    };
  }, [evaluation]);

  // Filtered requirements
  const filteredRequirements = useMemo(() => {
    if (!evaluation) return [];
    if (requirementFilter === "all") return evaluation.requirement_matches;
    return evaluation.requirement_matches.filter((rm) => rm.status === requirementFilter);
  }, [evaluation, requirementFilter]);

  const recBadge = evaluation
    ? getRecommendationBadge(evaluation.recommendation)
    : null;

  // Filter candidates in picker when none selected
  const filteredPickerCandidates = candidates.filter((c) => {
    if (!candidateSearchQuery.trim()) return true;
    const q = candidateSearchQuery.toLowerCase();
    const name = (c.masked_name || "").toLowerCase();
    const file = (c.original_filename || "").toLowerCase();
    const skills = (c.skills || []).map((s) => s.toLowerCase());
    return name.includes(q) || file.includes(q) || skills.some((s) => s.includes(q));
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ========================================================================= */}
      {/* 1. TOP SELECTION & SCOPE TOOLBAR (Candidate & JD Switcher)                */}
      {/* ========================================================================= */}
      <div className="p-4 rounded-2xl border border-slate-800 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          {/* Breadcrumb & Navigation */}
          <div className="flex items-center gap-3">
            <button
              onClick={onBackToPipeline}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-medium transition-colors cursor-pointer border border-slate-700/60"
              title="Return to Candidate Screening Pipeline"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Pipeline</span>
            </button>

            <div>
              <h1 className="text-base md:text-lg font-bold text-white tracking-tight flex items-center gap-2">
                <span>Verification &amp; Human-in-the-Loop Audit</span>
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Audit verbatim CV citations against atomic criteria and record Article 14 human validation.
              </p>
            </div>
          </div>

          {/* Quick Actions on the Right */}
          <div className="flex items-center gap-2 flex-wrap">
            {evaluation && (
              <>
                <button
                  onClick={() => setShowDocViewer(!showDocViewer)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all cursor-pointer shadow-sm ${
                    showDocViewer
                      ? "bg-blue-600/15 border-blue-500/40 text-blue-300"
                      : "bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-300"
                  }`}
                  title={showDocViewer ? "Hide split-screen CV document viewer" : "Open CV document viewer"}
                >
                  <FileText className="w-3.5 h-3.5 text-blue-400" />
                  <span>{showDocViewer ? "Hide Document" : "Inspect Document"}</span>
                </button>

                <button
                  onClick={() => setShowComplianceModal(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-500/40 text-indigo-200 text-xs font-semibold transition-all cursor-pointer shadow-sm hover:border-indigo-400/60"
                  title="Generate auditable EU AI Act Annex III Dossier"
                >
                  <FileCheck2 className="w-3.5 h-3.5 text-indigo-400" />
                  <span>EU AI Act Dossier</span>
                </button>

                <button
                  onClick={() => handleRunEvaluation()}
                  disabled={evaluating}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-medium transition-all cursor-pointer disabled:opacity-50"
                  title="Re-run semantic evaluation on candidate"
                >
                  <RotateCw className={`w-3.5 h-3.5 text-slate-400 ${evaluating ? "animate-spin text-blue-400" : ""}`} />
                  <span>{evaluating ? "Evaluating..." : "Re-evaluate"}</span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Dual Selectors: Job Description & Candidate Switcher */}
        <div className="pt-3 border-t border-slate-800/80 grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {/* Target Requisition Selector */}
          <div className="flex items-center gap-2.5 p-2 rounded-xl bg-slate-950/60 border border-slate-800/90">
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 shrink-0">
              <Briefcase className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <label className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 block mb-0.5">
                Target Job Requisition
              </label>
              <select
                value={activeJobId || ""}
                onChange={(e) => handleSelectJobChange(e.target.value)}
                className="w-full bg-transparent text-sm font-semibold text-white focus:outline-none cursor-pointer truncate"
              >
                {jobs.map((job) => (
                  <option key={job.id} value={job.id} className="bg-slate-900 text-slate-100">
                    {job.title} ({job.department || "General"} • {job.requirements?.length ?? 0} criteria)
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Candidate Selector with Prev / Next Buttons */}
          <div className="flex items-center gap-2 p-2 rounded-xl bg-slate-950/60 border border-slate-800/90">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 shrink-0">
              <UserCheck className="w-4 h-4" />
            </div>

            <div className="flex-1 min-w-0">
              <label className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 block mb-0.5">
                Audited Candidate ({candidates.length} in cohort)
              </label>
              <select
                value={activeCandidateId || ""}
                onChange={(e) => handleSelectCandidateChange(e.target.value)}
                className="w-full bg-transparent text-sm font-semibold text-white focus:outline-none cursor-pointer truncate"
              >
                <option value="" disabled className="bg-slate-900 text-slate-400">
                  Select a candidate to audit...
                </option>
                {activeCandidateId && !candidates.some((c) => c.id === activeCandidateId) && (
                  <option value={activeCandidateId} className="bg-slate-900 text-slate-100">
                    {candidateDetail?.masked_name || `Candidate-${activeCandidateId.slice(0, 6)}`} • {candidateDetail?.original_filename || "CV Document"} (Selected)
                  </option>
                )}
                {candidates.map((cand) => (
                  <option key={cand.id} value={cand.id} className="bg-slate-900 text-slate-100">
                    {cand.masked_name || `Candidate-${cand.id.slice(0, 6)}`} • {cand.original_filename || "CV Document"} ({cand.skills.length} skills)
                  </option>
                ))}
              </select>
            </div>

            {/* Stepper Buttons */}
            {candidates.length > 1 && (
              <div className="flex items-center gap-1 border-l border-slate-800 pl-2 shrink-0">
                <button
                  onClick={() => handleStepCandidate("prev")}
                  className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer border border-slate-800"
                  title="Previous Candidate in cohort"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => handleStepCandidate("next")}
                  className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer border border-slate-800"
                  title="Next Candidate in cohort"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Live Evaluation Timer & Cancellation Banner */}
      {evaluating && (
        <div className="w-full">
          <LiveProcessTimer
            isRunning={evalTimer.isRunning}
            elapsedSeconds={evalTimer.elapsedSeconds}
            onCancel={handleCancelEvaluation}
            label="Evaluating candidate match against requirements with AI Engine..."
            estimateText="Multi-agent reasoning active (typically 5 - 15s)"
            cancelLabel="Cancel Evaluation"
            modelName={evaluation?.token_usage?.display_name || "Active AI Model"}
            tokenUsage={evaluation?.token_usage}
          />
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. CANDIDATE SELECTION PICKER (Shown when no candidate is selected)       */}
      {/* ========================================================================= */}
      {!activeCandidateId ? (
        <div className="p-8 rounded-2xl border border-slate-800 bg-slate-900/40 text-center space-y-6">
          <div className="max-w-md mx-auto space-y-2">
            <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400 mx-auto shadow-inner">
              <Users2 className="w-6 h-6" />
            </div>
            <h2 className="text-base font-bold text-white">Select a Candidate for Grounded Audit</h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              Choose any candidate from your registered cohort to inspect verbatim citations, verify factual claims, and record your Article 14 recruiter validation.
            </p>
          </div>

          {/* Quick Search */}
          <div className="max-w-md mx-auto relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={candidateSearchQuery}
              onChange={(e) => setCandidateSearchQuery(e.target.value)}
              placeholder="Search by candidate name, filename, or skills..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Candidate Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-left max-h-[460px] overflow-y-auto pr-1">
            {filteredPickerCandidates.map((cand) => (
              <button
                key={cand.id}
                onClick={() => handleSelectCandidateChange(cand.id)}
                className="p-3.5 rounded-xl border border-slate-800/80 bg-slate-950/60 hover:bg-slate-900 hover:border-blue-500/50 transition-all text-left group cursor-pointer space-y-2 shadow-sm"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-semibold text-sm text-white group-hover:text-blue-300 transition-colors truncate">
                    {cand.masked_name || `Candidate-${cand.id.slice(0, 6)}`}
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

                <div className="text-xs text-slate-400 truncate">
                  {cand.original_filename || "Uploaded CV document"}
                </div>

                <div className="flex flex-wrap gap-1 pt-1">
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
              </button>
            ))}
          </div>

          {filteredPickerCandidates.length === 0 && (
            <div className="py-8 text-xs text-slate-500">
              No candidates found matching &quot;{candidateSearchQuery}&quot;. Upload a candidate in the Pipeline first.
            </div>
          )}
        </div>
      ) : loading ? (
        <div className="p-16 rounded-2xl border border-slate-800 bg-slate-900/30 flex flex-col items-center justify-center gap-3 text-slate-400 text-sm">
          <Loader2 className="w-7 h-7 animate-spin text-blue-500" />
          <span>Loading evaluation records and citations...</span>
        </div>
      ) : !evaluation ? (
        /* ========================================================================= */
        /* 3. CANDIDATE HAS NOT BEEN EVALUATED FOR THIS JOB                          */
        /* ========================================================================= */
        <div className="space-y-6">
          {/* 3a. Requisition Zero-Criteria Warning if applicable */}
          {(!activeJob?.requirements || activeJob.requirements.length === 0) ? (
            <div className="p-6 rounded-2xl border border-rose-500/40 bg-rose-950/20 text-rose-200 space-y-3 shadow-lg">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-rose-500/20 text-rose-400">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">
                    Zero Calibrated Criteria for &quot;{activeJob?.title || "Selected Requisition"}&quot;
                  </h3>
                  <p className="text-xs text-rose-300/80">
                    This job requisition currently has 0 requirements in the database. Running an evaluation against it will yield 0 criteria matches.
                  </p>
                </div>
              </div>
              <p className="text-xs text-slate-300">
                Please calibrate requirements in <strong>Requisition Studio</strong> or parse a new job description to generate atomic criteria before running evaluations.
              </p>
            </div>
          ) : (
            /* 3b. Ready to Evaluate Action Ribbon */
            <div className="p-5 rounded-2xl border border-blue-500/30 bg-gradient-to-r from-blue-950/40 via-slate-900/60 to-slate-900/40 shadow-xl space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-amber-500/15 border border-amber-500/30 text-amber-300">
                      Evaluation Pending
                    </span>
                    <span className="text-xs text-slate-400">
                      • {activeJob.requirements.length} atomic criteria calibrated
                    </span>
                  </div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <span>Audit Ready for {activeCandidate?.masked_name || candidateDetail?.masked_name || "Candidate"}</span>
                    <span className="text-xs font-normal text-slate-400">against</span>
                    <span className="text-blue-300">{activeJob.title}</span>
                  </h2>
                  <p className="text-xs text-slate-300">
                    Execute semantic analysis to score compliance, extract verbatim CV citations, and generate Article 14 audit trail.
                  </p>
                </div>

                <div className="flex items-center gap-2.5 flex-wrap">
                  <button
                    onClick={() => setShowDocViewer(!showDocViewer)}
                    className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border text-xs font-semibold transition-all cursor-pointer shadow-sm ${
                      showDocViewer
                        ? "bg-blue-600/15 border-blue-500/40 text-blue-300"
                        : "bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-300"
                    }`}
                    title={showDocViewer ? "Hide document viewer" : "Inspect candidate CV document"}
                  >
                    <FileText className="w-4 h-4 text-blue-400" />
                    <span>{showDocViewer ? "Hide Document" : "Inspect Document"}</span>
                  </button>

                  <button
                    onClick={() => handleRunEvaluation()}
                    disabled={evaluating}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-bold shadow-lg shadow-blue-600/30 transition-all cursor-pointer disabled:opacity-50"
                  >
                    {evaluating ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <ShieldCheck className="w-4 h-4" />
                    )}
                    <span>{evaluating ? "Evaluating..." : "Run AI Semantic Evaluation & Audit"}</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 3c. Split Layout: Requisition Criteria Preview vs Candidate CV Document */}
          <div className={showDocViewer ? "grid grid-cols-1 lg:grid-cols-12 gap-6 items-start" : "space-y-4"}>
            {/* Left Column: Calibrated Requirements Preview */}
            <div className={showDocViewer ? "lg:col-span-7 space-y-3" : "space-y-3"}>
              <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5 text-blue-400" />
                  <span>Calibrated Criteria ({activeJob?.requirements?.length || 0})</span>
                </span>
                <span className="text-slate-500">
                  Pre-evaluation Specification
                </span>
              </div>

              {(!activeJob?.requirements || activeJob.requirements.length === 0) ? (
                <div className="p-8 rounded-xl border border-slate-800 bg-slate-900/30 text-center text-slate-400 text-xs">
                  No criteria configured for this job requisition.
                </div>
              ) : (
                activeJob.requirements.map((req, rIdx) => {
                  const meta = getRequirementMeta(
                    {
                      requirement_id: req.id,
                      title: req.title,
                      jd_summary: req.description,
                      jd_citation: req.description,
                    },
                    activeJob
                  );

                  return (
                    <div
                      key={req.id || rIdx}
                      className="p-4 rounded-xl border border-slate-800/80 bg-slate-900/50 hover:border-slate-700/80 transition-all space-y-2.5 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-sm text-white">
                              {meta.title}
                            </span>
                            <span className="text-[10px] font-mono text-slate-500 px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">
                              {meta.slug}
                            </span>
                          </div>

                          <div className="flex items-center gap-2 text-xs text-slate-400">
                            <span
                              className={`font-semibold ${
                                req.category === "must_have" ? "text-rose-400" : "text-blue-400"
                              }`}
                            >
                              {req.category === "must_have" ? "Must-Have" : "Nice-to-Have"}
                            </span>
                            <span className="text-slate-600">•</span>
                            <span>Weight: {req.weight}x</span>
                            {req.minimum_years_experience && (
                              <>
                                <span className="text-slate-600">•</span>
                                <span className="text-slate-300">
                                  {req.minimum_years_experience}+ yrs exp required
                                </span>
                              </>
                            )}
                          </div>
                        </div>

                        <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/50">
                          Pending Audit
                        </span>
                      </div>

                      <p className="text-xs text-slate-300 leading-relaxed font-sans bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60">
                        {req.description}
                      </p>
                    </div>
                  );
                })
              )}
            </div>

            {/* Right Column: CV Document Inspector */}
            {showDocViewer && (
              <div className="lg:col-span-5 h-[calc(100vh-140px)] min-h-[560px] sticky top-0 self-start">
                <DocumentViewer
                  candidate={candidateDetail}
                  activeCitation={null}
                  allCitations={[]}
                  onClose={() => setShowDocViewer(false)}
                />
              </div>
            )}
          </div>
        </div>
      ) : (
        /* ========================================================================= */
        /* 4. ACTIVE EVALUATION DISPLAY (RE-DESIGNED, HIGH-LEGIBILITY LAYOUT)        */
        /* ========================================================================= */
        <div className="space-y-6">
          {/* Executive Verdict & KPI Summary Ribbon */}
          <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/70 backdrop-blur-md shadow-md space-y-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              {/* Score & Algorithmic Verdict */}
              <div className="flex items-center gap-4">
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-white tracking-tight tabular-nums">
                    {evaluation.overall_score.toFixed(0)}%
                  </span>
                  <span className="text-xs uppercase font-semibold text-slate-400">
                    Overall Match
                  </span>
                </div>

                <div className="h-6 w-px bg-slate-800" />

                {recBadge && (
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold tracking-wide uppercase shadow-sm ${recBadge.className}`}
                    >
                      {recBadge.label}
                    </span>
                  </div>
                )}

                <div className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-xs font-semibold text-emerald-300">
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{(evaluation.citation_verification_score * 100).toFixed(0)}% Grounded</span>
                </div>

                {evalDuration && (
                  <DurationBadge
                    duration={evalDuration}
                    label="Evaluation Duration"
                    className="hidden md:inline-flex bg-slate-900/90 border-slate-700 text-slate-300"
                  />
                )}

                {evaluation.token_usage && (
                  <TokenUsageBadge
                    usage={evaluation.token_usage}
                    className="hidden md:inline-flex"
                  />
                )}

                {statusCounts.clarification_needed > 0 && (
                  <div className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/30 text-xs font-semibold text-violet-300">
                    <HelpCircle className="w-3.5 h-3.5 text-violet-400" />
                    <span>{statusCounts.clarification_needed} Clarifications Needed</span>
                  </div>
                )}
              </div>

              {/* Recruiter Validation State */}
              <div className="flex items-center gap-2 text-xs">
                {evaluation.hitl_validated ? (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-950/40 border border-emerald-500/30 text-emerald-300">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span className="font-semibold">Article 14 Human Sign-off Recorded</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-950/40 border border-amber-500/30 text-amber-300">
                    <AlertCircle className="w-4 h-4 text-amber-400 animate-pulse" />
                    <span className="font-semibold">Recruiter Sign-off Pending</span>
                  </div>
                )}
              </div>
            </div>

            {/* Filter Tabs for Requirements List */}
            <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between flex-wrap gap-2 text-xs">
              <div className="flex items-center gap-1.5 p-1 bg-slate-950/80 rounded-xl border border-slate-800/80">
                <button
                  onClick={() => setRequirementFilter("all")}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
                    requirementFilter === "all"
                      ? "bg-blue-600 text-white font-semibold shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  All ({statusCounts.total})
                </button>
                <button
                  onClick={() => setRequirementFilter("met")}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
                    requirementFilter === "met"
                      ? "bg-emerald-600 text-white font-semibold shadow-sm"
                      : "text-emerald-400 hover:text-emerald-300"
                  }`}
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Met ({statusCounts.met})</span>
                </button>
                <button
                  onClick={() => setRequirementFilter("partial")}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
                    requirementFilter === "partial"
                      ? "bg-amber-600 text-white font-semibold shadow-sm"
                      : "text-amber-400 hover:text-amber-300"
                  }`}
                >
                  <AlertCircle className="w-3.5 h-3.5" />
                  <span>Partial ({statusCounts.partial})</span>
                </button>
                <button
                  onClick={() => setRequirementFilter("clarification_needed")}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
                    requirementFilter === "clarification_needed"
                      ? "bg-violet-600 text-white font-semibold shadow-sm"
                      : "text-violet-400 hover:text-violet-300"
                  }`}
                >
                  <HelpCircle className="w-3.5 h-3.5" />
                  <span>Clarification Needed ({statusCounts.clarification_needed})</span>
                </button>
                <button
                  onClick={() => setRequirementFilter("not_met")}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
                    requirementFilter === "not_met"
                      ? "bg-rose-600 text-white font-semibold shadow-sm"
                      : "text-rose-400 hover:text-rose-300"
                  }`}
                >
                  <XCircle className="w-3.5 h-3.5" />
                  <span>Unmet ({statusCounts.not_met})</span>
                </button>
              </div>

              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="text-xs text-slate-400">
                  Showing <strong>{filteredRequirements.length}</strong> requirements • Click titles to inspect JD request &amp; citation
                </div>

                {filteredRequirements.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      if (expandedReqIds.size === filteredRequirements.length) {
                        setExpandedReqIds(new Set());
                      } else {
                        setExpandedReqIds(new Set(filteredRequirements.map((r) => r.requirement_id)));
                      }
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 hover:text-white transition-colors cursor-pointer border border-slate-700/60"
                  >
                    <BookOpen className="w-3.5 h-3.5 text-blue-400" />
                    <span>
                      {expandedReqIds.size === filteredRequirements.length && filteredRequirements.length > 0
                        ? "Collapse All JD Citations"
                        : "Expand All JD Citations"}
                    </span>
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* ========================================================================= */}
          {/* 5. MAIN CONTENT SPLIT GRID: Requirements List vs Right Interactive Panel  */}
          {/* ========================================================================= */}
          <div className={showDocViewer ? "grid grid-cols-1 lg:grid-cols-12 gap-6 items-start" : "grid grid-cols-1 lg:grid-cols-3 gap-6 items-start"}>
            {/* Left Column: Requirements and Grounded Quotes */}
            <div className={showDocViewer ? "lg:col-span-7 space-y-4" : "lg:col-span-2 space-y-4"}>
              {filteredRequirements.length === 0 ? (
                <div className="p-8 rounded-xl border border-slate-800 bg-slate-900/30 text-center text-slate-400 text-sm">
                  No requirements match the selected filter ({requirementFilter}).
                </div>
              ) : (
                filteredRequirements.map((rm, idx) => {
                  const isMet = rm.status === "met";
                  const isPartial = rm.status === "partial";
                  const isClarification = rm.status === "clarification_needed";
                  const isObjective = rm.is_objective !== false;
                  const reqMeta = getRequirementMeta(rm, activeJob);
                  const isExpanded = expandedReqIds.has(rm.requirement_id);

                  return (
                    <div
                      key={idx}
                      className={`p-5 rounded-2xl border transition-all space-y-3.5 shadow-sm ${
                        isClarification
                          ? "border-violet-500/30 bg-slate-900/60 hover:border-violet-500/50"
                          : isExpanded
                          ? "border-blue-500/40 bg-slate-900/70 ring-1 ring-blue-500/20"
                          : "border-slate-800/90 bg-slate-900/50 hover:border-slate-700/80"
                      }`}
                    >
                      {/* Requirement Header */}
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-2.5 flex-1 min-w-0">
                          <div className="mt-0.5 shrink-0">
                            {isMet ? (
                              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                            ) : isPartial ? (
                              <AlertCircle className="w-5 h-5 text-amber-400" />
                            ) : isClarification ? (
                              <HelpCircle className="w-5 h-5 text-violet-400" />
                            ) : (
                              <XCircle className="w-5 h-5 text-rose-400" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <button
                                type="button"
                                onClick={() => toggleRequirementExpand(rm.requirement_id)}
                                className="text-left font-semibold text-base text-white hover:text-blue-300 transition-colors cursor-pointer group flex items-center gap-1.5 leading-snug"
                                title="Click to inspect JD request summary and verbatim citation"
                              >
                                <span>{reqMeta.title}</span>
                                <span className="p-0.5 rounded-md bg-slate-800 text-slate-400 group-hover:text-blue-300 group-hover:bg-blue-500/20 transition-all">
                                  {isExpanded ? (
                                    <ChevronUp className="w-3.5 h-3.5" />
                                  ) : (
                                    <ChevronDown className="w-3.5 h-3.5" />
                                  )}
                                </span>
                              </button>

                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setActiveModalReq(rm);
                                }}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 border border-blue-500/30 transition-all cursor-pointer"
                                title="Open full Requisition Specification & Citation dialog"
                              >
                                <BookOpen className="w-3 h-3 text-blue-400" />
                                <span>JD Citation</span>
                              </button>

                              <span className="text-[10px] font-mono text-slate-500 px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">
                                {reqMeta.slug}
                              </span>
                            </div>

                            <div className="text-xs text-slate-400 mt-1 flex items-center gap-2 flex-wrap">
                              <span>Confidence: {(rm.confidence * 100).toFixed(0)}% • Score: {(rm.score * 100).toFixed(0)}%</span>
                              <span className="text-slate-600">•</span>
                              <span className={reqMeta.category === "must_have" ? "text-rose-400 font-medium" : "text-blue-400 font-medium"}>
                                {reqMeta.category === "must_have" ? "Must-Have" : "Nice-to-Have"}
                              </span>
                              {reqMeta.minYears && (
                                <span className="text-slate-300">
                                  • {reqMeta.minYears}+ yrs exp
                                </span>
                              )}
                              {!isObjective && (
                                <span className="text-violet-300 font-medium">
                                  • Interpretive / Screening Detail
                                </span>
                              )}
                              {rm.transferable_skill && (
                                <span className="px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-medium inline-flex items-center gap-1">
                                  <ArrowRightLeft className="w-3 h-3 text-cyan-400" />
                                  <span>Transferable: {rm.transferable_skill}</span>
                                </span>
                              )}
                              {rm.benefit_of_doubt && (
                                <span className="px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-medium inline-flex items-center gap-1">
                                  <ShieldCheck className="w-3 h-3 text-indigo-400" />
                                  <span>Benefit of Doubt</span>
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        <span
                          className={`text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full shrink-0 ${
                            isMet
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : isPartial
                              ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              : isClarification
                              ? "bg-violet-500/20 text-violet-300 border border-violet-500/30 shadow-sm shadow-violet-500/10"
                              : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                          }`}
                        >
                          {isClarification ? "Clarification Needed" : rm.status.replace("_", " ")}
                        </span>
                      </div>

                      {/* Interactive Requisition Summary & Citation Panel */}
                      {isExpanded && (
                        <div className="p-4 rounded-xl border border-blue-500/40 bg-gradient-to-br from-blue-950/30 via-slate-950/80 to-slate-900/70 space-y-3.5 shadow-md animate-in fade-in slide-in-from-top-2 duration-200">
                          <div className="flex items-center justify-between gap-2 border-b border-blue-500/20 pb-2">
                            <div className="flex items-center gap-2">
                              <BookOpen className="w-4 h-4 text-blue-400" />
                              <span className="text-xs font-bold uppercase tracking-wider text-blue-300">
                                Requisition Specification &amp; JD Citation
                              </span>
                            </div>
                            <span className="text-[11px] text-slate-400">
                              Job Requisition: <strong className="text-slate-200">{activeJob?.title}</strong>
                            </span>
                          </div>

                          {/* 1. Summary of the Request */}
                          <div className="space-y-1">
                            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                              <FileText className="w-3.5 h-3.5 text-blue-400" />
                              <span>Summary of Request</span>
                            </div>
                            <p className="text-xs text-slate-200 leading-relaxed pl-5 font-sans">
                              {reqMeta.summary}
                            </p>
                          </div>

                          {/* 2. Verbatim Citation from the JD */}
                          <div className="space-y-1.5">
                            <div className="text-[11px] font-bold uppercase tracking-wider text-amber-300 flex items-center justify-between">
                              <span className="flex items-center gap-1.5">
                                <Quote className="w-3.5 h-3.5 text-amber-400" />
                                <span>Verbatim Citation from Job Description</span>
                              </span>
                              <button
                                type="button"
                                onClick={() => {
                                  navigator.clipboard.writeText(reqMeta.citation);
                                  setCitationCopiedId(rm.requirement_id);
                                  setTimeout(() => setCitationCopiedId(null), 2000);
                                }}
                                className="text-[10px] text-amber-300 hover:text-amber-200 font-medium transition-colors flex items-center gap-1 cursor-pointer"
                              >
                                <Copy className="w-3 h-3" />
                                <span>{citationCopiedId === rm.requirement_id ? "Copied Citation!" : "Copy Citation"}</span>
                              </button>
                            </div>

                            <div className="p-3.5 rounded-xl bg-slate-950/90 border border-amber-500/30 text-amber-100 text-xs italic font-serif leading-relaxed shadow-inner">
                              &ldquo;{reqMeta.citation}&rdquo;
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Reasoning paragraph (Clean 14px font for great readability) */}
                      <p className="text-sm text-slate-200 leading-relaxed font-sans pl-7">
                        {rm.reasoning}
                      </p>

                      {/* Transferable Skill Callout Card */}
                      {rm.transferable_skill && (
                        <div className="pl-7 pt-1">
                          <div className="p-3.5 rounded-xl bg-cyan-950/30 border border-cyan-500/30 flex items-center justify-between text-xs text-cyan-200 flex-wrap gap-2 shadow-inner">
                            <div className="flex items-center gap-2">
                              <ArrowRightLeft className="w-4 h-4 text-cyan-400 shrink-0" />
                              <span>
                                <strong className="text-cyan-300">Transferable Competency Detected:</strong> Candidate demonstrated proficiency with <strong className="text-white font-mono">{rm.transferable_skill}</strong>.
                              </span>
                            </div>
                            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                              Equivalent Tech
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Benefit of Doubt Callout Card */}
                      {rm.benefit_of_doubt && (
                        <div className="pl-7 pt-1">
                          <div className="p-3.5 rounded-xl bg-indigo-950/30 border border-indigo-500/30 flex items-center justify-between text-xs text-indigo-200 flex-wrap gap-2 shadow-inner">
                            <div className="flex items-center gap-2">
                              <ShieldCheck className="w-4 h-4 text-indigo-400 shrink-0" />
                              <span>
                                <strong className="text-indigo-300">Benefit of Doubt:</strong> Evaluated as partial match due to ambiguous phrasing in CV. Recommended for recruiter interview probe.
                              </span>
                            </div>
                            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                              Interview Probe
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Clarification Screening Question & Yes/No Recruiter Actions */}
                      {isClarification && (
                        <div className="pl-7 pt-1">
                          <div className="p-4 rounded-xl bg-violet-950/25 border border-violet-500/30 space-y-3 shadow-inner">
                            <div className="flex items-center justify-between gap-2 flex-wrap">
                              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-violet-300">
                                <HelpCircle className="w-4 h-4 text-violet-400" />
                                <span>Screening Question (Application Form or Recruiter Call)</span>
                              </span>
                              <span className="text-[11px] text-violet-400/80 italic">
                                Interpretive • Candidate cannot be disqualified based on CV silence
                              </span>
                            </div>

                            <p className="text-sm font-medium text-slate-100 pl-3.5 border-l-2 border-violet-500 py-0.5 leading-relaxed font-sans">
                              {rm.clarification_question || `Confirm candidate readiness for "${reqMeta.title}". [Yes / No]`}
                            </p>

                            <div className="flex items-center justify-between pt-1 border-t border-violet-500/20 flex-wrap gap-2">
                              <span className="text-xs text-slate-400">
                                Record candidate response:
                              </span>
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => handleResolveClarification(rm.requirement_id, "yes")}
                                  className="px-3 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/35 text-emerald-300 border border-emerald-500/30 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-sm hover:scale-[1.02]"
                                  title="Mark as confirmed on application form or call"
                                >
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                  <span>Yes (Confirmed)</span>
                                </button>
                                <button
                                  onClick={() => handleResolveClarification(rm.requirement_id, "no")}
                                  className="px-3 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/35 text-rose-300 border border-rose-500/30 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-sm hover:scale-[1.02]"
                                  title="Mark as not met/declined"
                                >
                                  <XCircle className="w-3.5 h-3.5 text-rose-400" />
                                  <span>No (Unconfirmed)</span>
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Verbatim Citations Grounding */}
                      {rm.citations && rm.citations.length > 0 && (
                        <div className="pl-7 space-y-2 pt-1">
                          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                            <span className="flex items-center gap-1.5 text-amber-300">
                              <Quote className="w-3.5 h-3.5 text-amber-400" />
                              <span>Verbatim CV Citations ({rm.citations.length})</span>
                            </span>
                            <span className="text-[11px] text-slate-500 font-sans normal-case">
                              Click quote to illuminate in Document Inspector
                            </span>
                          </div>

                          <div className="space-y-2">
                            {rm.citations.map((c, cIdx) => {
                              const isSelected = activeCitation === c.quote;
                              return (
                                <div
                                  key={cIdx}
                                  onClick={() => {
                                    setActiveCitation(c.quote);
                                    setShowDocViewer(true);
                                    setRightPanelTab("document");
                                  }}
                                  className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 ${
                                    isSelected
                                      ? "bg-amber-500/15 border-amber-500/60 ring-1 ring-amber-500/50 shadow-md"
                                      : "bg-slate-950/70 border-slate-800/90 hover:border-slate-700 hover:bg-slate-900/60"
                                  }`}
                                >
                                  <div className="flex items-start justify-between gap-3">
                                    <div
                                      className={`text-sm italic font-sans leading-relaxed ${
                                        isSelected ? "text-amber-100 font-medium" : "text-slate-200"
                                      }`}
                                    >
                                      &ldquo;{c.quote}&rdquo;
                                    </div>
                                    <span className="text-xs text-amber-300 hover:text-amber-200 font-sans font-semibold shrink-0 flex items-center gap-1">
                                      <Highlighter className="w-3.5 h-3.5 text-amber-400" /> View in CV &rarr;
                                    </span>
                                  </div>

                                  <div className="flex items-center justify-between text-xs text-slate-400 pt-1.5 border-t border-slate-800/70">
                                    <span>Source: {c.source_section || "Work Experience"}</span>
                                    {c.verified && (
                                      <span className="text-emerald-400 font-semibold flex items-center gap-1 text-[11px]">
                                        <Check className="w-3.5 h-3.5" /> Exact Substring Verified
                                      </span>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Gap analysis note if unmet (only for objective unmet gaps) */}
                      {rm.gap_analysis && !isClarification && (
                        <div className="pl-7 pt-1">
                          <div className="p-3 rounded-xl bg-rose-950/25 border border-rose-500/30 text-xs text-rose-200 flex items-start gap-2">
                            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                            <div>
                              <strong className="text-rose-300 font-semibold">Identified Gap: </strong>
                              {rm.gap_analysis}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Right Column: Dual-Tab Interactive Panel (Document Inspector + Sign-off Gate) */}
            <div className={showDocViewer ? "lg:col-span-5 sticky top-0 self-start space-y-4" : "lg:col-span-1 sticky top-0 self-start space-y-4"}>
              {/* Panel Tab Switcher */}
              <div className="p-1 rounded-xl bg-slate-900 border border-slate-800 flex items-center gap-1 shadow-sm">
                <button
                  onClick={() => {
                    setShowDocViewer(true);
                    setRightPanelTab("document");
                  }}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                    rightPanelTab === "document" && showDocViewer
                      ? "bg-blue-600 text-white shadow-md"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>CV Document Inspector</span>
                </button>

                <button
                  onClick={() => setRightPanelTab("signoff")}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                    rightPanelTab === "signoff"
                      ? "bg-blue-600 text-white shadow-md"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <UserCheck className="w-3.5 h-3.5" />
                  <span>Human Gate Sign-Off</span>
                  {!evaluation.hitl_validated && (
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  )}
                </button>
              </div>

              {/* View 1: CV Document Inspector */}
              {rightPanelTab === "document" && showDocViewer && (
                <div className="h-[calc(100vh-140px)] min-h-[560px] flex flex-col space-y-3">
                  <div className="flex-1 min-h-0">
                    <DocumentViewer
                      candidate={candidateDetail}
                      activeCitation={activeCitation}
                      allCitations={allCitations}
                      onClose={() => setShowDocViewer(false)}
                    />
                  </div>

                  {/* Quick Sign-off Banner beneath Document Inspector */}
                  <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/80 flex items-center justify-between gap-3 text-xs shrink-0">
                    <div className="text-slate-300">
                      Recruiter Decision:{" "}
                      <strong className="text-white capitalize">{decision.replace("_", " ")}</strong>
                    </div>
                    <button
                      onClick={() => setRightPanelTab("signoff")}
                      className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition-all cursor-pointer"
                    >
                      Record Justification &rarr;
                    </button>
                  </div>
                </div>
              )}

              {/* View 2: Human-in-the-Loop Sign-off Form */}
              {(rightPanelTab === "signoff" || !showDocViewer) && (
                <div className="p-5 rounded-2xl border border-blue-500/40 bg-slate-900/80 backdrop-blur-md shadow-2xl space-y-4 animate-in fade-in">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                    <div className="flex items-center gap-2 text-blue-400 font-bold text-sm uppercase tracking-wider">
                      <UserCheck className="w-4 h-4" />
                      <span>Article 14 Human Gate Sign-Off</span>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">
                      Audit Compliant
                    </span>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed">
                    EU AI Act mandate: The recruiter must explicitly confirm or override the algorithmic recommendation with documented justification notes before candidate progression.
                  </p>

                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-200">
                      Recruiter Final Decision <span className="text-rose-400">*</span>
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => setDecision("strong_match")}
                        className={`py-2 px-1 text-center rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                          decision === "strong_match"
                            ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 shadow-sm"
                            : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
                        }`}
                      >
                        Strong Match
                      </button>
                      <button
                        type="button"
                        onClick={() => setDecision("borderline")}
                        className={`py-2 px-1 text-center rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                          decision === "borderline"
                            ? "bg-amber-500/20 border-amber-500 text-amber-300 shadow-sm"
                            : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
                        }`}
                      >
                        Borderline
                      </button>
                      <button
                        type="button"
                        onClick={() => setDecision("reject")}
                        className={`py-2 px-1 text-center rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                          decision === "reject"
                            ? "bg-rose-500/20 border-rose-500 text-rose-300 shadow-sm"
                            : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
                        }`}
                      >
                        Reject
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-200">
                      Auditable Justification Notes <span className="text-rose-400">*</span>
                    </label>
                    <textarea
                      rows={5}
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Document rationale for verifying, confirming, or overriding the model evaluation. (e.g. Verified candidate's 4 years of Python in distributed systems; satisfactory domain depth)..."
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 leading-relaxed font-sans"
                    />
                  </div>

                  <button
                    onClick={handleSubmitHITL}
                    disabled={submittingHitl || !notes.trim()}
                    className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-bold shadow-lg shadow-blue-600/30 transition-all disabled:opacity-50 cursor-pointer"
                  >
                    {submittingHitl ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Check className="w-4 h-4" />
                    )}
                    <span>Persist Recruiter Sign-Off to Audit Trail</span>
                  </button>

                  {hitlSuccess && (
                    <div className="p-3 rounded-xl bg-emerald-950/50 border border-emerald-500/40 text-emerald-300 text-xs text-center flex items-center justify-center gap-2 animate-in fade-in">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span>Decision persisted to immutable audit log!</span>
                    </div>
                  )}

                  {showDocViewer && (
                    <button
                      onClick={() => setRightPanelTab("document")}
                      className="w-full text-center text-xs text-slate-400 hover:text-blue-300 transition-colors pt-2 cursor-pointer flex items-center justify-center gap-1"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      <span>Return to CV Document Inspector</span>
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* EU AI Act Annex III Compliance Dossier Modal */}
      {evaluation && (
        <ComplianceDossierModal
          evaluationId={evaluation.id}
          isOpen={showComplianceModal}
          onClose={() => setShowComplianceModal(false)}
        />
      )}

      {/* Requisition Specification & JD Citation Modal */}
      {activeModalReq && (() => {
        const modalMeta = getRequirementMeta(activeModalReq, activeJob);
        return (
          <div
            className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150"
            onClick={() => setActiveModalReq(null)}
          >
            <div
              className="w-full max-w-2xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl p-6 space-y-5 animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 shrink-0">
                    <BookOpen className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-base font-bold text-white tracking-tight">
                        {modalMeta.title}
                      </h3>
                      <span className="text-[10px] font-mono text-slate-400 px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">
                        {modalMeta.slug}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Target Requisition: <strong className="text-slate-200">{activeJob?.title}</strong>
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setActiveModalReq(null)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
                  title="Close dialog"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Requirement Meta Pills */}
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={`text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${
                    modalMeta.category === "must_have"
                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                      : "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                  }`}
                >
                  {modalMeta.category === "must_have" ? "Must-Have Requirement" : "Nice-to-Have"}
                </span>
                <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 font-mono">
                  Weight: {modalMeta.weight}x
                </span>
                {modalMeta.minYears && (
                  <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300">
                    Experience: {modalMeta.minYears}+ Years
                  </span>
                )}
                <span
                  className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                    activeModalReq.status === "met"
                      ? "bg-emerald-500/20 text-emerald-300"
                      : activeModalReq.status === "partial"
                      ? "bg-amber-500/20 text-amber-300"
                      : activeModalReq.status === "clarification_needed"
                      ? "bg-violet-500/20 text-violet-300"
                      : "bg-rose-500/20 text-rose-300"
                  }`}
                >
                  Evaluation: {activeModalReq.status.replace("_", " ").toUpperCase()}
                </span>
              </div>

              {/* 1. Summary of the Request */}
              <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                <div className="text-xs font-bold uppercase tracking-wider text-blue-400 flex items-center gap-1.5">
                  <FileText className="w-4 h-4" />
                  <span>Summary of the Request</span>
                </div>
                <p className="text-sm text-slate-100 leading-relaxed font-sans">
                  {modalMeta.summary}
                </p>
              </div>

              {/* 2. Verbatim Citation from Job Description */}
              <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    <Quote className="w-4 h-4" />
                    <span>Verbatim Citation from Job Description</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(modalMeta.citation);
                      setCitationCopiedId(activeModalReq.requirement_id);
                      setTimeout(() => setCitationCopiedId(null), 2000);
                    }}
                    className="text-xs text-amber-300 hover:text-amber-200 font-medium transition-colors flex items-center gap-1 cursor-pointer"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    <span>{citationCopiedId === activeModalReq.requirement_id ? "Copied Citation!" : "Copy Citation"}</span>
                  </button>
                </div>
                <div className="p-3.5 rounded-lg bg-slate-950/80 border border-amber-500/20 text-amber-100 text-sm italic font-serif leading-relaxed">
                  &ldquo;{modalMeta.citation}&rdquo;
                </div>
              </div>

              {/* 3. Candidate Grounding Evidence */}
              <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                <div className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                  <UserCheck className="w-4 h-4 text-emerald-400" />
                  <span>Candidate Evaluation &amp; Grounding</span>
                </div>
                <p className="text-sm text-slate-200 leading-relaxed font-sans">
                  {activeModalReq.reasoning}
                </p>
                {activeModalReq.citations && activeModalReq.citations.length > 0 && (
                  <div className="pt-2 border-t border-slate-800 space-y-1.5">
                    <span className="text-[11px] uppercase font-semibold text-slate-400">
                      Grounding Citations from Candidate CV ({activeModalReq.citations.length}):
                    </span>
                    {activeModalReq.citations.map((c: any, i: number) => (
                      <div key={i} className="text-xs italic text-slate-300 bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                        &ldquo;{c.quote}&rdquo; <span className="text-slate-400 font-normal">({c.source_section || "Work Experience"})</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setActiveModalReq(null)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
