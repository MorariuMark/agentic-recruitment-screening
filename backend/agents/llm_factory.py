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
import threading
import copy
import ast
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel

from backend.config import settings

logger = logging.getLogger("recruitment_screening.llm_factory")
T = TypeVar("T", bound=BaseModel)
_LAST_FALLBACK_EVENT: Optional[Dict[str, Any]] = None
_CLIENT_STATE_LOCK = threading.Lock()


# Shared across clients: concurrent requirement workers must not burst one key.
_GROQ_PACING_LOCK = threading.Lock()
_GROQ_NEXT_CALL: Dict[str, float] = {}


class ProviderCoolingDownError(RuntimeError):
    """A queued call was skipped after another worker exhausted this target."""
    retryable = True


class StructuredOutputTruncatedError(ValueError):
    """The response budget was exhausted, not an unavailable API credential."""


class ProviderResponseError(RuntimeError):
    """An upstream service returned no usable completion envelope."""
    retryable = True


def _completion_content(response, provider):
    choices = getattr(response, "choices", None)
    if not choices or getattr(choices[0], "message", None) is None:
        raise ProviderResponseError(f"{provider} returned no completion choices; the upstream service is unavailable or returned an invalid response.")
    return choices[0].message.content or ""


def _is_document_output_error(error: Exception) -> bool:
    """Bad output for one document must not open the shared provider circuit."""
    if isinstance(error, ValueError):
        return True
    return getattr(error, "status_code", None) in (400, 413, 422) and any(
        marker in str(error).lower() for marker in (
            "json_validate_failed", "failed to validate json", "context_length_exceeded",
            "maximum context length", "context window", "request too large"))


class LLMProvidersCoolingDownError(RuntimeError):
    """Temporary provider unavailability, not a document parsing failure."""
    retryable = True

    def __init__(self, retry_after: float, details: str = ""):
        self.retry_after = max(1.0, retry_after)
        super().__init__(
            "All LLM models in fallback chain failed or are temporarily cooling down. "
            f"No healthy provider can be called; retry in {self.retry_after:.1f}s. "
            + (details or "No new requests were sent because every configured target is in cooldown.")
        )


def _retry_after_seconds(error: Exception) -> Optional[float]:
    headers = getattr(getattr(error, "response", None), "headers", {}) or {}
    value = headers.get("retry-after") or headers.get("Retry-After")
    try:
        if value is not None:
            seconds = float(value)
            if 0 <= seconds <= 86400:
                return seconds
    except (TypeError, ValueError):
        pass
    def retry_info(value, depth=0):
        if depth > 6:
            return None
        if isinstance(value, dict):
            duration = value.get("retryDelay")
            if isinstance(duration, str) and re.fullmatch(r"\d+(?:\.\d+)?s", duration):
                return min(float(duration[:-1]), 86400)
            children = value.values()
        elif isinstance(value, list):
            children = value
        else:
            return None
        for child in children:
            seconds = retry_info(child, depth + 1)
            if seconds is not None:
                return seconds
        return None
    structured_delay = retry_info(getattr(error, "body", None))
    if structured_delay is not None:
        return structured_delay
    err_str = str(error)
    m_ms = re.search(r"(?:retry in|try again in|retry after)\s+(\d+(?:\.\d+)?)\s*ms\b", err_str, re.I)
    if m_ms:
        return float(m_ms.group(1)) * 0.001

    pattern = r"(?:retry in|try again in|retry after)\s+(?:(\d+(?:\.\d+)?)\s*(?:h|hours?)\s*)?(?:(\d+(?:\.\d+)?)\s*(?:m|min|minutes?)\s*)?(?:(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?)?)?"
    m = re.search(pattern, err_str, re.I)
    if m and any(m.groups()):
        h = float(m.group(1) or 0) * 3600
        mins = float(m.group(2) or 0) * 60
        s = float(m.group(3) or 0)
        total = h + mins + s
        if total > 0:
            return min(total, 86400)
    return None


def _is_format_error(error: Exception) -> bool:
    """Only unsupported JSON-mode errors justify another request to the same model."""
    return getattr(error, "status_code", None) in (400, 422) and any(
        marker in str(error).lower() for marker in ("response_format", "json mode", "json_object"))


def _paced_groq_call(client: Any, kwargs: Dict[str, Any], key: str) -> Any:
    model = kwargs.get("model", "")
    if is_model_in_cooldown("groq", model, key):
        raise ProviderCoolingDownError("Groq target is cooling down; use the next fallback.")
    with _GROQ_PACING_LOCK:
        now = time.monotonic()
        scheduled = max(now, _GROQ_NEXT_CALL.get(key, now))
        _GROQ_NEXT_CALL[key] = scheduled + 0.35
    time.sleep(max(0.0, scheduled - now))
    # Another worker may have received a 429 while this call was waiting.
    if is_model_in_cooldown("groq", model, key):
        raise ProviderCoolingDownError("Groq target entered cooldown while this request was queued.")
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as error:
        if getattr(error, "status_code", None) == 429 or re.search(r"\b429\b|rate.?limit", str(error), re.I):
            # Register immediately, before returning to the outer fallback client,
            # so queued calls and standalone key rotation share the same breaker.
            record_model_failure("groq", model, error, key)
        raise


def _build_compact_json_skeleton(model_cls: Type[BaseModel], depth: int = 0) -> Any:
    """
    Constructs a lightweight, compact JSON skeleton representing the required fields and types.
    Eliminates OpenAPI $defs, reference recursion, and verbose descriptions that overwhelm
    small local models (2B parameters) and consume thousands of prompt tokens.
    """
    if depth > 4:
        return {}
    skeleton: Dict[str, Any] = {}
    for name, field in getattr(model_cls, "model_fields", {}).items():
        if model_cls.__name__ == "ParsedCV" and name in {"raw_text", "audit_metadata", "dataset", "benchmark_annotations"}:
            continue  # Populated by application code, never generated from applicant instructions.
        annotation = field.annotation
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is Union:
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                annotation = non_none[0]
                origin = get_origin(annotation)
                args = get_args(annotation)
        if origin in (list, List):
            inner = args[0] if args else Any
            if hasattr(inner, "model_fields"):
                skeleton[name] = [_build_compact_json_skeleton(inner, depth + 1)]
            elif isinstance(inner, type) and issubclass(inner, Enum):
                skeleton[name] = [" | ".join(str(e.value) for e in inner)]
            else:
                inner_name = getattr(inner, "__name__", "string")
                skeleton[name] = [f"<{inner_name}>"]
        elif hasattr(annotation, "model_fields"):
            skeleton[name] = _build_compact_json_skeleton(annotation, depth + 1)
        elif isinstance(annotation, type) and issubclass(annotation, Enum):
            skeleton[name] = " | ".join(str(e.value) for e in annotation)
        else:
            t_name = getattr(annotation, "__name__", "string")
            skeleton[name] = f"<{t_name}>"
    return skeleton


def format_structured_schema_instruction(response_model: Type[Any]) -> str:
    """
    Constructs an optimized schema specification string for prompt injection.
    Prefers compact JSON skeleton to reduce token overhead by ~84%, falling back
    gracefully to model_json_schema() if skeleton compilation encounters unmapped constructs.
    """
    try:
        skeleton = _build_compact_json_skeleton(response_model)
        skeleton_json = json.dumps(skeleton, separators=(",", ":"))
        return f"You MUST respond ONLY with valid JSON conforming to this schema structure:\n{skeleton_json}"
    except Exception:
        fallback_schema = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
        return f"You MUST respond ONLY with valid JSON conforming to this JSON Schema:\n{fallback_schema}"


