"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, BriefcaseBusiness, Check, MapPin, Plus, Search, Trash2, X, WandSparkles } from "lucide-react";
import { JobDescription, JobRequirement } from "@/types";
import { api } from "@/lib/api";
import { validateJobDraft, JobDraftIssue } from "@/lib/job-draft";
import { downloadJson, Empty, message } from "./common";
import { ExtractedData } from "./parsed-profile";
import { ProcessIndicator, useTimedActivity } from "./process-indicator";

interface Props {
  jobs: JobDescription[];
  selectedId: string;
  editorIds: string[];
  onSelect: (id: string) => void;
  onSaved: (jobOrId: JobDescription | string) => Promise<void>;
  onContinue: () => void;
}

export function Jobs({jobs, selectedId, editorIds, onSelect, onSaved, onContinue}: Props) {
  const roleList = useRef<HTMLElement>(null);
  useEffect(() => {
    const panel = roleList.current;
    if (!panel) return;
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (window.innerWidth <= 900 || !panel.getClientRects().length) return;
        const top = Math.max(18, panel.getBoundingClientRect().top);
        const available = Math.max(240, window.innerHeight - top - 12);
        panel.style.setProperty("--r-roles-height", `${available}px`);
      });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(panel);
    window.addEventListener("scroll", measure, {passive: true});
    window.addEventListener("resize", measure);
    measure();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, []);
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const searchWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (searchWrapRef.current && !searchWrapRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);
  const [creating, setCreating] = useState(false);
  const [draftKey, setDraftKey] = useState<string | null>(null);
  const job = jobs.find(j => j.id === selectedId);
  const filtered = jobs.filter(j => `${j.title} ${j.department || ""}`.toLowerCase().includes(search.toLowerCase()));
  return <>
    <div className="r-section-toolbar">
      <div className="r-search" style={{ position: "relative" }} ref={searchWrapRef}>
        <Search size={17}/>
        <input
          aria-label="Search jobs"
          placeholder="Search job descriptions"
          value={search}
          onChange={e => {
            setSearch(e.target.value);
            setSearchOpen(true);
          }}
          onFocus={() => { if (search.trim()) setSearchOpen(true); }}
          onKeyDown={e => { if (e.key === "Escape") setSearchOpen(false); }}
        />
        {search && (
          <button
            type="button"
            className="r-job-search-clear"
            onClick={() => {
              setSearch("");
              setSearchOpen(false);
            }}
            aria-label="Clear job search"
          >
            <X size={14}/>
          </button>
        )}
        {searchOpen && search.trim() && (
          <div className="r-search-autocomplete" role="listbox">
            {filtered.length === 0 ? (
              <div className="r-search-empty">No matching roles found</div>
            ) : (
              filtered.slice(0, 8).map(j => (
                <button
                  key={j.id}
                  type="button"
                  className={`r-search-item ${j.id === selectedId ? "active" : ""}`}
                  onClick={() => {
                    setCreating(false);
                    onSelect(j.id);
                    setSearchOpen(false);
                  }}
                  role="option"
                  aria-selected={j.id === selectedId}
                >
                  <div className="r-search-item-title">
                    <span>{j.title}</span>
                    {j.id === selectedId && <span className="r-pill success" style={{ fontSize: 10, padding: "1px 6px" }}>Active</span>}
                  </div>
                  <div className="r-search-item-meta">
                    <span>{j.department || "General"}</span>
                    <span>·</span>
                    <span>{j.requirements?.length || 0} criteria</span>
                  </div>
                </button>
              ))
            )}
          </div>
        )}
      </div>
      <button className="r-button primary" onClick={() => {setDraftKey(current => current || crypto.randomUUID()); setCreating(true);}}><Plus size={17}/> Add job description</button>
    </div>
    <div className="r-jobs-layout">
      <section ref={roleList} className="r-job-list-shell" aria-label="Available jobs">
        <div className="r-list-heading">Available roles <span>{jobs.length}</span></div>
        <div className="r-job-list" tabIndex={0} aria-label="Scroll available roles">
        {filtered.map(j => <button className={`r-job-card ${!creating && j.id === selectedId ? "selected" : ""}`} key={j.id} onClick={() => {setCreating(false); onSelect(j.id);}}>
          <div className="r-job-card-icon"><BriefcaseBusiness size={19}/></div><h3>{j.title}</h3><p>{j.department || "Department not specified"}</p>
          <div><span><MapPin size={13}/>{j.location || j.work_model || "Location not specified"}</span><span>{j.requirements.length} criteria</span></div>
        </button>)}
        {!filtered.length && <Empty title={search ? "No matching roles" : "Start with a job description"}>{search ? "Try a different title or department." : "Add a role and define the criteria for your shortlist."}</Empty>}
        </div>
        <div className="r-job-list-footer">{filtered.length} {filtered.length === 1 ? "role" : "roles"}{filtered.length > 3 && <span>Scroll to browse</span>}</div>
      </section>
      <div>
        {draftKey && <div hidden={!creating}><JobEditor key={draftKey} onCancel={() => {setCreating(false); setDraftKey(null);}} onSave={async saved => {await onSaved(saved); setCreating(false); setDraftKey(null);}} onContinue={onContinue}/></div>}
        {editorIds.map(id => {const editorJob = jobs.find(item => item.id === id); return editorJob ? <div key={id} hidden={creating || id !== selectedId}><JobEditor job={editorJob} onSave={onSaved} onContinue={onContinue}/></div> : null;})}
        {!creating && !job && <div className="r-panel"><Empty title={jobs.length ? "Choose a role to begin" : "A clear role is a better starting point"}>{jobs.length ? "Select a saved role or add a new job description to begin screening." : "Add your first job description to begin screening."}</Empty></div>}
      </div>
    </div>
  </>;
}

