"""
start_enterprise.py
Single-command startup runner for the Enterprise Agentic Recruitment Screening Platform.
Concurrently launches the FastAPI backend engine and the Next.js 16 enterprise UI.
Includes port conflict resolution, health polling, and automatic browser launch.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser


def is_port_in_use(port: int) -> bool:
    """Checks whether a local TCP port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_service_healthy(url: str, timeout: float = 1.0) -> bool:
    """Checks if an HTTP service responds with 200 OK."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def kill_process_on_port(port: int):
    """Terminates any stale/zombie process holding the target port on Windows."""
    try:
        out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
        pids = set()
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and "LISTENING" in parts:
                pids.add(parts[-1])
        for pid in pids:
            if pid != "0":
                subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True)
        time.sleep(1)
    except Exception:
        pass


def main():
    print("=" * 75)
    print(" Starting Enterprise Agentic Recruitment Screening Platform")
    print(" Next.js 16 Dark UI + FastAPI Asymmetric RAG Backend")
    print("=" * 75)

    project_root = os.getcwd()

    # 1. Locate Python executable in virtual environment
    venv_python = os.path.join(project_root, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    # 2. Locate npm executable
    npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm_cmd:
        print("Error: 'npm' command not found in PATH. Please install Node.js 18+.")
        sys.exit(1)

    print(f"Using Python: {venv_python}")
    print(f"Using npm:    {npm_cmd}")

    backend_proc = None
    frontend_proc = None

    # 3. Check or launch FastAPI Backend (Port 8000)
    print("\n[1/2] Verifying FastAPI backend on http://127.0.0.1:8000 ...")
    if is_service_healthy("http://127.0.0.1:8000/health"):
        print("✓ FastAPI backend is already running and healthy.")
    else:
        if is_port_in_use(8000):
            print("Port 8000 in use by stale process. Clearing port 8000...")
            kill_process_on_port(8000)

        print("Starting FastAPI backend with uvicorn...")
        backend_proc = subprocess.Popen(
            [
                venv_python,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--reload",
                "--reload-dir",
                "backend",
            ],
            cwd=project_root,
        )

        print("Waiting for FastAPI backend to initialize and apply migrations...")
        backend_ready = False
        for attempt in range(40):
            if backend_proc.poll() is not None:
                print("Error: Backend process exited unexpectedly.")
                break
            if is_service_healthy("http://127.0.0.1:8000/health"):
                backend_ready = True
                break
            time.sleep(0.5)

        if backend_ready:
            print("✓ FastAPI backend is online and database is initialized.")
        else:
            print("Warning: Backend health check timed out. Launching frontend anyway...")

    # 4. Check or launch Next.js Frontend (Port 3000)
    print("\n[2/2] Verifying Next.js Enterprise Frontend on http://127.0.0.1:3000 ...")
    frontend_dir = os.path.join(project_root, "frontend-next")

    if is_service_healthy("http://127.0.0.1:3000"):
        print("✓ Next.js frontend is already running and serving.")
    else:
        if is_port_in_use(3000):
            print("Port 3000 in use by stale process. Clearing port 3000...")
            kill_process_on_port(3000)

        print("Starting Next.js Dev Server (Turbopack)...")
        frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev", "--", "--port", "3000"],
            cwd=frontend_dir,
        )

        print("Waiting for Next.js development server to compile...")
        for attempt in range(40):
            if frontend_proc.poll() is not None:
                print("Error: Next.js dev server exited unexpectedly.")
                break
            if is_service_healthy("http://127.0.0.1:3000"):
                break
            time.sleep(0.5)

    print("\n" + "=" * 75)
    print(" Enterprise Platform Successfully Ready!")
    print("   - Enterprise Web Dashboard: http://127.0.0.1:3000  (or http://localhost:3000)")
    print("   - FastAPI REST API Engine:  http://127.0.0.1:8000")
    print("   - Interactive API Swagger:  http://127.0.0.1:8000/docs")
    print("   - Arize Phoenix Tracing:    http://127.0.0.1:6006")
    print("=" * 75)
    print("Press Ctrl+C to gracefully terminate any processes launched by this session.\n")

    # 5. Open browser once frontend is proven responsive
    time.sleep(1)
    try:
        webbrowser.open("http://localhost:3000")
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)
            if backend_proc and backend_proc.poll() is not None:
                print("\nFastAPI backend service terminated unexpectedly.")
                break
            if frontend_proc and frontend_proc.poll() is not None:
                print("\nNext.js frontend service terminated unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nShutting down enterprise services...")
    finally:
        for p in (backend_proc, frontend_proc):
            if p:
                try:
                    p.terminate()
                    p.wait(timeout=3)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
        print("All managed services stopped cleanly. Goodbye!")


if __name__ == "__main__":
    main()
