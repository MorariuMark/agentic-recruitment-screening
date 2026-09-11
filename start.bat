@echo off
title Agentic Recruitment Screening Launcher
echo ======================================================================
echo   Starting Agentic Recruitment Screening System
echo ======================================================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Using Python: %PYTHON_EXE%
echo Launching Backend and Frontend UI...
echo.

"%PYTHON_EXE%" start.py

pause