def clean_and_parse_json(raw_content: str) -> Dict[str, Any]:
    """
    Resilient JSON extractor handling raw JSON, markdown code fences,
    and reasoning models (<think>...</think> tags such as DeepSeek R1).
    """
    text = (raw_content or "").strip()

    # Remove DeepSeek / reasoning thought blocks and prefill closing tags
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^</think>\s*", "", text).strip()

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
        raise ValueError("LLM returned an empty response")

    # Fast path: try raw extracted text first
    try:
        return json.loads(text)
    except Exception:
        pass

    # Normalize typography and curly/smart quotes
    repaired = text.replace("“", '"').replace("”", '"').replace("„", '"').replace("‟", '"')

    # Clean trailing commas in objects and arrays
    repaired = re.sub(r",\s*([\]}])", r"\1", repaired)

    # Insert missing commas between consecutive lines with key/value pairs or objects
    # 1. Between a literal primitive (string, number, true, false, null, ], }) and the next quoted key or object
    repaired = re.sub(r'("|\d+|true|false|null|\]|\})\s*\n\s*(")', r'\1,\n\2', repaired)
    # 2. Between consecutive objects or arrays on separate lines
    repaired = re.sub(r'(\]|\})\s*\n\s*(\{)', r'\1,\n\2', repaired)

    try:
        return json.loads(repaired)
    except Exception:
        pass

    # Balance unclosed brackets / braces if truncated by token limit
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    if open_brackets > 0 or open_braces > 0:
        candidate = repaired.rstrip().rstrip(",")
        candidate += ("]" * max(0, open_brackets)) + ("}" * max(0, open_braces))
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # Fallback: try python ast.literal_eval if single quotes were used
    try:
        val = ast.literal_eval(text)
        if isinstance(val, dict):
            return val
    except Exception:
        pass

    # If all repair attempts failed, raise standard json.loads error
    return json.loads(re.sub(r",\s*([\]}])", r"\1", text))


class BaseLLMClient(ABC):
    """Abstract interface for all LLM inference clients."""

    def __init__(self) -> None:
        self.last_usage: Optional[Dict[str, int]] = None
        self.last_raw_response: str = ""

    def _thread_state(self):
        if not hasattr(self, "_telemetry_state"):
            with _CLIENT_STATE_LOCK:
                if not hasattr(self, "_telemetry_state"):
                    self._telemetry_state = threading.local()
        return self._telemetry_state

    @property
    def last_usage(self):
        return getattr(self._thread_state(), "usage", None)

    @last_usage.setter
    def last_usage(self, value):
        self._thread_state().usage = value

    @property
    def last_raw_response(self):
        return getattr(self._thread_state(), "raw_response", "")

    @last_raw_response.setter
    def last_raw_response(self, value):
        self._thread_state().raw_response = value

    def _capture_usage(self, response: Any, prompt: str, output: str) -> Dict[str, int]:
        self.last_raw_response = str(output or "")
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

    def get_model_name(self) -> str:
        """Returns the active model identifier used by the client."""
        return getattr(self, "model", None) or getattr(settings, "llm_model", "unknown")

    def get_last_usage(self) -> Dict[str, int]:
        """Returns the most recent prompt/completion token consumption."""
        return getattr(self, "last_usage", None) or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

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
            max_retries=0,
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
        schema_instruction = format_structured_schema_instruction(response_model)
        augmented_system = (
            f"{system_prompt or ''}\n\n"
            f"{schema_instruction}"
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
            raw_content = response.choices[0].message.content or ""
            self._capture_usage(response, prompt, raw_content)
            parsed_dict = clean_and_parse_json(raw_content)
            return response_model.model_validate(parsed_dict)
        except Exception as err:
            if use_json_object and self.compatibility_mode == "auto" and _is_format_error(err):
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                )
                raw_content = response.choices[0].message.content or ""
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
            timeout=30.0,
            max_retries=0,
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
        content = _completion_content(response, "OpenRouter")
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
            raw_content = _completion_content(response, "OpenRouter")
            self._capture_usage(response, prompt, raw_content)
            parsed_dict = clean_and_parse_json(raw_content)
            return response_model.model_validate(parsed_dict)
        except Exception as err:
            if use_json_object and self.compatibility_mode == "auto" and _is_format_error(err):
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                )
                raw_content = _completion_content(response, "OpenRouter")
                self._capture_usage(response, prompt, raw_content)
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            raise err


