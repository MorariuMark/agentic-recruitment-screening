@echo off
title Enterprise Agentic Recruitment Screening Platform
echo =======================================================================
echo  Launching Enterprise Screening Platform (Next.js 15 + FastAPI)
echo =======================================================================

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

%PYTHON_EXE% start_enterprise.py
pause
