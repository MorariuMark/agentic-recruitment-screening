"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Activity,
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  Cpu,
  Filter,
  Layers,
  Pause,
  Play,
  RefreshCw,
  Search,
  Sparkles,
  Terminal,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { api, LiveLLMInFlightEntry, LiveLLMRecentEntry, LiveLLMState } from "@/lib/api";

interface LiveLLMDebugModalProps {
  open: boolean;
  onClose: () => void;
  onOpenLocalControls?: () => void;
}

type TabType = "prompt" | "response" | "tokens" | "parsed" | "system";

export function LiveLLMDebugModal({ open, onClose, onOpenLocalControls }: LiveLLMDebugModalProps) {
  const [data, setData] = useState<LiveLLMState>({ in_flight: [], recent: [], total_logged: 0 });
  const [isPolling, setIsPolling] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedProvider, setSelectedProvider] = useState<string>("all");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [activeTabs, setActiveTabs] = useState<Record<string, TabType>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Fetch telemetry
  const fetchLogs = async () => {
    try {
      const state = await api.getLiveLLMLogs(100);
      setData(state);
      // Auto-expand any currently in-flight requests
      if (state.in_flight.length > 0) {
        setExpandedIds((prev) => {
          const next = new Set(prev);
          state.in_flight.forEach((f) => next.add(f.id));
          return next;
        });
      }
    } catch (err) {
      console.warn("Failed fetching live LLM logs:", err);
    }
  };

  // Polling loop when open & polling enabled
  useEffect(() => {
    if (!open) return;
    setIsLoading(true);
    fetchLogs().finally(() => setIsLoading(false));

    if (!isPolling) return;
    const interval = setInterval(fetchLogs, 1500);
    return () => clearInterval(interval);
  }, [open, isPolling]);

  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  const handleClear = async () => {
    try {
      await api.clearLiveLLMLogs();
      setData({ in_flight: [], recent: [], total_logged: 0 });
      setExpandedIds(new Set());
    } catch (err) {
      console.error("Failed clearing logs:", err);
    }
  };

  const copyToClipboard = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((k) => (k === key ? null : k)), 2000);
    } catch {
      /* clipboard write fail */
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const getActiveTab = (id: string): TabType => activeTabs[id] || "prompt";
  const setActiveTab = (id: string, tab: TabType) => {
    setActiveTabs((prev) => ({ ...prev, [id]: tab }));
  };

  // Extract distinct providers for filter dropdown
  const availableProviders = useMemo(() => {
    const set = new Set<string>();
    data.in_flight.forEach((item) => set.add(item.provider));
    data.recent.forEach((item) => set.add(item.provider));
    return Array.from(set).sort();
  }, [data]);

  // Filtered recent actions
  const filteredRecent = useMemo(() => {
    return data.recent.filter((item) => {
      if (selectedProvider !== "all" && item.provider !== selectedProvider) return false;
      if (selectedStatus !== "all" && item.status !== selectedStatus) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesAction = item.action_type.toLowerCase().includes(q);
        const matchesModel = item.model.toLowerCase().includes(q);
        const matchesPrompt = item.prompt.toLowerCase().includes(q);
        const matchesResp = (item.raw_response || "").toLowerCase().includes(q);
        const matchesErr = (item.error || "").toLowerCase().includes(q);
        if (!matchesAction && !matchesModel && !matchesPrompt && !matchesResp && !matchesErr) {
          return false;
        }
      }
      return true;
    });
  }, [data.recent, selectedProvider, selectedStatus, searchQuery]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="flex flex-col w-full max-w-6xl h-[92vh] rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-slate-100">In-App LLM Console & Engine Inspector</h2>
                {data.in_flight.length > 0 ? (
                  <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono font-medium animate-pulse">
                    <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                    {data.in_flight.length} In-Flight
                  </span>
                ) : (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 text-xs font-mono">
                    Idle
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400">
                Real-time monitoring of LLM providers, active models, input prompts, output completions, token costs, and failover errors
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {onOpenLocalControls && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenLocalControls();
                }}
                className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-300 hover:bg-purple-500/20 text-xs font-mono font-medium transition-colors cursor-pointer"
                title="Manage Local GPU Models (Load / Unload in VRAM)"
              >
                <Cpu className="w-3.5 h-3.5 text-purple-400" />
                <span>Local GPU Models</span>
              </button>
            )}

            <button
              onClick={() => setIsPolling(!isPolling)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer ${
                isPolling
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20"
                  : "bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-750"
              }`}
              title={isPolling ? "Pause real-time updates" : "Resume real-time updates"}
            >
              {isPolling ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              <span>{isPolling ? "Live (1.5s)" : "Paused"}</span>
            </button>

            <button
              onClick={fetchLogs}
              disabled={isLoading}
              className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-750 transition-colors cursor-pointer disabled:opacity-50"
              title="Refresh now"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin text-blue-400" : ""}`} />
            </button>

            <button
              onClick={handleClear}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-rose-300 hover:bg-rose-500/10 hover:border-rose-500/30 text-xs font-medium transition-colors cursor-pointer"
              title="Clear log history"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Clear</span>
            </button>

            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-750 transition-colors cursor-pointer"
              title="Close modal (Esc)"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-2.5 border-b border-slate-800 bg-slate-900/60 text-xs">
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative w-full">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                placeholder="Filter by prompt, response, model, or error..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/50"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Provider Filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Provider:</span>
              <select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value)}
                className="px-2.5 py-1 rounded-md bg-slate-950 border border-slate-800 text-slate-300 focus:outline-none focus:border-blue-500/50 cursor-pointer"
              >
                <option value="all">All Providers</option>
                {availableProviders.map((p) => (
                  <option key={p} value={p}>
                    {p.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            {/* Status Filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Status:</span>
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="px-2.5 py-1 rounded-md bg-slate-950 border border-slate-800 text-slate-300 focus:outline-none focus:border-blue-500/50 cursor-pointer"
              >
                <option value="all">All Statuses</option>
                <option value="success">Success</option>
                <option value="failover">Failover</option>
                <option value="error">Error</option>
              </select>
            </div>

            <span className="text-slate-500 font-mono">
              Showing {filteredRecent.length} of {data.total_logged}
            </span>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* Active / In-Flight LLM Calls */}
          {data.in_flight.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-amber-400">
                <Cpu className="w-4 h-4 animate-spin text-amber-400" />
                <span>Currently Active GPU / Inference In-Flight ({data.in_flight.length})</span>
              </div>

              {data.in_flight.map((flight) => {
                const isExpanded = expandedIds.has(flight.id);
                const activeTab = getActiveTab(flight.id);

                return (
                  <div
                    key={flight.id}
                    className="rounded-xl border-2 border-amber-500/40 bg-amber-950/10 overflow-hidden shadow-lg shadow-amber-950/20"
                  >
                    <div
                      onClick={() => toggleExpand(flight.id)}
                      className="flex items-center justify-between p-4 cursor-pointer hover:bg-amber-500/5 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className="relative flex h-3 w-3">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm text-slate-100 font-mono">
                              {flight.provider.toUpperCase()} / {flight.model}
                            </span>
                            <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-amber-500/20 text-amber-300 border border-amber-500/30">
                              {flight.action_type}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5">
                            <span>Started {new Date(flight.timestamp).toLocaleTimeString()}</span>
                            <span>•</span>
                            <span className="font-mono text-amber-300">
                              ~{(flight.prompt_tokens || Math.round(flight.prompt.length / 4)).toLocaleString()} prompt tokens
                            </span>
                            <span>•</span>
                            <span className="font-mono text-emerald-400">16k Context Window</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 font-mono text-xs font-semibold">
                          <Clock className="w-3.5 h-3.5 animate-spin" />
                          <span>{flight.elapsed_seconds}s elapsed</span>
                        </div>
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4 text-slate-400" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-slate-400" />
                        )}
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-amber-500/20 bg-slate-950/90 p-4">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex gap-2">
                            <button
                              onClick={() => setActiveTab(flight.id, "prompt")}
                              className={`px-3 py-1 rounded text-xs font-medium cursor-pointer ${
                                activeTab === "prompt"
                                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                  : "text-slate-400 hover:text-slate-200"
                              }`}
                            >
                              Live Prompt Input ({flight.prompt.length} chars)
                            </button>
                            {flight.system_prompt && (
                              <button
                                onClick={() => setActiveTab(flight.id, "system")}
                                className={`px-3 py-1 rounded text-xs font-medium cursor-pointer ${
                                  activeTab === "system"
                                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                    : "text-slate-400 hover:text-slate-200"
                                }`}
                              >
                                System Prompt
                              </button>
                            )}
                          </div>

                          <button
                            onClick={() =>
                              copyToClipboard(
                                activeTab === "system" ? flight.system_prompt || "" : flight.prompt,
                                `flight-${flight.id}`
                              )
                            }
                            className="flex items-center gap-1 text-xs text-slate-400 hover:text-amber-300 transition-colors"
                          >
                            {copiedKey === `flight-${flight.id}` ? (
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                            <span>{copiedKey === `flight-${flight.id}` ? "Copied" : "Copy"}</span>
                          </button>
                        </div>

                        <div className="rounded-lg bg-slate-900 border border-slate-800 p-3 max-h-80 overflow-y-auto">
                          <pre className="font-mono text-xs text-slate-300 whitespace-pre-wrap break-words">
                            {activeTab === "system" ? flight.system_prompt : flight.prompt}
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Completed Action History */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                <Layers className="w-4 h-4 text-blue-400" />
                <span>Execution History ({filteredRecent.length})</span>
              </div>
            </div>

            {filteredRecent.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center text-slate-500 rounded-xl border border-slate-800 bg-slate-950/40">
                <Terminal className="w-10 h-10 mb-3 text-slate-600" />
                <p className="text-sm font-medium text-slate-400">No matching LLM actions recorded yet</p>
                <p className="text-xs text-slate-500 mt-1">
                  Run a job parse, CV upload, or candidate screening to see live prompts and outputs.
                </p>
              </div>
            ) : (
              filteredRecent.map((item) => {
                const isExpanded = expandedIds.has(item.id);
                const activeTab = getActiveTab(item.id);
                const isError = item.status === "error";
                const isFailover = item.status === "failover";

                return (
                  <div
                    key={item.id}
                    className={`rounded-xl border transition-all overflow-hidden ${
                      isError
                        ? "border-rose-500/40 bg-rose-950/10"
                        : isFailover
                        ? "border-amber-500/30 bg-amber-950/10"
                        : "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                    }`}
                  >
                    {/* Header Row */}
                    <div
                      onClick={() => toggleExpand(item.id)}
                      className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-800/30 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        {isError ? (
                          <div className="p-1 rounded bg-rose-500/20 text-rose-400">
                            <AlertCircle className="w-4 h-4" />
                          </div>
                        ) : isFailover ? (
                          <div className="p-1 rounded bg-amber-500/20 text-amber-400">
                            <Zap className="w-4 h-4" />
                          </div>
                        ) : (
                          <div className="p-1 rounded bg-emerald-500/20 text-emerald-400">
                            <Check className="w-4 h-4" />
                          </div>
                        )}

                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm text-slate-200 font-mono">
                              {item.provider.toUpperCase()} / {item.model}
                            </span>
                            <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300">
                              {item.action_type}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium uppercase ${
                                isError
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : isFailover
                                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                  : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              }`}
                            >
                              {item.status}
                            </span>
                          </div>

                          <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                            <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                            <span>•</span>
                            <span className="font-mono text-slate-300">
                              {(item.latency_ms / 1000).toFixed(2)}s
                            </span>
                            {item.tokens && item.tokens.total > 0 && (
                              <>
                                <span>•</span>
                                <span className="font-mono text-slate-300">
                                  {item.tokens.total.toLocaleString()} tokens ({item.tokens.prompt} in / {item.tokens.completion} out)
                                </span>
                                {(item.tokens_per_second || item.tokens.tokens_per_second) ? (
                                  <>
                                    <span>•</span>
                                    <span className="font-mono text-emerald-400 font-semibold">
                                      ⚡ {(item.tokens_per_second || item.tokens.tokens_per_second)?.toFixed(1)} tok/s
                                    </span>
                                  </>
                                ) : null}
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4 text-slate-400" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-slate-400" />
                        )}
                      </div>
                    </div>

                    {/* Error Banner if any */}
                    {item.error && (
                      <div className="px-4 py-2 border-t border-rose-500/20 bg-rose-950/30 text-rose-300 text-xs font-mono break-words">
                        <strong>Error:</strong> {item.error}
                      </div>
                    )}

                    {/* Expanded Detail Tabs */}
                    {isExpanded && (
                      <div className="border-t border-slate-800 bg-slate-950 p-4">
                        <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
                          <div className="flex gap-2">
                            <button
                              onClick={() => setActiveTab(item.id, "prompt")}
                              className={`px-3 py-1 rounded text-xs font-medium cursor-pointer transition-colors ${
                                activeTab === "prompt"
                                  ? "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                                  : "text-slate-400 hover:text-slate-200"
                              }`}
                            >
                              Prompt Input ({item.prompt.length.toLocaleString()} chars)
                            </button>

                            <button
                              onClick={() => setActiveTab(item.id, "response")}
                              className={`px-3 py-1 rounded text-xs font-medium cursor-pointer transition-colors ${
                                activeTab === "response"
                                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                                  : "text-slate-400 hover:text-slate-200"
                              }`}
                            >
                              Raw Model Output ({(item.raw_response || "").length.toLocaleString()} chars)
                            </button>

                            <button
                              onClick={() => setActiveTab(item.id, "tokens")}
                              className={`px-3 py-1 rounded text-xs font-medium cursor-pointer transition-colors ${
                                activeTab === "tokens"
                                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                  : "text-slate-400 hover:text-slate-200"
                              }`}
                            >
                              ⚡ Token Breakdown &amp; Speed
                            </button>

                            {item.parsed_json && (
                              <button
                                onClick={() => setActiveTab(item.id, "parsed")}
                                className={`px-3 py-1 rounded text-xs font-medium cursor-pointer transition-colors ${
                                  activeTab === "parsed"
                                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                    : "text-slate-400 hover:text-slate-200"
                                }`}
                              >
                                Parsed JSON Payload
                              </button>
                            )}

                            {item.system_prompt && (
                              <button
                                onClick={() => setActiveTab(item.id, "system")}
                                className={`px-3 py-1 rounded text-xs font-medium cursor-pointer transition-colors ${
                                  activeTab === "system"
                                    ? "bg-slate-700 text-slate-200 border border-slate-600"
                                    : "text-slate-400 hover:text-slate-200"
                                }`}
                              >
                                System Prompt
                              </button>
                            )}
                          </div>

                          {/* Quick copy of active tab */}
                          <button
                            onClick={() => {
                              let copyText = item.prompt;
                              if (activeTab === "response") copyText = item.raw_response || "";
                              else if (activeTab === "parsed")
                                copyText = JSON.stringify(item.parsed_json, null, 2);
                              else if (activeTab === "system") copyText = item.system_prompt || "";
                              copyToClipboard(copyText, `${item.id}-${activeTab}`);
                            }}
                            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-xs text-slate-400 hover:text-slate-200 hover:border-slate-700 transition-colors cursor-pointer"
                          >
                            {copiedKey === `${item.id}-${activeTab}` ? (
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                            <span>
                              {copiedKey === `${item.id}-${activeTab}` ? "Copied" : "Copy Tab"}
                            </span>
                          </button>
                        </div>

                        {/* Tab Content Display */}
                        <div className="rounded-lg bg-slate-900 border border-slate-800 p-4 max-h-96 overflow-y-auto">
                          {activeTab === "prompt" && (
                            <pre className="font-mono text-xs text-slate-300 whitespace-pre-wrap break-words leading-relaxed select-text">
                              {item.prompt}
                            </pre>
                          )}

                          {activeTab === "response" && (
                            item.raw_response ? (
                              <pre className="font-mono text-xs text-purple-200 whitespace-pre-wrap break-words leading-relaxed select-text">
                                {item.raw_response}
                              </pre>
                            ) : (
                              <div className="text-xs text-slate-500 italic">
                                {isError
                                  ? "No raw completion returned (client failed prior to receiving tokens, or model crashed)."
                                  : "Empty response body."}
                              </div>
                            )
                          )}

                          {activeTab === "parsed" && (
                            <pre className="font-mono text-xs text-emerald-300 whitespace-pre-wrap break-words leading-relaxed select-text">
                              {JSON.stringify(item.parsed_json, null, 2)}
                            </pre>
                          )}

                          {activeTab === "system" && (
                            <pre className="font-mono text-xs text-slate-400 whitespace-pre-wrap break-words leading-relaxed select-text">
                              {item.system_prompt || "No system prompt specified."}
                            </pre>
                          )}
                        </div>

                        {/* Metadata row */}
                        {item.metadata && Object.keys(item.metadata).length > 0 && (
                          <div className="mt-2.5 flex flex-wrap gap-2 text-[11px] font-mono text-slate-500">
                            {Object.entries(item.metadata).map(([k, v]) => (
                              <span key={k} className="px-2 py-0.5 rounded bg-slate-900 border border-slate-850">
                                {k}: {JSON.stringify(v)}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-slate-800 bg-slate-950/80 text-xs text-slate-500">
          <div className="flex items-center gap-4">
            <span>Buffer capacity: 500 actions</span>
            <span>•</span>
            <span>Real-time polling: {isPolling ? "1.5s active" : "Paused"}</span>
          </div>

          <div className="flex items-center gap-2">
            <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 font-mono text-[10px] text-slate-400">
              Esc
            </kbd>
            <span>to close</span>
          </div>
        </div>
      </div>
    </div>
  );
}
