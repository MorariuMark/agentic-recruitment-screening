"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Activity,
  AlertCircle,
  Check,
  CheckCircle2,
  Cpu,
  HardDrive,
  Info,
  Layers,
  Power,
  RefreshCw,
  Server,
  Sliders,
  Sparkles,
  Terminal,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import {
  api,
  LocalModelFullState,
  LocalEngineStatus,
  LocalCatalogModel,
} from "@/lib/api";

interface LocalModelControlProps {
  open: boolean;
  onClose: () => void;
  onOpenDebugModal?: () => void;
}

export function LocalModelControl({
  open,
  onClose,
  onOpenDebugModal,
}: LocalModelControlProps) {
  const [state, setState] = useState<LocalModelFullState | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<"lmstudio" | "ollama">("lmstudio");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [selectedContext, setSelectedContext] = useState<number>(0); // 0 = Auto-tune
  const [offloadMode, setOffloadMode] = useState<"auto" | "max" | "off">("auto");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isUnloading, setIsUnloading] = useState<boolean>(false);
  const [isStartingServer, setIsStartingServer] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<{ text: string; type: "success" | "error" | "info" } | null>(null);

  const fetchStatus = async () => {
    try {
      const fullState = await api.getLocalModelsStatus();
      setState(fullState);

      const currentEngine = selectedProvider === "lmstudio" ? fullState.lmstudio : fullState.ollama;
      if (!selectedModel && currentEngine?.models?.length > 0) {
        const preferred = currentEngine.loaded_models?.[0]?.model || currentEngine.models[0].id;
        setSelectedModel(preferred);
      }
    } catch (err) {
      console.warn("Failed fetching local models status:", err);
    }
  };

  useEffect(() => {
    if (!open) return;
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, [open, selectedProvider]);

  // Update selectedModel when provider changes
  useEffect(() => {
    if (!state) return;
    const engine = selectedProvider === "lmstudio" ? state.lmstudio : state.ollama;
    if (engine?.models?.length > 0) {
      const loaded = engine.loaded_models?.[0]?.model;
      setSelectedModel(loaded || engine.models[0].id);
    }
  }, [selectedProvider, state?.lmstudio?.models?.length, state?.ollama?.models?.length]);

  const currentEngine: LocalEngineStatus | undefined =
    selectedProvider === "lmstudio" ? state?.lmstudio : state?.ollama;

  const gpu = state?.gpu;
  const profile = state?.hardware_profile || gpu?.profile;
  const isLowEnd = profile?.is_low_end || (gpu?.total_vram_gb && gpu.total_vram_gb <= 4.5);

  const handleLoadModel = async () => {
    if (!selectedModel) return;
    setIsLoading(true);
    const targetCtx = selectedContext > 0 ? selectedContext : (profile?.recommended_context_window || 4096);
    setActionMessage({
      text: `Loading '${selectedModel}' into memory (${targetCtx.toLocaleString()} context, offload: ${offloadMode})...`,
      type: "info",
    });

    try {
      const res = await api.loadLocalModel({
        provider: selectedProvider,
        model: selectedModel,
        context_window: targetCtx,
        gpu_layers: offloadMode === "off" ? 0 : 99,
        gpu_offload_mode: offloadMode,
        set_as_active: true,
      });
      setActionMessage({
        text: res.message || `Loaded '${selectedModel}' with rolling window active!`,
        type: "success",
      });
      await fetchStatus();
    } catch (err: any) {
      setActionMessage({ text: err?.message || "Failed to load model", type: "error" });
    } finally {
      setIsLoading(false);
    }
  };

  const handleUnloadModel = async () => {
    setIsUnloading(true);
    setActionMessage({ text: "Unloading model and freeing GPU VRAM...", type: "info" });
    try {
      const res = await api.unloadLocalModel({
        provider: selectedProvider,
        model: selectedModel,
      });
      setActionMessage({ text: res.message || "Model unloaded. GPU memory freed.", type: "success" });
      await fetchStatus();
    } catch (err: any) {
      setActionMessage({ text: err?.message || "Failed to unload model", type: "error" });
    } finally {
      setIsUnloading(false);
    }
  };

  const handleStartServer = async () => {
    setIsStartingServer(true);
    setActionMessage({ text: "Starting LM Studio local server on port 1234...", type: "info" });
    try {
      const res = await api.startLocalServer(1234);
      setActionMessage({ text: res.message || "LM Studio server started!", type: "success" });
      await fetchStatus();
    } catch (err: any) {
      setActionMessage({ text: err?.message || "Failed starting LM Studio server", type: "error" });
    } finally {
      setIsStartingServer(false);
    }
  };

  if (!open) return null;

  const loadedModels = currentEngine?.loaded_models || [];
  const isLoaded = loadedModels.length > 0;
  const vramPercent = gpu?.total_vram_mb
    ? Math.round((gpu.used_vram_mb / gpu.total_vram_mb) * 100)
    : 0;

  // Sort models: if low-end hardware, place 4GB-friendly models first
  const sortedModels = (currentEngine?.models || []).slice().sort((a, b) => {
    if (isLowEnd) {
      if (a.is_4gb_friendly && !b.is_4gb_friendly) return -1;
      if (!a.is_4gb_friendly && b.is_4gb_friendly) return 1;
    }
    return a.id.localeCompare(b.id);
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="flex flex-col w-full max-w-2xl rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/70">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-slate-100">Local AI &amp; GPU Engine Manager</h2>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${
                    isLowEnd
                      ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                      : "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                  }`}
                >
                  {profile?.tier_label || (isLowEnd ? "4GB Laptop Profile" : "GPU Accelerated")}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Universal hardware auto-tuning • 4GB laptop to 16GB+ desktop • Zero-OOM rolling context window
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors cursor-pointer"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body Content */}
        <div className="p-6 space-y-5 overflow-y-auto max-h-[75vh]">
          {/* Hardware Telemetry Card */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Detected Hardware
                </span>
              </div>
              <span className="font-mono text-xs text-emerald-400 font-medium">
                {gpu?.name || "Host Graphics Adapter"}
              </span>
            </div>

            {/* VRAM Bar */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
                <span>Memory Pool (VRAM)</span>
                <span>
                  {gpu?.used_vram_gb || 0} GB / {gpu?.total_vram_gb || 4.0} GB ({vramPercent}%)
                </span>
              </div>
              <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className={`h-full transition-all duration-500 rounded-full ${
                    vramPercent > 90
                      ? "bg-rose-500"
                      : vramPercent > 70
                      ? "bg-amber-500"
                      : "bg-emerald-500"
                  }`}
                  style={{ width: `${Math.min(100, Math.max(2, vramPercent))}%` }}
                />
              </div>
            </div>

            {/* Hardware Profile Recommendation Banner */}
            {profile?.warning && (
              <div className="flex items-start gap-2.5 p-3 rounded-lg bg-amber-500/10 border border-amber-500/25 text-amber-300 text-xs font-mono">
                <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold text-amber-200">Hardware Notice for 4GB Setup:</div>
                  <div className="mt-0.5">{profile.warning}</div>
                </div>
              </div>
            )}

            {/* Hardware Guarantees Pills */}
            <div className="flex flex-wrap gap-2 pt-1">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-blue-500/10 text-blue-300 border border-blue-500/20">
                <Layers className="w-3 h-3 text-blue-400" />
                Safe Context: {(profile?.recommended_context_window || 4096).toLocaleString()} tokens
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                Rolling Window: Active (Zero OOM)
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-purple-500/10 text-purple-300 border border-purple-500/20">
                <Zap className="w-3 h-3 text-purple-400" />
                Best Models: {profile?.safe_models_description || "0.8B - 4B Q4"}
              </span>
            </div>
          </div>

          {/* Engine Provider Tabs */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Local Inference Runtime
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setSelectedProvider("lmstudio")}
                className={`flex items-center justify-between p-3 rounded-xl border text-left transition-all cursor-pointer ${
                  selectedProvider === "lmstudio"
                    ? "border-blue-500 bg-blue-950/30 text-blue-200 shadow-md shadow-blue-950/30"
                    : "border-slate-800 bg-slate-950/40 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                <div>
                  <div className="font-semibold text-sm text-slate-200">LM Studio</div>
                  <div className="text-xs font-mono text-slate-400 mt-0.5">http://localhost:1234</div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      state?.lmstudio?.available ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
                    }`}
                  />
                  <span className="text-[11px] font-mono capitalize">
                    {state?.lmstudio?.available ? "Online" : "Offline"}
                  </span>
                </div>
              </button>

              <button
                type="button"
                onClick={() => setSelectedProvider("ollama")}
                className={`flex items-center justify-between p-3 rounded-xl border text-left transition-all cursor-pointer ${
                  selectedProvider === "ollama"
                    ? "border-blue-500 bg-blue-950/30 text-blue-200 shadow-md shadow-blue-950/30"
                    : "border-slate-800 bg-slate-950/40 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                <div>
                  <div className="font-semibold text-sm text-slate-200">Ollama</div>
                  <div className="text-xs font-mono text-slate-400 mt-0.5">http://localhost:11434</div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      state?.ollama?.available ? "bg-emerald-400 animate-pulse" : "bg-slate-600"
                    }`}
                  />
                  <span className="text-[11px] font-mono capitalize">
                    {state?.ollama?.available ? "Online" : "Offline"}
                  </span>
                </div>
              </button>
            </div>
          </div>

          {/* Offline Warning & Start Server helper */}
          {!currentEngine?.available && (
            <div className="flex items-center justify-between p-3.5 rounded-xl border border-amber-500/30 bg-amber-950/20 text-amber-200 text-xs">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                <span>
                  {selectedProvider === "lmstudio"
                    ? "LM Studio server is not running on port 1234."
                    : "Ollama instance is not reachable on port 11434."}
                </span>
              </div>
              {selectedProvider === "lmstudio" && (
                <button
                  type="button"
                  onClick={handleStartServer}
                  disabled={isStartingServer}
                  className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold transition-colors cursor-pointer shrink-0 disabled:opacity-50"
                >
                  {isStartingServer ? "Starting..." : "Start LM Studio Server"}
                </button>
              )}
            </div>
          )}

          {/* Currently Loaded Model Banner */}
          {isLoaded ? (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-emerald-300">
                    Currently Active in Memory
                  </span>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  RESIDENT
                </span>
              </div>
              {loadedModels.map((lm, idx) => (
                <div key={idx} className="flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-200 font-semibold">
                    {lm.model || lm.identifier || "Active Model"}
                  </span>
                  <span className="text-slate-400">
                    {lm.size ? `Size: ${lm.size}` : lm.size_vram_mb ? `${lm.size_vram_mb} MB VRAM` : "Loaded"} •{" "}
                    {lm.context_length ? `${lm.context_length} ctx` : "Active Context"}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3.5 text-center text-xs text-slate-400 font-mono">
              No models currently resident in VRAM. Select a model below and click &quot;Load Model into GPU&quot;.
            </div>
          )}

          {/* Model Selection Dropdown */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                Select Model ({sortedModels.length} Available)
              </label>
              <button
                type="button"
                onClick={fetchStatus}
                className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
              >
                <RefreshCw className="w-3 h-3" />
                <span>Refresh List</span>
              </button>
            </div>

            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl bg-slate-950 border border-slate-700 text-slate-200 font-mono text-xs focus:outline-none focus:border-blue-500 cursor-pointer"
            >
              {sortedModels.length > 0 ? (
                sortedModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id} {m.size_gb ? `(${m.size_gb} GB)` : ""}{" "}
                    {m.is_4gb_friendly ? "★ [4GB Laptop Ready]" : "[Requires 6GB-8GB+ VRAM]"}
                  </option>
                ))
              ) : (
                <option value="">No models detected on host</option>
              )}
            </select>
          </div>

          {/* Hardware Tuning Controls (Context Window & GPU Offload) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            {/* Context Window Selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-blue-400" />
                <span>Context Window Size</span>
              </label>
              <select
                value={selectedContext}
                onChange={(e) => setSelectedContext(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-300 font-mono text-xs focus:outline-none focus:border-blue-500 cursor-pointer"
              >
                <option value={0}>
                  Auto-Detect ({profile?.recommended_context_window ? `${profile.recommended_context_window.toLocaleString()} ctx` : "Safe Default"})
                </option>
                <option value={2048}>2,048 tokens (Ultra-low / 2GB VRAM)</option>
                <option value={4096}>4,096 tokens (Standard Laptop / 4GB VRAM)</option>
                <option value={8192}>8,192 tokens (Mid-range / 6GB-8GB VRAM)</option>
                <option value={16384}>16,384 tokens (High-end / 12GB-16GB VRAM)</option>
                <option value={32768}>32,768 tokens (Workstation / 24GB+ VRAM)</option>
              </select>
            </div>

            {/* GPU Offload Strategy */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-purple-400" />
                <span>GPU Offload Strategy</span>
              </label>
              <select
                value={offloadMode}
                onChange={(e) => setOffloadMode(e.target.value as any)}
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-300 font-mono text-xs focus:outline-none focus:border-blue-500 cursor-pointer"
              >
                <option value="auto">Auto (Safe Layer Offload - Prevents 4GB OOM)</option>
                <option value="max">Max (100% GPU VRAM - High Throughput)</option>
                <option value="off">Off (CPU Mode - Zero VRAM Required)</option>
              </select>
            </div>
          </div>

          {/* Action Message Banner */}
          {actionMessage && (
            <div
              className={`p-3 rounded-xl border text-xs font-mono ${
                actionMessage.type === "success"
                  ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-300"
                  : actionMessage.type === "error"
                  ? "bg-rose-950/30 border-rose-500/40 text-rose-300"
                  : "bg-blue-950/30 border-blue-500/40 text-blue-300"
              }`}
            >
              {actionMessage.text}
            </div>
          )}

          {/* Action Buttons: Load & Unload */}
          <div className="flex items-center gap-3 pt-2">
            <button
              type="button"
              onClick={handleLoadModel}
              disabled={isLoading || !selectedModel}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs shadow-lg shadow-blue-600/20 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Loading model...</span>
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4 text-amber-300" />
                  <span>Load Model into GPU</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={handleUnloadModel}
              disabled={isUnloading}
              className="flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-rose-950/40 hover:border-rose-500/50 hover:text-rose-300 border border-slate-700 text-slate-300 font-semibold text-xs transition-all cursor-pointer disabled:opacity-50"
              title="Unload from VRAM to free GPU memory"
            >
              {isUnloading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4 text-rose-400" />
              )}
              <span>Unload</span>
            </button>
          </div>
        </div>

        {/* Modal Footer with Live Debug Shortcut */}
        <div className="flex items-center justify-between px-6 py-3.5 border-t border-slate-800 bg-slate-950/80">
          <div className="text-[11px] text-slate-500 font-mono">
            Profile:{" "}
            <span className="text-slate-300 font-semibold">
              {profile?.tier_label || "Auto-Tuned"}
            </span>
          </div>
          {onOpenDebugModal && (
            <button
              type="button"
              onClick={() => {
                onClose();
                onOpenDebugModal();
              }}
              className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 font-medium transition-colors cursor-pointer"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Inspect Live Token Debugger</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
