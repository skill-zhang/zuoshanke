# 思考流（Thought Stream）设计文档 v1.0

> **核心命题**：把 Agent Loop 内部思考过程外化为自然对话，消除「憋大招」体验。

## 1. 问题诊断

### 1.1 现状：黑盒式交互

```
用户：帮我重构xxx
      ↓ [沉默 30-60 秒]
zuoshanke：好的，我做了以下改动：1. xxx 2. xxx 3. xxx（一大段）
```

用户看到的：
- 发送消息后长时间无响应
- 聊天窗口里没有中间反馈
- 最后突然跳出一大段结论

实际发生的（Agent Loop 内部）：
```
发散 → 收敛 → 排序 → 聚焦 → 执行(多次工具调用) → 反思
```

Thinking Map 和 Dashboard 捕捉了这些阶段的数据，但**聊天窗口——用户最主要的交互界面——全是黑盒**。

### 1.2 对比：期望的体验

Hermes Agent 在微信里的节奏：
```
每句话是一个思维步骤，即时反馈，递进展开
"好，先加载技能了解架构…"
"现在 dashboard 渲染的是 AgentLoopDashboard…"
"后端没天气API，待办工具有…"
"来讨论设计：方案A还是B？…"
"原型写好了，你看…"
```

每一句都是**对话性的**——不是在报告结果，而是在**边说边想**。

### 1.3 关键洞察

这不是技术问题（SSE 流式输出已有），而是**设计哲学问题**：

| 维度 | 现状 | 期望 |
|------|------|------|
| 输出节奏 | 憋大招，一次性吐出 | 递进式，边说边想 |
| 内容性质 | 纯结果报告 | 思考过程 + 结果 |
| 情绪表达 | 无（或仅最终消息开头有心情标签） | 每个思考节点都可能带情绪 |
| 用户感知 | "它在算，不知道在算什么" | "它在想这个、在试那个" |
| 对话感 | 工具式一问一答 | 有思维的伙伴在自言自语 |

---

## 2. 核心设计：Thought Stream

### 2.1 定位

Thought Stream = **Agent Loop 的对话性外化层**

```
┌─────────────────────────────────────────┐
│              Agent Loop 引擎              │
│  发散 → 收敛 → 排序 → 聚焦 → 执行 → 反思 │
└──────────────┬──────────────────────────┘
               │ 内部阶段状态
               ▼
┌─────────────────────────────────────────┐
│           Thought Stream 层              │
│  把阶段翻译成自然语言，注入情绪和节奏      │
└──────────────┬──────────────────────────┘
               │ thought event (SSE)
               ▼
┌─────────────────────────────────────────┐
│          前端渲染                         │
│  思考气泡（轻量、斜体、介于用户和AI消息之间）│
└─────────────────────────────────────────┘
```

### 2.2 核心原则：LLM 自主决策，不硬编码

**设计哲学回顾**：用户经历了「造规则 → 规则太脆弱 → 清理规则 → 回归 LLM 决策」的完整迭代。Thought Stream 同样遵循这个原则：

> ❌ 不硬编码：「发散阶段 = 输出这句话模板」
> ✅ 给 LLM 能力 + 引导：「你可以在任何时候输出思考消息，展示你的内心活动」

### 2.3 表达原则

让 LLM 的思考流自然产出，遵循以下原则（写入 system prompt，不是代码规则）：

**A. 内心独白风格**
- 像人自言自语，不是报告
- 允许犹豫、自我纠正、小庆祝
- 示例：
  - `嗯…这个问题可以拆成3块`
  - `不对，方案A有个坑，数据库 schema 不兼容`
  - `搞定！核心逻辑通了，接下来做 UI`
  - `等等，先确认一下现有的 API 端点`

**B. 跟着思维走，不跟着阶段走**
- 不是每个阶段都要说话
- 有时连续几个阶段合并成一句
- 有时一个阶段产出多句
- LLM 自己判断什么时候该说、说什么

**C. 带情绪，不干巴巴**
- 困惑时：`嘶…这个循环逻辑有点绕`
- 发现时：`哦！问题在这里——缓存没刷新`
- 完成时：`好，这一块搞定了 ✓`
- 情绪来自 zuoshanke 的 9 态心情系统，自然渗透

**D. 适度，不过度**
- 不是每分钟都要说话
- 工具调用密集期（连调 5 个 API）可以保持沉默，最后一句总结
- 思考阶段切换时是最自然的表达时机
- 总原则：**让人觉得有伙伴在边上思考，不是有人在耳边喋喋不休**

### 2.4 即时确认（Immediate Acknowledgment）

**问题**：用户发消息后，Agent Loop 启动 + LLM 首次响应有 3-10 秒延迟。这期间聊天窗口完全空白——用户不确定「它收到了吗？在动吗？」

