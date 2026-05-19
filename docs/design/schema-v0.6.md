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

## 八、Dialog Engine — 对话阶段引擎（架构前瞻）

2026-05-20 确定方向。当前未实现，作为 v0.6 扩展阶段规划。

### 8.1 背景

坐山客的终极愿景：**用户感觉在和一个专家级伙伴一起工作，不是问答题机器。**

现状差距：
- **复杂度无感知**：所有问题走同一条路。简单问题过度复杂化，复杂问题不够深入。
- **引导无结构**：只有一句「先追问」的 prompt，没有阶段意识。
- **Thinking Map 是展示品**：不是协作板，用户被动接收。
- **讨论无进度管理**：多轮对话间无法承接讨论进度。

### 8.2 架构

```
用户输入
  │
  ├─ [Dialog Engine 入口] 复杂度检测（LLM 自主判断）
  │    ├─ 简单 → 直接走 Agent Loop 回答
  │    └─ 复杂 → 进入阶段引导模式
  │
  ├─ 阶段状态机（agent_core/dialog_engine.py）
  │    EXPLORE → FOCUS → CHALLENGE → FINALIZE → DECOMPOSE → EXECUTE
  │    ↑  每个阶段有独立引导策略 + 状态转移规则
  │    ↑  转移条件由 LLM 输出 + 用户输入信号共同驱动
  │
  ├─ 对 LLM 只暴露一行：「当前阶段: EXPLORE — 探索你的核心需求」
  │    阶段的逻辑在代码中，不在 prompt 中（机制驱动）
  │
  ├─ 持久化：dialog_state 表 + 进度快照
  │
  └─ 跨会话恢复：开场自动回溯上次讨论进度
```

### 8.3 6 阶段定义

| 阶段 | 名称 | LLM 角色 | 行为 | 转移到下一阶段的条件 |
|------|------|----------|------|---------------------|
| EXPLORE | 探索需求 | 引导师 | 开放式追问，弄清用户在解决什么根本问题 | 用户明确说了几个关键需求点 |
| FOCUS | 聚焦目标 | 分析师 | 「按你刚才说的，核心目标是不是这3个？」确认 | 用户确认了目标范围 |
| CHALLENGE | 方案博弈 | 参谋 | 提出 2-3 个方案对比（快VS稳、贵VS省），让用户决策 | 用户做出了一个方案选择 |
| FINALIZE | 定稿 | 记录员 | 总结确定的约束/方案，形成明确文档 | 用户说「好的」「就这样」 |
| DECOMPOSE | 拆解任务 | 项目经理 | 拆成 Action Map，排优先级和依赖 | Action Map 就绪 |
| EXECUTE | 执行 | 执行引擎 | Agent Loop 逐步行动，报告进度 | 全部完成 |

### 8.4 核心原则

- **零用户感知切换**：入口就是一个对话框，AI 自动判断走简单/引导模式。
- **结构在代码，提示在一行**：几千行的阶段机代码 → LLM 只读一行当前阶段。
- **机制驱动不 prompt 驱动**：阶段逻辑放在 `dialog_engine.py`，不从 prompt 衍生。
- **跨会话承接**：dialog_state 表记录每次讨论要点，下次开始自动回顾。

---

### 8.5 现状差距：一个活案例

场景：「查二手车」对话（2026-05-20 测试）

**现状**（用户输入"我想做二手车买卖"后）：

```
AI 回复一篇2000字攻略：
  平台排名、真实性判断方法、
  入行建议、风险提示……
```

✅ 内容质量过关 ✅ 有结构 ✅ 信息量充足
❌ **像论文摘要，不像对话**
❌ 一次性倒出所有信息 → 用户没有参与感
❌ 该有的对话节奏感完全缺失

**理想的引导模式**：

```
AI：你刚入行？是想收车转卖还是代客找车？
     这两个路线资源需求差别很大。
User：收车转卖吧，但我没车源
AI：明白。那先确定你要找什么价位的车？
     5万以下练手车还是10万左右走量？
User：先10万左右的练手
AI：好的，那咱们的目标是：10万以内收车转卖，缺车源渠道。
     核心约束是：新手入行，预算有限，先跑通模式再扩大。
     接下来我帮你列几个常用的车源平台，你根据自己所在城市判断哪个最方便……
```

差距本质：**不是信息不足，是对话结构缺失。** 用户需要被引导着一起思考，而不是收到一份报告。

---

### 8.6 实现路线

#### Phase 0（地基）— 当前阶段目标

最小可验证产品：让 Agent Loop 知道「当前在什么阶段」，能感知阶段变化。

| 步 | 文件 | 做什么 |
|----|------|--------|
| ① | `models.py` | 新增 `DialogState` 表（scene_id, phase, summary, decisions, context, created_at, updated_at） |
| ② | `agent_core/dialog_engine.py` | 基础阶段机：4 阶段简化版（EXPLORE → FOCUS → FINALIZE → EXECUTE），提供 get_phase_prompt() 和 detect_transition() |
| ③ | `agent_loop.py` | `run_agent_loop()` 中插入 get_phase_prompt() 一行到 system prompt |
| ④ | `scenes.py` | 场景消息入口中初始化/恢复 DialogState |

