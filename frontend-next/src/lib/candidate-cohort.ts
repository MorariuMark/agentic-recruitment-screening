import type { CandidateSummary } from "@/types";

/** Fetch every page; the table's display pagination must not limit screening. */
export async function loadCandidateCohort(getPage: (limit: number, offset: number) => Promise<CandidateSummary[]>) {
  const profiles = new Map<string, CandidateSummary>();
  const pageSize = 500;
  for (let offset = 0; ; offset += pageSize) {
    const page = await getPage(pageSize, offset);
    for (const profile of page) profiles.set(profile.id, profile);
    if (page.length < pageSize) return [...profiles.values()];
  }
}

export function cohortSelection(candidates: {id: string}[], count: number) {
  if (!Number.isInteger(count) || count < 1 || count > candidates.length) return null;
  return candidates.slice(0, count).map(candidate => candidate.id);
}
