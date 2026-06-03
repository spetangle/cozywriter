#!/bin/bash
set -e
echo "========================================"
echo "  CozyWriter - 小说编写助手"
echo "========================================"
echo ""

# ─── Step 1: virtual environment ───
if [ ! -d ".venv" ]; then
    echo "[1/4] 创建虚拟环境 .venv ..."
    python3 -m venv .venv
    echo "      完成。"
else
    echo "[1/4] 虚拟环境已就绪。"
fi
echo ""

# ─── Step 2: pip upgrade ───
echo "[2/4] 升级 pip ..."
.venv/bin/python -m pip install --upgrade pip --disable-pip-version-check 2>/dev/null
echo "      完成。"
echo ""

# ─── Step 3: install requirements ───
echo "[3/4] 安装依赖（首次运行可能需要几分钟）..."
echo ""
.venv/bin/python -m pip install -r requirements.txt --disable-pip-version-check
echo ""
echo "      所有依赖安装完成。"
echo ""

# ─── Step 4: launch server ───
echo "[4/4] 启动 CozyWriter 服务 ..."
echo "      浏览器打开 http://localhost:13567"
echo "      按 Ctrl+C 停止。"
echo ""
exec .venv/bin/python main.py
