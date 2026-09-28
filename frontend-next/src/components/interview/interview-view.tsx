"use client";

import { useState, useEffect } from "react";
import { InterviewPlan, JobDescription } from "@/types";
import { api } from "@/lib/api";
import {
  Clock,
  Copy,
  FileDown,
  HelpCircle,
  Lightbulb,
  Loader2,
  MessageSquareCode,
  Printer,
  Sparkles,
  Target,
} from "lucide-react";

interface InterviewViewProps {
  candidateId: string | null;
  selectedJobId: string | null;
  jobs: JobDescription[];
  onBackToPipeline: () => void;
}

export function InterviewView({
  candidateId,
  selectedJobId,
  jobs,
  onBackToPipeline,
}: InterviewViewProps) {
  const [interviewPlan, setInterviewPlan] = useState<InterviewPlan | null>(null);
  const [duration, setDuration] = useState<number>(45);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const activeJob = jobs.find((j) => j.id === selectedJobId) || jobs[0];

  const handleGenerate = async () => {
    if (!candidateId || !activeJob) return;

    try {
      setLoading(true);
      // Fetch evaluation id first or generate with dummy evaluation id
      const evals = await api.getJobEvaluations(activeJob.id);
      const matchedEval = evals.find((e) => e.candidate_id === candidateId);
      const evalId = matchedEval?.id || "00000000-0000-0000-0000-000000000000";

      const plan = await api.generateInterviewPlan(
        candidateId,
        evalId,
        activeJob,
        duration
      );
      setInterviewPlan(plan);
    } catch (err: any) {
      alert(`Interview guide synthesis failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleCopyMarkdown = () => {
    if (!interviewPlan) return;
    const text = `# Tailored Interview Guide
Candidate: ${candidateId}
Target Duration: ${interviewPlan.total_duration_minutes} minutes

## Executive Summary
${interviewPlan.executive_summary}

## Interview Questions
${interviewPlan.questions
  .map(
    (q, i) => `### Question ${i + 1}: ${q.question_text}
- Requirement: ${q.target_requirement_id}
- Difficulty: ${q.difficulty} (${q.target_duration_minutes}m)
- Rationale: ${q.rationale_for_asking}
- Expected Answer Rubric: ${q.expected_answer_rubric}
`
  )
  .join("\n")}
`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!candidateId) {
    return (
      <div className="p-12 text-center text-slate-500 text-xs">
        Select a candidate from the Candidate Pipeline to generate a role-tailored STAR interview guide.
      </div>
    );
  }

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
            Tailored STAR Interview Studio
          </h1>
          <p className="text-xs text-slate-400">
            Synthesize role-specific technical & behavioral interview questions grounded in candidate gaps and claims.
          </p>
        </div>

        {interviewPlan && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyMarkdown}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-colors"
            >
              <Copy className="w-3.5 h-3.5" />
              <span>{copied ? "Copied Markdown!" : "Copy Plan"}</span>
            </button>
            <button
              onClick={handlePrint}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-colors"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print Dossier</span>
            </button>
          </div>
        )}
      </div>

      {/* Synthesis Controls */}
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <span className="text-xs font-medium text-slate-300">Target Duration:</span>
          <div className="flex rounded-lg bg-slate-950 p-0.5 border border-slate-800 text-xs">
            {[30, 45, 60].map((mins) => (
              <button
                key={mins}
                onClick={() => setDuration(mins)}
                className={`px-3 py-1 rounded-md transition-colors ${
                  duration === mins
                    ? "bg-slate-800 text-white font-semibold"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {mins} mins
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={handleGenerate}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-all disabled:opacity-50 cursor-pointer"
        >
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Sparkles className="w-3.5 h-3.5" />
          )}
          <span>{interviewPlan ? "Regenerate Plan" : "Synthesize Tailored Plan"}</span>
        </button>
      </div>

      {/* Interview Dossier Display */}
      {interviewPlan ? (
        <div className="space-y-6">
          {/* Executive Summary Card */}
          <div className="p-5 rounded-xl border border-blue-500/20 bg-blue-950/20 space-y-2">
            <div className="text-xs font-bold uppercase tracking-wider text-blue-400 flex items-center gap-1.5">
              <Lightbulb className="w-4 h-4" />
              <span>Interviewer Executive Briefing</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              {interviewPlan.executive_summary}
            </p>
          </div>

          {/* Question Sequence */}
          <div className="space-y-4">
            <h2 className="text-sm font-bold text-white flex items-center justify-between">
              <span>Tailored STAR Questions ({interviewPlan.questions.length})</span>
              <span className="text-xs text-slate-400 font-mono">
                Total Allocated: {interviewPlan.total_duration_minutes}m
              </span>
            </h2>

            <div className="space-y-3">
              {interviewPlan.questions.map((q, idx) => (
                <div
                  key={idx}
                  className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-3 hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-full bg-blue-600/20 text-blue-400 font-bold text-xs flex items-center justify-center shrink-0">
                        {idx + 1}
                      </span>
                      <span className="font-semibold text-sm text-white">
                        {q.question_text}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-[10px] font-mono text-slate-300 uppercase">
                        {q.difficulty}
                      </span>
                      <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-[10px] font-mono text-slate-400">
                        <Clock className="w-3 h-3" />
                        {q.target_duration_minutes}m
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 text-xs">
                    {/* Rationale */}
                    <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 space-y-1">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                        <Target className="w-3 h-3 text-purple-400" />
                        <span>Why We Ask This</span>
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed">
                        {q.rationale_for_asking}
                      </p>
                    </div>

                    {/* Expected Answer Rubric */}
                    <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 space-y-1">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                        <HelpCircle className="w-3 h-3 text-emerald-400" />
                        <span>Evaluation Rubric (Good Answer)</span>
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed">
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
        <div className="p-12 text-center rounded-xl border border-slate-800 bg-slate-900/30 text-slate-500 text-xs">
          Click &ldquo;Synthesize Tailored Plan&rdquo; to prompt the agent to craft personalized interview questions.
        </div>
      )}
    </div>
  );
}
