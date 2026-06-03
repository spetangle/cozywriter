# CozyWriter - PowerShell startup script
# Usage: .\run.ps1  (from project root)
#
# Stages:
#   1) Create or reuse .venv
#   2) Upgrade pip (silent)
#   3) Install only missing deps (show progress only for new ones)
#   4) Start server

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

function Write-Step($n, $total, $msg) {
    Write-Host ""
    Write-Host "[$n/$total] $msg" -ForegroundColor Cyan
}

# === Step 1/4: virtual environment ===
Write-Step 1 4 "Checking virtual environment .venv ..."
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "  Creating..." -ForegroundColor Gray
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create venv. Python 3.10+ required." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Done." -ForegroundColor Green
} else {
    Write-Host "  Ready." -ForegroundColor Green
}

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Python not found at $PythonExe" -ForegroundColor Red
    exit 1
}

# === Step 2/4: upgrade pip (silent) ===
Write-Step 2 4 "Upgrading pip ..."
& $PythonExe -m pip install --upgrade pip --disable-pip-version-check --quiet 2>&1 | Out-Null
Write-Host "  Done." -ForegroundColor Green

# === Step 3/4: install deps (only show new) ===
Write-Step 3 4 "Checking dependencies (installed ones auto-skip) ..."
if (-not (Test-Path "requirements.txt")) {
    Write-Host "[ERROR] requirements.txt not found" -ForegroundColor Red
    exit 1
}

# Parse requirements.txt -> list of top-level package names
$requiredPackages = @()
Get-Content "requirements.txt" | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#") -or $line.StartsWith("-")) { return }
    # Take the part before the first version specifier or extras bracket
    $name = ($line -split '[><=!\[]')[0].Trim().ToLower()
    if ($name) { $requiredPackages += $name }
}

# List installed packages (use --format=columns to be robust, but parse JSON when possible)
$installedRaw = & $PythonExe -m pip list --format=json --disable-pip-version-check 2>&1
$installedNames = @()
try {
    $installed = $installedRaw | ConvertFrom-Json
    $installedNames = $installed | ForEach-Object { $_.Name.ToLower() }
} catch {
    Write-Host "  (cannot parse pip list; treating as fresh install)" -ForegroundColor Yellow
}

# Normalize package names: replace _ with - (e.g. some_pkgs vs some-pkgs)
$normalize = { param($n) $n -replace '_', '-' }
$installedNormalized = $installedNames | ForEach-Object { & $normalize $_ }
$requiredNormalized = $requiredPackages | ForEach-Object { & $normalize $_ }

# Diff
$missing = @()
foreach ($pkg in $requiredPackages) {
    $normPkg = & $normalize $pkg
    if (-not ($installedNormalized -contains $normPkg)) {
        $missing += $pkg
    }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "  Will install $($missing.Count) new package(s):" -ForegroundColor Yellow
    foreach ($pkg in $missing) {
        Write-Host "    + $pkg" -ForegroundColor Gray
    }
    Write-Host ""
    foreach ($pkg in $missing) {
        Write-Host "  Installing $pkg ..." -ForegroundColor Cyan
        & $PythonExe -m pip install $pkg --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to install $pkg" -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "  All $($requiredPackages.Count) dependencies ready." -ForegroundColor Green
}

# === Step 4/4: start server ===
Write-Step 4 4 "Starting CozyWriter server ..."
Write-Host "  Open http://localhost:13567 in your browser" -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

& $PythonExe main.py
