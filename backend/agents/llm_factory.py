"""
backend/agents/llm_factory.py
Pluggable LLM factory supporting Groq, OpenRouter, NVIDIA NIM, Google Gemini,
and local Ollama with structured Pydantic outputs and dynamic runtime switching.
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

from backend.config import settings

T = TypeVar("T", bound=BaseModel)


def clean_and_parse_json(raw_content: str) -> Dict[str, Any]:
    """
    Resilient JSON extractor handling raw JSON, markdown code fences,
    and reasoning models (<think>...</think> tags such as DeepSeek R1).
    """
    text = (raw_content or "").strip()

    # Remove DeepSeek / reasoning thought blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Strip markdown code blocks ```json ... ``` or ``` ... ```
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                text = stripped
                break

    # Extract outermost JSON object boundaries
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    if not text:
        return {}

    return json.loads(text)


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
        compatibility_mode: Optional[str] = None,
    ) -> None:
        from openai import OpenAI

        self.api_key = api_key or settings.openrouter_api_key
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY must be provided or set in environment variables.")
        self.base_url = base_url or settings.openrouter_base_url
        self.model = model or settings.openrouter_model
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=60.0,
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

        use_json_object = self.compatibility_mode in ("json_object", "auto")

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if use_json_object:
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)
            raw_content = response.choices[0].message.content or "{}"
            parsed_dict = clean_and_parse_json(raw_content)
            return response_model.model_validate(parsed_dict)
        except Exception as err:
            if use_json_object and self.compatibility_mode == "auto":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                )
                raw_content = response.choices[0].message.content or "{}"
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            raise err


class GroqClient(BaseLLMClient):
    """Client for Groq Cloud API with ultra-fast inference."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        from groq import Groq

        self.api_key = api_key or settings.groq_api_key
        if not self.api_key:
            raise ValueError("GROQ_API_KEY must be provided or set in environment variables.")
        self.model = model or settings.groq_model
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode
        self.client = Groq(api_key=self.api_key, timeout=60.0)

    def _get_candidate_models(self) -> List[str]:
        candidates = [self.model]
        for fallback in ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

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

        last_error = None
        for candidate_model in self._get_candidate_models():
            try:
                response = self.client.chat.completions.create(
                    model=candidate_model,
                    messages=messages,
                    temperature=temperature,
                )
                return response.choices[0].message.content or ""
            except Exception as err:
                err_str = str(err).lower()
                if "rate_limit" in err_str or "429" in str(err) or "too large" in err_str or "413" in str(err):
                    last_error = err
                    continue
                raise err
        if last_error:
            raise last_error
        return ""

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

        use_json_object = self.compatibility_mode in ("json_object", "auto")

        last_error = None
        for candidate_model in self._get_candidate_models():
            try:
                kwargs: Dict[str, Any] = {
                    "model": candidate_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 4096,
                }
                if use_json_object:
                    kwargs["response_format"] = {"type": "json_object"}

                response = self.client.chat.completions.create(**kwargs)
                raw_content = response.choices[0].message.content or "{}"
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            except Exception as err:
                err_str = str(err).lower()
                if (
                    "rate_limit" in err_str
                    or "429" in str(err)
                    or "too large" in err_str
                    or "413" in str(err)
                    or "400" in str(err)
                    or "json_validate_failed" in err_str
                ):
                    last_error = err
                    continue
                raise err
        if last_error:
            raise last_error
        return response_model.model_validate({})