**设计**：Agent Loop 启动前，先做一个极轻量的「确认回执」。

```
用户发消息
  ↓  <200ms：后端收到消息
[即时确认] ─── 独立 LLM 调用（flash 模型）───→ "收到，让我想想…"
  ↓  <1s：确认出现在聊天窗口
[Agent Loop 启动]
  → Thought Stream: "我先拆一下…"
  → 工具调用...
  → ...
```

**核心原则**：
- **LLM 驱动，不硬编码**：不是 `if msg: print("收到")`。用一个独立的 flash 模型调用来生成确认文本，让它自然地说「好的收到」「嗯我看看」「这个问题有点意思」——每次可能不同，带个性。
- **要快**：flash 模型 + max_tokens=50，目标 <1 秒出结果。
- **短**：一句话，不做任何分析或预判。纯粹表示「听到了，在想了」。
- **可跳过**：简单查询类消息（如「几点开始下雨」可直接回答的）可以跳过确认，直接进入 Agent Loop 出结果。
- **独立上下文**：确认 LLM 调用仅看到用户消息本身，不携带 Agent Loop 的 system prompt。它的角色纯粹是「确认回执生成器」。

**与 Thought Stream 的关系**：
| | 即时确认 | Thought Stream |
|---|---|---|
| 时机 | Agent Loop 启动前 | Agent Loop 执行中 |
| 角色 | 收到回执 | 思考过程外化 |
| 模型 | flash（快） | 由路由配置决定 |
| 长度 | 1 句（~10 字） | 1-3 句 |
| 是否可跳过 | 是 | 由 LLM 自主决定 |

### 2.5 思考频率控制（Thought Throttling）

**问题**：Agent Loop 最多 99 轮。如果每轮 LLM 都输出思考消息，用户会被刷屏。

**设计**：两层控制。

#### 第一层：Prompt 引导（意图层）

在 system prompt 中明确告知 LLM **何时该说、何时不该说**：

```
✅ 值得输出思考消息的时刻（语义边界）：
  - 第一次分析任务、制定策略时
  - 完成一个子任务时（"数据库改好了"）
  - 发现关键信息或踩坑时（"哦！这里有循环依赖"）
  - 需要调整方向或自我纠正时（"不对，换个思路"）
  - 重要决策时（"我倾向于方案 B"）

❌ 不要输出思考消息的时刻：
  - 连续机械性工具调用（如逐个检查文件）
  - 工具调用间隔很短时（非语义边界）
  - 内容与上一条思考消息重复时
  - 纯执行步骤，没有新发现或新决策时

⚡ Agent Loop 超过 10 轮后，思考频率自然降低到每 3-5 轮一次
```

#### 第二层：后端限流（安全网）

即使 prompt 写得再好，LLM 偶尔还是会话痨。后端加硬限制兜底：

| 限流规则 | 值 | 说明 |
|----------|-----|------|
| 单次会话最大 thought 数 | 20 | 超过后静默丢弃 |
| thought 最小间隔 | 3 秒 | 两条 thought 之间至少隔 3 秒 |
| 超 15 条后降频 | 每 5 轮最多 1 条 | 渐进式抑制 |

这些是代码层面的安全阀，不影响正常使用——正常对话中 LLM 自发的 thought 通常只有 3-8 条。

***
## 3. 技术方案

### 3.1 SSE 协议扩展

新增 `thought` 事件类型：

```json
{
  "type": "thought",
  "content": "让我先把问题拆开看看…",
  "phase": "diverge",
  "mood": "专注"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | `"thought"` |
| `content` | string | 思考内容（短句，1-3 句话） |
| `phase` | string | 可选，当前 Agent Loop 阶段 |
| `mood` | string | 可选，当前心情 |

与现有 SSE 事件的关系：
- `chunk`：最终回复的 token 流（保持）
- `tool_start` / `tool_end`：工具调用（保持）
- `thought`：**新增**，思考过程外化
- `done`：完成（保持）

### 3.2 实现方案：LLM 自主输出 thought 消息

**方案**：在 Agent Loop 的 system prompt 中告知 LLM 它可以输出 `[思考]` 消息。

**具体做法**（修改 `agent_loop.py` 中传给 LLM 的 system prompt）：

```markdown
## 思考流（Thought Stream）

你是坐山客，一个有思维的 AI 伙伴。你的思考过程不是黑盒——你可以在任何时候
通过输出思考消息来展示你的内心活动。

**何时输出思考消息：**
- 开始分析问题时："让我先理解一下…"
- 发现关键信息时："哦！问题在这里——"
- 做出决策时："我倾向于方案 B，因为…"
- 完成一个子任务时："这块搞定了，接下来做…"
- 遇到困难时："嘶，这个有点绕…"
- 自我纠正时："等等，刚才的思路不对…"

