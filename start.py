"""
start.py
Single-command startup runner for Agentic Recruitment Screening.
Launches both the FastAPI backend server and the Streamlit frontend dashboard concurrently.
"""

import os
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
    print("=" * 70)
    print(" Starting Agentic Recruitment Screening System")
    print("=" * 70)

    # Clean stale ports if occupied
    for port in (8000, 8501):
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

    print("Starting Streamlit frontend on http://127.0.0.1:8501 ...")
    frontend_proc = subprocess.Popen(
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

    print("\n" + "=" * 70)
    print(" Applications successfully launched!")
    print("   - Frontend Dashboard:   http://127.0.0.1:8501")
    print("   - FastAPI Backend:      http://127.0.0.1:8000")
    print("   - API Interactive Docs: http://127.0.0.1:8000/docs")
    print("   - Health Check:         http://127.0.0.1:8000/health")
    print("=" * 70)
    print("Press Ctrl+C to gracefully terminate both services.\n")

    # Automatically open browser to Streamlit dashboard
    try:
        webbrowser.open("http://127.0.0.1:8501")
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None or frontend_proc.poll() is not None:
                print("One of the child processes exited. Terminating...")
                break
    except KeyboardInterrupt:
        print("\nTerminating background services...")
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
        print("Both services terminated cleanly. Goodbye!")


if __name__ == "__main__":
    main()
