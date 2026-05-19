# Schema v0.6 — Context 管线修复：恢复提示词分层架构

> 版本: v0.6  
> 日期: 2026-05-20  
> 状态: 方案已定，待实现  
> 关联文件: `agent_core/context_builder.py`, `agent_core/agent_loop.py`, `router/scenes.py`

---

## 一、背景

### 原点

坐山客最初有一套完整的 Context 构建管线 —— `context_builder.py` 的 `build_scene_context()`：

```
[System] DB场景prompt + 用户背景 + skill块 + 工具列表 + 使用说明
[Assistant] 工具结果（预执行）
[User] 记忆块（"仅供参考"标记） + 天气桥接 + 用户消息
```

这套管线实现了清晰的**三层提示词分层**：
- **System Prompt 层（铁律）** — 角色定义 + 技能 + 工具列表
- **Assistant 层** — 预执行工具结果（仅预执行模式）
- **User Prompt 层（仅供参考）** — 记忆块（带免责声明） + 用户消息

### 变迁

2026-05-19，场景聊天从预执行模式全量迁移到 Agent Loop。Agent Loop 有自己的消息构建方式：

```python
# agent_loop.py: run_agent_loop()
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": task},
]
# 然后逐轮追加 assistant(tool_calls) + tool(results)
```

迁移时只把 task 和 system_prompt 带进来了，**context_builder 的整条管线被跳过了**。

### 迭代历程（从问题发现到根因确认）

| 迭代 | 做了什么 | 问题 |
|------|---------|------|
| 1 | 向 `scene_agent_prompt` 硬编码追问原则 | ❌ 另起炉灶，绕过 DB |
| 2 | 追问原则移到 `context_builder.SCENE_SYSTEM_PROMPT` | ⚠️ 修了 DB bypass，但分层仍然断裂 |
| 3 | 分析后发现 → 不是常量问题，是**整条管线断了** | ✅ 根因确认 |

---

## 二、当前架构（v0.5，有问题）

```
stream_scene_message()
  │
  ├─ scene_agent_prompt = context_builder.SCENE_SYSTEM_PROMPT    ← 只拿了个常量字符串
  │    + user_context
  │
  └─ run_agent_loop(task=data.content, system_prompt=scene_agent_prompt)
       │
       └─ Agent Loop 内部：
            [System] scene_agent_prompt     ← 无 skill 块、无工具列表文本
            [User]   原始 data.content      ← 无记忆块
            [tool calls loop]
```

### 断层的层

| 内容 | 在 `build_scene_context()` 中 | 在 Agent Loop 路径中 |
|------|-----------------------------|---------------------|
| System: DB场景prompt | ✅ | ✅（刚修好） |
| System: skill块 | ✅ | ❌ 丢失 |
| System: 工具列表文本 | ✅ | ❌ 丢失 |
| System: 使用说明 | ✅ | ❌ 丢失 |
| User: 记忆块（"仅供参考"） | ✅ | ❌ 丢失 |
| User: 天气桥接 | ✅ | ❌ 丢失 |

### 根本原因

`run_agent_loop()` 的函数签名只接受 `system_prompt: str` + `task: str` + `memory_context: str`，无法接收 `build_scene_context()` 产出的结构化消息列表。这两套消息构建机制**完全不兼容**。

---

## 三、目标架构（v0.6）

### 核心改动点

| 改动 | 文件 | 说明 |
|------|------|------|
| ① 新增 `build_agent_context()` | `context_builder.py` | 为 Agent Loop 路径构建上下文，共享分层逻辑 |
| ② 新增 `initial_messages` 参数 | `agent_loop.py` | 接收预构建的消息列表作为循环起点 |
| ③ 改用 `build_agent_context()` | `scenes.py` | 替代硬编码 prompt，走正确分层 |

### ① `build_agent_context()` — 新增

```python
def build_agent_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    user_context: Optional[str] = None,
    db=None,
) -> list[dict]:
```

与 `build_scene_context()` 的区别：

| 步骤 | `build_scene_context`（预执行用） | `build_agent_context`（新） |
|------|--------------------------------|----------------------------|
| 1. System prompt | DB场景prompt → 兜底 | 同左 |
| 1.5 用户背景 | ✅ user_context | 同左 |
| 2. 记忆块 | → User 层"仅供参考" | 同左 |
| 3. 技能块 | → System 层 | 同左 |
| 4. 工具列表 | `match_tools()` 自动匹配 | 同左，但过滤 `_EXCLUDED_TOOLS` |
| 5. 使用说明 | 「系统已自动执行了工具…」 | 「你可以调用工具…」+ 工具调用流程说明 |
| 6. 工具结果 | ✅ Assistant 角色 | ❌ 跳过（LLM 自主调工具） |
| 7. 历史消息 | ✅ | 同左 |
| 8. 用户消息 | 记忆块 + 天气桥接 + 用户内容 | 同左 |