class NvidiaNimClient(BaseLLMClient):
    """Client for NVIDIA NIM Microservices via OpenAI-compatible endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        from openai import OpenAI

        self.api_key = api_key or settings.nvidia_nim_api_key
        if not self.api_key:
            raise ValueError("NVIDIA_NIM_API_KEY must be provided or set in environment variables.")
        self.base_url = base_url or settings.nvidia_nim_base_url
        self.model = model or settings.nvidia_nim_model
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=60.0,
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
            max_tokens=4096,
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

        use_json_object = self.compatibility_mode in ("json_object", "auto")

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 4096,
            }
            if use_json_object:
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)
            raw_content = response.choices[0].message.content or "{}"
            parsed_dict = clean_and_parse_json(raw_content)
            return response_model.model_validate(parsed_dict)
        except Exception as err:
            if use_json_object and self.compatibility_mode == "auto":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4096,
                )
                raw_content = response.choices[0].message.content or "{}"
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            raise err


class GeminiClient(BaseLLMClient):
    """Client for Google Gemini (AI Studio) via official OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        from openai import OpenAI

        self.api_key = api_key or settings.gemini_api_key
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be provided or set in environment variables.")
        self.base_url = base_url or settings.gemini_base_url
        self.model = model or settings.gemini_model
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=60.0,
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

        use_json_object = self.compatibility_mode in ("json_object", "auto")

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if use_json_object:
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)
            raw_content = response.choices[0].message.content or "{}"
            parsed_dict = clean_and_parse_json(raw_content)
            return response_model.model_validate(parsed_dict)
        except Exception as err:
            if use_json_object and self.compatibility_mode == "auto":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                )
                raw_content = response.choices[0].message.content or "{}"
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            raise err


class OllamaClient(BaseLLMClient):
    """Client for local Ollama instance with privacy guarantees."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        import ollama

        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode
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
        parsed_dict = clean_and_parse_json(raw_content)
        return response_model.model_validate(parsed_dict)


def create_llm_client(
    provider: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    compatibility_mode: Optional[str] = None,
) -> BaseLLMClient:
    """Instantiate an explicit LLM client for a specific provider."""
    selected = provider.lower()
    if selected == "groq":
        return GroqClient(api_key=api_key, model=model, compatibility_mode=compatibility_mode)
    elif selected == "openrouter":
        return OpenRouterClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            compatibility_mode=compatibility_mode,
        )
    elif selected == "nvidia_nim":
        return NvidiaNimClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            compatibility_mode=compatibility_mode,
        )
    elif selected == "gemini":
        return GeminiClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            compatibility_mode=compatibility_mode,
        )
    elif selected == "ollama":
        return OllamaClient(
            base_url=base_url,
            model=model,
            compatibility_mode=compatibility_mode,
        )
    else:
        raise ValueError(
            f"Unsupported LLM provider '{selected}'. "
            f"Choose 'groq', 'openrouter', 'nvidia_nim', 'gemini', or 'ollama'."
        )


class DynamicLLMClient(BaseLLMClient):
    """
    Dynamic LLM client proxy. Resolves the active provider, model, and credentials
    from runtime settings on every invocation, enabling instant hot-reloading
    without restarting the application or re-instantiating agents.
    """

    def __init__(self) -> None:
        self._cached_client: Optional[BaseLLMClient] = None
        self._cached_signature: Optional[tuple] = None

    def _resolve_client(self) -> BaseLLMClient:
        provider = settings.llm_provider
        if provider == "groq":
            sig = (provider, settings.groq_model, settings.groq_api_key, settings.compatibility_mode)
        elif provider == "openrouter":
            sig = (provider, settings.openrouter_model, settings.openrouter_api_key, settings.compatibility_mode)
        elif provider == "nvidia_nim":
            sig = (provider, settings.nvidia_nim_model, settings.nvidia_nim_api_key, settings.compatibility_mode)
        elif provider == "gemini":
            sig = (provider, settings.gemini_model, settings.gemini_api_key, settings.compatibility_mode)
        elif provider == "ollama":
            sig = (provider, settings.ollama_model, settings.ollama_base_url, settings.compatibility_mode)
        else:
            sig = (provider, None, None, None)

        if self._cached_client is None or self._cached_signature != sig:
            self._cached_client = create_llm_client(provider)
            self._cached_signature = sig

        return self._cached_client

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        return self._resolve_client().generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        return self._resolve_client().generate_structured(
            prompt=prompt,
            response_model=response_model,
            system_prompt=system_prompt,
            temperature=temperature,
        )


def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    compatibility_mode: Optional[str] = None,
) -> BaseLLMClient:
    """
    Factory function returning the configured LLM client instance.
    If provider or model is passed, returns an explicit client.
    Otherwise, returns DynamicLLMClient which hot-swaps dynamically.
    """
    if provider:
        return create_llm_client(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            compatibility_mode=compatibility_mode,
        )
    return DynamicLLMClient()