function JobEditor({job, onSave, onContinue, onCancel}: {job?: JobDescription; onSave: (jobOrId: JobDescription | string) => Promise<void>; onContinue: () => void; onCancel?: () => void}) {
  const [draft, setDraft] = useState<JobDescription>(job || {id: crypto.randomUUID(), title: "", department: "", location: "", requirements: [], raw_text: ""});
  const [url, setUrl] = useState("");
  const [extractionDuration, setExtractionDuration] = useState<number | null>(null);
  const [busy, setBusy, startedAt, lastActivity] = useTimedActivity<string>("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [dirty, setDirty] = useState(!job);
  const [issues, setIssues] = useState<JobDraftIssue[]>([]);
  const errorSummary = useRef<HTMLDivElement>(null);
  useEffect(() => {if (error || issues.length) errorSummary.current?.focus();}, [error, issues]);
  function update(value: Partial<JobDescription>) {setDraft(current => ({...current, ...value})); setSaved(false); setDirty(true); setIssues([]); setError("");}
  async function extract(fromUrl: boolean) {
    const startTime = Date.now();
    setBusy(fromUrl ? "url" : "parse"); setError("");
    try {
      const result = fromUrl ? await api.parseRecruiterJobUrl(url) : await api.parseRecruiterJob(draft.raw_text!);
      // Preserve the parser's complete contract and requirement identifiers, as Admin does.
      update({...result.job_description, id: draft.id});
      setExtractionDuration(Math.round((Date.now() - startTime) / 100) / 10);
    } catch (e) {setError(message(e));} finally {setBusy("");}
  }
  return <form className="r-panel r-job-editor" noValidate onSubmit={async e => {
    e.preventDefault();
    if (busy) return;
    const continueToCvs = (e.nativeEvent as SubmitEvent).submitter?.getAttribute("data-intent") === "continue";
    const problems = validateJobDraft(draft, continueToCvs);
    setIssues(problems); setError("");
    if (problems.length) return;
    if (continueToCvs && job && !dirty) {onContinue(); return;}
    setBusy("save");
    try {
      const persisted = await api.createJob({...draft, title: draft.title.trim()});
      await onSave(persisted); setSaved(true); setDirty(false);
      if (continueToCvs) onContinue();
    }
    catch(e) {setError(message(e));} finally {setBusy("");}
  }}>
    <div className="r-panel-heading"><div><span className="r-muted">{job ? "Role details" : "New role"}</span><h2>{job?.title || "Define your next hire"}</h2></div><ProcessIndicator active={!!busy} timer={false} label="Updating job description"/>{onCancel && <button type="button" className="r-icon-button" aria-label="Cancel new job" disabled={!!busy} onClick={onCancel}><X size={18}/></button>}</div>
    {(error || issues.length > 0) && <div ref={errorSummary} className="r-alert" role="alert" tabIndex={-1}>
      <strong>{error || "Review the job description before saving:"}</strong>
      {issues.length > 0 && <ul>{issues.map((issue, index) => <li key={index}><a href={`#${draft.id}-${issue.field}`} onClick={event => {
        event.preventDefault(); const field = document.getElementById(`${draft.id}-${issue.field}`);
        const details = field?.closest("details"); if (details) details.open = true;
        requestAnimationFrame(() => {field?.focus(); field?.scrollIntoView({block: "center"});});
      }}>{issue.message}</a></li>)}</ul>}
    </div>}
    <div className="r-editor-body">
      <div className="r-form-grid">
        <label className="r-field r-span-2">Job title<input id={`${draft.id}-title`} required value={draft.title} onChange={e => update({title: e.target.value})} placeholder="e.g. Senior Backend Engineer"/></label>
        <label className="r-field">Department<input value={draft.department || ""} onChange={e => update({department: e.target.value})} placeholder="e.g. Engineering"/></label>
        <label className="r-field">Location<input value={draft.location || ""} onChange={e => update({location: e.target.value})} placeholder="e.g. Bucharest / Remote"/></label>
      </div>
      <details className="r-disclosure"><summary>Import a job description</summary>
        <label className="r-field">Job posting URL<input type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…"/></label>
        <button type="button" className="r-button" aria-busy={busy === "url"} disabled={!!busy || !/^https?:\/\//.test(url)} onClick={() => extract(true)}><WandSparkles size={16}/><ProcessIndicator active={busy === "url"} startedAt={lastActivity === "url" ? startedAt : null} label="Extracting from URL"/> {busy === "url" ? "Extracting from URL…" : "Extract from URL"}</button>
        <label className="r-field">Or paste the full description<textarea rows={6} value={draft.raw_text || ""} onChange={e => update({raw_text: e.target.value})} placeholder="Paste the job description here…"/></label>
        <button type="button" className="r-button" aria-busy={busy === "parse"} disabled={!!busy || !(draft.raw_text || "").trim()} onClick={() => extract(false)}><WandSparkles size={16}/><ProcessIndicator active={busy === "parse"} startedAt={lastActivity === "parse" ? startedAt : null} label="Extracting job criteria"/> {busy === "parse" ? "Extracting criteria…" : "Extract criteria"}</button>
        {extractionDuration != null && <span className="r-duration-badge success" style={{ marginLeft: 8 }}><Check size={12}/>Criteria extracted in {extractionDuration.toFixed(1)}s</span>}
      </details>
      <details className="r-disclosure"><summary>Role details & additional extracted content</summary>
        <div className="r-form-grid">
          <label className="r-field">Seniority<input value={draft.seniority_level || ""} onChange={e => update({seniority_level: e.target.value})}/></label>
          <label className="r-field">Work model<input value={draft.work_model || ""} onChange={e => update({work_model: e.target.value})} placeholder="Remote, hybrid or on-site"/></label>
          <label className="r-field">Employment type<input value={draft.employment_type || ""} onChange={e => update({employment_type: e.target.value})} placeholder="Full-time, contract…"/></label>
          <label className="r-field">Languages<input key={(draft.languages || []).join(",")} defaultValue={(draft.languages || []).join(", ")} onBlur={e => update({languages: e.target.value.split(",").map(s => s.trim()).filter(Boolean)})} placeholder="Comma-separated languages"/></label>
        </div>
        {!!draft.custom_sections?.length && <><h3>Additional sections</h3><ExtractedData value={draft.custom_sections}/></>}
        {!!draft.unused_details?.length && <><h3>Other source content</h3><ExtractedData value={draft.unused_details}/></>}
        <button type="button" className="r-button subtle" onClick={() => downloadJson(draft, "job-description.json")}>Download structured job description</button>
      </details>
      <div id={`${draft.id}-criteria`} tabIndex={-1} className="r-criteria-heading">
        <div>
          <h3>Screening criteria</h3>
          <p>Open a criterion to adjust its evidence, importance and experience.</p>
        </div>
        {extractionDuration != null && (
          <span className="r-duration-badge success" style={{ marginLeft: "auto", marginRight: 12 }}>
            <Check size={12}/>Criteria extracted in {extractionDuration.toFixed(1)}s
          </span>
        )}
        <button type="button" className="r-button subtle" onClick={() => update({requirements: [...draft.requirements, {id: crypto.randomUUID(), title: "", description: "", category: "must_have", weight: 1}]})}><Plus size={16}/> Add criterion</button>
      </div>
      {draft.requirements.length === 0 && <p className="r-inline-empty">No criteria yet. Add a requirement or extract them from the description.</p>}
      <div className="r-criteria-list">{draft.requirements.map((r, index) => <Criterion key={r.id} idPrefix={draft.id} requirement={r} index={index} onChange={value => update({requirements: draft.requirements.map((item, i) => i === index ? {...item, ...value} : item)})} onRemove={() => update({requirements: draft.requirements.filter((_, i) => i !== index)})}/>)}</div>
      {saved && <p className="r-success" role="status">Job description saved.</p>}
    </div>
    <div className="r-editor-footer"><button className="r-button" type="submit" disabled={!!busy}><ProcessIndicator active={busy === "save"} startedAt={lastActivity === "save" ? startedAt : null} label="Saving job description"/>{busy === "save" ? "Saving…" : "Save job description"}</button><button className="r-button primary" type="submit" data-intent="continue" disabled={!!busy}>{!job || dirty ? "Save and continue to CVs" : "Continue to CVs"}<ArrowRight size={16}/></button></div>
  </form>;
}

function Criterion({requirement: r, index, idPrefix, onChange, onRemove}: {idPrefix: string; requirement: JobRequirement; index: number; onChange: (value: Partial<JobRequirement>) => void; onRemove: () => void}) {
  const [open, setOpen] = useState(!r.title);
  return <details className="r-criterion" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="r-criterion-summary"><span>{r.title || "New criterion"}</span><small>{r.category === "must_have" ? "Required" : r.category === "nice_to_have" ? "Preferred" : "Soft skill"}</small></summary>
    <div className="r-criterion-title"><label className="r-field">Criterion {index + 1}<input id={`${idPrefix}-criterion-${index}-title`} required value={r.title} placeholder="e.g. Python development" onChange={e => onChange({title: e.target.value})}/></label><button type="button" aria-label={`Remove criterion ${index + 1}`} className="r-icon-button" onClick={onRemove}><Trash2 size={16}/></button></div>
    <label className="r-field">Evidence to look for<textarea rows={2} value={r.description} onChange={e => onChange({description: e.target.value})} placeholder="Describe what the candidate needs to demonstrate"/></label>
      {r.category === "must_have" && <label className="r-field">Evidence required before automatic deep evaluation<input value={r.eligibility_evidence || ""} placeholder="e.g. Based in Bucharest" onChange={e => onChange({eligibility_evidence: e.target.value || null})}/><small>Optional exact source phrase. Use an explicit availability statement for local presence. Missing evidence goes to clarification; it does not reject the candidate.</small></label>}
    <div className="r-criterion-controls">
      <label className="r-field">Priority<select value={r.category} onChange={e => onChange({category: e.target.value as JobRequirement["category"]})}><option value="must_have">Required</option><option value="nice_to_have">Nice to have</option><option value="soft_skill">Soft skill</option></select></label>
      <label className="r-field">Weight<input id={`${idPrefix}-criterion-${index}-weight`} type="number" min={0} max={10} step="any" required value={r.weight} onChange={e => onChange({weight: Number(e.target.value)})}/></label>
      <label className="r-field">Minimum years<input id={`${idPrefix}-criterion-${index}-years`} type="number" min={0} max={60} placeholder="Any" value={r.minimum_years_experience ?? ""} onChange={e => onChange({minimum_years_experience: e.target.value ? Number(e.target.value) : null})}/></label>
    </div>
  </details>;
}
