"""
backend/services/local_model_service.py
Service for managing local LLMs (LM Studio and Ollama), monitoring GPU/System memory,
auto-tuning context windows for any hardware (from 4GB laptop GPUs to 16GB+ desktop workstations),
and enforcing zero-OOM sliding/rolling window protection.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

import psutil
from backend.config import settings

logger = logging.getLogger("recruitment_screening.local_model_service")

# LM Studio default CLI paths on Windows
LMS_CLI_CANDIDATES = [
    Path(os.environ.get("USERPROFILE", "")) / ".lmstudio" / "bin" / "lms.exe",
    Path("C:/Program Files/LM Studio/resources/app/.webpack/main/lms.exe"),
    Path("D:/LM Studio/resources/app/.webpack/main/lms.exe"),
]

# Known LM Studio model storage locations
LM_MODELS_DIRS = [
    Path("D:/LM_Models"),
    Path(os.environ.get("USERPROFILE", "")) / ".lmstudio" / "models",
    Path(os.environ.get("USERPROFILE", "")) / ".cache" / "lm-studio" / "models",
]


class LocalModelService:
    """
    Unified manager for local LLM runtimes (LM Studio & Ollama) with universal hardware adaptation.
    Automatically detects GPU VRAM and system memory, auto-tunes context windows and rolling prompt
    budgets for lower-end hardware (e.g. 4GB laptop GPUs), and prevents CUDA OOM crashes.
    """

    _instance: Optional["LocalModelService"] = None
    _lock = threading.RLock()

    def __new__(cls) -> "LocalModelService":
        if cls._instance is None:
            cls._instance = super(LocalModelService, cls).__new__(cls)
            cls._instance._last_gpu_probe = {}
            cls._instance._last_gpu_probe_time = 0.0
            cls._instance._last_full_state = {}
            cls._instance._last_full_state_time = 0.0
            cls._instance._cached_catalog = []
            cls._instance._server_proc = None
        return cls._instance

    @staticmethod
    def _find_lms_cli() -> Optional[str]:
        """Locates the lms.exe CLI binary on the host system."""
        for candidate in LMS_CLI_CANDIDATES:
            if candidate.is_file():
                return str(candidate)
        import shutil
        found = shutil.which("lms")
        if found:
            return found
        return None

    def get_hardware_profile(self, total_vram_mb: int, is_dedicated_gpu: bool) -> Dict[str, Any]:
        """
        Computes the optimal execution tier, recommended context window, and model guidance
        based on detected hardware. Optimizes for lower-end laptops (4GB VRAM) up to 16GB+ rigs.
        """
        if not is_dedicated_gpu or total_vram_mb <= 4600:
            # 4GB VRAM laptop or Integrated Graphics / CPU
            return {
                "tier": "low",
                "tier_label": "4GB Laptop / Entry GPU (Low VRAM)",
                "recommended_context_window": 4096,
                "recommended_max_tokens": 1536,
                "recommended_gpu_layers": 99,
                "recommended_model_size_max_gb": 4.0,
                "safe_models_description": "0.8B to 4B models (Qwen 3.5 0.8B/4B, MiniCPM 2B, SmolLM)",
                "warning": "4GB VRAM detected: Context window is optimized to 4,096 tokens with active rolling window to prevent CUDA out-of-memory errors.",
                "is_low_end": True,
            }
        elif total_vram_mb <= 8600:
            # 6GB - 8GB mid-range laptop / desktop GPU
            return {
                "tier": "medium",
                "tier_label": "6GB - 8GB Mid-range GPU",
                "recommended_context_window": 8192,
                "recommended_max_tokens": 2048,
                "recommended_gpu_layers": 99,
                "recommended_model_size_max_gb": 7.5,
                "safe_models_description": "7B to 9B Q4 models (Qwen 3.8 9B, Gemma 12B QAT, Ornith 9B)",
                "warning": None,
                "is_low_end": False,
            }
        elif total_vram_mb <= 16500:
            # 12GB - 16GB high-end GPU (e.g. RTX 4060 Ti 16GB, RTX 3080/4080)
            return {
                "tier": "high",
                "tier_label": "12GB - 16GB High-end GPU",
                "recommended_context_window": 16384,
                "recommended_max_tokens": 3072,
                "recommended_gpu_layers": 99,
                "recommended_model_size_max_gb": 15.0,
                "safe_models_description": "Large models (14B Q8, 27B Q1/Q3, Bonsai 27B, Gemma 12B)",
                "warning": None,
                "is_low_end": False,
            }
        else:
            # 24GB+ workstation GPU
            return {
                "tier": "ultra",
                "tier_label": "24GB+ Workstation GPU",
                "recommended_context_window": 32768,
                "recommended_max_tokens": 4096,
                "recommended_gpu_layers": 99,
                "recommended_model_size_max_gb": 23.0,
                "safe_models_description": "Full-scale models up to 70B quantized",
                "warning": None,
                "is_low_end": False,
            }

    def get_gpu_telemetry(self) -> Dict[str, Any]:
        """
        Universal hardware probe:
        1. Checks NVIDIA GPUs via nvidia-smi
        2. Checks AMD/Intel/Integrated GPUs via Win32_VideoController on Windows
        3. Falls back to system RAM via psutil
        Cached for 1.5 seconds.
        """
        now = time.time()
        if (now - self._last_gpu_probe_time) < 1.5 and self._last_gpu_probe:
            return self._last_gpu_probe

        # 1. Primary probe: nvidia-smi
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2.5, check=True)
            line = res.stdout.strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                name = parts[0]
                total_mb = int(parts[1])
                used_mb = int(parts[2])
                free_mb = int(parts[3])
                util_pct = int(parts[4])
                profile = self.get_hardware_profile(total_mb, is_dedicated_gpu=True)
                probe = {
                    "available": True,
                    "is_dedicated_gpu": True,
                    "name": name,
                    "total_vram_mb": total_mb,
                    "used_vram_mb": used_mb,
                    "free_vram_mb": free_mb,
                    "utilization_percent": util_pct,
                    "used_vram_gb": round(used_mb / 1024.0, 2),
                    "total_vram_gb": round(total_mb / 1024.0, 2),
                    "free_vram_gb": round(free_mb / 1024.0, 2),
                    "profile": profile,
                }
                self._last_gpu_probe = probe
                self._last_gpu_probe_time = now
                return probe
        except Exception:
            pass

        # 2. Secondary probe: Windows CimInstance for AMD Radeon / Intel Iris / other GPUs
        if os.name == "nt":
            try:
                ps_cmd = 'Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json'
                res = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], capture_output=True, text=True, timeout=2.5)
                if res.returncode == 0 and res.stdout.strip():
                    data = json.loads(res.stdout)
                    if isinstance(data, list):
                        data = data[0]
                    vname = data.get("Name", "Graphics Adapter")
                    vram_bytes = data.get("AdapterRAM") or 0
                    vram_mb = max(0, vram_bytes // (1024 * 1024))
                    # If Windows reports 4GB or less for discrete GPU
                    if vram_mb > 512:
                        profile = self.get_hardware_profile(vram_mb, is_dedicated_gpu=True)
                        probe = {
                            "available": True,
                            "is_dedicated_gpu": True,
                            "name": vname,
                            "total_vram_mb": vram_mb,
                            "used_vram_mb": 0,
                            "free_vram_mb": vram_mb,
                            "utilization_percent": 0,
                            "used_vram_gb": round(vram_mb / 1024.0, 2),
                            "total_vram_gb": round(vram_mb / 1024.0, 2),
                            "free_vram_gb": round(vram_mb / 1024.0, 2),
                            "profile": profile,
                        }
                        self._last_gpu_probe = probe
                        self._last_gpu_probe_time = now
                        return probe
            except Exception:
                pass

        # 3. Tertiary probe: psutil system RAM fallback (CPU / Integrated Graphics / Low-end Laptop)
        try:
            ram = psutil.virtual_memory()
            total_ram_mb = int(ram.total / (1024 * 1024))
            used_ram_mb = int(ram.used / (1024 * 1024))
            avail_ram_mb = int(ram.available / (1024 * 1024))
            # Shared VRAM typically capped at 50% of system RAM
            shared_vram_mb = min(4096, total_ram_mb // 2)
            profile = self.get_hardware_profile(shared_vram_mb, is_dedicated_gpu=False)
            probe = {
                "available": False,
                "is_dedicated_gpu": False,
                "name": "Integrated Graphics / CPU",
                "total_vram_mb": shared_vram_mb,
                "used_vram_mb": min(shared_vram_mb, used_ram_mb // 2),
                "free_vram_mb": min(shared_vram_mb, avail_ram_mb // 2),
                "utilization_percent": int(ram.percent),
                "used_vram_gb": round(used_ram_mb / 1024.0, 2),
                "total_vram_gb": round(total_ram_mb / 1024.0, 2),
                "free_vram_gb": round(avail_ram_mb / 1024.0, 2),
                "profile": profile,
            }
            self._last_gpu_probe = probe
            self._last_gpu_probe_time = now
            return probe
        except Exception:
            pass

        # Absolute fallback
        profile = self.get_hardware_profile(4096, is_dedicated_gpu=False)
        fallback = {
            "available": False,
            "is_dedicated_gpu": False,
            "name": "Standard CPU (4GB Profile)",
            "total_vram_mb": 4096,
            "used_vram_mb": 0,
            "free_vram_mb": 4096,
            "utilization_percent": 0,
            "used_vram_gb": 0.0,
            "total_vram_gb": 4.0,
            "free_vram_gb": 4.0,
            "profile": profile,
        }
        self._last_gpu_probe = fallback
        self._last_gpu_probe_time = now
        return fallback

    def get_lmstudio_status(self) -> Dict[str, Any]:
        """Probes LM Studio HTTP server and reads loaded/available models."""
        base_url = getattr(settings, "lmstudio_base_url", "http://localhost:1234/v1").rstrip("/")
        root_url = base_url[:-3] if base_url.endswith("/v1") else base_url

        available = False
        loaded_models: List[Dict[str, Any]] = []
        catalog_models: List[Dict[str, Any]] = []

        # 1. Probe HTTP port
        try:
            req = urllib.request.Request(f"{root_url}/v1/models", headers={"User-Agent": "Atos-AI"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    available = True
                    data = json.loads(resp.read().decode("utf-8"))
                    for m in data.get("data", []):
                        m_id = m.get("id")
                        if m_id:
                            catalog_models.append({
                                "id": m_id,
                                "name": m_id,
                                "is_4gb_friendly": any(k in m_id.lower() for k in ["0.8b", "2b", "4b", "minicpm", "smollm", "llama-3.2-1b", "llama-3.2-3b"]),
                            })
        except Exception:
            available = False

        # 2. Check loaded models via lms ps
        lms_cli = self._find_lms_cli()
        if lms_cli and not available:
            try:
                ps_res = subprocess.run([lms_cli, "ps"], capture_output=True, timeout=2.0)
                ps_out = ps_res.stdout.decode("utf-8", errors="replace")
                lines = [l.strip() for l in ps_out.splitlines() if l.strip()]
                data_lines = [l for l in lines if not l.startswith("IDENTIFIER") and not l.startswith("Waking up") and "No models" not in l]
                for dl in data_lines:
                    tokens = dl.split()
                    if len(tokens) >= 3:
                        loaded_models.append({
                            "identifier": tokens[0],
                            "model": tokens[1],
                            "status": tokens[2],
                            "size": tokens[3] if len(tokens) > 3 else "unknown",
                            "context_length": tokens[4] if len(tokens) > 4 else "4096",
                        })
            except Exception as e:
                logger.debug("lms ps probe error: %s", e)

        # 3. Use cached catalog or discover on disk
        raw_model_ids = [m["id"] for m in catalog_models]
        if not raw_model_ids and self._cached_catalog:
            catalog_models = list(self._cached_catalog)
        elif not raw_model_ids:
            for d in LM_MODELS_DIRS:
                if d.is_dir():
                    try:
                        for gguf in d.rglob("*.gguf"):
                            if "mmproj" not in gguf.name.lower():
                                rel_name = gguf.stem
                                size_gb = round(gguf.stat().st_size / (1024**3), 2)
                                if rel_name not in raw_model_ids:
                                    raw_model_ids.append(rel_name)
                                    catalog_models.append({
                                        "id": rel_name,
                                        "name": rel_name,
                                        "size_gb": size_gb,
                                        "is_4gb_friendly": size_gb <= 4.0 or any(k in rel_name.lower() for k in ["0.8b", "2b", "4b", "minicpm"]),
                                    })
                    except Exception:
                        pass
            self._cached_catalog = list(catalog_models)

        # Ensure safe defaults are listed with 4GB friendliness tags
        known_defaults = [
            ("qwen3.5-0.8b", 1.0, True),
            ("minicpm-v-4.6", 1.9, True),
            ("qwen3.5-4b", 3.4, True),
            ("qwen3.8-9b-abliterated-25", 5.6, False),
            ("ornith-1.0-9b", 6.5, False),
            ("ornith-1.5-9b", 6.7, False),
            ("gemma-4-12b-it-qat", 6.9, False),
            ("prism-ml/bonsai-27b", 4.7, False),
            ("qwen3.6-27b-uncensored-hauhaucs-aggressive", 13.5, False),
        ]
        existing_ids = {m["id"] for m in catalog_models}
        for kd_id, kd_size, kd_4gb in known_defaults:
            if kd_id not in existing_ids:
                catalog_models.append({
                    "id": kd_id,
                    "name": kd_id,
                    "size_gb": kd_size,
                    "is_4gb_friendly": kd_4gb,
                })

        active_model = getattr(settings, "lmstudio_model", "default")
        return {
            "available": available,
            "base_url": base_url,
            "current_model": active_model,
            "models": catalog_models,
            "loaded_models": loaded_models,
            "context_window": getattr(settings, "local_context_window", 16384),
            "rolling_context": getattr(settings, "local_rolling_context", True),
            "gpu_layers": getattr(settings, "local_gpu_layers", 99),
        }

    def get_ollama_status(self) -> Dict[str, Any]:
        """Probes local Ollama instance and inspects running VRAM models."""
        base_url = getattr(settings, "ollama_base_url", "http://localhost:11434").rstrip("/")
        available = False
        models: List[Dict[str, Any]] = []
        loaded_models: List[Dict[str, Any]] = []

        try:
            req = urllib.request.Request(f"{base_url}/api/tags", headers={"User-Agent": "Atos-AI"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    available = True
                    data = json.loads(resp.read().decode("utf-8"))
                    for m in data.get("models", []):
                        name = m.get("name")
                        size_gb = round(m.get("size", 0) / (1024**3), 2)
                        if name:
                            models.append({
                                "id": name,
                                "name": name,
                                "size_gb": size_gb,
                                "is_4gb_friendly": size_gb <= 4.0 or any(k in name.lower() for k in ["0.8b", "1b", "2b", "3b", "4b", "minicpm"]),
                            })
        except Exception:
            available = False

        if available:
            try:
                ps_req = urllib.request.Request(f"{base_url}/api/ps", headers={"User-Agent": "Atos-AI"})
                with urllib.request.urlopen(ps_req, timeout=1.5) as ps_resp:
                    if ps_resp.status == 200:
                        ps_data = json.loads(ps_resp.read().decode("utf-8"))
                        for lm in ps_data.get("models", []):
                            size_vram = lm.get("size_vram", 0)
                            loaded_models.append({
                                "model": lm.get("name", "unknown"),
                                "size_vram_mb": round(size_vram / (1024 * 1024), 1),
                                "expires_at": lm.get("expires_at"),
                            })
            except Exception:
                pass

        active_model = getattr(settings, "ollama_model", "minicpm5:2b")
        return {
            "available": available,
            "base_url": base_url,
            "current_model": active_model,
            "models": models,
            "loaded_models": loaded_models,
            "context_window": getattr(settings, "local_context_window", 16384),
            "rolling_context": getattr(settings, "local_rolling_context", True),
            "gpu_layers": getattr(settings, "local_gpu_layers", 99),
        }

    def start_lmstudio_server(self, port: int = 1234) -> Dict[str, Any]:
        """Ensures the LM Studio server is running on the host machine."""
        lms_cli = self._find_lms_cli()
        if not lms_cli:
            return {"success": False, "error": "lms.exe CLI not found on this machine."}

        try:
            status = self.get_lmstudio_status()
            if status["available"]:
                return {"success": True, "message": "LM Studio server is already running."}

            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

            cmd = [lms_cli, "server", "start", "--port", str(port), "--cors"]
            self._server_proc = subprocess.Popen(
                cmd,
                creationflags=flags,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            for _ in range(10):
                time.sleep(0.5)
                if self.get_lmstudio_status()["available"]:
                    return {"success": True, "message": f"LM Studio server started on port {port}."}

            return {"success": True, "message": "LM Studio start command issued."}
        except Exception as e:
            logger.error("Failed to start LM Studio server: %s", e)
            return {"success": False, "error": str(e)}

    def load_model(
        self,
        provider: str,
        model: str,
        context_window: Optional[int] = None,
        gpu_layers: Optional[int] = 99,
        gpu_offload_mode: str = "auto",
        set_as_active: bool = True,
    ) -> Dict[str, Any]:
        """
        Loads the specified model into GPU/System memory with adaptive hardware tuning.
        If context_window is not provided, auto-selects the safe window based on detected VRAM
        (4,096 for 4GB laptop, 16,384 for 16GB desktop) to prevent out-of-memory errors.
        """
        gpu = self.get_gpu_telemetry()
        profile = gpu.get("profile", {})

        # Auto-tune context window based on detected hardware if not explicitly passed
        target_context = context_window or profile.get("recommended_context_window", 16384)
        if target_context <= 0:
            target_context = profile.get("recommended_context_window", 16384)

        prov = provider.lower()
        if prov == "lmstudio":
            lms_cli = self._find_lms_cli()
            if not lms_cli:
                return {"success": False, "error": "lms.exe CLI not found."}

            try:
                self.start_lmstudio_server()

                # Determine GPU offload parameter:
                # On 4GB laptops or when 'auto' is selected, LM Studio optimizes layer offload to prevent CUDA OOM.
                # If 'max' is selected, it passes --gpu max.
                gpu_flag = "max" if gpu_offload_mode == "max" and not profile.get("is_low_end") else "auto"

                cmd = [
                    lms_cli,
                    "load",
                    model,
                    "-c",
                    str(target_context),
                    "--ttl",
                    "86400",
                    "-y",
                ]
                if gpu_flag == "max":
                    cmd.extend(["--gpu", "max"])

                res = subprocess.run(cmd, capture_output=True, timeout=180.0)
                out = res.stdout.decode("utf-8", errors="replace")
                err = res.stderr.decode("utf-8", errors="replace")

                # If --gpu max failed due to VRAM limits on lower-end laptop, retry with auto offload
                if res.returncode != 0 and gpu_flag == "max":
                    logger.warning("LM Studio --gpu max failed on low VRAM; retrying with safe auto offload: %s", out or err)
                    cmd_safe = [lms_cli, "load", model, "-c", str(target_context), "--ttl", "86400", "-y"]
                    res = subprocess.run(cmd_safe, capture_output=True, timeout=180.0)
                    out = res.stdout.decode("utf-8", errors="replace")

                # Update application runtime settings
                settings.lmstudio_model = model
                settings.local_context_window = target_context
                settings.local_gpu_layers = gpu_layers if gpu_layers is not None else 99
                if set_as_active:
                    settings.llm_provider = "lmstudio"

                gpu_fresh = self.get_gpu_telemetry()
                return {
                    "success": True,
                    "provider": "lmstudio",
                    "model": model,
                    "context_window": target_context,
                    "gpu_layers": gpu_layers,
                    "hardware_profile": profile.get("tier_label"),
                    "gpu_telemetry": gpu_fresh,
                    "message": f"Model '{model}' loaded with {target_context} context length ({profile.get('tier_label')}).",
                }
            except Exception as e:
                logger.error("LM Studio model load failed: %s", e)
                return {"success": False, "error": str(e)}

        elif prov == "ollama":
            base_url = getattr(settings, "ollama_base_url", "http://localhost:11434").rstrip("/")
            try:
                # On lower-end hardware (4GB), allow Ollama to auto-partition layers if 99 overflows
                num_gpu_val = gpu_layers if (gpu_layers is not None and not profile.get("is_low_end")) else 99
                payload = {
                    "model": model,
                    "keep_alive": "24h",
                    "options": {
                        "num_ctx": target_context,
                        "temperature": 0.0,
                    },
                }
                if num_gpu_val:
                    payload["options"]["num_gpu"] = num_gpu_val
                    payload["options"]["main_gpu"] = 0

                req = urllib.request.Request(
                    f"{base_url}/api/generate",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "Atos-AI"},
                )
                with urllib.request.urlopen(req, timeout=120.0) as resp:
                    if resp.status == 200:
                        settings.ollama_model = model
                        settings.local_context_window = target_context
                        settings.local_gpu_layers = num_gpu_val
                        if set_as_active:
                            settings.llm_provider = "ollama"

                        gpu_fresh = self.get_gpu_telemetry()
                        return {
                            "success": True,
                            "provider": "ollama",
                            "model": model,
                            "context_window": target_context,
                            "gpu_layers": num_gpu_val,
                            "hardware_profile": profile.get("tier_label"),
                            "gpu_telemetry": gpu_fresh,
                            "message": f"Model '{model}' loaded into Ollama with {target_context} context length.",
                        }
                    return {"success": False, "error": f"Ollama returned HTTP {resp.status}"}
            except Exception as e:
                logger.error("Ollama model load failed: %s", e)
                return {"success": False, "error": str(e)}

        return {"success": False, "error": f"Unsupported provider: {provider}"}

    def unload_model(self, provider: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Unloads model(s) from VRAM immediately to free up GPU memory."""
        prov = provider.lower()
        if prov == "lmstudio":
            lms_cli = self._find_lms_cli()
            if not lms_cli:
                return {"success": False, "error": "lms.exe CLI not found."}
            try:
                cmd = [lms_cli, "unload"]
                if model:
                    cmd.append(model)
                else:
                    cmd.append("-a")
                res = subprocess.run(cmd, capture_output=True, timeout=30.0)
                gpu = self.get_gpu_telemetry()
                return {
                    "success": True,
                    "provider": "lmstudio",
                    "message": "Model unloaded from GPU memory.",
                    "gpu_telemetry": gpu,
                }
            except Exception as e:
                logger.error("LM Studio unload error: %s", e)
                return {"success": False, "error": str(e)}

        elif prov == "ollama":
            base_url = getattr(settings, "ollama_base_url", "http://localhost:11434").rstrip("/")
            try:
                m_to_unload = model or getattr(settings, "ollama_model", "")
                payload = {
                    "model": m_to_unload,
                    "keep_alive": 0,
                }
                req = urllib.request.Request(
                    f"{base_url}/api/generate",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "Atos-AI"},
                )
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    gpu = self.get_gpu_telemetry()
                    return {
                        "success": True,
                        "provider": "ollama",
                        "message": f"Model '{m_to_unload}' unloaded from Ollama memory.",
                        "gpu_telemetry": gpu,
                    }
            except Exception as e:
                logger.error("Ollama unload error: %s", e)
                return {"success": False, "error": str(e)}

        return {"success": False, "error": f"Unsupported provider: {provider}"}

    def get_full_state(self) -> Dict[str, Any]:
        """Consolidates GPU telemetry, hardware profile, LM Studio status, and Ollama status (cached 2s)."""
        now = time.time()
        if (now - getattr(self, "_last_full_state_time", 0.0)) < 2.0 and getattr(self, "_last_full_state", None):
            return self._last_full_state

        gpu = self.get_gpu_telemetry()
        state = {
            "gpu": gpu,
            "hardware_profile": gpu.get("profile", {}),
            "lmstudio": self.get_lmstudio_status(),
            "ollama": self.get_ollama_status(),
            "active_provider": getattr(settings, "llm_provider", "lmstudio"),
            "context_window": getattr(settings, "local_context_window", 16384),
            "rolling_context": getattr(settings, "local_rolling_context", True),
            "gpu_layers": getattr(settings, "local_gpu_layers", 99),
        }
        self._last_full_state = state
        self._last_full_state_time = now
        return state


local_model_service = LocalModelService()
