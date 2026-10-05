"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  TokenUsageAnalytics,
  ModelUsageStat,
  ActivityHeatmapItem,
  DailyUsageTrend,
} from "@/types";
import { api } from "@/lib/api";
import { formatTokens } from "@/components/ui/token-counter";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  BarChart3,
  Calendar,
  Check,
  ChevronDown,
  Clock,
  Cpu,
  Download,
  Filter,
  Flame,
  Gauge,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  TrendingUp,
  Zap,
} from "lucide-react";

interface TokenUsageDashboardProps {
  onRefresh?: () => void;
}

export function TokenUsageDashboard({ onRefresh }: TokenUsageDashboardProps) {
  const [analytics, setAnalytics] = useState<TokenUsageAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<"today" | "7d" | "30d" | "month" | "all">("30d");
  const [trendMetric, setTrendMetric] = useState<"total" | "input_output" | "requests">("total");
  const [hoveredTrendPoint, setHoveredTrendPoint] = useState<DailyUsageTrend | null>(null);
  const [hoveredHeatmapCell, setHoveredHeatmapCell] = useState<ActivityHeatmapItem | null>(null);
  const [modelFilter, setModelFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [resetting, setResetting] = useState(false);
  const [resetSuccess, setResetSuccess] = useState(false);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      const data = await api.getTokenUsageAnalytics(timeRange);
      setAnalytics(data);
    } catch (err) {
      console.error("Failed loading token usage analytics:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, [timeRange]);

  const handleResetData = async () => {
    if (!confirm("Are you sure you want to reset all token usage statistics? This cannot be undone.")) {
      return;
    }
    try {
      setResetting(true);
      await api.resetTokenUsage();
      setResetSuccess(true);
      setTimeout(() => setResetSuccess(false), 3000);
      await fetchAnalytics();
      onRefresh?.();
    } catch (err: any) {
      alert(`Failed to reset usage: ${err.message}`);
    } finally {
      setResetting(false);
    }
  };

  const handleExportCSV = () => {
    if (!analytics || !analytics.recent_logs) return;
    const headers = ["Timestamp", "Action", "Provider", "Model", "Input Tokens", "Output Tokens", "Total Tokens", "Latency (ms)", "Status"];
    const rows = analytics.recent_logs.map((log) => [
      log.timestamp,
      log.action,
      log.provider,
      log.model,
      log.prompt_tokens,
      log.completion_tokens,
      log.total_tokens,
      log.latency_ms,
      log.status,
    ]);
    const csvContent = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `token_usage_report_${timeRange}_${new Date().toISOString().split("T")[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Filtered logs in the detail table
  const filteredLogs = useMemo(() => {
    if (!analytics || !analytics.recent_logs) return [];
    return analytics.recent_logs.filter((log) => {
      const matchesModel =
        modelFilter === "all" ||
        log.model === modelFilter ||
        `${log.provider}:${log.model}` === modelFilter;
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        log.action.toLowerCase().includes(q) ||
        log.model.toLowerCase().includes(q) ||
        log.provider.toLowerCase().includes(q) ||
        log.model_name.toLowerCase().includes(q);
      return matchesModel && matchesSearch;
    });
  }, [analytics, modelFilter, searchQuery]);

  // Chart scaling calculations
  const trendPoints = analytics?.daily_trend || [];
  const maxTrendValue = useMemo(() => {
    if (trendPoints.length === 0) return 100;
    if (trendMetric === "requests") {
      return Math.max(...trendPoints.map((p) => p.requests), 10);
    }
    return Math.max(...trendPoints.map((p) => p.total_tokens), 1000);
  }, [trendPoints, trendMetric]);

  // Model color mapping for progress bars & tags
  const getModelColor = (provider: string, idx: number) => {
    const prov = provider.toLowerCase();
    if (prov === "agnes") return "from-blue-500 to-indigo-500 bg-blue-500 text-blue-400 border-blue-500/30";
    if (prov === "groq") return "from-orange-500 to-amber-500 bg-orange-500 text-orange-400 border-orange-500/30";
    if (prov === "gemini") return "from-purple-500 to-pink-500 bg-purple-500 text-purple-400 border-purple-500/30";
    if (prov === "openrouter") return "from-emerald-500 to-teal-500 bg-emerald-500 text-emerald-400 border-emerald-500/30";
    if (prov === "nvidia_nim") return "from-lime-500 to-green-500 bg-lime-500 text-lime-400 border-lime-500/30";
    return "from-slate-500 to-slate-400 bg-slate-500 text-slate-400 border-slate-700";
  };

  if (loading && !analytics) {
    return (
      <div className="p-16 rounded-2xl border border-slate-800 bg-slate-900/30 flex flex-col items-center justify-center gap-3 text-slate-400 text-sm">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
        <span>Loading token usage and model performance analytics...</span>
      </div>
    );
  }

  const a = analytics || {
    total_tokens: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    total_requests: 0,
    active_models_count: 0,
    avg_latency_ms: 0,
    active_days: 1,
    model_breakdown: [],
    activity_heatmap: [],
    daily_trend: [],
    recent_logs: [],
  };

  const promptPercent = a.total_tokens > 0 ? (a.prompt_tokens / a.total_tokens) * 100 : 0;
  const completionPercent = a.total_tokens > 0 ? (a.completion_tokens / a.total_tokens) * 100 : 0;

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      {/* ========================================================================= */}
      {/* 1. TOP CONTROLS & TIME RANGE RIBBON                                       */}
      {/* ========================================================================= */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400 fill-amber-400/20" />
            <span>Token Usage &amp; Multi-Model Telemetry</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Real-time token distribution, input/output breakdown, model comparisons, and activity heatmap.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Time range pills */}
          <div className="flex items-center p-1 rounded-xl bg-slate-950 border border-slate-800 text-xs">
            {(["today", "7d", "30d", "month", "all"] as const).map((range) => {
              const labels = {
                today: "Today",
                "7d": "Last 7 Days",
                "30d": "Last 30 Days",
                month: "This Month",
                all: "All Time",
              };
              const active = timeRange === range;
              return (
                <button
                  key={range}
                  onClick={() => setTimeRange(range)}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
                    active
                      ? "bg-blue-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  {labels[range]}
                </button>
              );
            })}
          </div>

          <button
            onClick={fetchAnalytics}
            className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer"
            title="Refresh statistics"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-blue-400" : ""}`} />
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. TOP SUMMARY METRIC CARDS (Matching Agnes AI Usage Cards)               */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
        {/* Card 1: Total Tokens */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Total Tokens
          </div>
          <div className="text-2xl font-extrabold text-white tracking-tight tabular-nums">
            {formatTokens(a.total_tokens)}
          </div>
          <div className="text-[11px] text-slate-400 flex items-center gap-1 font-mono">
            <span>{a.total_tokens.toLocaleString()} tokens</span>
          </div>
        </div>

        {/* Card 2: Input Tokens */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-semibold text-cyan-400 uppercase tracking-wider flex items-center gap-1">
            <ArrowDownLeft className="w-3 h-3" />
            <span>Input Tokens</span>
          </div>
          <div className="text-2xl font-extrabold text-white tracking-tight tabular-nums">
            {formatTokens(a.prompt_tokens)}
          </div>
          <div className="text-[11px] text-cyan-300/80 font-mono">
            {promptPercent.toFixed(1)}% of total
          </div>
        </div>

        {/* Card 3: Output Tokens */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
            <ArrowUpRight className="w-3 h-3" />
            <span>Output Tokens</span>
          </div>
          <div className="text-2xl font-extrabold text-white tracking-tight tabular-nums">
            {formatTokens(a.completion_tokens)}
          </div>
          <div className="text-[11px] text-emerald-300/80 font-mono">
            {completionPercent.toFixed(1)}% of total
          </div>
        </div>

        {/* Card 4: Requests */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Total Requests
          </div>
          <div className="text-2xl font-extrabold text-white tracking-tight tabular-nums">
            {a.total_requests}
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            Inference passes
          </div>
        </div>

        {/* Card 5: Active Models */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1">
            <Cpu className="w-3 h-3" />
            <span>Active Models</span>
          </div>
          <div className="text-2xl font-extrabold text-white tracking-tight tabular-nums">
            {a.active_models_count}
          </div>
          <div className="text-[11px] text-amber-300/80 font-mono">
            Across {a.active_days} day(s)
          </div>
        </div>

        {/* Card 6: Average Latency */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-semibold text-purple-400 uppercase tracking-wider flex items-center gap-1">
            <Gauge className="w-3 h-3" />
            <span>Avg Latency</span>
          </div>
          <div className="text-2xl font-extrabold text-white tracking-tight tabular-nums">
            {a.avg_latency_ms >= 1000
              ? `${(a.avg_latency_ms / 1000).toFixed(1)}s`
              : `${a.avg_latency_ms.toFixed(0)}ms`}
          </div>
          <div className="text-[11px] text-purple-300/80 font-mono">
            Per generation
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. ACTIVITY HEATMAP (Calendar Grid - Matching Agnes AI Screenshot)         */}
      {/* ========================================================================= */}
      <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-3.5 shadow-md">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Calendar className="w-4 h-4 text-emerald-400" />
              <span>Activity Calendar (Past 1 Year)</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Daily inference activity and token load distribution
            </p>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono">
            <span>Less</span>
            <div className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-slate-800/90 border border-slate-700/60" />
              <span className="w-2.5 h-2.5 rounded-sm bg-emerald-900/70 border border-emerald-800" />
              <span className="w-2.5 h-2.5 rounded-sm bg-emerald-700 border border-emerald-600" />
              <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500 border border-emerald-400" />
              <span className="w-2.5 h-2.5 rounded-sm bg-emerald-400 border border-emerald-300" />
            </div>
            <span>More</span>
          </div>
        </div>

        {/* Heatmap Grid */}
        <div className="overflow-x-auto pb-2">
          <div className="min-w-[720px] space-y-2">
            {/* Heatmap Squares Grid (approx 52 columns x 7 rows) */}
            <div className="grid grid-flow-col grid-rows-7 gap-1">
              {a.activity_heatmap.map((cell, idx) => {
                const levelColors = [
                  "bg-slate-800/80 hover:bg-slate-700 border-slate-800",
                  "bg-emerald-950 border-emerald-800/70 hover:bg-emerald-900",
                  "bg-emerald-700 border-emerald-600 hover:bg-emerald-600",
                  "bg-emerald-500 border-emerald-400 hover:bg-emerald-400",
                  "bg-emerald-400 border-emerald-300 hover:bg-emerald-300 shadow-sm shadow-emerald-500/30",
                ];
                return (
                  <div
                    key={cell.date || idx}
                    onMouseEnter={() => setHoveredHeatmapCell(cell)}
                    onMouseLeave={() => setHoveredHeatmapCell(null)}
                    className={`w-3.5 h-3.5 rounded-sm border transition-all cursor-pointer ${
                      levelColors[cell.level] || levelColors[0]
                    }`}
                    title={`${cell.date}: ${cell.count} requests (${cell.tokens.toLocaleString()} tokens)`}
                  />
                );
              })}
            </div>

            {/* Hover tooltip bar */}
            <div className="h-6 flex items-center justify-between text-xs text-slate-400 font-mono pt-1">
              {hoveredHeatmapCell ? (
                <div className="text-white font-medium flex items-center gap-2">
                  <span className="text-emerald-400">📅 {hoveredHeatmapCell.date}</span>
                  <span className="text-slate-600">•</span>
                  <span>{hoveredHeatmapCell.count} requests</span>
                  <span className="text-slate-600">•</span>
                  <span className="text-amber-300 font-bold">{hoveredHeatmapCell.tokens.toLocaleString()} tokens</span>
                </div>
              ) : (
                <span className="text-slate-500 text-[11px]">Hover over any day square to inspect daily tokens and requests</span>
              )}
              <span className="text-slate-500 text-[11px]">365-Day Rolling Window</span>
            </div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 4. USAGE TREND GRAPH (Interactive Line / Area Chart)                      */}
      {/* ========================================================================= */}
      <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-4 shadow-md">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-400" />
              <span>Usage Trend</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Historical token consumption curve across the selected interval
            </p>
          </div>

          {/* Metric toggle */}
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-950 border border-slate-800 text-xs">
            <button
              onClick={() => setTrendMetric("total")}
              className={`px-3 py-1 rounded-lg font-medium transition-all cursor-pointer ${
                trendMetric === "total"
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Total Tokens
            </button>
            <button
              onClick={() => setTrendMetric("input_output")}
              className={`px-3 py-1 rounded-lg font-medium transition-all cursor-pointer ${
                trendMetric === "input_output"
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Input vs Output
            </button>
            <button
              onClick={() => setTrendMetric("requests")}
              className={`px-3 py-1 rounded-lg font-medium transition-all cursor-pointer ${
                trendMetric === "requests"
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Requests
            </button>
          </div>
        </div>

        {/* SVG Area Chart */}
        <div className="relative h-60 w-full pt-4">
          {trendPoints.length === 0 ? (
            <div className="h-full flex items-center justify-center text-xs text-slate-500">
              No usage data available for this time range.
            </div>
          ) : (
            <div className="h-full flex flex-col justify-between">
              {/* Chart Canvas */}
              <div className="relative flex-1">
                <svg
                  className="w-full h-full overflow-visible cursor-crosshair"
                  preserveAspectRatio="none"
                  viewBox="0 0 1000 200"
                  onMouseMove={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    if (rect.width <= 0 || trendPoints.length === 0) return;
                    const relX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                    const count = trendPoints.length;
                    const step = count > 1 ? 1 / (count - 1) : 1;
                    const nearestIdx = Math.max(0, Math.min(count - 1, Math.round(relX / step)));
                    setHoveredTrendPoint(trendPoints[nearestIdx]);
                  }}
                  onMouseLeave={() => setHoveredTrendPoint(null)}
                >
                  <defs>
                    <linearGradient id="tokenGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.35" />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                    </linearGradient>
                    <linearGradient id="outputGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity="0.30" />
                      <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>

                  {/* Horizontal grid lines */}
                  {[0, 50, 100, 150].map((y) => (
                    <line
                      key={y}
                      x1="0"
                      y1={y}
                      x2="1000"
                      y2={y}
                      stroke="#334155"
                      strokeDasharray="4 4"
                      strokeWidth="0.8"
                    />
                  ))}

                  {/* Data Path */}
                  {(() => {
                    const count = trendPoints.length;
                    const step = count > 1 ? 1000 / (count - 1) : 1000;

                    const totalPoints = trendPoints.map((p, idx) => {
                      const val = trendMetric === "requests" ? p.requests : p.total_tokens;
                      const y = 190 - (val / (maxTrendValue || 1)) * 170;
                      return `${idx * step},${y}`;
                    });

                    const pathStr = totalPoints.join(" ");
                    const areaStr = `0,190 ${pathStr} 1000,190`;

                    const hoveredIdx = hoveredTrendPoint
                      ? trendPoints.findIndex((p) => p.date === hoveredTrendPoint.date)
                      : -1;

                    return (
                      <>
                        <polygon points={areaStr} fill="url(#tokenGradient)" />
                        <polyline
                          fill="none"
                          stroke="#3b82f6"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          points={pathStr}
                        />

                        {/* Vertical guideline for hovered point */}
                        {hoveredIdx !== -1 && (
                          <line
                            x1={hoveredIdx * step}
                            y1="0"
                            x2={hoveredIdx * step}
                            y2="190"
                            stroke="#60a5fa"
                            strokeWidth="1.5"
                            strokeDasharray="4 4"
                            opacity="0.8"
                          />
                        )}

                        {/* Interactive hover circles with large hit targets */}
                        {trendPoints.map((p, idx) => {
                          const val = trendMetric === "requests" ? p.requests : p.total_tokens;
                          const cx = idx * step;
                          const cy = 190 - (val / (maxTrendValue || 1)) * 170;
                          const isHovered = hoveredTrendPoint?.date === p.date;

                          return (
                            <g key={idx} className="cursor-pointer">
                              {/* Large transparent hit circle so hovering is reliable */}
                              <circle
                                cx={cx}
                                cy={cy}
                                r="22"
                                fill="transparent"
                                onMouseEnter={() => setHoveredTrendPoint(p)}
                              />
                              {/* Outer halo when active */}
                              {isHovered && (
                                <circle
                                  cx={cx}
                                  cy={cy}
                                  r="13"
                                  className="fill-amber-400/20 stroke-amber-400/60 stroke-1 animate-pulse"
                                />
                              )}
                              {/* Core dot */}
                              <circle
                                cx={cx}
                                cy={cy}
                                r={isHovered ? "7" : "4.5"}
                                className={`transition-all duration-150 ${
                                  isHovered
                                    ? "fill-amber-400 stroke-white stroke-2 shadow-lg"
                                    : "fill-blue-500 stroke-white stroke-1"
                                }`}
                              />
                            </g>
                          );
                        })}
                      </>
                    );
                  })()}
                </svg>
              </div>

              {/* X-axis date labels */}
              <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono pt-3 border-t border-slate-800">
                {trendPoints.filter((_, i) => i % Math.max(1, Math.floor(trendPoints.length / 7)) === 0).map((p, i) => (
                  <span key={i}>{p.label}</span>
                ))}
              </div>
            </div>
          )}

          {/* Hover Tooltip Card (pointer-events-none prevents flicker/hover conflicts) */}
          {hoveredTrendPoint && (
            <div className="absolute top-2 right-4 p-3.5 rounded-xl bg-slate-900/95 backdrop-blur-md border border-blue-500/50 shadow-2xl text-xs space-y-1.5 z-30 animate-in fade-in pointer-events-none min-w-[210px]">
              <div className="font-bold text-white flex items-center justify-between gap-2 border-b border-slate-800 pb-1">
                <span className="flex items-center gap-1.5 text-blue-400 font-semibold">
                  <Calendar className="w-3.5 h-3.5" />
                  <span>{hoveredTrendPoint.label}</span>
                </span>
                <span className="text-[10px] font-mono text-slate-400">({hoveredTrendPoint.date})</span>
              </div>
              <div className="text-slate-300 font-mono text-[11px] space-y-1 pt-0.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-400">Total Tokens:</span>
                  <span className="font-bold text-amber-300">{hoveredTrendPoint.total_tokens.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-cyan-400">Input Tokens:</span>
                  <span>{hoveredTrendPoint.prompt_tokens.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-emerald-400">Output Tokens:</span>
                  <span>{hoveredTrendPoint.completion_tokens.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-400">Total Requests:</span>
                  <span className="font-semibold text-white">{hoveredTrendPoint.requests}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 5. MODEL BREAKDOWN & PERFORMANCE COMPARISONS (Which models consume most) */}
      {/* ========================================================================= */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-indigo-400" />
              <span>Model Consumption &amp; Performance Ranking</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Ranked breakdown tracking which models consume the most tokens, input vs output distribution, and latency.
            </p>
          </div>

          <span className="text-xs font-mono text-slate-500">
            {a.model_breakdown.length} models tracked
          </span>
        </div>

        {/* Stacked Comparative Bar / Proportional Meter */}
        {a.total_tokens > 0 && (
          <div className="space-y-1.5 p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
              <span>Platform Token Distribution</span>
              <span className="text-slate-500 font-mono">100% of {formatTokens(a.total_tokens)}</span>
            </div>
            <div className="h-3 w-full rounded-full bg-slate-800 overflow-hidden flex">
              {a.model_breakdown.map((m, idx) => (
                <div
                  key={m.model_key}
                  style={{ width: `${Math.max(1, m.percentage_of_total)}%` }}
                  className={`h-full transition-all bg-gradient-to-r ${getModelColor(m.provider, idx)}`}
                  title={`${m.name}: ${m.percentage_of_total}% (${m.total_tokens.toLocaleString()} tokens)`}
                />
              ))}
            </div>
          </div>
        )}

        {/* Model Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {a.model_breakdown.map((m, idx) => {
            return (
              <div
                key={m.model_key}
                className="p-5 rounded-2xl border border-slate-800 bg-slate-900/60 hover:border-slate-700/80 transition-all space-y-4 shadow-sm"
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300">
                        #{idx + 1}
                      </span>
                      <h4 className="font-bold text-sm text-white">
                        {m.name}
                      </h4>
                      <span className="text-[10px] font-mono text-slate-400 px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700/60">
                        {m.provider}
                      </span>
                      {m.free && (
                        <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          FREE
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] font-mono text-slate-400">
                      ID: {m.model}
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <div className="text-base font-extrabold text-amber-300 font-mono">
                      {formatTokens(m.total_tokens)}
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono">
                      {m.percentage_of_total}% share
                    </div>
                  </div>
                </div>

                {/* Progress bar for share */}
                <div className="space-y-1">
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full"
                      style={{ width: `${Math.min(100, m.percentage_of_total)}%` }}
                    />
                  </div>
                </div>

                {/* KPI Breakdown Matrix */}
                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-800 text-xs font-mono">
                  {/* Input / Output */}
                  <div className="space-y-0.5">
                    <span className="text-[10px] text-slate-500 uppercase block">Input / Output</span>
                    <div className="text-slate-300 text-[11px]">
                      <span className="text-cyan-400">{formatTokens(m.prompt_tokens)}</span>
                      <span className="text-slate-600"> / </span>
                      <span className="text-emerald-400">{formatTokens(m.completion_tokens)}</span>
                    </div>
                  </div>

                  {/* Requests */}
                  <div className="space-y-0.5">
                    <span className="text-[10px] text-slate-500 uppercase block">Requests</span>
                    <div className="text-slate-300 text-[11px]">
                      {m.requests} calls
                    </div>
                  </div>

                  {/* Latency */}
                  <div className="space-y-0.5">
                    <span className="text-[10px] text-slate-500 uppercase block">Avg Latency</span>
                    <div className="text-purple-300 text-[11px]">
                      {m.avg_latency_ms >= 1000
                        ? `${(m.avg_latency_ms / 1000).toFixed(1)}s`
                        : `${m.avg_latency_ms}ms`}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}

          {a.model_breakdown.length === 0 && (
            <div className="col-span-2 p-8 rounded-xl border border-slate-800 bg-slate-900/30 text-center text-slate-400 text-xs">
              No models recorded for this interval yet. Run an evaluation, CV extraction, or ping test to view usage telemetry.
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 6. USAGE DETAILS & AUDIT LOGS TABLE (Matching Agnes AI Table)              */}
      {/* ========================================================================= */}
      <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-4 shadow-md">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-blue-400" />
              <span>Usage Details Table</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Auditable transaction logs of every inference call
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={handleExportCSV}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold transition-colors cursor-pointer"
              title="Download CSV export"
            >
              <Download className="w-3.5 h-3.5 text-blue-400" />
              <span>Export CSV</span>
            </button>

            <button
              onClick={handleResetData}
              disabled={resetting}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-950/60 hover:bg-rose-900/70 border border-rose-500/30 text-rose-200 text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50"
              title="Clear all recorded token usage data"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-400" />
              <span>Reset Data</span>
            </button>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="relative md:col-span-2">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by action, model, or provider..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <select
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500 cursor-pointer"
            >
              <option value="all">Filter by model (All Models)</option>
              {a.model_breakdown.map((m) => (
                <option key={m.model_key} value={m.model}>
                  {m.name} ({m.provider})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Transaction Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                <th className="py-2.5 px-3">Timestamp</th>
                <th className="py-2.5 px-3">Action / Feature</th>
                <th className="py-2.5 px-3">Model</th>
                <th className="py-2.5 px-3 text-right">Input Tokens</th>
                <th className="py-2.5 px-3 text-right">Output Tokens</th>
                <th className="py-2.5 px-3 text-right">Total Tokens</th>
                <th className="py-2.5 px-3 text-right">Latency</th>
                <th className="py-2.5 px-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filteredLogs.map((log, idx) => (
                <tr key={log.id || idx} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-2 px-3 text-slate-400 text-[11px] whitespace-nowrap">
                    {log.timestamp}
                  </td>
                  <td className="py-2 px-3 text-white font-sans font-medium capitalize">
                    {log.action?.replace(/_/g, " ")}
                  </td>
                  <td className="py-2 px-3">
                    <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300 text-[11px]">
                      {log.model_name || log.model}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right text-cyan-400">
                    {log.prompt_tokens?.toLocaleString() || 0}
                  </td>
                  <td className="py-2 px-3 text-right text-emerald-400">
                    {log.completion_tokens?.toLocaleString() || 0}
                  </td>
                  <td className="py-2 px-3 text-right font-bold text-amber-300">
                    {log.total_tokens?.toLocaleString() || 0}
                  </td>
                  <td className="py-2 px-3 text-right text-slate-300">
                    {log.latency_ms >= 1000 ? `${(log.latency_ms / 1000).toFixed(1)}s` : `${log.latency_ms}ms`}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                        log.status === "success"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : log.status === "failover"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                      }`}
                    >
                      {log.status}
                    </span>
                  </td>
                </tr>
              ))}

              {filteredLogs.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500 font-sans">
                    No matching log transactions found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
