"""
backend/services/ollama_service.py
Local Ollama service manager for detecting, launching, inspecting, loading,
and unloading local models into VRAM/RAM.
"""

import glob
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

import httpx
import psutil

from backend.config import settings


# Global in-memory caches to prevent blocking event loop on repetitive disk/subprocess calls
_HW_CACHE: Optional[Dict[str, Any]] = None
_HW_CACHE_TIME: float = 0.0

_INSTALLED_CACHE: Optional[List[Dict[str, Any]]] = None
_INSTALLED_CACHE_TIME: float = 0.0

_EXTERNAL_CACHE: Optional[List[Dict[str, Any]]] = None
_EXTERNAL_CACHE_TIME: float = 0.0


class OllamaService:
    """Manager for local Ollama daemon and model memory lifecycle."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = 3.0

    @staticmethod
    def get_ollama_binary() -> Optional[str]:
        """Locates the Ollama executable on the system."""
        # 1. PATH lookup
        path = shutil.which("ollama")
        if path:
            return path

        # 2. Windows LocalAppData check
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            candidate = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
            if os.path.exists(candidate):
                return candidate

        # 3. Userprofile check
        userprofile = os.environ.get("USERPROFILE", "")
        if userprofile:
            candidate = os.path.join(
                userprofile, "AppData", "Local", "Programs", "Ollama", "ollama.exe"
            )
            if os.path.exists(candidate):
                return candidate

        return None

    def is_installed(self) -> bool:
        """Returns True if the Ollama binary is found on disk."""
        return self.get_ollama_binary() is not None

    def get_status(self) -> Dict[str, Any]:
        """Checks if the local Ollama HTTP server is reachable and responsive."""
        binary = self.get_ollama_binary()
        installed = binary is not None

        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(f"{self.base_url}/api/version")
                if res.status_code == 200:
                    version = res.json().get("version", "unknown")
                    return {
                        "running": True,
                        "version": version,
                        "installed": installed,
                        "binary_path": binary,
                        "base_url": self.base_url,
                        "message": f"Ollama is running (v{version})",
                    }
        except Exception:
            pass

        return {
            "running": False,
            "version": None,
            "installed": installed,
            "binary_path": binary,
            "base_url": self.base_url,
            "message": "Ollama service is currently stopped or unreachable on port 11434.",
        }

    def start_service(self, max_wait_seconds: float = 8.0) -> Dict[str, Any]:
        """Spawns 'ollama serve' in background if not already running."""
        current_status = self.get_status()
        if current_status["running"]:
            return {
                "success": True,
                "message": "Ollama is already running.",
                "status": current_status,
            }

        binary = self.get_ollama_binary()
        if not binary:
            return {
                "success": False,
                "message": "Ollama executable not found. Please install Ollama from https://ollama.com",
                "status": current_status,
            }

        # Spawn background server process
        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            subprocess.Popen(
                [binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to spawn Ollama daemon: {e}",
                "status": self.get_status(),
            }

        # Wait for service to become responsive
        start_time = time.time()
        while time.time() - start_time < max_wait_seconds:
            time.sleep(0.5)
            status = self.get_status()
            if status["running"]:
                return {
                    "success": True,
                    "message": f"Ollama started successfully (v{status['version']})",
                    "status": status,
                }

        return {
            "success": False,
            "message": f"Ollama process started but did not respond within {max_wait_seconds}s.",
            "status": self.get_status(),
        }

    def get_hardware_profile(self, force: bool = False) -> Dict[str, Any]:
        """
        Inspects host machine RAM, available free memory, and GPU VRAM
        to compute hardware-specific recommendations for context window and local model execution.
        Cached for 300s to avoid repeated subprocess/smi stalls.
        """
        global _HW_CACHE, _HW_CACHE_TIME
        now = time.time()
        if not force and _HW_CACHE is not None and (now - _HW_CACHE_TIME < 300.0):
            profile = dict(_HW_CACHE)
            profile["current_settings"] = {
                "context_window": getattr(settings, "local_context_window", 4096),
                "rolling_context": getattr(settings, "local_rolling_context", True),
                "thinking_enabled": getattr(settings, "local_thinking_enabled", False),
            }
            return profile

        ram_total_gb = 8.0
        ram_avail_gb = 4.0
        try:
            mem = psutil.virtual_memory()
            ram_total_gb = round(mem.total / (1024**3), 1)
            ram_avail_gb = round(mem.available / (1024**3), 1)
        except Exception:
            pass

        gpus: List[Dict[str, Any]] = []
        try:
            smi = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                encoding="utf-8",
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            for line in smi.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpus.append({
                        "name": parts[0],
                        "vram_total_mb": int(parts[1]),
                        "vram_free_mb": int(parts[2]),
                        "vram_total_gb": round(int(parts[1]) / 1024.0, 1),
                    })
        except Exception:
            pass

        # Compute optimal recommendation
        max_vram_gb = max([g.get("vram_total_gb", 0) for g in gpus], default=0.0)

        if max_vram_gb >= 8.0:
            rec_context = 16384
            rec_reason = f"High VRAM detected ({max_vram_gb} GB). Full 16k context supported with high generation throughput."
            rec_options = [4096, 8192, 16384, 32768]
        elif max_vram_gb >= 4.0:
            rec_context = 4096
            rec_reason = f"Mid VRAM detected ({max_vram_gb} GB, e.g. GTX 1650/RTX 3050). 4096 tokens fits entirely in GPU VRAM for maximum speed without memory paging."
            rec_options = [2048, 4096, 8192]
        elif ram_total_gb >= 16.0:
            rec_context = 4096
            rec_reason = f"System RAM ({ram_total_gb} GB) allows 4096 tokens. Rolling context window prevents memory pressure."
            rec_options = [2048, 4096]
        else:
            rec_context = 2048
            rec_reason = f"Conservative memory budget ({ram_total_gb} GB RAM). 2048 tokens recommended for rapid inference."
            rec_options = [2048, 4096]

        result = {
            "ram_total_gb": ram_total_gb,
            "ram_avail_gb": ram_avail_gb,
            "gpus": gpus,
            "recommended_context_window": rec_context,
            "recommended_options": rec_options,
            "recommendation_reason": rec_reason,
            "current_settings": {
                "context_window": getattr(settings, "local_context_window", 4096),
                "rolling_context": getattr(settings, "local_rolling_context", True),
                "thinking_enabled": getattr(settings, "local_thinking_enabled", False),
            },
        }
        _HW_CACHE = result
        _HW_CACHE_TIME = now
        return result

    def scan_external_local_models(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        Scans LM Studio, Bionic, and common local GGUF directories
        to detect downloaded models that can be directly registered or loaded.
        Cached for 120s to eliminate disk crawl overhead on consecutive API calls.
        """
        global _EXTERNAL_CACHE, _EXTERNAL_CACHE_TIME
        now = time.time()
        if not force and _EXTERNAL_CACHE is not None and (now - _EXTERNAL_CACHE_TIME < 120.0):
            return _EXTERNAL_CACHE

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

        found_models: List[Dict[str, Any]] = []
        seen_paths = set()

        for directory in candidate_dirs:
            if not os.path.exists(directory):
                continue
            # Depth-limited walk (max 4 levels) to avoid runaway traversal
            base_sep_count = directory.rstrip(os.sep).count(os.sep)
            for root, dirs, files in os.walk(directory):
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

                        # Format a clean tag identifier
                        clean_tag = f.replace(".gguf", "").replace(".GGUF", "").lower()
                        if "minicpm5-2b" in clean_tag:
                            tag_id = "minicpm5:2b"
                        else:
                            tag_id = clean_tag.replace("_", "-")

                        found_models.append({
                            "source": "LM Studio / GGUF",
                            "file_name": f,
                            "tag": tag_id,
                            "full_path": full_path,
                            "size_gb": size_gb,
                        })

        _EXTERNAL_CACHE = found_models
        _EXTERNAL_CACHE_TIME = now
        return found_models

    def auto_import_gguf_to_ollama(self, gguf_path: str, model_tag: str) -> Dict[str, Any]:
        """
        Creates an Ollama model directly from a local .gguf file path using a Modelfile.
        """
        binary = self.get_ollama_binary()
        if not binary:
            return {"success": False, "message": "Ollama executable not found."}
        if not os.path.exists(gguf_path):
            return {"success": False, "message": f"File does not exist: {gguf_path}"}

        modelfile_content = f'''FROM "{gguf_path}"
TEMPLATE """{{{{ if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{ end }}}}{{{{ if .Prompt }}}}<|im_start|>user
{{{{ .Prompt }}}}<|im_end|>
{{{{ end }}}}<|im_start|>assistant
{{{{ .Response }}}}<|im_end|>"""
PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"
'''
        temp_dir = os.path.join(os.path.expanduser("~"), ".ollama_modelfiles")
        os.makedirs(temp_dir, exist_ok=True)
        modelfile_path = os.path.join(temp_dir, f"Modelfile.{model_tag.replace(':', '_')}")
        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(modelfile_content)

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
        try:
            res = subprocess.run(
                [binary, "create", model_tag, "-f", modelfile_path],
                capture_output=True,
                text=True,
                creationflags=creation_flags,
                timeout=45,
            )
            if res.returncode == 0:
                global _INSTALLED_CACHE
                _INSTALLED_CACHE = None
                return {
                    "success": True,
                    "model": model_tag,
                    "message": f"Successfully registered and imported '{model_tag}' into Ollama.",
                }
            return {
                "success": False,
                "model": model_tag,
                "message": f"Ollama create failed: {res.stderr or res.stdout}",
            }
        except Exception as e:
            return {"success": False, "model": model_tag, "message": str(e)}

    def list_installed_models(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieves list of all locally installed models from GET /api/tags,
        and auto-registers any external LM Studio / Bionic models found on disk.
        Cached for 45s to avoid blocking FastAPI request handling.
        """
        global _INSTALLED_CACHE, _INSTALLED_CACHE_TIME
        now = time.time()
        if not force and _INSTALLED_CACHE is not None and (now - _INSTALLED_CACHE_TIME < 45.0):
            return _INSTALLED_CACHE

        installed: List[Dict[str, Any]] = []
        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    raw_models = res.json().get("models", [])
                    for m in raw_models:
                        size_bytes = m.get("size", 0)
                        size_gb = round(size_bytes / (1024**3), 2)
                        details = m.get("details", {})
                        installed.append(
                            {
                                "name": m.get("name", "unknown"),
                                "model": m.get("model", m.get("name")),
                                "size_gb": size_gb,
                                "parameter_size": details.get("parameter_size", "N/A"),
                                "family": details.get("family", "N/A"),
                                "format": details.get("format", "gguf"),
                                "modified_at": m.get("modified_at", ""),
                                "digest": m.get("digest", "")[:12],
                                "source": "Ollama Library",
                            }
                        )
        except Exception:
            pass

        # Check if external LM Studio models are not yet in Ollama, and auto-import them
        existing_names = {m["name"] for m in installed}
        try:
            external_models = self.scan_external_local_models(force=force)
            for ext in external_models:
                tag = ext["tag"]
                if tag not in existing_names:
                    # Attempt quick auto-import if Ollama server is running
                    self.auto_import_gguf_to_ollama(ext["full_path"], tag)
                    installed.append({
                        "name": tag,
                        "model": tag,
                        "size_gb": ext["size_gb"],
                        "parameter_size": "2B-3B",
                        "family": "llama / minicpm",
                        "format": "gguf",
                        "modified_at": "",
                        "digest": "local-imported",
                        "source": "LM Studio / Bionic (Auto-Imported)",
                        "file_path": ext["full_path"],
                    })
                    existing_names.add(tag)
        except Exception:
            pass

        _INSTALLED_CACHE = installed
        _INSTALLED_CACHE_TIME = now
        return installed

    def list_running_models(self) -> List[Dict[str, Any]]:
        """Retrieves list of models currently loaded in RAM/VRAM from GET /api/ps."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.base_url}/api/ps")
                res.raise_for_status()
                raw_models = res.json().get("models", [])
                formatted = []
                for m in raw_models:
                    size_total = m.get("size", 0)
                    size_vram = m.get("size_vram", 0)
                    size_ram = max(0, size_total - size_vram)
                    formatted.append(
                        {
                            "name": m.get("name", "unknown"),
                            "model": m.get("model", m.get("name")),
                            "size_vram_mb": round(size_vram / (1024**2), 1),
                            "size_ram_mb": round(size_ram / (1024**2), 1),
                            "context_length": m.get("context_length", 4096),
                            "expires_at": m.get("expires_at", ""),
                        }
                    )
                return formatted
        except Exception:
            return []

    def load_model(self, model_name: str, keep_alive: str = "1h", num_ctx: Optional[int] = None) -> Dict[str, Any]:
        """
        Pre-loads a model into memory (GPU VRAM or RAM) via POST /api/generate with keep_alive
        and configured context window (num_ctx).
        """
        ctx = num_ctx or getattr(settings, "local_context_window", 4096)
        try:
            with httpx.Client(timeout=60.0) as client:
                payload = {
                    "model": model_name,
                    "keep_alive": keep_alive,
                    "options": {"num_ctx": ctx},
                }
                res = client.post(f"{self.base_url}/api/generate", json=payload)
                res.raise_for_status()
                return {
                    "success": True,
                    "model": model_name,
                    "keep_alive": keep_alive,
                    "context_window": ctx,
                    "message": f"Model '{model_name}' successfully loaded into memory (context: {ctx}, keep-alive: {keep_alive}).",
                }
        except Exception as e:
            return {
                "success": False,
                "model": model_name,
                "message": f"Failed to load model '{model_name}': {e}",
            }

    def unload_model(self, model_name: str) -> Dict[str, Any]:
        """
        Immediately evicts a model from GPU VRAM and system RAM via POST /api/generate with keep_alive=0.
        """
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": model_name, "keep_alive": 0},
                )
                res.raise_for_status()
                return {
                    "success": True,
                    "model": model_name,
                    "message": f"Model '{model_name}' successfully unloaded from memory.",
                }
        except Exception as e:
            return {
                "success": False,
                "model": model_name,
                "message": f"Failed to unload model '{model_name}': {e}",
            }

    def pull_model(self, model_name: str) -> Dict[str, Any]:
        """Pulls/downloads a model from Ollama registry."""
        try:
            with httpx.Client(timeout=300.0) as client:
                res = client.post(
                    f"{self.base_url}/api/pull",
                    json={"model": model_name, "stream": False},
                )
                res.raise_for_status()
                return {
                    "success": True,
                    "model": model_name,
                    "message": f"Model '{model_name}' pulled successfully.",
                }
        except Exception as e:
            return {
                "success": False,
                "model": model_name,
                "message": f"Failed to pull model '{model_name}': {e}",
            }
