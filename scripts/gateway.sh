#!/bin/bash
# 坐山客 Gateway 启动/停止/状态脚本
# Usage:
#   bash scripts/gateway.sh start      # 启动 Gateway
#   bash scripts/gateway.sh stop       # 停止 Gateway
#   bash scripts/gateway.sh status     # 查看 Gateway 状态
#   bash scripts/gateway.sh restart    # 重启 Gateway
#   bash scripts/gateway.sh config     # 查看配置状态

cd "$(dirname "$0")/.."  # 回到项目根目录
BACKEND_DIR="$PWD/backend"
PID_FILE="$HOME/.zuoshanke/gateway.pid"
LOG_FILE="$HOME/.zuoshanke/gateway.log"

mkdir -p "$HOME/.zuoshanke"

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "⚠️  Gateway 已在运行 (PID: $(cat "$PID_FILE"))"
        return 1
    fi

    echo "🚀 启动坐山客 Gateway..."
    nohup "$BACKEND_DIR/.venv/bin/python" -m backend.gateway.run \
        >> "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    echo "✅ Gateway 已启动 (PID: $PID)"
    echo "日志: $LOG_FILE"
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "⚠️  PID 文件不存在"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 停止 Gateway (PID: $PID)..."
        kill "$PID" 2>/dev/null
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            echo "强制终止..."
            kill -9 "$PID" 2>/dev/null
        fi
        rm -f "$PID_FILE"
        echo "✅ Gateway 已停止"
    else
        echo "⚠️  Gateway 未运行，清理 PID 文件"
        rm -f "$PID_FILE"
    fi
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        PID=$(cat "$PID_FILE")
        echo "✅ Gateway 运行中 (PID: $PID)"
        echo "日志文件: $LOG_FILE"
        echo "最近日志:"
        tail -5 "$LOG_FILE" 2>/dev/null || echo "(无日志)"
    else
        echo "❌ Gateway 未运行"
        if [ -f "$PID_FILE" ]; then
            echo "   (存在残留 PID 文件)"
        fi
    fi
}

config_status() {
    echo "📋 Gateway 配置状态:"
    if [ -f "$HOME/.zuoshanke/.gateway.env" ]; then
        echo "  配置文件: $HOME/.zuoshanke/.gateway.env ✅"
        grep -v '^#' "$HOME/.zuoshanke/.gateway.env" | grep -v '^$' | while IFS='=' read -r key value; do
            if [ "$key" = "WEIXIN_TOKEN" ]; then
                echo "  WEIXIN_TOKEN: ${value:0:8}...${value: -4}"
            elif [ "$key" = "WEIXIN_ACCOUNT_ID" ]; then
                echo "  WEIXIN_ACCOUNT_ID: ${value:0:8}..."
            else
                echo "  $key: $value"
            fi
        done
    else
        echo "  配置文件: ❌ 不存在"
        echo "  请运行后端 Settings 页面配置，或手动创建:"
        echo "    $HOME/.zuoshanke/.gateway.env"
    fi
}

case "${1:-status}" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 1; start ;;
    status) status ;;
    config) config_status ;;
    *)
        echo "用法: $0 {start|stop|restart|status|config}"
        exit 1
        ;;
esac
