# CozyWriter - PowerShell startup script
# Usage: .\run.ps1    (from project root)
#
# Stages:
#   1) Check Python 3.10+ and create/reuse .venv
#   2) Upgrade pip (silent)
#   3) Install requirements (progress for new packages only)
#   4) Start server at http://localhost:13567

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

function Write-Step($n, $total, $msg) {
    Write-Host ""
    Write-Host "[$n/$total] $msg" -ForegroundColor Cyan
}

function Fail($msg) {
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    exit 1
}

# === Step 1/4: Python + virtual environment ===
Write-Step 1 4 "Checking Python and virtual environment .venv ..."
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { $pythonCmd = Get-Command py -ErrorAction SilentlyContinue }
if (-not $pythonCmd) { Fail "Python not found on PATH. Please install Python 3.10+." }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "  Creating virtual environment ..." -ForegroundColor Gray
    & $pythonCmd.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create venv. Python 3.10+ required." }
    Write-Host "  Done." -ForegroundColor Green
} else {
    Write-Host "  Ready." -ForegroundColor Green
}

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) { Fail "Python not found at $PythonExe" }

# === Step 2/4: upgrade pip (silent) ===
Write-Step 2 4 "Upgrading pip ..."
& $PythonExe -m pip install --upgrade pip --disable-pip-version-check --quiet 2>&1 | Out-Null
Write-Host "  Done." -ForegroundColor Green

# === Step 3/4: install deps (only show new) ===
Write-Step 3 4 "Checking dependencies (installed ones auto-skip) ..."
if (-not (Test-Path "requirements.txt")) { Fail "requirements.txt not found" }

# Parse requirements.txt -> top-level package names
$requiredPackages = @()
Get-Content "requirements.txt" | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#") -or $line.StartsWith("-")) { return }
    $name = ($line -split '[><=!\[]')[0].Trim().ToLower()
    if ($name) { $requiredPackages += $name }
}

$installedRaw = & $PythonExe -m pip list --format=json --disable-pip-version-check 2>&1
$installedNames = @()
try {
    $installed = $installedRaw | ConvertFrom-Json
    $installedNames = $installed | ForEach-Object { $_.Name.ToLower() }
} catch {
    Write-Host "  (cannot parse pip list; treating as fresh install)" -ForegroundColor Yellow
}

$normalize = { param($n) $n -replace '_', '-' }
$installedNormalized = $installedNames | ForEach-Object { & $normalize $_ }

$missing = @()
foreach ($pkg in $requiredPackages) {
    $normPkg = & $normalize $pkg
    if (-not ($installedNormalized -contains $normPkg)) { $missing += $pkg }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "  Will install $($missing.Count) new package(s):" -ForegroundColor Yellow
    foreach ($pkg in $missing) { Write-Host "    + $pkg" -ForegroundColor Gray }
    Write-Host ""
    foreach ($pkg in $missing) {
        Write-Host "  Installing $pkg ..." -ForegroundColor Cyan
        & $PythonExe -m pip install $pkg --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) { Fail "Failed to install $pkg" }
    }
} else {
    Write-Host "  All $($requiredPackages.Count) dependencies ready." -ForegroundColor Green
}

# === Step 4/4: start server ===
if (-not (Test-Path "data")) { New-Item -ItemType Directory -Path "data" | Out-Null }
Write-Step 4 4 "Starting CozyWriter ..."
Write-Host "  URL  : http://localhost:13567" -ForegroundColor Green
Write-Host "  Hint : configure LLM provider in 'Settings - Providers' (DB first; .env is fallback)." -ForegroundColor Gray
Write-Host "         opencode needs an API key to enable; RAG is optional, see docs/rag_setup.md." -ForegroundColor Gray
Write-Host "  Stop : Ctrl+C" -ForegroundColor Gray
Write-Host ""

& $PythonExe main.py
