#!/usr/bin/env bash
# ── 坐山客一键恢复脚本 ──
# 面向非 IT 用户，一键查看状态、自动修复异常服务
#
# 用法:
#   ./zuoshanke-ctl.sh status       # 查看所有服务状态
#   ./zuoshanke-ctl.sh fix          # 自动检测并修复异常服务
#   ./zuoshanke-ctl.sh restart      # 一键重启所有服务
#   ./zuoshanke-ctl.sh logs         # 查看所有日志
#   ./zuoshanke-ctl.sh logs backend # 查看后端日志

set -euo pipefail

ZUOSHANKE_DIR="$HOME/zuoshanke"
SCRIPTS_DIR="$ZUOSHANKE_DIR/scripts"
BACKEND_PORT=8000
FRONTEND_PORT=5173
QWEEN_PORT=8083

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok()    { echo -e " ${GREEN}✅${NC} $1"; }
log_err()   { echo -e " ${RED}❌${NC} $1"; }
log_warn()  { echo -e " ${YELLOW}⚠${NC}  $1"; }

check_port() { lsof -ti :"$1" >/dev/null 2>&1; }

# ═══════════════════════════════════════════════
#  状态查看
# ═══════════════════════════════════════════════

status() {
    echo ""
    echo "═══════════ 坐山客服务状态 ═══════════"
    echo ""

    # 后端
    if check_port $BACKEND_PORT; then
        local pid=$(lsof -ti :$BACKEND_PORT 2>/dev/null)
        if curl -sf http://localhost:$BACKEND_PORT/api/channels >/dev/null 2>&1; then
            log_ok "后端 :$BACKEND_PORT (PID: $pid) — API 正常"
        else
            log_warn "后端 :$BACKEND_PORT (PID: $pid) — API 无响应"
        fi
    else
        log_err "后端 :$BACKEND_PORT — 未运行"
    fi

    # 前端
    if check_port $FRONTEND_PORT; then
        local pid=$(lsof -ti :$FRONTEND_PORT 2>/dev/null)
        log_ok "前端 :$FRONTEND_PORT (PID: $pid)"
    else
        log_err "前端 :$FRONTEND_PORT — 未运行"
    fi

    # Qwen LLM
    if check_port $QWEEN_PORT; then
        log_ok "Qwen LLM :$QWEEN_PORT"
    else
        log_warn "Qwen LLM :$QWEEN_PORT — 未运行"
    fi

    # Uptime Kuma 监控面板
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q uptime-kuma; then
        log_ok "Uptime Kuma 监控面板 — 运行中 (http://localhost:3001)"
    else
        log_warn "Uptime Kuma 监控面板 — 未运行"
    fi

    echo ""
    echo "═══════════════════════════════════════"
    echo ""
}

# ═══════════════════════════════════════════════
#  一键修复（自动检测异常服务并重启）
# ═══════════════════════════════════════════════

fix() {
    echo ""
    echo "🔍 检测异常服务..."
    echo ""
    local fixed=0

    # 后端
    if ! check_port $BACKEND_PORT; then
        log_warn "后端异常，正在重启..."
        bash "$SCRIPTS_DIR/start-zuoshanke.sh" backend && fixed=$((fixed+1))
    else
        log_ok "后端正常"
    fi

    # 前端
    if ! check_port $FRONTEND_PORT; then
        log_warn "前端异常，正在重启..."
        bash "$SCRIPTS_DIR/start-zuoshanke.sh" frontend && fixed=$((fixed+1))
    else
        log_ok "前端正常"
    fi

    # Uptime Kuma
    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q uptime-kuma; then
        log_warn "Uptime Kuma 异常，正在重启..."
        docker start uptime-kuma 2>/dev/null || \
        docker run -d --restart=always -p 3001:3001 -v uptime-kuma:/app/data --name uptime-kuma louislam/uptime-kuma:latest && \
        fixed=$((fixed+1))
    else
        log_ok "Uptime Kuma 正常"
    fi

    echo ""
    if [ $fixed -eq 0 ]; then
        log_ok "所有服务运行正常，无需修复 🎉"
    else
        log_ok "已修复 $fixed 个异常服务"
    fi
    echo ""
    status
}

# ═══════════════════════════════════════════════
#  查看日志
# ═══════════════════════════════════════════════

logs() {
    local service="${1:-all}"
    case "$service" in
        backend)
            echo "═══ 后端日志 (最后 50 行) ═══"
            tail -50 /tmp/zuoshanke-backend.log 2>/dev/null || echo "(日志文件不存在)"
            ;;
        frontend)
            echo "═══ 前端日志 (最后 50 行) ═══"
            tail -50 /tmp/zuoshanke-frontend.log 2>/dev/null || echo "(日志文件不存在)"
            ;;
        kuma)
            echo "═══ Uptime Kuma 日志 (最后 50 行) ═══"
            docker logs --tail 50 uptime-kuma 2>/dev/null || echo "(Uptime Kuma 未运行)"
            ;;
        all)
            echo "═══ 后端日志 ═══"
            tail -20 /tmp/zuoshanke-backend.log 2>/dev/null || echo "(无)"
            echo ""
            echo "═══ 前端日志 ═══"
            tail -20 /tmp/zuoshanke-frontend.log 2>/dev/null || echo "(无)"
            echo ""
            echo "═══ Uptime Kuma 日志 ═══"
            docker logs --tail 20 uptime-kuma 2>/dev/null || echo "(Uptime Kuma 未运行)"
            ;;
        *)
    echo "  $0 logs {backend|frontend|kuma|all}"
            exit 1
            ;;
    esac
}

# ═══════════════════════════════════════════════
#  帮助
# ═══════════════════════════════════════════════

usage() {
    echo "坐山客一键恢复工具"
    echo ""
    echo "用法:"
    echo "  $0 status       查看所有服务状态"
    echo "  $0 fix          自动检测并修复异常服务"
    echo "  $0 restart      一键重启所有服务"
    echo "  $0 logs         查看所有日志"
    echo "  $0 logs backend 查看后端日志"
    echo ""
    echo "示例:"
    echo "  $0 status       # 看看哪个服务挂了"
    echo "  $0 fix          # 自动修好"
}

# ═══════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════

case "${1:-help}" in
    status)
        status
        ;;
    fix)
        fix
        ;;
    restart)
        echo ""
        echo "🔄 一键重启所有服务..."
        bash "$SCRIPTS_DIR/start-zuoshanke.sh" restart
        echo ""
        status
        ;;
    logs)
        logs "${2:-all}"
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "未知命令: $1"
        echo ""
        usage
        exit 1
        ;;
esac
