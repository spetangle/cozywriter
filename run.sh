#!/bin/bash
echo "========================================"
echo "  CozyWriter - 小说编写助手"
echo "========================================"
echo ""

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "[INFO] 正在创建虚拟环境..."
    python -m venv .venv
fi

echo "[INFO] 安装依赖（如需要）..."
.venv/bin/pip install -r requirements.txt > /dev/null 2>&1

echo "[INFO] 启动服务..."
echo "[INFO] 访问 http://localhost:8000"
echo ""

.venv/bin/python main.py
