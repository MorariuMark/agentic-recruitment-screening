"""
backend/schemas/token_usage.py
Pydantic contracts for token tracking, live token counters, model performance metrics,
and Agnes-style usage analytics dashboards.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TokenUsageInfo(BaseModel):
    """Token consumption and latency details for an individual LLM action."""
    provider: str = Field(description="LLM provider: agnes, groq, gemini, openrouter, nvidia_nim, ollama")
    model: str = Field(description="Exact model identifier")
    display_name: Optional[str] = Field(default=None, description="Human-readable model name")
    prompt_tokens: int = Field(default=0, description="Input / prompt tokens")
    completion_tokens: int = Field(default=0, description="Output / completion tokens")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    latency_ms: float = Field(default=0.0, description="Execution duration in milliseconds")
    status: str = Field(default="success", description="Status: success, failover, error")


class ModelUsageStat(BaseModel):
    """Aggregated token usage and performance metrics for a specific model."""
    model_key: str = Field(description="Unique identifier: provider:model")
    provider: str = Field(description="Provider slug")
    model: str = Field(description="Model identifier")
    name: str = Field(description="Friendly model name")
    prompt_tokens: int = Field(default=0, description="Total input tokens")
    completion_tokens: int = Field(default=0, description="Total output tokens")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    requests: int = Field(default=0, description="Total successful requests")
    percentage_of_total: float = Field(default=0.0, description="Share of total platform token consumption (0-100%)")
    avg_latency_ms: float = Field(default=0.0, description="Average response latency in milliseconds")
    tokens_per_second: float = Field(default=0.0, description="Estimated throughput (tokens / sec)")
    free: bool = Field(default=True, description="Whether available on free tier")


class ActivityHeatmapItem(BaseModel):
    """Activity cell for the calendar heatmap (GitHub / Agnes AI style)."""
    date: str = Field(description="Date formatted YYYY-MM-DD")
    count: int = Field(default=0, description="Number of LLM requests on this date")
    tokens: int = Field(default=0, description="Total tokens consumed on this date")
    level: int = Field(default=0, ge=0, le=4, description="Activity intensity level from 0 (none) to 4 (peak)")


class DailyUsageTrend(BaseModel):
    """Time-series data point for token usage trend charts."""
    date: str = Field(description="YYYY-MM-DD")
    label: str = Field(description="Human display label (e.g. 'Oct 5' or '14:00')")
    prompt_tokens: int = Field(default=0, description="Input tokens")
    completion_tokens: int = Field(default=0, description="Output tokens")
    total_tokens: int = Field(default=0, description="Total tokens")
    requests: int = Field(default=0, description="Number of requests")


class TokenUsageAnalytics(BaseModel):
    """Complete analytics payload for the Settings Token Usage & Model Statistics dashboard."""
    total_tokens: int = Field(default=0, description="Total tokens consumed across all models")
    prompt_tokens: int = Field(default=0, description="Total prompt / input tokens")
    completion_tokens: int = Field(default=0, description="Total completion / output tokens")
    total_requests: int = Field(default=0, description="Total LLM API requests executed")
    active_models_count: int = Field(default=0, description="Number of unique models used")
    avg_latency_ms: float = Field(default=0.0, description="Platform average latency in milliseconds")
    active_days: int = Field(default=1, description="Number of active days with LLM calls")
    model_breakdown: List[ModelUsageStat] = Field(default_factory=list, description="Usage breakdown sorted by token volume")
    activity_heatmap: List[ActivityHeatmapItem] = Field(default_factory=list, description="Annual/monthly activity calendar grid")
    daily_trend: List[DailyUsageTrend] = Field(default_factory=list, description="Trend points for the selected time range")
    recent_logs: List[Dict[str, Any]] = Field(default_factory=list, description="Recent execution logs for detailed auditing")
