"use client";

import { useState, useEffect } from "react";
import { CandidateSummary, InterviewPlan, JobDescription } from "@/types";
import { api } from "@/lib/api";
import {
  ArrowLeft,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  HelpCircle,
  Lightbulb,
  Loader2,
  MessageSquareCode,
  Printer,
  RotateCw,
  Search,
  Sparkles,
  Target,
  UserCheck,
  Users2,
} from "lucide-react";
import { LiveProcessTimer, DurationBadge, useProcessTimer } from "@/components/ui/live-process-timer";
import { getRequirementMeta } from "@/components/evaluation/evaluation-view";

interface InterviewViewProps {
  candidateId: string | null;
  selectedJobId: string | null;
  jobs: JobDescription[];
  onBackToPipeline: () => void;
  onSelectCandidate?: (candidateId: string) => void;
  onSelectJob?: (jobId: string) => void;
}

export function InterviewView({
  candidateId,
  selectedJobId,
  jobs,
  onBackToPipeline,
  onSelectCandidate,
  onSelectJob,
}: InterviewViewProps) {
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(selectedJobId || (jobs[0]?.id ?? null));
  const [activeCandidateId, setActiveCandidateId] = useState<string | null>(candidateId || null);

  const [interviewPlan, setInterviewPlan] = useState<InterviewPlan | null>(null);
  const [duration, setDuration] = useState<number>(45);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const interviewTimer = useProcessTimer();
  const [lastInterviewDuration, setLastInterviewDuration] = useState<number | null>(null);

  useEffect(() => {
    if (selectedJobId && selectedJobId !== activeJobId) {
      setActiveJobId(selectedJobId);
    }
  }, [selectedJobId]);

  useEffect(() => {
    if (candidateId && candidateId !== activeCandidateId) {
      setActiveCandidateId(candidateId);
    }
  }, [candidateId]);

  // Fetch candidate cohort list
  useEffect(() => {
    api.getCandidates()
      .then((data) => {
        if (Array.isArray(data)) setCandidates(data);
      })
      .catch((err) => console.warn("Failed fetching candidates in InterviewView:", err));
  }, []);

  const activeJob = jobs.find((j) => j.id === activeJobId) || jobs[0];
  const activeCandidate = candidates.find((c) => c.id === activeCandidateId);

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
      setInterviewPlan(null);
    }
  };

  const handleSelectJobChange = (newJobId: string) => {
    setActiveJobId(newJobId);
    onSelectJob?.(newJobId);
    setInterviewPlan(null);
  };

  const handleSelectCandidateChange = (newCandidateId: string) => {
    setActiveCandidateId(newCandidateId);
    onSelectCandidate?.(newCandidateId);
    setInterviewPlan(null);
  };

  const handleGenerate = async () => {
    if (!activeCandidateId || !activeJob) return;

    const controller = interviewTimer.startTimer();
    try {
      setLoading(true);
      const evals = await api.getJobEvaluations(activeJob.id);
      const matchedEval = (evals || []).find((e) => e.candidate_id === activeCandidateId);
      let evalId = matchedEval?.id;

      if (!evalId) {
        const evalResult = await api.evaluateCandidate(activeCandidateId, activeJob, controller.signal);
        evalId = evalResult.id;
      }

      const plan = await api.generateInterviewPlan(
        activeCandidateId,
        evalId,
        activeJob,
        duration,
        controller.signal
      );
      const timeTaken = interviewTimer.stopTimer(true);
      if (timeTaken !== null) {
        setLastInterviewDuration(timeTaken);
      }
      setInterviewPlan(plan);
    } catch (err: any) {
      if (err.name === "AbortError" || controller.signal.aborted) {
        interviewTimer.stopTimer(false);
        return;
      }
      interviewTimer.stopTimer(false);
      alert(`Interview guide synthesis failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelInterview = () => {
    interviewTimer.cancelTimer();
    setLoading(false);
  };

  const handleCopyMarkdown = () => {
    if (!interviewPlan) return;
    const text = `# Tailored STAR Interview Guide
Candidate: ${activeCandidate?.masked_name || activeCandidateId}
Requisition: ${activeJob?.title}
Duration: ${interviewPlan.total_duration_minutes} minutes

## Executive Summary
${interviewPlan.executive_summary}

## Tailored STAR Questions
${interviewPlan.questions
  .map(
    (q, i) => `### Question ${i + 1}: ${q.question_text}
- Requirement: ${q.target_requirement_id}
- Difficulty: ${q.difficulty} (${q.target_duration_minutes}m)
- Rationale: ${q.rationale_for_asking}
- Evaluation Rubric: ${q.expected_answer_rubric}
`
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
      {/* 1. TOP HEADER & INTERVIEW SCOPE TOOLBAR                                   */}
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
                <span>Tailored STAR Interview Studio</span>
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Synthesize role-specific behavioral & technical questions grounded in candidate CV claims and identified gaps.
              </p>
            </div>
          </div>

          {interviewPlan && (
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopyMarkdown}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-colors cursor-pointer shadow-sm"
              >
                <Copy className="w-3.5 h-3.5" />
                <span>{copied ? "Copied Guide!" : "Copy Guide"}</span>
              </button>
              <button
                onClick={() => window.print()}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-colors cursor-pointer shadow-sm"
              >
                <Printer className="w-3.5 h-3.5" />
                <span>Print Dossier</span>
              </button>
            </div>
          )}
        </div>

        {/* Dual Selectors: Job Description & Candidate Switcher */}
        <div className="pt-3 border-t border-slate-800/80 grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {/* Target Job Selector */}
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
                className="w-full bg-transparent text-sm font-semibold text-slate-100 focus:outline-none cursor-pointer truncate"
              >
                {jobs.map((job) => (
                  <option key={job.id} value={job.id} className="bg-slate-900 text-slate-100">
                    {job.title} ({job.department || "General"} • {job.seniority_level || "Standard"})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Candidate Selector with Stepper Buttons */}
          <div className="flex items-center gap-2 p-2 rounded-xl bg-slate-950/60 border border-slate-800/90">
            <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400 shrink-0">
              <UserCheck className="w-4 h-4" />
            </div>

            <div className="flex-1 min-w-0">
              <label className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 block mb-0.5">
                Interviewee Candidate ({candidates.length} in cohort)
              </label>
              <select
                value={activeCandidateId || ""}
                onChange={(e) => handleSelectCandidateChange(e.target.value)}
                className="w-full bg-transparent text-sm font-semibold text-slate-100 focus:outline-none cursor-pointer truncate"
              >
                <option value="" disabled className="bg-slate-900 text-slate-400">
                  Select candidate to interview...
                </option>
                {candidates.map((cand) => (
                  <option key={cand.id} value={cand.id} className="bg-slate-900 text-slate-100">
                    {cand.masked_name || `Candidate-${cand.id.slice(0, 6)}`} • {cand.original_filename || "CV Document"}
                  </option>
                ))}
              </select>
            </div>

            {candidates.length > 1 && (
              <div className="flex items-center gap-1 border-l border-slate-800 pl-2 shrink-0">
                <button
                  onClick={() => handleStepCandidate("prev")}
                  className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer border border-slate-800"
                  title="Previous Candidate"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => handleStepCandidate("next")}
                  className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer border border-slate-800"
                  title="Next Candidate"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. CANDIDATE SELECTION PICKER (Shown when no candidate selected)          */}
      {/* ========================================================================= */}
      {!activeCandidateId ? (
        <div className="p-8 rounded-2xl border border-slate-800 bg-slate-900/40 text-center space-y-6">
          <div className="max-w-md mx-auto space-y-2">
            <div className="w-12 h-12 rounded-2xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400 mx-auto shadow-inner">
              <MessageSquareCode className="w-6 h-6" />
            </div>
            <h2 className="text-base font-bold text-white">Select a Candidate for Interview Preparation</h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              Generate a personalized question plan tailored to probe candidate gaps and verify qualifications.
            </p>
          </div>

          <div className="max-w-md mx-auto relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search candidate by name or skill..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5 text-left max-h-[460px] overflow-y-auto pr-1">
            {filteredPickerCandidates.map((cand) => (
              <button
                key={cand.id}
                onClick={() => handleSelectCandidateChange(cand.id)}
                className="p-3.5 rounded-xl border border-slate-800/80 bg-slate-950/60 hover:bg-slate-900 hover:border-purple-500/50 transition-all text-left group cursor-pointer space-y-2 shadow-sm"
              >
                <div className="font-semibold text-sm text-white group-hover:text-purple-300 transition-colors truncate">
                  {cand.masked_name || `Candidate-${cand.id.slice(0, 6)}`}
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
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        /* ========================================================================= */
        /* 3. SYNTHESIS CONTROLS & GENERATED INTERVIEW GUIDE                          */
        /* ========================================================================= */
        <div className="space-y-6">
          {/* Synthesis Control Banner */}
          <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/60 backdrop-blur-md flex flex-col sm:flex-row items-center justify-between gap-4 shadow-sm">
            <div className="flex items-center gap-4 flex-wrap">
              <span className="text-xs font-semibold text-slate-300">Target Duration:</span>
              <div className="flex rounded-xl bg-slate-950 p-1 border border-slate-800 text-xs">
                {[
                  { mins: 30, label: "30 min (Express)" },
                  { mins: 45, label: "45 min (Standard)" },
                  { mins: 60, label: "60 min (Deep Dive)" },
                ].map((item) => (
                  <button
                    key={item.mins}
                    onClick={() => setDuration(item.mins)}
                    className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
                      duration === item.mins
                        ? "bg-blue-600 text-white font-semibold shadow-sm"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={handleGenerate}
              disabled={loading}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all disabled:opacity-50 cursor-pointer"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4 text-amber-300" />
              )}
              <span>{interviewPlan ? "Regenerate Questions" : "Synthesize Tailored STAR Guide"}</span>
            </button>
          </div>

          {/* Generated Plan Display */}
          {loading ? (
            <LiveProcessTimer
              timer={interviewTimer}
              title="Synthesizing STAR Interview Plan"
              description="Analyzing candidate profile, evaluation gaps, and role requirements to synthesize targeted questions."
              estimatedTimeText="Estimated time: ~10 - 20s"
              onCancel={handleCancelInterview}
            />
          ) : interviewPlan ? (
            <div className="space-y-6 animate-in fade-in duration-200">
              {/* Executive Briefing Card */}
              <div className="p-5 rounded-2xl border border-blue-500/30 bg-gradient-to-r from-blue-950/40 to-slate-900/60 space-y-2.5 shadow-md">
                <div className="text-xs font-bold uppercase tracking-wider text-blue-300 flex items-center gap-2">
                  <Lightbulb className="w-4 h-4 text-amber-400" />
                  <span>Interviewer Executive Briefing</span>
                </div>
                <p className="text-sm text-slate-100 leading-relaxed font-sans">
                  {interviewPlan.executive_summary}
                </p>
              </div>

              {/* Questions List */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                      <span>Tailored STAR Questions</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-normal">
                        {interviewPlan.questions.length} Items • {interviewPlan.total_duration_minutes}m Total
                      </span>
                    </h2>
                    {lastInterviewDuration !== null && (
                      <DurationBadge duration={lastInterviewDuration} label="Synthesized in" />
                    )}
                  </div>
                </div>

                <div className="space-y-4">
                  {interviewPlan.questions.map((q, idx) => (
                    <div
                      key={idx}
                      className="p-5 rounded-2xl border border-slate-800/90 bg-slate-900/50 hover:border-slate-700/80 transition-all space-y-4 shadow-sm"
                    >
                      {/* Question Header */}
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3">
                          <span className="w-7 h-7 rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-300 font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                            {idx + 1}
                          </span>
                          <div>
                            <h3 className="font-bold text-base text-white leading-snug">
                              {q.question_text}
                            </h3>
                            <div className="text-xs text-slate-400 mt-1 flex items-center gap-1.5 flex-wrap">
                              <span>Target Requirement:</span>
                              <strong className="text-slate-200">
                                {getRequirementMeta({ requirement_id: q.target_requirement_id }, activeJob).title}
                              </strong>
                              <span className="font-mono text-[10px] text-slate-500">
                                ({q.target_requirement_id})
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <span className="px-2.5 py-0.5 rounded-full bg-slate-800 text-xs font-semibold text-slate-300 uppercase font-mono">
                            {q.difficulty}
                          </span>
                          <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-slate-800 text-xs font-medium text-slate-400">
                            <Clock className="w-3.5 h-3.5" />
                            {q.target_duration_minutes}m
                          </span>
                        </div>
                      </div>

                      {/* 2-Column Details: Rationale & Evaluation Rubric */}
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5 pt-1">
                        {/* Why We Ask This */}
                        <div className="p-3.5 rounded-xl bg-slate-950/80 border border-amber-500/20 space-y-1.5">
                          <div className="text-xs font-semibold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
                            <Target className="w-3.5 h-3.5 text-amber-400" />
                            <span>Interviewer Rationale (Candidate Gap Probe)</span>
                          </div>
                          <p className="text-xs text-slate-200 leading-relaxed font-sans">
                            {q.rationale_for_asking}
                          </p>
                        </div>

                        {/* Expected Answer Rubric */}
                        <div className="p-3.5 rounded-xl bg-slate-950/80 border-l-2 border-emerald-400 border-r border-t border-b border-slate-800/80 space-y-1.5">
                          <div className="text-xs font-semibold uppercase tracking-wider text-emerald-300 flex items-center gap-1.5">
                            <HelpCircle className="w-3.5 h-3.5 text-emerald-400" />
                            <span>STAR Evaluation Rubric (What Good Looks Like)</span>
                          </div>
                          <p className="text-xs text-emerald-950 dark:text-emerald-100/90 leading-relaxed font-sans">
                            {q.expected_answer_rubric}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center rounded-2xl border border-slate-800 bg-slate-900/30 text-slate-400 text-sm space-y-2">
              <Sparkles className="w-8 h-8 text-blue-400 mx-auto" />
              <div className="font-semibold text-slate-200">Ready to Synthesize STAR Guide</div>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Click &ldquo;Synthesize Tailored STAR Guide&rdquo; to prompt the agent to formulate personalized questions probed from candidate citations and gaps.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
