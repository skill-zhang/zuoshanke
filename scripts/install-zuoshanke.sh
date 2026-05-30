#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
# 坐山客 (Zuoshanke) v1.8 — 一键安装脚本
# One-Click Install for Zuoshanke AI Platform
# ═══════════════════════════════════════════════════════
set -euo pipefail

# ── 颜色 ──
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e " ${GREEN}ℹ${NC}  $1"; }
ok()   { echo -e " ${GREEN}✅${NC} $1"; }
err()  { echo -e " ${RED}❌${NC} $1"; }
warn() { echo -e " ${YELLOW}⚠${NC}  $1"; }
title(){ echo -e "\n ${CYAN}━━━ $1 ━━━${NC}\n"; }

# ── 默认路径 ──
ZUOSHANKE_DIR="${ZUOSHANKE_DIR:-$HOME/zuoshanke}"
ZUOSHANKE_ENV_DIR="$HOME/.zuoshanke"
ZUOSHANKE_SCRIPTS_DIR="$HOME/scripts"
ZUOSHANKE_GIT_REPO="https://ghfast.top/https://github.com/skill-zhang/zuoshanke.git"
ZUOSHANKE_BRANCH="main"

# ── 系统检测 ──
detect_os() {
  if [[ "$(uname -s)" == "Linux" ]]; then
    if grep -qi microsoft /proc/version 2>/dev/null; then
      echo "wsl"
    else
      echo "linux"
    fi
  elif [[ "$(uname -s)" == "Darwin" ]]; then
    echo "macos"
  else
    echo "other"
  fi
}
OS=$(detect_os)
log "检测到系统: $OS"

# ══════════════════════════════════════════════════════
# 1. 前置依赖检查
# ══════════════════════════════════════════════════════
title "1/7  前置依赖检查"

check_dep() {
  local name=$1 cmd=$2 hint=$3
  if command -v "$cmd" &>/dev/null; then
    local ver=$("$cmd" --version 2>/dev/null | head -1)
    ok "$name: $ver"
    return 0
  else
    err "$name 未安装"
    warn "请先安装: $hint"
    return 1
  fi
}

MISSING=0
check_dep "Python 3" python3 "apt install python3 python3-venv python3-pip / brew install python3"
check_dep "Node.js" node "https://nodejs.org 或 nvm install 20"
check_dep "pnpm" pnpm "npm install -g pnpm 或 brew install pnpm"
check_dep "Git" git "apt install git / brew install git"

# 检查 python3-venv
if python3 -c "import venv" &>/dev/null; then
  ok "Python venv 模块可用"
else
  err "python3-venv 未安装"
  if [[ "$OS" == "wsl" || "$OS" == "linux" ]]; then
    warn "运行: sudo apt install python3-venv -y"
  elif [[ "$OS" == "macos" ]]; then
    warn "Python3 通常自带 venv，请检查 Python 安装"
  fi
  MISSING=1
fi

# 检查国内镜像（中国用户）
if [[ -n "${CN_MIRROR:-}" || "$(curl -s --connect-timeout 2 https://www.baidu.com 2>/dev/null | grep -c baidu)" -gt 0 ]]; then
  USE_CN_MIRROR=true
  warn "检测到中国网络环境 → 使用国内镜像加速"
else
  USE_CN_MIRROR=false
fi

[[ $MISSING -gt 0 ]] && { err "请安装缺失依赖后重新运行"; exit 1; }

# ══════════════════════════════════════════════════════
# 2. 克隆/更新代码
# ══════════════════════════════════════════════════════
title "2/7  获取坐山客代码"

clone_or_pull() {
  if [[ -d "$ZUOSHANKE_DIR/.git" ]]; then
    log "坐山客目录已存在，拉取最新代码..."
    cd "$ZUOSHANKE_DIR"
    git stash 2>/dev/null || true
    git pull origin "$ZUOSHANKE_BRANCH" --rebase 2>/dev/null || {
      warn "拉取失败，保留现有代码"
    }
    ok "代码已更新"
  else
    log "正在克隆坐山客代码..."
    if [[ -d "$ZUOSHANKE_DIR" ]]; then
      warn "目录 $ZUOSHANKE_DIR 已存在但不是 git 仓库，备份到 ${ZUOSHANKE_DIR}.bak"
      mv "$ZUOSHANKE_DIR" "${ZUOSHANKE_DIR}.bak.$(date +%Y%m%d%H%M%S)"
    fi
    git clone --depth 1 -b "$ZUOSHANKE_BRANCH" "$ZUOSHANKE_GIT_REPO" "$ZUOSHANKE_DIR"
    ok "代码克隆完成"
  fi
}
clone_or_pull

