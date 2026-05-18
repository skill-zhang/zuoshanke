# 场景 Agent Loop 迁移记录

**日期**：2026-05-19  
**状态**：✅ 已上线

## 背景

场景（scene）聊天原本使用规则预执行层 + 4路路由选择不同的 AI 流路径。这种方式有几个问题：

1. **城市名硬编码**：`_extract_city()` 只匹配 42 个国内城市，外国城市名（柏林、巴黎、东京）直接跳过，get_weather 工具不会触发
2. **system prompt 硬编码**：`context_builder.py` 的 `SCENE_SYSTEM_PROMPT` 写着"天气、景点推荐、装备建议等"，导致 LLM 以为自己是户外出行机器人
3. **规则层先于 LLM 决策**：规则层决定调不调工具，LLM 没机会用知识判断"德国首都是柏林"
4. **4路路由复杂**：light/medium/heavy/missing_info 四条路径，各有不同的 system prompt 和行为

## 改造方案

### 删除
- `detect_and_preexecute()` 预执行调用
- `_needs_search_fallback()` web_search 兜底
- 4路路由（`agent_core_light_stream` / `ai_scene_chat_stream` / `ai_scene_ask_missing_stream`）
- `MODEL_MAP` 硬编码 dict
- 相关的 import

### 新增
- 场景消息直接调 `run_agent_loop(task, system_prompt=scene_agent_prompt)`
- Agent Loop 事件 → 场景 SSE 事件映射（tool_start→tool_status, thinking→token 等）
- 工具结果收集 → `_build_tool_cards()` 重建天气卡片

### 改动文件

| 文件 | 改动 |
|------|------|
| `agent_core/agent_loop.py` | 移除 get_weather/recommend/equipment 排除；新增 system_prompt 参数 |
| `router/scenes.py` | ~100 行预执行+路由替换为 ~30 行 Agent Loop 调用 |
| `agent_core/context_builder.py` | SCENE_SYSTEM_PROMPT 清理+优先读 DB settings |

## 影响范围

- ✅ **场景（scene）**：全走 Agent Loop
- ❌ **频道（channel）**：不受影响，仍走原流式路径
- ❌ **Agent Loop 独立端点** `/api/agent-loop/stream`：不受影响

## 后续注意事项

1. 新加工具时，如果它需要 LLM 常识就能调，直接加到 registry.json 即可，Agent Loop 自动发现
2. 只有需要环境上下文（用户位置、设备信息等）的工具才考虑放在预执行层
3. 场景的 `user_context` 字段作为用户背景设定，会追加到 Agent Loop system prompt 中
