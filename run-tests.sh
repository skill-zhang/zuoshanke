#!/usr/bin/env bash
# 坐山客测试环境 — 一键运行脚本
#
# 用法:
#   bash run-tests.sh          # 跑全部测试
#   bash run-tests.sh server   # 只启动测试服务器（后端9001 + 前端9002）
#   bash run-tests.sh py       # 只跑后端 pytest
#   bash run-tests.sh js       # 只跑前端 vitest
#   bash run-tests.sh e2e      # 只跑 Playwright E2E
#   bash run-tests.sh stop     # 停止测试服务器
#

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV="$BACKEND_DIR/.venv-test"
PID_FILE="/tmp/zuoshanke-test-server.pids"

# 检查 venv
if [ ! -f "$VENV/bin/python3" ]; then
    echo "❌ 未找到测试 venv，请先运行: cd backend && python3 -m venv .venv-test && .venv-test/bin/pip install -r requirements.txt pytest httpx pytest-asyncio requests python-multipart"
    exit 1
fi

start_server() {
    echo "🚀 启动测试环境后端 (端口 9001)..."
    cd "$BACKEND_DIR"
    ZUOSHANKE_REBUILD_DB=1 "$VENV/bin/python3" main.py &
    BACKEND_PID=$!
    echo "  后端 PID: $BACKEND_PID"

    echo "🚀 启动测试环境前端 (端口 9002)..."
    cd "$FRONTEND_DIR"
    export PATH="$PATH:$HOME/.hermes/node/bin"
    npx vite --port 9002 &
    FRONTEND_PID=$!
    echo "  前端 PID: $FRONTEND_PID"

    echo "$BACKEND_PID" > "$PID_FILE"
    echo "$FRONTEND_PID" >> "$PID_FILE"

    # 等待后端就绪
    echo "⏳ 等待后端就绪..."
    for i in $(seq 1 30); do
        if curl -s http://localhost:9001/api/health > /dev/null 2>&1; then
            echo "✅ 后端就绪 (http://localhost:9001)"
            break
        fi
        sleep 1
    done

    # 等待前端就绪
    echo "⏳ 等待前端就绪..."
    for i in $(seq 1 30); do
        if curl -s http://localhost:9002/ > /dev/null 2>&1; then
            echo "✅ 前端就绪 (http://localhost:9002)"
            break
        fi
        sleep 1
    done

    echo "✅ 测试环境已启动"
}

stop_server() {
    if [ -f "$PID_FILE" ]; then
        echo "🛑 停止测试环境..."
        while read -r pid; do
            kill "$pid" 2>/dev/null && echo "  已停止 PID $pid" || true
        done < "$PID_FILE"
        rm -f "$PID_FILE"
        echo "✅ 已停止"
    else
        echo "ℹ️  没有运行中的测试服务器"
    fi
}

run_py() {
    echo "🧪 运行后端单元测试（TestClient，无需服务器）..."
    cd "$BACKEND_DIR"
    ZUOSHANKE_REBUILD_DB=1 "$VENV/bin/pytest" tests/ -v --tb=short -m "not server" "$@"
}

run_py_all() {
    echo "🧪 运行后端全部测试（含需服务器集成测试）..."
    cd "$BACKEND_DIR"
    ZUOSHANKE_REBUILD_DB=1 "$VENV/bin/pytest" tests/ -v --tb=short "$@"
}

run_js() {
    echo "🧪 运行前端 vitest..."
    cd "$FRONTEND_DIR"
    export PATH="$PATH:$HOME/.hermes/node/bin"
    npx vitest run --config vitest.config.ts "$@"
}

run_e2e() {
    echo "🧪 运行 Playwright E2E 测试..."
    cd "$FRONTEND_DIR"
    export PATH="$PATH:$HOME/.hermes/node/bin"
    npx playwright test "$@"
}

# Main
case "${1:-all}" in
    server)
        start_server
        ;;
    stop)
        stop_server
        ;;
    py)
        shift 2>/dev/null || true
        run_py "$@"
        ;;
    js)
        shift 2>/dev/null || true
        run_js "$@"
        ;;
    e2e)
        shift 2>/dev/null || true
        run_e2e "$@"
        ;;
    all)
        echo "═══════════════════════════════════════"
        echo "  坐山客测试环境 — 全部测试"
        echo "═══════════════════════════════════════"
        
        # 后端测试
        run_py
        PY_EXIT=$?
        
        echo ""
        
        # 前端测试
        run_js
        JS_EXIT=$?
        
        # 汇总
        echo ""
        echo "═══════════════════════════════════════"
        echo "  测试汇总"
        echo "═══════════════════════════════════════"
        [ $PY_EXIT -eq 0 ] && echo "  ✅ 后端 pytest: 通过" || echo "  ❌ 后端 pytest: 失败 ($PY_EXIT)"
        [ $JS_EXIT -eq 0 ] && echo "  ✅ 前端 vitest: 通过" || echo "  ❌ 前端 vitest: 失败 ($JS_EXIT)"
        
        # 汇总退出码
        if [ $PY_EXIT -eq 0 ] && [ $JS_EXIT -eq 0 ]; then
            echo ""
            echo "🎉 全部测试通过"
            exit 0
        else
            echo ""
            echo "❌ 有测试失败"
            exit 1
        fi
        ;;
    *)
        echo "用法: bash run-tests.sh [server|stop|py|js|e2e|all]"
        exit 1
        ;;
esac
