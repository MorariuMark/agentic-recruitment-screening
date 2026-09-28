"use client";

import { useState, useEffect, useMemo } from "react";
import { CandidateDetail, JobDescription, MatchEvaluationResult, Recommendation } from "@/types";
import { api } from "@/lib/api";
import { getRecommendationBadge } from "@/lib/utils";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  FileCheck2,
  FileText,
  HelpCircle,
  Highlighter,
  Loader2,
  Quote,
  ShieldCheck,
  UserCheck,
  XCircle,
} from "lucide-react";
import { ComplianceDossierModal } from "@/components/compliance/compliance-dossier-modal";
import { DocumentViewer } from "@/components/evaluation/document-viewer";

interface EvaluationViewProps {
  candidateId: string | null;
  selectedJobId: string | null;
  jobs: JobDescription[];
  onBackToPipeline: () => void;
}

export function EvaluationView({
  candidateId,
  selectedJobId,
  jobs,
  onBackToPipeline,
}: EvaluationViewProps) {
  const [evaluation, setEvaluation] = useState<MatchEvaluationResult | null>(null);
  const [candidateDetail, setCandidateDetail] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [decision, setDecision] = useState<"strong_match" | "borderline" | "reject">("strong_match");
  const [notes, setNotes] = useState("");
  const [submittingHitl, setSubmittingHitl] = useState(false);
  const [hitlSuccess, setHitlSuccess] = useState(false);
  const [showComplianceModal, setShowComplianceModal] = useState(false);
  const [showDocViewer, setShowDocViewer] = useState(true);
  const [activeCitation, setActiveCitation] = useState<string | null>(null);

  const activeJob = jobs.find((j) => j.id === selectedJobId) || jobs[0];

  const loadEvaluation = async () => {
    if (!candidateId || !activeJob) return;

    try {
      setLoading(true);
      const [evals, cand] = await Promise.all([
        api.getJobEvaluations(activeJob.id),
        api.getCandidate(candidateId).catch(() => null),
      ]);
      setCandidateDetail(cand);

      const existing = evals.find((e) => e.candidate_id === candidateId);

      if (existing) {
        setEvaluation(existing);
        setDecision(existing.recommendation);
        setNotes(existing.recruiter_notes || "");
        const firstQuote = existing.requirement_matches.find((rm) => rm.citations?.length > 0)?.citations[0]?.quote;
        if (firstQuote) setActiveCitation(firstQuote);
      } else {
        setEvaluation(null);
      }
    } catch (err) {
      console.error("Failed loading candidate evaluation:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEvaluation();
  }, [candidateId, activeJob?.id]);

  const handleRunEvaluation = async () => {
    if (!candidateId || !activeJob) return;
    try {
      setEvaluating(true);
      const [result, cand] = await Promise.all([
        api.evaluateCandidate(candidateId, activeJob),
        api.getCandidate(candidateId).catch(() => null),
      ]);
      setEvaluation(result);
      setCandidateDetail(cand);
      setDecision(result.recommendation);
      const firstQuote = result.requirement_matches.find((rm) => rm.citations?.length > 0)?.citations[0]?.quote;
      if (firstQuote) setActiveCitation(firstQuote);
    } catch (err: any) {
      alert(`Evaluation failed: ${err.message}`);
    } finally {
      setEvaluating(false);
    }
  };

  const allCitations = useMemo(() => {
    if (!evaluation) return [];
    return evaluation.requirement_matches.flatMap((rm) => rm.citations || []);
  }, [evaluation]);

  const handleSubmitHITL = async () => {
    if (!evaluation) return;
    if (!notes.trim()) {
      alert("Please provide recruiter justification notes for the audit trail.");
      return;
    }

    try {
      setSubmittingHitl(true);
      const updated = await api.submitHITLDecision(evaluation.id, decision, notes);
      setEvaluation(updated);
      setHitlSuccess(true);
      setTimeout(() => setHitlSuccess(false), 3000);
    } catch (err: any) {
      alert(`HITL submission failed: ${err.message}`);
    } finally {
      setSubmittingHitl(false);
    }
  };

  const renderHitlCard = () => (
    <div className="p-5 rounded-xl border border-blue-500/30 bg-slate-900/60 space-y-4 shadow-xl">
      <div className="flex items-center gap-2 text-blue-400 font-semibold text-xs uppercase tracking-wider">
        <UserCheck className="w-4 h-4" />
        <span>Human-in-the-Loop Gate</span>
      </div>

      <p className="text-xs text-slate-400">
        EU AI Act Article 14 mandate: Recruiter must confirm or override algorithmic recommendation with auditable notes.
      </p>

      <div className="space-y-2">
        <label className="text-xs font-medium text-slate-300">
          Recruiter Final Decision
        </label>
        <div className="grid grid-cols-3 gap-2">
          <button
            type="button"
            onClick={() => setDecision("strong_match")}
            className={`py-2 px-1 text-center rounded-lg text-xs font-medium border transition-colors ${
              decision === "strong_match"
                ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 font-semibold"
                : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
            }`}
          >
            Strong Match
          </button>
          <button
            type="button"
            onClick={() => setDecision("borderline")}
            className={`py-2 px-1 text-center rounded-lg text-xs font-medium border transition-colors ${
              decision === "borderline"
                ? "bg-amber-500/20 border-amber-500 text-amber-300 font-semibold"
                : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
            }`}
          >
            Borderline
          </button>
          <button
            type="button"
            onClick={() => setDecision("reject")}
            className={`py-2 px-1 text-center rounded-lg text-xs font-medium border transition-colors ${
              decision === "reject"
                ? "bg-rose-500/20 border-rose-500 text-rose-300 font-semibold"
                : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
            }`}
          >
            Reject
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium text-slate-300">
          Auditable Justification Notes <span className="text-rose-400">*</span>
        </label>
        <textarea
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Record rationale for agreeing with or overriding the model evaluation..."
          className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-blue-500 leading-relaxed"
        />
      </div>

      <button
        onClick={handleSubmitHITL}
        disabled={submittingHitl || !notes.trim()}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-all disabled:opacity-50 cursor-pointer"
      >
        {submittingHitl ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Check className="w-3.5 h-3.5" />
        )}
        <span>Record Recruiter Sign-Off</span>
      </button>

      {hitlSuccess && (
        <div className="p-2.5 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs text-center flex items-center justify-center gap-1.5 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>Decision persisted to immutable audit log!</span>
        </div>
      )}
    </div>
  );

  if (!candidateId) {
    return (
      <div className="p-12 text-center text-slate-500 text-xs">
        Select a candidate from the Candidate Pipeline to review verbatim citations and verify compliance.
      </div>
    );
  }

  const recBadge = evaluation
    ? getRecommendationBadge(evaluation.recommendation)
    : null;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <button
              onClick={onBackToPipeline}
              className="text-xs text-blue-400 hover:text-blue-300 font-medium"
            >
              ← Back to Pipeline
            </button>
            <span className="text-slate-600">•</span>
            <span className="text-xs text-slate-400 font-mono">Candidate ID: {candidateId}</span>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-white mt-1">
            Grounded Citation Audit & Human Gate
          </h1>
          <p className="text-xs text-slate-400">
            Audit verbatim quotes extracted from candidate CV to verify claims and validate decision.
          </p>
        </div>

        {evaluation && recBadge && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowDocViewer(!showDocViewer)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors cursor-pointer shadow-sm ${
                showDocViewer
                  ? "bg-blue-950/60 border-blue-500/50 text-blue-300"
                  : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"
              }`}
            >
              <FileText className="w-3.5 h-3.5 text-blue-400" />
              <span>{showDocViewer ? "Hide Document" : "CV Document Inspector"}</span>
            </button>
            <button
              onClick={() => setShowComplianceModal(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-500/30 text-indigo-300 text-xs font-semibold transition-colors cursor-pointer shadow-sm hover:border-indigo-400/50"
            >
              <FileCheck2 className="w-3.5 h-3.5 text-indigo-400" />
              <span>EU AI Act Dossier</span>
            </button>
            <div className="text-right pl-2 border-l border-slate-800">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                Algorithmic Verdict
              </div>
              <span
                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${recBadge.className}`}
              >
                {recBadge.label}
              </span>
            </div>
            <div className="text-right pl-3 border-l border-slate-800">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                Overall Match
              </div>
              <div className="text-lg font-bold text-white tabular-nums">
                {evaluation.overall_score.toFixed(0)}%
              </div>
            </div>
          </div>
        )}
      </div>

      {loading ? (
        <div className="p-12 flex flex-col items-center justify-center gap-3 text-slate-500 text-xs">
          <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
          <span>Loading candidate evaluation...</span>
        </div>
      ) : !evaluation ? (
        <div className="p-12 rounded-xl border border-slate-800 bg-slate-900/30 text-center space-y-4">
          <div className="text-sm font-semibold text-slate-200">
            Candidate Has Not Been Evaluated for &quot;{activeJob?.title || "Active Requisition"}&quot;
          </div>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            Run deterministic semantic matching against the requisition criteria to extract citations and score requirements.
          </p>
          <button
            onClick={handleRunEvaluation}
            disabled={evaluating}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-all cursor-pointer disabled:opacity-50"
          >
            {evaluating ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <ShieldCheck className="w-3.5 h-3.5" />
            )}
            <span>Execute Semantic Evaluation</span>
          </button>
        </div>
      ) : (
        <div className={showDocViewer ? "grid grid-cols-1 lg:grid-cols-12 gap-6 items-start" : "grid grid-cols-1 lg:grid-cols-3 gap-6 items-start"}>
          {/* Left Column: Requirements Matches */}
          <div className={showDocViewer ? "lg:col-span-7 space-y-6" : "lg:col-span-2 space-y-4"}>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <span>Evaluated Requirements ({evaluation.requirement_matches.length})</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  CVS: {(evaluation.citation_verification_score * 100).toFixed(0)}%
                </span>
              </h2>
              {candidateDetail && (
                <span className="text-xs text-slate-400 font-mono">
                  CV: {candidateDetail.original_filename || "Attached"}
                </span>
              )}
            </div>

            <div className="space-y-3">
              {evaluation.requirement_matches.map((rm, idx) => {
                const isMet = rm.status === "met";
                const isPartial = rm.status === "partial";

                return (
                  <div
                    key={idx}
                    className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 space-y-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2">
                        {isMet ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        ) : isPartial ? (
                          <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                        )}
                        <span className="font-semibold text-xs text-white">
                          {rm.requirement_id}
                        </span>
                      </div>

                      <span
                        className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                          isMet
                            ? "bg-emerald-500/20 text-emerald-300"
                            : isPartial
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-rose-500/20 text-rose-300"
                        }`}
                      >
                        {rm.status}
                      </span>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      {rm.reasoning}
                    </p>

                    {/* Verbatim Citations Grounding with click-to-highlight */}
                    {rm.citations && rm.citations.length > 0 && (
                      <div className="space-y-1.5 pt-1">
                        <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                          <span className="flex items-center gap-1">
                            <Quote className="w-3 h-3 text-blue-400" />
                            <span>Verbatim CV Citations ({rm.citations.length})</span>
                          </span>
                          <span className="text-[10px] text-slate-500 font-sans">
                            Click citation to illuminate in CV
                          </span>
                        </div>
                        {rm.citations.map((c, cIdx) => {
                          const isSelected = activeCitation === c.quote;
                          return (
                            <div
                              key={cIdx}
                              onClick={() => {
                                setActiveCitation(c.quote);
                                setShowDocViewer(true);
                              }}
                              className={`p-2.5 rounded-lg border text-[11px] font-mono space-y-1.5 transition-all cursor-pointer ${
                                isSelected
                                  ? "bg-amber-500/10 border-amber-500/50 shadow-md ring-1 ring-amber-500/40"
                                  : "bg-slate-950 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
                              }`}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div
                                  className={`italic leading-relaxed ${
                                    isSelected ? "text-amber-200 font-medium" : "text-slate-300"
                                  }`}
                                >
                                  &ldquo;{c.quote}&rdquo;
                                </div>
                                <span className="text-[10px] text-blue-400 font-sans font-medium shrink-0 flex items-center gap-1 hover:underline">
                                  <Highlighter className="w-3 h-3 text-amber-400" /> View in CV →
                                </span>
                              </div>
                              <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/60">
                                <span>Source: {c.source_section || "Experience Section"}</span>
                                {c.verified && (
                                  <span className="text-emerald-400 font-sans font-medium flex items-center gap-1">
                                    <Check className="w-3 h-3" /> Exact Substring Verified
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Gap analysis note if unmet */}
                    {rm.gap_analysis && (
                      <div className="p-2 rounded bg-rose-950/20 border border-rose-500/20 text-[11px] text-rose-300">
                        <span className="font-semibold">Gap Identified:</span> {rm.gap_analysis}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {showDocViewer && renderHitlCard()}
          </div>

          {/* Right Column: Document Viewer or HITL Card */}
          {showDocViewer ? (
            <div className="lg:col-span-5 sticky top-20 h-[calc(100vh-140px)] min-h-[620px]">
              <DocumentViewer
                candidate={candidateDetail}
                activeCitation={activeCitation}
                allCitations={allCitations}
                onClose={() => setShowDocViewer(false)}
              />
            </div>
          ) : (
            <div className="lg:col-span-1 space-y-4 sticky top-20">
              {renderHitlCard()}
            </div>
          )}
        </div>
      )}

      {/* EU AI Act Annex III Compliance Modal */}
      {evaluation && (
        <ComplianceDossierModal
          evaluationId={evaluation.id}
          isOpen={showComplianceModal}
          onClose={() => setShowComplianceModal(false)}
        />
      )}
    </div>
  );
}