**4 阶段简化版**（跳过 CHALLENGE 和 DECOMPOSE，后续迭代加）：

| 阶段 | LLM 角色 | 行为 |
|------|----------|------|
| EXPLORE | 引导师 | 开放式追问，一次只聚焦一个问题，弄清用户在解决什么 |
| FOCUS | 分析师 | 总结已知信息，确认核心目标 |
| FINALIZE | 记录员 | 输出明确的方案摘要，形成约束清单 |
| EXECUTE | 执行引擎 | Agent Loop 按计划执行 |

**MVP 验证**：自测一个复杂问题（如「想做个 AI 写作助手」），看：

```
[阶段: EXPLORE] 你说的AI写作助手，是想帮你写什么类型的内容？
↓
用户：公众号文章吧
↓
[阶段: FOCUS] 好，那核心需求是：公众号文章写作助手。
             还有什么其他约束吗？比如字数、风格、频率？
↓
用户：每周3篇，2000字左右
↓
[阶段: FINALIZE] 确定方案：公众号写作助手，每周×3，2000字/篇。
                接下来开始动手做……
```

**复杂度检测**：不做硬编码规则。LLM 自主判断「这个问题需要进入引导模式吗？」第一版最简单方案——不进阶段机就是简单。只有 LLM 认为「需要」才创建 dialog state。

#### 后续迭代（Phase 1+）

| Phase | 新增 |
|-------|------|
| 1 | CHALLENGE 阶段 + DECOMPOSE 阶段。完整的 6 阶段状态机 |
| 2 | Thinking Map 协作编辑 — Agent Loop 能通过 tool-calling 修改 TM 节点 |
| 3 | 跨会话恢复 — 新会话开场自动回溯上次讨论进度和决策 |
| 4 | 阶段感知的 SSE 事件 — 前端展示当前阶段和进度 |
| 5 | 对话进度可视化 — 在场景聊天界面显示阶段进度条 |

---

### 8.7 当前阶段任务

**核心改动文件**：

| 文件 | 改动 | 估计行数 |
|------|------|---------|
| `models.py` | 新增 DialogState 模型 | ~30 |
| `agent_core/dialog_engine.py` | 新建：阶段机核心 | ~120 |
| `agent_loop.py` | 注入 get_phase_prompt() | ~15 |
| `scenes.py` | 初始化/恢复 dialog state | ~15 |

**可逆性**：所有新增代码不修改现有行为。DialogState 表 zero-downtime `create_all()`。dialog_engine.py 完全独立，不改变 Agent Loop 逻辑。移除只需删除引用和表。

**不做的**：
- ❌ 不修改前端（阶段信息通过 system prompt 注入，LLM 回复自然包含阶段提示）
- ❌ 不做复杂度检测规则（LLM 自主判断）
- ❌ 不做 Thinking Map 联动（Phase 2+）
- ❌ 不做跨会话恢复（Phase 3+）

---

## 九、记忆系统重构 v2 — LLM 自主管理 + 工具化

> 日期: 2026-05-20
> 状态: 方案已定，待实现
> 关联文件: `tools/memory_tool.py`（新建）, `agent_core/memory_extractor.py`, `agent_core/context_builder.py`, `tools/registry.json`

### 9.1 原系统问题

坐山客的记忆系统（MemoryExtractor + MemoryManager）核心问题：

| 问题 | 根因 | 表现 |
|------|------|------|
| 后台偷偷塞 | `_fast_path()` 关键词匹配自动创建，用户无感知 | 用户没说要记也被记了 |
| 规则的不可靠 | `_extract_fact()` 正则模式有限，漏匹配/错匹配 | 该记的不记，不该记的记了 |
| key 不稳定 | LLM 每次生成不同 key，精确匹配无效 | 同一事实反复创建多条 |
| 无内容级去重 | `mm.get(key)` 是唯一去重手段 | 内容相似但 key 不同 = 两条记录 |
| 提取时机过频 | 每次对话结束都跑一次 LLM 提取 | 昨天记了今天又记 |

### 9.2 目标架构

核心转变：**从后台代码自动提取 → LLM 自主调 memory 工具管理记忆。**

```
旧模式：
  对话结束 → MemoryExtractor._fast_path（正则匹配）
           → MemoryExtractor._call_extraction_llm（后台偷偷跑）
           → 直接 mm.add() 入库
           
新模式：
  对话中 → LLM 自主判断「这条该记吗？」
         → 如果该记 → 调 memory(action='add') 工具入库
         → 每次调 memory 工具也是对话的一部分
         → MemoryExtractor.LLM 通道降级为辅助补充
         → 快速通道完全删除
```

### 9.3 核心改动

#### ① 新增 `memory` 工具（`tools/memory_tool.py`）

