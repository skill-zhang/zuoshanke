#!/usr/bin/env bash
# ── 启动 Qwen LLM（llama-server）──
# 用法:
#   ./start-qwen.sh              # 启动 Qwen3.5-9B 多模态（默认，支持图片识别）
#   ./start-qwen.sh text         # 启动 Qwen3-8B 纯文本
#   ./start-qwen.sh stop         # 停掉当前 llama-server
#   ./start-qwen.sh status       # 查看运行状态

set -euo pipefail
PORT=${QWEN_PORT:-8083}

# ── 二进制路径 ──
B9070="$HOME/llama-cpp/llama-b9070/llama-server"      # ✅ 推荐：b9070 预编译版，Qwen3.5 多模态正常
MASTER="$HOME/llama-cpp/llama-src/llama.cpp-master/build/bin/llama-server"  # ⚠️ master 版 SSM 层有 bug
SYSTEM="/usr/local/bin/llama-server"                   # ⚠️ 旧全局安装版

# ── 模型路径 ──
MODEL_DIR="$HOME/models"
MODEL_35="$MODEL_DIR/Qwen3.5-9B-Q4_K_M.gguf"   # 多模态（5.3GB）
MMPROJ="$MODEL_DIR/mmproj-F16.gguf"             # 多模态投影（876MB）
MODEL_8B="$MODEL_DIR/Qwen3-8B-Q4_K_M.gguf"     # 纯文本（4.7GB）

# ── 公共参数 ──
COMMON_ARGS="--host 0.0.0.0 --port $PORT -ngl 99 --ctx-size 16384 --threads 6 --temp 0.7 --repeat-penalty 1.1 --no-mmap --reasoning off"

stop_llama() {
    local pids
    pids=$(pgrep -f "llama-server.*port $PORT" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "🔴 停掉 llama-server (PID: $pids)..."
        kill $pids 2>/dev/null || true
        sleep 1
        # 确认已停
        if pgrep -f "llama-server.*port $PORT" >/dev/null 2>&1; then
            echo "   ⏳ 强制终止..."
            kill -9 $pids 2>/dev/null || true
            sleep 1
        fi
        echo "   ✅ 已停止"
    else
        echo "   ℹ️  没有运行中的 llama-server"
    fi
}

status_llama() {
    local pids
    pids=$(pgrep -f "llama-server.*port $PORT" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "🟢 llama-server 正在运行"
        ps -p $pids -o pid,lstart,args --no-headers 2>/dev/null
        echo ""
        # 检查健康状态
        if curl -sf http://localhost:$PORT/health >/dev/null 2>&1; then
            echo "   ✅ 健康检查通过"
            curl -s http://localhost:$PORT/v1/models 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for m in d.get('data', []):
        caps = ', '.join(m.get('meta', {}).get('capabilities', m.get('capabilities', [])))
        print(f'   📦 模型: {m[\"id\"]}')
        print(f'   🔧 能力: {caps}')
except: pass
" 2>/dev/null || true
        else
            echo "   ⚠️  健康检查失败（可能正在加载中）"
        fi
    else
        echo "🔴 llama-server 未运行"
    fi
}

case "${1:-multimodal}" in
    stop)
        stop_llama
        exit 0
        ;;
    status)
        status_llama
        exit 0
        ;;
    restart)
        stop_llama
        exec "$0" "${2:-multimodal}"
        ;;
    text|8b)
        echo "🚀 启动 Qwen3-8B 纯文本（端口 $PORT）..."
        BIN="$B9070"
        MODEL="$MODEL_8B"
        MMARG=""
        shift 2>/dev/null || true
        ;;
    multimodal|35|9b|*)
        echo "🚀 启动 Qwen3.5-9B 多模态（端口 $PORT，支持图片识别）..."
        BIN="$B9070"
        MODEL="$MODEL_35"
        MMARG="--mmproj $MMPROJ"
        shift 2>/dev/null || true
        ;;
esac

# 校验
for f in "$BIN" "$MODEL"; do
    if [ ! -f "$f" ]; then
        echo "❌ 文件不存在: $f"
        exit 1
    fi
done
if [ -n "$MMARG" ] && [ ! -f "$MMPROJ" ]; then
    echo "❌ 多模态投影文件不存在: $MMPROJ"
    exit 1
fi

stop_llama

echo "   二进制: $BIN"
echo "   模型:   $MODEL"
echo "   端口:   $PORT"
echo ""

# 在后台启动并确认
nohup "$BIN" $COMMON_ARGS $MMARG > /tmp/llama-server.log 2>&1 &
PID=$!
echo "   PID: $PID"

# 等待启动完成（最多 60 秒）
echo "   等待启动..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:$PORT/health >/dev/null 2>&1; then
        echo "   ✅ 启动成功（${i}s）"
        status_llama
        exit 0
    fi
    sleep 1
done

echo "❌ 启动超时（60s），查看日志: tail -50 /tmp/llama-server.log"
exit 1
