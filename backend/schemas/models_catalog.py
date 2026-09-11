"""
backend/schemas/models_catalog.py
Comprehensive catalog of free and production models across Groq, OpenRouter,
NVIDIA NIM, Google Gemini, and local Ollama, including real-time rate limits,
context windows, and schema compatibility definitions.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    id: str = Field(description="Exact model identifier for API calls")
    name: str = Field(description="Human readable display name")
    provider: str = Field(description="Provider slug: groq, openrouter, nvidia_nim, gemini, ollama")
    free: bool = Field(default=True, description="Whether available on free tier")
    rate_limits: str = Field(description="Display string of RPM, TPM, RPD, or TPD rate limits")
    context_window: str = Field(description="Max context token size")
    category: str = Field(description="General, Reasoning, Fast, Coding")
    compatibility: str = Field(default="Native JSON Object Mode", description="Supported structured output mode")
    description: Optional[str] = Field(default=None, description="Short summary of model capabilities")

    @property
    def display_label(self) -> str:
        free_badge = " [FREE]" if self.free else ""
        return f"{self.id} — {self.name}{free_badge} ({self.rate_limits} | Ctx: {self.context_window})"


class ProviderInfo(BaseModel):
    id: str
    name: str
    icon: str
    description: str
    api_key_url: str
    default_model: str
    default_base_url: Optional[str] = None
    env_key_var: str
    models: List[ModelInfo]


# ---------------------------------------------------------------------------
# Provider & Model Catalog Definitions
# ---------------------------------------------------------------------------

CATALOG_PROVIDERS: Dict[str, ProviderInfo] = {
    "groq": ProviderInfo(
        id="groq",
        name="Groq Cloud LPU",
        icon="⚡",
        description="Ultra-fast LPUs with free on-demand quotas for open models.",
        api_key_url="https://console.groq.com/keys",
        default_model="openai/gpt-oss-20b",
        default_base_url="https://api.groq.com/openai/v1",
        env_key_var="GROQ_API_KEY",
        models=[
            ModelInfo(
                id="openai/gpt-oss-20b",
                name="GPT-OSS 20B (OpenAI)",
                provider="groq",
                free=True,
                rate_limits="30 RPM | 8,000 TPM | 200,000 TPD",
                context_window="128k",
                category="Fast / General",
                compatibility="Native JSON Object Mode",
                description="High throughput, clean structured JSON extraction with generous daily quota.",
            ),
            ModelInfo(
                id="qwen/qwen3.8-27b",
                name="Qwen 3.8 27B",
                provider="groq",
                free=True,
                rate_limits="30 RPM | 6,000 TPM | 500,000 TPD",
                context_window="128k",
                category="Multilingual / Strong",
                compatibility="Native JSON Object Mode",
                description="Top multilingual comprehension across English, Romanian, French, German.",
            ),
            ModelInfo(
                id="openai/gpt-oss-120b",
                name="GPT-OSS 120B (OpenAI)",
                provider="groq",
                free=True,
                rate_limits="30 RPM | 8,000 TPM | 200,000 TPD",
                context_window="128k",
                category="Reasoning / Heavy",
                compatibility="Native JSON Object Mode",
                description="Flagship open weights model for complex semantic decomposition.",
            ),
            ModelInfo(
                id="llama-3.3-70b-versatile",
                name="Llama 3.3 70B Versatile",
                provider="groq",
                free=True,
                rate_limits="30 RPM | 6,000 TPM | 100,000 TPD",
                context_window="128k",
                category="General",
                compatibility="Native JSON Object Mode",
                description="Meta's top general-purpose model hosted on Groq LPUs.",
            ),
            ModelInfo(
                id="llama-3.1-8b-instant",
                name="Llama 3.1 8B Instant",
                provider="groq",
                free=True,
                rate_limits="30 RPM | 6,000 TPM | 500,000 TPD",
                context_window="128k",
                category="Ultra-Fast",
                compatibility="Native JSON Object Mode",
                description="Sub-second latency model for lightweight entity extraction.",
            ),
            ModelInfo(
                id="allam-2-7b",
                name="Allam 2 7B",
                provider="groq",
                free=True,
                rate_limits="30 RPM | 6,000 TPM | 500,000 TPD",
                context_window="32k",
                category="Lightweight",
                compatibility="Native JSON Object Mode",
                description="SDAIA compact multilingual model.",
            ),
            ModelInfo(
                id="groq/compound",
                name="Groq Compound Router",
                provider="groq",
                free=True,
                rate_limits="15 RPM | 5,000 TPM | 100,000 TPD",
                context_window="128k",
                category="Agentic Router",
                compatibility="Compound Output",
                description="Groq's compound agentic reasoning framework.",
            ),
        ],
    ),
    "openrouter": ProviderInfo(
        id="openrouter",
        name="OpenRouter (Free Tier)",
        icon="🌐",
        description="Universal gateway with 20+ completely free community open-source models (:free).",
        api_key_url="https://openrouter.ai/keys",
        default_model="openrouter/free",
        default_base_url="https://openrouter.ai/api/v1",
        env_key_var="OPENROUTER_API_KEY",
        models=[
            ModelInfo(
                id="openrouter/free",
                name="OpenRouter Free Router",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="128k",
                category="Auto-Router",
                compatibility="OpenAI JSON Mode & Schema Prompt",
                description="Dynamic auto-routing to the highest-availability active free models on OpenRouter.",
            ),
            ModelInfo(
                id="nvidia/nemotron-3.5-lightning:free",
                name="NVIDIA Nemotron 3.5 Lightning (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="1,000,000",
                category="1M Context",
                compatibility="OpenAI JSON Mode",
                description="Ultra-long 1M token context for massive multi-document analysis.",
            ),
            ModelInfo(
                id="nvidia/nemotron-3-super-120b-a12b:free",
                name="NVIDIA Nemotron 3 Super 120B (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="262k",
                category="Heavy Enterprise",
                compatibility="OpenAI JSON Mode",
                description="NVIDIA 120B MoE model tuned for enterprise reasoning and extraction.",
            ),
            ModelInfo(
                id="nvidia/nemotron-3-ultra-550b-a55b:free",
                name="NVIDIA Nemotron 3 Ultra 550B (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="262k",
                category="Giant MoE",
                compatibility="OpenAI JSON Mode",
                description="Colossal 550B MoE architecture hosted for free on OpenRouter.",
            ),
            ModelInfo(
                id="google/gemma-4-31b-it:free",
                name="Google Gemma 4 31B (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="262k",
                category="Google / Multilingual",
                compatibility="OpenAI JSON Mode",
                description="Google's dense open-weights architecture with 262k context.",
            ),
            ModelInfo(
                id="google/gemma-4-26b-a4b-it:free",
                name="Google Gemma 4 26B A4B (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="262k",
                category="Google Fast",
                compatibility="OpenAI JSON Mode",
                description="High-speed Mixture-of-Experts Gemma architecture.",
            ),
            ModelInfo(
                id="cohere/north-mini-code:free",
                name="Cohere North Mini Code (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="256k",
                category="Fast / Code",
                compatibility="OpenAI JSON Mode",
                description="Cohere compact coding model with 256k context.",
            ),
            ModelInfo(
                id="liquid/lfm-2.5-2.6b:free",
                name="Liquid LFM 2.5 2.6B (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="32k",
                category="Ultra-Fast",
                compatibility="OpenAI JSON Mode",
                description="Liquid Foundation Model optimized for rapid inference.",
            ),
            ModelInfo(
                id="poolside/laguna-s-2.1:free",
                name="Poolside Laguna S 2.1 (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="64k",
                category="Coding / Technical",
                compatibility="OpenAI JSON Mode",
                description="Specialized code intelligence and requirement breakdown.",
            ),
            ModelInfo(
                id="nex-agi/nex-n2.5-mini:free",
                name="NEX N2.5 Mini (Free)",
                provider="openrouter",
                free=True,
                rate_limits="20 RPM | 200 RPD",
                context_window="64k",
                category="Lightweight Reasoning",
                compatibility="OpenAI JSON Mode",
                description="Compact instruction following model for parsing tasks.",
            ),
        ],
    ),
    "nvidia_nim": ProviderInfo(
        id="nvidia_nim",
        name="NVIDIA NIM Microservices",
        icon="🟢",
        description="NVIDIA AI Foundation Endpoints optimized on DGX Cloud with free developer credits.",
        api_key_url="https://build.nvidia.com/",
        default_model="meta/llama-3.2-11b-vision-instruct",
        default_base_url="https://integrate.api.nvidia.com/v1",
        env_key_var="NVIDIA_NIM_API_KEY",
        models=[
            ModelInfo(
                id="meta/llama-3.2-11b-vision-instruct",
                name="Llama 3.2 11B Vision Instruct (NIM)",
                provider="nvidia_nim",
                free=True,
                rate_limits="40 RPM | 4,000 TPM | 1,000 trial credits",
                context_window="128k",
                category="High Speed / General",
                compatibility="NVIDIA OpenAI JSON Mode",
                description="Ultra-fast Llama 3.2 11B optimized for rapid structured CV entity extraction.",
            ),
            ModelInfo(
                id="nvidia/nemotron-3.5-lightning-30b-a3b",
                name="NVIDIA Nemotron 3.5 Lightning 30B (NIM)",
                provider="nvidia_nim",
                free=True,
                rate_limits="40 RPM | 4,000 TPM | 1,000 trial credits",
                context_window="128k",
                category="Reasoning & Extraction",
                compatibility="NVIDIA OpenAI JSON Mode",
                description="NVIDIA MoE reasoning model fine-tuned for high precision candidate evaluation.",
            ),
            ModelInfo(
                id="nvidia/nemotron-3-super-120b-a12b",
                name="NVIDIA Nemotron 3 Super 120B (NIM)",
                provider="nvidia_nim",
                free=True,
                rate_limits="40 RPM | 4,000 TPM | 1,000 trial credits",
                context_window="262k",
                category="Enterprise MoE",
                compatibility="NVIDIA OpenAI JSON Mode",
                description="NVIDIA 120B MoE flagship for enterprise candidate and requirement mapping.",
            ),
            ModelInfo(
                id="nvidia/nemotron-3-ultra-550b-a55b",
                name="NVIDIA Nemotron 3 Ultra 550B (NIM)",
                provider="nvidia_nim",
                free=True,
                rate_limits="20 RPM | 2,000 TPM | 1,000 trial credits",
                context_window="262k",
                category="Giant MoE",
                compatibility="NVIDIA OpenAI JSON Mode",
                description="Massive 550B parameter model for deep cross-discipline evaluation.",
            ),
            ModelInfo(
                id="meta/llama-3.2-90b-vision-instruct",
                name="Llama 3.2 90B Vision Instruct (NIM)",
                provider="nvidia_nim",
                free=True,
                rate_limits="20 RPM | 2,000 TPM | 1,000 trial credits",
                context_window="128k",
                category="Heavy Reasoning",
                compatibility="NVIDIA OpenAI JSON Mode",
                description="Meta's top-tier 90B architecture for complex semantic reasoning.",
            ),
        ],
    ),
    "gemini": ProviderInfo(
        id="gemini",
        name="Google Gemini (AI Studio)",
        icon="✨",
        description="Google AI Studio Free Tier with 1M-2M context windows and generous 1,500 RPD quotas.",
        api_key_url="https://aistudio.google.com/app/apikey",
        default_model="gemini-flash-latest",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        env_key_var="GEMINI_API_KEY",
        models=[
            ModelInfo(
                id="gemini-flash-latest",
                name="Gemini Flash (Latest Stable)",
                provider="gemini",
                free=True,
                rate_limits="15 RPM | 1,000,000 TPM | 1,500 RPD",
                context_window="1,000,000",
                category="Flagship Speed & Reasoning",
                compatibility="Google AI Studio OpenAI Endpoint",
                description="Google's canonical fast multimodal model with 1M token context.",
            ),
            ModelInfo(
                id="gemini-flash-lite-latest",
                name="Gemini Flash-Lite (High Throughput)",
                provider="gemini",
                free=True,
                rate_limits="30 RPM | 1,000,000 TPM | 1,500 RPD",
                context_window="1,000,000",
                category="High Throughput (30 RPM)",
                compatibility="Google AI Studio OpenAI Endpoint",
                description="30 RPM doubled rate limit for rapid CV parsing without quota throttling.",
            ),
            ModelInfo(
                id="gemini-3.5-flash-lite",
                name="Gemini 3.5 Flash-Lite",
                provider="gemini",
                free=True,
                rate_limits="30 RPM | 1,000,000 TPM | 1,500 RPD",
                context_window="1,000,000",
                category="Ultra-Fast",
                compatibility="Google AI Studio OpenAI Endpoint",
                description="High throughput generation for high-volume candidate screening.",
            ),
            ModelInfo(
                id="gemini-3.6-flash",
                name="Gemini 3.6 Flash",
                provider="gemini",
                free=True,
                rate_limits="15 RPM | 1,000,000 TPM | 1,500 RPD",
                context_window="1,000,000",
                category="Next-Gen Reasoning",
                compatibility="Google AI Studio OpenAI Endpoint",
                description="Google's latest Flash iteration with enhanced multilingual reasoning.",
            ),
            ModelInfo(
                id="gemini-pro-latest",
                name="Gemini Pro (Latest)",
                provider="gemini",
                free=True,
                rate_limits="2 RPM | 32,000 TPM | 50 RPD",
                context_window="2,000,000",
                category="Deep Complex Analysis",
                compatibility="Google AI Studio OpenAI Endpoint",
                description="Massive 2M token context for deep archival candidate comparison.",
            ),
        ],
    ),
    "ollama": ProviderInfo(
        id="ollama",
        name="Local Ollama (Self-Hosted)",
        icon="🦙",
        description="Runs 100% locally on your machine with zero data egress and unlimited requests.",
        api_key_url="https://ollama.com/",
        default_model="llama3.1:8b",
        default_base_url="http://localhost:11434",
        env_key_var="OLLAMA_BASE_URL",
        models=[
            ModelInfo(
                id="llama3.1:8b",
                name="Llama 3.1 8B (Local)",
                provider="ollama",
                free=True,
                rate_limits="Unlimited (Hardware Bound)",
                context_window="128k",
                category="Local Privacy",
                compatibility="Ollama JSON Format",
                description="Local privacy-first inference without cloud API dependencies.",
            ),
            ModelInfo(
                id="qwen2.5-coder:7b",
                name="Qwen 2.5 Coder 7B (Local)",
                provider="ollama",
                free=True,
                rate_limits="Unlimited (Hardware Bound)",
                context_window="32k",
                category="Local Technical",
                compatibility="Ollama JSON Format",
                description="High precision local parser for technical requirements and coding stacks.",
            ),
            ModelInfo(
                id="mistral:7b",
                name="Mistral 7B (Local)",
                provider="ollama",
                free=True,
                rate_limits="Unlimited (Hardware Bound)",
                context_window="32k",
                category="Local General",
                compatibility="Ollama JSON Format",
                description="Solid general local model.",
            ),
        ],
    ),
}


def sync_local_ollama_models() -> List[ModelInfo]:
    """Syncs the actual locally installed Ollama models from the running Ollama instance."""
    try:
        from backend.services.ollama_service import OllamaService
        svc = OllamaService()
        installed = svc.list_installed_models()
        if installed:
            models = []
            for m in installed:
                models.append(
                    ModelInfo(
                        id=m["name"],
                        name=f"{m['name']} (Local)",
                        provider="ollama",
                        free=True,
                        rate_limits="Unlimited (Local GPU/CPU)",
                        context_window="128k",
                        category=f"Local {m.get('parameter_size', '')}",
                        compatibility="Ollama JSON Format",
                        description=f"Installed local model ({m.get('size_gb', 0)} GB, {m.get('family', '')}).",
                    )
                )
            CATALOG_PROVIDERS["ollama"].models = models
            if models:
                CATALOG_PROVIDERS["ollama"].default_model = models[0].id
            return models
    except Exception:
        pass
    return CATALOG_PROVIDERS["ollama"].models


def get_providers_catalog() -> Dict[str, ProviderInfo]:
    """Returns all registered LLM providers with their metadata and models."""
    sync_local_ollama_models()
    return CATALOG_PROVIDERS


def get_models_for_provider(provider_id: str) -> List[ModelInfo]:
    """Returns the list of available models for a given provider."""
    if provider_id.lower() == "ollama":
        sync_local_ollama_models()
    provider = CATALOG_PROVIDERS.get(provider_id.lower())
    if not provider:
        return []
    return provider.models


def get_model_info(provider_id: str, model_id: str) -> Optional[ModelInfo]:
    """Returns specific model information including rate limits and context window."""
    models = get_models_for_provider(provider_id)
    for m in models:
        if m.id.lower() == model_id.lower():
            return m
    return None

