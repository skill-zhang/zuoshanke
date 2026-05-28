# 坐山客 Schema v1.6 — 可运维设计

> 2026-07-03
> 核心命题：Agent Loop 执行过程可观测、可追溯、可复盘。日志和 DB trace 记录留存 3 天自动轮转，前端实时可视化执行步骤。

---

## 一、问题陈述

### 1.1 当前状态

Agent Loop 在执行过程中有完整的事件数据（`tool_start`、`tool_done`、`tool_error`、`thinking`、`status`），但这些事件**只通过 SSE 流 yield 给前端，不落地到文件或 DB**。

```python
# agent_loop.py — 当前：事件只 yield，不记录
yield {"type": "tool_start", "tool": "run_code", "args": {"code": "..."}}
# 执行工具...
yield {"type": "tool_done", "tool": "run_code", "result": {...}}
```

后端日志文件 `/tmp/zuoshanke-backend.log` 中只有两句：

```
[AgentLoop] temperature=0.3 (from scene_config={})
[AgentLoop] LLM 请求: roles={'system':1, 'user':19, 'assistant':18, 'tool':21} msgs=59 tools=52
```

工具名、参数、返回值、LLM 思考过程 → **全不记录**。

### 1.2 故障场景：分身杀死后端

真实案例（2026-05-28）：分身通过 Agent Loop 部署监控方案时，执行了类似 `fuser -k 8000/tcp` 的命令**杀死了运行中的后端进程**。进程一死：

1. SSE 流断开 → yield 的事件全部丢失
2. 日志文件中只有两行统计，看不到最后执行的命令
3. 唯一能查的工具记录存储在内存的 `messages` 列表中 → 进程死亡 = 证据消失
4. 排查人员（AI 或人类）只能"怀疑"发生了什么

### 1.3 三个缺失

| 缺失项 | 影响 |
|--------|------|
| **文件日志** — 无结构化实时落盘 | 进程崩溃后无据可查 |
| **DB trace 记录** — 无持久化执行轨迹 | 无法跨会话追溯、SSE 离线后无记录 |
| **前端执行面板** — 无实时可视化工具调用 | 用户看不到 LLM 在做什么、卡在哪 |

---

## 二、设计总览

### 2.1 三层记录体系

```
┌─────────────────────────────────────────┐
│          前端执行追踪面板                 │
│  (SSE 分流 → 实时展示工具调用)           │
└────────────────────┬────────────────────┘
                     │ SSE 分流（实时）
                     ▼
┌─────────────────────────────────────────┐
│          agent.log 文件日志              │
│  (JSONL, 实时落盘, 3天轮转)             │
└────────────────────┬────────────────────┘
                     │ 批量写入（每步完成）
                     ▼
┌─────────────────────────────────────────┐
│      agent_loop_traces 表 (SQLite)      │
│  (独立表, 3天 TTL, 只用于复盘)          │
└─────────────────────────────────────────┘
```

### 2.2 设计原则

1. **写穿透** — `agent.log` 在 yield SSE 事件之前写入，即使下一步进程崩溃也能保留最后一行
2. **不离耦合** — trace 数据直接复用 SSE 流，不额外开 WebSocket。SSE 中已有完整事件序列（`tool_start` → `tool_done`/`tool_error` → `thinking`），前端 decode 后 filter 分流即可
3. **不给 LLM 看** — `agent_loop_traces` 表不加入 LLM 的 messages context，独立存储，只用于复盘查询
4. **过期即删** — 日志和 DB trace 均保留 3 天，单人系统日志量不大，不留永久
5. **对 AI 友好** — JSONL 格式每行独立自描述，AI 逐行 parse 即可

---

## 三、agent.log — 文件日志

### 3.1 格式：JSONL

文件路径：`~/zuoshanke/logs/agent.log`

每行一个 JSON 对象，key 全小写蛇形：

