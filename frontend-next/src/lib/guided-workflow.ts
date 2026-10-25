import type {ScreeningRun} from "@/types";

export const workflowStages = [
  {id: "library", label: "Import CVs"},
  {id: "jobs", label: "Job description"},
  {id: "verification", label: "Screening"},
  {id: "comparison", label: "Comparison"},
  {id: "interview", label: "Interview"},
] as const;

export function workflowProgress(candidateCount: number, jobReady: boolean, run: ScreeningRun | null) {
  const evaluated = run?.rows.filter(row => row.deep_status === "completed" && row.deep_evaluation) || [];
  const screeningReady = !!run && ["completed", "partial"].includes(run.status) && evaluated.length > 0;
  const approved = run?.shortlist_ids.filter(id => run.decisions[id]?.decision === "interview") || [];
  const complete = [candidateCount > 0, jobReady, screeningReady, approved.length > 0,
    approved.length > 0 && approved.every(id => !!run?.interviews?.[id]?.questions.length)];
  const hints = [
    "Import and parse at least one CV to continue.",
    "Save and select a job with at least one active requirement.",
    "Finish screening with at least one completed deep evaluation.",
    "Save an interview approval for at least one candidate in comparison.",
    "Generate interview questions for each approved candidate.",
  ];
  return {complete, hints, evaluatedCount: evaluated.length};
}
