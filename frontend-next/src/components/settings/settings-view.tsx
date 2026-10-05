"use client";

import { useState, useEffect } from "react";
import {
  FallbackHierarchyItem,
  LLMSettings,
  ModelCatalogInfo,
  ProviderCatalogInfo,
} from "@/types";
import { api } from "@/lib/api";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Check,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Gauge,
  Key,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { TokenUsageDashboard } from "./token-usage-dashboard";

export function SettingsView() {
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [settingsTab, setSettingsTab] = useState<"models" | "tokens">("models");
  const [selectedProvider, setSelectedProvider] = useState<string>("groq");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [onlyFreeModels, setOnlyFreeModels] = useState<boolean>(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Fallback hierarchy state
  const [fallbackChain, setFallbackChain] = useState<FallbackHierarchyItem[]>([]);
  const [addProvider, setAddProvider] = useState<string>("groq");
  const [addModel, setAddModel] = useState<string>("");
  const [savingHierarchy, setSavingHierarchy] = useState(false);
  const [hierarchySuccess, setHierarchySuccess] = useState(false);

  // Latency benchmark state
  const [testingPing, setTestingPing] = useState(false);
  const [pingResult, setPingResult] = useState<{
    latency_ms: number;
    status: string;
    sample_output?: string;
    error_message?: string;
  } | null>(null);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const data = await api.getLLMSettings();
      setSettings(data);
      setSelectedProvider(data.active_provider);
      setSelectedModel(data.active_model);

      // Populate fallback hierarchy from custom or automatic chain
      if (data.custom_fallback_chain && data.custom_fallback_chain.length > 0) {
        setFallbackChain(data.custom_fallback_chain);
      } else {
        // Derive initial chain from fallback_chain labels
        const initial = data.fallback_chain.map((label) => {
          const parts = label.split(":");
          const p = parts[0] || "groq";
          const m = parts.slice(1).join(":") || "";
          const pInfo = data.providers_catalog[p];
          const mInfo = pInfo?.models?.find((x) => x.id === m);
          return {
            provider: p,
            model: m,
            name: mInfo?.name || m,
            free: mInfo?.free ?? false,
            rate_limits: mInfo?.rate_limits || null,
          };
        });
        setFallbackChain(initial);
      }

      // Initialize add model picker
      const groqModels = data.providers_catalog["groq"]?.models || [];
      if (groqModels.length > 0) {
        setAddModel(groqModels[0].id);
      }
    } catch (err) {
      console.error("Failed loading LLM settings:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleProviderChange = (prov: string) => {
    setSelectedProvider(prov);
    if (settings?.providers_catalog[prov]) {
      const models = settings.providers_catalog[prov].models || [];
      if (models.length > 0) {
        setSelectedModel(models[0].id);
      }
    }
  };

  const handleAddProviderChange = (prov: string) => {
    setAddProvider(prov);
    if (settings?.providers_catalog[prov]) {
      const models = settings.providers_catalog[prov].models || [];
      if (models.length > 0) {
        setAddModel(models[0].id);
      }
    }
  };

  const handleSaveSettings = async () => {
    try {
      setSaving(true);
      const updated = await api.updateLLMSettings({
        provider: selectedProvider,
        model: selectedModel,
      });
      setSettings(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      alert(`Failed to save LLM settings: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTestPing = async () => {
    try {
      setTestingPing(true);
      setPingResult(null);
      const res = await api.testLLMConnectivity({
        provider: selectedProvider,
        model: selectedModel,
      });
      setPingResult(res);
    } catch (err: any) {
      setPingResult({
        latency_ms: 0,
        status: "error",
        error_message: err.message,
      });
    } finally {
      setTestingPing(false);
    }
  };

  // Fallback Hierarchy Operations
  const handleMoveTier = (index: number, direction: "up" | "down") => {
    const newChain = [...fallbackChain];
    const targetIdx = direction === "up" ? index - 1 : index + 1;
    if (targetIdx < 0 || targetIdx >= newChain.length) return;
    const temp = newChain[index];
    newChain[index] = newChain[targetIdx];
    newChain[targetIdx] = temp;
    setFallbackChain(newChain);
  };

  const handleRemoveTier = (index: number) => {
    setFallbackChain(fallbackChain.filter((_, i) => i !== index));
  };

  const handleAddTier = () => {
    if (!addProvider || !addModel) return;
    // Prevent duplicates
    if (fallbackChain.some((item) => item.provider === addProvider && item.model === addModel)) {
      alert("This provider/model target is already in the fallback sequence.");
      return;
    }
    const pInfo = settings?.providers_catalog[addProvider];
    const mInfo = pInfo?.models?.find((x) => x.id === addModel);
    const newItem: FallbackHierarchyItem = {
      provider: addProvider,
      model: addModel,
      name: mInfo?.name || addModel,
      free: mInfo?.free ?? false,
      rate_limits: mInfo?.rate_limits || null,
    };
    setFallbackChain([...fallbackChain, newItem]);
  };

  const handleSaveHierarchy = async () => {
    try {
      setSavingHierarchy(true);
      const updated = await api.saveFallbackChain(
        fallbackChain.map((item) => ({ provider: item.provider, model: item.model }))
      );
      setSettings(updated);
      setHierarchySuccess(true);
      setTimeout(() => setHierarchySuccess(false), 3000);
    } catch (err: any) {
      alert(`Failed to save fallback hierarchy: ${err.message}`);
    } finally {
      setSavingHierarchy(false);
    }
  };

  const handleResetHierarchy = async () => {
    if (!confirm("Reset to default automatic multi-tier failover hierarchy?")) return;
    try {
      setSavingHierarchy(true);
      const updated = await api.resetFallbackChain();
      setSettings(updated);
      const initial = updated.fallback_chain.map((label) => {
        const parts = label.split(":");
        const p = parts[0] || "groq";
        const m = parts.slice(1).join(":") || "";
        const pInfo = updated.providers_catalog[p];
        const mInfo = pInfo?.models?.find((x) => x.id === m);
        return {
          provider: p,
          model: m,
          name: mInfo?.name || m,
          free: mInfo?.free ?? false,
          rate_limits: mInfo?.rate_limits || null,
        };
      });
      setFallbackChain(initial);
      setHierarchySuccess(true);
      setTimeout(() => setHierarchySuccess(false), 3000);
    } catch (err: any) {
      alert(`Failed to reset fallback hierarchy: ${err.message}`);
    } finally {
      setSavingHierarchy(false);
    }
  };

  const handleLoadRecommendedFreeHierarchy = () => {
    const recommended: FallbackHierarchyItem[] = [
      {
        provider: "groq",
        model: "openai/gpt-oss-20b",
        name: "GPT-OSS 20B (OpenAI)",
        free: true,
        rate_limits: "30 RPM | 8,000 TPM | 200,000 TPD",
      },
      {
        provider: "groq",
        model: "qwen/qwen3.8-27b",
        name: "Qwen 3.8 27B",
        free: true,
        rate_limits: "30 RPM | 6,000 TPM | 500,000 TPD",
      },
      {
        provider: "gemini",
        model: "gemini-2.0-flash",
        name: "Gemini 2.0 Flash",
        free: true,
        rate_limits: "15 RPM | 1M TPM | 1,500 RPD",
      },
      {
        provider: "agnes",
        model: "agnes-2.5-flash",
        name: "Agnes Flash 2.5",
        free: true,
        rate_limits: "Ultra Fast / Free Quota",
      },
      {
        provider: "agnes",
        model: "agnes-3.0-flash",
        name: "Agnes Flash 3.0",
        free: true,
        rate_limits: "High Throughput / Free Quota",
      },
      {
        provider: "openrouter",
        model: "openrouter/free",
        name: "OpenRouter Free Meta-Router",
        free: true,
        rate_limits: "20 RPM | Generous Free Pool",
      },
      {
        provider: "nvidia_nim",
        model: "meta/llama-3.2-11b-vision-instruct",
        name: "Llama 3.2 11B Vision",
        free: true,
        rate_limits: "NVIDIA NIM Free Credits",
      },
      {
        provider: "ollama",
        model: "qwen3.5:2b-q4_K_M",
        name: "Qwen 3.5 2B (Local Offline)",
        free: true,
        rate_limits: "Unlimited (Local Host)",
      },
    ];
    setFallbackChain(recommended);
  };

  const handleClearFallbackAlert = async () => {
    try {
      await api.clearFallbackEvent();
      await fetchSettings();
    } catch (err: any) {
      console.error("Failed clearing fallback event:", err);
    }
  };

  if (loading || !settings) {
    return (
      <div className="p-12 flex flex-col items-center justify-center gap-3 text-slate-500 text-xs">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
        <span>Loading model configurations, rate limits, and fallback hierarchy...</span>
      </div>
    );
  }

  const currentProviderInfo = settings.providers_catalog[selectedProvider] || { models: [] };
  const rawModels: ModelCatalogInfo[] = currentProviderInfo.models || [];
  const filteredModels = onlyFreeModels ? rawModels.filter((m) => m.free) : rawModels;
  const selectedModelInfo = rawModels.find((m) => m.id === selectedModel);

  const addProviderInfo = settings.providers_catalog[addProvider] || { models: [] };
  const addAvailableModels: ModelCatalogInfo[] = addProviderInfo.models || [];

  return (
    <div className="space-y-8 max-w-5xl pb-16">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
          <Settings className="w-6 h-6 text-blue-400" />
          <span>Model Architecture & Failover Settings</span>
        </h1>
        <p className="text-sm text-slate-300 mt-1.5 leading-relaxed">
          Dynamically route prompts between cloud frontier models and local private instances (Ollama). Configure custom multi-tier fallback sequences to guarantee uninterrupted screening during rate-limits or outages.
        </p>
      </div>

      {/* Active Failover Alert Notification */}
      {settings.last_fallback_event && (
        <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-950/20 backdrop-blur-md flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between animate-in fade-in">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 shrink-0 mt-0.5 sm:mt-0">
              <AlertTriangle className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <div className="text-sm font-bold text-white flex items-center gap-2">
                <span>Automatic Failover Active</span>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono font-medium">
                  {settings.last_fallback_event.from_provider}:{settings.last_fallback_event.from_model} &rarr; {settings.last_fallback_event.to_provider}:{settings.last_fallback_event.to_model}
                </span>
              </div>
              <div className="text-xs text-slate-300 mt-1 max-w-2xl line-clamp-2 leading-relaxed">
                {settings.last_fallback_event.error || "Primary model hit rate limits or downtime. Execution seamlessly completed via next candidate in fallback chain."}
              </div>
            </div>
          </div>
          <button
            onClick={handleClearFallbackAlert}
            className="px-3.5 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 text-xs font-semibold transition-colors shrink-0 cursor-pointer"
          >
            Dismiss Alert
          </button>
        </div>
      )}

      {/* Settings Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
        <button
          onClick={() => setSettingsTab("models")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
            settingsTab === "models"
              ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
              : "bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white border border-slate-800"
          }`}
        >
          <Cpu className="w-4 h-4" />
          <span>Model Architecture & Failover</span>
        </button>

        <button
          onClick={() => setSettingsTab("tokens")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
            settingsTab === "tokens"
              ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
              : "bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white border border-slate-800"
          }`}
        >
          <Zap className="w-4 h-4 text-amber-400 fill-amber-400/20" />
          <span>Token Usage & Model Statistics</span>
          <span className="px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono text-[10px]">
            Analytics
          </span>
        </button>
      </div>

      {settingsTab === "tokens" ? (
        <TokenUsageDashboard onRefresh={fetchSettings} />
      ) : (
        <>
          {/* ========================================================================= */}
          {/* SECTION 1: PRIMARY INFERENCE PROVIDER & FREE MODEL SELECTOR               */}
          {/* ========================================================================= */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <span>Primary Active Engine</span>
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyFreeModels}
              onChange={(e) => setOnlyFreeModels(e.target.checked)}
              className="rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-0"
            />
            <span className="font-semibold text-emerald-400">Show Free Models Only</span>
          </label>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Left: Provider Picker Cards */}
          <div className="space-y-2">
            {Object.keys(settings.providers_catalog).map((provKey) => {
              const prov = settings.providers_catalog[provKey];
              const isConfigured = settings.api_keys_configured[provKey];
              const isSelected = selectedProvider === provKey;
              const freeCount = prov.models.filter((m) => m.free).length;

              return (
                <button
                  key={provKey}
                  onClick={() => handleProviderChange(provKey)}
                  className={`w-full text-left p-3.5 rounded-xl border transition-all flex items-center justify-between cursor-pointer ${
                    isSelected
                      ? "bg-slate-900 border-blue-500/60 shadow-md shadow-blue-500/10 ring-1 ring-blue-500/20"
                      : "bg-slate-950/80 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900/40"
                  }`}
                >
                  <div className="space-y-1">
                    <div className="font-semibold text-sm text-white flex items-center gap-2">
                      <span>{prov.name}</span>
                      {isSelected && <span className="w-2 h-2 rounded-full bg-blue-400" />}
                    </div>
                    <div className="text-xs text-slate-400">
                      {prov.models.length} models ({freeCount} free)
                    </div>
                  </div>

                  <span
                    className={`text-xs px-2 py-0.5 rounded font-mono font-medium ${
                      isConfigured
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {isConfigured ? "Key Active" : "No Key"}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Right: Model Selection & Details Card */}
          <div className="md:col-span-2 space-y-4">
            <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/40 space-y-5">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-200 flex items-center justify-between">
                  <span>Target Inference Model</span>
                  <span className="text-xs text-slate-400 font-normal">
                    {filteredModels.length} models available
                  </span>
                </label>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-sm text-slate-100 focus:outline-none focus:border-blue-500 font-mono cursor-pointer"
                >
                  {filteredModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} {m.free ? "— [FREE]" : ""} ({m.id})
                    </option>
                  ))}
                </select>
              </div>

              {/* Selected Model Deep Dive Info */}
              {selectedModelInfo && (
                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800/80 text-sm space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white text-base">{selectedModelInfo.name}</span>
                    <div className="flex items-center gap-2">
                      {selectedModelInfo.free ? (
                        <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono font-semibold">
                          FREE TIER
                        </span>
                      ) : (
                        <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono font-medium">
                          STANDARD TIER
                        </span>
                      )}
                      <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
                        {selectedModelInfo.context_window} Context
                      </span>
                    </div>
                  </div>

                  <p className="text-sm text-slate-300 leading-relaxed">
                    {selectedModelInfo.description}
                  </p>

                  <div className="pt-2.5 border-t border-slate-800/80 grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-slate-400">Rate Limits: </span>
                      <span className="text-slate-200 font-mono font-medium">{selectedModelInfo.rate_limits || "Provider default"}</span>
                    </div>
                    <div>
                      <span className="text-slate-400">Structured Output: </span>
                      <span className="text-blue-400 font-mono font-medium">{selectedModelInfo.compatibility}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center gap-3 pt-1">
                <button
                  onClick={handleSaveSettings}
                  disabled={saving}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-sm font-semibold shadow-lg shadow-blue-600/20 transition-all cursor-pointer disabled:opacity-50"
                >
                  {saving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4" />
                  )}
                  <span>Activate Configuration</span>
                </button>

                <button
                  onClick={handleTestPing}
                  disabled={testingPing}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
                >
                  {testingPing ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" />
                  ) : (
                    <Gauge className="w-3.5 h-3.5 text-amber-400" />
                  )}
                  <span>Ping Latency</span>
                </button>
              </div>

              {saveSuccess && (
                <div className="p-2.5 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Primary inference engine updated dynamically across all agents!</span>
                </div>
              )}

              {/* Latency Ping Result Box */}
              {pingResult && (
                <div
                  className={`p-3 rounded-lg border text-xs space-y-1 animate-in fade-in ${
                    pingResult.status === "ok"
                      ? "bg-slate-950 border-emerald-500/30 text-slate-300"
                      : "bg-rose-950/30 border-rose-500/30 text-rose-300"
                  }`}
                >
                  <div className="flex items-center justify-between font-semibold">
                    <span className="flex items-center gap-1.5">
                      {pingResult.status === "ok" ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Activity className="w-3.5 h-3.5 text-rose-400" />
                      )}
                      <span>{pingResult.status === "ok" ? "Connection Verified" : "Ping Failure"}</span>
                    </span>
                    <span className="font-mono text-emerald-400">
                      {pingResult.latency_ms.toFixed(0)} ms
                    </span>
                  </div>
                  {pingResult.error_message && (
                    <div className="text-[11px] text-rose-400 font-mono">
                      {pingResult.error_message}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 2: CUSTOM FALLBACK & FAILOVER HIERARCHY BUILDER                   */}
      {/* ========================================================================= */}
      <div className="space-y-4 pt-6 border-t border-slate-800/80">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Layers className="w-4 h-4 text-blue-400" />
              <span>Multi-Tier Fallback Hierarchy Builder</span>
            </div>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed max-w-2xl">
              If the primary engine hits TPM/RPM limits (429), quota exhaustion, or downtime, requests cascade down this exact sequence in order.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleLoadRecommendedFreeHierarchy}
              className="px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5"
              title="Prepopulate optimal chain of 100% free high-speed models"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Recommended Free Preset</span>
            </button>
            <button
              onClick={handleResetHierarchy}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
              title="Reset to automated cascading multi-tier failover"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset to Auto</span>
            </button>
          </div>
        </div>

        {/* Live Fallback Sequence Visualizer */}
        <div className="space-y-2.5">
          {fallbackChain.map((item, index) => {
            const isPrimary = index === 0;
            return (
              <div
                key={`${item.provider}:${item.model}:${index}`}
                className={`p-3.5 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-all ${
                  isPrimary
                    ? "bg-blue-950/20 border-blue-500/40 shadow-sm"
                    : "bg-slate-950/60 border-slate-800/80 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-8 h-8 rounded-lg flex items-center justify-center font-mono font-bold text-sm shrink-0 ${
                      isPrimary
                        ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                        : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    T{index + 1}
                  </div>

                  <div className="space-y-0.5">
                    <div className="text-sm font-semibold text-white flex items-center gap-2">
                      <span className="capitalize text-slate-400">{item.provider}:</span>
                      <span>{item.name || item.model}</span>
                      {item.free && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono font-medium">
                          FREE
                        </span>
                      )}
                      {isPrimary && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 font-semibold font-mono">
                          PRIMARY
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 font-mono">
                      {item.model} {item.rate_limits ? `• ${item.rate_limits}` : ""}
                    </div>
                  </div>
                </div>

                {/* Priority Reordering & Deletion Controls */}
                <div className="flex items-center gap-1.5 self-end sm:self-center">
                  <button
                    onClick={() => handleMoveTier(index, "up")}
                    disabled={index === 0}
                    className="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 disabled:opacity-30 disabled:pointer-events-none cursor-pointer"
                    title="Increase Priority"
                  >
                    <ArrowUp className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => handleMoveTier(index, "down")}
                    disabled={index === fallbackChain.length - 1}
                    className="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 disabled:opacity-30 disabled:pointer-events-none cursor-pointer"
                    title="Decrease Priority"
                  >
                    <ArrowDown className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => handleRemoveTier(index)}
                    className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 hover:bg-rose-500/20 text-rose-400 cursor-pointer"
                    title="Remove from Hierarchy"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Add Tier Bar */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/30 flex flex-col md:flex-row items-center gap-3">
          <div className="text-sm font-semibold text-slate-200 shrink-0 flex items-center gap-2">
            <Plus className="w-4 h-4 text-blue-400" />
            <span>Add Fallback Target:</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 flex-1 w-full">
            <select
              value={addProvider}
              onChange={(e) => handleAddProviderChange(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-sm text-slate-200 capitalize cursor-pointer font-mono"
            >
              {Object.keys(settings.providers_catalog).map((pKey) => (
                <option key={pKey} value={pKey}>
                  {settings.providers_catalog[pKey].name}
                </option>
              ))}
            </select>

            <select
              value={addModel}
              onChange={(e) => setAddModel(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-sm text-slate-200 cursor-pointer font-mono"
            >
              {addAvailableModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} {m.free ? "— [FREE]" : ""}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleAddTier}
            className="w-full md:w-auto px-4 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-100 text-xs font-semibold cursor-pointer shrink-0 transition-colors"
          >
            Add to Sequence
          </button>
        </div>

        {/* Save Hierarchy Button */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleSaveHierarchy}
            disabled={savingHierarchy}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white text-sm font-semibold shadow-lg shadow-emerald-600/20 transition-all cursor-pointer disabled:opacity-50"
          >
            {savingHierarchy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Check className="w-4 h-4" />
            )}
            <span>Save & Apply Fallback Hierarchy</span>
          </button>

          {hierarchySuccess && (
            <div className="p-2.5 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>Custom fallback hierarchy persisted and active across all screening pipelines!</span>
            </div>
          )}
        </div>
      </div>
        </>
      )}
    </div>
  );
}