# ══════════════════════════════════════════════════════
# 3. 后端环境
# ══════════════════════════════════════════════════════
title "3/7  后端 Python 环境"

BACKEND_DIR="$ZUOSHANKE_DIR/backend"
cd "$BACKEND_DIR"

# 创建 .venv（统一命名，与 start-zuoshanke.sh 一致）
VENV_DIR=".venv"
if [[ -d "$VENV_DIR" ]]; then
  ok ".venv 已存在"
elif [[ -d "venv" ]]; then
  warn "检测到旧的 venv/ 目录，重命名为 .venv..."
  mv venv "$VENV_DIR"
  ok "已重命名为 .venv"
else
  log "创建 Python .venv..."
  python3 -m venv "$VENV_DIR"
  ok ".venv 创建完成"
fi

# 国内镜像
if [[ "$USE_CN_MIRROR" == true ]]; then
  log "配置 pip 国内镜像..."
  ./"$VENV_DIR"/bin/pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || true
fi

# 安装依赖
log "安装 Python 依赖..."
./"$VENV_DIR"/bin/pip install --upgrade pip -q
./"$VENV_DIR"/bin/pip install -r requirements.txt -q
ok "requirements.txt 依赖安装完成"

# 额外依赖（numpy/pandas 供 ml_experiment）
log "安装额外依赖 (numpy, pandas)..."
./"$VENV_DIR"/bin/pip install numpy pandas -q
ok "额外依赖安装完成"

# 验证关键依赖
./"$VENV_DIR"/bin/python -c "from dotenv import load_dotenv; print('dotenv OK')" 2>/dev/null && ok "dotenv 验证通过" || err "dotenv 验证失败"
./"$VENV_DIR"/bin/python -c "from sqlalchemy import create_engine; print('SQLAlchemy OK')" 2>/dev/null && ok "SQLAlchemy 验证通过" || err "SQLAlchemy 验证失败"

# 安装 zuoshanke-ctl 到 PATH
chmod +x "$ZUOSHANKE_DIR/scripts/zuoshanke-ctl.sh" 2>/dev/null || true

# ══════════════════════════════════════════════════════
# 4. 前端环境
# ══════════════════════════════════════════════════════
title "4/7  前端环境"

FRONTEND_DIR="$ZUOSHANKE_DIR/frontend"
cd "$FRONTEND_DIR"

if [[ -d "node_modules" ]]; then
  ok "前端 node_modules 已存在 ($(du -sh "$FRONTEND_DIR/node_modules" | cut -f1))"
else
  log "安装前端依赖..."
  if [[ "$USE_CN_MIRROR" == true ]]; then
    pnpm config set registry https://registry.npmmirror.com 2>/dev/null || true
  fi
  CI=true pnpm install 2>&1 | tail -5
  ok "前端依赖安装完成"
fi

# 验证 vite 可执行
if [[ -f "node_modules/.bin/vite" || -f "node_modules/vite/bin/vite.js" ]]; then
  ok "Vite 可执行"
else
  warn "Vite 未找到，尝试重新安装..."
  CI=true pnpm install 2>&1 | tail -3
fi

# ══════════════════════════════════════════════════════
# 5. 工作台环境 (Schema v1.8)
# ══════════════════════════════════════════════════════
title "5/7  工作台 (Workbench) 环境"

