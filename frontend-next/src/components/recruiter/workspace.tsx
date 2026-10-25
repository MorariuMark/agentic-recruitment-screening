"use client";



import { useEffect, useRef, useState } from "react";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { BriefcaseBusiness, FileCheck2, Columns3, MessagesSquare, LogOut, ChevronRight, Cpu, Menu, X, PanelLeftClose, PanelLeftOpen, ChartNoAxesColumn, RotateCcw, ScrollText, Terminal, AlertTriangle, Zap } from "lucide-react";
import { LiveLLMDebugModal } from "@/components/layout/live-llm-debug-modal";

import { beginWorkspaceReset, finishWorkspaceReset, clearWorkspaceSession, freshWorkspaceAfter } from "@/lib/workspace-session";

import { setParsingBatch, useParsingBatch } from "@/lib/parsing-batch";

import { clearTrackedProcesses } from "@/lib/processes";

import { api } from "@/lib/api";

import { CandidateSummary, ScreeningRun } from "@/types";

import { workflowProgress, workflowStages } from "@/lib/guided-workflow";
import { WorkflowProgress } from "./workflow-progress";

import { StatisticsDialog } from "./statistics";

import { LogsDialog } from "./logs-dialog";

import { GhostMascot } from "./ghost-mascot";

import { loadCandidateCohort } from "@/lib/candidate-cohort";

import { CVLibrary } from "./cv-library";

import { ActiveProcesses } from "./active-processes";

import { Jobs } from "./jobs";

import { Verification } from "./verification";

import { Review, Interviews } from "./review";

import { message } from "./common";

import { ActivityProvider, ProcessIndicator, useWorkspaceActivity, useResetTimers } from "./process-indicator";



const steps = [

  {id: "library", label: "CV library", icon: FileCheck2, description: "Import, organize and manage your CV files."},

  {id: "jobs", label: "Job descriptions", icon: BriefcaseBusiness, description: "Define what a great match looks like."},

  {id: "verification", label: "CV verification", icon: FileCheck2, description: "Build your cohort. Find your strongest candidates."},

  {id: "comparison", label: "Comparison matrix", icon: Columns3, description: "Review the evidence. Make the next decision."},

  {id: "interview", label: "Interview", icon: MessagesSquare, description: "Turn your shortlist into meaningful conversations."},

] as const;

type Step = typeof steps[number]["id"];



