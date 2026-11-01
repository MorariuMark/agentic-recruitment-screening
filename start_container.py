"""
start_container.py
Container process supervisor for single-container cloud deployment.
Concurrently launches the FastAPI backend on localhost:8000 and the Next.js frontend
on the public container port (default 7860 for Hugging Face Spaces / cloud environments).
Handles health checks, graceful shutdown (SIGTERM/SIGINT), and process supervision.
"""

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def is_service_healthy(url: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ContainerSupervisorHealthCheck/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    port = os.environ.get("PORT", "7860")
    print("=" * 70)
    print(" Starting Enterprise Agentic Screening Platform in Container")
    print(f" Target Public Port: {port}")
    print("=" * 70, flush=True)

    # 1. Ensure persistent local directories exist
    data_dir = Path("./data")
    chroma_dir = Path("./data/chroma_db")
    data_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    backend_proc = None
    frontend_proc = None

    def shutdown_children(signum=None, frame=None):
        print("\n[Supervisor] Received termination signal. Stopping services...", flush=True)
        if frontend_proc and frontend_proc.poll() is None:
            try:
                frontend_proc.terminate()
            except Exception:
                pass
        if backend_proc and backend_proc.poll() is None:
            try:
                backend_proc.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_children)
    signal.signal(signal.SIGINT, shutdown_children)

    # 2. Launch FastAPI Backend on 127.0.0.1:8000
    print("[Supervisor] Launching FastAPI backend on 127.0.0.1:8000...", flush=True)
    backend_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ]
    )

    # 3. Wait for Backend /health readiness
    health_url = "http://127.0.0.1:8000/health"
    print("[Supervisor] Polling backend health endpoint...", flush=True)
    max_wait_seconds = 60
    start_time = time.time()
    backend_ready = False

    while time.time() - start_time < max_wait_seconds:
        if backend_proc.poll() is not None:
            print(f"[Supervisor] Backend process exited unexpectedly with code {backend_proc.returncode}!", flush=True)
            sys.exit(1)
        if is_service_healthy(health_url):
            backend_ready = True
            print(f"[Supervisor] FastAPI backend is healthy ({time.time() - start_time:.1f}s)!", flush=True)
            break
        time.sleep(1)

    if not backend_ready:
        print("[Supervisor] Backend failed to become healthy within timeout. Continuing anyway...", flush=True)

    # 4. Launch Next.js Frontend on 0.0.0.0:{PORT}
    print(f"[Supervisor] Launching Next.js frontend on 0.0.0.0:{port}...", flush=True)
    frontend_env = os.environ.copy()
    frontend_env["PORT"] = port
    frontend_env["BACKEND_API_URL"] = "http://127.0.0.1:8000"

    frontend_dir = Path("./frontend-next")
    frontend_proc = subprocess.Popen(
        [
            "npm",
            "run",
            "start",
            "--",
            "-p",
            str(port),
            "-H",
            "0.0.0.0",
        ],
        cwd=str(frontend_dir),
        env=frontend_env,
    )

    print("[Supervisor] Both services are running. Monitoring container...", flush=True)

    # 5. Monitor processes
    while True:
        if backend_proc.poll() is not None:
            print(f"[Supervisor] Backend exited with code {backend_proc.returncode}. Shutting down.", flush=True)
            shutdown_children()
            break
        if frontend_proc.poll() is not None:
            print(f"[Supervisor] Frontend exited with code {frontend_proc.returncode}. Shutting down.", flush=True)
            shutdown_children()
            break
        time.sleep(2)


if __name__ == "__main__":
    main()
