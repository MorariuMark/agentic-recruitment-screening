"""
backend/agents/llm_factory.py
Pluggable LLM factory supporting OpenRouter (default), Groq, and local Ollama with structured Pydantic outputs.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from backend.config import settings

T = TypeVar("T", bound=BaseModel)


class BaseLLMClient(ABC):
    """Abstract interface for all LLM inference clients."""

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        """Generate unstructured text from the model."""
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        """Generate and parse structured JSON into a Pydantic model."""
        pass


class OpenRouterClient(BaseLLMClient):
    """Client for OpenRouter API supporting hundreds of models via OpenAI-compatible endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        from openai import OpenAI

        self.api_key = api_key or settings.openrouter_api_key
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY must be provided or set in environment variables.")
        self.base_url = base_url or settings.openrouter_base_url
        self.model = model or settings.openrouter_model

        # Initialize OpenAI client pointed at OpenRouter
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/MorariuMark/agentic-recruitment-screening",
                "X-Title": "Agentic Recruitment Screening",
            },
        )

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        augmented_system = (
            f"{system_prompt or ''}\n\n"
            f"You MUST respond ONLY with valid JSON conforming to this JSON Schema:\n{schema_json}"
        ).strip()

        messages = [
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": prompt},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content or "{}"
        return response_model.model_validate_json(raw_content)


class GroqClient(BaseLLMClient):
    """Client for Groq Cloud API with ultra-fast inference."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        from groq import Groq

        self.api_key = api_key or settings.groq_api_key
        if not self.api_key:
            raise ValueError("GROQ_API_KEY must be provided or set in environment variables.")
        self.model = model or settings.groq_model
        self.client = Groq(api_key=self.api_key)

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        augmented_system = (
            f"{system_prompt or ''}\n\n"
            f"You MUST respond ONLY with valid JSON conforming to this JSON Schema:\n{schema_json}"
        ).strip()

        messages = [
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": prompt},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content or "{}"
        return response_model.model_validate_json(raw_content)


class OllamaClient(BaseLLMClient):
    """Client for local Ollama instance with privacy guarantees."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None) -> None:
        import ollama

        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        self.client = ollama.Client(host=self.base_url)

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": temperature},
        )
        return response.message.content or ""

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        augmented_system = (
            f"{system_prompt or ''}\n\n"
            f"You MUST respond ONLY with valid JSON conforming to this JSON Schema:\n{schema_json}"
        ).strip()

        messages = [
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": prompt},
        ]

        response = self.client.chat(
            model=self.model,
            messages=messages,
            format="json",
            options={"temperature": temperature},
        )
        raw_content = response.message.content or "{}"
        return response_model.model_validate_json(raw_content)


def get_llm_client(provider: Optional[str] = None) -> BaseLLMClient:
    """
    Factory function returning the configured LLM client instance.
    Defaults to settings.llm_provider ('openrouter', 'groq', or 'ollama').
    """
    selected = (provider or settings.llm_provider).lower()
    if selected == "openrouter":
        return OpenRouterClient()
    elif selected == "groq":
        return GroqClient()
    elif selected == "ollama":
        return OllamaClient()
    else:
        raise ValueError(
            f"Unsupported LLM provider '{selected}'. Choose 'openrouter', 'groq', or 'ollama'."
        )
