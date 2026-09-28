@echo off
setlocal EnableDelayedExpansion
chcp 65001 >/dev/null 2>&1
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"

set "RAG_MODE="
set "IDX="
set "IDX_SET="
set "TUNA=https://pypi.tuna.tsinghua.edu.cn/simple"
set "ALIYUN=https://mirrors.aliyun.com/pypi/simple/"
set "OFFICIAL=https://pypi.org/simple"

REM === 解析参数 ===
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--rag" set "RAG_MODE=rag"
if /I "%~1"=="--rag-cpu" set "RAG_MODE=rag_cpu"
if /I "%~1"=="--official" ( set "IDX=%OFFICIAL%" & set "IDX_SET=1" )
if /I "%~1"=="--mirror" (
    shift
    if /I "%~1"=="aliyun" ( set "IDX=%ALIYUN%" ) else ( set "IDX=%TUNA%" )
    set "IDX_SET=1"
)
if /I "%~1"=="--index-url" ( shift & set "IDX=%~1" & set "IDX_SET=1" )
if /I "%~1"=="-h" goto show_help
if /I "%~1"=="--help" goto show_help
shift
goto parse_args

:show_help
echo Usage: run.bat [--official ^| --mirror aliyun ^| --index-url URL] [--rag ^| --rag-cpu]
exit /b 0

:args_done
REM 优先级：CLI > 环境变量 > 默认（清华镜像）
if not defined IDX_SET (
    if defined COZYWRITER_PIP_INDEX set "IDX=%COZYWRITER_PIP_INDEX%"
)
if not defined IDX (
    if defined PIP_INDEX_URL set "IDX=%PIP_INDEX_URL%"
)
if not defined IDX set "IDX=%TUNA%"

echo ========================================
echo   CozyWriter - AI Novel / Script Writer
echo ========================================
echo.

REM 统一 pip / uv 源，并防止依赖装到用户级 site-packages
set "PIP_INDEX_URL=%IDX%"
set "UV_DEFAULT_INDEX=%IDX%"
set "UV_INDEX_URL=%IDX%"
set "PIP_USER=0"
set "PYTHONNOUSERSITE=1"
set "PIP_REQUIRE_VIRTUALENV=1"

REM === Step 1: virtual environment ===
echo [1/4] Checking Python and virtual environment .venv ...

if exist ".venv\Scripts\python.exe" goto :venv_ready
if exist ".venv\bin\python" (
    echo [ERROR] Detected a Linux/macOS virtualenv ^(.venv/bin^).
    echo         Run ./run.sh on Linux/macOS, or delete .venv and retry here.
    pause
    exit /b 1
)

where python >nul 2>&1
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

:venv_ready
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] Virtual environment is broken. Delete .venv and retry.
    pause
    exit /b 1
)
"%PY%" -c "import os,sys; p=os.path.abspath(sys.prefix); r=os.path.abspath(os.getcwd()); sys.exit(0 if p.startswith(r) else 2)"
if errorlevel 1 (
    echo [ERROR] .venv is broken or outside the project folder. Delete .venv and retry.
    pause
    exit /b 1
)
echo       Ready: %PROJECT_ROOT%\.venv
echo       Index: %IDX%
echo.

REM === Step 2: pip upgrade ===
echo [2/4] Upgrading pip ...
"%PY%" -m pip install --upgrade pip --no-user --disable-pip-version-check --quiet
if errorlevel 1 (
    echo [WARN] pip upgrade failed; continuing with existing pip.
)
echo       Done.
echo.

REM === Step 3: install requirements ===
echo [3/4] Installing dependencies ^(first run may take a few minutes^) ...
echo.
"%PY%" -m pip install -r requirements.txt --no-user --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [!] Install failed with %IDX%
    if /I not "%IDX%"=="%TUNA%" (
        echo     Retrying with Tsinghua mirror %TUNA% ...
        set "PIP_INDEX_URL=%TUNA%"
        "%PY%" -m pip install -r requirements.txt --no-user --disable-pip-version-check
    )
    if errorlevel 1 (
        echo [ERROR] pip install failed. Check the error above.
        pause
        exit /b 1
    )
)

if /I "%RAG_MODE%"=="rag_cpu" (
    echo       Installing CPU RAG dependencies ...
    call tools\install_rag_cpu.bat
)
if /I "%RAG_MODE%"=="rag" (
    echo       Installing RAG dependencies ^(may include nvidia-*^) ...
    "%PY%" -m pip install -r requirements-rag.txt --no-user --disable-pip-version-check
)

echo.
echo       Verifying install location ...
"%PY%" -c "import os,sys; e=os.path.abspath(sys.executable); r=os.path.abspath(os.getcwd()); assert e.startswith(r), 'not in project venv: '+e; import fastapi; print('       OK:', sys.executable)"
if errorlevel 1 (
    echo [ERROR] Dependencies are not installed inside the project .venv.
    pause
    exit /b 1
)
echo       Dependencies ready.
echo.

REM === Step 4: launch server ===
if not exist "data" mkdir data
echo [4/4] Starting CozyWriter ...
echo.
echo   URL  : http://localhost:13567
echo   Hint : configure LLM provider in "Settings - Providers" (DB first; .env is fallback).
echo          opencode needs an API key to enable.
echo          RAG: "Settings - RAG" local CPU or online API (see docs/rag_setup.md).
echo   Stop : Ctrl+C
echo.
"%PY%" main.py
