@echo off
setlocal EnableDelayedExpansion
chcp 65001 >/dev/null 2>&1
cd /d "%~dp0.."

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] .venv\Scripts\python.exe not found. Run run.bat first.
    pause
    exit /b 1
)

echo [1/4] Uninstalling existing torch if any ...
"%PY%" -m pip uninstall -y torch >nul 2>&1

echo [2/4] Installing CPU-only torch ...
"%PY%" -m pip install --upgrade torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo [ERROR] torch (CPU) install failed.
    pause
    exit /b 1
)

echo [3/4] Installing RAG dependencies ^(sentence-transformers^) ...
"%PY%" -m pip install -r requirements-rag.txt
if errorlevel 1 (
    echo [ERROR] requirements-rag.txt install failed.
    pause
    exit /b 1
)

echo [4/4] Verifying ...
"%PY%" -c "import torch; print('  torch=', torch.__version__, ' cuda_available=', torch.cuda.is_available())"

echo.
echo [OK] CPU RAG installed.
pause