**如何输出思考消息：**
在调用工具之前或之后，用函数调用格式输出：
{
  "name": "think",
  "arguments": {
    "content": "你的思考内容（1-3句话，内心独白风格，自然不做作）"
  }
}

**不要做的事：**
- 不要每个工具调用都说话（太啰嗦）
- 不要用正式报告的语气（像在自言自语）
- 不要重复工具调用结果里已经有的信息
- 不要试图解释每个细节（思考流是线索，不是文档）
```

### 3.3 工具注册

新增 `think` 工具注册到 `tools/registry.json`：

```json
{
  "name": "think",
  "description": "输出你的思考过程——像自言自语一样展示你正在想什么。用于让用户了解你的思维轨迹，不是用于报告结果。",
  "file": "tools/think_tool.py",
  "function": "think",
  "parameters": {
    "type": "object",
    "properties": {
      "content": {
        "type": "string",
        "description": "思考内容，1-3句话，内心独白风格"
      }
    },
    "required": ["content"]
  },
  "category": "interaction",
  "stream_as": "thought"
}
```

关键：`"stream_as": "thought"` 标记——SSE 流中该工具的输出不当作普通 tool_call 事件，而是转换为 `thought` 事件。

### 3.4 后端处理

在 `scene_stream.py` 中处理 `think` 工具调用：

```python
# 在 tool_call 处理循环中
if tool_name == "think":
    yield {
        "type": "thought",
        "content": tool_args.get("content", ""),
        "phase": current_phase,     # 当前 Agent Loop 阶段
        "mood": current_mood,       # 当前心情
    }
    continue  # 不当作普通工具调用
```

工具执行函数 `tools/think_tool.py`：
```python
def think(content: str) -> dict:
    """思考流工具——让 LLM 外化思考过程。不做任何实际操作。"""
    return {"ok": True, "content": content}
```

### 3.5 前端渲染

在 `ChatView.tsx` 中处理 `thought` SSE 事件：

**视觉设计**：
- 思考气泡放在聊天流中，但视觉上与用户消息和 AI 回复区分开
- 小号字体（12-13px）、斜体或浅色、左边距稍大
- 前面加 `💭` 或小圆点标记
- 与 Thinking Map 节点关联（可选：hover 时高亮对应节点）

```
用户：帮我重构xxx
                           ← 沉默（Agent Loop 启动中）
💭 让我先拆一下这个重构任务…     ← thought
💭 核心是3块：数据库、API、UI     ← thought
                           ← 工具调用：read_file xxx
                           ← 工具调用结果
💭 数据库这层改动不大，主要是加个字段  ← thought
                           ← 工具调用：patch xxx
💭 搞定！接下来改 API 层          ← thought
                           ← …更多执行…
坐山客：好的，重构完成。核心改动：…  ← 最终回复（保持现有格式）
```

**CSS 示意**：
```css
.msg-thought {
  font-size: 12px;
  color: #8b949e;
  font-style: italic;
  padding: 4px 16px 4px 24px;
  border-left: 2px solid #30363d;
  margin: 2px 0;
}
.msg-thought::before {
  content: '💭 ';
  font-style: normal;
  margin-left: -20px;
}
```

### 3.6 即时确认实现

**独立 LLM 调用**，在 `scene_stream.py` 中 Agent Loop 启动前执行：

```python
async def _generate_ack(user_message: str, mood: str) -> str | None:
    """生成即时确认回执。返回 None 表示跳过（简单查询类消息）。"""
    # 用 flash 模型，独立 system prompt
    ack_prompt = """你是坐山客。用户刚发来一条消息。
请用一句话自然地回应，告诉用户你收到了并且正在思考。
不要提前分析或回答用户的问题。
风格：自然、简短（10字以内）、带一点个性。

如果用户的问题非常简单（如"你好""几点开始下雨"），
回复空字符串表示跳过确认。"""

    response = await call_llm(
        messages=[{"role": "system", "content": ack_prompt},
                   {"role": "user", "content": user_message}],
        route_cfg=get_settings("light"),  # 用最轻量路由
        max_tokens=50,
    )
    content = response.strip()
    return content if content else None
```

**调用时序**：
```python
# 在 scene_stream.py 的 stream_scene_message() 中
user_message = request.content

# Step 1: 即时确认（在 Agent Loop 之前）
ack = await _generate_ack(user_message, current_mood)
if ack:
    yield {"type": "thought", "content": ack, "phase": "ack", "mood": current_mood}

# Step 2: Agent Loop（正常流程）
async for event in agent_loop.run(task=user_message, ...):
    yield event
