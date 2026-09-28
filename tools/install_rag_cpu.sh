#!/usr/bin/env bash
# 安装 CPU 版 RAG 依赖（Linux / macOS）
#
# 作用：
#   - 卸载可能存在的 CUDA 版 torch，改装 CPU 版 torch
#   - 安装 requirements-rag.txt（sentence-transformers）
#   - 可选清理残留的 nvidia-* / triton 包
#
# 用法：
#   ./tools/install_rag_cpu.sh
set -e

cd "$(dirname "$0")/.."

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "[ERROR] 未找到 .venv/bin/python。请先运行 ./run.sh 创建虚拟环境。" >&2
    exit 1
fi

echo "[1/4] 卸载现有 torch（如有）..."
"$PY" -m pip uninstall -y torch >/dev/null 2>&1 || true

echo "[2/4] 安装 CPU 版 torch ..."
"$PY" -m pip install --upgrade torch --index-url https://download.pytorch.org/whl/cpu

echo "[3/4] 安装 RAG 依赖（sentence-transformers）..."
"$PY" -m pip install -r requirements-rag.txt

echo "[4/4] 清理残留的 nvidia-* / triton（可选）..."
NVIDIA_PKGS=$("$PY" -m pip list --format=freeze 2>/dev/null | sed 's/==.*//' | grep -E '^(nvidia-|triton$)' || true)
if [ -n "$NVIDIA_PKGS" ]; then
    echo "       发现并卸载：$(echo "$NVIDIA_PKGS" | tr '\n' ' ')"
    echo "$NVIDIA_PKGS" | xargs -r "$PY" -m pip uninstall -y >/dev/null 2>&1 || true
else
    echo "       无残留。"
fi

echo ""
echo "[✓] 完成。验证："
"$PY" - <<'PYEOF'
try:
    import torch
    print(f"  torch={torch.__version__}  cuda_available={torch.cuda.is_available()}")
    if torch.version.cuda:
        print("  ⚠️ 仍是 CUDA 版 torch；可重跑本脚本或 pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cpu")
except Exception as e:
    print("  torch 导入失败:", e)
PYEOF
