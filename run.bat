@echo off
setlocal EnableDelayedExpansion
chcp 65001 >/dev/null 2>&1
echo ========================================
echo   CozyWriter - Novel Writing Assistant
echo ========================================
echo.

REM === Step 1: virtual environment ===
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Is Python 3.10+ installed and on PATH?
        pause
        exit /b 1
    )
    echo       Done.
) else (
    echo [1/4] Virtual environment ready.
)
echo.

REM === Step 2: pip upgrade ===
echo [2/4] Upgrading pip ...
.venv\Scripts\python -m pip install --upgrade pip --disable-pip-version-check 2>/dev/null
echo       Done.
echo.

REM === Step 3: install requirements ===
echo [3/4] Installing dependencies (this may take a few minutes on first run) ...
echo.
.venv\Scripts\python -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed. Check the error above.
    pause
    exit /b 1
)
echo.
echo       All dependencies installed.
echo.

REM === Step 4: launch server ===
echo [4/4] Starting CozyWriter server ...
echo       Open http://localhost:13567 in your browser
echo       Press Ctrl+C to stop.
echo.
.venv\Scripts\python main.py