class GroqClient(BaseLLMClient):
    """Client for Groq Cloud API with ultra-fast inference and multi-key failover across all configured keys."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secondary_api_key: Optional[str] = None,
        tertiary_api_key: Optional[str] = None,
        quaternary_api_key: Optional[str] = None,
        quinary_api_key: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        from groq import Groq

        keys: List[str] = []
        if api_keys:
            keys.extend([k for k in api_keys if k and k not in keys])
        for k in [api_key, secondary_api_key, tertiary_api_key, quaternary_api_key, quinary_api_key]:
            if k and k not in keys:
                keys.append(k)
        if not keys:
            keys = settings.get_provider_keys("groq")
        if not keys:
            raise ValueError("GROQ_API_KEY must be provided or set in environment variables.")

        self.api_keys = keys
        self.api_key = keys[0]
        self.secondary_api_key = keys[1] if len(keys) > 1 else None
        self.tertiary_api_key = keys[2] if len(keys) > 2 else None
        self.quaternary_api_key = keys[3] if len(keys) > 3 else None
        self.quinary_api_key = keys[4] if len(keys) > 4 else None

        self.model = model or settings.groq_model
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode
        self.clients = [Groq(api_key=k, timeout=20.0, max_retries=0) for k in self.api_keys]
        self.client = self.clients[0]
        self.secondary_client = self.clients[1] if len(self.clients) > 1 else None
        self.tertiary_client = self.clients[2] if len(self.clients) > 2 else None
        self.last_key_used: str = "primary"

    def _get_candidate_models(self) -> List[str]:
        candidates = [self.model]
        for fallback in ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]:
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def _is_rate_limit_error(self, err: Exception) -> bool:
        err_msg = str(err).lower()
        return any(
            x in err_msg
            for x in ["429", "rate_limit", "rate limit", "ratelimit", "tpm", "rpm", "rpd", "tpd", "quota", "resource_exhausted"]
        )

    def _get_active_clients_and_keys(self) -> List[tuple[str, Any]]:
        client_candidates = [
            (getattr(self, "api_key", self.api_keys[0] if getattr(self, "api_keys", None) else "default"), getattr(self, "client", None)),
            (getattr(self, "secondary_api_key", self.api_keys[1] if len(getattr(self, "api_keys", [])) > 1 else None), getattr(self, "secondary_client", None)),
            (getattr(self, "tertiary_api_key", self.api_keys[2] if len(getattr(self, "api_keys", [])) > 2 else None), getattr(self, "tertiary_client", None)),
            (getattr(self, "quaternary_api_key", self.api_keys[3] if len(getattr(self, "api_keys", [])) > 3 else None), getattr(self, "quaternary_client", None)),
            (getattr(self, "quinary_api_key", self.api_keys[4] if len(getattr(self, "api_keys", [])) > 4 else None), getattr(self, "quinary_client", None)),
        ]
        active = [(k, c) for k, c in client_candidates if c is not None and k is not None]
        if not active and hasattr(self, "clients") and hasattr(self, "api_keys"):
            active = list(zip(self.api_keys, self.clients))
        return active

    def _execute_chat_completion(self, kwargs: Dict[str, Any]) -> Any:
        errors = []
        active_pairs = self._get_active_clients_and_keys()
        for idx, (k, cli) in enumerate(active_pairs):
            if is_model_in_cooldown("groq", self.model, k):
                continue
            try:
                res = _paced_groq_call(cli, kwargs, k)
                key_names = ["primary", "secondary", "tertiary", "quaternary", "quinary"]
                self.last_key_used = key_names[idx] if idx < len(key_names) else f"key_{idx + 1}"
                return res
            except Exception as err:
                errors.append(err)
                record_model_failure("groq", self.model, err, k)
                logger.warning(
                    "Groq key %d failed for model [%s]: %s. Immediately failing over to next Groq key with 0 cooldown...",
                    idx + 1,
                    self.model,
                    err,
                )
                continue
        if errors:
            raise errors[-1]
        raise RuntimeError("All Groq API keys are currently cooling down.")

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

        response = self._execute_chat_completion({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        })
        return response.choices[0].message.content or ""

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        schema_instruction = format_structured_schema_instruction(response_model)
        augmented_system = (
            f"{system_prompt or ''}\n\n"
            f"{schema_instruction}"
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
            "max_tokens": settings.groq_parser_max_output_tokens if response_model.__name__ == "ParsedCV"
                else settings.groq_jd_max_output_tokens if response_model.__name__ == "StructuredJobPosting"
                else min(700 if response_model.__name__ == "RequirementMatch" else 4096, settings.groq_max_output_tokens),
        }
        if self.model.startswith("qwen/qwen3"):
            kwargs.update(reasoning_effort="none", reasoning_format="hidden")
        elif self.model.startswith("openai/gpt-oss"):
            kwargs.update(reasoning_effort="low", include_reasoning=False)
        if use_json_object:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._execute_chat_completion(kwargs)
            raw_content = response.choices[0].message.content or ""
            self._capture_usage(response, prompt, raw_content)
            if getattr(response.choices[0], "finish_reason", None) == "length":
                raise StructuredOutputTruncatedError("Groq structured output was truncated at its token budget; use a larger-capacity fallback.")
            parsed_dict = clean_and_parse_json(raw_content)
            return response_model.model_validate(parsed_dict)
        except Exception as err:
            json_rejected = getattr(err, "status_code", None) == 400 and any(
                marker in str(err).lower() for marker in ("json_validate_failed", "failed to validate json"))
            if json_rejected:
                body = getattr(err, "body", None)
                detail = body.get("error", body) if isinstance(body, dict) else {}
                failed_generation = detail.get("failed_generation") if isinstance(detail, dict) else None
                if isinstance(failed_generation, str):
                    try:
                        # Only accept a complete response that passes the same schema validation.
                        result = response_model.model_validate(json.loads(failed_generation))
                        self._capture_usage(None, prompt, failed_generation)
                        return result
                    except ValueError:
                        pass
            if use_json_object and self.compatibility_mode == "auto" and (_is_format_error(err) or json_rejected):
                kwargs_retry = dict(kwargs)
                kwargs_retry.pop("response_format", None)
                response = self._execute_chat_completion(kwargs_retry)
                raw_content = response.choices[0].message.content or ""
                self._capture_usage(response, prompt, raw_content)
                if getattr(response.choices[0], "finish_reason", None) == "length":
                    raise StructuredOutputTruncatedError("Groq structured output was truncated at its token budget; use a larger-capacity fallback.")
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            raise err


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
            timeout=25.0,
            max_retries=0,
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
        schema_instruction = format_structured_schema_instruction(response_model)
        augmented_system = (
            f"{system_prompt or ''}\n\n"
            f"{schema_instruction}"
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
            raw_content = response.choices[0].message.content or ""
            parsed_dict = clean_and_parse_json(raw_content)
            return response_model.model_validate(parsed_dict)
        except Exception as err:
            if use_json_object and self.compatibility_mode == "auto" and _is_format_error(err):
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4096,
                )
                raw_content = response.choices[0].message.content or ""
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            raise err


class GeminiClient(BaseLLMClient):
    """Client for Google Gemini (AI Studio) via official OpenAI-compatible endpoint with multi-key failover."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secondary_api_key: Optional[str] = None,
        tertiary_api_key: Optional[str] = None,
        quaternary_api_key: Optional[str] = None,
        quinary_api_key: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        from openai import OpenAI

        keys: List[str] = []
        if api_keys:
            keys.extend([k for k in api_keys if k and k not in keys])
        for k in [api_key, secondary_api_key, tertiary_api_key, quaternary_api_key, quinary_api_key]:
            if k and k not in keys:
                keys.append(k)
        if not keys:
            keys = settings.get_provider_keys("gemini")
        if not keys:
            raise ValueError("GEMINI_API_KEY must be provided or set in environment variables.")

        self.api_keys = keys
        self.api_key = keys[0]
        self.secondary_api_key = keys[1] if len(keys) > 1 else None
        self.tertiary_api_key = keys[2] if len(keys) > 2 else None
        self.quaternary_api_key = keys[3] if len(keys) > 3 else None
        self.quinary_api_key = keys[4] if len(keys) > 4 else None

        self.base_url = base_url or settings.gemini_base_url
        self.model = model or settings.gemini_model
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode

        self.clients = [
            OpenAI(base_url=self.base_url, api_key=k, timeout=60.0, max_retries=0)
            for k in self.api_keys
        ]
        self.client = self.clients[0]
        self.secondary_client = self.clients[1] if len(self.clients) > 1 else None
        self.tertiary_client = self.clients[2] if len(self.clients) > 2 else None
        self.last_key_used: str = "primary"

    def _get_active_clients_and_keys(self) -> List[tuple[str, Any]]:
        client_candidates = [
            (getattr(self, "api_key", self.api_keys[0] if getattr(self, "api_keys", None) else "default"), getattr(self, "client", None)),
            (getattr(self, "secondary_api_key", self.api_keys[1] if len(getattr(self, "api_keys", [])) > 1 else None), getattr(self, "secondary_client", None)),
            (getattr(self, "tertiary_api_key", self.api_keys[2] if len(getattr(self, "api_keys", [])) > 2 else None), getattr(self, "tertiary_client", None)),
            (getattr(self, "quaternary_api_key", self.api_keys[3] if len(getattr(self, "api_keys", [])) > 3 else None), getattr(self, "quaternary_client", None)),
            (getattr(self, "quinary_api_key", self.api_keys[4] if len(getattr(self, "api_keys", [])) > 4 else None), getattr(self, "quinary_client", None)),
        ]
        active = [(k, c) for k, c in client_candidates if c is not None and k is not None]
        if not active and hasattr(self, "clients") and hasattr(self, "api_keys"):
            active = list(zip(self.api_keys, self.clients))
        return active

    def _is_rate_limit_error(self, err: Exception) -> bool:
        err_msg = str(err).lower()
        return any(
            x in err_msg
            for x in ["429", "rate_limit", "rate limit", "ratelimit", "tpm", "rpm", "rpd", "tpd", "quota", "resource_exhausted"]
        )

    def _execute_chat_completion(self, kwargs: Dict[str, Any]) -> Any:
        errors = []
        active_pairs = self._get_active_clients_and_keys()
        for idx, (k, cli) in enumerate(active_pairs):
            if is_model_in_cooldown("gemini", self.model, k):
                continue
            try:
                res = cli.chat.completions.create(**kwargs)
                key_names = ["primary", "secondary", "tertiary", "quaternary", "quinary"]
                self.last_key_used = key_names[idx] if idx < len(key_names) else f"key_{idx + 1}"
                return res
            except Exception as err:
                errors.append(err)
                record_model_failure("gemini", self.model, err, k)
                logger.warning(
                    "Gemini key %d failed for model [%s]: %s. Immediately failing over to next Gemini key with 0 cooldown...",
                    idx + 1,
                    self.model,
                    err,
                )
                continue
        if errors:
            raise errors[-1]
        raise RuntimeError("All Gemini API keys are currently cooling down.")

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

        response = self._execute_chat_completion({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        })
        return response.choices[0].message.content or ""

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        schema_instruction = format_structured_schema_instruction(response_model)
        augmented_system = (
            f"{system_prompt or ''}\n\n"
            f"{schema_instruction}"
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

            response = self._execute_chat_completion(kwargs)
            raw_content = response.choices[0].message.content or ""
            parsed_dict = clean_and_parse_json(raw_content)
            return response_model.model_validate(parsed_dict)
        except Exception as err:
            if use_json_object and self.compatibility_mode == "auto" and _is_format_error(err):
                response = self._execute_chat_completion({
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                })
                raw_content = response.choices[0].message.content or ""
                parsed_dict = clean_and_parse_json(raw_content)
                return response_model.model_validate(parsed_dict)
            raise err


class CohereClient(BaseLLMClient):
    """
    Client for Cohere API (v2) supporting Command R, Command R+, Aya Expanse models,
    with native JSON schema extraction, usage token tracking, and dual-key failover.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secondary_api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        import httpx

        self.api_key = api_key or getattr(settings, "cohere_api_key", None)
        if not self.api_key:
            raise ValueError("COHERE_API_KEY must be provided or set in environment variables.")

        cfg_secondary = getattr(settings, "cohere_secondary_api_key", None)
        if secondary_api_key and secondary_api_key != self.api_key:
            self.secondary_api_key = secondary_api_key
        elif cfg_secondary and cfg_secondary != self.api_key:
            self.secondary_api_key = cfg_secondary
        else:
            self.secondary_api_key = None

        raw_url = (base_url or getattr(settings, "cohere_base_url", "https://api.cohere.com/v2")).rstrip("/")
        self.base_url = raw_url
        self.model = model or getattr(settings, "cohere_model", "command-r-08-2024")
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode
        self.last_key_used = "primary"

        timeout_sec = min(float(getattr(settings, "screening_ai_request_seconds", 25.0)), 25.0)
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Atos-AI/1.0",
            },
            timeout=timeout_sec,
        )
        self.secondary_client = (
            httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.secondary_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Atos-AI/1.0",
                },
                timeout=timeout_sec,
            )
            if self.secondary_api_key
            else None
        )

    def _execute_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes chat request with automatic secondary key failover upon 429."""
        active_client = self.client
        self.last_key_used = "primary"

        try:
            resp = active_client.post("/chat", json=payload)
            if resp.status_code == 429 and self.secondary_client:
                logger.warning("Cohere primary key hit rate limit (429); failing over to secondary key.")
                self.last_key_used = "secondary"
                record_model_failure("cohere", self.model, RuntimeError("429 Rate Limit"), self.api_key)
                resp = self.secondary_client.post("/chat", json=payload)

            if resp.status_code != 200:
                resp.raise_for_status()

            return resp.json()
        except Exception as e:
            if getattr(e, "response", None) is not None and e.response.status_code == 429:
                used_key = self.secondary_api_key if self.last_key_used == "secondary" else self.api_key
                record_model_failure("cohere", self.model, e, used_key)
            raise

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

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        t0 = time.perf_counter()
        data = self._execute_request(payload)
        lat_ms = (time.perf_counter() - t0) * 1000.0

        content = ""
        msg = data.get("message", {})
        for part in msg.get("content", []):
            if part.get("type") == "text":
                content += part.get("text", "")

        self.last_raw_response = content
        self._capture_usage(data, prompt, content, lat_ms)
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

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        t0 = time.perf_counter()
        data = self._execute_request(payload)
        lat_ms = (time.perf_counter() - t0) * 1000.0

        content = ""
        msg = data.get("message", {})
        for part in msg.get("content", []):
            if part.get("type") == "text":
                content += part.get("text", "")

        self.last_raw_response = content
        self._capture_usage(data, prompt, content, lat_ms)
        parsed_dict = clean_and_parse_json(content)
        return response_model.model_validate(parsed_dict)

    def _capture_usage(self, data: Dict[str, Any], prompt: str, completion: str, lat_ms: float = 0.0) -> None:
        usage = data.get("usage", {}).get("tokens", {})
        pt = usage.get("input_tokens") or max(1, len(prompt) // 4)
        ct = usage.get("output_tokens") or max(1, len(completion) // 4)
        self.last_usage = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
        }
        try:
            from backend.services.token_tracker import TokenTracker
            tracker = TokenTracker.get_instance()
            tracker.record_call(
                provider="cohere",
                model=self.model,
                prompt_tokens=pt,
                completion_tokens=ct,
                latency_ms=lat_ms,
                status="success",
            )
        except Exception:
            pass


class OllamaClient(BaseLLMClient):
    """
    Client for local Ollama instance with privacy guarantees, hardware-optimized context windows,
    rolling context sliding window, thinking toggle, live speed telemetry, and small-model prompt enhancement.
    """

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
        self.client = ollama.Client(host=self.base_url, timeout=getattr(settings, "ollama_timeout_seconds", 300.0))

    def _get_execution_options(self, temperature: float = 0.0) -> Dict[str, Any]:
        """Builds hardware-tuned generation options for the local engine."""
        num_ctx = getattr(settings, "local_context_window", 16384)
        num_gpu = 999
        max_tok = getattr(settings, "local_max_tokens", 3072)
        opts: Dict[str, Any] = {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": max_tok,
            "num_gpu": num_gpu,
            "main_gpu": 0,
        }
        return opts

    def _apply_rolling_context(self, prompt: str) -> str:
        """
        Sliding / rolling window protection for continuous generation without out-of-memory (OOM) errors.
        When rolling context is enabled, oversized prompts are gracefully truncated to the most recent/salient text.
        """
        if not getattr(settings, "local_rolling_context", True):
            return prompt

        num_ctx = getattr(settings, "local_context_window", 4096)
        # Allow prompt to take at most ~70% of context window (approx 4 chars/token)
        max_prompt_chars = int(num_ctx * 0.7 * 4.0)

        if len(prompt) > max_prompt_chars:
            head_chars = int(max_prompt_chars * 0.2)
            tail_chars = max_prompt_chars - head_chars
            prompt = (
                f"{prompt[:head_chars]}\n\n"
                f"... [Rolling Context: intermediate lines condensed to prevent local VRAM OOM] ...\n\n"
                f"{prompt[-tail_chars:]}"
            )
        return prompt

    def _enhance_system_prompt_for_local_model(
        self,
        system_prompt: Optional[str] = None,
        response_model: Optional[Type[T]] = None,
    ) -> str:
        """
        Enhances system prompt for smaller local models (e.g. MiniCPM 2B, Qwen 2B, SmolLM).
        Suppresses unwanted thinking/monologue tags if disabled, and enforces strict, concise schema compliance.
        """
        thinking_enabled = getattr(settings, "local_thinking_enabled", False)
        base = (system_prompt or "").strip()

        directives = []
        if not thinking_enabled:
            directives.append(
                "STRICT EFFICIENCY DIRECTIVE: Do NOT output any internal monologue, scratchpad, reasoning, or <think>...</think> tags. "
                "Provide the final direct answer immediately."
            )

        if response_model is not None:
            try:
                skeleton = _build_compact_json_skeleton(response_model)
                skeleton_json = json.dumps(skeleton, indent=2)
            except Exception:
                skeleton_json = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
            directives.append(
                "STRICT JSON OUTPUT DIRECTIVE:\n"
                "1. Output a SINGLE valid JSON object adhering strictly to the JSON schema structure below.\n"
                "2. Use the EXACT property names shown in the template (e.g. 'job_title', 'company_name', 'degree_title', 'institution_name').\n"
                "3. Ensure list fields (e.g. 'skills', 'certifications', 'work_description') are flat JSON arrays of strings like [\"Python\", \"Docker\"], NOT nested objects or categorized dictionaries.\n"
                "4. Do NOT output conversational text, markdown formatting, explanations, or commentary outside the JSON.\n"
                f"JSON Template:\n{skeleton_json}"
            )

        directive_block = "\n\n".join(directives)
        if base and directive_block:
            return f"{base}\n\n{directive_block}"
        return base or directive_block

    def _record_telemetry(
        self,
        prompt: str,
        response: Any,
        duration_s: float,
        action: str = "general",
    ) -> None:
        """Records token metrics and generation speed (tokens/sec) into the token tracker."""
        p_eval = getattr(response, "prompt_eval_count", None) or max(1, len(prompt) // 4)
        c_eval = getattr(response, "eval_count", None) or 0
        eval_dur_ns = getattr(response, "eval_duration", None) or 0

        lat_ms = duration_s * 1000.0
        self.last_usage = {
            "prompt_tokens": p_eval,
            "completion_tokens": c_eval,
            "total_tokens": p_eval + c_eval,
        }

        try:
            from backend.services.token_tracker import token_tracker
            token_tracker.record_usage(
                provider="ollama",
                model=self.model,
                prompt_tokens=p_eval,
                completion_tokens=c_eval,
                total_tokens=p_eval + c_eval,
                action=action,
                latency_ms=lat_ms,
                status="success",
            )
        except Exception:
            pass

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        prompt = self._apply_rolling_context(prompt)
        sys_prompt = self._enhance_system_prompt_for_local_model(system_prompt)

        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": prompt})
        t0 = time.perf_counter()
        response = self.client.chat(
            model=self.model,
            messages=messages,
            stream=False,
            think=getattr(settings, "local_thinking_enabled", False),
            options=self._get_execution_options(temperature=temperature),
        )
        duration_s = time.perf_counter() - t0

        self._record_telemetry(prompt, response, duration_s, action="text_generation")
        content = (response.message.content or "").strip()

        # If thinking is disabled, sanitize away any residual thinking tags
        if not getattr(settings, "local_thinking_enabled", False):
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            content = re.sub(r"^</think>\s*", "", content).strip()

        return content

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        prompt = self._apply_rolling_context(prompt)
        augmented_system = self._enhance_system_prompt_for_local_model(
            system_prompt=system_prompt,
            response_model=response_model,
        )

        messages = [
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": prompt},
        ]
        t0 = time.perf_counter()
        response = self.client.chat(
            model=self.model,
            messages=messages,
            format="json",
            stream=False,
            think=getattr(settings, "local_thinking_enabled", False),
            options=self._get_execution_options(temperature=temperature),
        )
        duration_s = time.perf_counter() - t0

        self._record_telemetry(prompt, response, duration_s, action="structured_generation")
        raw_content = response.message.content or ""
        parsed_dict = clean_and_parse_json(raw_content)
        return response_model.model_validate(parsed_dict)


class LMStudioClient(BaseLLMClient):
    """
    Client for local LM Studio instance (or other OpenAI-compatible local engines)
    running locally on port 1234 with zero data egress and 100% local GPU acceleration.
    Features 16,384-token sliding/rolling window protection against VRAM OOM errors.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        compatibility_mode: Optional[str] = None,
    ) -> None:
        from openai import OpenAI

        raw_url = (base_url or getattr(settings, "lmstudio_base_url", "http://localhost:1234/v1")).rstrip("/")
        if not raw_url.endswith("/v1"):
            raw_url = f"{raw_url}/v1"
        self.base_url = raw_url
        self.model = model or getattr(settings, "lmstudio_model", "default")
        self.compatibility_mode = compatibility_mode or settings.compatibility_mode

        self.client = OpenAI(
            base_url=self.base_url,
            api_key="lm-studio",
            timeout=getattr(settings, "lmstudio_timeout_seconds", 300.0),
            max_retries=0,
        )
        if self.model in ("default", "", None):
            try:
                models_list = self.client.models.list()
                if models_list and models_list.data:
                    self.model = models_list.data[0].id
            except Exception:
                pass

    def _apply_rolling_context(self, prompt: str) -> str:
        """
        Sliding / rolling window protection for continuous generation without out-of-memory (OOM) errors.
        When rolling context is active, oversized prompts are gracefully condensed to fit within the 16k context window.
        """
        if not getattr(settings, "local_rolling_context", True):
            return prompt

        num_ctx = getattr(settings, "local_context_window", 16384)
        # Allocate up to ~75% of context window for prompt text (~4 chars/token)
        max_prompt_chars = int(num_ctx * 0.75 * 4.0)

        if len(prompt) > max_prompt_chars:
            head_chars = int(max_prompt_chars * 0.25)
            tail_chars = max_prompt_chars - head_chars
            prompt = (
                f"{prompt[:head_chars]}\n\n"
                f"... [Rolling Context Active: intermediate text condensed to fit {num_ctx} token context and prevent local VRAM OOM] ...\n\n"
                f"{prompt[-tail_chars:]}"
            )
        return prompt

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        prompt = self._apply_rolling_context(prompt)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=getattr(settings, "local_max_tokens", 3072),
        )
        duration_s = time.perf_counter() - t0
        content = response.choices[0].message.content or ""
        self.last_raw_response = content
        self._capture_usage(response, prompt, content, duration_s)
        return content

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        prompt = self._apply_rolling_context(prompt)
        compact_skeleton = json.dumps(_build_compact_json_skeleton(response_model), indent=2)
        system_content = (
            f"{system_prompt or ''}\n\n"
            "You MUST output valid JSON matching the following structure:\n"
            f"{compact_skeleton}"
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        t0 = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=getattr(settings, "local_max_tokens", 3072),
            )
        except Exception as error:
            # Only retry without JSON mode when the server rejects that request format.
            if getattr(error, "status_code", None) not in (400, 422):
                raise
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=getattr(settings, "local_max_tokens", 3072),
            )

        duration_s = time.perf_counter() - t0
        raw_content = response.choices[0].message.content or ""
        self.last_raw_response = raw_content
        self._capture_usage(response, prompt, raw_content, duration_s)
        parsed_dict = clean_and_parse_json(raw_content)
        return response_model.model_validate(parsed_dict)

    def _capture_usage(self, response: Any, prompt: str, completion: str, duration_s: float = 0.0) -> None:
        try:
            usage = getattr(response, "usage", None)
            pt = getattr(usage, "prompt_tokens", None) or max(1, len(prompt) // 4)
            ct = getattr(usage, "completion_tokens", None) or max(1, len(completion) // 4)
            self.last_usage = {
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": pt + ct,
            }
            from backend.services.token_tracker import TokenTracker
            tracker = TokenTracker.get_instance()
            tracker.record_call(
                provider="lmstudio",
                model=self.model,
                prompt_tokens=pt,
                completion_tokens=ct,
                latency_ms=duration_s * 1000.0,
                status="success",
            )
        except Exception:
            pass


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
        return GroqClient(
            api_key=api_key,
            secondary_api_key=getattr(settings, "groq_secondary_api_key", None),
            tertiary_api_key=getattr(settings, "groq_tertiary_api_key", None),
            model=model,
            compatibility_mode=compatibility_mode,
        )
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
            secondary_api_key=getattr(settings, "gemini_secondary_api_key", None),
            base_url=base_url,
            model=model,
            compatibility_mode=compatibility_mode,
        )
    elif selected == "cohere":
        return CohereClient(
            api_key=api_key,
            secondary_api_key=getattr(settings, "cohere_secondary_api_key", None),
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
    elif selected == "lmstudio":
        return LMStudioClient(
            base_url=base_url,
            model=model,
            compatibility_mode=compatibility_mode,
        )
    else:
        raise ValueError(
            f"Unsupported LLM provider '{selected}'. "
            f"Choose 'agnes', 'groq', 'openrouter', 'nvidia_nim', 'gemini', 'ollama', or 'lmstudio'."
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
        return "qwen/qwen3.8-27b"
    elif prov == "nvidia_nim":
        return "meta/llama-3.2-11b-vision-instruct"
    elif prov == "gemini":
        return "gemini-3.5-flash"
    elif prov == "openrouter":
        return "openrouter/free"
    elif prov == "cohere":
        return getattr(settings, "cohere_model", "command-r-08-2024") or "command-r-08-2024"
    elif prov == "ollama":
        return "qwen3.5:2b-q4_K_M"
    elif prov == "lmstudio":
        return getattr(settings, "lmstudio_model", "default") or "default"
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


_MODEL_COOLDOWNS: Dict[Tuple[str, str, Optional[str]], float] = {}
_LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio"})


def record_model_failure(provider: str, model: str, error: Exception, key: Optional[str] = None) -> None:
    """
    Marks a provider/model target (optionally key-specific) in temporary cooldown to prevent
    cascading repeated retries across concurrent threads or batch evaluation items.
    """
    if provider.lower() in _LOCAL_PROVIDERS or isinstance(error, ProviderCoolingDownError) or _is_document_output_error(error):
        return
    err_str = str(error).lower()
    # Permanent or long-lasting failures: 404 Not Found, 410 Gone, 402 Insufficient credits
    if any(code in err_str for code in ["404", "not_found", "not found", "410", "gone", "insufficient credits", "insufficient_quota"]):
        cooldown = 1800.0  # 30 minutes
    # Rate limit or quota exhaustion
    elif getattr(error, "status_code", None) == 429 or any(code in err_str for code in ["429", "rate_limit", "rate limit", "quota", "resource_exhausted"]):
        retry_after = _retry_after_seconds(error)
        if retry_after is not None:
            cooldown = max(1.0, retry_after + .25)
        else:
            cooldown = 300.0 if any(w in err_str for w in ["daily quota exceeded", "quota per day exceeded"]) else 30.0
    else:
        cooldown = 30.0        # 30 seconds for general errors / timeouts

    _MODEL_COOLDOWNS[(provider.lower(), model, key)] = time.time() + cooldown
    if key is None:
        _MODEL_COOLDOWNS[(provider.lower(), model, None)] = time.time() + cooldown

    logger.warning(
        "Failover circuit breaker: Marked [%s / %s%s] in cooldown for %.1fs. Error snippet: %s",
        provider,
        model,
        f" (key ...{key[-6:]})" if key else "",
        cooldown,
        err_str[:120],
    )


def is_model_in_cooldown(provider: str, model: str, key: Optional[str] = None) -> bool:
    """Returns True if the provider/model (or key-specific target) is currently under failure cooldown."""
    if provider.lower() in _LOCAL_PROVIDERS:
        return False
    now = time.time()
    if key is not None:
        key_expires = _MODEL_COOLDOWNS.get((provider.lower(), model, key), 0.0)
        if now < key_expires:
            return True
    general_expires = _MODEL_COOLDOWNS.get((provider.lower(), model, None), 0.0)
    return now < general_expires


def clear_model_cooldown(provider: str, model: str, key: Optional[str] = None) -> None:
    """Removes model from failure cooldown upon confirmed healthy generation."""
    _MODEL_COOLDOWNS.pop((provider.lower(), model, key), None)
    _MODEL_COOLDOWNS.pop((provider.lower(), model, None), None)


def clear_all_model_cooldowns() -> None:
    """Resets all active failover circuit breaker cooldowns."""
    _MODEL_COOLDOWNS.clear()


def get_active_cooldown_statuses() -> Dict[str, Dict[str, Any]]:
    """Returns a dict of currently cooling down / exhausted models with remaining cooldown seconds."""
    now = time.time()
    result = {}
    with _CLIENT_STATE_LOCK:
        # Group active cooldowns by (provider, model)
        grouped: Dict[Tuple[str, str], Dict[Optional[str], float]] = {}
        for (provider, model, key), expires in list(_MODEL_COOLDOWNS.items()):
            if provider.lower() in _LOCAL_PROVIDERS:
                continue
            remaining = expires - now
            if remaining > 0:
                grouped.setdefault((provider.lower(), model), {})[key] = remaining

        for (provider, model), key_cooldowns in grouped.items():
            if None in key_cooldowns:
                remaining = key_cooldowns[None]
                target_key = f"{provider}:{model}"
                result[target_key] = {
                    "provider": provider,
                    "model": model,
                    "remaining_seconds": round(remaining, 1),
                    "exhausted": remaining > 300.0,
                }
                continue

            # Check configured keys for this provider
            keys = []
            for k_attr in [f"{provider}_api_key", f"{provider}_secondary_api_key", f"{provider}_tertiary_api_key"]:
                k_val = getattr(settings, k_attr, None)
                if k_val and k_val not in keys:
                    keys.append(k_val)

            if keys:
                # Only flag model if ALL configured keys are currently in cooldown
                all_cooling = all(k in key_cooldowns for k in keys)
                if all_cooling:
                    remaining = min(key_cooldowns[k] for k in keys)
                    target_key = f"{provider}:{model}"
                    result[target_key] = {
                        "provider": provider,
                        "model": model,
                        "remaining_seconds": round(remaining, 1),
                        "exhausted": remaining > 300.0,
                    }
            else:
                remaining = max(key_cooldowns.values())
                target_key = f"{provider}:{model}"
                result[target_key] = {
                    "provider": provider,
                    "model": model,
                    "remaining_seconds": round(remaining, 1),
                    "exhausted": remaining > 300.0,
                }
    return result


def _cooling_down_error(chain, details="", failures=()):
    now = time.time()
    expiries = []
    all_cooling = True
    for provider, model, client in chain:
        key = getattr(client, "api_key", None)
        if not is_model_in_cooldown(provider, model, key):
            all_cooling = False
        else:
            expiries.append(max(_MODEL_COOLDOWNS.get((provider.lower(), model, key), 0),
                                _MODEL_COOLDOWNS.get((provider.lower(), model, None), 0)))
    temporary_failure = any(
        getattr(error, "retryable", False) or isinstance(error, TimeoutError)
        or getattr(error, "status_code", None) in (408, 429, 500, 502, 503, 504)
        or re.search(r"\b429\b|rate.?limit|quota|timed?\s*out|connection error", str(error), re.I)
        for error in failures)
    # A slow fallback can outlast the first provider's cooldown. That does not
    # turn an upstream outage into a permanent candidate evaluation failure.
    if chain and (all_cooling or temporary_failure):
        return LLMProvidersCoolingDownError(min(expiries) - now if expiries else 2, details)
    return None


class DynamicLLMClient(BaseLLMClient):
    """
    Dynamic LLM client proxy with multi-tier failover protection.
    Resolves the active provider, model, and credentials from runtime settings,
    and automatically falls over through intra-provider alternatives and cross-provider
    configured endpoints if any model encounters an error, rate limit, timeout, or outage.
    """

    def __init__(self) -> None:
        self._client_cache: Dict[Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]], BaseLLMClient] = {}

    @staticmethod
    def _generate_with_local_retry(provider, fallback_enabled, generate, **kwargs):
        """Retry the same local target when failover is disabled, with a bounded wait."""
        attempts = 3 if provider.lower() in _LOCAL_PROVIDERS and not fallback_enabled else 1
        for attempt in range(attempts):
            try:
                result = generate(**kwargs)
                if isinstance(result, str) and not result.strip():
                    raise ValueError("LLM returned an empty response")
                return result
            except Exception as error:
                if attempt + 1 == attempts:
                    raise
                delay = attempt + 1
                logger.warning("Local model request failed (%s); retrying in %ss (%s/%s).", error, delay, attempt + 1, attempts - 1)
                time.sleep(delay)

    def freeze_configuration(self) -> None:
        """Retain this run's factory targets without changing shared Admin settings."""
        self._snapshot_fallback_enabled = settings.fallback_enabled
        self._snapshot_chain = self.get_fallback_chain()

    def get_healthy_provider_pool(self) -> list:
        """
        Returns a list of unique, healthy provider clients currently available for parallel dispatch.
        Spreads concurrently across all healthy distinct API keys to multiply rate limit quotas.
        """
        chain = self.get_fallback_chain()
        healthy = []
        seen_targets = set()
        for prov, mod, client in chain:
            key = getattr(client, "api_key", None)
            if not is_model_in_cooldown(prov, mod, key):
                target_ident = (prov, mod, key)
                if target_ident not in seen_targets:
                    healthy.append((prov, mod, client))
                    seen_targets.add(target_ident)
        return healthy

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
                # The dynamic chain owns key rotation; a per-key client must not
                # internally retry the same secondary keys again.
                if isinstance(client, (GroqClient, GeminiClient)) and api_key:
                    client.api_keys = [api_key]
                    client.clients = [client.clients[0]] if getattr(client, "clients", None) else []
                    client.secondary_client = None
                    if hasattr(client, "tertiary_client"):
                        client.tertiary_client = None
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
        if hasattr(self, "_snapshot_chain"):
            return list(self._snapshot_chain)
        chain: List[Tuple[str, str, BaseLLMClient]] = []
        seen_targets = set()

        def get_provider_keys(prov: str) -> List[str]:
            return settings.get_provider_keys(prov)

        def add_candidate(
            prov: str,
            mod: Optional[str],
            key: Optional[str] = None,
            url: Optional[str] = None,
            mode: Optional[str] = None,
        ):
            if not prov or not mod:
                return
            if prov.lower() == "nvidia_nim" and mod == "nvidia/llama-3.1-nemotron-70b-instruct":
                return  # Retired endpoint returns an account-level 404; never schedule it.
            target_key = (prov.lower(), mod, key)
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

        def add_model_candidates(
            prov: str,
            mod: Optional[str],
            url: Optional[str] = None,
            mode: Optional[str] = None,
        ):
            if not prov or not mod:
                return
            keys = get_provider_keys(prov.lower())
            if keys:
                for k in keys:
                    add_candidate(prov, mod, key=k, url=url, mode=mode)
            else:
                add_candidate(prov, mod, url=url, mode=mode)

        # If fallback failover is disabled, strictly resolve only the primary configured engine
        if not getattr(settings, "fallback_enabled", True):
            primary_prov = settings.llm_provider.lower()
            primary_model = _get_fallback_primary_model(primary_prov)
            add_candidate(primary_prov, primary_model, key=getattr(settings, f"{primary_prov}_api_key", None))
            return chain

        # Check for user-defined custom fallback hierarchy first
        custom = get_custom_fallback_chain()
        if custom and len(custom) > 0:
            primary_prov = settings.llm_provider.lower()
            primary_model = _get_fallback_primary_model(primary_prov)

            # Ensure current primary model is Tier 1 (with secondary/tertiary key backup)
            add_model_candidates(primary_prov, primary_model)

            # Append custom sequence configured by the user (with secondary/tertiary keys for each target)
            for target in custom:
                t_prov = (target.get("provider") or "").lower()
                t_mod = target.get("model")
                if not t_prov or not t_mod:
                    continue
                t_url = getattr(settings, f"{t_prov}_base_url", None)
                add_model_candidates(t_prov, t_mod, url=t_url)

            if chain:
                healthy_chain = [item for item in chain if not is_model_in_cooldown(item[0], item[1], getattr(item[2], "api_key", None))]
                return healthy_chain if healthy_chain else chain

        # 1. Primary configured model (Default automatic chain: same model with secondary/tertiary keys first)
        primary_prov = settings.llm_provider.lower()
        primary_model = _get_fallback_primary_model(primary_prov)
        add_model_candidates(primary_prov, primary_model)

        # 2. Intra-provider backup models for primary provider (each with secondary/tertiary keys first)
        intra_fallbacks = {
            "agnes": ["agnes-2.5-flash", "agnes-3.0-flash", "agnes-2.0-flash", "agnes-2.5-pro"],
            "groq": ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"],
            "cohere": ["command-r-08-2024", "command-r-plus-08-2024", "c4ai-aya-expanse-32b", "command-r7b-12-2024"],
            "nvidia_nim": ["meta/llama-3.2-11b-vision-instruct", "mistralai/mistral-large-2-instruct"],
            "gemini": ["gemini-3.5-flash", "gemini-2.5-pro"],
            "openrouter": ["openrouter/free", "google/gemini-2.0-flash-exp:free", "meta-llama/llama-3.3-70b-instruct:free"],
            "ollama": [settings.ollama_model, "qwen3.5:2b-q4_K_M", "smollm2:latest", "qwen3:4b"],
            "lmstudio": [settings.lmstudio_model or "default"],
        }
        for fallback_mod in intra_fallbacks.get(primary_prov, []):
            add_model_candidates(primary_prov, fallback_mod)

        # 3. Cross-provider fallbacks: prioritize Groq -> Google Gemini -> Agnes -> NVIDIA NIM -> Cohere -> OpenRouter
        provider_priority = ["groq", "gemini", "agnes", "nvidia_nim", "cohere", "openrouter", "lmstudio", "ollama"]
        for p in provider_priority:
            if p == primary_prov:
                continue

            if p == "groq":
                for m in ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]:
                    add_model_candidates("groq", m)
            elif p == "gemini":
                if settings.gemini_api_key or settings.get_provider_keys("gemini"):
                    add_model_candidates("gemini", settings.gemini_model or "gemini-3.5-flash")
                    add_model_candidates("gemini", "gemini-3.8-flash")
            elif p == "agnes":
                if settings.agnes_api_key:
                    add_model_candidates("agnes", settings.agnes_model or "agnes-2.5-flash")
                    add_model_candidates("agnes", "agnes-3.0-flash")
            elif p == "nvidia_nim":
                if settings.nvidia_nim_api_key:
                    add_model_candidates("nvidia_nim", settings.nvidia_nim_model or "meta/llama-3.2-11b-vision-instruct")
            elif p == "cohere":
                if settings.cohere_api_key or getattr(settings, "cohere_secondary_api_key", None):
                    add_model_candidates("cohere", settings.cohere_model or "command-r-08-2024")
                    add_model_candidates("cohere", "command-r-plus-08-2024")
            elif p == "ollama":
                # Quick probe to see if local Ollama is responding
                if _is_local_port_open("127.0.0.1", 11434):
                    add_model_candidates("ollama", settings.ollama_model or "qwen3.5:2b-q4_K_M")

        if not getattr(settings, "fallback_enabled", True):
            return chain[:1]

        # Circuit breaker: prioritize healthy candidates not currently under failure cooldown
        healthy_chain = [item for item in chain if not is_model_in_cooldown(item[0], item[1], getattr(item[2], "api_key", None))]
        if healthy_chain:
            return healthy_chain

        return chain

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        global _LAST_FALLBACK_EVENT
        action_context = (getattr(self._thread_state(), "action", "general"), copy.deepcopy(getattr(self._thread_state(), "metadata", {})))
        fallback_enabled = getattr(self, "_snapshot_fallback_enabled", getattr(settings, "fallback_enabled", True))
        from backend.services.action_logger import action_logger
        preparation_started = time.perf_counter()
        preparation_id = action_logger.record_start(
            action_type="provider_preparation", provider=settings.llm_provider,
            model="Preparing provider chain", prompt="", metadata=action_context[1],
        )
        try:
            chain = self.get_fallback_chain()
        except Exception as exc:
            action_logger.record_finish(
                call_id=preparation_id, action_type="provider_preparation",
                provider=settings.llm_provider, model="Preparing provider chain", prompt="",
                latency_ms=(time.perf_counter() - preparation_started) * 1000,
                status="error", error=str(exc), metadata=action_context[1],
            )
            raise
        action_logger.record_finish(
            call_id=preparation_id, action_type="provider_preparation",
            provider=settings.llm_provider, model="Preparing provider chain", prompt="",
            latency_ms=(time.perf_counter() - preparation_started) * 1000,
            status="success" if chain else "error",
            error=None if chain else "No configured or reachable providers available",
            metadata=action_context[1],
        )
        if not chain:
            raise RuntimeError("No configured or reachable LLM providers available in fallback chain.")

        if not fallback_enabled:
            chain = chain[:1]

        primary_prov, primary_mod, _ = chain[0]
        last_error: Optional[Exception] = None
        attempt_history: List[str] = []
        attempt_errors: List[Exception] = []

        for idx, (prov, mod, client) in enumerate(chain):
            if fallback_enabled and is_model_in_cooldown(prov, mod, getattr(client, "api_key", None)):
                continue
            t0 = time.perf_counter()
            from backend.services.action_logger import action_logger
            call_id = action_logger.record_start(
                action_type=action_context[0],
                provider=prov,
                model=mod,
                prompt=prompt,
                system_prompt=system_prompt,
                metadata=action_context[1],
            )
            try:
                result = self._generate_with_local_retry(prov, fallback_enabled, client.generate_text,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )
                if isinstance(result, str) and not result.strip():
                    raise ValueError("LLM returned an empty response")
                lat_ms = (time.perf_counter() - t0) * 1000.0
                usage = getattr(client, "last_usage", None) or {}
                p_tok = usage.get("prompt_tokens") or max(1, len(prompt) // 4)
                c_tok = usage.get("completion_tokens") or max(1, len(result) // 4)
                t_tok = usage.get("total_tokens") or (p_tok + c_tok)

                from backend.services.token_tracker import token_tracker
                is_key_failover = getattr(client, "last_key_used", None) in ("secondary", "tertiary")
                call_status = "success" if (idx == 0 and not is_key_failover) else "failover"
                self._thread_state().last_usage = token_tracker.record_usage(
                    provider=prov,
                    model=mod,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                    action=action_context[0],
                    latency_ms=lat_ms,
                    status=call_status,
                )

                raw_resp = getattr(client, "last_raw_response", "") or result
                action_logger.record_finish(
                    call_id=call_id,
                    action_type=action_context[0],
                    provider=prov,
                    model=mod,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    raw_response=raw_resp,
                    parsed_json=None,
                    latency_ms=lat_ms,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                    status=call_status,
                    metadata=action_context[1],
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
                    if not hasattr(self, "_snapshot_chain"):
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
                clear_model_cooldown(prov, mod, getattr(client, "api_key", None))
                return result
            except ProviderCoolingDownError as err:
                last_error = err
                attempt_errors.append(err)
                from backend.services.action_logger import action_logger
                action_logger.record_finish(
                    call_id=call_id,
                    action_type=action_context[0],
                    provider=prov,
                    model=mod,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    raw_response="",
                    parsed_json=None,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    status="cooling_down",
                    error=str(err),
                    metadata=action_context[1],
                )
                continue
            except Exception as err:
                last_error = err
                attempt_errors.append(err)
                from backend.services.action_logger import action_logger
                raw_resp = getattr(client, "last_raw_response", "") or ""
                action_logger.record_finish(
                    call_id=call_id,
                    action_type=action_context[0],
                    provider=prov,
                    model=mod,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    raw_response=raw_resp,
                    parsed_json=None,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    status="error",
                    error=f"{type(err).__name__}: {str(err)}",
                    metadata=action_context[1],
                )
                record_model_failure(prov, mod, err, getattr(client, "api_key", None))
                attempt_history.append(f"{prov}:{mod} ({type(err).__name__}: {str(err)[:100]})")
                if not fallback_enabled:
                    logger.warning(
                        "LLM generation failed on [%s / %s]: %s (Failover disabled).",
                        prov,
                        mod,
                        err,
                    )
                    cooling = None if prov.lower() in _LOCAL_PROVIDERS else _cooling_down_error(chain, failures=[err])
                    if cooling:
                        raise cooling from err
                    raise RuntimeError(
                        f"Primary LLM engine [{prov} / {mod}] failed: {err} (Failover disabled)"
                    ) from err
                logger.warning(
                    "LLM generation failed on [%s / %s]: %s. Advancing to next fallback...",
                    prov,
                    mod,
                    err,
                )
                continue

        cooling = _cooling_down_error(chain, "Attempted: " + "; ".join(attempt_history) if attempt_history else "", attempt_errors)
        if cooling:
            raise cooling from last_error
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
        action_context = (getattr(self._thread_state(), "action", "general"), copy.deepcopy(getattr(self._thread_state(), "metadata", {})))
        fallback_enabled = getattr(self, "_snapshot_fallback_enabled", getattr(settings, "fallback_enabled", True))
        chain = self.get_fallback_chain()
        if not chain:
            raise RuntimeError("No configured or reachable LLM providers available in fallback chain.")

        if not fallback_enabled:
            chain = chain[:1]

        primary_prov, primary_mod, _ = chain[0]
        last_error: Optional[Exception] = None
        attempt_history: List[str] = []
        attempt_errors: List[Exception] = []
        document_rejected_models = set()

        for idx, (prov, mod, client) in enumerate(chain):
            if (prov, mod) in document_rejected_models:
                continue
            if fallback_enabled and is_model_in_cooldown(prov, mod, getattr(client, "api_key", None)):
                continue
            t0 = time.perf_counter()
            from backend.services.action_logger import action_logger
            call_id = action_logger.record_start(
                action_type=action_context[0],
                provider=prov,
                model=mod,
                prompt=prompt,
                system_prompt=system_prompt,
                metadata=action_context[1],
            )
            try:
                result = self._generate_with_local_retry(prov, fallback_enabled, client.generate_structured,
                    prompt=prompt,
                    response_model=response_model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )
                if isinstance(result, str) and not result.strip():
                    raise ValueError("LLM returned an empty response")
                lat_ms = (time.perf_counter() - t0) * 1000.0
                usage = getattr(client, "last_usage", None) or {}
                p_tok = usage.get("prompt_tokens") or max(1, len(prompt) // 4)
                c_tok = usage.get("completion_tokens") or max(1, len(str(result)) // 4)
                t_tok = usage.get("total_tokens") or (p_tok + c_tok)

                from backend.services.token_tracker import token_tracker
                is_key_failover = getattr(client, "last_key_used", None) in ("secondary", "tertiary")
                call_status = "success" if (idx == 0 and not is_key_failover) else "failover"
                self._thread_state().last_usage = token_tracker.record_usage(
                    provider=prov,
                    model=mod,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                    action=action_context[0],
                    latency_ms=lat_ms,
                    status=call_status,
                )

                raw_resp = getattr(client, "last_raw_response", "") or ""
                parsed_payload = None
                try:
                    if hasattr(result, "model_dump"):
                        parsed_payload = result.model_dump(mode="json")
                    elif isinstance(result, (dict, list)):
                        parsed_payload = result
                except Exception:
                    parsed_payload = None

                action_logger.record_finish(
                    call_id=call_id,
                    action_type=action_context[0],
                    provider=prov,
                    model=mod,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    raw_response=raw_resp,
                    parsed_json=parsed_payload,
                    latency_ms=lat_ms,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                    status=call_status,
                    metadata=action_context[1],
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
                    if not hasattr(self, "_snapshot_chain"):
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
                clear_model_cooldown(prov, mod, getattr(client, "api_key", None))
                return result
            except ProviderCoolingDownError as err:
                last_error = err
                attempt_errors.append(err)
                from backend.services.action_logger import action_logger
                action_logger.record_finish(
                    call_id=call_id,
                    action_type=action_context[0],
                    provider=prov,
                    model=mod,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    raw_response="",
                    parsed_json=None,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    status="cooling_down",
                    error=str(err),
                    metadata=action_context[1],
                )
                continue
            except Exception as err:
                last_error = err
                attempt_errors.append(err)
                from backend.services.action_logger import action_logger
                raw_resp = getattr(client, "last_raw_response", "") or ""
                action_logger.record_finish(
                    call_id=call_id,
                    action_type=action_context[0],
                    provider=prov,
                    model=mod,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    raw_response=raw_resp,
                    parsed_json=None,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    status="error",
                    error=f"{type(err).__name__}: {str(err)}",
                    metadata=action_context[1],
                )
                if _is_document_output_error(err):
                    document_rejected_models.add((prov, mod))
                record_model_failure(prov, mod, err, getattr(client, "api_key", None))
                attempt_history.append(f"{prov}:{mod} ({type(err).__name__}: {str(err)[:100]})")
                if not fallback_enabled:
                    logger.warning(
                        "Structured LLM generation failed on [%s / %s]: %s (Failover disabled).",
                        prov,
                        mod,
                        err,
                    )
                    cooling = None if prov.lower() in _LOCAL_PROVIDERS else _cooling_down_error(chain, failures=[err])
                    if cooling:
                        raise cooling from err
                    raise RuntimeError(
                        f"Primary LLM engine [{prov} / {mod}] failed: {err} (Failover disabled)"
                    ) from err
                logger.warning(
                    "Structured LLM generation failed on [%s / %s]: %s. Advancing to next fallback...",
                    prov,
                    mod,
                    err,
                )
                continue

        cooling = _cooling_down_error(chain, "Attempted: " + "; ".join(attempt_history) if attempt_history else "", attempt_errors)
        if cooling:
            raise cooling from last_error
        raise RuntimeError(
            f"All LLM models in fallback chain failed for schema '{response_model.__name__}'. "
            f"Attempted: {'; '.join(attempt_history)}. Last error: {last_error}"
        ) from last_error

    def get_last_usage(self) -> Optional[Any]:
        """Returns the token usage info for the most recent successful LLM call."""
        from backend.services.token_tracker import token_tracker
        return getattr(self._thread_state(), "last_usage", None) or token_tracker.get_last_usage()

    def set_action_context(self, action: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Sets action tag and metadata for usage and action logs."""
        self._thread_state().action = action
        self._thread_state().metadata = copy.deepcopy(metadata or {})



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






