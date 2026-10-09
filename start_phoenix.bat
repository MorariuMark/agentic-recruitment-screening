@echo off
echo ===================================================
echo  Pornire Server Observabilitate Arize Phoenix
echo ===================================================
echo  Acces Dashboard: http://localhost:6006
echo ===================================================

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -m phoenix.server.main serve --port 6006
) else (
    python -m phoenix.server.main serve --port 6006
)

pause
