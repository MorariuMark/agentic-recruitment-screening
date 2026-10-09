"""
backend/config.py
Application settings and configuration management using Pydantic Settings.
"""

from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings loaded from environment variables and .env file."""

    # Application
    app_name: str = "Agentic Recruitment Screening"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = True

    # Active LLM Provider: 'agnes', 'groq', 'openrouter', 'nvidia_nim', 'gemini', 'ollama', or 'lmstudio'
    llm_provider: Literal["agnes", "groq", "openrouter", "nvidia_nim", "gemini", "ollama", "lmstudio"] = Field(
        default="groq",
        description="Active LLM backend provider ('agnes', 'groq', 'openrouter', 'nvidia_nim', 'gemini', 'ollama', 'lmstudio')",
    )

    # Global structured output compatibility mode: 'auto', 'json_object', 'schema_prompt'
    compatibility_mode: Literal["auto", "json_object", "schema_prompt"] = Field(
        default="auto",
        description="Structured JSON compatibility strategy",
    )

    # Agnes AI Settings
    agnes_api_key: Optional[str] = Field(
        default=None,
        description="API key for Agnes AI (platform.agnes-ai.com)",
    )
    agnes_base_url: str = Field(
        default="https://apihub.agnes-ai.com/v1",
        description="Base URL for Agnes AI OpenAI endpoint",
    )
    agnes_model: str = Field(
        default="agnes-2.5-flash",
        description="Agnes AI model identifier",
    )

    # OpenRouter Settings
    openrouter_api_key: Optional[str] = Field(
        default=None,
        description="API key for OpenRouter API",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL for OpenRouter API",
    )
    openrouter_model: str = Field(
        default="openrouter/free",
        description="Default model identifier for OpenRouter",
    )

    # Groq Settings
    groq_api_key: Optional[str] = Field(
        default=None,
        description="API key for Groq Cloud API",
    )
    groq_model: str = Field(
        default="openai/gpt-oss-20b",
        description="Groq model identifier",
    )

    # NVIDIA NIM Settings
    nvidia_nim_api_key: Optional[str] = Field(
        default=None,
        description="API key for NVIDIA NIM Microservices (build.nvidia.com)",
    )
    nvidia_nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        description="Base URL for NVIDIA NIM OpenAI endpoint",
    )
    nvidia_nim_model: str = Field(
        default="meta/llama-3.2-11b-vision-instruct",
        description="NVIDIA NIM model identifier",
    )

    # Google Gemini Settings (AI Studio)
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="API key for Google Gemini (aistudio.google.com)",
    )
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        description="Base URL for Gemini OpenAI endpoint",
    )
    gemini_model: str = Field(
        default="gemini-flash-latest",
        description="Google Gemini model identifier",
    )

    # Ollama & Local Model Settings
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for local Ollama instance",
    )
    ollama_model: str = Field(
        default="minicpm5:2b",
        description="Ollama model identifier",
    )
    local_context_window: int = Field(
        default=4096,
        description="Local model context window size in tokens (e.g. 2048, 4096, 8192, 16384)",
    )
    local_rolling_context: bool = Field(
        default=True,
        description="Enable rolling context window with sliding chunk summarization to prevent OOM errors",
    )
    local_thinking_enabled: bool = Field(
        default=False,
        description="Enable thinking/reasoning tags for local reasoning models (when disabled, suppresses <think> tokens for speed)",
    )
    fallback_enabled: bool = Field(
        default=True,
        description="Enable multi-tier fallback failover to alternate models upon rate limit or failure",
    )

    # LM Studio & Local OpenAI-compatible Settings
    lmstudio_base_url: str = Field(
        default="http://localhost:1234/v1",
        description="Base URL for local LM Studio OpenAI-compatible endpoint",
    )
    lmstudio_model: str = Field(
        default="default",
        description="LM Studio model identifier",
    )

    # ChromaDB & Embeddings
    chroma_db_dir: str = Field(
        default="./data/chroma_db",
        description="Directory path for local ChromaDB persistence",
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="SentenceTransformer embedding model name",
    )

    # Relational Database Persistence (SQLite or PostgreSQL)
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/screening.db",
        description="Async database connection string (e.g. postgresql+asyncpg://... or sqlite+aiosqlite:///...)",
    )

    # Observability (Arize Phoenix)
    phoenix_collector_endpoint: Optional[str] = Field(
        default=None,
        description="Arize Phoenix OpenTelemetry collector endpoint (e.g. http://127.0.0.1:6006/v1/traces)",
    )

    @property
    def async_database_url(self) -> str:
        """Normalizes postgres://, postgresql://, and sqlite:/// to async drivers for async SQLAlchemy."""
        url = self.database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton settings instance
settings = Settings()