```jsonl
{"ts":"2026-05-28T08:30:42.123","scene":"scene-xxx","session":"ws-xxx","step":8,"type":"llm_call","model":"deepseek-v4-flash","msgs":36,"tools":52}
{"ts":"2026-05-28T08:30:44.456","scene":"scene-xxx","session":"ws-xxx","step":8,"type":"llm_response","finish_reason":"tool_calls","usage":{"prompt_tokens":12345,"completion_tokens":678}}
{"ts":"2026-05-28T08:30:44.789","scene":"scene-xxx","session":"ws-xxx","step":8,"type":"tool_start","tool":"run_code","args":{"language":"bash","code":"curl -s http://localhost:8000/api/health"}}
{"ts":"2026-05-28T08:30:45.012","scene":"scene-xxx","session":"ws-xxx","step":8,"type":"tool_done","tool":"run_code","success":true,"result":{"stdout":"{\"status\":\"ok\"}","exit_code":0}}
{"ts":"2026-05-28T08:30:46.789","scene":"scene-xxx","session":"ws-xxx","step":8,"type":"thinking","text":"看起来后端返回了200，说明服务正常..."}
{"ts":"2026-05-28T08:30:47.000","scene":"scene-xxx","session":"ws-xxx","step":9,"type":"tool_start","tool":"run_code","args":{"language":"bash","code":"fuser -k 8000/tcp"}}
```

### 3.2 事件类型

| type | 写入时机 | 额外字段 |
|------|---------|---------|
| `llm_call` | 调 DeepSeek 前 | model, msgs, tools（工具数）, temperature |
| `llm_response` | DeepSeek 返回后 | finish_reason, usage |
| `thinking` | LLM 返回纯文本（非 tool_calls） | text（LLM 想法全文） |
| `tool_start` | execute_tool 之前 | tool, args（完整参数） |
| `tool_done` | 工具执行成功 | tool, success, result（完整返回值）, duration_ms |
| `tool_error` | 工具执行失败 | tool, success, error, duration_ms, high_risk |
| `status` | 每步开始/结束 | message |
| `done` | Agent Loop 完成 | summary, steps, usage |

### 3.3 写入策略

**写穿透**：在 `yield` SSE 事件之前写入文件。例如：

```python
# 在 agent_loop.py 中
_trace_logger.write({
    "ts": now,
    "scene": scene_id,
    "session": session_id,
    "step": step,
    "type": "tool_start",
    "tool": tool_name,
    "args": args,
})
yield {"type": "tool_start", "tool": tool_name, "args": args, ...}
```

这样保证：**即使下一步「工具把进程杀了」，`tool_start` 已经落盘**，最后一行就是犯罪工具。

### 3.4 日志轮转

**天级轮转，保留 3 天**：

```
~/zuoshanke/logs/
├── agent.log          ← 今天
├── agent.log.1        ← 昨天（自动改名）
├── agent.log.2        ← 前天
└── agent.log.3        ← 大前天
```

**轮转时机**：每次写入时检查 `agent.log` 的 mtime，如果不是今天则：
1. `agent.log.3` → 删除
2. `agent.log.2` → 重命名为 `agent.log.3`
3. `agent.log.1` → 重命名为 `agent.log.2`
4. `agent.log` → 重命名为 `agent.log.1`
5. 创建新的 `agent.log`

不依赖 logrotate 等外部工具。

### 3.5 数据完整性

每条记录都是完整的 JSON 行（以 `\n` 结尾）。即使文件在写入过程中被截断（进程崩溃），最后一行可能不完整，但**之前的所有行都可以逐行 parse**。

`tool_start` 在 `execute_tool()` 之前写入 → **最后一行完整 = 能确认当时执行了什么命令**。

---

## 四、agent_loop_traces — DB 记录表

### 4.1 表结构