### ② `run_agent_loop()` — 新增 `initial_messages` 参数

```python
def run_agent_loop(
    task: str = "",
    memory_context: str = "",
    tools: Optional[list[dict]] = None,
    model: str = "flash",
    max_steps: int = 25,
    system_prompt: Optional[str] = None,
    initial_messages: Optional[list[dict]] = None,  # 🆕
) -> Generator[dict, None, None]:
```

行为：

- **`initial_messages` 有值**：用它替换 `[system_prompt] + [task]` 构造的初始消息，直接作为循环起点
- **`initial_messages` 为 None**：保持现有行为（`system_prompt` → `build_agent_system_prompt` 兜底 + `task` 作为首条 user msg）

Agent Loop 的 tool calling 循环逻辑不变 —— 在初始消息列表末尾逐条追加 `assistant(tool_calls)` + `tool(result)`。

### ③ `stream_scene_message()` — 改用新管线

```
原有：
  scene_agent_prompt = scene_sp + user_ctx
  run_agent_loop(task=data.content, system_prompt=scene_agent_prompt)

改为：
  messages = build_agent_context(
      user_content=data.content,
      history_messages=history_messages,
      user_context=scene.user_context,
      db=db,
  )
  # scene_agent_prompt 变量移除
  run_agent_loop(initial_messages=messages)
```

**注意**：`build_agent_context()` 内部已经处理 DB 读取 + 兜底，`stream_scene_message()` 不再需要单独读 SCENE_SYSTEM_PROMPT。

---

## 四、恢复后的分层结构

```
stream_scene_message()
  │
  └─ build_agent_context(db=db)
       │
       ├─ [System] DB场景prompt / SCENE_SYSTEM_PROMPT(兜底)     ← 铁律层
       │    + user_context
       │    + skill_block（匹配到的可复用知识）
       │    + tools_text（工具列表，过滤排除项）
       │    + usage_instructions（LLM自主调工具说明）
       │
       └─ [User] 记忆块「仅供参考，不相关可忽略」                ← 仅供参考层
            + 天气桥接（如有）
            + 用户消息
              │
              └─ → Agent Loop（initial_messages）
                   │
                   ├─ [assistant(tool_calls)]  → LLM 决定调工具
                   ├─ [tool(results)]           → 工具执行结果
                   └─ 循环直到 [assistant: 最终回复]
```

---

## 五、调用方影响矩阵

| 调用方 | 当前方式 | v0.6 变化 |
|--------|---------|-----------|
| `stream_scene_message()`（场景消息） | 硬编码 `scene_agent_prompt` → `run_agent_loop(system_prompt=...)` | 改为 `build_agent_context()` → `run_agent_loop(initial_messages=...)` |
| 频道消息（channel） | 不走 Agent Loop | ❌ 不受影响 |
| 直接调 `run_agent_loop()`（如 API `/api/agent-loop/stream`） | 无 `initial_messages` | ❌ 不受影响，默认行为不变 |
| 旧预执行路径 `agent_core_light_stream()` | 内部调 `build_scene_context()` | ❌ 不受影响 |

---

## 六、实施步骤

1. **`context_builder.py`** — 新增 `build_agent_context()`，复制 `build_scene_context()` 骨架，修改步骤 5（使用说明）和 6（跳过工具结果）
2. **`agent_loop.py`** — `run_agent_loop()` 新增 `initial_messages` 参数，在函数开头判断：有则用它替代初始消息构建
3. **`scenes.py`** — `stream_scene_message()` 中移除 `from agent_core.context_builder import SCENE_SYSTEM_PROMPT` 和 DB 读取逻辑，改为：
   ```python
   from agent_core.context_builder import build_agent_context
   messages = build_agent_context(...)
   agent_stream = run_agent_loop(initial_messages=messages)
   ```
4. 验证：发场景消息 → 后台日志应有记忆块注入 → Thinking Map 自动发散正常

---

## 七、风险与边界

1. **不与现存改动冲突** — `build_agent_context()` 是新函数，不动 `build_scene_context()`
2. **频道不受影响** — 频道没有走 Agent Loop
3. **LLM 自主调工具的提示要合适** — 使用说明不能写成「系统已自动执行」，要写「你可以调用以下工具」
4. **工具列表过滤** — `match_tools()` 会返回全部匹配工具，需要在 `build_agent_context()` 中过滤 `_EXCLUDED_TOOLS`，与 `agent_loop.build_tool_definitions()` 保持一致
5. **记忆块位置不变** — 仍放在 User 层带「仅供参考」标记，不升级到 System 层
6. **记忆块不传给频道** — 只在场景路径注入

---

## 八、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.5 | 2026-05-19 | 场景全走 Agent Loop，但 context_builder 管线断裂 |
| v0.6 | 2026-05-20 | 修复：`build_agent_context()` + `initial_messages` 参数，恢复三层分层 |