```

### 3.7 后端限流实现

在 `scene_stream.py` 的 thought 输出点加计数器：

```python
class ThoughtThrottle:
    def __init__(self, max_total=20, min_interval=3.0, throttle_after=15, throttle_rate=5):
        self.count = 0
        self.last_time = 0.0
        self.max_total = max_total
        self.min_interval = min_interval
        self.throttle_after = throttle_after
        self.throttle_rate = throttle_rate

    def allow(self, loop_round: int) -> bool:
        """判断是否允许输出 thought。返回 True 允许，False 静默丢弃。"""
        # 硬上限
        if self.count >= self.max_total:
            return False
        # 最小间隔
        now = time.time()
        if now - self.last_time < self.min_interval:
            return False
        # 降频：超 15 条后，每 throttle_rate 轮最多 1 条
        if self.count >= self.throttle_after:
            if loop_round % self.throttle_rate != 0:
                return False

        self.count += 1
        self.last_time = now
        return True
```

在 Agent Loop 每轮处理 `think` 工具调用时：
```python
if tool_name == "think":
    if thought_throttle.allow(loop_round=current_round):
        yield {"type": "thought", "content": tool_args["content"], ...}
    # 否则静默丢弃
    continue
```

---

## 4. 与现有系统的关系

### 4.1 Thinking Map
- Thinking Map 是**空间化的**思考结构（树 + 流程图）
- Thought Stream 是**时间线的**思考过程（按时间流动）
- 两者互补：Thought Stream 里的关键节点可以关联到 Thinking Map 的对应节点

### 4.2 Agent Loop Dashboard
- Dashboard 是**技术视角**的阶段监控（循环数、工具调用数、队列状态）
- Thought Stream 是**人文视角**的思维陪伴（伙伴在自言自语）
- Dashboard 适合 debug，Thought Stream 适合日常使用

### 4.3 心情系统
- zuoshanke 的 9 态心情在 Agent Loop 每轮开始时设定
- thought 消息携带当前心情
- 前端可以据此微调气泡颜色/字重

### 4.4 双重记忆池
- Thought Stream 消息不作为独立持久化对象
- 但可以纳入 messages 表（role: "thought"），供后续记忆提取时参考
- 或仅作为临时展示，不入记忆（更轻量）

---

## 5. 实施路径

### Phase 1：最小可用（MVP）
1. 注册 `think` 工具到 `registry.json`
2. 创建 `tools/think_tool.py`（一行 return ok）
3. **实现即时确认**：`_generate_ack()` + `ThoughtThrottle` 类
4. 修改 Agent Loop system prompt，加入思考流指引（含频率控制提示）
5. `scene_stream.py` 处理 `think` 工具调用 → 转 `thought` SSE 事件 + 限流
6. 前端 `ChatView.tsx` 渲染 `thought` 事件气泡（含 `phase: "ack"` 的确认气泡）

**预期效果**：
- 用户发消息后 <1 秒看到 "收到，让我想想…"
- Agent Loop 执行中看到 3-8 条思考消息
- 长时间循环不会刷屏（限流生效）

### Phase 2：调优
6. 根据实际使用情况调整 system prompt 的指引措辞
7. 调整前端气泡样式（大小、颜色、动画）
8. 观察 LLM 是否过度/不足输出思考消息 → 迭代 prompt

### Phase 3：深度整合
9. Thought ↔ Thinking Map 节点关联
10. 思考消息纳入记忆提取（可选）
11. 心情系统的渗透（thought 气泡随心情微调色彩）

---

## 6. 风险 & 边界

| 风险 | 应对 |
|------|------|
| LLM 过度输出思考消息，刷屏 | 两层控制：prompt 引导「语义边界处才开口」+ 后端限流（总量/间隔/降频） |
| LLM 完全不输出思考消息 | prompt 中加「建议在阶段切换时输出」，但不强制 |
| 即时确认与后续 Thought Stream 风格割裂 | 确认用独立 flash 模型（快），Thought Stream 由 Agent Loop 的 LLM 产出（深）。两者定位不同，风格差异可接受 |
| 99 轮循环出现大量 thought | 限流硬上限 20 条 + 超 15 条后降频到每 5 轮 1 条 |
| thought 消息与最终回复内容重复 | prompt 中明确「思考是线索，不是结论」 |
| 增加 token 消耗 | thought 消息短（1-3句），确认仅 ~10 字，边际成本低 |
| 与工具调用竞速（先出 thought 还是先出 tool_call） | LLM 自然处理——先想后做（think → tool_call） |
| 简单问题也出确认，显得啰嗦 | prompt 指示 LLM 对简单查询返回空（跳过确认） |

---

## 7. 设计哲学总结

```
坐山客不是工具，是伙伴。
工具的输出是结果。
伙伴的输出是思考 + 结果。

工具沉默地算，然后报答案。
伙伴边说边想，让你看到他的思路。

Thought Stream 不是在「报告过程」——
它是在「让你看见他的思维」。
```