```sql
CREATE TABLE agent_loop_traces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id    TEXT NOT NULL,
    session_id  TEXT,
    step        INTEGER,
    event_type  TEXT NOT NULL,       -- llm_call | llm_response | tool_start | tool_done | tool_error | thinking | status | done
    tool_name   TEXT,                 -- tool 事件专用
    args_text   TEXT,                 -- 工具参数（JSON 字符串，不对 LLM 注入）
    result_text TEXT,                 -- 工具返回（JSON 字符串，不对 LLM 注入）
    error_text  TEXT,                 -- 错误信息
    thinking_text TEXT,               -- LLM 想法全文
    summary     TEXT,                 -- done 事件的摘要
    duration_ms INTEGER,              -- 工具执行耗时
    metadata    TEXT,                 -- 其他元数据（JSON），如 usage, finish_reason
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 索引：按场景查，按时间倒序
CREATE INDEX idx_traces_scene_time ON agent_loop_traces(scene_id, created_at DESC);

-- 可选：按场景+会话查
CREATE INDEX idx_traces_scene_session ON agent_loop_traces(scene_id, session_id);
```

### 4.2 与 messages 表的隔离

| 维度 | messages 表 | agent_loop_traces 表 |
|------|------------|-------------------|
| 用途 | LLM 对话上下文 | 复盘/定位 |
| 注入 LLM？ | ✅ 是 | ❌ 否 |
| 保留期 | 永久（场景级别） | 3 天 |
| 数据粒度 | 对话摘要 + tool result 摘要 | 完整参数 + 返回值 |
| 行数 | 每轮对话几条 | 每步 3-5 条 |

**不给 LLM 看**：`context_composer.py` 和 `agent_loop.py` 的 prompt 构建逻辑不查询此表。

### 4.3 批量写入策略

每步 Agent Loop 执行完毕后，一次性写入该步的所有 trace 行：

```python
# 伪代码 — 每步收集 trace，步结束时批量 flush
step_traces = [
    {"event_type": "tool_start", "tool_name": "run_code", "args_text": "...", ...},
    {"event_type": "tool_done", "tool_name": "run_code", "result_text": "...", ...},
    {"event_type": "thinking", "thinking_text": "...", ...},
]
db.bulk_insert("agent_loop_traces", step_traces)  # 单条 SQL，一次 commit
```

**极端情况下**（进程在步内崩溃），`tool_start` 已在 `agent.log` 中落盘 → 能从文件日志找回。DB 可能丢失该步，但不丢关键信息。

### 4.4 过期清理

```sql
DELETE FROM agent_loop_traces
WHERE created_at < datetime('now', '-3 days', 'localtime');
```

**清理时机**：每次写入 trace 后 + 后端启动时执行一次（兜底）。

### 4.5 前端 API：查询 trace

```
GET /api/scenes/{scene_id}/traces?limit=200&offset=0
```

返回 `agent_loop_traces` 按 `created_at DESC` 排序的最新记录。前端追踪面板打开时加载最近的 trace，SSE 流实时补充新事件。

---

## 五、前端执行追踪面板

### 5.1 交互设计

```
┌─────────────────────────────────────────────────┐
│  聊天区域              │ 🔄 执行追踪 ☰          │
│                        │                        │
│ 用户: 部署监控方案      │ ─── 第 1 步 ───────── │
│                        │ 💭 分析需求，决定先检  │
│ AI: 我推荐Uptime Kuma  │   查当前服务状态       │
│                        │                        │
│                        │ ─── 第 2 步 ───────── │
│                        │ 💭 先 curl 检查各端口  │
│                        │ ⚡ run_code            │
│                        │   bash: curl -s ...    │
│                        │   ✅ {status: ok}      │
│                        │                        │
│                        │ ─── 第 3 步 ───────── │
│                        │ 💭 部署 Uptime Kuma... │
│                        │ ⚡ run_code            │
│                        │   bash: docker run...  │
│                        │   ❌ 连接超时          │
│                        │                        │
│                        │ ⏸ 完成 · 3 步 · 12 工具│
└─────────────────────────────────────────────────┘
```

