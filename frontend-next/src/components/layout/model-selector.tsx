"use client";

import { useState, useEffect, useRef } from "react";
import { LLMSettings, ModelCatalogInfo } from "@/types";
import { api } from "@/lib/api";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Layers,
  Settings2,
  Zap,
} from "lucide-react";

interface ModelSelectorProps {
  onNavigateToSettings?: () => void;
  className?: string;
  align?: "left" | "right";
}

export function ModelSelector({
  onNavigateToSettings,
  className = "",
  align = "right",
}: ModelSelectorProps) {
  const [llmSettings, setLlmSettings] = useState<LLMSettings | null>(null);
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [selectedProviderTab, setSelectedProviderTab] = useState<string>("groq");
  const [onlyFreeModels, setOnlyFreeModels] = useState<boolean>(false);
  const [isSwitchingModel, setIsSwitchingModel] = useState<boolean>(false);
  const [isTogglingFallback, setIsTogglingFallback] = useState<boolean>(false);
  const [isTogglingParallel, setIsTogglingParallel] = useState<boolean>(false);

  const modelDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(event.target as Node)) {
        setIsModelDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchSettings = async () => {
    try {
      const data = await api.getLLMSettings();
      setLlmSettings(data);
      if (!isModelDropdownOpen) {
        setSelectedProviderTab(data.active_provider);
      }
    } catch (err) {
      console.warn("Failed to fetch LLM settings in ModelSelector:", err);
    }
  };

  // Real-time polling: every 4 seconds normally, 2.5s when dropdown is open
  useEffect(() => {
    fetchSettings();
    const interval = setInterval(fetchSettings, isModelDropdownOpen ? 2500 : 4000);
    return () => clearInterval(interval);
  }, [isModelDropdownOpen]);

  const handleSelectModel = async (provider: string, modelId: string) => {
    try {
      setIsSwitchingModel(true);
      const updated = await api.updateLLMSettings({
        provider,
        model: modelId,
      });
      setLlmSettings(updated);
      setSelectedProviderTab(provider);
      setIsModelDropdownOpen(false);
    } catch (err: any) {
      alert(`Failed to switch model: ${err.message}`);
    } finally {
      setIsSwitchingModel(false);
    }
  };

  const activeProvider = llmSettings?.active_provider || "groq";
  const activeModelId = llmSettings?.active_model || "openai/gpt-oss-20b";
  const hasFallbackEvent = Boolean(llmSettings?.last_fallback_event);
  const fallbackCount = llmSettings?.fallback_chain?.length || 0;
  const fallbackEnabled = llmSettings?.fallback_enabled ?? true;
  const parallelEnabled = llmSettings?.parallel_screening_enabled ?? false;

  const handleToggleParallel = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setIsTogglingParallel(true);
      const updated = await api.toggleParallelScreening(!parallelEnabled);
      setLlmSettings(updated);
    } catch (err: any) {
      console.error("Failed to toggle parallel screening:", err);
    } finally {
      setIsTogglingParallel(false);
    }
  };

  const handleToggleFallback = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setIsTogglingFallback(true);
      const updated = await api.toggleFailover(!fallbackEnabled);
      setLlmSettings(updated);
    } catch (err: any) {
      console.error("Failed to toggle failover:", err);
    } finally {
      setIsTogglingFallback(false);
    }
  };

  // Active model info lookup
  const activeProviderInfo = llmSettings?.providers_catalog?.[activeProvider];
  const activeModelInfo = activeProviderInfo?.models?.find((m) => m.id === activeModelId);
  const isActiveModelFree = activeModelInfo?.free ?? true;

  // Active cooldown statuses
  const getProviderCooldownStatus = (pKey: string) => {
    if (!llmSettings?.cooldown_statuses) return null;
    const statuses = Object.values(llmSettings.cooldown_statuses).filter(
      (s: any) => s.provider?.toLowerCase() === pKey.toLowerCase()
    );
    if (statuses.length === 0) return null;
    const hasExhausted = statuses.some((s: any) => s.exhausted);
    const maxRemaining = Math.max(...statuses.map((s: any) => s.remaining_seconds || 0));
    return {
      isCoolingDown: maxRemaining > 0,
      isExhausted: hasExhausted,
      remainingSeconds: Math.ceil(maxRemaining),
      affectedCount: statuses.length,
    };
  };

  const activeModelStatusKey = `${activeProvider}:${activeModelId}`;
  const activeModelCooldown = llmSettings?.cooldown_statuses?.[activeModelStatusKey];
  const activeProviderCooldown = getProviderCooldownStatus(activeProvider);
  const currentTabCooldown = getProviderCooldownStatus(selectedProviderTab);

  // Available models for currently selected provider tab in popover
  const currentTabProviderInfo = llmSettings?.providers_catalog?.[selectedProviderTab];
  const currentTabModels: ModelCatalogInfo[] = currentTabProviderInfo?.models || [];
  const filteredModels = onlyFreeModels
    ? currentTabModels.filter((m) => m.free)
    : currentTabModels;

  const getProviderDisplayName = (prov: string) => {
    switch (prov.toLowerCase()) {
      case "agnes":
        return "Agnes AI";
      case "groq":
        return "Groq LPU";
      case "gemini":
        return "Google Gemini";
      case "openrouter":
        return "OpenRouter";
      case "nvidia_nim":
        return "NVIDIA NIM";
      case "cohere":
        return "Cohere Command";
      case "ollama":
        return "Local Ollama";
      default:
        return prov.toUpperCase();
    }
  };

  const providerDisplayName = getProviderDisplayName(activeProvider);
  const activeModelDisplayName = activeModelInfo?.name || activeModelId;

  return (
    <div className={`relative space-y-2 ${className}`} ref={modelDropdownRef}>
      {/* 1. Main Model Selection Card */}
      <button
        type="button"
        onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
        className={`w-full rounded-xl border p-3 transition-all text-left cursor-pointer group shadow-sm select-none ${
          activeModelCooldown?.exhausted
            ? "bg-gradient-to-b from-rose-950/40 to-slate-900 border-rose-500/50 hover:border-rose-400 text-rose-200"
            : activeModelCooldown || activeProviderCooldown
            ? "bg-gradient-to-b from-amber-950/40 to-slate-900 border-amber-500/50 hover:border-amber-400 text-amber-200"
            : hasFallbackEvent
            ? "bg-gradient-to-b from-amber-950/40 to-slate-900 border-amber-500/50 hover:border-amber-400 text-amber-200"
            : "bg-gradient-to-b from-slate-900 to-slate-950 border-slate-800 hover:border-slate-700 hover:bg-slate-900/90 text-slate-200"
        }`}
        title="Click to switch AI provider or model"
      >
        {/* Row 1: Provider Label & Engine Status Badge */}
        <div className="flex items-center justify-between gap-1.5 mb-1.5">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="relative flex h-2 w-2 shrink-0">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  activeModelCooldown?.exhausted
                    ? "bg-rose-400"
                    : activeModelCooldown || activeProviderCooldown
                    ? "bg-amber-400"
                    : hasFallbackEvent
                    ? "bg-amber-400"
                    : "bg-emerald-400"
                }`}
              />
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  activeModelCooldown?.exhausted
                    ? "bg-rose-500"
                    : activeModelCooldown || activeProviderCooldown
                    ? "bg-amber-500"
                    : hasFallbackEvent
                    ? "bg-amber-500"
                    : "bg-emerald-500"
                }`}
              />
            </span>
            <span className="text-[10px] font-mono font-semibold tracking-wider text-slate-400 uppercase truncate">
              {providerDisplayName}
            </span>
          </div>

          <div className="shrink-0">
            {activeModelCooldown?.exhausted ? (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 text-[10px] font-semibold border border-rose-500/30 animate-pulse">
                <AlertTriangle className="w-2.5 h-2.5 text-rose-400" />
                <span>Rate Limit Hit</span>
              </span>
            ) : activeModelCooldown ? (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-semibold border border-amber-500/30">
                <AlertTriangle className="w-2.5 h-2.5 text-amber-400" />
                <span>Cooldown ({Math.round(activeModelCooldown.remaining_seconds)}s)</span>
              </span>
            ) : activeProviderCooldown ? (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-semibold border border-amber-500/30">
                <AlertTriangle className="w-2.5 h-2.5 text-amber-400" />
                <span>
                  {activeProviderCooldown.isExhausted
                    ? "Provider Exhausted"
                    : `Cooldown (${activeProviderCooldown.remainingSeconds}s)`}
                </span>
              </span>
            ) : hasFallbackEvent ? (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-semibold border border-amber-500/30">
                <AlertTriangle className="w-2.5 h-2.5 text-amber-400" />
                <span>Failover Active</span>
              </span>
            ) : activeProvider === "ollama" ? (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300 text-[10px] font-semibold border border-purple-500/20 font-mono">
                Local GPU
              </span>
            ) : isActiveModelFree ? (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[10px] font-semibold border border-emerald-500/20 font-mono">
                Free Tier
              </span>
            ) : (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 text-[10px] font-semibold border border-blue-500/20 font-mono">
                Online
              </span>
            )}
          </div>
        </div>

        {/* Row 2: Prominent Model Display Name & ID */}
        <div className="space-y-0.5 mb-2">
          <div className="text-sm font-bold text-white tracking-tight group-hover:text-blue-300 transition-colors truncate">
            {activeModelDisplayName}
          </div>
          <div className="text-[11px] font-mono text-slate-400 truncate flex items-center gap-1">
            <Zap className="w-3 h-3 text-amber-400/80 shrink-0" />
            <span className="truncate">{activeModelId}</span>
          </div>
        </div>

        {/* Row 3: Operational Status Strip & Switch Action */}
        <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
          <span className="text-slate-400 text-[10px] flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                !fallbackEnabled ? "bg-slate-500" : "bg-emerald-400"
              }`}
            />
            <span>
              {!fallbackEnabled
                ? "Failover Off"
                : fallbackCount > 0
                ? `${fallbackCount}-Tier Failover`
                : "Active Engine"}
            </span>
          </span>
          <span className="text-blue-400 group-hover:text-blue-300 font-medium flex items-center gap-1 transition-colors">
            <span>Change</span>
            <ChevronDown
              className={`w-3.5 h-3.5 transition-transform duration-200 ${
                isModelDropdownOpen ? "rotate-180" : ""
              }`}
            />
          </span>
        </div>
      </button>

      {/* 2. Screening Architecture Toggle Button (Always visible in the Model Selector Section) */}
      <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800 shadow-sm space-y-2">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-slate-300 font-semibold flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-blue-400" />
            <span>Screening Mode</span>
          </span>
          <span
            className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-bold uppercase tracking-wider ${
              parallelEnabled
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                : "bg-slate-800 text-slate-400 border border-slate-700"
            }`}
          >
            {parallelEnabled ? "Parallel Active" : "Sequential"}
          </span>
        </div>

        {/* Segmented Switch Buttons */}
        <div className="grid grid-cols-2 gap-1 p-0.5 bg-slate-950 rounded-lg border border-slate-800/80">
          <button
            type="button"
            disabled={isTogglingParallel || !parallelEnabled}
            onClick={(e) => {
              if (parallelEnabled) handleToggleParallel(e);
            }}
            className={`py-1.5 px-2 rounded-md text-[11px] font-medium transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
              !parallelEnabled
                ? "bg-slate-800 text-white shadow-sm font-semibold border border-slate-700"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
            title="Sequential: Original screening mode; evaluates criteria one-by-one using the active single provider"
          >
            <span>Sequential</span>
          </button>

          <button
            type="button"
            disabled={isTogglingParallel || parallelEnabled}
            onClick={(e) => {
              if (!parallelEnabled) handleToggleParallel(e);
            }}
            className={`py-1.5 px-2 rounded-md text-[11px] font-medium transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
              parallelEnabled
                ? "bg-gradient-to-r from-cyan-600 to-blue-600 text-white shadow-sm font-semibold border border-cyan-400/40"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
            title="Parallel: New multi-provider mode; spreads requirements concurrently across all healthy tested providers with automatic failover"
          >
            <Zap className="w-3 h-3 text-cyan-300" />
            <span>Parallel</span>
          </button>
        </div>

        <p className="text-[10px] text-slate-400 leading-tight">
          {parallelEnabled
            ? "⚡ Spreading criteria concurrently across all healthy providers with cooldown protection."
            : "Standard single-provider screening; runs all criteria sequentially on the selected model."}
        </p>
      </div>

      {/* 3. Model & Provider Quick Popover */}
      {isModelDropdownOpen && llmSettings && (
        <div
          className={`absolute ${
            align === "left" ? "left-0" : "right-0"
          } mt-2 w-[340px] md:w-[420px] rounded-xl bg-slate-900/95 border border-slate-800 shadow-2xl backdrop-blur-xl p-3 z-50 text-xs space-y-3 animate-in fade-in zoom-in-95`}
        >
          {/* Header */}
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div className="font-semibold text-slate-200 flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-amber-400" />
              <span>Select Active Inference Model</span>
            </div>
            <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={onlyFreeModels}
                onChange={(e) => setOnlyFreeModels(e.target.checked)}
                className="rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-0"
              />
              <span>Free Only</span>
            </label>
          </div>

          {/* Provider Tabs with Real-time Status Badges */}
          <div className="flex gap-1 p-1 bg-slate-950 rounded-lg border border-slate-800/80 overflow-x-auto">
            {Object.keys(llmSettings.providers_catalog).map((pKey) => {
              const p = llmSettings.providers_catalog[pKey];
              const isCurrent = selectedProviderTab === pKey;
              const isActive = activeProvider === pKey;
              const provCooldown = getProviderCooldownStatus(pKey);

              return (
                <button
                  key={pKey}
                  onClick={() => setSelectedProviderTab(pKey)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all whitespace-nowrap cursor-pointer flex items-center gap-1.5 ${
                    isCurrent
                      ? "bg-blue-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                  title={
                    provCooldown
                      ? provCooldown.isExhausted
                        ? "Provider Rate Limit Hit: Requests will auto-failover"
                        : `Provider Cooling Down: ${provCooldown.remainingSeconds}s remaining`
                      : undefined
                  }
                >
                  {isActive && !provCooldown && (
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  )}

                  {provCooldown?.isExhausted ? (
                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
                  ) : provCooldown?.isCoolingDown ? (
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  ) : null}

                  <span className="capitalize">
                    {pKey === "nvidia_nim" ? "NVIDIA" : p?.name?.split(" ")[0] || pKey}
                  </span>

                  {provCooldown?.isExhausted ? (
                    <span className="text-[8px] font-bold px-1 rounded bg-rose-500/30 text-rose-300 border border-rose-500/50">
                      EXHAUSTED
                    </span>
                  ) : provCooldown?.isCoolingDown ? (
                    <span className="text-[8px] font-semibold px-1 rounded bg-amber-500/30 text-amber-300 border border-amber-500/50">
                      {provCooldown.remainingSeconds}s
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>

          {/* Provider Status Alert Banner */}
          {currentTabCooldown && (
            <div
              className={`p-2 rounded-lg border text-[11px] flex items-center justify-between gap-2 ${
                currentTabCooldown.isExhausted
                  ? "bg-rose-950/40 border-rose-500/40 text-rose-300"
                  : "bg-amber-950/40 border-amber-500/40 text-amber-300"
              }`}
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">
                  {currentTabCooldown.isExhausted
                    ? "Provider Rate Limit Exhausted — auto-failover will divert requests."
                    : `Provider Cooling Down — requests will auto-failover (${currentTabCooldown.remainingSeconds}s remaining).`}
                </span>
              </div>
              <span className="font-mono text-[10px] font-bold shrink-0">
                {currentTabCooldown.remainingSeconds}s
              </span>
            </div>
          )}

          {/* Local Provider Helpers */}
          {selectedProviderTab === "ollama" && (
            <div className="px-2 py-1.5 rounded-lg bg-purple-950/30 border border-purple-500/20 text-[10px] text-purple-300 flex items-center justify-between">
              <span>Host GGUF / Ollama Models</span>
              <span className="font-mono text-purple-400">100% Offline</span>
            </div>
          )}
          {selectedProviderTab === "lmstudio" && (
            <div className="px-2 py-1.5 rounded-lg bg-blue-950/30 border border-blue-500/20 text-[10px] text-blue-300 flex items-center justify-between">
              <span>LM Studio Local Server (Port 1234)</span>
              <span className="font-mono text-blue-400">Local Privacy</span>
            </div>
          )}

          {/* Model List for Selected Provider */}
          <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
            {filteredModels.length === 0 ? (
              <div className="p-4 text-center text-slate-500 text-[11px]">
                No models match the filter.
              </div>
            ) : (
              filteredModels.map((m) => {
                const isSelected = activeProvider === selectedProviderTab && activeModelId === m.id;
                const isLocal = selectedProviderTab === "ollama";
                const statusKey = `${selectedProviderTab}:${m.id}`;
                const status = llmSettings?.cooldown_statuses?.[statusKey];

                return (
                  <button
                    key={m.id}
                    disabled={isSwitchingModel}
                    onClick={() => handleSelectModel(selectedProviderTab, m.id)}
                    className={`w-full text-left p-2 rounded-lg border transition-all cursor-pointer flex items-start justify-between gap-2 ${
                      isSelected
                        ? "bg-blue-600/10 border-blue-500/50 text-slate-200"
                        : "bg-slate-950/60 border-slate-800/60 hover:border-slate-700 text-slate-300"
                    }`}
                  >
                    <div className="space-y-0.5 min-w-0">
                      <div className="font-semibold text-[11px] text-white flex items-center gap-1.5">
                        <span className="truncate">{m.name}</span>
                        {status ? (
                          status.exhausted ? (
                            <span
                              className="text-[9px] px-1 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 font-semibold"
                              title={`Rate limit exhausted: ${status.remaining_seconds}s cooldown`}
                            >
                              EXHAUSTED
                            </span>
                          ) : (
                            <span
                              className="text-[9px] px-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-semibold"
                              title={`Cooling down: ${status.remaining_seconds}s remaining`}
                            >
                              COOLDOWN ({Math.round(status.remaining_seconds)}s)
                            </span>
                          )
                        ) : null}
                        {isLocal ? (
                          <span className="text-[9px] px-1 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20 font-mono">
                            LOCAL
                          </span>
                        ) : m.free ? (
                          <span className="text-[9px] px-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
                            FREE
                          </span>
                        ) : null}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono truncate">
                        {m.id}
                      </div>
                      {m.rate_limits && (
                        <div className="text-[9px] text-slate-500 truncate">
                          {m.rate_limits}
                        </div>
                      )}
                    </div>

                    {isSelected ? (
                      <div className="p-1 rounded bg-blue-500/20 text-blue-400 shrink-0">
                        <Check className="w-3.5 h-3.5" />
                      </div>
                    ) : null}
                  </button>
                );
              })
            )}
          </div>

          {/* Failover & Parallel Controls in Popover Footer */}
          <div className="pt-2 border-t border-slate-800/80 space-y-2">
            {/* Failover Switch Row */}
            <div className="flex items-center justify-between text-[11px]">
              <button
                type="button"
                disabled={isTogglingFallback}
                onClick={handleToggleFallback}
                className="flex items-center gap-2 group/failover text-slate-400 hover:text-slate-200 transition-colors cursor-pointer select-none"
                title={
                  fallbackEnabled
                    ? "Failover enabled: will automatically fallback to cloud models on error. Click to disable."
                    : "Failover disabled: will strictly stay on the chosen model without switching to cloud. Click to enable."
                }
              >
                <div
                  className={`w-6 h-3.5 flex items-center rounded-full p-0.5 transition-colors ${
                    fallbackEnabled ? "bg-emerald-500/80" : "bg-slate-700"
                  }`}
                >
                  <div
                    className={`bg-white w-2.5 h-2.5 rounded-full shadow-sm transform transition-transform duration-200 ${
                      fallbackEnabled ? "translate-x-2.5" : "translate-x-0"
                    }`}
                  />
                </div>
                <span className="flex items-center gap-1 text-[11px]">
                  <span>Failover:</span>
                  <span
                    className={`font-semibold ${
                      fallbackEnabled ? "text-emerald-400" : "text-slate-400"
                    }`}
                  >
                    {fallbackEnabled ? "Active" : "Off"}
                  </span>
                  {fallbackEnabled && (
                    <span className="text-[10px] text-slate-500 font-mono">
                      ({fallbackCount})
                    </span>
                  )}
                </span>
              </button>

              {onNavigateToSettings && (
                <button
                  onClick={() => {
                    setIsModelDropdownOpen(false);
                    onNavigateToSettings();
                  }}
                  className="text-blue-400 hover:text-blue-300 hover:underline flex items-center gap-1 cursor-pointer font-medium text-[11px]"
                >
                  <Settings2 className="w-3 h-3" />
                  <span>Configure &rarr;</span>
                </button>
              )}
            </div>

            {/* Parallel Switch Row (Under failover tick) */}
            <div className="flex items-center justify-between text-[11px] pt-1.5 border-t border-slate-800/60">
              <button
                type="button"
                disabled={isTogglingParallel}
                onClick={handleToggleParallel}
                className="flex items-center gap-2 group/parallel text-slate-400 hover:text-slate-200 transition-colors cursor-pointer select-none"
                title={
                  parallelEnabled
                    ? "Parallel Multi-Provider Screening active: spreading criteria across all healthy tested providers. Click to disable."
                    : "Parallel Multi-Provider Screening disabled: single-provider processing. Click to enable."
                }
              >
                <div
                  className={`w-6 h-3.5 flex items-center rounded-full p-0.5 transition-colors ${
                    parallelEnabled ? "bg-cyan-500/80" : "bg-slate-700"
                  }`}
                >
                  <div
                    className={`bg-white w-2.5 h-2.5 rounded-full shadow-sm transform transition-transform duration-200 ${
                      parallelEnabled ? "translate-x-2.5" : "translate-x-0"
                    }`}
                  />
                </div>
                <span className="flex items-center gap-1 text-[11px]">
                  <span>Parallel Screening:</span>
                  <span
                    className={`font-semibold ${
                      parallelEnabled ? "text-cyan-400" : "text-slate-400"
                    }`}
                  >
                    {parallelEnabled ? "Active" : "Off"}
                  </span>
                </span>
              </button>

              <span className="text-[10px] text-slate-500 font-mono">
                {parallelEnabled ? "Multi-Provider" : "Sequential"}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
