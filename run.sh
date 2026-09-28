#!/usr/bin/env bash
# CozyWriter 启动脚本（Linux / macOS）
#
# 用法：
#   ./run.sh                     # 安装核心依赖并启动（默认国内镜像）
#   ./run.sh --official          # 使用 PyPI 官方源
#   ./run.sh --mirror aliyun     # 使用阿里云镜像
#   ./run.sh --index-url URL     # 自定义源
#   ./run.sh --rag               # 额外安装 RAG 依赖（可能带 nvidia-*）
#   ./run.sh --rag-cpu           # 额外安装 CPU 版 RAG（不装 nvidia-*）
#
# 镜像也可以通过环境变量或 .env 覆盖：
#   COZYWRITER_PIP_INDEX / PIP_INDEX_URL / UV_INDEX_URL
#
# 保证：所有依赖都安装到项目目录内的 .venv。
set -e

# 即使用 `sh run.sh` 调用也切换到 bash，避免 dash 兼容问题
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"
TOTAL=4

TUNA="https://pypi.tuna.tsinghua.edu.cn/simple"
ALIYUN="https://mirrors.aliyun.com/pypi/simple/"
OFFICIAL="https://pypi.org/simple"

# ─── 解析参数 ───
RAG_MODE=""
INDEX_URL=""
INDEX_EXPLICIT=0
USE_OFFICIAL=0

show_help() {
    echo "用法: ./run.sh [--official | --mirror tuna|aliyun | --index-url URL] [--rag | --rag-cpu]"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --rag) RAG_MODE="rag" ;;
        --rag-cpu) RAG_MODE="rag_cpu" ;;
        --official) USE_OFFICIAL=1; INDEX_URL="$OFFICIAL"; INDEX_EXPLICIT=1 ;;
        --mirror)
            shift
            case "${1:-}" in
                tuna|tsinghua|cn) INDEX_URL="$TUNA" ;;
                aliyun) INDEX_URL="$ALIYUN" ;;
                official|pypi) INDEX_URL="$OFFICIAL" ;;
                "") echo "[ERROR] --mirror 需要一个值（tuna/aliyun）" >&2; exit 1 ;;
                *) INDEX_URL="$1" ;;
            esac
            INDEX_EXPLICIT=1 ;;
        --mirror=*)
            val="${1#--mirror=}"
            case "$val" in
                tuna|tsinghua|cn) INDEX_URL="$TUNA" ;;
                aliyun) INDEX_URL="$ALIYUN" ;;
                official|pypi) INDEX_URL="$OFFICIAL" ;;
                *) INDEX_URL="$val" ;;
            esac
            INDEX_EXPLICIT=1 ;;
        --index-url)
            shift
            if [ -z "${1:-}" ]; then echo "[ERROR] --index-url 需要一个 URL" >&2; exit 1; fi
            INDEX_URL="$1"; INDEX_EXPLICIT=1 ;;
        --index-url=*) INDEX_URL="${1#--index-url=}"; INDEX_EXPLICIT=1 ;;
        -h|--help) show_help; exit 0 ;;
        *) echo "[WARN] 忽略未知参数: $1" >&2 ;;
    esac
    shift
done

# ─── 解析镜像优先级：CLI > 环境变量 > .env > 默认(清华) ───
if [ "$INDEX_EXPLICIT" != "1" ]; then
    if [ -n "${COZYWRITER_PIP_INDEX:-}" ]; then
        INDEX_URL="$COZYWRITER_PIP_INDEX"
    elif [ -n "${PIP_INDEX_URL:-}" ]; then
        INDEX_URL="$PIP_INDEX_URL"
    elif [ -n "${UV_INDEX_URL:-}" ]; then
        INDEX_URL="$UV_INDEX_URL"
    elif [ -f ".env" ]; then
        env_index="$(grep -E '^(COZYWRITER_PIP_INDEX|PIP_INDEX_URL)=' .env | tail -1 | cut -d= -f2- | tr -d '\r' | xargs 2>/dev/null || true)"
        if [ -n "$env_index" ]; then INDEX_URL="$env_index"; fi
    fi
fi
if [ -z "$INDEX_URL" ]; then
    INDEX_URL="$TUNA"   # 默认国内镜像，避免 pypi.org 超时
fi
# 未显式指定时，失败后回退到清华镜像
FALLBACK_INDEX=""
if [ "$INDEX_EXPLICIT" != "1" ] && [ "$INDEX_URL" != "$TUNA" ]; then
    FALLBACK_INDEX="$TUNA"
fi

export PIP_INDEX_URL="$INDEX_URL"
export UV_DEFAULT_INDEX="$INDEX_URL"
export UV_INDEX_URL="$INDEX_URL"

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
echo "       依赖源：$INDEX_URL"
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

# 带镜像回退的安装：先用当前源，失败则尝试 FALLBACK_INDEX
install_with_fallback() {
    if pip_install "$@"; then
        return 0
    fi
    if [ -n "$FALLBACK_INDEX" ]; then
        echo ""
        echo "       [!] 当前源安装失败，改用镜像重试：$FALLBACK_INDEX"
        export PIP_INDEX_URL="$FALLBACK_INDEX" UV_DEFAULT_INDEX="$FALLBACK_INDEX" UV_INDEX_URL="$FALLBACK_INDEX"
        pip_install "$@"
    else
        return 1
    fi
}

# ─── Step 2: pip 升级（静默，失败不阻断）───
echo "[2/$TOTAL] 准备包管理器 ..."
if [ "$USE_UV" = "0" ]; then
    install_with_fallback --upgrade pip --quiet || true
fi
echo "       完成。"
echo ""

# ─── Step 3: 安装依赖 ───
echo "[3/$TOTAL] 安装/校验依赖（首次运行可能需要几分钟）..."
install_with_fallback -r requirements.txt

if [ "$RAG_MODE" = "rag_cpu" ]; then
    echo "       安装 CPU 版 RAG 依赖..."
    ./tools/install_rag_cpu.sh
elif [ "$RAG_MODE" = "rag" ]; then
    echo "       安装 RAG 依赖（可能包含 nvidia-* CUDA 包）..."
    install_with_fallback -r requirements-rag.txt
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
