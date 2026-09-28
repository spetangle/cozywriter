# CozyWriter - PowerShell startup script
# Usage:
#   .\run.ps1                     # install core deps and start (default: Tsinghua mirror)
#   .\run.ps1 --official          # use PyPI official index
#   .\run.ps1 --mirror aliyun     # use Aliyun mirror
#   .\run.ps1 --index-url URL     # custom index
#   .\run.ps1 --rag               # also install RAG deps
#   .\run.ps1 --rag-cpu           # also install CPU-only RAG (no nvidia-*)
#
# Index can also come from env: COZYWRITER_PIP_INDEX / PIP_INDEX_URL.
# Guarantees all dependencies go into the project-local .venv.

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$Tuna = "https://pypi.tuna.tsinghua.edu.cn/simple"
$Aliyun = "https://mirrors.aliyun.com/pypi/simple/"
$Official = "https://pypi.org/simple"

$RagMode = ""
$IndexUrl = ""
$IndexExplicit = $false

for ($i = 0; $i -lt $Args.Count; $i++) {
    $a = $Args[$i]
    switch -Regex ($a) {
        '^--rag$'        { $RagMode = "rag" }
        '^--rag-cpu$'    { $RagMode = "rag_cpu" }
        '^--official$'   { $IndexUrl = $Official; $IndexExplicit = $true }
        '^--mirror=aliyun$' { $IndexUrl = $Aliyun; $IndexExplicit = $true }
        '^--mirror(=.*)?$'  { $IndexUrl = $Tuna; $IndexExplicit = $true }
        '^--mirror$'     {
            if ($i + 1 -lt $Args.Count -and $Args[$i+1] -eq 'aliyun') { $IndexUrl = $Aliyun; $i++ }
            else { $IndexUrl = $Tuna }
            $IndexExplicit = $true
        }
        '^--index-url$'  { if ($i + 1 -lt $Args.Count) { $IndexUrl = $Args[$i+1]; $i++ }; $IndexExplicit = $true }
        '^--index-url='  { $IndexUrl = $a.Substring(12); $IndexExplicit = $true }
        '^(-h|--help)$'  { Write-Host "Usage: .\run.ps1 [--official | --mirror aliyun | --index-url URL] [--rag | --rag-cpu]"; exit 0 }
    }
}

if (-not $IndexExplicit) {
    if ($env:COZYWRITER_PIP_INDEX) { $IndexUrl = $env:COZYWRITER_PIP_INDEX }
    elseif ($env:PIP_INDEX_URL)    { $IndexUrl = $env:PIP_INDEX_URL }
    elseif ($env:UV_INDEX_URL)     { $IndexUrl = $env:UV_INDEX_URL }
}
if (-not $IndexUrl) { $IndexUrl = $Tuna }

function Write-Step($n, $total, $msg) {
    Write-Host ""
    Write-Host "[$n/$total] $msg" -ForegroundColor Cyan
}
function Fail($msg) {
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    exit 1
}

# 统一 pip / uv 源，避免 pypi.org 超时；并防止装到用户级 site-packages
$env:PIP_INDEX_URL = $IndexUrl
$env:UV_DEFAULT_INDEX = $IndexUrl
$env:UV_INDEX_URL = $IndexUrl
$env:PIP_USER = "0"
$env:PYTHONNOUSERSITE = "1"
$env:PIP_REQUIRE_VIRTUALENV = "1"

# === Step 1/4: Python + virtual environment ===
Write-Step 1 4 "Checking Python and virtual environment .venv ..."

if (Test-Path ".venv\bin\python") {
    Fail "Detected a Linux/macOS virtualenv (.venv/bin). Run ./run.sh on Linux/macOS, or delete .venv and retry."
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { $pythonCmd = Get-Command py -ErrorAction SilentlyContinue }
if (-not $pythonCmd) { Fail "Python not found on PATH. Please install Python 3.10+." }

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "  Creating virtual environment ..." -ForegroundColor Gray
    & $pythonCmd.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create venv. Python 3.10+ required." }
}
if (-not (Test-Path $PythonExe)) { Fail "Virtual environment is broken. Delete .venv and retry." }

& $PythonExe -c "import os,sys; p=os.path.abspath(sys.prefix); r=os.path.abspath(os.getcwd()); sys.exit(0 if p.startswith(r) else 2)"
if ($LASTEXITCODE -ne 0) { Fail ".venv is broken or outside the project folder. Delete .venv and retry." }
Write-Host "  Ready: $ProjectRoot\.venv" -ForegroundColor Green
Write-Host "  Index: $IndexUrl" -ForegroundColor Green

# === Step 2/4: upgrade pip ===
Write-Step 2 4 "Upgrading pip ..."
& $PythonExe -m pip install --upgrade pip --no-user --disable-pip-version-check --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "  [WARN] pip upgrade failed; continuing." -ForegroundColor Yellow }
else { Write-Host "  Done." -ForegroundColor Green }

# === Step 3/4: install deps ===
Write-Step 3 4 "Installing dependencies (first run may take a few minutes) ..."
& $PythonExe -m pip install -r requirements.txt --no-user --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    if ($IndexUrl -ne $Tuna) {
        Write-Host "  [!] Install failed with $IndexUrl; retrying with Tsinghua mirror ..." -ForegroundColor Yellow
        $env:PIP_INDEX_URL = $Tuna
        $env:UV_DEFAULT_INDEX = $Tuna
        $env:UV_INDEX_URL = $Tuna
        & $PythonExe -m pip install -r requirements.txt --no-user --disable-pip-version-check
    }
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Check the output above." }
}

if ($RagMode -eq "rag_cpu") {
    Write-Host "  Installing CPU RAG dependencies ..." -ForegroundColor Cyan
    & (Join-Path $ProjectRoot "tools\install_rag_cpu.ps1")
}
elseif ($RagMode -eq "rag") {
    Write-Host "  Installing RAG dependencies (may include nvidia-*) ..." -ForegroundColor Cyan
    & $PythonExe -m pip install -r requirements-rag.txt --no-user --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Fail "requirements-rag.txt install failed." }
}

Write-Host "  Verifying install location ..." -ForegroundColor Gray
& $PythonExe -c "import os,sys; e=os.path.abspath(sys.executable); r=os.path.abspath(os.getcwd()); assert e.startswith(r), 'not in project venv: '+e; import fastapi; print('  OK:', sys.executable)"
if ($LASTEXITCODE -ne 0) { Fail "Dependencies are not installed inside the project .venv." }
Write-Host "  Dependencies ready." -ForegroundColor Green

# === Step 4/4: start server ===
if (-not (Test-Path "data")) { New-Item -ItemType Directory -Path "data" | Out-Null }
Write-Step 4 4 "Starting CozyWriter ..."
Write-Host "  URL  : http://localhost:13567" -ForegroundColor Green
Write-Host "  Hint : configure LLM provider in 'Settings - Providers' (DB first; .env is fallback)." -ForegroundColor Gray
Write-Host "         opencode needs an API key to enable." -ForegroundColor Gray
Write-Host "         RAG: 'Settings - RAG' local CPU or online API (see docs/rag_setup.md)." -ForegroundColor Gray
Write-Host "  Stop : Ctrl+C" -ForegroundColor Gray
Write-Host ""

& $PythonExe main.py
