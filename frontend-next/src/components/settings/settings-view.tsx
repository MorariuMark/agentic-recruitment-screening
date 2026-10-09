"use client";

import { useState, useEffect } from "react";
import {
  FallbackHierarchyItem,
  LLMSettings,
  LocalModelScanResult,
  DiscoveredLocalModel,
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
  Database,
  Gauge,
  Key,
  Layers,
  Loader2,
  Moon,
  Palette,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  FolderSearch,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  Trash2,
  Zap,
  HardDrive,
  HelpCircle,
  Play,
  Square,
  Brain,
  Sliders,
  Laptop,
} from "lucide-react";
import { TokenUsageDashboard } from "./token-usage-dashboard";
import { useTheme } from "@/components/providers/theme-provider";

export function SettingsView() {
  const { theme, setTheme } = useTheme();
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [settingsTab, setSettingsTab] = useState<"models" | "tokens">("models");
  const [selectedProvider, setSelectedProvider] = useState<string>("groq");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [onlyFreeModels, setOnlyFreeModels] = useState<boolean>(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Local Model Specific Controls & Hardware Tuning
  const [localContextWindow, setLocalContextWindow] = useState<number>(4096);
  const [localRollingContext, setLocalRollingContext] = useState<boolean>(true);
  const [localThinkingEnabled, setLocalThinkingEnabled] = useState<boolean>(false);
  const [runningLocalModels, setRunningLocalModels] = useState<any[]>([]);
  const [loadingLocalModel, setLoadingLocalModel] = useState<string | null>(null);
  const [localActionMessage, setLocalActionMessage] = useState<string | null>(null);

  // Local AI Model Auto-Discovery state
  const [localScanResult, setLocalScanResult] = useState<LocalModelScanResult | null>(null);
  const [isScanningLocal, setIsScanningLocal] = useState<boolean>(false);
  const [autoImportGguf, setAutoImportGguf] = useState<boolean>(false);
  const [importingModelPath, setImportingModelPath] = useState<string | null>(null);

  // Fallback hierarchy state
  const [fallbackEnabled, setFallbackEnabled] = useState<boolean>(true);
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

      if (data.local_context_window) {
        setLocalContextWindow(data.local_context_window);
      }
      if (data.local_rolling_context !== undefined) {
        setLocalRollingContext(data.local_rolling_context);
      }
      if (data.local_thinking_enabled !== undefined) {
        setLocalThinkingEnabled(data.local_thinking_enabled);
      }
      if (data.fallback_enabled !== undefined) {
        setFallbackEnabled(data.fallback_enabled);
      }

      // Check running Ollama models in background
      try {
        const ollamaInfo = await api.getOllamaModels();
        if (ollamaInfo?.running) {
          setRunningLocalModels(ollamaInfo.running);
        }
      } catch (err) {
        // Ollama may be idle or not started
      }

      // Auto-discover available local models across Ollama, LM Studio, Jan, and disk
      try {
        const localScan = await api.getLocalModels(false);
        if (localScan?.success) {
          setLocalScanResult(localScan);
        }
      } catch (err) {
        // Local scan silent fallback
      }

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
        local_context_window: localContextWindow,
        local_rolling_context: localRollingContext,
        local_thinking_enabled: localThinkingEnabled,
        fallback_enabled: fallbackEnabled,
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

  const handleToggleFailover = async () => {
    try {
      const updated = await api.toggleFailover(!fallbackEnabled);
      setFallbackEnabled(updated.fallback_enabled);
      setSettings(updated);
    } catch (err: any) {
      alert(`Failed to toggle failover: ${err.message}`);
    }
  };

  const handleLoadModelToMemory = async (modelName: string) => {
    try {
      setLoadingLocalModel(modelName);
      setLocalActionMessage(`Loading ${modelName} into GPU VRAM / Host RAM...`);
      await api.loadOllamaModel(modelName);
      const ollamaData = await api.getOllamaModels();
      setRunningLocalModels(ollamaData.running || []);
      setLocalActionMessage(`Successfully loaded ${modelName} into active memory!`);
      setTimeout(() => setLocalActionMessage(null), 4000);
    } catch (err: any) {
      setLocalActionMessage(`Failed to load ${modelName}: ${err.message}`);
      setTimeout(() => setLocalActionMessage(null), 5000);
    } finally {
      setLoadingLocalModel(null);
    }
  };

  const handleUnloadModelFromMemory = async (modelName: string) => {
    try {
      setLoadingLocalModel(modelName);
      setLocalActionMessage(`Unloading ${modelName} from memory...`);
      await api.unloadOllamaModel(modelName);
      const ollamaData = await api.getOllamaModels();
      setRunningLocalModels(ollamaData.running || []);
      setLocalActionMessage(`Released ${modelName} from memory.`);
      setTimeout(() => setLocalActionMessage(null), 4000);
    } catch (err: any) {
      setLocalActionMessage(`Failed to unload ${modelName}: ${err.message}`);
      setTimeout(() => setLocalActionMessage(null), 5000);
    } finally {
      setLoadingLocalModel(null);
    }
  };

  const handleScanLocalModels = async (force: boolean = true) => {
    try {
      setIsScanningLocal(true);
      setLocalActionMessage("Scanning Ollama, LM Studio (server & disk), Jan, and local folders...");
      const result = await api.scanLocalModels(autoImportGguf, force);
      setLocalScanResult(result);
      setLocalActionMessage(result.message);
      // Refresh global settings to update catalog with discovered models
      const data = await api.getLLMSettings();
      setSettings(data);
    } catch (err: any) {
      console.error("Local model scan failed:", err);
      setLocalActionMessage(`Scan failed: ${err.message}`);
    } finally {
      setIsScanningLocal(false);
      setTimeout(() => setLocalActionMessage(null), 6000);
    }
  };

  const handleActivateDiscoveredModel = async (provider: string, modelId: string) => {
    try {
      setSaving(true);
      const updated = await api.updateLLMSettings({
        provider,
        model: modelId,
        local_context_window: localContextWindow,
        local_rolling_context: localRollingContext,
        local_thinking_enabled: localThinkingEnabled,
        fallback_enabled: fallbackEnabled,
      });
      setSettings(updated);
      setSelectedProvider(provider);
      setSelectedModel(modelId);
      setSaveSuccess(true);
      setLocalActionMessage(`Activated '${modelId}' as the primary inference model.`);
      setTimeout(() => setSaveSuccess(false), 3000);
      setTimeout(() => setLocalActionMessage(null), 5000);
    } catch (err: any) {
      alert(`Failed to activate model: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleImportGgufToOllama = async (fullPath: string, modelTag: string) => {
    try {
      setImportingModelPath(fullPath);
      setLocalActionMessage(`Importing '${modelTag}' into Ollama via Modelfile...`);
      const res = await api.importLocalModelToOllama(fullPath, modelTag);
      if (res.success) {
        setLocalActionMessage(`Successfully imported '${modelTag}' into Ollama!`);
        await handleScanLocalModels(true);
      } else {
        setLocalActionMessage(`Import failed: ${res.message}`);
      }
    } catch (err: any) {
      setLocalActionMessage(`Import failed: ${err.message}`);
    } finally {
      setImportingModelPath(null);
      setTimeout(() => setLocalActionMessage(null), 6000);
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
        model: "gemini-3.8-flash",
        name: "Gemini 3.8 Flash",
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
    <div className="space-y-8 max-w-7xl 2xl:max-w-[1700px] mx-auto pb-16">
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

      {/* ========================================================================= */}
      {/* INTERFACE APPEARANCE & SKIN SELECTION                                     */}
      {/* ========================================================================= */}
      <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 backdrop-blur-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Palette className="w-4 h-4 text-purple-400" />
              <span>Workspace Skin &amp; Appearance</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Select your active interface theme. Themes feature intentional contrast, balanced palettes, and sharpened box geometry.
            </p>
          </div>
          <div className="flex items-center gap-1.5 self-start sm:self-auto">
            <span className="text-[11px] text-slate-400 font-mono">Current Skin:</span>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-300 font-mono">
              {theme === "default" ? "Obsidian Midnight" : theme === "dark" ? "Graphite Dark" : "Clean Editorial"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 pt-1">
          {/* Option 1: Default (Obsidian Midnight) */}
          <button
            type="button"
            onClick={() => setTheme("default")}
            className={`p-4 rounded-xl border text-left transition-all cursor-pointer relative flex flex-col justify-between ${
              theme === "default"
                ? "bg-slate-950/90 border-blue-500 shadow-lg shadow-blue-500/15 ring-2 ring-blue-500/30"
                : "bg-slate-950/40 border-slate-800/80 hover:border-slate-700 hover:bg-slate-950/60"
            }`}
          >
            <div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <span className="font-bold text-sm text-white">Obsidian Midnight</span>
                </div>
                {theme === "default" && (
                  <CheckCircle2 className="w-4 h-4 text-blue-400 shrink-0" />
                )}
              </div>
              <p className="text-xs text-slate-400 mt-2.5 leading-relaxed">
                The original look exactly as it is. Deep midnight black canvas, central blue glow, and original curved corner geometry.
              </p>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800/60 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="w-3.5 h-3.5 rounded-full bg-[#08090c] border border-slate-700" title="#08090c Black" />
                <span className="w-3.5 h-3.5 rounded-full bg-[#183476] border border-blue-900" title="#183476 Blue Glow" />
                <span className="w-3.5 h-3.5 rounded-full bg-[#0f172a] border border-slate-700" title="#0f172a Card" />
              </div>
              <span className="text-[11px] font-mono text-slate-500">Curved (12-16px)</span>
            </div>
          </button>

          {/* Option 2: Dark Mode (Graphite & Slate - Gray & Dark Gray, Not Black) */}
          <button
            type="button"
            onClick={() => setTheme("dark")}
            className={`p-4 rounded-xl border text-left transition-all cursor-pointer relative flex flex-col justify-between ${
              theme === "dark"
                ? "bg-[#222630] border-blue-500 shadow-lg shadow-blue-500/15 ring-2 ring-blue-500/30"
                : "bg-slate-950/40 border-slate-800/80 hover:border-slate-700 hover:bg-slate-950/60"
            }`}
          >
            <div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-slate-700/30 border border-slate-600/40 text-slate-300">
                    <Moon className="w-4 h-4" />
                  </div>
                  <span className="font-bold text-sm text-white">Graphite Dark</span>
                </div>
                {theme === "dark" && (
                  <CheckCircle2 className="w-4 h-4 text-blue-400 shrink-0" />
                )}
              </div>
              <p className="text-xs text-slate-400 mt-2.5 leading-relaxed">
                Balanced gray and dark gray palette (no pure black). Crisp architectural dividing borders with sharpened 4-6px box geometry.
              </p>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800/60 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="w-3.5 h-3.5 rounded-full bg-[#181b20] border border-slate-600" title="#181b20 Neutral Gray" />
                <span className="w-3.5 h-3.5 rounded-full bg-[#222630] border border-slate-600" title="#222630 Surface Gray" />
                <span className="w-3.5 h-3.5 rounded-full bg-[#343a47] border border-slate-500" title="#343a47 Border Gray" />
              </div>
              <span className="text-[11px] font-mono text-slate-400">Sharpened (4-6px)</span>
            </div>
          </button>

          {/* Option 3: Light Mode (Clean Editorial) */}
          <button
            type="button"
            onClick={() => setTheme("light")}
            className={`p-4 rounded-xl border text-left transition-all cursor-pointer relative flex flex-col justify-between ${
              theme === "light"
                ? "bg-slate-950/90 border-blue-500 shadow-lg shadow-blue-500/15 ring-2 ring-blue-500/30"
                : "bg-slate-950/40 border-slate-800/80 hover:border-slate-700 hover:bg-slate-950/60"
            }`}
          >
            <div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-300">
                    <Sun className="w-4 h-4" />
                  </div>
                  <span className="font-bold text-sm text-white">Clean Editorial</span>
                </div>
                {theme === "light" && (
                  <CheckCircle2 className="w-4 h-4 text-blue-400 shrink-0" />
                )}
              </div>
              <p className="text-xs text-slate-400 mt-2.5 leading-relaxed">
                Crisp daylight theme with pure white surfaces, soft cool-slate canvas, high-contrast dark typography, and sharpened box geometry.
              </p>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800/60 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="w-3.5 h-3.5 rounded-full bg-[#f4f6f8] border border-slate-300" title="#f4f6f8 Canvas" />
                <span className="w-3.5 h-3.5 rounded-full bg-[#ffffff] border border-slate-300" title="#ffffff Surface" />
                <span className="w-3.5 h-3.5 rounded-full bg-[#0f172a] border border-slate-400" title="#0f172a Dark Text" />
              </div>
              <span className="text-[11px] font-mono text-slate-400">Sharpened (4-6px)</span>
            </div>
          </button>
        </div>
      </div>

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
      {/* SECTION 1.4: AUTONOMOUS LOCAL AI MODEL DISCOVERY (OLLAMA, LM STUDIO & DISK) */}
      {/* ========================================================================= */}
      <div className="p-6 rounded-xl border border-cyan-900/60 bg-gradient-to-br from-slate-950 via-slate-900/80 to-cyan-950/20 backdrop-blur-md space-y-6 shadow-xl shadow-cyan-950/10">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Brain className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <span>Autonomous Local AI Model Discovery</span>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  Zero Data Egress
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Automatically searches Ollama daemon, LM Studio local server, Jan, Hugging Face cache, and filesystem models, providing instant zero-config execution access.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none px-2.5 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800">
              <input
                type="checkbox"
                checked={autoImportGguf}
                onChange={(e) => setAutoImportGguf(e.target.checked)}
                className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0"
              />
              <span className="text-slate-300">Auto-Import Disk GGUF to Ollama</span>
            </label>

            <button
              onClick={() => handleScanLocalModels(true)}
              disabled={isScanningLocal}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-bold transition-all cursor-pointer disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-cyan-600/20"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isScanningLocal ? "animate-spin" : ""}`} />
              <span>{isScanningLocal ? "Searching Local Models..." : "Auto-Discover Local Models"}</span>
            </button>
          </div>
        </div>

        {/* Engine Probing & Detection Status Badges */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 text-xs">
          {/* 1. Ollama Daemon Status */}
          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
            <div className="space-y-1">
              <div className="text-slate-400 font-medium flex items-center gap-1.5">
                <Server className="w-3.5 h-3.5 text-emerald-400" />
                <span>Ollama Engine (:11434)</span>
              </div>
              <div className="font-semibold text-slate-200">
                {localScanResult?.providers_detected?.ollama?.running ? (
                  <span className="text-emerald-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Running (v{localScanResult.providers_detected.ollama.version || "latest"})
                  </span>
                ) : (
                  <span className="text-slate-500">Service Unreachable</span>
                )}
              </div>
            </div>
            <span className="px-2 py-0.5 rounded font-mono text-[11px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              {localScanResult?.providers_detected?.ollama?.models_count ?? 0} Models
            </span>
          </div>

          {/* 2. LM Studio Server Status */}
          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
            <div className="space-y-1">
              <div className="text-slate-400 font-medium flex items-center gap-1.5">
                <Laptop className="w-3.5 h-3.5 text-blue-400" />
                <span>LM Studio Server (:1234)</span>
              </div>
              <div className="font-semibold text-slate-200">
                {localScanResult?.providers_detected?.lmstudio?.running ? (
                  <span className="text-blue-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                    Live API Active
                  </span>
                ) : (
                  <span className="text-slate-500">Server Offline</span>
                )}
              </div>
            </div>
            <span className="px-2 py-0.5 rounded font-mono text-[11px] bg-blue-500/10 text-blue-300 border border-blue-500/20">
              {localScanResult?.providers_detected?.lmstudio?.live_models_count ?? 0} Live
            </span>
          </div>

          {/* 3. Filesystem GGUF & Repository Models */}
          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
            <div className="space-y-1">
              <div className="text-slate-400 font-medium flex items-center gap-1.5">
                <FolderSearch className="w-3.5 h-3.5 text-purple-400" />
                <span>GGUF Disk Repositories</span>
              </div>
              <div className="font-semibold text-slate-200">
                <span>~/.lmstudio, HF Cache &amp; Dirs</span>
              </div>
            </div>
            <span className="px-2 py-0.5 rounded font-mono text-[11px] bg-purple-500/10 text-purple-300 border border-purple-500/20">
              {(localScanResult?.providers_detected?.lmstudio?.disk_models_count ?? 0) +
                (localScanResult?.providers_detected?.filesystem_gguf?.count ?? 0)}{" "}
              Files
            </span>
          </div>
        </div>

        {/* Discovered Local Models Grid */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Layers className="w-3.5 h-3.5 text-cyan-400" />
              <span>Available Local AI Models ({localScanResult?.all_models?.length ?? 0})</span>
            </h3>
            {localScanResult && (
              <span className="text-[11px] text-slate-400 font-mono">
                Last Scanned: {new Date(localScanResult.scanned_at * 1000).toLocaleTimeString()}
              </span>
            )}
          </div>

          {!localScanResult || localScanResult.all_models.length === 0 ? (
            <div className="p-8 rounded-xl border border-slate-800/80 bg-slate-950/40 text-center space-y-3">
              <Search className="w-8 h-8 text-slate-600 mx-auto" />
              <div className="text-sm font-semibold text-slate-300">No local models scanned yet</div>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Click &quot;Auto-Discover Local Models&quot; to probe running Ollama or LM Studio daemons and search your disk for GGUF model files.
              </p>
              <button
                onClick={() => handleScanLocalModels(true)}
                disabled={isScanningLocal}
                className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition-all cursor-pointer inline-flex items-center gap-2"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isScanningLocal ? "animate-spin" : ""}`} />
                <span>Search Local AI Models</span>
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
              {localScanResult.all_models.map((m: DiscoveredLocalModel) => {
                const isCurrentlyActive =
                  settings.active_model.toLowerCase() === m.id.toLowerCase() &&
                  settings.active_provider.toLowerCase() === m.provider.toLowerCase();
                const isRunningInVram =
                  m.status === "running_in_vram" ||
                  runningLocalModels.some((rm) => rm.name === m.id || rm.model === m.id);

                return (
                  <div
                    key={`${m.provider}-${m.id}`}
                    className={`p-4 rounded-xl border transition-all flex flex-col justify-between space-y-3 ${
                      isCurrentlyActive
                        ? "bg-cyan-950/30 border-cyan-500/60 ring-1 ring-cyan-500/30 shadow-lg shadow-cyan-950/20"
                        : "bg-slate-950/70 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900/40"
                    }`}
                  >
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-bold text-sm text-white truncate" title={m.name}>
                          {m.name}
                        </div>
                        {isCurrentlyActive ? (
                          <span className="shrink-0 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[10px] font-mono font-bold flex items-center gap-1">
                            <Check className="w-3 h-3" />
                            ACTIVE
                          </span>
                        ) : isRunningInVram ? (
                          <span className="shrink-0 px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 text-[10px] font-mono flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                            IN VRAM
                          </span>
                        ) : (
                          <span className="shrink-0 px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 text-[10px] font-mono">
                            {m.size_gb > 0 ? `${m.size_gb} GB` : "READY"}
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                        <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300 font-mono">
                          {m.source}
                        </span>
                        {m.quantization && (
                          <span className="px-2 py-0.5 rounded bg-purple-950/50 border border-purple-800/50 text-purple-300 font-mono">
                            {m.quantization}
                          </span>
                        )}
                        <span className="px-2 py-0.5 rounded bg-blue-950/50 border border-blue-800/50 text-blue-300 font-mono uppercase">
                          {m.provider}
                        </span>
                      </div>

                      {m.full_path && (
                        <div
                          className="text-[10px] font-mono text-slate-500 truncate"
                          title={m.full_path}
                        >
                          {m.full_path}
                        </div>
                      )}
                    </div>

                    <div className="pt-2 border-t border-slate-800/60 flex items-center gap-2">
                      {isCurrentlyActive ? (
                        <div className="w-full py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Selected Primary Engine</span>
                        </div>
                      ) : (
                        <button
                          onClick={() => handleActivateDiscoveredModel(m.provider, m.id)}
                          className="flex-1 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-1.5 shadow-sm"
                        >
                          <Zap className="w-3.5 h-3.5" />
                          <span>Use Model</span>
                        </button>
                      )}

                      {/* Import to Ollama button if it is a raw disk file and not in Ollama */}
                      {m.full_path && !m.source.includes("Ollama") && (
                        <button
                          onClick={() => handleImportGgufToOllama(m.full_path!, m.id)}
                          disabled={Boolean(importingModelPath)}
                          className="px-2.5 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-300 text-xs font-medium transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1"
                          title="Import this GGUF model directly into Ollama via Modelfile"
                        >
                          {importingModelPath === m.full_path ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <HardDrive className="w-3.5 h-3.5" />
                          )}
                          <span>Import</span>
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 1.5: LOCAL ENGINE HARDWARE TUNING & PERFORMANCE OPTIMIZATIONS     */}
      {/* ========================================================================= */}
      {(selectedProvider === "ollama" || selectedProvider === "lmstudio" || settings.active_provider === "ollama" || settings.active_provider === "lmstudio") && (
        <div className="p-6 rounded-xl border border-purple-900/60 bg-gradient-to-br from-slate-950 via-slate-900/80 to-purple-950/20 backdrop-blur-md space-y-6 shadow-xl shadow-purple-950/10 animate-in fade-in">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
                <HardDrive className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <span>Local Hardware Tuning &amp; Execution Parameters</span>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    100% Private &amp; Offline
                  </span>
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Host GPU/VRAM hardware profiling, continuous rolling context memory, and small-model prompt enhancement.
                </p>
              </div>
            </div>

            {/* In-Memory VRAM Status & Pre-load / Unload Action */}
            <div className="flex items-center gap-2 self-start sm:self-auto">
              {runningLocalModels.some((m) => m.name === selectedModel || m.model === selectedModel) ? (
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono font-medium">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    Loaded in VRAM / Memory
                  </span>
                  <button
                    onClick={() => handleUnloadModelFromMemory(selectedModel)}
                    disabled={Boolean(loadingLocalModel)}
                    className="px-3 py-1 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs font-medium transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
                    title="Evict model from memory to free up VRAM"
                  >
                    {loadingLocalModel === selectedModel ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Square className="w-3.5 h-3.5" />
                    )}
                    <span>Unload Memory</span>
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-400 text-xs font-mono">
                    Cold (On Disk)
                  </span>
                  <button
                    onClick={() => handleLoadModelToMemory(selectedModel)}
                    disabled={Boolean(loadingLocalModel)}
                    className="px-3 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5 shadow-md shadow-purple-600/20"
                    title="Warm up model into GPU VRAM for instant inference response"
                  >
                    {loadingLocalModel === selectedModel ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Play className="w-3.5 h-3.5" />
                    )}
                    <span>Pre-load into VRAM</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {localActionMessage && (
            <div className="p-3 rounded-lg bg-purple-950/40 border border-purple-500/30 text-purple-200 text-xs flex items-center gap-2 animate-in fade-in">
              <Sparkles className="w-4 h-4 text-purple-400 shrink-0" />
              <span>{localActionMessage}</span>
            </div>
          )}

          {/* Live Host Hardware Profile Strip */}
          {settings.hardware_profile && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 text-xs">
              <div className="space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-medium">
                  <Cpu className="w-3.5 h-3.5 text-blue-400" />
                  <span>Host GPU Acceleration</span>
                </div>
                <div className="font-semibold text-slate-100 font-mono">
                  {settings.hardware_profile.gpus && settings.hardware_profile.gpus.length > 0
                    ? `${settings.hardware_profile.gpus[0].name} (${settings.hardware_profile.gpus[0].vram_total_gb} GB VRAM)`
                    : "CPU Only (Host RAM Fallback)"}
                </div>
              </div>

              <div className="space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-medium">
                  <Database className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Host System Memory</span>
                </div>
                <div className="font-semibold text-slate-100 font-mono">
                  {settings.hardware_profile.ram_total_gb} GB Total &bull; {settings.hardware_profile.ram_avail_gb} GB Available
                </div>
              </div>

              <div className="space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-medium">
                  <Gauge className="w-3.5 h-3.5 text-amber-400" />
                  <span>Hardware Recommendation</span>
                </div>
                <div className="font-semibold text-amber-300 font-mono">
                  {settings.hardware_profile.recommended_context_window} Tokens
                </div>
              </div>
            </div>
          )}

          {/* Tuning Controls Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* 1. Context Window Size */}
            <div className="space-y-3 p-4 rounded-xl bg-slate-950/60 border border-slate-800/70">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                  <Sliders className="w-3.5 h-3.5 text-purple-400" />
                  <span>Context Window Size (num_ctx)</span>
                </label>
                <span className="text-xs font-mono font-semibold text-purple-400 px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/20">
                  {localContextWindow} tokens
                </span>
              </div>

              <p className="text-[11px] text-slate-400 leading-relaxed">
                {settings.hardware_profile?.recommendation_reason ||
                  "Determines maximum tokens held in KV cache. 4,096 tokens fits entirely in 4GB VRAM for 70+ tokens/sec throughput."}
              </p>

              <div className="grid grid-cols-3 gap-2 pt-1">
                {[2048, 4096, 8192].map((ctx) => {
                  const isRec = settings.hardware_profile?.recommended_context_window === ctx;
                  const isCur = localContextWindow === ctx;
                  return (
                    <button
                      key={ctx}
                      type="button"
                      onClick={() => setLocalContextWindow(ctx)}
                      className={`p-2.5 rounded-lg border text-center transition-all cursor-pointer relative ${
                        isCur
                          ? "bg-purple-600/20 border-purple-500 text-purple-200 font-bold shadow-sm"
                          : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700"
                      }`}
                    >
                      <div className="text-xs font-mono">{ctx}</div>
                      <div className="text-[9px] mt-0.5 text-slate-400">
                        {ctx === 2048 ? "Fast / 2k" : ctx === 4096 ? "Optimal / 4k" : "Deep / 8k"}
                      </div>
                      {isRec && (
                        <span className="absolute -top-1.5 right-1 px-1 rounded text-[8px] bg-amber-500 text-slate-950 font-bold uppercase">
                          Rec
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 2. Rolling Context & Thinking Toggles */}
            <div className="space-y-4 p-4 rounded-xl bg-slate-950/60 border border-slate-800/70">
              {/* Rolling Context Toggle */}
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                    <span>Continuous Rolling Context</span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 font-mono">
                      OOM Protection
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    Dynamically slides the attention window across extensive CV documents, preventing Out-Of-Memory stops while retaining core profile context.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setLocalRollingContext(!localRollingContext)}
                  className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer shrink-0 mt-0.5 ${
                    localRollingContext ? "bg-purple-600" : "bg-slate-800"
                  }`}
                >
                  <span
                    className={`block w-4 h-4 rounded-full bg-white transition-transform ${
                      localRollingContext ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>

              <div className="border-t border-slate-800/80 pt-3">
                {/* Thinking Monologue Toggle */}
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                      <Brain className="w-3.5 h-3.5 text-pink-400" />
                      <span>Thinking / Reasoning Monologue</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Disabled: Strips internal &lt;think&gt; monologue for ~3x faster generation (~72 tok/s) and strict JSON extraction. Enabled: Shows step-by-step thinking traces.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setLocalThinkingEnabled(!localThinkingEnabled)}
                    className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer shrink-0 mt-0.5 ${
                      localThinkingEnabled ? "bg-purple-600" : "bg-slate-800"
                    }`}
                  >
                    <span
                      className={`block w-4 h-4 rounded-full bg-white transition-transform ${
                        localThinkingEnabled ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Local Optimization & Telemetry Badges Strip */}
          <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800/80 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="flex items-center gap-2 text-slate-300">
              <Zap className="w-4 h-4 text-amber-400 shrink-0" />
              <div>
                <span className="font-semibold text-white">~72 tokens/sec</span>
                <span className="text-[11px] text-slate-400 block">GTX 1650 Tested Speed</span>
              </div>
            </div>

            <div className="flex items-center gap-2 text-slate-300">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
              <div>
                <span className="font-semibold text-emerald-300">100% On-Device Privacy</span>
                <span className="text-[11px] text-slate-400 block">No candidate data leaves machine</span>
              </div>
            </div>

            <div className="flex items-center gap-2 text-slate-300">
              <Sparkles className="w-4 h-4 text-purple-400 shrink-0" />
              <div>
                <span className="font-semibold text-purple-300">2B Model Prompt Tuning</span>
                <span className="text-[11px] text-slate-400 block">Compact schemas &amp; strict JSON</span>
              </div>
            </div>
          </div>
        </div>
      )}

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
              onClick={handleToggleFailover}
              className={`px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5 ${
                fallbackEnabled
                  ? "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/20"
                  : "bg-slate-800 hover:bg-slate-700 text-slate-400 border-slate-700"
              }`}
              title="Enable or disable automatic cascading failover across model tiers"
            >
              <div
                className={`w-2 h-2 rounded-full ${
                  fallbackEnabled ? "bg-emerald-400" : "bg-slate-500"
                }`}
              />
              <span>Failover: {fallbackEnabled ? "Enabled" : "Disabled"}</span>
            </button>
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
                  {m.name}
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
