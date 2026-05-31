#!/usr/bin/env bash
# ── 启动坐山客（zuoshanke）全套服务 ──
# 用法:
#   start-zuoshanke.sh              # 启动全部（后端 + 前端）
#   start-zuoshanke.sh backend      # 仅启动后端
#   start-zuoshanke.sh frontend     # 仅启动前端
#   start-zuoshanke.sh all          # 同上，全部启动
#   start-zuoshanke.sh stop         # 停掉全部
#   start-zuoshanke.sh status       # 查看运行状态
#   start-zuoshanke.sh install-deps # 仅安装所有依赖

set -euo pipefail

ZUOSHANKE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ZUOSHANKE_DIR/backend"
FRONTEND_DIR="$ZUOSHANKE_DIR/frontend"
BACKEND_PORT=8000
FRONTEND_PORT=5173

# ── 颜色 ──
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e " ${GREEN}ℹ${NC}  $1"; }
log_ok()    { echo -e " ${GREEN}✅${NC} $1"; }
log_err()   { echo -e " ${RED}❌${NC} $1"; }
log_warn()  { echo -e " ${YELLOW}⚠${NC}  $1"; }
log_cmd()   { echo -e " ${CYAN}→${NC}  $1"; }

# ── 日志文件 ──
BACKEND_LOG="/tmp/zuoshanke-backend.log"
FRONTEND_LOG="/tmp/zuoshanke-frontend.log"

# ═══════════════════════════════════════════════
#  检测操作系统
# ═══════════════════════════════════════════════

detect_os() {
    case "$(uname -s)" in
        Darwin*)  echo "macos" ;;
        Linux*)   echo "linux" ;;
        *)        echo "$(uname -s)" ;;
    esac
}

# ═══════════════════════════════════════════════
#  依赖检查 & 安装引导（一键自动化）
# ═══════════════════════════════════════════════

check_nodejs() {
    if command -v node &>/dev/null; then
        return 0
    fi
    log_warn "Node.js 未安装"
    local os
    os=$(detect_os)
    if [ "$os" = "macos" ]; then
        echo ""
        echo "   建议自动安装："
        log_cmd "请在新开的终端中执行："
        echo ""
        echo '      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        echo '      echo '\''eval "$(/opt/homebrew/bin/brew shellenv)"'\'' >> ~/.zshrc'
        echo '      source ~/.zshrc'
        echo '      brew install node'
        echo ""
        echo "   或手动下载: https://nodejs.org (选择 LTS 版本)"
        echo ""
        return 1
    else
        echo ""
        echo "   建议自动安装："
        log_cmd "Ubuntu/Debian:"
        echo '      curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -'
        echo '      sudo apt-get install -y nodejs'
        echo ""
        log_cmd "CentOS/RHEL:"
        echo '      curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -'
        echo '      sudo yum install -y nodejs'
        echo ""
        return 1
    fi
}

check_pnpm() {
    if command -v pnpm &>/dev/null; then
        return 0
    fi
    log_warn "pnpm 未安装，尝试自动安装..."
    # 方法1: corepack (Node >= 16.17 自带)
    if command -v corepack &>/dev/null; then
        log_cmd "corepack enable && corepack prepare pnpm@latest --activate"
        corepack enable && corepack prepare pnpm@latest --activate && {
            log_ok "pnpm 安装成功（via corepack）"
            return 0
        }
    fi
    # 方法2: npm install -g
    if command -v npm &>/dev/null; then
        log_cmd "npm install -g pnpm"
        npm install -g pnpm && {
            log_ok "pnpm 安装成功（via npm）"
            return 0
        }
    fi
    # 都不行 → 给手动指引
    echo ""
    echo "   先确保 Node.js 已安装，然后执行："
    log_cmd "npm install -g pnpm"
    echo ""
    return 1
}

check_python() {
    local found=""
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            found="$cmd"
            break
        fi
    done
    if [ -z "$found" ]; then
        log_err "Python 3 未安装"
        echo ""
        echo "   建议安装："
        log_cmd "macOS: brew install python"
        log_cmd "Ubuntu: sudo apt install -y python3 python3-venv"
        echo ""
        return 1
    fi
    # 检查版本 >= 3.9
    local ver
    ver=$("$found" --version 2>&1 | grep -oP '\d+\.\d+')
    local major
    major=$(echo "$ver" | cut -d. -f1)
    local minor
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 9 ]; }; then
        log_err "Python 版本过低: $("$found" --version)，需要 >= 3.9"
        return 1
    fi
    log_ok "Python $ver （$found）"
    return 0
}

