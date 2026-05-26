# 坐山客 Prompt Caching 实现

## 动机

当用户选择 Anthropic Claude 模型（通过 OpenRouter 或原生 API）时，若无前缀缓存，
每次对话请求都要重新传输完整的 system prompt 和历史消息。Prompt Caching 通过
注入 `cache_control` 断点，让 API 提供商缓存对话前缀，典型节省 ~75% input token。

## 设计

### system_and_3 策略

Anthropic 允许单次请求最多 4 个 `cache_control({"type": "ephemeral"})` 断点：

1. **System Prompt** — 始终缓存，跨所有对话轮次不变
2. **倒数第 3 条非 system 消息** — 滚动窗口
3. **倒数第 2 条非 system 消息** — 滚动窗口
4. **最后 1 条非 system 消息** — 滚动窗口

### 检测逻辑

仅模型名包含 `claude` 或 `qwen` 时注入。支持：
- OpenRouter + Claude（OpenAI 兼容格式）
- 原生 Anthropic API
- MiniMax/GLM/LiteLLM 等 Anthropic 兼容网关
- **Qwen 系**（DashScope/OpenCode Go 也认这些标记，不加标记时缓存命中为 0）

### 集成点

```
用户消息 → call_llm / call_llm_stream / call_llm_with_tools
                               ↓
                    inject_prompt_cache_markers()
                               ↓
                      （deep copy + 注入标记）
                               ↓
                    requests.post(..., messages=带标记的消息)
```

## 文件清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `backend/agent_core/prompt_caching.py` | 新建 | ~120 |
| `backend/ai_engine.py` | `call_llm()` + `call_llm_stream()` 内注入 | +3 行 |
| `backend/agent_core/agent_loop.py` | `call_llm_with_tools()` 内注入 | +4 行 |

## 与非 Claude 模型的关系

| 模型 | 缓存方式 | 需 Inject? |
|------|---------|-----------|
| Claude (OpenRouter) | cache_control 标记 | ✅ 是 |
| Claude (原生 API) | cache_control 标记 | ✅ 是 |
| DeepSeek | 自动服务端前缀缓存 | ❌ 不（自动生效） |
| Qwen / Alibaba | 自动服务端前缀缓存 | ❌ 不 |
| 本地 Qwen (llama.cpp) | 无 | ❌ 不 |

## 验证

```bash
# 编译检查
cd /home/administrator/zuoshanke && \
  backend/.venv/bin/python -m py_compile backend/agent_core/prompt_caching.py && \
  backend/.venv/bin/python -m py_compile backend/ai_engine.py && \
  backend/.venv/bin/python -m py_compile backend/agent_core/agent_loop.py

# 单元测试
backend/.venv/bin/python /tmp/test_prompt_cache.py
```