WORKBENCH_DIR="$ZUOSHANKE_DIR/workbench"
if [[ -d "$WORKBENCH_DIR" ]]; then
  # 工作台后端
  if [[ -d "$WORKBENCH_DIR/backend" ]]; then
    cd "$WORKBENCH_DIR/backend"
    if [[ -f "requirements.txt" ]]; then
      log "安装工作台后端依赖..."
      # 复用主项目 .venv 或 fallback 到 venv
      if [[ -f "$BACKEND_DIR/.venv/bin/pip" ]]; then
        "$BACKEND_DIR/.venv/bin/pip" install -r requirements.txt -q
      else
        "$BACKEND_DIR/venv/bin/pip" install -r requirements.txt -q
      fi
      ok "工作台后端依赖安装完成"
    fi
  fi

  # 工作台前端
  if [[ -d "$WORKBENCH_DIR/frontend" && ! -f "$WORKBENCH_DIR/frontend/node_modules/.package-lock.json" ]]; then
    cd "$WORKBENCH_DIR/frontend"
    if [[ -f "package.json" ]]; then
      log "安装工作台前端依赖..."
      if [[ -f "pnpm-lock.yaml" ]]; then
        CI=true pnpm install 2>&1 | tail -3
      elif [[ -f "package-lock.json" ]]; then
        npm install 2>&1 | tail -3
      else
        npm install 2>&1 | tail -3
      fi
      ok "工作台前端依赖安装完成"
    fi
  elif [[ -d "$WORKBENCH_DIR/frontend/node_modules" ]]; then
    ok "工作台前端依赖已存在"
  fi

  # 工作台启动脚本
  chmod +x "$WORKBENCH_DIR/scripts/start.sh" "$WORKBENCH_DIR/scripts/stop.sh" 2>/dev/null || true
else
  warn "工作台目录不存在，跳过（不影响主应用）"
fi

# ══════════════════════════════════════════════════════
# 6. 环境变量配置
# ══════════════════════════════════════════════════════
title "6/7  环境变量配置"

mkdir -p "$ZUOSHANKE_ENV_DIR"

if [[ -f "$ZUOSHANKE_ENV_DIR/.env" ]]; then
  ok "环境变量文件已存在: $ZUOSHANKE_ENV_DIR/.env"
  # 检查是否有 DEEPSEEK_API_KEY
  if grep -q "DEEPSEEK_API_KEY=sk-" "$ZUOSHANKE_ENV_DIR/.env" 2>/dev/null; then
    ok "DEEPSEEK_API_KEY 已配置"
  else
    warn "DEEPSEEK_API_KEY 未配置或格式不正确"
    warn "请编辑 $ZUOSHANKE_ENV_DIR/.env 填入你的 API Key"
  fi
else
  log "创建环境变量文件..."
  cat > "$ZUOSHANKE_ENV_DIR/.env" << 'ENVEOF'
# ═══ 坐山客环境变量 ═══
# 填入你的 DeepSeek API Key（必填）
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY_HERE
DEEPSEEK_BASE_URL=https://api.deepseek.com
ENVEOF
  warn "请编辑 $ZUOSHANKE_ENV_DIR/.env，填入你的 DEEPSEEK_API_KEY"
  warn "获取地址: https://platform.deepseek.com/api_keys"
fi

# 复制启动脚本到 ~/scripts/
title "  安装启动脚本到 ~/scripts/"
mkdir -p "$ZUOSHANKE_SCRIPTS_DIR"

# start-zuoshanke.sh
if [[ -f "$ZUOSHANKE_DIR/scripts/start-zuoshanke.sh" ]]; then
  cp "$ZUOSHANKE_DIR/scripts/start-zuoshanke.sh" "$ZUOSHANKE_SCRIPTS_DIR/start-zuoshanke.sh"
  chmod +x "$ZUOSHANKE_SCRIPTS_DIR/start-zuoshanke.sh"
  ok "start-zuoshanke.sh → ~/scripts/"
fi

# zuoshanke-ctl.sh
if [[ -f "$ZUOSHANKE_DIR/scripts/zuoshanke-ctl.sh" ]]; then
  cp "$ZUOSHANKE_DIR/scripts/zuoshanke-ctl.sh" "$ZUOSHANKE_SCRIPTS_DIR/zuoshanke-ctl.sh"
  chmod +x "$ZUOSHANKE_SCRIPTS_DIR/zuoshanke-ctl.sh"
  ok "zuoshanke-ctl.sh → ~/scripts/"
fi

# 确保 ~/scripts/ 在 PATH 中
if [[ ":$PATH:" != *":$HOME/scripts:"* ]]; then
  SHELL_CONFIG="$HOME/.bashrc"
  [[ -f "$HOME/.zshrc" ]] && SHELL_CONFIG="$HOME/.zshrc"
  echo 'export PATH="$HOME/scripts:$PATH"' >> "$SHELL_CONFIG"
  ok "已将 ~/scripts/ 添加到 PATH ($SHELL_CONFIG)"
  export PATH="$HOME/scripts:$PATH"
fi

