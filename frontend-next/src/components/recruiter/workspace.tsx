"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BriefcaseBusiness, FileCheck2, Columns3, MessagesSquare, LogOut, ChevronRight, Cpu, Menu, X, PanelLeftClose, PanelLeftOpen, ChartNoAxesColumn, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { CandidateSummary, ScreeningRun } from "@/types";
import { StatisticsDialog } from "./statistics";
import { Jobs } from "./jobs";
import { Verification } from "./verification";
import { Review, Interviews } from "./review";
import { message } from "./common";
import { ActivityProvider, ProcessIndicator, useWorkspaceActivity, useResetTimers } from "./process-indicator";

const steps = [
  {id: "jobs", label: "Job descriptions", icon: BriefcaseBusiness, description: "Define what a great match looks like."},
  {id: "verification", label: "CV verification", icon: FileCheck2, description: "Build your cohort. Find your strongest candidates."},
  {id: "comparison", label: "Comparison matrix", icon: Columns3, description: "Review the evidence. Make the next decision."},
  {id: "interview", label: "Interview", icon: MessagesSquare, description: "Turn your shortlist into meaningful conversations."},
] as const;
type Step = typeof steps[number]["id"];

function EngineSelector({compact}: {compact: boolean}) {
  const workspaceActive = useWorkspaceActivity();
  const cache = useQueryClient();
  const settings = useQuery({queryKey: ["recruiter-model"], queryFn: () => api.recruiterModels(), refetchInterval: 60000});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!compact || !open) return;
    const close = (event: MouseEvent) => {if (!root.current?.contains(event.target as Node)) setOpen(false);};
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [compact, open]);
  const data = settings.data;
  const loading = settings.isFetching || !!busy || workspaceActive;
  return <div ref={root} className={`r-engine ${compact ? "compact" : ""}`} onKeyDown={e => {if (e.key === "Escape") setOpen(false);}}>
    {compact && <button className="r-engine-launch" aria-label="Model and failover settings" aria-expanded={open} title="Model and failover settings" onClick={() => setOpen(!open)}>
      {loading ? <ProcessIndicator active timer={false} track={false} label="Model activity"/> : <Cpu size={20}/>}
    </button>}
    <div className={`r-engine-content ${compact ? "r-engine-popover" : ""}`} hidden={compact && !open}>
      <label htmlFor="recruiter-model"><Cpu size={15}/> Evaluation model <ProcessIndicator active={loading} timer={false} track={false} label="Model activity"/></label>
      <select id="recruiter-model" disabled={!!busy || !data} aria-busy={loading} value={data ? `${data.active_provider}|${data.active_model}` : ""} onChange={async event => {
        const [provider, ...modelParts] = event.target.value.split("|"); setBusy("model"); setError("");
        try {const next = await api.selectRecruiterModel(provider, modelParts.join("|")); cache.setQueryData(["recruiter-model"], next);}
        catch (e) {setError(message(e));} finally {setBusy("");}
      }}>
        {!data && <option>{settings.isError ? "Model unavailable" : "Loading model…"}</option>}
        {data && <option value={`${data.active_provider}|${data.active_model}`}>{data.active_model}</option>}
        {Object.entries(data?.providers_catalog || {}).map(([provider, info]) => <optgroup key={provider} label={info.name}>{info.models.filter(m => `${provider}|${m.id}` !== `${data?.active_provider}|${data?.active_model}`).map(model => <option key={model.id} value={`${provider}|${model.id}`}>{model.name}</option>)}</optgroup>)}
      </select>
      <small>{busy === "model" ? "Switching model…" : data ? `Provider: ${data.active_provider}` : "Connect the backend to choose a model"}</small>
      <button type="button" role="switch" aria-label="Automatic failover" aria-checked={data?.fallback_enabled ?? true} disabled={!data || !!busy} className="r-failover-switch" onClick={async () => {
        setBusy("failover"); setError("");
        try {cache.setQueryData(["recruiter-model"], await api.toggleRecruiterFailover(!data!.fallback_enabled));}
        catch (e) {setError(message(e));} finally {setBusy("");}
      }}><span>Failover <span className="r-failover-state">{data?.fallback_enabled ? "On" : "Off"}</span></span><span className={`r-switch-track ${data?.fallback_enabled ? "on" : ""}`} aria-hidden="true"><span/></span></button>
      {(error || settings.isError) && <small role="alert">{error || message(settings.error)}</small>}
    </div>
  </div>;
}

