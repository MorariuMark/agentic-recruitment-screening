"""
backend/agents/llm_factory.py
Pluggable LLM factory supporting Groq, OpenRouter, NVIDIA NIM, Google Gemini,
and local Ollama with structured Pydantic outputs and dynamic runtime switching.
"""

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel

from backend.config import settings

logger = logging.getLogger("recruitment_screening.llm_factory")
T = TypeVar("T", bound=BaseModel)
_LAST_FALLBACK_EVENT: Optional[Dict[str, Any]] = None


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

    def __init__(self) -> None:
        self.last_usage: Optional[Dict[str, int]] = None

    def _capture_usage(self, response: Any, prompt: str, output: str) -> Dict[str, int]:
        usage = getattr(response, "usage", None)
        if usage:
            p = getattr(usage, "prompt_tokens", 0) or 0
            c = getattr(usage, "completion_tokens", 0) or 0
            t = getattr(usage, "total_tokens", 0) or (p + c)
            if t > 0:
                self.last_usage = {"prompt_tokens": p, "completion_tokens": c, "total_tokens": t}
                return self.last_usage

        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta:
            p = getattr(usage_meta, "prompt_token_count", 0) or 0
            c = getattr(usage_meta, "candidates_token_count", 0) or 0
            t = getattr(usage_meta, "total_token_count", 0) or (p + c)
            if t > 0:
                self.last_usage = {"prompt_tokens": p, "completion_tokens": c, "total_tokens": t}
                return self.last_usage

        p = max(1, len(prompt) // 4)
        c = max(1, len(str(output)) // 4)
        self.last_usage = {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c}
        return self.last_usage

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



class AgnesClient(BaseLLMClient):
    """Client for Agnes AI via OpenAI-compatible endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        from openai import OpenAI

        self.api_key = api_key or settings.agnes_api_key
        if not self.api_key:
            raise ValueError("AGNES_API_KEY must be provided or set in environment variables.")
        self.base_url = base_url or settings.agnes_base_url
        self.model = model or settings.agnes_model
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=30.0,
            max_retries=1,
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
        content = response.choices[0].message.content or ""
        self._capture_usage(response, prompt, content)
        return content

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        schema_json = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
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
            self._capture_usage(response, prompt, raw_content)
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
                self._capture_usage(response, prompt, raw_content)
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            raise err



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
        schema_json = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
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
        self.client = Groq(api_key=self.api_key, timeout=20.0, max_retries=0)

    def _get_candidate_models(self) -> List[str]:
        candidates = [self.model]
        for fallback in ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]:
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
        schema_json = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
        augmented_system = (
            f"{system_prompt or ''}\n\n"
            f"You MUST respond ONLY with valid JSON conforming to this JSON Schema:\n{schema_json}"
        ).strip()

        messages = [
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": prompt},
        ]

        use_json_object = self.compatibility_mode in ("json_object", "auto")

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
            timeout=12.0,
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
        schema_json = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
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
        schema_json = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
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
        schema_json = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
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
    if selected == "agnes":
        return AgnesClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            compatibility_mode=compatibility_mode,
        )
    elif selected == "groq":
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
            f"Choose 'agnes', 'groq', 'openrouter', 'nvidia_nim', 'gemini', or 'ollama'."
        )


_FALLBACK_CHAIN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "fallback_hierarchy.json",
)
_CUSTOM_FALLBACK_CHAIN: Optional[List[Dict[str, str]]] = None


def load_custom_fallback_chain() -> Optional[List[Dict[str, str]]]:
    """Loads user-defined custom fallback hierarchy from disk if present."""
    global _CUSTOM_FALLBACK_CHAIN
    if os.path.exists(_FALLBACK_CHAIN_FILE):
        try:
            with open(_FALLBACK_CHAIN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    _CUSTOM_FALLBACK_CHAIN = data
                    logger.info("Loaded custom LLM fallback hierarchy (%d tiers).", len(data))
                    return _CUSTOM_FALLBACK_CHAIN
        except Exception as e:
            logger.warning("Failed loading fallback hierarchy file: %s", e)
    return _CUSTOM_FALLBACK_CHAIN


def save_custom_fallback_chain(chain: Optional[List[Dict[str, str]]]) -> None:
    """Persists or clears user-defined custom fallback hierarchy."""
    global _CUSTOM_FALLBACK_CHAIN
    _CUSTOM_FALLBACK_CHAIN = chain
    try:
        os.makedirs(os.path.dirname(_FALLBACK_CHAIN_FILE), exist_ok=True)
        if chain is not None:
            with open(_FALLBACK_CHAIN_FILE, "w", encoding="utf-8") as f:
                json.dump(chain, f, indent=2)
            logger.info("Saved custom LLM fallback hierarchy (%d tiers) to disk.", len(chain))
        else:
            if os.path.exists(_FALLBACK_CHAIN_FILE):
                os.remove(_FALLBACK_CHAIN_FILE)
            logger.info("Cleared custom LLM fallback hierarchy; reverted to automatic multi-tier failover.")
    except Exception as e:
        logger.warning("Failed saving fallback hierarchy file: %s", e)


def get_custom_fallback_chain() -> Optional[List[Dict[str, str]]]:
    """Returns the currently active user-defined fallback hierarchy, if configured."""
    global _CUSTOM_FALLBACK_CHAIN
    if _CUSTOM_FALLBACK_CHAIN is None:
        load_custom_fallback_chain()
    return _CUSTOM_FALLBACK_CHAIN


# Auto-load persisted fallback hierarchy on module startup
load_custom_fallback_chain()


def _get_fallback_primary_model(prov: str) -> str:
    m = getattr(settings, f"{prov}_model", None)
    if m:
        return m
    if prov == "agnes":
        return "agnes-2.5-flash"
    elif prov == "groq":
        return "openai/gpt-oss-20b"
    elif prov == "nvidia_nim":
        return "meta/llama-3.2-11b-vision-instruct"
    elif prov == "gemini":
        return "gemini-flash-latest"
    elif prov == "openrouter":
        return "openrouter/free"
    elif prov == "ollama":
        return "qwen3.5:2b-q4_K_M"
    return "default"


def get_last_fallback_event() -> Optional[Dict[str, Any]]:
    """Returns the most recent fallback failover event metadata, if any occurred."""
    return _LAST_FALLBACK_EVENT


def clear_last_fallback_event() -> None:
    """Resets the last recorded fallback failover event."""
    global _LAST_FALLBACK_EVENT
    _LAST_FALLBACK_EVENT = None


def _is_local_port_open(host: str, port: int, timeout: float = 0.15) -> bool:
    """Fast non-blocking socket test to check if local port is listening."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except Exception:
        return False


class DynamicLLMClient(BaseLLMClient):
    """
    Dynamic LLM client proxy with multi-tier failover protection.
    Resolves the active provider, model, and credentials from runtime settings,
    and automatically falls over through intra-provider alternatives and cross-provider
    configured endpoints if any model encounters an error, rate limit, timeout, or outage.
    """

    def __init__(self) -> None:
        self._client_cache: Dict[Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]], BaseLLMClient] = {}

    def _get_or_create_client(
        self,
        provider: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> Optional[BaseLLMClient]:
        """Returns or creates a cached client instance for a candidate target."""
        cache_key = (provider, model, api_key, base_url, compatibility_mode)
        if cache_key not in self._client_cache:
            try:
                client = create_llm_client(
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    compatibility_mode=compatibility_mode,
                )
                self._client_cache[cache_key] = client
            except Exception as e:
                logger.debug("Failed to initialize fallback client for %s/%s: %s", provider, model, e)
                return None
        return self._client_cache.get(cache_key)

    def get_fallback_chain(self) -> List[Tuple[str, str, BaseLLMClient]]:
        """
        Builds the ordered sequence of candidate targets (provider, model, client)
        starting with the primary user configuration, followed by user-defined custom hierarchy
        or automatic multi-tier alternatives.
        """
        chain: List[Tuple[str, str, BaseLLMClient]] = []
        seen_targets = set()

        def add_candidate(
            prov: str,
            mod: Optional[str],
            key: Optional[str] = None,
            url: Optional[str] = None,
            mode: Optional[str] = None,
        ):
            if not prov or not mod:
                return
            target_key = (prov.lower(), mod)
            if target_key in seen_targets:
                return
            cli = self._get_or_create_client(
                provider=prov,
                model=mod,
                api_key=key,
                base_url=url,
                compatibility_mode=mode or settings.compatibility_mode,
            )
            if cli is not None:
                seen_targets.add(target_key)
                chain.append((prov.lower(), mod, cli))

        # Check for user-defined custom fallback hierarchy first
        custom = get_custom_fallback_chain()
        if custom and len(custom) > 0:
            primary_prov = settings.llm_provider.lower()
            primary_model = _get_fallback_primary_model(primary_prov)

            # Ensure current primary model is Tier 1
            add_candidate(primary_prov, primary_model)

            # Append custom sequence configured by the user
            for target in custom:
                t_prov = (target.get("provider") or "").lower()
                t_mod = target.get("model")
                if not t_prov or not t_mod:
                    continue
                t_key = getattr(settings, f"{t_prov}_api_key", None)
                t_url = getattr(settings, f"{t_prov}_base_url", None)
                add_candidate(t_prov, t_mod, key=t_key, url=t_url)

            if chain:
                return chain

        # 1. Primary configured model (Default automatic chain)
        primary_prov = settings.llm_provider.lower()
        primary_model = _get_fallback_primary_model(primary_prov)
        add_candidate(primary_prov, primary_model)

        # 2. Intra-provider backup models for primary provider
        intra_fallbacks = {
            "agnes": ["agnes-2.5-flash", "agnes-3.0-flash", "agnes-2.0-flash", "agnes-2.5-pro"],
            "groq": ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"],
            "nvidia_nim": ["meta/llama-3.2-11b-vision-instruct", "meta/llama-3.1-8b-instruct", "meta/llama-3.3-70b-instruct"],
            "gemini": ["gemini-flash-latest", "gemini-2.0-flash", "gemini-1.5-flash"],
            "openrouter": ["openrouter/free", "google/gemini-2.0-flash-exp:free", "meta-llama/llama-3.3-70b-instruct:free"],
            "ollama": [settings.ollama_model, "qwen3.5:2b-q4_K_M", "smollm2:latest", "qwen3:4b"],
        }
        for fallback_mod in intra_fallbacks.get(primary_prov, []):
            add_candidate(primary_prov, fallback_mod)

        # 3. Cross-provider fallbacks (ordered by speed and reliability: Groq -> Gemini -> Agnes -> OpenRouter -> NVIDIA -> Ollama)
        provider_priority = ["groq", "gemini", "agnes", "openrouter", "nvidia_nim", "ollama"]
        for p in provider_priority:
            if p == primary_prov:
                continue

            if p == "groq" and settings.groq_api_key:
                add_candidate("groq", "openai/gpt-oss-20b", key=settings.groq_api_key)
                add_candidate("groq", "qwen/qwen3.8-27b", key=settings.groq_api_key)
            elif p == "gemini" and settings.gemini_api_key:
                add_candidate("gemini", settings.gemini_model or "gemini-flash-latest", key=settings.gemini_api_key)
                add_candidate("gemini", "gemini-2.0-flash", key=settings.gemini_api_key)
            elif p == "agnes" and settings.agnes_api_key:
                add_candidate("agnes", settings.agnes_model or "agnes-2.5-flash", key=settings.agnes_api_key)
                add_candidate("agnes", "agnes-2.5-flash", key=settings.agnes_api_key)
                add_candidate("agnes", "agnes-3.0-flash", key=settings.agnes_api_key)
            elif p == "openrouter" and settings.openrouter_api_key:
                add_candidate("openrouter", settings.openrouter_model or "openrouter/free", key=settings.openrouter_api_key)
            elif p == "nvidia_nim" and settings.nvidia_nim_api_key:
                add_candidate("nvidia_nim", settings.nvidia_nim_model or "meta/llama-3.2-11b-vision-instruct", key=settings.nvidia_nim_api_key)
                add_candidate("nvidia_nim", "meta/llama-3.1-8b-instruct", key=settings.nvidia_nim_api_key)
            elif p == "ollama":
                # Quick probe to see if local Ollama is responding
                if _is_local_port_open("127.0.0.1", 11434):
                    add_candidate("ollama", settings.ollama_model or "qwen3.5:2b-q4_K_M")

        return chain

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        global _LAST_FALLBACK_EVENT
        chain = self.get_fallback_chain()
        if not chain:
            raise RuntimeError("No configured or reachable LLM providers available in fallback chain.")

        primary_prov, primary_mod, _ = chain[0]
        last_error: Optional[Exception] = None
        attempt_history: List[str] = []

        for idx, (prov, mod, client) in enumerate(chain):
            t0 = time.perf_counter()
            try:
                result = client.generate_text(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )
                lat_ms = (time.perf_counter() - t0) * 1000.0
                usage = getattr(client, "last_usage", None) or {}
                p_tok = usage.get("prompt_tokens") or max(1, len(prompt) // 4)
                c_tok = usage.get("completion_tokens") or max(1, len(result) // 4)
                t_tok = usage.get("total_tokens") or (p_tok + c_tok)

                from backend.services.token_tracker import token_tracker
                self._last_usage = token_tracker.record_usage(
                    provider=prov,
                    model=mod,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                    action=getattr(self, "_current_action", "general"),
                    latency_ms=lat_ms,
                    status="success" if idx == 0 else "failover",
                )

                if idx > 0:
                    _LAST_FALLBACK_EVENT = {
                        "timestamp": time.time(),
                        "from_provider": primary_prov,
                        "from_model": primary_mod,
                        "to_provider": prov,
                        "to_model": mod,
                        "error": str(last_error),
                    }
                    # Hot-swap runtime configuration to the working fallback model
                    settings.llm_provider = prov
                    if hasattr(settings, f"{prov}_model"):
                        setattr(settings, f"{prov}_model", mod)
                    logger.warning(
                        "Failover event: Text generation succeeded via fallback [%s / %s] after primary [%s / %s] failed. Active engine updated.",
                        prov,
                        mod,
                        primary_prov,
                        primary_mod,
                    )
                return result
            except Exception as err:
                last_error = err
                attempt_history.append(f"{prov}:{mod} ({type(err).__name__}: {str(err)[:100]})")
                logger.warning(
                    "LLM generation failed on [%s / %s]: %s. Advancing to next fallback...",
                    prov,
                    mod,
                    err,
                )
                continue

        raise RuntimeError(
            f"All LLM models in fallback chain failed. Attempted: {'; '.join(attempt_history)}. Last error: {last_error}"
        ) from last_error

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        global _LAST_FALLBACK_EVENT
        chain = self.get_fallback_chain()
        if not chain:
            raise RuntimeError("No configured or reachable LLM providers available in fallback chain.")

        primary_prov, primary_mod, _ = chain[0]
        last_error: Optional[Exception] = None
        attempt_history: List[str] = []

        for idx, (prov, mod, client) in enumerate(chain):
            t0 = time.perf_counter()
            try:
                result = client.generate_structured(
                    prompt=prompt,
                    response_model=response_model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )
                lat_ms = (time.perf_counter() - t0) * 1000.0
                usage = getattr(client, "last_usage", None) or {}
                p_tok = usage.get("prompt_tokens") or max(1, len(prompt) // 4)
                c_tok = usage.get("completion_tokens") or max(1, len(str(result)) // 4)
                t_tok = usage.get("total_tokens") or (p_tok + c_tok)

                from backend.services.token_tracker import token_tracker
                self._last_usage = token_tracker.record_usage(
                    provider=prov,
                    model=mod,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                    action=getattr(self, "_current_action", "general"),
                    latency_ms=lat_ms,
                    status="success" if idx == 0 else "failover",
                )

                if idx > 0:
                    _LAST_FALLBACK_EVENT = {
                        "timestamp": time.time(),
                        "from_provider": primary_prov,
                        "from_model": primary_mod,
                        "to_provider": prov,
                        "to_model": mod,
                        "error": str(last_error),
                    }
                    # Hot-swap runtime configuration to the working fallback model
                    settings.llm_provider = prov
                    if hasattr(settings, f"{prov}_model"):
                        setattr(settings, f"{prov}_model", mod)
                    logger.warning(
                        "Failover event: Structured generation succeeded via fallback [%s / %s] after primary [%s / %s] failed. Active engine updated.",
                        prov,
                        mod,
                        primary_prov,
                        primary_mod,
                    )
                return result
            except Exception as err:
                last_error = err
                attempt_history.append(f"{prov}:{mod} ({type(err).__name__}: {str(err)[:100]})")
                logger.warning(
                    "Structured LLM generation failed on [%s / %s]: %s. Advancing to next fallback...",
                    prov,
                    mod,
                    err,
                )
                continue

        raise RuntimeError(
            f"All LLM models in fallback chain failed for schema '{response_model.__name__}'. "
            f"Attempted: {'; '.join(attempt_history)}. Last error: {last_error}"
        ) from last_error

    def get_last_usage(self) -> Optional[Any]:
        """Returns the token usage info for the most recent successful LLM call."""
        from backend.services.token_tracker import token_tracker
        return getattr(self, "_last_usage", None) or token_tracker.get_last_usage()

    def set_action_context(self, action: str) -> None:
        """Sets action tag (e.g. 'candidate_evaluation', 'cv_extraction', 'job_parsing') for usage logs."""
        self._current_action = action



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
