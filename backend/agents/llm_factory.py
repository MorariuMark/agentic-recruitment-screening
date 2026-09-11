"""
backend/agents/llm_factory.py
Pluggable LLM factory supporting Groq, OpenRouter, NVIDIA NIM, Google Gemini,
and local Ollama with structured Pydantic outputs and dynamic runtime switching.
"""

import json
import logging
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


def get_last_fallback_event() -> Optional[Dict[str, Any]]:
    """Returns the most recent fallback failover event metadata, if any occurred."""
    return _LAST_FALLBACK_EVENT


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
        starting with the primary user configuration, followed by intra-provider alternatives,
        and finally cross-provider fallbacks with verified credentials.
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

        # 1. Primary configured model
        primary_prov = settings.llm_provider.lower()
        primary_model = getattr(settings, f"{primary_prov}_model", None)
        if not primary_model:
            if primary_prov == "groq":
                primary_model = "openai/gpt-oss-20b"
            elif primary_prov == "nvidia_nim":
                primary_model = "meta/llama-3.2-11b-vision-instruct"
            elif primary_prov == "gemini":
                primary_model = "gemini-flash-latest"
            elif primary_prov == "openrouter":
                primary_model = "openrouter/free"
            elif primary_prov == "ollama":
                primary_model = "qwen3.5:2b-q4_K_M"

        add_candidate(primary_prov, primary_model)

        # 2. Intra-provider backup models for primary provider
        intra_fallbacks = {
            "groq": ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
            "nvidia_nim": ["meta/llama-3.2-11b-vision-instruct", "meta/llama-3.1-8b-instruct", "meta/llama-3.3-70b-instruct"],
            "gemini": ["gemini-flash-latest", "gemini-2.0-flash", "gemini-1.5-flash"],
            "openrouter": ["openrouter/free", "google/gemini-2.0-flash-exp:free", "meta-llama/llama-3.3-70b-instruct:free"],
            "ollama": [settings.ollama_model, "qwen3.5:2b-q4_K_M", "smollm2:latest", "qwen3:4b"],
        }
        for fallback_mod in intra_fallbacks.get(primary_prov, []):
            add_candidate(primary_prov, fallback_mod)

        # 3. Cross-provider fallbacks (ordered by speed and reliability)
        provider_priority = ["groq", "nvidia_nim", "gemini", "openrouter", "ollama"]
        for p in provider_priority:
            if p == primary_prov:
                continue

            if p == "groq" and settings.groq_api_key:
                add_candidate("groq", "openai/gpt-oss-20b", key=settings.groq_api_key)
                add_candidate("groq", "qwen/qwen3.8-27b", key=settings.groq_api_key)
            elif p == "nvidia_nim" and settings.nvidia_nim_api_key:
                add_candidate("nvidia_nim", settings.nvidia_nim_model or "meta/llama-3.2-11b-vision-instruct", key=settings.nvidia_nim_api_key)
                add_candidate("nvidia_nim", "meta/llama-3.1-8b-instruct", key=settings.nvidia_nim_api_key)
            elif p == "gemini" and settings.gemini_api_key:
                add_candidate("gemini", settings.gemini_model or "gemini-flash-latest", key=settings.gemini_api_key)
                add_candidate("gemini", "gemini-2.0-flash", key=settings.gemini_api_key)
            elif p == "openrouter" and settings.openrouter_api_key:
                add_candidate("openrouter", settings.openrouter_model or "openrouter/free", key=settings.openrouter_api_key)
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
            try:
                result = client.generate_text(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
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
                    logger.warning(
                        "Failover active: Text generation succeeded via fallback [%s / %s] after primary [%s / %s] failed.",
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
            try:
                result = client.generate_structured(
                    prompt=prompt,
                    response_model=response_model,
                    system_prompt=system_prompt,
                    temperature=temperature,
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
                    logger.warning(
                        "Failover active: Structured generation succeeded via fallback [%s / %s] after primary [%s / %s] failed.",
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
