"""
start_container.py
Container process supervisor for single-container cloud deployment.
Concurrently launches the FastAPI backend on localhost:8000 and the Next.js frontend
on the public container port (default 10000 for Render / 7860 for Hugging Face Spaces).
Transparently forwards ports (10000 <-> 7860 <-> 8080) so that all cloud routing works.
Automatically restores untrashed seed data (CVs, JDs, ChromaDB) on startup.
Handles health checks, graceful shutdown (SIGTERM/SIGINT), and process supervision.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
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


def start_port_forwarder(source_port: int, target_port: int):
    """Transparently pipes TCP traffic from source_port to target_port so multiple cloud hosts work."""
    def handle_client(client_socket):
        try:
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.connect(("127.0.0.1", target_port))

            def pipe(src, dst):
                try:
                    while True:
                        data = src.recv(16384)
                        if not data:
                            break
                        dst.sendall(data)
                except Exception:
                    pass
                finally:
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except Exception:
                        pass

            t1 = threading.Thread(target=pipe, args=(client_socket, target_socket), daemon=True)
            t2 = threading.Thread(target=pipe, args=(target_socket, client_socket), daemon=True)
            t1.start()
            t2.start()
        except Exception:
            try:
                client_socket.close()
            except Exception:
                pass

    def server_loop():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("0.0.0.0", source_port))
            server.listen(128)
            print(f"[Port Forwarder] Active: 0.0.0.0:{source_port} -> 127.0.0.1:{target_port}", flush=True)
            while True:
                client, _ = server.accept()
                threading.Thread(target=handle_client, args=(client,), daemon=True).start()
        except Exception as e:
            print(f"[Port Forwarder] Port {source_port} binding skipped ({e})", flush=True)

    threading.Thread(target=server_loop, daemon=True).start()


def main():
    # Render sets PORT to 10000 by default; Hugging Face uses 7860
    port_str = os.environ.get("PORT", "10000")
    try:
        primary_port = int(port_str)
    except ValueError:
        primary_port = 10000

    print("=" * 70)
    print(" Starting Enterprise Agentic Screening Platform in Container")
    print(f" Primary Public Port: {primary_port}")
    print("=" * 70, flush=True)

    # 1. Ensure persistent local directories exist
    data_dir = Path("./data")
    chroma_dir = Path("./data/chroma_db")
    data_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    # 1.1 Automatically restore untrashed seed database if screening.db is missing or empty
    seed_gz = data_dir / "screening_seed.db.gz"
    db_file = data_dir / "screening.db"
    if seed_gz.exists() and (not db_file.exists() or db_file.stat().st_size < 1024):
        print(f"[Supervisor] Restoring untrashed seed database from {seed_gz.name}...", flush=True)
        try:
            import gzip
            import shutil
            with gzip.open(seed_gz, "rb") as f_in:
                with open(db_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            print(f"[Supervisor] Database restored successfully ({db_file.stat().st_size / (1024*1024):.1f} MB)!", flush=True)
        except Exception as e:
            print(f"[Supervisor] Database restoration failed: {e}", flush=True)

    # 1.2 Automatically restore pre-computed vector index if chroma_db is empty
    chroma_gz = data_dir / "chroma_db.tar.gz"
    if chroma_gz.exists() and (not chroma_dir.exists() or not any(chroma_dir.iterdir())):
        print(f"[Supervisor] Restoring ChromaDB vector store from {chroma_gz.name}...", flush=True)
        try:
            import tarfile
            with tarfile.open(chroma_gz, "r:gz") as tar:
                tar.extractall(path=str(data_dir))
            print("[Supervisor] ChromaDB vector store restored successfully!", flush=True)
        except Exception as e:
            print(f"[Supervisor] ChromaDB restoration failed: {e}", flush=True)

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

    # 2. Select non-colliding backend port (avoid primary_port)
    backend_port = 8000 if primary_port != 8000 else 8088
    backend_url = f"http://127.0.0.1:{backend_port}"

    # 3. Launch Next.js Frontend immediately so public port 10000 opens in seconds
    print(f"[Supervisor] Launching Next.js frontend on 0.0.0.0:{primary_port}...", flush=True)
    frontend_env = os.environ.copy()
    frontend_env["PORT"] = str(primary_port)
    frontend_env["BACKEND_API_URL"] = backend_url
    frontend_env["NODE_OPTIONS"] = "--max-old-space-size=256"

    frontend_dir = Path("./frontend-next")
    frontend_proc = subprocess.Popen(
        [
            "npm",
            "run",
            "start",
            "--",
            "-p",
            str(primary_port),
            "-H",
            "0.0.0.0",
        ],
        cwd=str(frontend_dir),
        env=frontend_env,
    )

    # 4. Start auxiliary port forwarders so all cloud platforms route successfully
    candidate_ports = [10000, 7860, 8080]
    for p in candidate_ports:
        if p != primary_port:
            start_port_forwarder(p, primary_port)

    # 5. Launch FastAPI Backend with low-memory thread tuning
    print(f"[Supervisor] Launching FastAPI backend on 127.0.0.1:{backend_port}...", flush=True)
    backend_env = os.environ.copy()
    backend_env["OMP_NUM_THREADS"] = "1"
    backend_env["OPENBLAS_NUM_THREADS"] = "1"
    backend_env["MKL_NUM_THREADS"] = "1"
    backend_env["DISABLE_RERANKER_WARMUP"] = "1"
    backend_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(backend_port),
            "--timeout-keep-alive",
            "30",
        ],
        env=backend_env,
    )

    # 6. Monitor Backend /health readiness
    health_url = f"{backend_url}/health"
    print("[Supervisor] Polling backend health endpoint...", flush=True)
    max_wait_seconds = 60
    start_time = time.time()
    backend_ready = False

    while time.time() - start_time < max_wait_seconds:
        if backend_proc.poll() is not None:
            print(f"[Supervisor] Backend process exited unexpectedly with code {backend_proc.returncode}!", flush=True)
            shutdown_children()
            sys.exit(1)
        if is_service_healthy(health_url):
            backend_ready = True
            print(f"[Supervisor] FastAPI backend is healthy ({time.time() - start_time:.1f}s)!", flush=True)
            break
        time.sleep(1)

    if not backend_ready:
        print("[Supervisor] Backend failed to become healthy within timeout. Continuing anyway...", flush=True)

    print("[Supervisor] Both services are running. Monitoring container...", flush=True)

    # 6. Monitor processes
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