# ══════════════════════════════════════════════════════
# 7. 最终检查 & 启动
# ══════════════════════════════════════════════════════
title "7/7  安装完成检查"

echo ""
echo -e " ${CYAN}════════════════════════════════════════════════${NC}"
echo -e " ${CYAN}  坐山客 v$(cat "$ZUOSHANKE_DIR/VERSION" 2>/dev/null || echo "?")  安装完成！${NC}"
echo -e " ${CYAN}════════════════════════════════════════════════${NC}"
echo ""

# 摘要
BACKEND_OK="❌ 未就绪"
if [[ -d "$BACKEND_DIR/.venv" ]]; then
  BACKEND_OK="✅ 就绪 (.venv + $("$BACKEND_DIR/.venv/bin/pip" list --format=columns 2>/dev/null | wc -l | xargs) packages)"
elif [[ -d "$BACKEND_DIR/venv" ]]; then
  BACKEND_OK="✅ 就绪 (venv + $("$BACKEND_DIR/venv/bin/pip" list --format=columns 2>/dev/null | wc -l | xargs) packages)"
fi

FRONTEND_OK="❌ 未就绪"
if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
  FRONTEND_OK="✅ 就绪 ($(du -sh "$FRONTEND_DIR/node_modules" | cut -f1))"
fi

echo "  后端     $BACKEND_OK"
echo "  前端     $FRONTEND_OK"
echo "  配置     $([ -f "$ZUOSHANKE_ENV_DIR/.env" ] && echo '✅ .env 存在' || echo '❌ 缺少 .env')"
echo "  脚本     $([ -f "$ZUOSHANKE_SCRIPTS_DIR/start-zuoshanke.sh" ] && echo '✅ start-zuoshanke.sh' || echo '❌ 未安装')"
echo "  DB       $([ -f "$BACKEND_DIR/zuoshanke.db" ] && echo '✅ 已存在' || echo '⏳ 首次启动自动创建')"
echo ""

# ── 重要提示 ──
echo -e " ${YELLOW}📋 启动指南${NC}"
echo ""
echo "  1. 确保 DEEPSEEK_API_KEY 已配置:"
echo "     nano $ZUOSHANKE_ENV_DIR/.env"
echo ""
echo "  2. 一键启动:"
echo "     start-zuoshanke.sh"
echo "     # 或分步启动:"
echo "     start-zuoshanke.sh backend"
echo "     start-zuoshanke.sh frontend"
echo ""
echo "  3. 浏览器打开:"
echo "     http://localhost:5173"
echo ""
echo "  4. 查看状态:"
echo "     start-zuoshanke.sh status"
echo ""
echo "  5. 停止服务:"
echo "     start-zuoshanke.sh stop"
echo ""

# ── 可选：Qwen LLM 配置指引 ──
echo -e " ${YELLOW}🤖 可选：Qwen LLM 本地模型 (GPU 加速)${NC}"
echo ""
echo "  坐山客默认使用 DeepSeek API（云端）。"
echo "  如需离线运行，可部署 Qwen3.5-9B GGUF 模型:"
echo "     start-qwen.sh              # 需要先配置 CUDA + llama-cpp"
echo "     # 详见: $ZUOSHANKE_DIR/docs/design/ 下的文档"
echo ""

# ── 如需立即启动 ──
if [[ -z "${SKIP_START:-}" ]]; then
  echo -e " ${YELLOW}按回车键立即启动坐山客，或 Ctrl+C 退出手动启动...${NC}"
  read -r -t 5 || true
fi

# 检查 API Key 是否已填
if grep -q "YOUR_DEEPSEEK_API_KEY_HERE" "$ZUOSHANKE_ENV_DIR/.env" 2>/dev/null; then
  warn "DEEPSEEK_API_KEY 尚未配置，请先编辑 $ZUOSHANKE_ENV_DIR/.env"
  warn "启动后 LLM 调用会失败，但前端页面仍可正常打开"
fi

# 如果按了回车且在 5 秒内，启动
if [[ -n "${REPLY:-}" ]]; then
  echo ""
  log "启动坐山客服务..."
  if command -v start-zuoshanke.sh &>/dev/null; then
    start-zuoshanke.sh
  else
    bash "$ZUOSHANKE_DIR/scripts/start-zuoshanke.sh"
  fi
fi

echo -e " ${GREEN}🎉 安装完成！enjoy 坐山客~${NC}"
