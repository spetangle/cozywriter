# 安装 CPU 版 RAG 依赖（PowerShell）
# 用法：.\tools\install_rag_cpu.ps1
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] .venv\Scripts\python.exe not found. Run .\run.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "[1/4] Uninstalling existing torch if any ..." -ForegroundColor Cyan
& $PythonExe -m pip uninstall -y torch 2>&1 | Out-Null

$IndexUrl = if ($env:COZYWRITER_PIP_INDEX) { $env:COZYWRITER_PIP_INDEX }
            elseif ($env:PIP_INDEX_URL) { $env:PIP_INDEX_URL }
            else { "https://pypi.tuna.tsinghua.edu.cn/simple" }
$TorchIndex = if ($env:TORCH_CPU_INDEX) { $env:TORCH_CPU_INDEX } else { "https://download.pytorch.org/whl/cpu" }
$env:PIP_INDEX_URL = $IndexUrl
$env:UV_DEFAULT_INDEX = $IndexUrl
$env:UV_INDEX_URL = $IndexUrl

Write-Host "[2/4] Installing CPU-only torch from $TorchIndex ..." -ForegroundColor Cyan
& $PythonExe -m pip install --upgrade torch --index-url $TorchIndex
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] torch (CPU) install failed." -ForegroundColor Red; exit 1 }

Write-Host "[3/4] Installing RAG dependencies from $IndexUrl ..." -ForegroundColor Cyan
& $PythonExe -m pip install -r requirements-rag.txt
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] requirements-rag.txt install failed." -ForegroundColor Red; exit 1 }

Write-Host "[4/4] Verifying ..." -ForegroundColor Cyan
& $PythonExe -c "import torch; print('  torch=', torch.__version__, ' cuda_available=', torch.cuda.is_available())"

$nvidia = & $PythonExe -m pip list --format=freeze 2>$null | Where-Object { $_ -match '^(nvidia-|triton=)' }
if ($nvidia) {
    Write-Host "Removing leftover CUDA packages:" -ForegroundColor Yellow
    $nvidia | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    $names = $nvidia | ForEach-Object { ($_ -split '==')[0] }
    & $PythonExe -m pip uninstall -y @names 2>&1 | Out-Null
}

Write-Host "[OK] CPU RAG installed." -ForegroundColor Green
