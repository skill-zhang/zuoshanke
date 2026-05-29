#!/usr/bin/env bash
# 坐山客 · 个人工作台停止脚本

PID_DIR="$(cd "$(dirname "$0")/../.." && pwd)/logs"

echo "🛑 停止工作台..."

if [ -f "$PID_DIR/workbench-backend.pid" ]; then
  PID=$(cat "$PID_DIR/workbench-backend.pid")
  kill "$PID" 2>/dev/null && echo "  → 后端进程 $PID 已停止" || echo "  → 后端进程 $PID 未运行"
  rm -f "$PID_DIR/workbench-backend.pid"
fi

if [ -f "$PID_DIR/workbench-frontend.pid" ]; then
  PID=$(cat "$PID_DIR/workbench-frontend.pid")
  kill "$PID" 2>/dev/null && echo "  → 前端进程 $PID 已停止" || echo "  → 前端进程 $PID 未运行"
  rm -f "$PID_DIR/workbench-frontend.pid"
fi

echo "✅ 工作台已停止"
