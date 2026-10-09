"use client";

import { useState, useEffect, useRef } from "react";
import { LLMSettings, ModelCatalogInfo } from "@/types";
import { api } from "@/lib/api";
import {
  AlertTriangle,
  Check,
  ChevronDown,
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
      setSelectedProviderTab(data.active_provider);
    } catch (err) {
      console.warn("Failed to fetch LLM settings in ModelSelector:", err);
    }
  };

  useEffect(() => {
    fetchSettings();
    const interval = setInterval(fetchSettings, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (isModelDropdownOpen) {
      fetchSettings();
    }
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
      case "ollama":
        return "Local Ollama";
      default:
        return prov.toUpperCase();
    }
  };

  const providerDisplayName = getProviderDisplayName(activeProvider);
  const activeModelDisplayName = activeModelInfo?.name || activeModelId;

  return (
    <div className={`relative ${className}`} ref={modelDropdownRef}>
      <button
        type="button"
        onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
        className={`w-full rounded-xl border p-3 transition-all text-left cursor-pointer group shadow-sm select-none ${
          hasFallbackEvent
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
                  hasFallbackEvent ? "bg-amber-400" : "bg-emerald-400"
                }`}
              />
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  hasFallbackEvent ? "bg-amber-500" : "bg-emerald-500"
                }`}
              />
            </span>
            <span className="text-[10px] font-mono font-semibold tracking-wider text-slate-400 uppercase truncate">
              {providerDisplayName}
            </span>
          </div>

          <div className="shrink-0">
            {hasFallbackEvent ? (
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

      {/* Model & Provider Quick Popover */}
      {isModelDropdownOpen && llmSettings && (
        <div
          className={`absolute ${
            align === "left" ? "left-0" : "right-0"
          } mt-2 w-[340px] md:w-[400px] rounded-xl bg-slate-900/95 border border-slate-800 shadow-2xl backdrop-blur-xl p-3 z-50 text-xs space-y-3 animate-in fade-in zoom-in-95`}
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

          {/* Provider Tabs */}
          <div className="flex gap-1 p-1 bg-slate-950 rounded-lg border border-slate-800/80 overflow-x-auto">
            {Object.keys(llmSettings.providers_catalog).map((pKey) => {
              const p = llmSettings.providers_catalog[pKey];
              const isCurrent = selectedProviderTab === pKey;
              const isActive = activeProvider === pKey;
              return (
                <button
                  key={pKey}
                  onClick={() => setSelectedProviderTab(pKey)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all whitespace-nowrap cursor-pointer flex items-center gap-1 ${
                    isCurrent
                      ? "bg-blue-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                >
                  {isActive && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
                  <span className="capitalize">{pKey === "nvidia_nim" ? "NVIDIA" : p?.name?.split(" ")[0] || pKey}</span>
                </button>
              );
            })}
          </div>

          {/* Model List for Selected Provider */}
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

          <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
            {filteredModels.length === 0 ? (
              <div className="p-4 text-center text-slate-500 text-[11px]">
                No models match the filter.
              </div>
            ) : (
              filteredModels.map((m) => {
                const isSelected = activeProvider === selectedProviderTab && activeModelId === m.id;
                const isLocal = selectedProviderTab === "ollama";
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
                        <div className="text-[9px] text-slate-500">
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

          {/* Failover Status & Settings Link */}
          <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
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
        </div>
      )}
    </div>
  );
}