install_all_deps() {
    echo ""
    echo "═══════ 安装所有依赖 ═══════"
    echo ""

    # Python 后端
    log_info "检查 Python 依赖..."
    VENV_PATH="$BACKEND_DIR/.venv"
    if [ ! -d "$VENV_PATH" ]; then
        VENV_PATH="$BACKEND_DIR/venv"
    fi
    if [ ! -d "$VENV_PATH" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$BACKEND_DIR/.venv"
        VENV_PATH="$BACKEND_DIR/.venv"
        log_ok "虚拟环境创建完成"
    fi
    "$VENV_PATH/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q
    log_ok "Python 依赖安装完成"

    # Node 前端
    log_info "安装前端依赖..."
    cd "$FRONTEND_DIR"
    if command -v pnpm &>/dev/null; then
        pnpm install
    elif command -v npm &>/dev/null; then
        npm install
    else
        log_err "pnpm 和 npm 都不可用，无法安装前端依赖"
        return 1
    fi
    log_ok "前端依赖安装完成"

    echo ""
    log_ok "所有依赖就绪"
}

# ═══════════════════════════════════════════════
#  检查 & 停止
# ═══════════════════════════════════════════════

stop_service() {
    local name="$1" port="$2"
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

stop_all() {
    stop_service "后端" "$BACKEND_PORT"
    stop_service "前端" "$FRONTEND_PORT"
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

    if check_port "$BACKEND_PORT"; then
        local pid
        pid=$(lsof -ti :$BACKEND_PORT 2>/dev/null)
        log_ok "后端 http://localhost:$BACKEND_PORT (PID: $pid)"
        if curl -sf http://localhost:$BACKEND_PORT/api/channels >/dev/null 2>&1; then
            echo "   └─ API 正常"
        else
            log_warn "   └─ API 无响应"
        fi
    else
        log_err "后端 :$BACKEND_PORT — 未运行"
    fi

    if check_port "$FRONTEND_PORT"; then
        local pid
        pid=$(lsof -ti :$FRONTEND_PORT 2>/dev/null)
        log_ok "前端 http://localhost:$FRONTEND_PORT (PID: $pid)"
    else
        log_err "前端 :$FRONTEND_PORT — 未运行"
    fi

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

    if [ ! -d "$BACKEND_DIR" ]; then
        log_err "后端目录不存在: $BACKEND_DIR"
        exit 1
    fi

    # ── 确保虚拟环境存在 ──
    VENV_PATH="$BACKEND_DIR/.venv"
    if [ ! -d "$VENV_PATH" ]; then
        VENV_PATH="$BACKEND_DIR/venv"
    fi
    if [ ! -d "$VENV_PATH" ]; then
        log_warn "虚拟环境不存在，正在创建 .venv..."
        python3 -m venv "$BACKEND_DIR/.venv"
        VENV_PATH="$BACKEND_DIR/.venv"
        log_ok ".venv 创建完成"
    fi

    # ── 确保依赖已安装 ──
    log_info "检查 Python 依赖..."
    "$VENV_PATH/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q 2>&1 | tail -3
    log_ok "依赖检查完成"

    cd "$BACKEND_DIR"
    export no_proxy="${no_proxy:-localhost,127.0.0.1,api.deepseek.com,*.deepseek.com}"
    export NO_PROXY="$no_proxy"
    nohup "$VENV_PATH/bin/python" main.py > "$BACKEND_LOG" 2>&1 &
    log_info "PID: $!，日志: $BACKEND_LOG"

    for i in $(seq 1 30); do
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

    # ── 前置检查：Node.js 和 pnpm ──
    check_nodejs || exit 1
    check_pnpm || exit 1

    # ── 依赖安装 ──
    if [ ! -f "$FRONTEND_DIR/node_modules/.modules.yaml" ]; then
        log_warn "node_modules 未安装，正在安装前端依赖..."
        cd "$FRONTEND_DIR"
        pnpm install || { log_err "pnpm install 失败"; exit 1; }
        log_ok "前端依赖安装完成"
    fi

    cd "$FRONTEND_DIR"
    nohup node ./node_modules/vite/bin/vite.js --host 0.0.0.0 > "$FRONTEND_LOG" 2>&1 &
    log_info "PID: $!，日志: $FRONTEND_LOG"

    # 等待启动
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

# ═══════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════

case "${1:-all}" in
    install-deps)
        install_all_deps
        exit 0
        ;;
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
    all|"")
        # 先检查关键依赖（不阻塞，让用户知道缺什么）
        echo ""
        echo "═══════ 坐山客启动检查 ═══════"
        echo ""
        check_python
        check_nodejs
        check_pnpm
        echo ""
        sleep 1

        start_backend || log_warn "后端健康检查超时，但进程可能仍在启动中，继续启动前端..."
        start_frontend
        echo ""
        log_ok "全部服务启动完成"
        echo ""
        status
        ;;
    *)
        echo "用法: $0 {all|backend|frontend|stop|status|restart|install-deps}"
        echo ""
        echo "  all          启动全部（后端 + 前端）"
        echo "  backend      仅后端"
        echo "  frontend     仅前端"
        echo "  stop         全部停止"
        echo "  status       查看状态"
        echo "  restart      全部重启"
        echo "  install-deps 仅安装依赖（场景迁移/重装时用）"
        exit 1
        ;;
esac
