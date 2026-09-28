"use client";

import { useState, useEffect } from "react";
import { LLMSettings } from "@/types";
import { api } from "@/lib/api";
import {
  Activity,
  Check,
  CheckCircle2,
  Cpu,
  Gauge,
  Key,
  Layers,
  Loader2,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  Zap,
} from "lucide-react";

export function SettingsView() {
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedProvider, setSelectedProvider] = useState<string>("openrouter");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Latency test state
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
      const models = Object.keys(settings.providers_catalog[prov].models || {});
      if (models.length > 0) {
        setSelectedModel(models[0]);
      }
    }
  };

  const handleSaveSettings = async () => {
    try {
      setSaving(true);
      await api.updateLLMSettings({
        provider: selectedProvider,
        model: selectedModel,
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      await fetchSettings();
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

  if (loading || !settings) {
    return (
      <div className="p-12 flex flex-col items-center justify-center gap-3 text-slate-500 text-xs">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
        <span>Loading model configurations and API provider registry...</span>
      </div>
    );
  }

  const currentProviderInfo = settings.providers_catalog[selectedProvider] || {};
  const availableModels = Object.keys(currentProviderInfo.models || {});

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
          <span>Model Architecture & Failover Settings</span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Dynamically route prompts between cloud frontier models and local private instances (Ollama) with automatic multi-tier failover.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left: Active Provider Selector */}
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 px-1">
            LLM Provider
          </div>
          <div className="space-y-1.5">
            {Object.keys(settings.providers_catalog).map((provKey) => {
              const prov = settings.providers_catalog[provKey];
              const isConfigured = settings.api_keys_configured[provKey];
              const isSelected = selectedProvider === provKey;

              return (
                <button
                  key={provKey}
                  onClick={() => handleProviderChange(provKey)}
                  className={`w-full text-left p-3 rounded-xl border transition-all flex items-center justify-between ${
                    isSelected
                      ? "bg-slate-900 border-blue-500/50 shadow-md shadow-blue-500/5"
                      : "bg-slate-950 border-slate-800/80 hover:border-slate-700"
                  }`}
                >
                  <div className="space-y-0.5">
                    <div className="font-semibold text-xs text-white">
                      {prov.name}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {Object.keys(prov.models || {}).length} models available
                    </div>
                  </div>

                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-mono ${
                      isConfigured
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-slate-800 text-slate-500"
                    }`}
                  >
                    {isConfigured ? "Key Active" : "No Key"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Model Selection & Ping Benchmark */}
        <div className="md:col-span-2 space-y-4">
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-5">
            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-300">
                Target Model Identifier
              </label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            {/* Provider Details */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 text-xs space-y-2">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">Default Context Window:</span>
                <span className="text-slate-200 font-mono">128k tokens</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">Structured JSON Mode:</span>
                <span className="text-blue-400 font-mono font-medium">Native JSON Schema</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">Failover Enabled:</span>
                <span className="text-emerald-400 font-mono font-medium">True (Automatic failover)</span>
              </div>
            </div>

            {/* Actions: Save & Benchmark */}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleSaveSettings}
                disabled={saving}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-all cursor-pointer disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Check className="w-3.5 h-3.5" />
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
                <span>Active model configuration updated dynamically!</span>
              </div>
            )}

            {/* Ping Result Box */}
            {pingResult && (
              <div
                className={`p-3.5 rounded-lg border text-xs space-y-1.5 animate-in fade-in ${
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
                    <span>{pingResult.status === "ok" ? "Connection Verified" : "Ping Error"}</span>
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
  );
}
