"""
backend/services/ollama_service.py
Local Ollama service manager for detecting, launching, inspecting, loading,
and unloading local models into VRAM/RAM.
"""

import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

import httpx

from backend.config import settings


class OllamaService:
    """Manager for local Ollama daemon and model memory lifecycle."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = 10.0

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
            with httpx.Client(timeout=2.0) as client:
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

    def list_installed_models(self) -> List[Dict[str, Any]]:
        """Retrieves list of all locally installed models from GET /api/tags."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.base_url}/api/tags")
                res.raise_for_status()
                raw_models = res.json().get("models", [])
                formatted = []
                for m in raw_models:
                    size_bytes = m.get("size", 0)
                    size_gb = round(size_bytes / (1024**3), 2)
                    details = m.get("details", {})
                    formatted.append(
                        {
                            "name": m.get("name", "unknown"),
                            "model": m.get("model", m.get("name")),
                            "size_gb": size_gb,
                            "parameter_size": details.get("parameter_size", "N/A"),
                            "family": details.get("family", "N/A"),
                            "format": details.get("format", "gguf"),
                            "modified_at": m.get("modified_at", ""),
                            "digest": m.get("digest", "")[:12],
                        }
                    )
                return formatted
        except Exception as e:
            return []

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
                            "expires_at": m.get("expires_at", ""),
                        }
                    )
                return formatted
        except Exception as e:
            return []

    def load_model(self, model_name: str, keep_alive: str = "1h") -> Dict[str, Any]:
        """
        Pre-loads a model into memory (GPU VRAM or RAM) via POST /api/generate with keep_alive.
        """
        try:
            with httpx.Client(timeout=60.0) as client:
                res = client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": model_name, "keep_alive": keep_alive},
                )
                res.raise_for_status()
                return {
                    "success": True,
                    "model": model_name,
                    "keep_alive": keep_alive,
                    "message": f"Model '{model_name}' successfully loaded into memory (keep-alive: {keep_alive}).",
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
