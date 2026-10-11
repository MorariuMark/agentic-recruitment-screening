"""
scripts/clean_cache.py
Safely purges ephemeral build and compilation caches without touching dependencies, databases, or project code.
Reclaims ~350MB+ disk space from Next.js and Python bytecode caches.
"""

import os
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

TARGETS = [
    ROOT_DIR / "frontend-next" / ".next",
    ROOT_DIR / ".pytest_cache",
]

def purge_caches():
    freed_bytes = 0
    print("=" * 60)
    print(" Agentic Recruitment Screening - Cache Purge Utility")
    print("=" * 60)

    # 1. Purge targeted build folders
    for target in TARGETS:
        if target.exists():
            try:
                size = sum(f.stat().st_size for f in target.glob("**/*") if f.is_file())
                shutil.rmtree(target)
                freed_bytes += size
                print(f"Purged: {target.relative_to(ROOT_DIR)} ({round(size / 1024 / 1024, 2)} MB freed)")
            except Exception as e:
                print(f"Skipped {target.relative_to(ROOT_DIR)}: {e}")

    # 2. Purge __pycache__ folders across the repo (excluding .venv)
    pycache_count = 0
    pycache_bytes = 0
    for path in ROOT_DIR.rglob("__pycache__"):
        if ".venv" in path.parts:
            continue
        try:
            size = sum(f.stat().st_size for f in path.glob("**/*") if f.is_file())
            shutil.rmtree(path)
            pycache_count += 1
            pycache_bytes += size
        except Exception:
            pass

    freed_bytes += pycache_bytes
    print(f"Purged: {pycache_count} __pycache__ directories ({round(pycache_bytes / 1024 / 1024, 2)} MB freed)")
    print("-" * 60)
    print(f"Total space reclaimed: {round(freed_bytes / 1024 / 1024, 2)} MB")
    print("=" * 60)

if __name__ == "__main__":
    purge_caches()
