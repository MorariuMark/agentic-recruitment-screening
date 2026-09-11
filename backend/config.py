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

    # Active LLM Provider: 'groq', 'openrouter', 'nvidia_nim', 'gemini', or 'ollama'
    llm_provider: Literal["groq", "openrouter", "nvidia_nim", "gemini", "ollama"] = Field(
        default="groq",
        description="Active LLM backend provider ('groq', 'openrouter', 'nvidia_nim', 'gemini', 'ollama')",
    )

    # Global structured output compatibility mode: 'auto', 'json_object', 'schema_prompt'
    compatibility_mode: Literal["auto", "json_object", "schema_prompt"] = Field(
        default="auto",
        description="Structured JSON compatibility strategy",
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

    # Ollama Settings
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for local Ollama instance",
    )
    ollama_model: str = Field(
        default="llama3.1:8b",
        description="Ollama model identifier",
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

    # Arize Phoenix Observability
    phoenix_collector_endpoint: Optional[str] = Field(
        default=None,
        description="Arize Phoenix collector endpoint for OpenTelemetry traces",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton settings instance
settings = Settings()