function EngineSelector({compact}: {compact: boolean}) {
  const workspaceActive = useWorkspaceActivity();
  const cache = useQueryClient();
  // Poll every 3 seconds so cooldowns and limit flags update in real time
  const settings = useQuery({queryKey: ["recruiter-model"], queryFn: () => api.recruiterModels(), refetchInterval: 3000});
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

  // Real-time cooldown inspection for active model
  const activeStatusKey = data ? `${data.active_provider}:${data.active_model}` : "";
  const activeCooldown = data?.cooldown_statuses?.[activeStatusKey];

  return <div ref={root} className={`r-engine ${compact ? "compact" : ""}`} onKeyDown={e => {if (e.key === "Escape") setOpen(false);}}>
    {compact && <button className="r-engine-launch" aria-label="Model and failover settings" aria-expanded={open} title="Model and failover settings" onClick={() => setOpen(!open)}>
      {loading ? <ProcessIndicator active timer={false} track={false} label="Model activity"/> : <Cpu size={20}/>}
    </button>}
    <div className={`r-engine-content ${compact ? "r-engine-popover" : ""}`} hidden={compact && !open}>
      <label htmlFor="recruiter-model"><Cpu size={15}/> Evaluation model <ProcessIndicator active={loading} timer={false} track={false} label="Model activity"/></label>
      <select id="recruiter-model" disabled={!data || !!busy || workspaceActive} aria-busy={loading} value={data ? `${data.active_provider}|${data.active_model}` : ""} onChange={async event => {
        const [provider, ...modelParts] = event.target.value.split("|"); setBusy("model"); setError("");
        try {const next = await api.selectRecruiterModel(provider, modelParts.join("|")); cache.setQueryData(["recruiter-model"], next);}
        catch (e) {setError(message(e));} finally {setBusy("");}
      }}>
        {!data && <option>{settings.isError ? "Model unavailable" : "Loading model…"}</option>}
        {data && <option value={`${data.active_provider}|${data.active_model}`}>{data.active_model}</option>}
        {Object.entries(data?.providers_catalog || {}).map(([provider, info]) => {
          const provCooldowns = Object.values(data?.cooldown_statuses || {}).filter(
            (s: any) => s.provider?.toLowerCase() === provider.toLowerCase()
          );
          const provHasExhausted = provCooldowns.some((s: any) => s.exhausted);
          const provMaxSec = provCooldowns.length > 0 ? Math.max(...provCooldowns.map((s: any) => s.remaining_seconds || 0)) : 0;
          const provFlag = provHasExhausted ? " (⚠️ Limit Hit)" : provMaxSec > 0 ? ` (⏳ Cooldown ${Math.round(provMaxSec)}s)` : "";

          return (
            <optgroup key={provider} label={`${info.name}${provFlag}`}>
              {info.models.filter(m => `${provider}|${m.id}` !== `${data?.active_provider}|${data?.active_model}`).map(model => {
                const mStatusKey = `${provider}:${model.id}`;
                const mStatus = data?.cooldown_statuses?.[mStatusKey];
                const flag = mStatus?.exhausted ? " [⚠️ EXHAUSTED]" : mStatus ? ` [⏳ COOLDOWN ${Math.round(mStatus.remaining_seconds)}s]` : "";
                return (
                  <option key={model.id} value={`${provider}|${model.id}`}>
                    {model.name}{flag}
                  </option>
                );
              })}
            </optgroup>
          );
        })}
      </select>

      {/* Real-time cooldown warning banner */}
      {activeCooldown && (
        <div className={activeCooldown.exhausted ? "r-engine-exhausted-warning" : "r-engine-cooldown-warning"}>
          <AlertTriangle size={13} />
          <span>
            {activeCooldown.exhausted
              ? "Active model rate limit hit — requests auto-failover."
              : `Active model cooling down (${Math.round(activeCooldown.remaining_seconds)}s remaining).`}
          </span>
        </div>
      )}

      <small>{busy === "model" ? "Switching model…" : data ? `Provider: ${data.active_provider}` : "Connect the backend to choose a model"}</small>

      {/* Automatic Failover Switch */}
      <button type="button" role="switch" aria-label="Automatic failover" aria-checked={data?.fallback_enabled ?? true} disabled={!data || !!busy || workspaceActive} className="r-failover-switch" onClick={async () => {
        setBusy("failover"); setError("");
        try {cache.setQueryData(["recruiter-model"], await api.toggleRecruiterFailover(!data!.fallback_enabled));}
        catch (e) {setError(message(e));} finally {setBusy("");}
      }}>
        <span>Failover <span className="r-failover-state">{data?.fallback_enabled ? "On" : "Off"}</span></span>
        <span className={`r-switch-track ${data?.fallback_enabled ? "on" : ""}`} aria-hidden="true"><span/></span>
      </button>

      {/* Parallel Multi-Provider Screening Toggle */}
      <button
        type="button"
        role="switch"
        aria-label="Parallel multi-provider screening"
        aria-checked={data?.parallel_screening_enabled ?? false}
        disabled={!data || !!busy || workspaceActive}
        className="r-failover-switch r-parallel-switch"
        onClick={async () => {
          setBusy("parallel"); setError("");
          try {
            const next = await api.toggleRecruiterParallel(!data?.parallel_screening_enabled);
            cache.setQueryData(["recruiter-model"], next);
          } catch (e) { setError(message(e)); }
          finally { setBusy(""); }
        }}
      >
        <span>
          Parallel Screening{" "}
          <span className="r-failover-state" style={{ color: data?.parallel_screening_enabled ? "#38bdf8" : undefined }}>
            {data?.parallel_screening_enabled ? "⚡ On (Parallel)" : "Off (Sequential)"}
          </span>
        </span>
        <span className={`r-switch-track cyan ${data?.parallel_screening_enabled ? "on" : ""}`} aria-hidden="true">
          <span />
        </span>
      </button>
      <small className="r-engine-help">
        {data?.parallel_screening_enabled
          ? "⚡ Requirements spread concurrently across all healthy tested providers with auto-failover."
          : "Sequential screening: active provider evaluates criteria one-by-one."}
      </small>

      {(error || settings.isError) && <small role="alert">{error || message(settings.error)}</small>}
    </div>
  </div>;
}

