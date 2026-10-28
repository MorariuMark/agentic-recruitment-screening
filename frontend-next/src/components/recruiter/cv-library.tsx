"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, FileText, Search, Trash2, Upload, RotateCcw, LoaderCircle } from "lucide-react";
import { useParsingBatch } from "@/lib/parsing-batch";
import { ParsingProgress } from "./parsing-progress";
import { api, type CVDocument } from "@/lib/api";
import { Empty, message } from "./common";
import { ProfileDialog } from "./profile";
import { RawCVDialog } from "./raw-cv-dialog";

export function CVLibrary() {
  const cache = useQueryClient();
  const {batchId, batch, setBatchId} = useParsingBatch();
  const [batchLimit, setBatchLimit] = useState(25);
  const [concurrency, setConcurrency] = useState(4);
  const [starting, setStarting] = useState(false);
  const startLock = useRef(false);
  const [preview, setPreview] = useState<CVDocument | null>(null);
  const parsing = starting || (!!batchId && batch.isPending) || ["PROCESSING", "QUEUED"].includes(batch.data?.status || "");
  const library = useQuery({queryKey: ["cv-library"], queryFn: () => api.cvLibrary(), refetchInterval: 10000});
  const input = useRef<HTMLInputElement>(null);
  const progressPanel = useRef<HTMLDivElement>(null);
  const [trash, setTrash] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<string>("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  const records = (library.data || []).filter(cv => !!cv.deleted_at === trash);
  const filtered = records.filter(cv => cv.filename.toLowerCase().includes(search.toLowerCase()));
  const ids = selected.filter(id => records.some(cv => cv.id === id));
  const fileProgress = new Map((batch.data?.files || []).filter(file => file.document_id).map(file => [file.document_id, file]));
  const candidateId = (cv: CVDocument) => cv.candidate_id || fileProgress.get(cv.id)?.candidate_id || null;
  const pendingIds = ids.filter(id => records.some(cv => cv.id === id && !candidateId(cv)));
  const parsedCount = records.filter(cv => candidateId(cv)).length;
  const validLimit = Number.isInteger(batchLimit) && batchLimit >= 1 && batchLimit <= 1000;
  const parseCount = validLimit ? Math.min(batchLimit, pendingIds.length) : 0;
  const waitingOutsideBatch = pendingIds.filter(id => !fileProgress.has(id)).length;
  const all = filtered.length > 0 && filtered.every(cv => ids.includes(cv.id));
  const currentPage = Math.min(page, Math.max(0, Math.ceil(filtered.length / 25) - 1));
  const visible = filtered.slice(currentPage * 25, currentPage * 25 + 25);
  async function perform(work: () => Promise<string>, actionType: string = "", targetId: string | null = null) {
    setBusy(true); setBusyAction(actionType); setDeletingId(targetId); setError(""); setNotice("");
    try {setNotice(await work()); setSelected([]);}
    catch (e) {setError(message(e));}
    finally {setBusy(false); setBusyAction(""); setDeletingId(null); await cache.invalidateQueries({queryKey: ["cv-library"]}); await cache.invalidateQueries({queryKey: ["recruiter-candidates"]}); await cache.invalidateQueries({queryKey: ["recruiter-run"]});}
  }
  function change(action: "trash" | "restore" | "delete", targets = ids) {
    if (action === "delete" && !window.confirm(`Permanently delete ${targets.length} CV(s), including their profiles and screening results? This cannot be undone.`)) return;
    const targetSingle = targets.length === 1 ? targets[0] : null;
    void perform(async () => {const result = await api.libraryAction(targets, action); return `${result.changed} CV(s) ${action === "trash" ? "moved to Trash for 30 days" : action === "restore" ? "restored" : "permanently deleted"}.`;}, action, targetSingle);
  }
  return <>
    <div className="r-tabs" role="tablist" aria-label="CV library view">
      <button role="tab" aria-selected={!trash} className={!trash ? "active" : ""} onClick={() => {setTrash(false); setSelected([]); setPage(0);}}><FileText size={17}/>All CVs<span>{library.data?.filter(cv => !cv.deleted_at).length || 0}</span></button>
      <button role="tab" aria-selected={trash} className={trash ? "active" : ""} onClick={() => {setTrash(true); setSelected([]); setPage(0);}}><Trash2 size={17}/>Trash<span>{library.data?.filter(cv => cv.deleted_at).length || 0}</span></button>
    </div>
    <p className="r-muted">Import and manage original CVs here. Importing does not parse, verify or screen them. Exact duplicate files are automatically discarded, keeping one original. Reuploading an identical CV from Trash permanently replaces the trashed copy.</p>
    {!trash && <div className="r-library-totals" role="status" aria-live="polite"><span><strong>{parsedCount}</strong> parsed</span><span><strong>{records.length - parsedCount}</strong> still need parsing</span><span><strong>{records.length}</strong> total CVs</span></div>}
    {trash && <p className="r-processing-note">CVs can be restored for 30 days. Expired files are permanently deleted automatically while the backend is running.</p>}
    {(error || library.error) && <div className="r-alert" role="alert">{error || message(library.error)}<button onClick={() => library.refetch()}>Refresh library</button></div>}
    {notice && <p className="r-processing-note" role="status">{notice}</p>}
    <input ref={input} type="file" multiple accept=".pdf,.docx,.txt" hidden aria-label="Import CV files" disabled={busy} onChange={event => {
      const files = Array.from(event.target.files || []); event.target.value = "";
      if (files.length) void perform(async () => {const result = await api.importCVs(files); return `${result.imported} CV(s) imported. ${result.duplicates_removed} exact duplicate(s) discarded. No verification started.`;});
    }}/>
    <div ref={progressPanel} className="r-parsing-anchor"><ParsingProgress/></div>
    <section className="r-panel r-cohort" aria-busy={busy}>
      <div className="r-table-toolbar"><div><h2>{trash ? "Trash" : "CV library"} <span>{records.length}</span></h2><p>{ids.length} selected · {filtered.length} matching</p></div>
        <div className="r-table-toolbar-actions"><div className="r-search"><Search size={16}/><input aria-label="Search CV filenames" placeholder="Search CV filenames" value={search} onChange={event => {setSearch(event.target.value); setPage(0);}}/></div>
          {!trash && <button className="r-button primary" disabled={busy} onClick={() => input.current?.click()}><Upload size={16}/>Import CVs</button>}
        </div>
      </div>
      <div className="r-library-actions">
        <button className="r-button" disabled={busy || !records.length} onClick={() => setSelected(records.map(cv => cv.id))}>Select all {records.length} CVs</button>
        <button className="r-button subtle" disabled={busy || !ids.length} onClick={() => setSelected([])}>Clear selection</button>
        {trash ? <button className="r-button" disabled={busy || !ids.length} onClick={() => change("restore")}><RotateCcw size={16}/>Restore selected</button> : <>
          <button className="r-button" disabled={busy || !ids.length} onClick={() => change("trash")}><Trash2 size={16}/>Move selected to Trash</button>

        </>}
        <button className="r-button r-danger" disabled={busy || !ids.length} onClick={() => change("delete")}>{busy && busyAction === "delete" && !deletingId ? <><LoaderCircle className="r-spinner" size={15}/> Deleting {ids.length} CV(s)…</> : "Permanently delete selected"}</button>
      </div>
      {!trash && <div className="r-library-parse-controls" aria-label="Batch parsing settings">
        <label className="r-field">CVs in this batch<input type="number" min={1} max={1000} value={batchLimit} disabled={parsing} onChange={event => setBatchLimit(Number(event.target.value))}/></label>
        <label className="r-field">Process simultaneously<select value={concurrency} disabled={parsing} onChange={event => setConcurrency(Number(event.target.value))}>{[1, 2, 3, 4].map(count => <option key={count} value={count}>{count} CV{count > 1 ? "s" : ""} at a time</option>)}</select></label>
        <div><p>{parsing ? `${waitingOutsideBatch} selected CV(s) outside this batch. Live results are shown above.` : `${pendingIds.length} selected CVs still need parsing. ${parseCount} will be queued in the next batch.`}</p><small>{ids.length - pendingIds.length} already parsed selected CV(s) will be ignored. Each batch stops when finished; another batch starts only when you click Parse.</small></div>
        <button className="r-button primary" disabled={busy || parsing || !parseCount || !validLimit} onClick={async () => {
          if (startLock.current || parsing) return;
          startLock.current = true;
          setStarting(true); setError(""); setNotice("");
          try {
            // Recheck durable links at the moment of submission, including work finished in another tab.
            const fresh = await api.cvLibrary();
            cache.setQueryData(["cv-library"], fresh);
            const remaining = new Set(pendingIds);
            const eligible = fresh.filter(cv => remaining.has(cv.id) && !cv.deleted_at && !cv.candidate_id).map(cv => cv.id);
            if (!eligible.length) {setNotice("All selected CVs are already parsed. No new parsing session was started."); return;}
            const result = await api.prepareCVs(eligible, batchLimit, concurrency);
            setBatchId(result.batch_id);
            requestAnimationFrame(() => {
              if (progressPanel.current?.getClientRects().length) progressPanel.current.scrollIntoView({block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"});
            });
            setNotice(`Batch contains ${result.total_files} CV(s). ${result.remaining_unparsed} selected CV(s) are outside this batch.`);
            void cache.invalidateQueries({queryKey: ["active-processes"]});
          } catch (e) {setError(message(e));} finally {startLock.current = false; setStarting(false);}
        }}>{parsing ? "Parsing in progress..." : `Parse next ${parseCount} CV${parseCount !== 1 ? "s" : ""}`}</button>
        {!validLimit && <p className="r-inline-error" role="alert">Choose a whole number between 1 and 1000 CVs.</p>}
      </div>}
      {library.isPending ? <p className="r-processing-note" role="status">Loading CV library…</p> : !filtered.length ? <Empty title={trash ? "Trash is empty" : "No CVs found"}>{trash ? "Deleted CVs will appear here for 30 days." : "Import PDF, DOCX or TXT files without starting verification."}</Empty> : <div className="r-table-scroll"><table className="r-table"><thead><tr>
        <th><input type="checkbox" aria-label="Select all matching CVs across every page" disabled={busy} checked={all} ref={node => {if (node) node.indeterminate = !all && filtered.some(cv => ids.includes(cv.id));}} onChange={() => setSelected(all ? selected.filter(id => !filtered.some(cv => cv.id === id)) : [...new Set([...selected, ...filtered.map(cv => cv.id)])])}/></th>
        <th>CV file</th><th>Status</th><th>Size</th><th>{trash ? "Permanently deleted after" : "Added"}</th><th>Actions</th><th><span className="r-sr-only">Preview</span></th>
      </tr></thead><tbody>{visible.map(cv => <tr key={cv.id} className={ids.includes(cv.id) ? "selected" : ""}>
        <td><input type="checkbox" aria-label={`Select ${cv.filename}`} disabled={busy} checked={ids.includes(cv.id)} onChange={() => setSelected(ids.includes(cv.id) ? selected.filter(id => id !== cv.id) : [...selected, cv.id])}/></td>
        <td><strong>{cv.filename}</strong>{!cv.content_hash && <small className="r-muted"> · Existing parsed profile</small>}</td>
        <td><span className={`r-pill ${!trash && candidateId(cv) ? "success" : ""}`}>{trash ? "In Trash" : candidateId(cv) ? "Ready for verification" : fileProgress.get(cv.id)?.status === "PROCESSING" && parsing ? "Processing" : fileProgress.get(cv.id)?.status === "QUEUED" && parsing ? "Queued" : fileProgress.get(cv.id)?.status === "FAILED" ? "Parsing failed" : "Imported · not parsed"}</span>{!trash && parsing && fileProgress.get(cv.id)?.status === "PROCESSING" && <small className="r-library-file-phase">{fileProgress.get(cv.id)?.phase}</small>}</td>
        <td>{cv.size === null ? "Original unavailable" : `${Math.max(1, Math.ceil(cv.size / 1024))} KB`}</td>
        <td>{new Date((trash ? cv.expires_at : cv.created_at)!).toLocaleString()}</td>
        <td><div className="r-library-row-actions"><button className="r-button subtle" disabled={busy} onClick={() => change(trash ? "restore" : "trash", [cv.id])}>{trash ? "Restore" : "Move to Trash"}</button><button className="r-button r-danger" disabled={busy} onClick={() => change("delete", [cv.id])}>{busy && busyAction === "delete" && deletingId === cv.id ? <><LoaderCircle className="r-spinner" size={14}/> Deleting…</> : "Delete permanently"}</button></div></td>
        <td><button className="r-icon-button" aria-label={`View ${cv.filename} ${candidateId(cv) ? "parsed profile" : "original text"}`} onClick={() => setPreview({...cv, candidate_id: candidateId(cv)})}><ChevronRight size={18}/></button></td>
      </tr>)}</tbody></table></div>}
      <div className="r-table-footer"><span>{filtered.length} CV(s) · Page {currentPage + 1} of {Math.max(1, Math.ceil(filtered.length / 25))}</span><div><button className="r-button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><button className="r-button" disabled={(currentPage + 1) * 25 >= filtered.length} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>
    </section>
    {preview && (preview.candidate_id ? <ProfileDialog id={preview.candidate_id} onClose={() => setPreview(null)}/> : <RawCVDialog document={preview} onClose={() => setPreview(null)}/>)}
  </>;
}