function savedSidebarCollapsed() {
  try {return localStorage.getItem("atos_recruiter_sidebar_collapsed") === "true";} catch {return false;}
}

export function RecruiterWorkspace({onLogout}: {onLogout: () => Promise<void>}) {
  return <ActivityProvider><RecruiterWorkspaceContent onLogout={onLogout}/></ActivityProvider>;
}

function RecruiterWorkspaceContent({onLogout}: {onLogout: () => Promise<void>}) {
  const resetTimers = useResetTimers();
  const [statisticsOpen, setStatisticsOpen] = useState(false);
  const cache = useQueryClient();
  const [step, setStep] = useState<Step>("jobs");
  const [selectedJob, setSelectedJob] = useState("");
  const [visitedJobs, setVisitedJobs] = useState<string[]>([]);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(savedSidebarCollapsed);
  const jobs = useQuery({queryKey: ["recruiter-jobs"], queryFn: () => api.getJobs(1000)});
  const candidates = useQuery({queryKey: ["recruiter-candidates"], queryFn: () => api.getCandidates()});
  const jobId = jobs.data?.some(j => j.id === selectedJob) ? selectedJob : jobs.data?.[0]?.id || "";
  const openedJobs = [...new Set([...visitedJobs, jobId])].filter(id => id && jobs.data?.some(j => j.id === id));
  const runQuery = useQuery({queryKey: ["recruiter-run", jobId], queryFn: () => api.latestScreeningRun(jobId), enabled: !!jobId});
  const run = runQuery.data || null;
  const updateRun = (value: ScreeningRun) => cache.setQueryData(["recruiter-run", value.job_id], value);
  const navigate = (next: Step) => {setStep(next); setMobileOpen(false); window.scrollTo({top: 0, behavior: "instant"});};
  const selectJob = (id: string) => {setVisitedJobs(current => [...new Set([...current, jobId, id])].filter(Boolean)); setSelectedJob(id);};
  const currentStep = steps.find(s => s.id === step)!;
  const approved = run?.shortlist_ids.filter(id => run.decisions[id]?.decision === "interview").length || 0;
  const error = jobs.error || candidates.error || runQuery.error;
  return <div className={`recruiter r-workspace ${collapsed ? "sidebar-collapsed" : ""}`} data-theme="dark">
    {statisticsOpen && <StatisticsDialog onClose={() => setStatisticsOpen(false)}/>}
    <a className="r-skip" href="#recruiter-main">Skip to content</a>
    {mobileOpen && <button aria-label="Close navigation" className="r-nav-scrim" onClick={() => setMobileOpen(false)}/>}
    <aside id="recruiter-sidebar" className={`r-sidebar ${mobileOpen ? "open" : ""}`}>
      <div className="r-brand"><span className="r-brand-mark">a</span><span className="r-brand-name">atos<small>Talent screening</small></span><button className="r-mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={20}/></button></div>
      <button className="r-collapse-sidebar" aria-label={collapsed ? "Expand sidebar" : "Minimize sidebar"} title={collapsed ? "Expand sidebar" : "Minimize sidebar"} aria-controls="recruiter-sidebar" aria-expanded={!collapsed} onClick={() => {const next = !collapsed; setCollapsed(next); try {localStorage.setItem("atos_recruiter_sidebar_collapsed", String(next));} catch { /* Sidebar remains usable without storage. */ }}}>{collapsed ? <PanelLeftOpen size={16}/> : <PanelLeftClose size={16}/>}</button>
      <EngineSelector compact={collapsed && !mobileOpen}/>
      <div className="r-nav-label">Your hiring workflow</div>
      <nav aria-label="Recruiter workflow">{steps.map((item, index) => <button key={item.id} className={`r-nav-item ${step === item.id ? "active" : ""}`} aria-label={`${item.label} ${index + 1}`} title={item.label} aria-current={step === item.id ? "page" : undefined} onClick={() => navigate(item.id)}><item.icon size={19}/><span>{item.label}</span><small>{index + 1}</small></button>)}</nav>
      
      <div className="r-profile"><span className="r-avatar">R</span><div><strong>Recruiter</strong><small>User workspace</small></div><button onClick={onLogout} title="Sign out" aria-label="Sign out"><LogOut size={18}/></button></div>
    </aside>
    <div className="r-main-wrap"><header className="r-topbar"><div>
      <button className="r-mobile-menu" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={20}/></button>
      <span>Workspace</span><ChevronRight size={14}/><strong>{currentStep.label}</strong></div><div className="r-topbar-actions"><button type="button" className="r-reset-timers" onClick={resetTimers} title="Clear completed process durations" aria-label="Reset timers"><RotateCcw size={13}/><span>Reset timers</span></button><button type="button" className="r-statistics-button" aria-haspopup="dialog" onClick={() => setStatisticsOpen(true)}><ChartNoAxesColumn size={16}/>Statistics</button></div></header>
      <main id="recruiter-main" className="r-main"><div className="r-page-heading"><div><h1>{currentStep.label}</h1><p>{currentStep.description}</p></div><span className="r-step-count">Step {steps.findIndex(s => s.id === step) + 1} of 4</span></div>
        {step !== "jobs" && <div className="r-job-context"><label htmlFor="active-role">Hiring for</label><select id="active-role" value={jobId} onChange={e => selectJob(e.target.value)} disabled={!jobs.data?.length}><option value="" disabled>Select a job description</option>{jobs.data?.map(job => <option key={job.id} value={job.id}>{job.title}</option>)}</select><span>{run?.shortlist_ids.length || 0} in comparison <span className="r-dot">/</span> {approved} approved for interview</span></div>}
        {error && <div role="alert" className="r-alert">{message(error)} <button onClick={() => {jobs.refetch(); candidates.refetch(); runQuery.refetch();}}>Retry</button></div>}
        {jobs.isPending || candidates.isPending ? <div className="r-loading" role="status"><ProcessIndicator active timer={false} label="Loading workspace"/>Loading your workspace…</div> : <>
          <div hidden={step !== "jobs"}><Jobs jobs={jobs.data || []} selectedId={jobId} editorIds={openedJobs} onSelect={selectJob} onSaved={async id => {await jobs.refetch(); selectJob(id);}} onContinue={() => navigate("verification")}/></div>
          {openedJobs.map(id => <CandidateWorkspace key={id} jobId={id} visible={id === jobId && step !== "jobs"} step={step} candidates={candidates.data || []} onRun={updateRun} onRefresh={() => candidates.refetch()} onNavigate={navigate}/>)}
          {!jobId && step !== "jobs" && <p className="r-inline-empty">Add a job description to begin screening candidates.</p>}
        </>}
      </main>
    </div>
  </div>;
}