```json
{
  "name": "memory",
  "description": "管理长期记忆——add 存新信息、read 查看已有记忆、replace 更新、remove 删除。每次写入前建议先 read 确认没有重复。",
  "parameters": {
    "action": {"type": "string", "enum": ["add", "read", "replace", "remove"]},
    "target": {"type": "string", "enum": ["memory", "user"]},
    "content": {"type": "string", "description": "记忆内容（add/replace 时必需）"},
    "old_text": {"type": "string", "description": "要替换/删除的旧记忆文本片段（replace/remove 时必需）"},
    "key": {"type": "string", "description": "可选：记忆的唯一标识键，不传则自动生成"}
  },
  "required": ["action", "target"],
  "preexecute": {"enabled": false}
}
```

行为：

- **add(target, content, key?)** — 写入前检查 `content` 是否已存在（fuzzy match），已存在则强化不创建
- **read(target)** — 返回当前所有记忆，格式化与 system prompt 注入一致
- **replace(target, old_text, content)** — 查找含 old_text 的条目并替换
- **remove(target, old_text)** — 删除含 old_text 的条目

#### ② MemoryExtractor 改造

| 原能力 | 变化 |
|--------|------|
| `_fast_path()`（关键词"记住"） | ❌ 完全删除 |
| `_infer_topic_from_pattern()` | ❌ 完全删除 |
| `MEMORY_FAST_TRIGGERS` 配置 | ❌ 删除 |
| 快速通道用到的所有正则模式 | ❌ 删除 |
| LLM 通道 | ⚠️ 保留但改造：不直接 `mm.add()`，改为返回格式化建议让 LLM 自主决定是否调 memory 工具 |
| `EXTRACTOR_SYSTEM_PROMPT` | 保留，指导 LLM 提取值得记的信息 |

LLM 通道改造后：

```python
# 改造后：LLM 通道只生成「建议」，不直接入库
llm_suggestions = self._llm_suggest_memories(conversation)
# 建议格式：[{"key": "...", "content": "...", "confidence": 0.9, "topic": "..."}]
# 这些建议附加到 AI 回复中，让 LLM 自己决定是否调 memory 工具
# [系统将以下内容追加到 AI 回复末尾作为记忆提取建议]
```

#### ③ context_builder.py 系统 prompt 增加记忆能力

在 `build_agent_context()` 的使用说明节末尾添加：

```
## 📝 记忆能力
你可以通过 memory 工具主动管理长期记忆：
- add(key, content) — 你觉得重要的信息存起来，下次会话自动注入
- read() — 查看当前所有记忆
- replace/remove — 旧的或错的自己改
建议：每次 add 新内容前先 read 一次，避免重复。
```

#### ④ registry.json 注册

`memory` 工具 `preexecute: false`（Agent 自主调用），不在 `_excluded_tools` 列表中。

### 9.4 分层定位

```
记忆系统在 Schema v0.6 分层中的位置：

[User Prompt 层] — 记忆块「仅供参考，不相关可忽略」
    └─ 注入方式：_build_memory_block() 从 DB 读取 Top-N 条
    └─ Topic 匹配 + 权重排序（保留原有）

[工具层] — memory 工具（LLM 自主调用）
    └─ add → 入库 → 下次会话自动出现在记忆块中
    └─ read → 查看当前记忆
    └─ replace/remove → 修正/淘汰记忆

[存储层] — MemoryManager（保留原有）
    └─ 权重公式不变：base × recency × frequency × boost
    └─ decay/auto_level/P0-P3 不变
    └─ topic 标签按 LLM 写入时指定
```

### 9.5 实施步骤

| 步 | 文件 | 做什么 |
|----|------|--------|
| ① | `tools/memory_tool.py` | **新建** — memory 工具四个 action 实现 |
| ② | `tools/registry.json` | 注册 memory 工具（preexecute=false） |
| ③ | `agent_core/memory_extractor.py` | 删除 fast path + 改造 LLM 通道 |
| ④ | `config/matching_rules.py` | 删除 `MEMORY_FAST_TRIGGERS`（如需） |
| ⑤ | `agent_core/agent_loop.py` | 确认 memory 不在 `_EXCLUDED_TOOLS` |
| ⑥ | `agent_core/context_builder.py` | 系统 prompt 增加记忆能力说明 |
| ⑦ | 删除不必要的 import | 检查 `channels.py`/`scenes.py` 中的 `MemoryExtractor` 引用 |

### 9.6 可逆性

- 新增文件 `tools/memory_tool.py` 完全独立，不修改任何现有文件
- MemoryExtractor fast_path 删除后，如检测到异常可回滚 git 恢复
- LLM 通道改造为建议模式后，原有 extract 调用方（channels/scenes）不受影响——返回值格式不变

### 9.7 验证

1. 发消息「我叫张三，我喜欢冷色系」→ LLM 应自主调 memory 工具记录
2. `memory(action='read')` → 返回记忆列表
3. `memory(action='add', key='preference_color', content='用户喜欢冷色系')` → 入库成功
4. 新会话 → 记忆块应包含刚存的条目
5. `READ.md` 中没有后台偷偷创建的、用户没要求记的条目
