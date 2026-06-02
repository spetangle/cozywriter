@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
echo ========================================
echo   CozyWriter - Novel Writing Assistant
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
)

echo [INFO] Installing dependencies...
.venv\Scripts\python -m pip install -r requirements.txt >nul 2>&1

echo [INFO] Starting server...
echo [INFO] Open http://localhost:8000
echo.

.venv\Scripts\python main.py
