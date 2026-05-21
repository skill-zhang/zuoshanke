# Qwen3-8B llama-server 启动配置

> 最后更新: 2026-05-21

## 硬件

- **GPU:** NVIDIA GeForce RTX 5070 (12GB VRAM)
- **CPU:** 20 核 (llama-server 用 6 线程)
- **RAM:** 充足

## 启动命令

### CUDA 版（推荐 - 带 GPU 加速）

```bash
export LD_LIBRARY_PATH=$HOME/llama-cpp/llama-src/llama.cpp-master/build/bin:$LD_LIBRARY_PATH
$HOME/llama-cpp/llama-src/llama.cpp-master/build/bin/llama-server \
  --host 0.0.0.0 --port 8083 \
  -m $HOME/models/Qwen3-8B-Q4_K_M.gguf \
  -ngl 99 --ctx-size 16384 --threads 6 \
  --temp 0.7 --repeat-penalty 1.1 \
  --no-mmap \
  --reasoning off
```

### CPU-only 版（不用）

```bash
export LD_LIBRARY_PATH=$HOME/llama-cpp/llama-b9070:$LD_LIBRARY_PATH
$HOME/llama-cpp/llama-b9070/llama-server \
  ... # 同上参数，但 ngl=0，慢很多
```

## 关键参数说明

| 参数 | 值 | 原因 |
|------|-----|------|
| `--port` | 8083 | 后端 config/urls.py 中 QWEN_API 配置的端口 |
| `-ngl` | 99 | 全部层跑 GPU（RTX 5070 12GB 足够容纳 Q4_K_M） |
| `--ctx-size` | 16384 | 4096 太小，实际会话常超 5000+ token |
| `--no-mmap` | 必需 | WSL 环境下 mmap 有问题 |
| `--reasoning off` | 关掉 Qwen3 思路链 | 不想看 `...` 推理过程就加这个 |
| `--threads` | 6 | 不占满 20 核，留余量给后端和前端 |

## 常见错误

### `request (N tokens) exceeds the available context size`
- ctx-size 太小。Qwen3-8B 最大支持 40960，设 16384 够用。

### 浏览器报 `/tools` `/cors-proxy` 404
- 浏览器缓存了旧 Web UI 的 SPA。Ctrl+F5 硬刷新。

## 验证

```bash
# 健康检查
curl http://localhost:8083/health
# 返回: {"status":"ok"}

# 模型列表
curl http://localhost:8083/v1/models
```

## 后端集成

- `config/urls.py` 中 `QWEN_API` 指向 `http://localhost:8083/v1/chat/completions`
- `router/garden_chat.py` → `_call_local_llm()` 导入 `config.urls.QWEN_API`（不要硬编码端口）
- `router/settings.py` 的 `/api/settings/service` 也会从 `QWEN_API` 推导端口
