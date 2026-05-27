#!/usr/bin/env bash
# ── 启动坐山客（zuoshanke）全套服务 ──
# 用法:
#   start-zuoshanke.sh              # 启动全部（后端 + 前端）
#   start-zuoshanke.sh backend      # 仅启动后端
#   start-zuoshanke.sh frontend     # 仅启动前端
#   start-zuoshanke.sh gateway      # 仅启动 Hermes 消息网关
#   start-zuoshanke.sh all          # 同上，全部启动
#   start-zuoshanke.sh stop         # 停掉全部
#   start-zuoshanke.sh status       # 查看运行状态

set -euo pipefail

ZUOSHANKE_DIR="$HOME/zuoshanke"
BACKEND_DIR="$ZUOSHANKE_DIR/backend"
FRONTEND_DIR="$ZUOSHANKE_DIR/frontend"
BACKEND_PORT=8000
FRONTEND_PORT=5173

# ── pnpm 不在默认 PATH ──
PNPM="$HOME/.hermes/node/bin/pnpm"

# ── 颜色 ──
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e " ${GREEN}ℹ${NC}  $1"; }
log_ok()    { echo -e " ${GREEN}✅${NC} $1"; }
log_err()   { echo -e " ${RED}❌${NC} $1"; }
log_warn()  { echo -e " ${YELLOW}⚠${NC}  $1"; }

# ── 日志文件 ──
BACKEND_LOG="/tmp/zuoshanke-backend.log"
FRONTEND_LOG="/tmp/zuoshanke-frontend.log"
GATEWAY_LOG="/tmp/zuoshanke-gateway.log"

# ═══════════════════════════════════════════════
#  检查 & 停止
# ═══════════════════════════════════════════════

stop_service() {
    local name="$1" port="$2" pid_var="$3"
    local pids
    pids=$(pgrep -f "$port" 2>/dev/null || true)
    if [ -z "$pids" ]; then
        pids=$(lsof -ti :"$port" 2>/dev/null || true)
    fi
    if [ -n "$pids" ]; then
        log_warn "停掉 $name (PID: $(echo $pids | tr '\n' ' '))..."
        kill $pids 2>/dev/null || true
        sleep 1
        if lsof -ti :"$port" >/dev/null 2>&1; then
            log_warn "  强制终止..."
            kill -9 $pids 2>/dev/null || true
            sleep 1
        fi
        log_ok "$name 已停止"
    fi
}

stop_gateway() {
    if ps -p "$GATEWAY_PID" >/dev/null 2>&1; then
        log_warn "停掉 Gateway..."
        python3 -m hermes_cli.main gateway stop 2>/dev/null || true
        kill "$GATEWAY_PID" 2>/dev/null || true
        sleep 1
        log_ok "Gateway 已停止"
    fi
}

stop_all() {
    stop_service "后端" "$BACKEND_PORT" ""
    stop_service "前端" "$FRONTEND_PORT" ""
    stop_gateway
    log_ok "全部服务已停止"
}

# ═══════════════════════════════════════════════
#  状态检查
# ═══════════════════════════════════════════════

check_port() {
    lsof -ti :"$1" >/dev/null 2>&1
}

status() {
    echo ""
    echo "═══ 坐山客服务状态 ═══"
    echo ""

    # 后端
    if check_port "$BACKEND_PORT"; then
        local pid=$(lsof -ti :$BACKEND_PORT 2>/dev/null)
        log_ok "后端 http://localhost:$BACKEND_PORT (PID: $pid)"
        if curl -sf http://localhost:$BACKEND_PORT/api/channels >/dev/null 2>&1; then
            echo "   └─ API 正常"
        else
            log_warn "   └─ API 无响应"
        fi
    else
        log_err "后端 :$BACKEND_PORT — 未运行"
    fi

    # 前端
    if check_port "$FRONTEND_PORT"; then
        local pid=$(lsof -ti :$FRONTEND_PORT 2>/dev/null)
        log_ok "前端 http://localhost:$FRONTEND_PORT (PID: $pid)"
    else
        log_err "前端 :$FRONTEND_PORT — 未运行"
    fi

    # Gateway (Hermes)
    if pgrep -f "hermes_cli.*gateway" >/dev/null 2>&1; then
        local pid=$(pgrep -f "hermes_cli.*gateway" 2>/dev/null | head -1)
        log_ok "Gateway (PID: $pid)"
    else
        log_err "Gateway — 未运行"
    fi

    # Qwen LLM
    if check_port 8083; then
        log_ok "Qwen LLM :8083"
    else
        log_warn "Qwen LLM :8083 — 未运行（用 start-qwen.sh 启动）"
    fi
}

