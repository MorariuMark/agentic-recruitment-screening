"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Copy,
  Download,
  FileCode,
  FileText,
  Filter,
  Layers,
  RefreshCw,
  Search,
  Sparkles,
  UserCheck,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { ActionTraceLogEntry, ActionTraceResponse } from "@/types";
import { message } from "./common";
import { ProcessIndicator } from "./process-indicator";

type TabId = "trace" | "actions" | "jd" | "cvs" | "results";

interface LogsDialogProps {
  jobId?: string;
  runId?: string;
  onClose: () => void;
}

export function LogsDialog({ jobId, runId, onClose }: LogsDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [activeTab, setActiveTab] = useState<TabId>("actions");
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>("");
  const [expandedActionIds, setExpandedActionIds] = useState<Set<string>>(new Set());

  const traceQuery = useQuery<ActionTraceResponse>({
    queryKey: ["screening-action-trace", jobId, runId],
    queryFn: () => api.actionTrace(jobId, runId),
    refetchInterval: (query) => {
      const status = query.state.data?.screening_run?.status;
      return status === "ranking" || status === "evaluating" ? 3000 : 15000;
    },
  });

  const data = traceQuery.data;

  useEffect(() => {
    const el = dialog.current;
    if (el && !el.open) {
      try {
        el.showModal();
      } catch {}
    }
    return () => {
      el?.close();
    };
  }, []);

  // Sync candidate selection default
  useEffect(() => {
    if (data?.candidates?.length && !selectedCandidateId) {
      setSelectedCandidateId(data.candidates[0].candidate_id);
    }
  }, [data, selectedCandidateId]);

  const copyToClipboard = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((k) => (k === key ? null : k)), 2000);
    } catch {
      /* Clipboard write may fail without permission */
    }
  };

  const downloadJson = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `screening-trace-${jobId || data.export_metadata?.job_id || "full"}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copyMarkdownSummary = () => {
    if (!data) return;
    const md = buildMarkdownSummary(data);
    copyToClipboard(md, "markdown-summary");
  };

  const toggleExpand = (id: string) => {
    setExpandedActionIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAllActions = () => {
    if (!data?.actions) return;
    setExpandedActionIds(new Set(data.actions.map((a) => a.id)));
  };

  const collapseAllActions = () => {
    setExpandedActionIds(new Set());
  };

  // Filter actions by search query
  const filteredActions = useMemo(() => {
    if (!data?.actions) return [];
    if (!searchQuery.trim()) return data.actions;
    const q = searchQuery.toLowerCase();
    return data.actions.filter((item) => {
      const matchType = item.action_type.toLowerCase().includes(q);
      const matchModel = item.model.toLowerCase().includes(q);
      const matchPrompt = item.prompt.toLowerCase().includes(q);
      const matchRaw = item.raw_response.toLowerCase().includes(q);
      const matchParsed = JSON.stringify(item.parsed_json || {}).toLowerCase().includes(q);
      const matchMeta = JSON.stringify(item.metadata || {}).toLowerCase().includes(q);
      return matchType || matchModel || matchPrompt || matchRaw || matchParsed || matchMeta;
    });
  }, [data?.actions, searchQuery]);

  const selectedCandidate = useMemo(() => {
    if (!data?.candidates?.length) return null;
    return data.candidates.find((c) => c.candidate_id === selectedCandidateId) || data.candidates[0];
  }, [data?.candidates, selectedCandidateId]);

  return (
    <dialog
      ref={dialog}
      className="recruiter r-profile-dialog r-logs-dialog"
      aria-labelledby="logs-dialog-title"
      onClose={() => {
        if (!dialog.current?.open) onClose();
      }}
    >
      <header className="r-logs-header">
        <div>
          <span className="r-muted">Full AI Action Trace & Audit Provenance</span>
          <h2 id="logs-dialog-title">Action logs & AI agent inspector</h2>
        </div>
        <div className="r-logs-header-actions">
          <button
            type="button"
            className="r-action-btn"
            title="Download full trace as JSON"
            onClick={downloadJson}
            disabled={!data}
          >
            <Download size={14} />
            <span>Download JSON</span>
          </button>
          <button
            type="button"
            className="r-action-btn"
            title="Copy prompt-ready Markdown summary for AI agent analysis"
            onClick={copyMarkdownSummary}
            disabled={!data}
          >
            {copiedKey === "markdown-summary" ? <Check size={14} className="r-check-green" /> : <Sparkles size={14} />}
            <span>{copiedKey === "markdown-summary" ? "Copied MD!" : "Copy AI Markdown"}</span>
          </button>
          <button
            type="button"
            className="r-action-btn r-action-btn-primary"
            title="Copy complete JSON trace to clipboard"
            onClick={() => copyToClipboard(JSON.stringify(data || {}, null, 2), "full-json")}
            disabled={!data}
          >
            {copiedKey === "full-json" ? <Check size={14} className="r-check-green" /> : <Copy size={14} />}
            <span>{copiedKey === "full-json" ? "Copied JSON!" : "Copy Full JSON"}</span>
          </button>
          <button
            type="button"
            className="r-icon-button"
            aria-label="Refresh trace data"
            disabled={traceQuery.isFetching}
            onClick={() => void traceQuery.refetch()}
          >
            <RefreshCw size={16} className={traceQuery.isFetching ? "r-spinner" : ""} />
          </button>
          <button type="button" className="r-icon-button" aria-label="Close dialog" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
      </header>

      {/* Summary KPI Strip */}
      {data && (
        <div className="r-logs-kpis">
          <div className="r-logs-kpi">
            <small>Total LLM Actions</small>
            <strong>{data.actions?.length || 0}</strong>
          </div>
          <div className="r-logs-kpi">
            <small>Cohort Candidates</small>
            <strong>{data.candidates?.length || 0}</strong>
          </div>
          <div className="r-logs-kpi">
            <small>Active Provider / Model</small>
            <strong className="r-truncate" title={`${data.export_metadata.active_engine?.provider} / ${data.export_metadata.active_engine?.model}`}>
              {data.export_metadata.active_engine?.provider} · {data.export_metadata.active_engine?.model}
            </strong>
          </div>
          <div className="r-logs-kpi">
            <small>Screening Run Status</small>
            <strong className="r-capitalize">
              {data.screening_run?.status || "Idle"} {data.screening_run?.pipeline_version ? `(${data.screening_run.pipeline_version})` : ""}
            </strong>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <nav className="r-logs-tabs" aria-label="Logs inspection tabs">
        <button
          type="button"
          className={`r-logs-tab ${activeTab === "actions" ? "active" : ""}`}
          onClick={() => setActiveTab("actions")}
        >
          <Code2 size={15} />
          <span>LLM Actions & JSON ({data?.actions?.length || 0})</span>
        </button>
        <button
          type="button"
          className={`r-logs-tab ${activeTab === "jd" ? "active" : ""}`}
          onClick={() => setActiveTab("jd")}
        >
          <FileText size={15} />
          <span>Raw Job Description</span>
        </button>
        <button
          type="button"
          className={`r-logs-tab ${activeTab === "cvs" ? "active" : ""}`}
          onClick={() => setActiveTab("cvs")}
        >
          <UserCheck size={15} />
          <span>Raw Candidate CVs ({data?.candidates?.length || 0})</span>
        </button>
        <button
          type="button"
          className={`r-logs-tab ${activeTab === "results" ? "active" : ""}`}
          onClick={() => setActiveTab("results")}
        >
          <Layers size={15} />
          <span>Screening Results</span>
        </button>
        <button
          type="button"
          className={`r-logs-tab ${activeTab === "trace" ? "active" : ""}`}
          onClick={() => setActiveTab("trace")}
        >
          <FileCode size={15} />
          <span>Full Agent Trace (JSON)</span>
        </button>
      </nav>

      {/* Content Container */}
      <div className="r-profile-content r-logs-content">
        {traceQuery.isPending && (
          <div className="r-logs-loading" role="status">
            <ProcessIndicator active timer={false} label="Loading action trace" />
            <span>Gathering complete action audit, raw documents and LLM JSON outputs…</span>
          </div>
        )}

        {traceQuery.error && (
          <div role="alert" className="r-alert">
            {message(traceQuery.error)}{" "}
            <button type="button" onClick={() => void traceQuery.refetch()}>
              Retry
            </button>
          </div>
        )}

        {data && (
          <>
            {/* TAB 1: LLM Actions & JSON Outputs */}
            {activeTab === "actions" && (
              <section className="r-logs-tab-panel" aria-label="LLM Actions">
                <div className="r-logs-toolbar">
                  <div className="r-logs-search">
                    <Search size={14} />
                    <input
                      type="text"
                      placeholder="Search prompts, models, actions, JSON keys or candidate names…"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                    {searchQuery && (
                      <button type="button" onClick={() => setSearchQuery("")} aria-label="Clear search">
                        <X size={13} />
                      </button>
                    )}
                  </div>
                  <div className="r-logs-toolbar-actions">
                    <button type="button" onClick={expandAllActions} className="r-mini-btn">
                      Expand all
                    </button>
                    <button type="button" onClick={collapseAllActions} className="r-mini-btn">
                      Collapse all
                    </button>
                    <span className="r-logs-count">
                      Showing {filteredActions.length} of {data.actions?.length || 0}
                    </span>
                  </div>
                </div>

                {!filteredActions.length ? (
                  <p className="r-inline-empty">
                    {searchQuery
                      ? "No action logs matched your search filter."
                      : "No LLM actions recorded yet in this session. Once you parse a role, upload CVs, or run candidate screening, all action prompts and JSON responses will appear here."}
                  </p>
                ) : (
                  <div className="r-actions-list">
                    {filteredActions.map((action, idx) => {
                      const isExpanded = expandedActionIds.has(action.id);
                      const actionKey = `action-${action.id}`;
                      const hasJson = action.parsed_json !== null && action.parsed_json !== undefined;

                      return (
                        <div key={action.id} className={`r-action-card ${action.status === "error" ? "error" : ""}`}>
                          <div className="r-action-card-header" onClick={() => toggleExpand(action.id)}>
                            <button
                              type="button"
                              className="r-action-toggle"
                              aria-expanded={isExpanded}
                              aria-label={isExpanded ? "Collapse action card" : "Expand action card"}
                            >
                              {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            </button>
                            <span className="r-action-seq">#{idx + 1}</span>
                            <span className={`r-action-tag r-tag-${action.action_type}`}>{action.action_type}</span>
                            <span className="r-action-model" title={`${action.provider} / ${action.model}`}>
                              {action.provider}/{action.model}
                            </span>
                            <span className="r-action-timing">{action.latency_ms} ms</span>
                            <span className="r-action-tokens">
                              {action.tokens.total.toLocaleString()} tok ({action.tokens.prompt} in / {action.tokens.completion} out)
                            </span>
                            <span className={`r-action-status r-status-${action.status}`}>{action.status}</span>
                            <span className="r-action-time">{action.timestamp ? new Date(action.timestamp).toLocaleTimeString() : "Time unavailable"}</span>
                          </div>

                          {/* Quick summary line when collapsed */}
                          {!isExpanded && (
                            <div className="r-action-collapsed-preview" onClick={() => toggleExpand(action.id)}>
                              {action.metadata?.candidate_name && <span>Candidate: <strong>{action.metadata.candidate_name}</strong></span>}
                              {action.metadata?.requirement_title && <span>Requirement: <strong>{action.metadata.requirement_title}</strong></span>}
                              {action.error && <span className="r-error-text">Error: {action.error}</span>}
                              {!action.error && hasJson && (
                                <span className="r-json-preview">
                                  Output keys: [{Object.keys(action.parsed_json || {}).slice(0, 5).join(", ")}]
                                </span>
                              )}
                            </div>
                          )}

                          {/* Expanded Full Details */}
                          {isExpanded && (
                            <div className="r-action-body">
                              {/* Metadata Strip */}
                              {action.metadata && Object.keys(action.metadata).length > 0 && (
                                <div className="r-action-meta-box">
                                  <strong>Metadata:</strong>
                                  <div className="r-action-meta-pills">
                                    {Object.entries(action.metadata).map(([k, v]) => (
                                      <span key={k}>
                                        <code>{k}</code>: {String(v)}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Error notice if present */}
                              {action.error && (
                                <div className="r-action-error-box">
                                  <strong>Execution Failure:</strong>
                                  <pre>{action.error}</pre>
                                </div>
                              )}

                              {/* Structured JSON Output */}
                              {hasJson && (
                                <div className="r-action-section">
                                  <div className="r-action-section-head">
                                    <h4>Parsed LLM Output (Structured JSON)</h4>
                                    <button
                                      type="button"
                                      className="r-mini-copy"
                                      onClick={() =>
                                        copyToClipboard(JSON.stringify(action.parsed_json, null, 2), `${actionKey}-json`)
                                      }
                                    >
                                      {copiedKey === `${actionKey}-json` ? <Check size={12} /> : <Copy size={12} />}
                                      <span>{copiedKey === `${actionKey}-json` ? "Copied" : "Copy JSON"}</span>
                                    </button>
                                  </div>
                                  <pre className="r-code-block">
                                    <code>{JSON.stringify(action.parsed_json, null, 2)}</code>
                                  </pre>
                                </div>
                              )}

                              {/* Raw Model Response Text */}
                              {action.raw_response && (
                                <div className="r-action-section">
                                  <div className="r-action-section-head">
                                    <h4>Raw LLM Output String</h4>
                                    <button
                                      type="button"
                                      className="r-mini-copy"
                                      onClick={() => copyToClipboard(action.raw_response, `${actionKey}-raw`)}
                                    >
                                      {copiedKey === `${actionKey}-raw` ? <Check size={12} /> : <Copy size={12} />}
                                      <span>{copiedKey === `${actionKey}-raw` ? "Copied" : "Copy Raw"}</span>
                                    </button>
                                  </div>
                                  <pre className="r-code-block r-raw-block">
                                    <code>{action.raw_response}</code>
                                  </pre>
                                </div>
                              )}

                              {/* Input Prompt Context */}
                              <div className="r-action-section">
                                <div className="r-action-section-head">
                                  <h4>Input Prompt Context</h4>
                                  <button
                                    type="button"
                                    className="r-mini-copy"
                                    onClick={() => copyToClipboard(action.prompt, `${actionKey}-prompt`)}
                                  >
                                    {copiedKey === `${actionKey}-prompt` ? <Check size={12} /> : <Copy size={12} />}
                                    <span>{copiedKey === `${actionKey}-prompt` ? "Copied" : "Copy Prompt"}</span>
                                  </button>
                                </div>
                                <pre className="r-code-block r-prompt-block">
                                  <code>{action.prompt}</code>
                                </pre>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            )}

            {/* TAB 2: Raw Job Description */}
            {activeTab === "jd" && (
              <section className="r-logs-tab-panel" aria-label="Job Description">
                {data.job ? (
                  <div className="r-jd-viewer">
                    <div className="r-jd-meta-grid">
                      <div>
                        <small>Role Title</small>
                        <strong>{data.job.title}</strong>
                      </div>
                      <div>
                        <small>Department</small>
                        <strong>{data.job.department || "—"}</strong>
                      </div>
                      <div>
                        <small>Location & Work Model</small>
                        <strong>
                          {data.job.location || "—"} {data.job.work_model ? `(${data.job.work_model})` : ""}
                        </strong>
                      </div>
                      <div>
                        <small>Job ID</small>
                        <code>{data.job.id}</code>
                      </div>
                    </div>

                    <div className="r-action-section">
                      <div className="r-action-section-head">
                        <h4>Raw Job Description Text (Source Document)</h4>
                        <button
                          type="button"
                          className="r-mini-copy"
                          onClick={() => copyToClipboard(data.job?.raw_text || "", "jd-raw")}
                        >
                          {copiedKey === "jd-raw" ? <Check size={12} /> : <Copy size={12} />}
                          <span>{copiedKey === "jd-raw" ? "Copied" : "Copy Raw JD"}</span>
                        </button>
                      </div>
                      <pre className="r-code-block r-document-block">
                        <code>{data.job.raw_text || "No raw text stored for this job requisition."}</code>
                      </pre>
                    </div>

                    {/* Atomic Criteria Table */}
                    <div className="r-action-section">
                      <div className="r-action-section-head">
                        <h4>Decomposed Atomic Criteria ({data.job.requirements?.length || 0})</h4>
                        <button
                          type="button"
                          className="r-mini-copy"
                          onClick={() =>
                            copyToClipboard(JSON.stringify(data.job?.requirements || [], null, 2), "jd-reqs")
                          }
                        >
                          {copiedKey === "jd-reqs" ? <Check size={12} /> : <Copy size={12} />}
                          <span>{copiedKey === "jd-reqs" ? "Copied" : "Copy Criteria JSON"}</span>
                        </button>
                      </div>
                      <div className="r-table-wrap">
                        <table className="r-table">
                          <thead>
                            <tr>
                              <th>ID</th>
                              <th>Title & Description</th>
                              <th>Category</th>
                              <th>Weight</th>
                              <th>Min Years</th>
                            </tr>
                          </thead>
                          <tbody>
                            {data.job.requirements?.map((req) => (
                              <tr key={req.id}>
                                <td>
                                  <code>{req.id}</code>
                                </td>
                                <td>
                                  <strong>{req.title}</strong>
                                  <p className="r-table-desc">{req.description}</p>
                                </td>
                                <td>
                                  <span className={`r-pill-cat r-cat-${req.category}`}>{req.category}</span>
                                </td>
                                <td>{req.weight}</td>
                                <td>{req.minimum_years_experience ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="r-inline-empty">No active job requisition associated with this trace.</p>
                )}
              </section>
            )}

            {/* TAB 3: Raw Candidate CVs */}
            {activeTab === "cvs" && (
              <section className="r-logs-tab-panel" aria-label="Candidate CVs">
                {!data.candidates?.length ? (
                  <p className="r-inline-empty">No candidate records stored in this cohort.</p>
                ) : (
                  <div className="r-candidate-viewer">
                    {/* Selector */}
                    <div className="r-candidate-selector">
                      <label htmlFor="trace-cand-select">Select Candidate:</label>
                      <select
                        id="trace-cand-select"
                        value={selectedCandidate?.candidate_id || ""}
                        onChange={(e) => setSelectedCandidateId(e.target.value)}
                      >
                        {data.candidates.map((c) => (
                          <option key={c.candidate_id} value={c.candidate_id}>
                            {c.candidate_name} ({c.original_filename || c.candidate_id.slice(0, 8)})
                          </option>
                        ))}
                      </select>
                      <span className="r-muted">
                        Candidate ID: <code>{selectedCandidate?.candidate_id}</code>
                      </span>
                    </div>

                    {selectedCandidate && (
                      <div className="r-cand-detail-blocks">
                        {/* Candidate Metadata Strip */}
                        <div className="r-jd-meta-grid">
                          <div>
                            <small>Candidate Name</small>
                            <strong>{selectedCandidate.candidate_name}</strong>
                          </div>
                          <div>
                            <small>Original File</small>
                            <strong>{selectedCandidate.original_filename || "Direct Input"}</strong>
                          </div>
                          <div>
                            <small>Raw CV Length</small>
                            <strong>{selectedCandidate.raw_cv_text?.length || 0} characters</strong>
                          </div>
                          <div>
                            <small>Sanitized Text Length</small>
                            <strong>{selectedCandidate.sanitized_text?.length || 0} characters</strong>
                          </div>
                        </div>

                        {/* Raw CV Text */}
                        <div className="r-action-section">
                          <div className="r-action-section-head">
                            <h4>Original Raw CV Text (Full Unparsed Content)</h4>
                            <button
                              type="button"
                              className="r-mini-copy"
                              onClick={() => copyToClipboard(selectedCandidate.raw_cv_text || "", "cv-raw")}
                            >
                              {copiedKey === "cv-raw" ? <Check size={12} /> : <Copy size={12} />}
                              <span>{copiedKey === "cv-raw" ? "Copied" : "Copy Raw CV"}</span>
                            </button>
                          </div>
                          <pre className="r-code-block r-document-block">
                            <code>{selectedCandidate.raw_cv_text || "No raw CV text recorded."}</code>
                          </pre>
                        </div>

                        {/* Sanitized Text */}
                        <div className="r-action-section">
                          <div className="r-action-section-head">
                            <h4>PII-Scrubbed Sanitized Text (LLM & Embedding Input)</h4>
                            <button
                              type="button"
                              className="r-mini-copy"
                              onClick={() => copyToClipboard(selectedCandidate.sanitized_text || "", "cv-sanitized")}
                            >
                              {copiedKey === "cv-sanitized" ? <Check size={12} /> : <Copy size={12} />}
                              <span>{copiedKey === "cv-sanitized" ? "Copied" : "Copy Sanitized"}</span>
                            </button>
                          </div>
                          <pre className="r-code-block r-document-block">
                            <code>{selectedCandidate.sanitized_text || "No sanitized text recorded."}</code>
                          </pre>
                        </div>

                        {/* Structured Parsed Profile JSON */}
                        <div className="r-action-section">
                          <div className="r-action-section-head">
                            <h4>Anonymized Candidate Profile (Structured JSON)</h4>
                            <button
                              type="button"
                              className="r-mini-copy"
                              onClick={() =>
                                copyToClipboard(
                                  JSON.stringify(selectedCandidate.anonymized_profile || {}, null, 2),
                                  "cv-anon-json"
                                )
                              }
                            >
                              {copiedKey === "cv-anon-json" ? <Check size={12} /> : <Copy size={12} />}
                              <span>{copiedKey === "cv-anon-json" ? "Copied" : "Copy Profile JSON"}</span>
                            </button>
                          </div>
                          <pre className="r-code-block">
                            <code>{JSON.stringify(selectedCandidate.anonymized_profile || {}, null, 2)}</code>
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

            {/* TAB 4: Screening Run Results */}
            {activeTab === "results" && (
              <section className="r-logs-tab-panel" aria-label="Screening Results">
                {!data.screening_run ? (
                  <p className="r-inline-empty">No screening run recorded yet for this role.</p>
                ) : (
                  <div className="r-results-viewer">
                    {/* Run Diagnostics Grid */}
                    <div className="r-jd-meta-grid">
                      <div>
                        <small>Run ID</small>
                        <code>{data.screening_run.id}</code>
                      </div>
                      <div>
                        <small>Pipeline Version</small>
                        <strong>{data.screening_run.pipeline_version || "v1"}</strong>
                      </div>
                      <div>
                        <small>Status & Phase</small>
                        <strong>
                          {data.screening_run.status} — {data.screening_run.phase || "—"}
                        </strong>
                      </div>
                      <div>
                        <small>Ranked Candidates</small>
                        <strong>{data.screening_run.rows?.length || 0}</strong>
                      </div>
                    </div>

                    {/* Pre-Screen Rankings */}
                    <div className="r-action-section">
                      <div className="r-action-section-head">
                        <h4>Pre-Screen & Hybrid Rankings</h4>
                        <button
                          type="button"
                          className="r-mini-copy"
                          onClick={() => copyToClipboard(JSON.stringify(data.screening_run.rows || [], null, 2), "rows-json")}
                        >
                          {copiedKey === "rows-json" ? <Check size={12} /> : <Copy size={12} />}
                          <span>{copiedKey === "rows-json" ? "Copied" : "Copy Table JSON"}</span>
                        </button>
                      </div>
                      <div className="r-table-wrap">
                        <table className="r-table">
                          <thead>
                            <tr>
                              <th>Rank</th>
                              <th>Candidate ID</th>
                              <th>Pre-Screen Score</th>
                              <th>Rerank Score</th>
                              <th>Deep Eval Status</th>
                              <th>Overall Deep Score</th>
                            </tr>
                          </thead>
                          <tbody>
                            {data.screening_run.rows?.map((row: any) => (
                              <tr key={row.candidate_id}>
                                <td>#{row.rank}</td>
                                <td>
                                  <code>{row.candidate_id}</code>
                                </td>
                                <td>{Math.round((row.pre_screen_score || 0) * 100)}%</td>
                                <td>{row.rerank_score != null ? `${Math.round(row.rerank_score * 100)}%` : "—"}</td>
                                <td>
                                  <span className={`r-pill-deep r-deep-${row.deep_status}`}>{row.deep_status}</span>
                                </td>
                                <td>
                                  {row.deep_evaluation
                                    ? `${Math.round((row.deep_evaluation.overall_score || 0) * 100)}%`
                                    : "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Deep Evaluation Breakdowns */}
                    <div className="r-action-section">
                      <div className="r-action-section-head">
                        <h4>Deep Evaluations & Grounded Citations</h4>
                      </div>
                      {data.screening_run.rows
                        ?.filter((r: any) => r.deep_evaluation)
                        .map((r: any) => (
                          <div key={r.candidate_id} className="r-deep-eval-card">
                            <div className="r-deep-eval-header">
                              <div>
                                <strong>Candidate ID: {r.candidate_id}</strong>
                                <span className="r-score-badge">
                                  Overall: {Math.round(r.deep_evaluation.overall_score * 100)}% | Must-have:{" "}
                                  {Math.round(r.deep_evaluation.must_have_score * 100)}% | Citation Verif:{" "}
                                  {Math.round((r.deep_evaluation.citation_verification_score ?? 1.0) * 100)}%
                                </span>
                              </div>
                              <span className={`r-pill-rec r-rec-${r.deep_evaluation.recommendation}`}>
                                {r.deep_evaluation.recommendation}
                              </span>
                            </div>

                            <div className="r-deep-matches-list">
                              {r.deep_evaluation.matches?.map((m: any, mIdx: number) => (
                                <div key={m.requirement_id || mIdx} className="r-match-item">
                                  <div className="r-match-item-head">
                                    <span className="r-match-title">
                                      <code>{m.requirement_id}</code> — {m.title}
                                    </span>
                                    <span className={`r-match-status r-match-${m.status}`}>{m.status}</span>
                                    <span className="r-match-score">{Math.round((m.score || 0) * 100)}%</span>
                                  </div>
                                  <p className="r-match-reasoning">
                                    <strong>Reasoning:</strong> {m.reasoning}
                                  </p>
                                  {m.citations?.length > 0 && (
                                    <div className="r-match-citations">
                                      <strong>Citations (verbatim CV quotes):</strong>
                                      <ul>
                                        {m.citations.map((cit: string, cIdx: number) => (
                                          <li key={cIdx}>&ldquo;{cit}&rdquo;</li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}
                                  {m.gap_analysis && (
                                    <p className="r-match-gap">
                                      <strong>Gap Analysis:</strong> {m.gap_analysis}
                                    </p>
                                  )}
                                  {m.clarification_question && (
                                    <p className="r-match-clarification">
                                      <strong>Recruiter Probe:</strong> {m.clarification_question}
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </section>
            )}

            {/* TAB 5: Full AI Agent Trace (JSON) */}
            {activeTab === "trace" && (
              <section className="r-logs-tab-panel" aria-label="Full AI Agent Trace JSON">
                <div className="r-action-section">
                  <div className="r-action-section-head">
                    <h4>Complete AI Agent Machine-Readable Audit Envelope (JSON)</h4>
                    <div className="r-action-section-actions">
                      <button
                        type="button"
                        className="r-mini-copy"
                        onClick={() => copyToClipboard(JSON.stringify(data, null, 2), "trace-json-tab")}
                      >
                        {copiedKey === "trace-json-tab" ? <Check size={12} /> : <Copy size={12} />}
                        <span>{copiedKey === "trace-json-tab" ? "Copied" : "Copy Trace"}</span>
                      </button>
                      <button type="button" className="r-mini-copy" onClick={downloadJson}>
                        <Download size={12} />
                        <span>Download</span>
                      </button>
                    </div>
                  </div>
                  <pre className="r-code-block r-full-trace-block">
                    <code>{JSON.stringify(data, null, 2)}</code>
                  </pre>
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </dialog>
  );
}

/**
 * Builds an AI-agent prompt-ready Markdown document consolidating the full session trace.
 */
function buildMarkdownSummary(trace: ActionTraceResponse): string {
  const meta = trace.export_metadata;
  const job = trace.job;
  const candidates = trace.candidates || [];
  const actions = trace.actions || [];
  const run = trace.screening_run;

  const lines: string[] = [
    `# ATOS Screening AI Agent Audit Dossier`,
    `Generated at: ${meta.generated_at}`,
    `Schema Version: ${meta.schema_version}`,
    `Active Engine: ${meta.active_engine?.provider} / ${meta.active_engine?.model} (Failover: ${meta.active_engine?.fallback_enabled})`,
    ``,
    `---`,
    `## 1. Job Requisition`,
    `**Title:** ${job?.title || "Unknown"}`,
    `**Department:** ${job?.department || "N/A"}`,
    `**Location:** ${job?.location || "N/A"} (${job?.work_model || "N/A"})`,
    `**Job ID:** ${job?.id || "N/A"}`,
    ``,
    `### Raw Job Description:`,
    `\`\`\``,
    job?.raw_text || "No raw text available.",
    `\`\`\``,
    ``,
    `### Atomic Criteria:`,
  ];

  for (const r of job?.requirements || []) {
    lines.push(
      `- **[${r.id}] ${r.title}** (${r.category}, weight: ${r.weight}, min years: ${r.minimum_years_experience ?? "N/A"}): ${r.description}`
    );
  }

  lines.push(``, `---`, `## 2. Candidates in Cohort (${candidates.length})`);
  for (const c of candidates) {
    lines.push(
      `### Candidate: ${c.candidate_name} (ID: ${c.candidate_id})`,
      `File: ${c.original_filename || "N/A"}`,
      `#### Raw CV Text:`,
      `\`\`\``,
      c.raw_cv_text || "No raw CV text.",
      `\`\`\``,
      `#### Sanitized Text:`,
      `\`\`\``,
      c.sanitized_text || "No sanitized text.",
      `\`\`\``,
      ``
    );
  }

  lines.push(`---`, `## 3. LLM Action Logs & JSON Outputs (${actions.length})`);
  for (const [idx, a] of actions.entries()) {
    lines.push(
      `### Action #${idx + 1}: ${a.action_type} [${a.status.toUpperCase()}]`,
      `- Timestamp: ${a.timestamp}`,
      `- Provider/Model: ${a.provider} / ${a.model}`,
      `- Latency: ${a.latency_ms} ms | Tokens: ${a.tokens.total} (${a.tokens.prompt} prompt / ${a.tokens.completion} completion)`,
      `- Metadata: ${JSON.stringify(a.metadata || {})}`,
      ``,
      `#### Input Prompt:`,
      `\`\`\``,
      a.prompt,
      `\`\`\``,
      ``,
      `#### Parsed JSON Output:`,
      `\`\`\`json`,
      JSON.stringify(a.parsed_json || a.raw_response, null, 2),
      `\`\`\``,
      ``
    );
  }

  if (run) {
    lines.push(
      `---`,
      `## 4. Screening Run Results`,
      `**Run ID:** ${run.id}`,
      `**Pipeline:** ${run.pipeline_version || "v1"}`,
      `**Status:** ${run.status} (${run.phase || "—"})`,
      ``,
      `### Candidate Rankings & Evaluations:`
    );
    for (const row of run.rows || []) {
      lines.push(
        `- **Rank #${row.rank} — Candidate ${row.candidate_id}**: Pre-Screen Score: ${Math.round((row.pre_screen_score || 0) * 100)}%, Deep Status: ${row.deep_status}`
      );
      if (row.deep_evaluation) {
        lines.push(
          `  - Overall: ${Math.round(row.deep_evaluation.overall_score * 100)}% | Recommendation: ${row.deep_evaluation.recommendation} | Citation Verification: ${Math.round((row.deep_evaluation.citation_verification_score ?? 1.0) * 100)}%`
        );
        for (const m of row.deep_evaluation.matches || []) {
          lines.push(
            `    - [${m.requirement_id}] ${m.title}: status=${m.status}, score=${Math.round((m.score || 0) * 100)}%`,
            `      Reasoning: ${m.reasoning}`,
            `      Citations: ${JSON.stringify(m.citations || [])}`
          );
        }
      }
    }
  }

  return lines.join("\n");
}
