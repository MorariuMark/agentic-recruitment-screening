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

    # Active LLM Provider: 'openrouter' (default), 'groq', or 'ollama'
    llm_provider: Literal["openrouter", "groq", "ollama"] = Field(
        default="openrouter",
        description="Active LLM backend provider ('openrouter', 'groq', or 'ollama')",
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
        default="meta-llama/llama-3.3-70b-instruct",
        description="Default model identifier for OpenRouter",
    )

    # Groq Settings
    groq_api_key: Optional[str] = Field(
        default=None,
        description="API key for Groq Cloud API",
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model identifier",
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