# ═══════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════

start_backend() {
    echo ""
    echo "🚀 启动后端 http://localhost:$BACKEND_PORT ..."

    # 检查目录
    if [ ! -d "$BACKEND_DIR" ]; then
        log_err "后端目录不存在: $BACKEND_DIR"
        exit 1
    fi
    if [ ! -f "$BACKEND_DIR/.venv/bin/python" ]; then
        log_err "虚拟环境不存在: $BACKEND_DIR/.venv"
        exit 1
    fi

    cd "$BACKEND_DIR"
    nohup .venv/bin/python main.py > "$BACKEND_LOG" 2>&1 &
    local pid=$!
    log_info "PID: $pid，日志: $BACKEND_LOG"

    # 等待启动（最多 15 秒）
    for i in $(seq 1 15); do
        sleep 1
        if curl -sf http://localhost:$BACKEND_PORT/api/channels >/dev/null 2>&1; then
            log_ok "后端启动成功（${i}s）"
            return 0
        fi
    done

    log_err "后端启动超时，日志最后 10 行:"
    tail -10 "$BACKEND_LOG" 2>/dev/null
    return 1
}

start_frontend() {
    echo ""
    echo "🚀 启动前端 http://localhost:$FRONTEND_PORT ..."

    if [ ! -d "$FRONTEND_DIR" ]; then
        log_err "前端目录不存在: $FRONTEND_DIR"
        exit 1
    fi
    if [ ! -f "$PNPM" ]; then
        log_err "pnpm 不存在: $PNPM"
        exit 1
    fi

    cd "$FRONTEND_DIR"
    nohup node ./node_modules/vite/bin/vite.js --host 0.0.0.0 > "$FRONTEND_LOG" 2>&1 &
    local pid=$!
    log_info "PID: $pid，日志: $FRONTEND_LOG"

    # 等待启动（最多 30 秒，Vite 编译慢）
    for i in $(seq 1 30); do
        sleep 1
        if check_port "$FRONTEND_PORT"; then
            log_ok "前端启动成功（${i}s）"
            return 0
        fi
    done

    log_err "前端启动超时，日志最后 10 行:"
    tail -10 "$FRONTEND_LOG" 2>/dev/null
    return 1
}

start_gateway() {
    echo ""
    echo "🚀 启动 Hermes Gateway ..."

    if pgrep -f "hermes_cli.*gateway" >/dev/null 2>&1; then
        log_warn "Gateway 已在运行"
        return 0
    fi

    nohup python3 -m hermes_cli.main gateway run --replace > "$GATEWAY_LOG" 2>&1 &
    local pid=$!
    log_info "PID: $pid，日志: $GATEWAY_LOG"

    # 等待启动（最多 10 秒）
    for i in $(seq 1 10); do
        sleep 1
        if pgrep -f "hermes_cli.*gateway" >/dev/null 2>&1; then
            log_ok "Gateway 启动成功（${i}s）"
            return 0
        fi
    done

    log_err "Gateway 启动失败，日志:"
    tail -5 "$GATEWAY_LOG" 2>/dev/null
    return 1
}

# ═══════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════

case "${1:-all}" in
    stop)
        stop_all
        exit 0
        ;;
    status)
        status
        exit 0
        ;;
    restart)
        stop_all
        sleep 2
        exec "$0" "${2:-all}"
        ;;
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    gateway)
        start_gateway
        ;;
    all|"")
        start_backend
        start_frontend
        start_gateway
        echo ""
        log_ok "全部服务启动完成"
        echo ""
        status
        ;;
    *)
        echo "用法: $0 {all|backend|frontend|gateway|stop|status|restart}"
        echo ""
        echo "  all        启动全部（后端 + 前端 + Gateway）"
        echo "  backend    仅后端"
        echo "  frontend   仅前端"
        echo "  gateway    仅消息网关"
        echo "  stop       全部停止"
        echo "  status     查看状态"
        echo "  restart    全部重启"
        exit 1
        ;;
esac
