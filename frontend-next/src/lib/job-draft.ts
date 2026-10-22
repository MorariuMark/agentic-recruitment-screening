import type { JobDescription } from "@/types";

export interface JobDraftIssue { field: string; message: string; }

export function validateJobDraft(job: JobDescription, forScreening = false): JobDraftIssue[] {
  const issues: JobDraftIssue[] = [];
  if (!job.title.trim()) issues.push({field: "title", message: "Enter a job title."});
  const ids = new Set<string>();
  job.requirements.forEach((requirement, index) => {
    const prefix = `criterion-${index}`;
    const label = `Criterion ${index + 1}`;
    if (!requirement.title.trim()) issues.push({field: `${prefix}-title`, message: `${label}: enter a title.`});
    if (!requirement.id || ids.has(requirement.id)) issues.push({field: `${prefix}-title`, message: `${label}: identifiers must be unique. Re-extract or replace this criterion.`});
    ids.add(requirement.id);
    if (!Number.isFinite(requirement.weight) || requirement.weight < 0 || requirement.weight > 10) issues.push({field: `${prefix}-weight`, message: `${label}: weight must be between 0 and 10.`});
    const years = requirement.minimum_years_experience;
    if (years != null && (!Number.isInteger(years) || years < 0 || years > 60)) issues.push({field: `${prefix}-years`, message: `${label}: minimum years must be a whole number between 0 and 60, or left blank.`});
  });
  if (forScreening && !job.requirements.some(requirement => requirement.weight > 0)) issues.push({field: "criteria", message: "Add at least one active criterion before continuing to CVs."});
  return issues;
}
