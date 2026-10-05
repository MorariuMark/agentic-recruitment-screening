"""
start.py
Single-command startup runner for Agentic Recruitment Screening.
Supports launching the modern Next.js 15 enterprise UI, legacy Streamlit dashboard, or both concurrently.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser


def is_port_in_use(port: int) -> bool:
    """Checks whether a local TCP port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


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
    parser = argparse.ArgumentParser(description="Start the Agentic Recruitment Screening Platform")
    parser.add_argument(
        "--ui",
        choices=["next", "streamlit", "all"],
        default="next",
        help="Frontend UI to launch: 'next' (Next.js 15 enterprise studio, default), 'streamlit' (legacy dashboard), or 'all' (both).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open the browser on startup.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print(" Starting Agentic Recruitment Screening Platform")
    print(f" Mode: UI={args.ui.upper()} | Backend=FastAPI")
    print("=" * 70)

    # Clean stale ports if occupied
    ports_to_check = [8000]
    if args.ui in ("next", "all"):
        ports_to_check.append(3000)
    if args.ui in ("streamlit", "all"):
        ports_to_check.append(8501)

    for port in ports_to_check:
        if is_port_in_use(port):
            print(f"Port {port} in use by stale process. Clearing port {port}...")
            kill_process_on_port(port)

    # Determine Python executable
    venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    print(f"Using Python: {venv_python}")
    print("Starting FastAPI backend on http://127.0.0.1:8000 ...")

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
            "--timeout-keep-alive",
            "75",
        ],
        cwd=os.getcwd(),
    )

    # Wait for backend to be ready via /health polling
    print("Waiting for FastAPI backend to initialize...")
    import urllib.request

    backend_ready = False
    for attempt in range(40):  # up to 20 seconds (0.5s intervals)
        if backend_proc.poll() is not None:
            print("Backend process terminated unexpectedly during startup.")
            break
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1.0) as resp:
                if resp.status == 200:
                    backend_ready = True
                    break
        except Exception:
            time.sleep(0.5)

    if backend_ready:
        print("FastAPI backend is healthy and responding.")
    else:
        print("Warning: Backend health check timed out. Launching frontend anyway...")

    frontend_procs = []

    # 1. Launch Next.js Enterprise UI
    if args.ui in ("next", "all"):
        print("Starting Next.js enterprise UI on http://localhost:3000 ...")
        frontend_dir = os.path.join(os.getcwd(), "frontend-next")
        npm_cmd = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
        next_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=frontend_dir,
            shell=True,
        )
        frontend_procs.append(("Next.js Enterprise Studio", next_proc, "http://localhost:3000"))

    # 2. Launch Streamlit Legacy UI
    if args.ui in ("streamlit", "all"):
        print("Starting Streamlit legacy UI on http://127.0.0.1:8501 ...")
        st_proc = subprocess.Popen(
            [
                venv_python,
                "-m",
                "streamlit",
                "run",
                "frontend/app.py",
                "--server.port=8501",
                "--server.address=127.0.0.1",
            ],
            cwd=os.getcwd(),
        )
        frontend_procs.append(("Streamlit Dashboard", st_proc, "http://127.0.0.1:8501"))

    print("\n" + "=" * 70)
    print(" Applications successfully launched!")
    for name, _, url in frontend_procs:
        print(f"   - {name:<26}: {url}")
    print("   - FastAPI Backend           : http://127.0.0.1:8000")
    print("   - API Interactive Docs      : http://127.0.0.1:8000/docs")
    print("   - Backend Health Check      : http://127.0.0.1:8000/health")
    print("=" * 70)
    print("Press Ctrl+C to gracefully terminate all services.\n")

    # Automatically open primary browser
    if not args.no_browser and frontend_procs:
        try:
            webbrowser.open(frontend_procs[0][2])
        except Exception:
            pass

    all_procs = [backend_proc] + [p for _, p, _ in frontend_procs]
    try:
        while True:
            time.sleep(1)
            if any(p.poll() is not None for p in all_procs):
                print("One of the child processes exited. Terminating remaining services...")
                break
    except KeyboardInterrupt:
        print("\nTerminating background services...")
    finally:
        for p in all_procs:
            if p:
                try:
                    p.terminate()
                    p.wait(timeout=3)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
        print("All services terminated cleanly. Goodbye!")


if __name__ == "__main__":
    main()
