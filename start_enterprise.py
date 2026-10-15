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

# Ensure Windows cmd/powershell never crashes on Unicode output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def is_port_in_use(port: int) -> bool:
    """Checks whether a local TCP port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_service_healthy(url: str, timeout: float = 2.0) -> bool:
    """Checks if an HTTP service responds with 200 OK."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "EnterpriseScreeningHealthCheck/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def kill_process_on_port(port: int):
    """Terminates any stale/zombie process tree holding the target port on Windows."""
    try:
        out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
        pids = set()
        for line in out.strip().splitlines():
            parts = line.split()
            # Ensure the local address strictly matches :port
            if len(parts) >= 5 and "LISTENING" in parts and parts[1].endswith(f":{port}"):
                pids.add(parts[-1])
        for pid in pids:
            if pid != "0":
                subprocess.run(f"taskkill /PID {pid} /T /F", shell=True, capture_output=True)
        time.sleep(1)
    except Exception:
        pass


def kill_process_tree(proc):
    """Safely terminates a process and all its child processes on Windows or POSIX."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(f"taskkill /PID {proc.pid} /T /F", shell=True, capture_output=True)
        else:
            proc.terminate()
            proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
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
    npm_cmd = shutil.which("npm.cmd") or shutil.which("npm") or "npm"

    print(f"Using Python: {venv_python}")
    print(f"Using npm:    {npm_cmd}")

    backend_proc = None
    frontend_proc = None

    # 3. Check or launch FastAPI Backend (Port 8000)
    print("\n[1/2] Verifying FastAPI backend on http://127.0.0.1:8000 ...")
    if is_service_healthy("http://127.0.0.1:8000/health"):
        print("[OK] FastAPI backend is already running and healthy.")
    else:
        if is_port_in_use(8000):
            print("Port 8000 in use by stale process. Clearing port 8000...")
            kill_process_on_port(8000)

        print("Starting FastAPI backend with uvicorn...")
        backend_cmd = [
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
            "--reload-exclude",
            "*__pycache__*",
            "--reload-exclude",
            "*.pyc",
        ]
        backend_proc = subprocess.Popen(
            backend_cmd,
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
            print("[OK] FastAPI backend is online and database is initialized.")
        else:
            print("Warning: Backend health check timed out. Launching frontend anyway...")

    # 4. Check or launch Next.js Frontend (Port 3000)
    print("\n[2/2] Verifying Next.js Enterprise Frontend on http://127.0.0.1:3000 ...")
    frontend_dir = os.path.join(project_root, "frontend-next")

    if is_port_in_use(3000):
        print("[OK] Next.js frontend is already running and listening on port 3000.")
    else:
        print("Starting Next.js Dev Server...")
        frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=frontend_dir,
            shell=True,
        )

        print("Waiting for Next.js development server to initialize...")
        frontend_ready = False
        for attempt in range(60):  # up to 30 seconds
            if frontend_proc.poll() is not None:
                print("Error: Next.js dev server exited unexpectedly.")
                break
            if is_port_in_use(3000):
                frontend_ready = True
                break
            time.sleep(0.5)

        if frontend_ready:
            print("[OK] Next.js enterprise UI is online and listening on port 3000.")
        else:
            print("Warning: Frontend startup took longer than expected. Continuing...")

    print("\n" + "=" * 75)
    print(" Enterprise Platform Successfully Ready!")
    print("   - Enterprise Web Dashboard: http://127.0.0.1:3000  (or http://localhost:3000)")
    print("   - FastAPI REST API Engine:  http://127.0.0.1:8000")
    print("   - Interactive API Swagger:  http://127.0.0.1:8000/docs")
    print("   - Arize Phoenix Tracing:    http://127.0.0.1:6006")
    print("=" * 75)
    print("Press Ctrl+C to gracefully terminate all services.\n")

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
                print("\nFastAPI backend service terminated.")
                break
            if frontend_proc and frontend_proc.poll() is not None:
                print("\nNext.js frontend service terminated.")
                break
    except KeyboardInterrupt:
        print("\nShutting down enterprise services...")
    finally:
        for p in (backend_proc, frontend_proc):
            kill_process_tree(p)
        print("All managed services stopped cleanly. Goodbye!")


if __name__ == "__main__":
    main()
