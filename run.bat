@echo off
setlocal EnableDelayedExpansion
chcp 65001 >/dev/null 2>&1
cd /d "%~dp0"

echo ========================================
echo   CozyWriter - AI Novel / Script Writer
echo ========================================
echo.

REM === Step 1: virtual environment ===
echo [1/4] Checking Python and virtual environment .venv ...
if not exist ".venv\Scripts\python.exe" (
    where python >/dev/null 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found on PATH. Please install Python 3.10+.
        pause
        exit /b 1
    )
    echo       Creating virtual environment ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Is Python 3.10+ installed?
        pause
        exit /b 1
    )
    echo       Done.
) else (
    echo       Virtual environment ready.
)
echo.

REM === Step 2: pip upgrade ===
echo [2/4] Upgrading pip ...
.venv\Scripts\python -m pip install --upgrade pip --disable-pip-version-check --quiet
echo       Done.
echo.

REM === Step 3: install requirements ===
echo [3/4] Installing dependencies ^(first run may take a few minutes^) ...
echo.
.venv\Scripts\python -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed. Check the error above.
    pause
    exit /b 1
)
echo.
echo       Dependencies ready.
echo.

REM === Step 4: launch server ===
if not exist "data" mkdir data
echo [4/4] Starting CozyWriter ...
echo.
echo   URL  : http://localhost:13567
echo   Hint : configure LLM provider in "Settings - Providers" (DB first; .env is fallback).
echo          opencode needs an API key to enable; RAG is optional, see docs/rag_setup.md.
echo   Stop : Ctrl+C
echo.
.venv\Scripts\python main.py