/** Keep each visited job's working views mounted so navigation never discards a request or result. */
function CandidateWorkspace({jobId, visible, step, candidates, onRun, onRefresh, onNavigate}: {
  jobId: string; visible: boolean; step: Step; candidates: CandidateSummary[];
  onRun: (run: ScreeningRun) => void; onRefresh: () => Promise<unknown>; onNavigate: (step: Step) => void;
}) {
  const query = useQuery({queryKey: ["recruiter-run", jobId], queryFn: () => api.latestScreeningRun(jobId),
    refetchInterval: current => ["ranking", "evaluating"].includes(current.state.data?.status || "") ? 2000 : false});
  const run = query.data || null;
  return <div hidden={!visible}>
    <div hidden={step !== "verification"}><Verification jobId={jobId} candidates={candidates} run={run} onRun={onRun} onRefresh={onRefresh} onCompare={() => onNavigate("comparison")}/></div>
    <div hidden={step !== "comparison"}><Review key={run?.id || jobId} run={run} candidates={candidates} onRun={onRun} onInterview={() => onNavigate("interview")} onBack={() => onNavigate("verification")}/></div>
    <div hidden={step !== "interview"}><Interviews key={run?.id || jobId} run={run} candidates={candidates} onBack={() => onNavigate("comparison")}/></div>
  </div>;
}
