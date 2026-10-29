"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, FileText, MessagesSquare, Zap } from "lucide-react";
import { CandidateSummary, InterviewPlan, ScreeningRun } from "@/types";
import { api } from "@/lib/api";
import { candidateName, Empty, message } from "./common";
import { ProfileDialog } from "./profile";
import { RequirementEvidence } from "./requirement-evidence";
import { ParsedProfile } from "./parsed-profile";
import { ProcessIndicator, useTimedActivity } from "./process-indicator";

interface Props {run: ScreeningRun | null; candidates: CandidateSummary[]; onBack: () => void;}
export function Review({run, candidates, onRun, onInterview, onBack}: Props & {onRun: (run: ScreeningRun) => void; onInterview: () => void}) {
  const [selectedIds, setVisibleIds] = useState<string[] | null>(null);
  const visibleIds = selectedIds ?? run?.shortlist_ids.slice(0,3) ?? [];
  const [notes, setNotes] = useState<Record<string,string>>(Object.fromEntries(Object.entries(run?.decisions || {}).map(([id, d]) => [id, d.notes])));
  const [decisions, setDecisions] = useState<Record<string,string>>(Object.fromEntries(Object.entries(run?.decisions || {}).map(([id, d]) => [id, d.decision])));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [profileId, setProfileId] = useState("");
  const [focusedQuote, setFocusedQuote] = useState("");
  const [notice, setNotice] = useState("");
  const savedDecisions = useRef(run?.decisions || {});
  useEffect(() => {
    const previous = savedDecisions.current;
    const next = run?.decisions || {};
    const ids = new Set([...Object.keys(previous), ...Object.keys(next)]);
    setNotes(current => {
      const merged = {...current};
      for (const id of ids) if (current[id] === undefined || current[id] === (previous[id]?.notes || "")) merged[id] = next[id]?.notes || "";
      return merged;
    });
    setDecisions(current => {
      const merged = {...current};
      for (const id of ids) if (current[id] === undefined || current[id] === (previous[id]?.decision || "")) merged[id] = next[id]?.decision || "";
      return merged;
    });
    savedDecisions.current = next;
  }, [run?.decisions]);

  const runTotalSeconds = useMemo(() => {
    if (!run) return null;
    if (run.diagnostics?.timings_ms) {
      const sum = Object.values(run.diagnostics.timings_ms).reduce((a, b) => a + b, 0);
      if (sum > 0) return sum / 1000;
    }
    if (run.ended_at && run.started_at) {
      const diff = typeof run.ended_at === "number" && typeof run.started_at === "number"
        ? (run.ended_at > 1e11 ? (run.ended_at - run.started_at) / 1000 : run.ended_at - run.started_at)
        : null;
      if (diff && diff > 0) return diff;
    }
    return null;
  }, [run]);

  if (!run?.shortlist_ids.length) return <section className="r-panel"><Empty title="Build your comparison shortlist">Rank a cohort, then send the top candidates here for review.</Empty><div className="r-empty-action"><button className="r-button" onClick={onBack}><ArrowLeft size={16}/>Back to cohort</button></div></section>;
  const shortlisted = run.rows.filter(row => run.shortlist_ids.includes(row.candidate_id));
  const visible = shortlisted.filter(row => visibleIds.includes(row.candidate_id));
  const approved = run.shortlist_ids.filter(id => run.decisions[id]?.decision === "interview").length;

  return <><div className="r-review-intro"><div><h2>{shortlisted.length} candidates. One considered shortlist.</h2><p>Select up to 4 candidates to compare. Review their CV evidence before recording your decision.</p></div><div style={{ display: "flex", alignItems: "center", gap: 10 }}>{runTotalSeconds != null && <span className="r-duration-badge success"><Zap size={13}/>Screening completed in {runTotalSeconds.toFixed(1)}s</span>}<span className="r-pill">Human review</span></div></div>
    <div className="r-candidate-picker" aria-label="Candidates to compare">{shortlisted.map(row => <button key={row.candidate_id} aria-pressed={visibleIds.includes(row.candidate_id)} disabled={!visibleIds.includes(row.candidate_id) && visibleIds.length >= 4} className={visibleIds.includes(row.candidate_id) ? "selected" : ""} onClick={() => setVisibleIds(visibleIds.includes(row.candidate_id) ? visibleIds.filter(id => id !== row.candidate_id) : [...visibleIds, row.candidate_id])}><span>#{row.rank}</span>{candidateName(row.candidate_id, candidates)}{run.decisions[row.candidate_id]?.decision === "interview" && <Check size={14}/>}</button>)}</div>
    {error && <div className="r-alert" role="alert">{error}</div>}{notice && <p className="r-success" role="status">{notice}</p>}
    {!visible.length ? <Empty title="Choose candidates to compare">Select a candidate above to open the comparison matrix.</Empty> : <section className="r-panel r-matrix-scroll"><table className="r-matrix"><thead><tr><th>Review criteria<small>Evidence against this role</small></th>{visible.map(row => <th key={row.candidate_id}><span className="r-muted">Rank {row.rank}</span><h3>{candidateName(row.candidate_id, candidates)}</h3><button type="button" className="r-button subtle" onClick={() => { setProfileId(row.candidate_id); setFocusedQuote(""); }}><FileText size={15}/>Read CV</button></th>)}</tr></thead><tbody>
      <tr className="r-decision-row r-decision-top"><th>Your decision<small>Review & record decision upfront</small></th>{visible.map(row => <td key={row.candidate_id}><label className="r-field">Recruiter decision<select value={decisions[row.candidate_id] || ""} onChange={e => setDecisions({...decisions, [row.candidate_id]: e.target.value})}><option value="" disabled>Choose a decision</option><option value="interview">Advance to interview</option><option value="hold">Hold for review</option><option value="reject">Do not progress</option></select></label><label className="r-field">Review notes<textarea rows={2} maxLength={5000} placeholder="Record your reasoning or questions to follow up." value={notes[row.candidate_id] || ""} onChange={e => setNotes({...notes, [row.candidate_id]: e.target.value})}/></label><button className="r-button primary" disabled={!!busy || !decisions[row.candidate_id]} onClick={async () => {setBusy(row.candidate_id); setError(""); setNotice(""); try {onRun(await api.reviewCandidate(run.id, row.candidate_id, decisions[row.candidate_id] as "interview" | "hold" | "reject", notes[row.candidate_id] || "")); setNotice(`Decision saved for ${candidateName(row.candidate_id, candidates)}.`);} catch(e) {setError(message(e));} finally {setBusy("");}}}>{busy === row.candidate_id ? "Saving…" : "Save decision"}</button>{run.decisions[row.candidate_id] && <small className="r-saved-decision"><Check size={13}/>Saved: {run.decisions[row.candidate_id].decision === "interview" ? "Advance to interview" : run.decisions[row.candidate_id].decision === "hold" ? "Hold for review" : "Do not progress"}</small>}</td>)}</tr>
      <tr><th>Pre-screen score</th>{visible.map(row => {const preClass = row.pre_screen_score >= 75 ? "r-score-high" : row.pre_screen_score < 50 ? "r-score-low" : ""; return <td key={row.candidate_id}><span className={`r-score ${preClass}`}>{row.pre_screen_score.toFixed(1)}<small>/100</small></span></td>;})}</tr>
      <tr><th>Deep evaluation</th>{visible.map(row => {const score = row.deep_evaluation?.overall_score; let rec = row.deep_evaluation?.recommendation; let recClass = "alert-pill"; if (score != null) { if (score >= 75) { rec = "strong_match"; recClass = "success"; } else if (score < 50) { rec = "reject"; recClass = "alert-pill"; } else { rec = "borderline"; recClass = "warning"; } } else if (rec) { recClass = rec === "strong_match" ? "success" : rec === "borderline" ? "warning" : "alert-pill"; } return <td key={row.candidate_id}><div className="r-matrix-score-box"><span className="r-score">{row.deep_evaluation?.overall_score.toFixed(1) ?? "Unavailable"}<small>/100</small></span>{rec && <span className={`r-pill ${recClass}`}>{rec === "strong_match" ? "Match" : rec === "borderline" ? "Borderline" : "Reject"}</span>}</div><small className="r-muted">{row.deep_evaluation?.must_have_gaps_count ?? 0} required criteria gaps</small>{!!row.deep_evaluation?.clarification_count && <p className="r-muted">Needs confirmation: {row.deep_evaluation.requirement_matches.filter(match => match.status === "clarification_needed").map(match => match.title || match.requirement_id).join(", ")}. A clarification keeps the automated recommendation borderline; your saved decision controls progression.</p>}</td>;})}</tr>
      <tr><th>Skills & experience</th>{visible.map(row => {const candidate = candidates.find(c => c.id === row.candidate_id); return <td key={row.candidate_id}><div className="r-tags">{candidate?.skills.slice(0,6).map((skill,i) => <span key={i}>{skill}</span>)}</div><p>{candidate?.total_years_experience != null ? `${candidate.total_years_experience.toFixed(1)} years documented` : "Experience duration not stated"}</p></td>;})}</tr>
      {visible.some(row => row.requirement_assessments?.length) && <tr><th>Pre-screen evidence<small>Unknown needs clarification.</small></th>{visible.map(row => <td key={row.candidate_id}>{row.requirement_assessments?.length ? <details><summary>Requirement evidence</summary><RequirementEvidence assessments={row.requirement_assessments}/></details> : <span className="r-muted">Legacy screening</span>}</td>)}</tr>}
      <tr><th>CV profile<small>Open profiles for a side-by-side review.</small></th>{visible.map(row => <td key={row.candidate_id}><ComparisonProfile candidateId={row.candidate_id}/></td>)}</tr>
      {run.job.requirements.map(requirement => <tr key={requirement.id}><th>{requirement.title}<small>{requirement.category === "must_have" ? "Required" : "Preferred"} · Weight {requirement.weight}</small></th>{visible.map(row => {const match = row.deep_evaluation?.requirement_matches.find(m => m.requirement_id === requirement.id); const statusClass = match?.status === "met" ? "success" : match?.status === "clarification_needed" ? "warning" : "alert-pill"; return <td key={row.candidate_id}>{match ? <><span className={`r-pill ${statusClass}`}>{match.status.replaceAll("_", " ")}</span><p>{match.reasoning}</p>{match.citations.length > 0 && <details className="r-evidence-citations"><summary>CV evidence ({match.citations.length})</summary>{match.citations.map((citation,i) => <blockquote key={i} className="r-clickable-quote" tabIndex={0} role="button" title="Click to view and highlight quote in CV text" onClick={() => { setProfileId(row.candidate_id); setFocusedQuote(citation.quote); }} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { setProfileId(row.candidate_id); setFocusedQuote(citation.quote); } }}><span className="r-quote-text">“{citation.quote}”</span><small className="r-quote-badge">{citation.verified ? "✓ Verified quote" : "⚠ Needs verification"} · View in CV</small></blockquote>)}</details>}{match.clarification_question && <small>Clarify: {match.clarification_question}</small>}</> : <span className="r-muted">No evaluation for this criterion</span>}</td>;})}</tr>)}
    </tbody></table></section>}
    <div className="r-next-step"><div><h3>{approved} {approved === 1 ? "candidate" : "candidates"} approved for interview</h3><p>Saved decisions carry forward to interview preparation.</p></div><button className="r-button primary" disabled={!approved || !!busy} onClick={onInterview}>Prepare interviews<ArrowRight size={16}/></button></div>
    {profileId && <ProfileDialog id={profileId} row={run.rows.find(r => r.candidate_id === profileId)} initialQuote={focusedQuote} onClose={() => { setProfileId(""); setFocusedQuote(""); }}/>}
  </>;
}

