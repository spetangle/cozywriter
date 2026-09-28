#!/usr/bin/env bash
# CozyWriter 启动脚本（Linux / macOS）
# 用法：./run.sh
#
# 步骤：
#   1) 检查 Python 3.10+，创建/复用 .venv
#   2) 升级 pip
#   3) 安装 requirements.txt
#   4) 启动服务（http://localhost:13567）
set -e

cd "$(dirname "$0")"

echo "========================================"
echo "  CozyWriter - AI 小说 / 剧本编写助手"
echo "========================================"
echo ""

TOTAL=4

# ─── Step 1: virtual environment ───
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

if [ ! -x ".venv/bin/python" ]; then
    echo "       创建虚拟环境（Python $PY_VERSION）..."
    if ! python3 -m venv .venv 2>/tmp/cozywriter_venv_err.log; then
        echo "" >&2
        echo "[ERROR] 创建虚拟环境失败：系统 python3 可能缺少 venv/ensurepip 模块。" >&2
        echo "        解决方式（任选其一）：" >&2
        echo "          1) Ubuntu/Debian: sudo apt install -y python3-venv python3-pip" >&2
        echo "          2) 使用 uv:      uv venv .venv && uv pip install -r requirements.txt" >&2
        echo "          3) 手动创建后重跑本脚本" >&2
        echo "" >&2
        cat /tmp/cozywriter_venv_err.log >&2 || true
        rm -f /tmp/cozywriter_venv_err.log
        exit 1
    fi
    rm -f /tmp/cozywriter_venv_err.log
    echo "       完成。"
else
    echo "       虚拟环境已就绪（Python $PY_VERSION）。"
fi
echo ""

# ─── Step 2: pip upgrade ───
echo "[2/$TOTAL] 升级 pip ..."
.venv/bin/python -m pip install --upgrade pip --disable-pip-version-check --quiet
echo "       完成。"
echo ""

# ─── Step 3: install requirements ───
echo "[3/$TOTAL] 安装/校验依赖（首次运行可能需要几分钟）..."
.venv/bin/python -m pip install -r requirements.txt --disable-pip-version-check
echo "       依赖就绪。"
echo ""

# ─── Step 4: launch server ───
mkdir -p data
echo "[4/$TOTAL] 启动 CozyWriter ..."
echo ""
echo "  地址：http://localhost:13567"
echo "  提示：LLM Provider 在「全局设置 → 服务商」里配置（数据库优先，.env 仅作回退）。"
echo "       opencode 需在服务商里填写 API Key 才可启用；RAG 可选，见 docs/rag_setup.md。"
echo "  停止：Ctrl+C"
echo ""
exec .venv/bin/python main.py
