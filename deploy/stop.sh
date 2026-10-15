#!/usr/bin/env bash
# 城市内涝（积水）水位预测预警系统 · 停止服务
# 用法：./stop.sh
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/app.pid"
PORT="${WL_PORT:-8000}"

stopped=0

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "停止进程 PID=$PID ..."
    kill "$PID" 2>/dev/null || true
    sleep 2
    kill -9 "$PID" 2>/dev/null || true
    stopped=1
  fi
  rm -f "$PID_FILE"
fi

# 兜底：按端口清理残留进程
if command -v fuser >/dev/null 2>&1; then
  if fuser -k "${PORT}/tcp" 2>/dev/null; then
    stopped=1
  fi
elif command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  if [ -n "$PIDS" ]; then
    echo "按端口 $PORT 清理：$PIDS"
    kill $PIDS 2>/dev/null || true
    stopped=1
  fi
fi

if [ "$stopped" -eq 1 ]; then
  echo "服务已停止。"
else
  echo "未发现运行中的服务。"
fi
