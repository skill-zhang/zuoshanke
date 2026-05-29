#!/usr/bin/env bash
# 坐山客 · 个人工作台启动脚本
# 启动独立后端 (:8001) 和独立前端 (:5174)

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$DIR/backend"
FRONTEND_DIR="$DIR/frontend"

echo "🚀 启动工作台沙箱..."

# 使用主项目的 venv（已有 SQLAlchemy 2.x + uvicorn）
VENV_PYTHON="$DIR/../backend/venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
  VENV_PYTHON="$DIR/../backend/.venv/bin/python"
fi
if [ ! -f "$VENV_PYTHON" ]; then
  echo "⚠️  未找到 venv Python，尝试系统 Python"
  VENV_PYTHON="python3"
fi

PID_DIR="$DIR/../logs"
mkdir -p "$PID_DIR"

# 1. 启动后端
echo "  → 启动后端 :8001"
cd "$BACKEND_DIR"
$VENV_PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8001 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_DIR/workbench-backend.pid"
echo "    PID: $BACKEND_PID"

# 等后端就绪
for i in $(seq 1 10); do
  sleep 0.5
  if curl -s http://localhost:8001/api/health >/dev/null 2>&1; then
    echo "    ✅ 后端就绪"
    break
  fi
done

# 2. 启动前端
echo "  → 启动前端 :5174"
cd "$FRONTEND_DIR"
npx vite --host 0.0.0.0 --port 5174 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$PID_DIR/workbench-frontend.pid"
echo "    PID: $FRONTEND_PID"

echo ""
echo "✅ 工作台已启动："
echo "   后端  → http://localhost:8001"
echo "   前端  → http://localhost:5174"
echo ""
echo "   停止：bash $DIR/scripts/stop.sh"

wait
