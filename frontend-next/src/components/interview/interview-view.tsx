"use client";

import { useState, useEffect } from "react";
import { CandidateSummary, InterviewPlan, JobDescription } from "@/types";
import { api } from "@/lib/api";
import {
  AlertTriangle,
  ArrowLeft,
  Briefcase,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  Copy,
  HelpCircle,
  Lightbulb,
  Loader2,
  MessageSquareCode,
  Minus,
  Plus,
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
  const [collapsedQuestions, setCollapsedQuestions] = useState<Set<number>>(new Set());

  const toggleQuestionCollapse = (idx: number) => {
    setCollapsedQuestions((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const handleToggleAllAnswers = () => {
    if (!interviewPlan) return;
    if (collapsedQuestions.size === interviewPlan.questions.length) {
      setCollapsedQuestions(new Set());
    } else {
      setCollapsedQuestions(new Set(interviewPlan.questions.map((_, i) => i)));
    }
  };

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

  const handlePrintDossier = () => {
    if (!interviewPlan) return;
    const durationMins = interviewPlan.total_duration_minutes || interviewPlan.total_estimated_minutes || duration;
    const summary = interviewPlan.executive_summary || interviewPlan.interview_focus_summary || "";
    const candName = activeCandidate?.masked_name || `Candidate-${activeCandidateId?.slice(0, 8) || "Profile"}`;
    const jobTitle = activeJob?.title || "Requisition";

    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      window.print();
      return;
    }

    const questionsHtml = interviewPlan.questions
      .map((q, idx) => {
        const qDuration = q.target_duration_minutes || q.estimated_minutes || 10;
        const expectedText = q.expected_answer || q.expected_answer_rubric || "";
        const badText = q.bad_answer || "";
        const signals = (q.expected_answers?.length ? q.expected_answers : q.expected_positive_signals || []);
        const redFlags = (q.bad_answers?.length ? q.bad_answers : q.red_flags || []);

        return `
          <div style="border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px; margin-bottom: 20px; page-break-inside: avoid; background: #ffffff;">
            <div style="display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-start;">
              <span style="background: #2563eb; color: #ffffff; font-weight: 700; font-size: 11pt; padding: 3px 10px; border-radius: 6px;">Q${idx + 1}</span>
              <div style="flex: 1;">
                <div style="font-weight: 700; font-size: 13pt; color: #0f172a; line-height: 1.35;">${q.question_text}</div>
                <div style="font-size: 9.5pt; color: #64748b; margin-top: 4px;">
                  Target Requirement: <strong>${q.target_requirement_id}</strong> &bull; Difficulty: <strong style="text-transform: uppercase;">${q.difficulty || "mid"}</strong> &bull; Allocated: <strong>${qDuration} mins</strong>
                </div>
              </div>
            </div>

            ${q.rationale_for_asking ? `
              <div style="background: #fefce8; border: 1px solid #fef08a; padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 10pt; color: #854d0e;">
                <strong style="text-transform: uppercase; font-size: 8.5pt; letter-spacing: 0.5px; display: block; margin-bottom: 3px;">Interviewer Rationale</strong>
                ${q.rationale_for_asking}
              </div>
            ` : ""}

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 10px;">
              <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #16a34a; padding: 12px 14px; border-radius: 6px; font-size: 9.5pt;">
                <span style="color: #15803d; font-weight: 700; font-size: 9pt; text-transform: uppercase; letter-spacing: 0.4px; display: block; margin-bottom: 6px;">&check; Expected Answer (What Good Looks Like)</span>
                ${expectedText ? `<p style="margin: 0 0 6px 0; color: #14532d; line-height: 1.45;">${expectedText}</p>` : ""}
                ${signals.length > 0 ? `
                  <div style="margin-top: 8px; border-top: 1px solid #dcfce7; padding-top: 6px;">
                    <span style="font-size: 8pt; font-weight: 700; text-transform: uppercase; color: #166534; display: block; margin-bottom: 4px;">Key Mastery Signals:</span>
                    <ul style="margin: 0; padding-left: 16px; color: #166534; font-size: 9pt;">
                      ${signals.map((s) => `<li style="margin-bottom: 2px;">${s}</li>`).join("")}
                    </ul>
                  </div>
                ` : ""}
              </div>

              <div style="background: #fff1f2; border: 1px solid #fecdd3; border-left: 4px solid #e11d48; padding: 12px 14px; border-radius: 6px; font-size: 9.5pt;">
                <span style="color: #be123c; font-weight: 700; font-size: 9pt; text-transform: uppercase; letter-spacing: 0.4px; display: block; margin-bottom: 6px;">&cross; Bad Answer (Warning Signs &amp; Red Flags)</span>
                ${badText ? `<p style="margin: 0 0 6px 0; color: #881337; line-height: 1.45;">${badText}</p>` : ""}
                ${redFlags.length > 0 ? `
                  <div style="margin-top: 8px; border-top: 1px solid #ffe4e6; padding-top: 6px;">
                    <span style="font-size: 8pt; font-weight: 700; text-transform: uppercase; color: #9f1239; display: block; margin-bottom: 4px;">Red Flag Indicators:</span>
                    <ul style="margin: 0; padding-left: 16px; color: #9f1239; font-size: 9pt;">
                      ${redFlags.map((r) => `<li style="margin-bottom: 2px;">${r}</li>`).join("")}
                    </ul>
                  </div>
                ` : ""}
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>Interview Guide - ${candName} - ${jobTitle}</title>
          <style>
            @page { margin: 15mm; size: A4; }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; color: #0f172a; line-height: 1.5; font-size: 11pt; padding: 20px; margin: 0; background: #ffffff; }
            h1 { margin: 0 0 6px 0; font-size: 20pt; color: #0f172a; font-weight: 800; }
            .header-strip { border-bottom: 2px solid #0f172a; padding-bottom: 14px; margin-bottom: 20px; }
            .meta-tags { display: flex; flex-wrap: wrap; gap: 16px; font-size: 10pt; color: #475569; }
            .briefing-box { background: #eff6ff; border-left: 4px solid #2563eb; padding: 14px 18px; border-radius: 6px; margin-bottom: 24px; }
            .briefing-title { font-weight: 800; font-size: 10.5pt; text-transform: uppercase; color: #1e40af; margin-bottom: 6px; letter-spacing: 0.5px; }
            .briefing-content { font-size: 10.5pt; color: #1e293b; margin: 0; line-height: 1.5; }
            @media print {
              body { padding: 0; }
            }
          </style>
        </head>
        <body>
          <div class="header-strip">
            <h1>Tailored Interview Dossier</h1>
            <div class="meta-tags">
              <span><strong>Candidate:</strong> ${candName}</span>
              <span><strong>Job Requisition:</strong> ${jobTitle}</span>
              <span><strong>Total Allocated:</strong> ${durationMins} minutes</span>
              <span><strong>Questions:</strong> ${interviewPlan.questions.length} items</span>
              <span><strong>Date:</strong> ${new Date().toLocaleDateString()}</span>
            </div>
          </div>
          ${summary ? `
            <div class="briefing-box">
              <div class="briefing-title">Interviewer Executive Briefing</div>
              <p class="briefing-content">${summary}</p>
            </div>
          ` : ""}
          <div style="margin-top: 16px;">
            ${questionsHtml}
          </div>
        </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
      printWindow.print();
      printWindow.close();
    }, 250);
  };

  const handleCopyMarkdown = () => {
    if (!interviewPlan) return;
    const durationMins = interviewPlan.total_duration_minutes || interviewPlan.total_estimated_minutes || duration;
    const summary = interviewPlan.executive_summary || interviewPlan.interview_focus_summary || "";
    const text = `# Tailored Interview Guide
Candidate: ${activeCandidate?.masked_name || activeCandidateId}
Requisition: ${activeJob?.title}
Duration: ${durationMins} minutes

## Executive Summary
${summary}

## Tailored Questions
${interviewPlan.questions
  .map(
    (q, i) => {
      const qDuration = q.target_duration_minutes || q.estimated_minutes || 10;
      const expectedText = q.expected_answer || q.expected_answer_rubric || "";
      const badText = q.bad_answer || "";
      const signals = (q.expected_answers?.length ? q.expected_answers : q.expected_positive_signals || []);
      const redFlags = (q.bad_answers?.length ? q.bad_answers : q.red_flags || []);

      return `### Question ${i + 1}: ${q.question_text}
- Requirement: ${q.target_requirement_id}
- Difficulty: ${q.difficulty || "mid"} (${qDuration}m)
- Rationale: ${q.rationale_for_asking || "Probe candidate competency"}
- Expected Answer:
  ${expectedText}${signals.length > 0 ? `\n  Key Mastery Signals:\n${signals.map((s) => `  * ${s}`).join("\n")}` : ""}
- Bad Answer:
  ${badText}${redFlags.length > 0 ? `\n  Red Flag Indicators:\n${redFlags.map((r) => `  * ${r}`).join("\n")}` : ""}
`;
    }
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
    <div className="space-y-6 max-w-7xl 2xl:max-w-[1700px] mx-auto">
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
                <span>Tailored Interview Studio</span>
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
                onClick={handlePrintDossier}
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
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-xs font-semibold text-slate-300">Target Duration:</span>
              <div className="flex rounded-xl bg-slate-950 p-1 border border-slate-800 text-xs">
                {[
                  { mins: 30, label: "30m" },
                  { mins: 45, label: "45m" },
                  { mins: 60, label: "60m" },
                ].map((item) => (
                  <button
                    key={item.mins}
                    type="button"
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

              {/* Custom Duration Stepper */}
              <div className="flex items-center rounded-xl bg-slate-950 border border-slate-800 p-0.5 focus-within:border-blue-500/80 transition-all shadow-inner">
                <button
                  type="button"
                  title="Decrease duration by 5m"
                  onClick={() => setDuration((prev) => Math.max(5, (prev || 45) - 5))}
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-slate-800/80 active:scale-95 transition-all cursor-pointer"
                >
                  <Minus className="w-3.5 h-3.5" />
                </button>
                <div className="flex items-center px-1.5 gap-1">
                  <Clock className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                  <input
                    type="number"
                    min={5}
                    max={240}
                    step={5}
                    value={duration || ""}
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10);
                      if (!isNaN(val)) {
                        setDuration(val);
                      } else {
                        setDuration(0);
                      }
                    }}
                    onBlur={() => {
                      if (!duration || duration < 5) setDuration(15);
                      else if (duration > 240) setDuration(240);
                    }}
                    placeholder="45"
                    className="w-9 bg-transparent text-xs font-bold text-white text-center focus:outline-none font-mono [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                  <span className="text-[11px] font-medium text-slate-400">m</span>
                </div>
                <button
                  type="button"
                  title="Increase duration by 5m"
                  onClick={() => setDuration((prev) => Math.min(240, (prev || 45) + 5))}
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-slate-800/80 active:scale-95 transition-all cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
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
              <span>{interviewPlan ? "Regenerate Questions" : "Synthesize Tailored Guide"}</span>
            </button>
          </div>

          {/* Generated Plan Display */}
          {loading ? (
            <LiveProcessTimer
              timer={interviewTimer}
              title="Synthesizing Interview Plan"
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
                  {interviewPlan.executive_summary || interviewPlan.interview_focus_summary}
                </p>
              </div>

              {/* Questions List */}
              <div className="space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div className="flex items-center gap-3">
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                      <span>Tailored Questions</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-normal">
                        {interviewPlan.questions.length} Items • {interviewPlan.total_duration_minutes || interviewPlan.total_estimated_minutes || duration}m Total
                      </span>
                    </h2>
                    {lastInterviewDuration !== null && (
                      <DurationBadge duration={lastInterviewDuration} label="Synthesized in" />
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={handleToggleAllAnswers}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900/80 hover:bg-slate-800 hover:text-white text-slate-300 text-xs font-medium transition-all cursor-pointer shadow-sm"
                  >
                    {collapsedQuestions.size === interviewPlan.questions.length ? (
                      <>
                        <ChevronDown className="w-3.5 h-3.5 text-blue-400" />
                        <span>Expand All Answers</span>
                      </>
                    ) : (
                      <>
                        <ChevronUp className="w-3.5 h-3.5 text-blue-400" />
                        <span>Collapse All Answers</span>
                      </>
                    )}
                  </button>
                </div>

                <div className="space-y-5">
                  {interviewPlan.questions.map((q, idx) => {
                    const expectedSignals = (q.expected_answers && q.expected_answers.length > 0)
                      ? q.expected_answers
                      : (q.expected_positive_signals || []);
                    const badSignals = (q.bad_answers && q.bad_answers.length > 0)
                      ? q.bad_answers
                      : (q.red_flags || []);
                    const qDuration = q.target_duration_minutes || q.estimated_minutes || 10;
                    const expectedMain = q.expected_answer || q.expected_answer_rubric;
                    const isAnswersCollapsed = collapsedQuestions.has(idx);

                    return (
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
                              {q.difficulty || "mid"}
                            </span>
                            <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-slate-800 text-xs font-medium text-slate-400">
                              <Clock className="w-3.5 h-3.5" />
                              {qDuration}m
                            </span>
                            <button
                              type="button"
                              onClick={() => toggleQuestionCollapse(idx)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-xs font-medium text-slate-300 hover:text-white border border-slate-700/60 transition-all cursor-pointer"
                              title={isAnswersCollapsed ? "Expand expected & bad answers" : "Collapse expected & bad answers"}
                            >
                              {isAnswersCollapsed ? (
                                <>
                                  <span>Answers</span>
                                  <ChevronDown className="w-3.5 h-3.5 text-blue-400" />
                                </>
                              ) : (
                                <>
                                  <span>Answers</span>
                                  <ChevronUp className="w-3.5 h-3.5 text-blue-400" />
                                </>
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Rationale Pill */}
                        {q.rationale_for_asking && (
                          <div className="p-3.5 rounded-xl bg-slate-950/80 border border-amber-500/20 space-y-1">
                            <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
                              <Target className="w-3.5 h-3.5 text-amber-400" />
                              <span>Interviewer Rationale (Candidate Gap Probe)</span>
                            </div>
                            <p className="text-xs text-slate-200 leading-relaxed font-sans">
                              {q.rationale_for_asking}
                            </p>
                          </div>
                        )}

                        {/* 2-Column Comparison: Expected Answers vs Bad Answers */}
                        {!isAnswersCollapsed ? (
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5 pt-1 animate-in fade-in duration-200">
                            {/* Expected Answer (Good Response) */}
                            <div className="p-4 rounded-xl bg-slate-950/90 border-l-2 border-emerald-400 border-r border-t border-b border-slate-800/80 space-y-2.5">
                              <div className="text-xs font-bold uppercase tracking-wider text-emerald-300 flex items-center gap-1.5">
                                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                                <span>Expected Answer (What Good Looks Like)</span>
                              </div>
                              {expectedMain && (
                                <p className="text-xs text-emerald-100/90 leading-relaxed font-sans whitespace-pre-line">
                                  {expectedMain}
                                </p>
                              )}
                              {expectedSignals.length > 0 && (
                                <div className="pt-2 border-t border-emerald-500/20 space-y-1.5">
                                  <span className="text-[10px] uppercase font-semibold text-emerald-400/80 tracking-wider block">
                                    Key Mastery Signals
                                  </span>
                                  <ul className="space-y-1 text-xs text-emerald-200/90">
                                    {expectedSignals.map((sig, sIdx) => (
                                      <li key={sIdx} className="flex items-start gap-1.5">
                                        <span className="text-emerald-400 font-bold shrink-0">•</span>
                                        <span>{sig}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>

                            {/* Bad Answer / Red Flags (Poor Response) */}
                            <div className="p-4 rounded-xl bg-slate-950/90 border-l-2 border-rose-400 border-r border-t border-b border-slate-800/80 space-y-2.5">
                              <div className="text-xs font-bold uppercase tracking-wider text-rose-300 flex items-center gap-1.5">
                                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                                <span>Bad Answer (Warning Signs & Red Flags)</span>
                              </div>
                              {q.bad_answer && (
                                <p className="text-xs text-rose-100/90 leading-relaxed font-sans whitespace-pre-line">
                                  {q.bad_answer}
                                </p>
                              )}
                              {badSignals.length > 0 && (
                                <div className="pt-2 border-t border-rose-500/20 space-y-1.5">
                                  <span className="text-[10px] uppercase font-semibold text-rose-400/80 tracking-wider block">
                                    Red Flag Indicators
                                  </span>
                                  <ul className="space-y-1 text-xs text-rose-200/90">
                                    {badSignals.map((rf, rIdx) => (
                                      <li key={rIdx} className="flex items-start gap-1.5">
                                        <span className="text-rose-400 font-bold shrink-0">•</span>
                                        <span>{rf}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {!q.bad_answer && badSignals.length === 0 && (
                                <p className="text-xs text-slate-500 italic">No specific red flags flagged for this question.</p>
                              )}
                            </div>
                          </div>
                        ) : (
                          <div
                            onClick={() => toggleQuestionCollapse(idx)}
                            className="p-2.5 rounded-xl bg-slate-950/50 border border-slate-800/80 flex items-center justify-between text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-950/80 cursor-pointer transition-all"
                          >
                            <span className="flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full bg-blue-500/80 inline-block"></span>
                              <span>Expected &amp; bad answers are collapsed</span>
                            </span>
                            <span className="text-[11px] text-blue-400 font-medium flex items-center gap-1">
                              Show answers <ChevronDown className="w-3.5 h-3.5" />
                            </span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center rounded-2xl border border-slate-800 bg-slate-900/30 text-slate-400 text-sm space-y-2">
              <Sparkles className="w-8 h-8 text-blue-400 mx-auto" />
              <div className="font-semibold text-slate-200">Ready to Synthesize Interview Guide</div>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Click &ldquo;Synthesize Tailored Guide&rdquo; to prompt the agent to formulate personalized questions probed from candidate citations and gaps.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