export function Interviews({run, candidates, onBack}: Props) {
  const cache = useQueryClient();
  const approved = run?.rows.filter(r => run.shortlist_ids.includes(r.candidate_id) && run.decisions[r.candidate_id]?.decision === "interview") || [];
  const [selected, setSelected] = useState("");
  const [duration, setDuration] = useState(45);
  const [plans, setPlans] = useState<Record<string, InterviewPlan>>(run?.interviews || {});
  const [genDurations, setGenDurations] = useState<Record<string, number>>({});
  const [busy, setBusy, startedAt] = useTimedActivity<boolean>(false);
  useEffect(() => {if (!busy) setPlans(run?.interviews || {});}, [run?.interviews, busy]);
  const [error, setError] = useState("");
  const candidateId = approved.some(r => r.candidate_id === selected) ? selected : approved[0]?.candidate_id || "";
  const plan = plans[candidateId];
  if (!approved.length) return <section className="r-panel"><Empty title="Your interview list is waiting">Approve candidates in the comparison matrix to prepare their interview questions.</Empty><div className="r-empty-action"><button className="r-button" onClick={onBack}><ArrowLeft size={16}/>Review candidates</button></div></section>;
  return <div className="r-interview-layout"><aside className="r-panel r-interview-list"><div className="r-panel-heading"><div><h2>Ready for interview</h2><p>{approved.length} approved candidates</p></div></div>{approved.map(row => <button key={row.candidate_id} className={candidateId === row.candidate_id ? "selected" : ""} disabled={busy} onClick={() => setSelected(row.candidate_id)}><span className="r-avatar">{row.rank}</span><div><strong>{candidateName(row.candidate_id, candidates)}</strong><small><Check size={12}/>Recruiter approved</small></div></button>)}</aside>
    <section className="r-panel r-interview-plan" aria-busy={busy}><div className="r-panel-heading"><div><span className="r-muted">Interview preparation</span><h2>{candidateName(candidateId, candidates)}</h2><p>Questions grounded in the role, evidence and gaps.</p></div>{busy ? <ProcessIndicator active timer={false} label="Preparing interview questions"/> : <MessagesSquare size={24}/>}</div><div className="r-interview-controls"><label className="r-field">Interview duration<select disabled={busy} value={duration} onChange={e => setDuration(Number(e.target.value))}><option value={30}>30 minutes</option><option value={45}>45 minutes</option><option value={60}>60 minutes</option><option value={90}>90 minutes</option></select></label><button className="r-button primary" disabled={busy} onClick={async () => {setBusy(true); setError(""); const startTime = Date.now(); try {const result = await api.recruiterInterview(run!.id, candidateId, duration); setPlans(p => ({...p, [candidateId]: result})); setGenDurations(d => ({...d, [candidateId]: Math.round((Date.now() - startTime) / 100) / 10})); cache.setQueriesData<ScreeningRun>({queryKey: ["recruiter-run", run!.job_id]}, current => current?.id === run!.id ? {...current, interviews: {...current.interviews, [candidateId]: result}} : current);} catch(e) {setError(message(e));} finally {setBusy(false);}}}><ProcessIndicator active={busy} startedAt={startedAt} label="Preparing interview questions"/>{busy ? "Preparing questions…" : plan ? "Regenerate questions" : "Generate interview questions"}</button></div>
      {run?.decisions[candidateId]?.notes && <div className="r-review-notes"><strong>Your review notes</strong><p>{run.decisions[candidateId].notes}</p></div>}{error && <div className="r-alert" role="alert">{error}</div>}
      {busy && <div className="r-processing-note" role="status">Preparing your question guide. You can switch pages while this continues.</div>}
      {!plan && !busy && <Empty title="Make the conversation count">Generate questions tailored to this candidate’s strengths and the areas you want to explore.</Empty>}
      {plan && !busy && <div className="r-questions"><div className="r-question-summary"><span className="r-pill">{plan.questions.length} questions</span><span className="r-pill">{plan.total_estimated_minutes || duration} minutes</span>{genDurations[candidateId] != null && <span className="r-duration-badge success"><Check size={12}/>Questions generated in {genDurations[candidateId].toFixed(1)}s</span>}</div>
        {(plan.executive_summary || plan.interview_focus_summary) && <p>{plan.executive_summary || plan.interview_focus_summary}</p>}
        {!!plan.interviewer_tips?.length && <details className="r-profile-section"><summary>Interview tips</summary><ul className="r-data-list">{plan.interviewer_tips.map((tip,i) => <li key={i}>{tip}</li>)}</ul></details>}
        {plan.questions.map((q,index) => <article className="r-question" key={q.id || q.question_id || index}><div className="r-question-number">{String(index + 1).padStart(2,"0")}</div><div><div className="r-question-meta">{q.archetype?.replaceAll("_", " ") || "Candidate question"}<span>{q.estimated_minutes || q.target_duration_minutes || "—"} min</span></div><h3>{q.question_text}</h3>{q.rationale_for_asking && <p>{q.rationale_for_asking}</p>}<details><summary>Interviewer guidance</summary>{(q.expected_answer_rubric || q.expected_answer) && <p>{q.expected_answer_rubric || q.expected_answer}</p>}{[...new Set([...(q.expected_positive_signals || []), ...(q.expected_answers || [])])].filter(s => s !== q.expected_answer_rubric && s !== q.expected_answer).map((s,i) => <p key={i}>Look for: {s}</p>)}{[...new Set([...(q.red_flags || []), ...(q.bad_answers || []), ...(q.bad_answer ? [q.bad_answer] : [])])].map((s,i) => <p key={i}>Follow up: {s}</p>)}</details></div></article>)}</div>}
    </section></div>;
}

function ComparisonProfile({candidateId}: {candidateId: string}) {
  const [open, setOpen] = useState(false);
  const profile = useQuery({queryKey: ["recruiter-profile", candidateId], queryFn: () => api.getCandidate(candidateId), enabled: open});
  return <details open={open} onToggle={e => setOpen(e.currentTarget.open)}><summary>Show extracted profile</summary>
    {profile.isPending && <p role="status">Loading profile…</p>}
    {profile.error && <p role="alert">{message(profile.error)}</p>}
    {profile.data?.parsed_cv && <ParsedProfile profile={profile.data.parsed_cv}/>}
  </details>;
}
