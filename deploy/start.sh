#!/usr/bin/env bash
# 城市内涝（积水）水位预测预警系统 · 一键启动（Linux 单端口）
# 用法：./start.sh            （默认 0.0.0.0:8000）
#       WL_PORT=9000 ./start.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${WL_HOST:-0.0.0.0}"
PORT="${WL_PORT:-8000}"

echo "[1/5] 检查 Python（需 >= 3.11）..."
"$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "错误：Python 版本过低，需要 3.11+（当前 $("$PYTHON_BIN" -V)）"; exit 1; }

echo "[2/5] 准备虚拟环境..."
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
fi
# shellcheck disable=SC1091
source "$BACKEND_DIR/.venv/bin/activate"
pip install --quiet --upgrade pip
echo "[3/5] 安装依赖（极简清单，无编译依赖）..."
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

echo "[4/5] 检查前端构建产物与模拟数据..."
if [ ! -f "$PROJECT_ROOT/frontend/dist/index.html" ]; then
  echo "警告：frontend/dist/index.html 不存在——服务将以纯 API 模式启动。"
  echo "      请在开发机上执行 frontend 的 npm install && npm run build 后一并上传 dist/。"
fi
cd "$BACKEND_DIR"
if [ ! -f data/app.db ] || [ -z "$(ls data/parquet/station_*.parquet 2>/dev/null || true)" ]; then
  echo "      生成模拟数据（SQLite + Parquet）..."
  python scripts/generate_demo_data.py
fi

echo "[5/5] 启动服务：http://${HOST}:${PORT}/ （API: /api/v1，文档: /docs）"
echo $$ > "$SCRIPT_DIR/app.pid"
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
