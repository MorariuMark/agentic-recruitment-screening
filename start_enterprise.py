"""
start_enterprise.py
Single-command startup runner for the Enterprise Agentic Recruitment Screening Platform.
Concurrently launches the FastAPI backend engine and the Next.js 15 enterprise UI.
"""

import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser


def main():
    print("=" * 75)
    print(" Starting Enterprise Agentic Recruitment Screening Platform")
    print(" Next.js 15 Dark UI + FastAPI Asymmetric RAG Backend")
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
    print("\n[1/2] Starting FastAPI backend on http://127.0.0.1:8000 ...")

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

    # 3. Poll backend /health endpoint
    print("Waiting for FastAPI backend to initialize and apply migrations...")
    backend_ready = False
    for attempt in range(40):
        if backend_proc.poll() is not None:
            print("Error: Backend process exited unexpectedly.")
            break
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1.0) as resp:
                if resp.status == 200:
                    backend_ready = True
                    break
        except Exception:
            time.sleep(0.5)

    if backend_ready:
        print("✓ FastAPI backend is online and database is initialized.")
    else:
        print("Warning: Backend health check timed out. Launching frontend anyway...")

    # 4. Start Next.js frontend in frontend-next/
    print("\n[2/2] Starting Next.js Enterprise Frontend on http://127.0.0.1:3000 ...")
    frontend_dir = os.path.join(project_root, "frontend-next")

    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev", "--", "--port", "3000"],
        cwd=frontend_dir,
    )

    print("\n" + "=" * 75)
    print(" Enterprise Platform Successfully Launched!")
    print("   - Enterprise Web Dashboard: http://127.0.0.1:3000")
    print("   - FastAPI REST API Engine:  http://127.0.0.1:8000")
    print("   - Interactive API Swagger:  http://127.0.0.1:8000/docs")
    print("   - Arize Phoenix Tracing:    http://127.0.0.1:6006")
    print("=" * 75)
    print("Press Ctrl+C to gracefully terminate both services.\n")

    # 5. Open browser to Next.js dashboard
    time.sleep(2)
    try:
        webbrowser.open("http://127.0.0.1:3000")
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None or frontend_proc.poll() is not None:
                print("\nOne of the services terminated unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nShutting down enterprise services...")
    finally:
        for p in (backend_proc, frontend_proc):
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        print("All services stopped cleanly. Goodbye!")


if __name__ == "__main__":
    main()
