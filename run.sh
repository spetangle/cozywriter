#!/usr/bin/env bash
# CozyWriter 启动脚本（Linux / macOS）
#
# 用法：
#   ./run.sh                # 安装核心依赖并启动
#   ./run.sh --rag          # 额外安装 RAG 依赖（sentence-transformers）
#   ./run.sh --rag-cpu      # 额外安装 CPU 版 RAG（不会装 nvidia-*）
#
# 保证：所有依赖都安装到项目目录内的 .venv，不使用全局 / --user site-packages。
set -e

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"
TOTAL=4

# ─── 解析参数 ───
RAG_MODE=""
for arg in "$@"; do
    case "$arg" in
        --rag) RAG_MODE="rag" ;;
        --rag-cpu) RAG_MODE="rag_cpu" ;;
        -h|--help)
            echo "用法: ./run.sh [--rag|--rag-cpu]"
            exit 0 ;;
    esac
done

echo "========================================"
echo "  CozyWriter - AI 小说 / 剧本编写助手"
echo "========================================"
echo ""

# 防止依赖装到用户级 site-packages
export PIP_USER=0
export PYTHONNOUSERSITE=1
export PIP_REQUIRE_VIRTUALENV=1

# ─── Step 1: 虚拟环境 ───
echo "[1/$TOTAL] 检查 Python 与虚拟环境 .venv ..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] 未找到 python3，请先安装 Python 3.10+。" >&2
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)')
if [ "$PY_OK" != "1" ]; then
    echo "[ERROR] 需要 Python 3.10+，当前为 $PY_VERSION。" >&2
    exit 1
fi

# 跨平台 venv 检测：Windows 创建的 .venv 在 Linux 下不可用
if [ -e ".venv/Scripts/python.exe" ] && [ ! -x ".venv/bin/python" ]; then
    echo "[ERROR] 检测到 Windows 版虚拟环境（.venv/Scripts）。" >&2
    echo "        请在 Windows 运行 run.bat / run.ps1，或删除 .venv 后在 Linux 重跑本脚本。" >&2
    exit 1
fi

# 损坏的 venv：目录在但 python 不可执行
if [ -d ".venv" ] && [ ! -x ".venv/bin/python" ]; then
    echo "       检测到不可用的 .venv，正在重建..."
    rm -rf .venv
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "       创建虚拟环境（Python $PY_VERSION）..."
    if ! python3 -m venv .venv 2>/tmp/cozywriter_venv_err.log; then
        echo "" >&2
        echo "[ERROR] 创建虚拟环境失败：系统 python3 可能缺少 venv/ensurepip 模块。" >&2
        echo "        解决方式（任选其一）：" >&2
        echo "          1) Ubuntu/Debian: sudo apt install -y python3-venv python3-pip" >&2
        echo "          2) 使用 uv:      uv venv .venv && uv pip install -r requirements.txt" >&2
        echo "" >&2
        cat /tmp/cozywriter_venv_err.log >&2 || true
        rm -f /tmp/cozywriter_venv_err.log
        exit 1
    fi
    rm -f /tmp/cozywriter_venv_err.log
fi

PY=".venv/bin/python"

# 校验：venv 必须可用，且位于项目目录内
if ! "$PY" - <<'PYEOF'
import os, sys
prefix = os.path.abspath(sys.prefix)
project = os.path.abspath(os.getcwd())
if not prefix.startswith(project):
    print(f"venv prefix not inside project: {prefix}", file=sys.stderr)
    sys.exit(2)
PYEOF
then
    echo "[ERROR] .venv 校验失败（可能损坏或不在项目目录内）。请删除 .venv 后重试。" >&2
    exit 1
fi
echo "       虚拟环境就绪：$PY_VERSION · $PROJECT_ROOT/.venv"
echo ""

# ─── 选择安装器（venv 内 pip，缺失则用 uv）───
USE_UV=0
if "$PY" -m pip --version >/dev/null 2>&1; then
    :
elif command -v uv >/dev/null 2>&1; then
    USE_UV=1
    echo "       未找到 venv 内 pip，改用 uv 安装到 .venv。"
else
    echo "[ERROR] .venv 内没有 pip，也未找到 uv。请安装 python3-venv 或 uv。" >&2
    exit 1
fi

pip_install() {
    if [ "$USE_UV" = "1" ]; then
        uv pip install --python "$PY" "$@"
    else
        "$PY" -m pip install --no-user --disable-pip-version-check "$@"
    fi
}

# ─── Step 2: pip 升级（静默，失败不阻断）───
echo "[2/$TOTAL] 准备包管理器 ..."
if [ "$USE_UV" = "0" ]; then
    "$PY" -m pip install --upgrade pip --no-user --disable-pip-version-check --quiet || true
fi
echo "       完成。"
echo ""

# ─── Step 3: 安装依赖 ───
echo "[3/$TOTAL] 安装/校验依赖（首次运行可能需要几分钟）..."
pip_install -r requirements.txt

if [ "$RAG_MODE" = "rag_cpu" ]; then
    echo "       安装 CPU 版 RAG 依赖..."
    ./tools/install_rag_cpu.sh
elif [ "$RAG_MODE" = "rag" ]; then
    echo "       安装 RAG 依赖（可能包含 nvidia-* CUDA 包）..."
    pip_install -r requirements-rag.txt
fi
echo "       依赖就绪。"
echo ""

# 校验依赖确实安装在项目内 .venv
"$PY" - <<'PYEOF'
import os, sys
exe = os.path.abspath(sys.executable)
project = os.path.abspath(os.getcwd())
if not exe.startswith(project):
    print(f"[ERROR] 依赖未安装到项目内 .venv：sys.executable={exe}", file=sys.stderr)
    sys.exit(2)
import fastapi  # noqa: F401
sp = [p for p in sys.path if p.endswith("site-packages")]
print(f"       校验通过：{exe}")
if sp:
    print(f"       site-packages: {sp[-1]}")
PYEOF

# ─── Step 4: 启动 ───
mkdir -p data
echo "[4/$TOTAL] 启动 CozyWriter ..."
echo ""
echo "  地址：http://localhost:13567"
echo "  提示：LLM Provider 在「全局设置 → 服务商」里配置（数据库优先，.env 仅作回退）。"
echo "       opencode 需在服务商里填写 API Key 才可启用。"
echo "       RAG：在「全局设置 → RAG 向量」选择本地 CPU 或在线 API（见 docs/rag_setup.md）。"
echo "  停止：Ctrl+C"
echo ""
exec "$PY" main.py