function savedSidebarCollapsed() {

  try {return localStorage.getItem("atos_recruiter_sidebar_collapsed") === "true";} catch {return false;}

}



export function RecruiterWorkspace({onLogout}: {onLogout: () => Promise<void>}) {

  const cache = useQueryClient();

  const [version, setVersion] = useState(0);

  const [freshAfter, setFreshAfter] = useState(freshWorkspaceAfter);

  const reset = async () => {

    beginWorkspaceReset();

    try {

      await api.resetWorkspace();

      await cache.cancelQueries({predicate: query => query.queryKey[0] !== "workspace-session"});

      finishWorkspaceReset(true);

      clearTrackedProcesses();

      clearWorkspaceSession();

      setParsingBatch("");

      cache.removeQueries({predicate: query => query.queryKey[0] !== "workspace-session"});

      setFreshAfter(Date.now());

      setVersion(current => current + 1);

      window.scrollTo({top: 0, behavior: "instant"});

    } catch (error) {finishWorkspaceReset(false); throw error;}

  };

  return <ActivityProvider key={version}><RecruiterWorkspaceContent onLogout={onLogout} onReset={reset} freshAfter={freshAfter}/></ActivityProvider>;

}



function RecruiterWorkspaceContent({onLogout, onReset, freshAfter}: {onLogout: () => Promise<void>; onReset: () => Promise<void>; freshAfter: number}) {

  const resetTimers = useResetTimers();
  const workspaceBusy = useWorkspaceActivity();
  const parsing = useParsingBatch();
  const [guided, setGuided] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const advanceLock = useRef(false);
  const jobsPanel = useRef<HTMLDivElement>(null);
  const [workflowError, setWorkflowError] = useState("");
  useEffect(() => {
    try {setGuided(localStorage.getItem("atos_guided_workflow") === "true");} catch { /* Optional preference. */ }
  }, []);


  const [resetting, setResetting] = useState(false);

  const [resetError, setResetError] = useState("");

  const [statisticsOpen, setStatisticsOpen] = useState(false);

  const [logsOpen, setLogsOpen] = useState(false);
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [inFlightCount, setInFlightCount] = useState(0);

  useEffect(() => {
    let mounted = true;
    const checkFlight = async () => {
      try {
        const state = await api.getLiveLLMLogs(1);
        if (mounted) setInFlightCount(state?.in_flight?.length || 0);
      } catch { /* ignore */ }
    };
    checkFlight();
    const interval = setInterval(checkFlight, 2500);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  const cache = useQueryClient();

  const getInitialParam = (key: string, fallback: string = "") => {

    if (typeof window === "undefined") return fallback;

    try {

      const p = new URLSearchParams(window.location.search);

      return p.get(key) || fallback;

    } catch {

      return fallback;

    }

  };



  const initialStep = (getInitialParam("step") as Step) || "jobs";

  const validStep = steps.some(s => s.id === initialStep) ? initialStep : "jobs";

  const [step, setStep] = useState<Step>(validStep);

  const [selectedJob, setSelectedJob] = useState(() => getInitialParam("job"));

  const [activeRunId, setActiveRunId] = useState(() => getInitialParam("run"));

  const [visitedJobs, setVisitedJobs] = useState<string[]>([]);

  const [mobileOpen, setMobileOpen] = useState(false);

  const [collapsed, setCollapsed] = useState(savedSidebarCollapsed);

  const jobs = useQuery({queryKey: ["recruiter-jobs"], queryFn: () => api.getJobs(1000)});

  const candidates = useQuery({queryKey: ["recruiter-candidates", "all"], queryFn: ({signal}) => loadCandidateCohort((limit, offset) => api.getCandidates(limit, offset, signal)), gcTime: 0});

  const jobId = jobs.data?.some(j => j.id === selectedJob) ? selectedJob : freshAfter ? "" : jobs.data?.[0]?.id || "";

  const activeRunRef = useRef(activeRunId);

  activeRunRef.current = activeRunId;

  const activeJobRef = useRef(jobId);

  activeJobRef.current = jobId;

  const openedJobs = [...new Set([...visitedJobs, jobId])].filter(id => id && jobs.data?.some(j => j.id === id));

  const runHistoryQuery = useQuery({queryKey: ["recruiter-run-history", jobId], queryFn: () => api.jobScreeningRuns(jobId), enabled: !!jobId});

  const runQuery = useQuery({

    queryKey: ["recruiter-run", jobId, activeRunId || ""],

    queryFn: () => activeRunId ? api.screeningRun(activeRunId, jobId) : api.latestScreeningRun(jobId),

    enabled: !!jobId,

    refetchInterval: current => ["ranking", "evaluating"].includes(current.state.data?.status || "") ? 2000 : false,

  });

  const run = runQuery.data?.job_id === jobId && (activeRunId || !freshAfter || (runQuery.data.started_at || 0) >= freshAfter) ? runQuery.data : null;



  useEffect(() => {

    if (typeof window === "undefined") return;

    const params = new URLSearchParams(window.location.search);

    if (step) params.set("step", step);

    if (jobId) params.set("job", jobId); else params.delete("job");

    if (activeRunId) params.set("run", activeRunId);

    else params.delete("run");

    const newSearch = params.toString() ? `?${params.toString()}` : "";

    if (window.location.search !== newSearch) {

      window.history.replaceState(null, "", `${window.location.pathname}${newSearch}`);

    }

  }, [step, jobId, activeRunId]);



  const updateRun = (value: ScreeningRun, originRunId?: string) => {

    const stillSelected = value.job_id === activeJobRef.current && (originRunId === undefined || originRunId === activeRunRef.current);

    if (stillSelected) setActiveRunId(value.id);

    cache.setQueryData(["recruiter-run", value.job_id, value.id], value);

    void cache.invalidateQueries({queryKey: ["recruiter-run", value.job_id, ""], exact: true});

    void runHistoryQuery.refetch();

  };

  useEffect(() => {

    const restore = () => {

      const params = new URLSearchParams(window.location.search);

      const next = params.get("step") as Step;

      setStep(steps.some(s => s.id === next) ? next : "jobs");

      setSelectedJob(params.get("job") || "");

      setActiveRunId(params.get("run") || "");

    };

    window.addEventListener("popstate", restore);

    return () => window.removeEventListener("popstate", restore);

  }, []);

  const navigate = (next: Step) => {

    const params = new URLSearchParams(window.location.search); params.set("step", next);

    window.history.pushState(null, "", `${window.location.pathname}?${params}`);

    setStep(next); setMobileOpen(false); window.scrollTo({top: 0, behavior: "instant"});

  };

  const selectJob = (id: string) => {setVisitedJobs(current => [...new Set([...current, jobId, id])].filter(Boolean)); setSelectedJob(id); setActiveRunId("");};

  const currentStep = steps.find(s => s.id === step)!;

  const approved = run?.shortlist_ids.filter(id => run.decisions[id]?.decision === "interview").length || 0;

  const selectedRole = jobs.data?.find(job => job.id === jobId);
  const progress = workflowProgress(candidates.data?.length || 0,
    !!selectedRole?.requirements.some(requirement => requirement.weight > 0), run);
  const stageIndex = workflowStages.findIndex(item => item.id === step);
  const workflowBusy = workspaceBusy || advancing || jobs.isPending || candidates.isPending || runQuery.isFetching ||
    (!!parsing.batchId && (parsing.batch.isPending || ["PROCESSING", "QUEUED"].includes(parsing.batch.data?.status || "")));
  const advance = async () => {
    if (advanceLock.current || workflowBusy || !progress.complete[stageIndex] || stageIndex >= workflowStages.length - 1) return;
    advanceLock.current = true;
    setAdvancing(true); setWorkflowError("");
    const originJob = jobId;
    const originRun = activeRunId;
    try {
      if (step === "jobs") {
        const form = Array.from(jobsPanel.current?.querySelectorAll<HTMLFormElement>("form") || []).find(item => item.getClientRects().length > 0);
        const submitter = form?.querySelector<HTMLButtonElement>('button[data-intent="continue"]');
        if (form && submitter) {form.requestSubmit(submitter); return;}
      }
      if (step === "verification" && run && !run.shortlist_ids.length) {
        const updated = await api.shortlist(run.id, Math.min(10, progress.evaluatedCount));
        updateRun(updated, originRun);
        if (activeJobRef.current !== originJob || activeRunRef.current !== originRun) return;
      }
      navigate(workflowStages[stageIndex + 1].id);
    } catch (error) {setWorkflowError(message(error));}
    finally {advanceLock.current = false; setAdvancing(false);}
  };
  const toggleGuided = () => {
    const next = !guided;
    setGuided(next); setWorkflowError("");
    const firstIncomplete = progress.complete.findIndex(done => !done);
    if (next && firstIncomplete >= 0 && firstIncomplete < stageIndex) navigate(workflowStages[firstIncomplete].id);
    try {localStorage.setItem("atos_guided_workflow", String(next));} catch { /* Optional preference. */ }
  };

  const workflowProps = {
    stage: step, complete: progress.complete, hints: progress.hints, busy: workflowBusy, error: workflowError,
    shortlistNeeded: step === "verification" && !run?.shortlist_ids.length,
    onNavigate: (next: Step) => {setWorkflowError(""); navigate(next);}, onNext: () => void advance(),
  };

  const error = jobs.error || candidates.error || runQuery.error;

  return <div className={`recruiter r-workspace ${collapsed ? "sidebar-collapsed" : ""}`} data-theme="dark">

    {statisticsOpen && <StatisticsDialog onClose={() => setStatisticsOpen(false)}/>}

    {logsOpen && <LogsDialog jobId={jobId} runId={run?.id} onClose={() => setLogsOpen(false)}/>}
    {consoleOpen && <LiveLLMDebugModal open={consoleOpen} onClose={() => setConsoleOpen(false)}/>}

    <a className="r-skip" href="#recruiter-main">Skip to content</a>

    {mobileOpen && <button aria-label="Close navigation" className="r-nav-scrim" onClick={() => setMobileOpen(false)}/>}

    <aside id="recruiter-sidebar" className={`r-sidebar ${mobileOpen ? "open" : ""}`}>

      <div className="r-brand"><GhostMascot activityKey={`${step}:${jobId}`}/><span className="r-brand-name r-asap-wordmark">ASAP</span><button className="r-mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={20}/></button><button className="r-collapse-sidebar" aria-label={collapsed ? "Expand sidebar" : "Minimize sidebar"} title={collapsed ? "Expand sidebar" : "Minimize sidebar"} aria-controls="recruiter-sidebar" aria-expanded={!collapsed} onClick={() => {const next = !collapsed; setCollapsed(next); try {localStorage.setItem("atos_recruiter_sidebar_collapsed", String(next));} catch { /* Sidebar remains usable without storage. */ }}}>{collapsed ? <PanelLeftOpen size={16}/> : <PanelLeftClose size={16}/>}</button></div>



      <EngineSelector compact={collapsed && !mobileOpen}/>

      <div className="r-nav-label">Your hiring workflow</div>

      <nav aria-label="Recruiter workflow">{steps.map((item, index) => <button key={item.id} className={`r-nav-item ${step === item.id ? "active" : ""}`} aria-label={item.label} title={item.label} aria-current={step === item.id ? "page" : undefined} onClick={() => navigate(item.id)}><item.icon size={19}/><span>{item.label}</span><small>{guided ? index + 1 : item.id === "library" ? "" : index}</small></button>)}</nav>

      

      <div className="r-sidebar-bottom">

        <button type="button" className="r-workspace-reset" aria-label="Reset workspace" disabled={resetting} title="Stop this tab's processes and clear selections, drafts, results and timers. Saved CVs and jobs are kept." onClick={async () => {

          setResetting(true); setResetError("");

          try {await onReset();} catch (e) {setResetError(message(e)); setResetting(false);}

        }}><RotateCcw size={18} aria-hidden="true"/><span>{resetting ? "Resetting…" : "Reset workspace"}</span></button>

        {resetError && <p className="r-inline-error" role="alert">{resetError}</p>}

      <div className="r-profile"><span className="r-avatar">R</span><div><strong>Recruiter</strong><small>User workspace</small></div><button onClick={onLogout} title="Sign out" aria-label="Sign out"><LogOut size={18}/></button></div>

      </div>

    </aside>

    <div className="r-main-wrap"><div className="r-header-container"><header className={`r-topbar ${guided ? "r-topbar-guided" : ""}`}><div>

      <button className="r-mobile-menu" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={20}/></button>

      <span>Workspace</span><ChevronRight size={14}/><strong>{currentStep.label}</strong></div>
      {guided && <WorkflowProgress {...workflowProps} part="stages"/>}
      <div className="r-topbar-actions">
        {/* In-App LLM Console Button in Top Right */}
        <button
          type="button"
          className={`r-console-button ${inFlightCount > 0 ? "active-flight" : ""}`}
          onClick={() => setConsoleOpen(true)}
          title="Open In-App LLM Console: inspect models, providers, input prompts, raw outputs, latency, tokens, and errors"
          aria-label="Open LLM Console"
        >
          <Terminal size={14} />
          <span>LLM Console</span>
          {inFlightCount > 0 ? (
            <span className="r-console-pill">{inFlightCount} active</span>
          ) : (
            <span className="r-console-pill">Live</span>
          )}
        </button><button type="button" className="r-reset-timers" onClick={resetTimers} title="Clear completed process durations" aria-label="Reset timers"><RotateCcw size={13}/><span>Reset timers</span></button><button type="button" className="r-logs-button" aria-haspopup="dialog" onClick={() => setLogsOpen(true)} title="View full action trace, LLM outputs, raw JD and candidate CVs" aria-label="Action logs"><ScrollText size={13}/><span>Logs</span></button><button type="button" className="r-statistics-button" aria-haspopup="dialog" onClick={() => setStatisticsOpen(true)}><ChartNoAxesColumn size={16}/>Statistics</button></div></header></div>

      <main id="recruiter-main" className={`r-main ${guided ? "r-guided-main" : ""}`}>
        <div className="r-workflow-mode"><label><input type="checkbox" checked={guided} onChange={toggleGuided}/>Guided progression</label><small>{guided ? "Complete each stage, then continue with Next." : "Turn on step-by-step hiring."}</small></div>
        {guided && <WorkflowProgress {...workflowProps} part="footer"/>}
        <div className="r-page-heading"><div><h1>{currentStep.label}</h1><p>{currentStep.description}</p></div><span className="r-step-count">{guided ? `Step ${stageIndex + 1} of ${workflowStages.length}` : step === "library" ? "File management" : `Step ${steps.filter(s => s.id !== "library").findIndex(s => s.id === step) + 1} of 4`}</span></div>

        {step !== "jobs" && step !== "library" && <div className="r-job-context">

          <label htmlFor="active-role">Hiring for</label>

          <select id="active-role" value={jobId} onChange={e => selectJob(e.target.value)} disabled={!jobs.data?.length}>

            <option value="" disabled>Select a job description</option>

            {jobs.data?.map(job => <option key={job.id} value={job.id}>{job.title}</option>)}

          </select>

          {!!runHistoryQuery.data?.length && runHistoryQuery.data.length > 1 && (

            <select aria-label="Run history" value={run?.id || ""} onChange={e => setActiveRunId(e.target.value)} title="Select past screening run">

              <option value="">Latest run</option>

              {runHistoryQuery.data.map(r => (

                <option key={r.id} value={r.id}>

                  Run: {r.created_at ? new Date(r.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : r.id.slice(0,6)} ({r.ranked_candidates} candidates)

                </option>

              ))}

            </select>

          )}

          <span>{run?.shortlist_ids.length || 0} in comparison <span className="r-dot">/</span> {approved} approved for interview</span>

        </div>}

        <ActiveProcesses/>

        {error && <div role="alert" className="r-alert">{message(error)} <button onClick={() => {jobs.refetch(); candidates.refetch(); runQuery.refetch();}}>Retry</button>{activeRunId && <button onClick={() => setActiveRunId("")}>Load latest run for this role</button>}</div>}

        {jobs.isPending || candidates.isPending ? <div className="r-loading" role="status"><ProcessIndicator active timer={false} label="Loading workspace"/>Loading your workspace…</div> : <>

          <div hidden={step !== "library"}><CVLibrary/></div>

          <div ref={jobsPanel} hidden={step !== "jobs"}><Jobs jobs={jobs.data || []} selectedId={jobId} editorIds={openedJobs} onSelect={selectJob} onSaved={async id => {await jobs.refetch(); selectJob(id);}} onContinue={() => navigate("verification")}/></div>

          {openedJobs.map(id => <CandidateWorkspace key={id} jobId={id} activeRunId={id === jobId ? activeRunId : ""} freshAfter={freshAfter} visible={id === jobId && step !== "jobs" && step !== "library"} step={step} candidates={candidates.data || []} onRun={updateRun} onRefresh={() => candidates.refetch()} onNavigate={next => {if (activeJobRef.current === id) navigate(next);}} onRunHistoryUpdate={() => runHistoryQuery.refetch()}/>)}

          {!jobId && step !== "jobs" && step !== "library" && <p className="r-inline-empty">{jobs.data?.length ? "Select a job description above to begin a fresh screening." : "Add a job description to begin screening candidates."}</p>}

          {!jobId && <div hidden={step !== "verification"}><Verification jobId="" candidates={candidates.data || []} run={null} onRun={updateRun} onRefresh={() => candidates.refetch()} onCompare={() => navigate("comparison")}/></div>}

        </>}

      </main>

    </div>

  </div>;

}



/** Keep each visited job's working views mounted so navigation never discards a request or result. */

function CandidateWorkspace({jobId, activeRunId, freshAfter, visible, step, candidates, onRun, onRefresh, onNavigate, onRunHistoryUpdate}: {

  jobId: string; activeRunId: string; freshAfter: number; visible: boolean; step: Step; candidates: CandidateSummary[];

  onRun: (run: ScreeningRun, originRunId?: string) => void; onRefresh: () => Promise<unknown>; onNavigate: (step: Step) => void;

  onRunHistoryUpdate?: () => void;

}) {

  const query = useQuery({queryKey: ["recruiter-run", jobId, activeRunId || ""], queryFn: () => activeRunId ? api.screeningRun(activeRunId, jobId) : api.latestScreeningRun(jobId),

    refetchInterval: current => ["ranking", "evaluating"].includes(current.state.data?.status || "") ? 2000 : false});

  const run = query.data?.job_id === jobId && (activeRunId || !freshAfter || (query.data.started_at || 0) >= freshAfter) ? query.data : null;

  const prevStatus = useRef(run?.status);

  useEffect(() => {

    if (run && ["completed", "partial", "failed", "cancelled"].includes(run.status) && prevStatus.current !== run.status) {

      prevStatus.current = run.status;

      onRunHistoryUpdate?.();

    }

  }, [run?.status, onRunHistoryUpdate]);

  useEffect(() => {prevStatus.current = run?.status;}, [run?.status]);

  const receiveRun = (value: ScreeningRun) => onRun(value, activeRunId);

  return <div hidden={!visible}>

    <div hidden={step !== "verification"}><Verification jobId={jobId} candidates={candidates} run={run} onRun={receiveRun} onRefresh={onRefresh} onCompare={() => onNavigate("comparison")}/></div>

    <div hidden={step !== "comparison"}><Review key={run?.id || jobId} run={run} candidates={candidates} onRun={receiveRun} onInterview={() => onNavigate("interview")} onBack={() => onNavigate("verification")}/></div>

    <div hidden={step !== "interview"}><Interviews key={run?.id || jobId} run={run} candidates={candidates} onBack={() => onNavigate("comparison")}/></div>

  </div>;

}

