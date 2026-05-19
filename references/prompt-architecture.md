# 坐山客提示词分层架构

> 归档日期: 2026-05-19  
> 相关文件: `backend/agent_core/context_builder.py`, `backend/router/scenes.py`,  
>              `backend/agent_core/agent_loop.py`

## 核心理念

**system prompt 不是万能补丁箱。**

遇到新需求时，本能反应往往是「在 system prompt 里加一段话」。这种捷径思维短期有效，长期导致 prompt 臃肿、矛盾堆叠、LLM 不知道听哪条。

正确的做法：**优先考虑机制驱动的方案**（后端逻辑判断 + 结构化处理），而不是靠「加一段 prompt 让 LLM 记住」。

## 三层提示词体系

### ① System Prompt 层（铁律层）

定义 AI 的「人格」和基本原则。

```
DB settings.system_prompts["scene"]   ← 最高优先级，后台可配
        ↓ (读不到则)
context_builder.SCENE_SYSTEM_PROMPT   ← 代码兜底
```

**规则：**
- 只说「做什么」「是什么」，不说「做几次」「做多少」
- 禁止量化约束：如「追问 2-3 轮」「总结 5 条」
- 禁止具体行业举例：如「如二手车/电商」
- 判断的深度、次数交给 LLM 自主决定

### ② User Prompt 层（仅供参考层）

注入上下文信息，标记为「不相关可忽略」。

```
user_content（用户消息）
  + memory_block（记忆提示，标注「仅供参考」）
  + weather_context（天气桥接）
  + skill_block（匹配到的可复用知识）
```

**规则：**
- 所有注入内容带前缀说明：「仅供参考，不相关可忽略」
- LLM 觉得有用就用，觉得不相关可以忽略
- 不会当成铁律强制执行

### ③ Agent Prompt 层（工具调用层）

Agent Loop 的内部执行上下文。

```
system_prompt  = System Prompt + user_context
task           = 用户当前消息
tools          = function calling 注册表 (build_tool_definitions)
memory_context = 额外记忆注入
```

**规则：**
- Agent Loop 内的 prompt 由调用方传递，不硬编码
- 工具列表由 `agent_loop.build_tool_definitions()` 自动构建
- 不依赖预执行 + 规则匹配，LLM 自主决定调什么工具

## 代码路径对比

### 场景聊天（Agent Loop 模式）

```
用户发消息 → stream_scene_message()
  → 读 SCENE_SYSTEM_PROMPT（DB → code 兜底）
  → 拼上 user_context
  → 传给 run_agent_loop(system_prompt=..., task=...)
  → Agent Loop 循环：LLM 自主调工具
  → 回复完成（done 事件）
  → 可选：自动发散 Thinking Map（首次消息触发）
```

### 频道聊天（预执行模式，与场景不同）

```
用户发消息 → channel 路由
  → context_builder.build_scene_context() 构建全量消息
  → 含：system prompt + 工具结果 + 记忆 + 技能 + 历史 + 当前消息
  → 单次调 LLM 流式回复
```

## 经验教训

1. **不要通过加 system prompt 来「教育」LLM 怎么做具体的事。**
   - 事无巨细的 prompt 会让 LLM 变笨（注意力被稀释）
   - 具体行为应该用代码逻辑控制，而不是 LLM 自觉

2. **量化约束是 system prompt 的大忌。**
   - 「追问 2-3 轮」→ LLM 会严格卡在 2-3 轮，即使需要更多
   - 「输出 5 个建议」→ 即使只有 3 个有价值的，也会硬凑 5 个

3. **场景是入口，不是预设。**
   - 创建场景时用户也不清楚自己要什么
   - 通过对话逐步清晰，而不是 prompt 一次性规定

4. **先分析再动手，不要条件反射式改 prompt。**
   - 遇到问题 → 分析根因 → 判断是 prompt 问题还是代码问题
   - 90% 的情况是代码/流程问题，不是 prompt 问题