### 5.2 组件树

```
AgentTracePanel                     ← 右侧抽屉容器
├── AgentTraceHeader                ← 标题 + 关闭按钮 + 统计
│   ├── step_count: "3 步"
│   ├── tool_count: "12 工具调用"
│   └── status: "已完成 / 运行中 / 出错"
├── AgentTraceStep[]                ← 按 step 分组，可折叠
│   ├── StepHeader                  ← "第 N 步" + 耗时 + 状态图标
│   ├── ThinkingCard                ← 💭 LLM 思考过程
│   │   └── text                    ← 全文（可展开/折叠）
│   ├── ToolCallCard[]              ← ⚡ 工具调用卡片
│   │   ├── ToolHeader              ← 工具名 + 耗时
│   │   ├── ToolArgs                ← 参数（默认折叠，点开展开）
│   │   └── ToolResult              ← 结果（成功/失败 + 返回值）
│   └── ...更多事件
└── AgentTraceFooter                ← 底部信息（展开全部/收起全部）
```

### 5.3 核心状态管理

```typescript
// Store — 与 chat store 独立，但通过 SSE 事件源连接
interface TraceStore {
  // key=sceneId, value=按时间排序的 trace 事件
  tracesByScene: Map<string, TraceEvent[]>;
  
  // UI 状态
  isPanelOpen: boolean;
  expandedSteps: Set<number>;    // 展开的 step 编号
  expandedArgs: Set<string>;     // 展开的参数（格式: "step-toolName"）
  
  // 统计
  summary: {
    totalSteps: number;
    totalTools: number;
    status: 'running' | 'completed' | 'error' | 'idle';
  };
}
```

### 5.4 SSE 分流

前端 SSE 的 `onmessage` 处理器不再直接渲染到聊天区，而是加一层 dispatch：

```typescript
// scene_stream.ts — SSE message handler
function handleSceneStreamEvent(event: SSEEvent) {
  // 所有事件先往 trace store 写（如果开启了追踪）
  traceStore.append(currentSceneId, event);
  
  // 根据事件类型渲染到不同区域
  switch (event.type) {
    case 'token':
      chatStore.appendToken(event.text);
      break;
    case 'tool_start':
    case 'tool_done':
    case 'tool_error':
      chatStore.updateToolCall(event); // 已有逻辑
      break;
    case 'thought':
    case 'thinking':
      // 思考事件 → 追踪面板 + 聊天区可选
      traceStore.recordThought(event);
      break;
  }
}
```

**分流时机**：所有事件先走 trace store（实时更新面板），再按类型派发给聊天区。这样追踪面板始终保有全量事件，不影响聊天区的现有渲染逻辑。

### 5.5 样式规范

| 元素 | 样式 |
|------|------|
| 面板宽度 | 50% 视口，min 420px，max 640px |
| 步骤分组 | 顶部分割线 + 步骤号徽章 |
| 💭 思考 | 浅色渐变背景，斜体 |
| ⚡ 工具调用 | 代码块样式（深色背景等宽字体） |
| ✅ 成功 | 绿色状态点 |
| ❌ 错误 | 红色状态点 + 错误高亮 |
| 参数/返回值 | 默认折叠，点击展开，代码高亮 |
| 滚动 | 面板单独滚动，不跟随聊天区 |

### 5.6 场景隔离

```typescript
// 切场景时自动切换
useEffect(() => {
  // 当前场景的 traces 来自 tracesByScene.get(sceneId)
  // 切换 sceneId 时 trace panel 的内容自动变
}, [sceneId]);
```

---

## 六、实现路径

