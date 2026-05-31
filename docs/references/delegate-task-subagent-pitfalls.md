# Delegate Task / 并行子任务排坑指南

## 常见错误

### 1. `❌ AI 响应生成异常: 'str' object has no attribute 'get'`

**根因**: `scene_stream.py` 的 `tool_start` 事件处理中 `event.get("args", {})` 返回了字符串而非 dict。理论上 `agent_loop.py` 的 `_safe_parse_tool_args()` 保证 args 为 dict，但 LLM 传参格式极端异常时仍可能字符串穿透。

**修复** (2026-05-31): 见 [设计文档](../design/delegate-task-blocking-fix.md#p0--防御性参数解析)

### 2. 子 Agent 执行期间前端卡死无进度

**根因**: `execute_tool(delegate_task)` 是同步函数，阻塞主 Generator 数百秒，SSE 流无事件。

**修复** (2026-05-31): 见 [设计文档](../design/delegate-task-blocking-fix.md#p1--线程化执行--进度推送)

### 3. 前端面板永远"执行中"（tool_error 未清空面板）

**根因**: `scene_stream.py` 的 `tool_error` 分支没有处理 `delegate_task`。子 Agent 失败时 agent_loop 走 `tool_error` 而非 `tool_done`，`child:done` 事件从未发射，前台 `DelegationMonitor` 面板的 `_runningTasks` 永远不置空。

**修复** (2026-05-31): `scene_stream.py` `tool_error` 分支加：
```python
if event["tool"] == "delegate_task":
    yield sse_event("child:done", children=[])
```

### 4. 子 Agent 超时

**多层超时关系**：

```
主 Agent Loop: timeout(10, 300) per LLM call
  └─ delegate_task: _CHILD_TIMEOUT = 600 (总限制)
       └─ 子 Agent 每步: timeout(10, 300) per LLM call
            └─ max_steps = 25
```

子 Agent 的总可用时间 = min(_CHILD_TIMEOUT, steps × LLM_timeout) ≈ 600s 或约 2 步 LLM 调用（每步 300s）。

### 4. `run_code` 高危命令阻断后 NameError

**根因** (已有 bug): `agent_loop.py:892` 使用未定义变量 `params`（应为 `args`）。
```python
# 改前 — NameError
event["blocked_command"] = params.get("command", "")
# 改后
event["blocked_command"] = args.get("code") or args.get("command", "")
```

## 超时值参考

| 位置 | 值 | 含义 |
|------|-----|------|
| `agent_loop.py:287,316` | `(10, 300)` | 每次 LLM API 调用（主+子），10s connect + 300s read |
| `delegate_engine.py:195` | `_CHILD_TIMEOUT = 600` | 每个子 Agent 总执行时间上限 |
| `delegate_engine.py:194` | `_MAX_WORKERS = 3` | 最大并行子 Agent 数 |
| `ai_engine.py:193,247,1008` | `timeout=300` | 其他 LLM 调用路径（闲聊等） |
