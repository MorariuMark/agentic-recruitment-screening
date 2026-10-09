"""
backend/services/local_model_scanner.py
Comprehensive local AI model discovery and registration engine.
Automatically searches across:
1. Local Ollama daemon (port 11434 / tags / ps / manifests)
2. LM Studio live OpenAI server (port 1234 / v1 / models)
3. LM Studio model repositories on disk (~/.lmstudio/models, LocalAppData, D:/LM Studio, etc.)
4. Jan AI server (port 1337) and directory (~/.jan/models)
5. Hugging Face Hub cache (~/.cache/huggingface/hub)
6. Common local GGUF directories (~/models, C:/models, D:/models, workspace)

Automatically registers detected models into the platform's active catalog
and grants immediate execution access.
"""

import glob
import logging
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Set

import httpx

from backend.config import settings
from backend.services.ollama_service import OllamaService

logger = logging.getLogger("recruitment_screening.local_scanner")

_DISCOVERY_CACHE: Optional[Dict[str, Any]] = None
_DISCOVERY_CACHE_TIME: float = 0.0
_DISCOVERY_CACHE_TTL: float = 60.0  # Cache for 60 seconds unless forced


class LocalModelScanner:
    """Service for discovering and managing local LLM engines and model artifacts."""

    def __init__(self, ollama_service: Optional[OllamaService] = None) -> None:
        self.ollama_svc = ollama_service or OllamaService()

    @staticmethod
    def _clean_model_tag(raw_name: str) -> str:
        """Transforms complex filenames or paths into clean, friendly model identifiers."""
        base = os.path.basename(raw_name)
        # Strip known model extensions
        for ext in [".gguf", ".GGUF", ".bin", ".safetensors"]:
            if base.endswith(ext):
                base = base[: -len(ext)]
        # Normalize delimiters
        cleaned = re.sub(r"[_\s]+", "-", base).lower()
        cleaned = re.sub(r"-+", "-", cleaned).strip("-")
        return cleaned or "local-model"

    @staticmethod
    def _extract_quantization(file_name: str) -> str:
        """Extracts quantization level like Q4_K_M, Q5_K_S, Q8_0, etc."""
        m = re.search(r"(q\d+_[a-z0-9_]+|f16|f32|bf16)", file_name, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return "GGUF"

    def scan_ollama(self) -> Dict[str, Any]:
        """Probes the local Ollama daemon for installed and active in-memory models."""
        status = self.ollama_svc.get_status()
        installed_models: List[Dict[str, Any]] = []
        running_models: List[Dict[str, Any]] = []

        if status.get("running"):
            try:
                installed_raw = self.ollama_svc.list_installed_models(force=True)
                for item in installed_raw:
                    installed_models.append({
                        "id": item.get("name", "unknown"),
                        "name": item.get("name", "unknown").replace(":latest", ""),
                        "provider": "ollama",
                        "source": item.get("source", "Ollama Library"),
                        "size_gb": item.get("size_gb", 0.0),
                        "parameter_size": item.get("parameter_size", "N/A"),
                        "format": item.get("format", "gguf"),
                        "status": "ready",
                        "is_running": False,
                        "full_path": item.get("file_path"),
                        "can_activate": True,
                    })
            except Exception as e:
                logger.warning(f"Error listing Ollama installed models: {e}")

            try:
                running_raw = self.ollama_svc.list_running_models()
                running_names = {m.get("name") for m in running_raw}
                for item in running_raw:
                    running_models.append(item)
                # Mark installed models as running if loaded
                for m in installed_models:
                    if m["id"] in running_names:
                        m["status"] = "running_in_vram"
                        m["is_running"] = True
            except Exception as e:
                logger.warning(f"Error checking Ollama running models: {e}")

        # Also check local Ollama manifest directories on disk if daemon is stopped
        if not installed_models:
            user_dir = os.path.expanduser("~")
            manifest_candidates = [
                os.path.join(user_dir, ".ollama", "models", "manifests", "registry.ollama.ai", "library"),
                os.environ.get("OLLAMA_MODELS", ""),
            ]
            for m_dir in manifest_candidates:
                if m_dir and os.path.exists(m_dir):
                    try:
                        for model_folder in os.listdir(m_dir):
                            folder_path = os.path.join(m_dir, model_folder)
                            if os.path.isdir(folder_path):
                                for tag_file in os.listdir(folder_path):
                                    tag_id = f"{model_folder}:{tag_file}"
                                    installed_models.append({
                                        "id": tag_id,
                                        "name": model_folder,
                                        "provider": "ollama",
                                        "source": "Ollama Manifest (Disk)",
                                        "size_gb": 0.0,
                                        "parameter_size": "Local",
                                        "format": "ollama-blob",
                                        "status": "installed",
                                        "is_running": False,
                                        "can_activate": status.get("running", False),
                                    })
                    except Exception as e:
                        logger.debug(f"Manifest parse error: {e}")

        return {
            "status": status,
            "installed_count": len(installed_models),
            "installed_models": installed_models,
            "running_models": running_models,
        }

    def scan_lm_studio(self) -> Dict[str, Any]:
        """
        Probes LM Studio via both:
        1. Live OpenAI-compatible HTTP endpoint (http://localhost:1234/v1/models)
        2. Filesystem search across common LM Studio models storage locations.
        """
        server_running = False
        live_models: List[Dict[str, Any]] = []
        base_urls = [
            getattr(settings, "lmstudio_base_url", "http://localhost:1234/v1"),
            "http://127.0.0.1:1234/v1",
        ]
        active_url = base_urls[0]

        # 1. Probe live server endpoint
        for url in base_urls:
            endpoint = f"{url.rstrip('/')}/models"
            try:
                with httpx.Client(timeout=1.2) as client:
                    resp = client.get(endpoint)
                    if resp.status_code == 200:
                        server_running = True
                        active_url = url
                        data = resp.json().get("data", [])
                        for m in data:
                            m_id = m.get("id", "unknown")
                            live_models.append({
                                "id": m_id,
                                "name": m_id,
                                "provider": "lmstudio",
                                "source": "LM Studio (Live API)",
                                "size_gb": 0.0,
                                "format": "gguf",
                                "status": "running_in_vram",
                                "is_running": True,
                                "can_activate": True,
                                "endpoint": url,
                            })
                        break
            except Exception:
                pass

        # 2. Filesystem scan for LM Studio GGUF models
        disk_models: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()

        candidate_dirs = [
            os.path.expanduser("~/.lmstudio/models"),
            os.path.expanduser("~/.cache/lm-studio/models"),
            r"D:\LM Studio Bionic\Models",
            r"D:\LM Studio\models",
            r"C:\LM Studio\models",
        ]
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            candidate_dirs.append(os.path.join(local_app_data, "lm-studio", "models"))

        user_profile = os.environ.get("USERPROFILE", "")
        if user_profile:
            candidate_dirs.append(os.path.join(user_profile, ".cache", "lm-studio", "models"))
            candidate_dirs.append(os.path.join(user_profile, ".lmstudio", "models"))

        for c_dir in candidate_dirs:
            if not c_dir or not os.path.exists(c_dir):
                continue
            base_sep_count = c_dir.rstrip(os.sep).count(os.sep)
            for root, dirs, files in os.walk(c_dir):
                if root.count(os.sep) - base_sep_count > 4:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower().endswith(".gguf"):
                        full_path = os.path.join(root, f)
                        if full_path in seen_paths:
                            continue
                        seen_paths.add(full_path)
                        try:
                            size_bytes = os.path.getsize(full_path)
                            size_gb = round(size_bytes / (1024**3), 2)
                        except Exception:
                            size_gb = 0.0

                        tag = self._clean_model_tag(f)
                        quant = self._extract_quantization(f)
                        disk_models.append({
                            "id": tag,
                            "name": f"{tag} ({quant})",
                            "file_name": f,
                            "provider": "lmstudio",
                            "source": "LM Studio (Disk GGUF)",
                            "size_gb": size_gb,
                            "quantization": quant,
                            "format": "gguf",
                            "status": "ready",
                            "is_running": False,
                            "full_path": full_path,
                            "can_activate": server_running,
                        })

        return {
            "server_running": server_running,
            "base_url": active_url,
            "live_models": live_models,
            "disk_models": disk_models,
            "total_count": len(live_models) + len(disk_models),
        }

    def scan_jan_and_local_servers(self) -> Dict[str, Any]:
        """Probes other local LLM engines: Jan AI (port 1337), LocalAI (port 8080), TextGen WebUI (port 5000)."""
        detected: List[Dict[str, Any]] = []

        servers = [
            ("jan", "http://localhost:1337/v1", "Jan AI Local Server"),
            ("localai", "http://localhost:8080/v1", "LocalAI / llama.cpp Server"),
            ("textgen", "http://localhost:5000/v1", "Text Generation WebUI"),
        ]

        for s_id, base_url, display in servers:
            try:
                with httpx.Client(timeout=0.8) as client:
                    resp = client.get(f"{base_url}/models")
                    if resp.status_code == 200:
                        models = resp.json().get("data", [])
                        for m in models:
                            m_id = m.get("id", "local-model")
                            detected.append({
                                "id": f"{s_id}:{m_id}",
                                "name": m_id,
                                "provider": "lmstudio",  # Compatible with OpenAI client
                                "source": display,
                                "size_gb": 0.0,
                                "format": "server",
                                "status": "running_in_vram",
                                "is_running": True,
                                "can_activate": True,
                                "endpoint": base_url,
                            })
            except Exception:
                pass

        # Scan Jan disk folder
        jan_dir = os.path.expanduser("~/.jan/models")
        if os.path.exists(jan_dir):
            try:
                for root, dirs, files in os.walk(jan_dir):
                    for f in files:
                        if f.lower().endswith(".gguf"):
                            full_path = os.path.join(root, f)
                            size_gb = round(os.path.getsize(full_path) / (1024**3), 2)
                            tag = self._clean_model_tag(f)
                            detected.append({
                                "id": f"jan-{tag}",
                                "name": f"{tag} (Jan)",
                                "file_name": f,
                                "provider": "lmstudio",
                                "source": "Jan AI (Disk GGUF)",
                                "size_gb": size_gb,
                                "format": "gguf",
                                "status": "ready",
                                "is_running": False,
                                "full_path": full_path,
                                "can_activate": False,
                            })
            except Exception:
                pass

        return {"detected_servers": detected}

    def scan_common_directories(self) -> List[Dict[str, Any]]:
        """Scans HuggingFace cache and standard local models directories for GGUF artifacts."""
        user_dir = os.path.expanduser("~")
        candidate_dirs = [
            os.path.join(user_dir, ".cache", "huggingface", "hub"),
            os.path.join(user_dir, "models"),
            os.path.join(user_dir, ".models"),
            r"D:\models",
            r"C:\models",
            os.path.join(os.getcwd(), "models"),
            os.path.join(os.getcwd(), "data", "models"),
        ]

        found_models: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()

        for c_dir in candidate_dirs:
            if not os.path.exists(c_dir):
                continue
            base_sep_count = c_dir.rstrip(os.sep).count(os.sep)
            for root, dirs, files in os.walk(c_dir):
                if root.count(os.sep) - base_sep_count > 4:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower().endswith(".gguf"):
                        full_path = os.path.join(root, f)
                        if full_path in seen_paths:
                            continue
                        seen_paths.add(full_path)
                        try:
                            size_bytes = os.path.getsize(full_path)
                            size_gb = round(size_bytes / (1024**3), 2)
                        except Exception:
                            size_gb = 0.0

                        source_name = "HuggingFace Cache" if "huggingface" in root.lower() else "Local Disk"
                        tag = self._clean_model_tag(f)
                        quant = self._extract_quantization(f)
                        found_models.append({
                            "id": tag,
                            "name": f"{tag} ({quant})",
                            "file_name": f,
                            "provider": "ollama",  # Default target for disk GGUFs
                            "source": source_name,
                            "size_gb": size_gb,
                            "quantization": quant,
                            "format": "gguf",
                            "status": "ready",
                            "is_running": False,
                            "full_path": full_path,
                            "can_activate": False,
                        })

        return found_models

    def scan_all(self, force: bool = False, auto_import_to_ollama: bool = False) -> Dict[str, Any]:
        """
        Executes a complete scan across Ollama, LM Studio, other local engines, and common disk paths.
        Updates CATALOG_PROVIDERS automatically with active model choices.
        Cached for 60s to prevent stalling.
        """
        global _DISCOVERY_CACHE, _DISCOVERY_CACHE_TIME
        now = time.time()
        if not force and _DISCOVERY_CACHE is not None and (now - _DISCOVERY_CACHE_TIME < _DISCOVERY_CACHE_TTL):
            return _DISCOVERY_CACHE

        ollama_res = self.scan_ollama()
        lm_res = self.scan_lm_studio()
        other_servers_res = self.scan_jan_and_local_servers()
        common_dirs_res = self.scan_common_directories()

        all_models: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        # 1. Add Ollama models
        for m in ollama_res.get("installed_models", []):
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                all_models.append(m)

        # 2. Add LM Studio live models
        for m in lm_res.get("live_models", []):
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                all_models.append(m)

        # 3. Add other local servers
        for m in other_servers_res.get("detected_servers", []):
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                all_models.append(m)

        # 4. Add LM Studio disk GGUF models
        for m in lm_res.get("disk_models", []):
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                all_models.append(m)

        # 5. Add common directories GGUF models
        for m in common_dirs_res:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                all_models.append(m)

        # Auto-import disk GGUF models into Ollama if requested and Ollama is running
        imported_count = 0
        if auto_import_to_ollama and ollama_res.get("status", {}).get("running"):
            existing_ollama_names = {m["id"] for m in ollama_res.get("installed_models", [])}
            for m in all_models:
                path = m.get("full_path")
                tag = m.get("id")
                if path and tag and tag not in existing_ollama_names and m.get("format") == "gguf":
                    try:
                        import_res = self.ollama_svc.auto_import_gguf_to_ollama(path, tag)
                        if import_res.get("success"):
                            imported_count += 1
                            m["provider"] = "ollama"
                            m["can_activate"] = True
                            m["status"] = "ready"
                    except Exception as e:
                        logger.debug(f"Auto-import error for {tag}: {e}")

        # Update the live catalog with discovered models
        self._update_catalog_with_discovered_models(all_models, lm_res.get("server_running", False))

        result = {
            "success": True,
            "scanned_at": now,
            "total_found": len(all_models),
            "imported_count": imported_count,
            "providers_detected": {
                "ollama": {
                    "running": ollama_res.get("status", {}).get("running", False),
                    "version": ollama_res.get("status", {}).get("version"),
                    "models_count": len(ollama_res.get("installed_models", [])),
                    "models": ollama_res.get("installed_models", []),
                },
                "lmstudio": {
                    "running": lm_res.get("server_running", False),
                    "base_url": lm_res.get("base_url"),
                    "live_models_count": len(lm_res.get("live_models", [])),
                    "disk_models_count": len(lm_res.get("disk_models", [])),
                    "models": lm_res.get("live_models", []) + lm_res.get("disk_models", []),
                },
                "other_local_servers": {
                    "count": len(other_servers_res.get("detected_servers", [])),
                    "models": other_servers_res.get("detected_servers", []),
                },
                "filesystem_gguf": {
                    "count": len(common_dirs_res),
                    "models": common_dirs_res,
                },
            },
            "all_models": all_models,
            "catalog_updated": True,
            "message": f"Discovered {len(all_models)} local model(s) across Ollama, LM Studio, and filesystem.",
        }

        _DISCOVERY_CACHE = result
        _DISCOVERY_CACHE_TIME = now
        return result

    def _update_catalog_with_discovered_models(
        self, all_models: List[Dict[str, Any]], lmstudio_running: bool
    ) -> None:
        """Injects discovered models into CATALOG_PROVIDERS so they appear in selectors."""
        from backend.schemas.models_catalog import CATALOG_PROVIDERS, ModelInfo, ProviderInfo

        ctx_display = f"{getattr(settings, 'local_context_window', 4096) // 1024}k"

        # 1. Update Ollama Provider Models
        ollama_models: List[ModelInfo] = []
        for m in all_models:
            if m.get("provider") == "ollama" or "ollama" in m.get("source", "").lower():
                clean_name = m["name"].replace(":latest", "")
                src_badge = f" [{m['source']}]" if "Disk" in m["source"] or "Auto" in m["source"] else ""
                ollama_models.append(
                    ModelInfo(
                        id=m["id"],
                        name=f"{clean_name}{src_badge}",
                        provider="ollama",
                        free=True,
                        rate_limits="Unlimited (Local GPU/CPU)",
                        context_window=f"{ctx_display} (Local Config)",
                        category=f"Local {m.get('parameter_size', 'Model')}",
                        compatibility="Native Ollama JSON Mode",
                        description=f"{m['source']} ({m.get('size_gb', 0)} GB). 100% private offline inference.",
                    )
                )

        if ollama_models and "ollama" in CATALOG_PROVIDERS:
            CATALOG_PROVIDERS["ollama"].models = ollama_models

        # 2. Register or Update LM Studio Provider Models
        lm_models: List[ModelInfo] = []
        for m in all_models:
            if m.get("provider") == "lmstudio" or "lm studio" in m.get("source", "").lower():
                lm_models.append(
                    ModelInfo(
                        id=m["id"],
                        name=f"{m['name']} [{m['source']}]",
                        provider="lmstudio",
                        free=True,
                        rate_limits="Unlimited (Local Server)",
                        context_window="32k-128k (LM Studio)",
                        category="Local LM Studio",
                        compatibility="OpenAI JSON Object Mode",
                        description=f"LM Studio local engine ({m.get('size_gb', 0)} GB). Zero latency, local privacy.",
                    )
                )

        if "lmstudio" not in CATALOG_PROVIDERS:
            CATALOG_PROVIDERS["lmstudio"] = ProviderInfo(
                id="lmstudio",
                name="LM Studio (Local Server)",
                icon="💻",
                description="Local OpenAI-compatible inference server running on your machine via LM Studio.",
                api_key_url="https://lmstudio.ai/",
                default_model=lm_models[0].id if lm_models else "default",
                default_base_url=getattr(settings, "lmstudio_base_url", "http://localhost:1234/v1"),
                env_key_var="LMSTUDIO_BASE_URL",
                models=lm_models,
            )
        else:
            if lm_models:
                CATALOG_PROVIDERS["lmstudio"].models = lm_models
                if not CATALOG_PROVIDERS["lmstudio"].default_model or CATALOG_PROVIDERS["lmstudio"].default_model == "default":
                    CATALOG_PROVIDERS["lmstudio"].default_model = lm_models[0].id


_scanner_instance: Optional[LocalModelScanner] = None


def get_local_model_scanner() -> LocalModelScanner:
    """Returns singleton instance of the LocalModelScanner."""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = LocalModelScanner()
    return _scanner_instance