### Phase 1: 文件日志 + DB 记录

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 创建 `AgentTraceLogger` 类 | `backend/agent_core/trace_logger.py` | ~80 行 |
| `agent.log` JSONL 写入 + 轮转 | 同上 | ~60 行 |
| `agent_loop_traces` 表定义 + migration | `backend/database.py` | ~30 行 |
| 在 `run_agent_loop()` 中注入日志调用 | `backend/agent_core/agent_loop.py` | ~50 行 |
| trace 过期清理 | `trace_logger.py` | ~20 行 |
| `GET /api/scenes/{id}/traces` 接口 | `backend/router/scenes.py` | ~30 行 |

### Phase 2: 前端追踪面板

| 任务 | 文件 | 工作量 |
|------|------|--------|
| `AgentTracePanel` 组件 | `frontend/src/components/` | ~200 行 |
| `AgentTraceStep` 组件 | 同上 | ~100 行 |
| `ToolCallCard` + `ThinkingCard` | 同上 | ~120 行 |
| trace store | `frontend/src/stores/traceStore.ts` | ~80 行 |
| SSE 分流改造 | `frontend/src/stores/appStore.ts` | ~30 行 |
| CSS 样式 | 内联或独立 CSS | ~100 行 |

### Phase 3: 集成与验证

| 任务 | 说明 |
|------|------|
| 启动新场景执行 Agent Loop | 验证 agent.log 是否正确写入 |
| 查看 DB trace 表 | 验证批量写入正确性 |
| 前端打开追踪面板 | 验证实时展示 + 场景隔离 |
| 模拟 run_code 杀死后端 | 验证最后一行能在 agent.log 中看到 |
| 检查 3 天过期 | 手动修改 mtime 触发轮转 |

---

## 七、与现有系统的关系

### 7.1 不改动的内容

- `agent_loop.py` 的 yield 事件格式不变
- `scene_stream.py` 的 SSE 推送逻辑不变
- `messages` 表结构不变
- `context_composer.py` 的 prompt 构建逻辑不变
- 前端聊天区的渲染逻辑不变（仅在旁边加面板）

### 7.2 新增的文件

| 文件 | 说明 |
|------|------|
| `backend/agent_core/trace_logger.py` | trace 日志核心模块 |
| `frontend/src/components/AgentTracePanel.tsx` | 执行追踪面板 |
| `frontend/src/stores/traceStore.ts` | trace 状态管理 |

### 7.3 修改的文件

| 文件 | 改动 |
|------|------|
| `backend/agent_core/agent_loop.py` | 注入 `trace_logger.write()` + `db.bulk_insert_traces()` |
| `backend/database.py` | 加 `agent_loop_traces` 表定义 |
| `backend/router/scenes.py` | 加 `GET /traces` 路由 |
| `frontend/src/stores/appStore.ts` | SSE 事件分流 |

---

## 八、附录：SSE 复用 vs 额外 WebSocket 决策记录

| 方案 | 优势 | 劣势 | 结论 |
|------|------|------|------|
| **复用 SSE** | 天然有序、零额外连接、开发量小 | 前端需 filter 分流 | ✅ **选中** |
| **额外 WebSocket** | 解耦、支持双向通信 | 双流时序对齐问题、连接管理翻倍、单向需求用 REST 即可 | ❌ 不优于 SSE |

决策理由：

1. **时序一致性**是 trace 最重要的特性——"第 5 步的 `tool_start` 先于 `tool_done`"这种顺序必须保证。同一个 SSE 流天然保证，双流需要 seq_id 校准，增加复杂度且无明显收益。
2. "解耦"在此场景下是伪需求——trace 是 Agent Loop 执行过程的投影，它们天然耦合。强行解耦只会引入双流校准问题。
3. 当前无双向通信需求。未来如果有（重试步骤、中断执行），可以通过已有的 REST API 体系实现（`POST /api/scenes/{id}/retry-step`），不需要 WebSocket。
4. 额外连接增加故障面：一个断了另一个还连着，前端需要处理"trace 连上了但 SSE 断了"等非正常状态，开发量和测试量翻倍。
