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

# 配置文件路径（新旧兼容）
CONFIG_OLD="$HOME/.zuoshanke/.gateway.env"
CONFIG_NEW="$HOME/.zuoshanke/gateway.env"

mkdir -p "$HOME/.zuoshanke"

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "⚠️  Gateway 已在运行 (PID: $(cat "$PID_FILE"))"
        return 1
    fi

    echo "🚀 启动坐山客 Gateway v0.2 (多平台)..."
    echo "   配置文件: $CONFIG_NEW (新版) / $CONFIG_OLD (旧版)"
    
    # 检测配置
    if [ -f "$CONFIG_NEW" ]; then
        echo "   检测到新版配置，支持多平台"
        grep -E '^(WEIXIN|TELEGRAM|DISCORD|SIGNAL|EMAIL|SLACK|WHATSAPP|FEISHU|DINGTALK|WECOM|MATRIX|SMS|YYB)_' "$CONFIG_NEW" | \
            sed 's/=.*//' | sort -u | while read -r prefix; do
            echo "   📱 ${prefix%_*} 已配置"
        done
    elif [ -f "$CONFIG_OLD ]; then
        echo "   检测到旧版配置（仅微信）"
    else
        echo "   ⚠️  无配置文件，Gateway 退出"
    fi

    cd "$BACKEND_DIR" && nohup ".venv/bin/python" -m backend.gateway.run \
        >> "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    echo "✅ Gateway 已启动 (PID: $PID)"
    echo "日志: $LOG_FILE"
    sleep 1
    tail -3 "$LOG_FILE" 2>/dev/null || true
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
    echo ""
    
    if [ -f "$CONFIG_NEW" ]; then
        echo "  ✅ 新版配置文件: $CONFIG_NEW"
        echo ""
        echo "  已配置平台:"
        grep -v '^#' "$CONFIG_NEW" | grep -v '^$' | while IFS='=' read -r key value; do
            # 提取平台前缀
            prefix="${key%%_*}"
            case "$prefix" in
                WEIXIN)
                    if [ "$key" = "WEIXIN_TOKEN" ]; then
                        echo "  📱 微信 (iLink)"
                        echo "     Token: ${value:0:8}...${value: -4}"
                    elif [ "$key" = "WEIXIN_ACCOUNT_ID" ]; then
                        echo "     Account: ${value:0:8}..."
                    fi
                    ;;
                TELEGRAM)
                    if [ "$key" = "TELEGRAM_TOKEN" ]; then
                        echo "  📱 Telegram"
                        echo "     Token: ${value:0:8}...${value: -4}"
                    fi
                    ;;
                DISCORD)
                    if [ "$key" = "DISCORD_BOT_TOKEN" ]; then
                        echo "  📱 Discord"
                        echo "     Token: ${value:0:8}...${value: -4}"
                    fi
                    ;;
                SIGNAL)
                    if [ "$key" = "SIGNAL_PHONE_NUMBER" ]; then
                        echo "  📱 Signal"
                        echo "     Phone: ${value:0:6}...${value: -4}"
                    fi
                    ;;
                EMAIL)
                    if [ "$key" = "EMAIL_SMTP_HOST" ]; then
                        echo "  📧 Email: $value"
                    fi
                    ;;
                SLACK)
                    if [ "$key" = "SLACK_BOT_TOKEN" ]; then
                        echo "  📱 Slack (已配置)"
                    fi
                    ;;
                WHATSAPP)
                    if [ "$key" = "WHATSAPP_PHONE_NUMBER_ID" ]; then
                        echo "  📱 WhatsApp: $value"
                    fi
                    ;;
                FEISHU)
                    if [ "$key" = "FEISHU_APP_ID" ]; then
                        echo "  📱 飞书: $value"
                    fi
                    ;;
                DINGTALK)
                    if [ "$key" = "DINGTALK_CLIENT_ID" ]; then
                        echo "  📱 钉钉: $value"
                    fi
                    ;;
                WECOM)
                    if [ "$key" = "WECOM_CORP_ID" ]; then
                        echo "  📱 企业微信: $value"
                    fi
                    ;;
                *)
                    echo "  📱 ${prefix}: (已配置)"
                    ;;
            esac
        done
    elif [ -f "$CONFIG_OLD ]; then
        echo "  ⚠️  旧版配置文件: $CONFIG_OLD"
        echo "  建议迁移到新版格式: cp $CONFIG_OLD $CONFIG_NEW"
        echo ""
        grep -v '^#' "$CONFIG_OLD" | grep -v '^$' | while IFS='=' read -r key value; do
            if [ "$key" = "WEIXIN_TOKEN" ]; then
                echo "  📱 微信"
                echo "     Token: ${value:0:8}...${value: -4}"
            elif [ "$key" = "WEIXIN_ACCOUNT_ID" ]; then
                echo "     Account: ${value:0:8}..."
            else
                echo "  $key: $value"
            fi
        done
    else
        echo "  ❌ 无配置文件"
        echo ""
        echo "  请创建配置文件:"
        echo "    $CONFIG_NEW"
        echo ""
        echo "  示例内容:"
        echo "    # 微信"
        echo "    WEIXIN_TOKEN=your_token"
        echo "    WEIXIN_ACCOUNT_ID=your_account_id"
        echo "    # Telegram"
        echo "    TELEGRAM_TOKEN=123456:ABC-DEF..."
        echo "    # Discord"
        echo "    DISCORD_BOT_TOKEN=your_discord_token"
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
