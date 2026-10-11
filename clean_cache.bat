@echo off
title Clean Cache
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe scripts\clean_cache.py
) else (
    python scripts\clean_cache.py
)
pause
