# Delegate Task 阻塞与超时修复

## 背景

分身场景中 LLM 调 `delegate_task` 工具派子 Agent 并行画原型时，出现三个问题：

1. `scene_stream.py` 中 `event.get("args", {}).get("tasks")` 在 `args` 为字符串时报 `'str' object has no attribute 'get'`
2. 子 Agent 执行期间主 Agent Loop 同步阻塞 300 秒，前端 SSE 流无任何事件，UI 卡死在"执行中"
3. LLM API 调用超时 120s、子 Agent 总超时 300s 对复杂任务（画原型）太短

## 改动

### P0 — 防御性参数解析

**文件**: `backend/router/scene_stream.py`

`tool_start` 事件中 3 处 `args = event.get("args", {})` 后加防御：

```python
if isinstance(args, str):
    try:
        args = json.loads(args)
    except json.JSONDecodeError:
        args = {}
if not isinstance(args, dict):
    args = {}
```

涉及工具：`think`、`clarify`、`delegate_task`

### P1 — 线程化执行 + 进度推送

**文件**: `backend/agent_core/agent_loop.py`

原流程：

```
yield tool_start → execute_tool(delegate_task) → 同步阻塞 300s → yield tool_done
```

新流程：

```
yield tool_start
ThreadPoolExecutor.submit(_thread_execute)  → 后台线程
while True:
    fut.result(timeout=10)  # 每 10s 轮询
    → yield keepalive("已等待 N 秒")
    （直到 fut 返回或 GeneratorExit）
yield tool_done
```

**关键细节**：
- `_thread_execute()` 闭包在 worker 线程内重设 `set_tool_context(scene_id=scene_id)`，因 `threading.local()` 不跨线程
- 客户端断连时 `GeneratorExit` 触发内层 `finally: _pool.shutdown(wait=False, cancel_futures=True)`，后台子 Agent 继续跑完但结果无人消费
- `cancel_futures` 仅取消未启动的任务，已在运行的任务不受影响（Python 3.9+）

**文件**: `backend/router/scene_stream.py`

`keepalive` 事件增加 `message` 字段透传，前端可显示 "⏳ 子任务执行中...（已等待 10s）"

### P2 — 超时放宽

| 位置 | 改前 | 改后 |
|------|------|------|
| `agent_loop.py:287,316` (主 Agent LLM 调用) | `(10, 120)` | `(10, 300)` |
| `delegate_engine.py:195` (子 Agent 总超时) | `_CHILD_TIMEOUT = 300` | `_CHILD_TIMEOUT = 600` |
| `ai_engine.py:193,247,1008` (其他 LLM 调用) | `timeout=120` | `timeout=300` |

connect timeout 维持 10s（网络不可达应快速失败），read timeout 从 120s → 300s（给生成代码草图留余量）。

### 额外修复

- `agent_loop.py:892` 发现已有 bug：`params.get("command")` 中 `params` 未定义（应为 `args`）。修法：`args.get("code") or args.get("command", "")`
- `scene_stream.py` `tool_error` 分支缺少 `delegate_task` 处理：子 Agent 失败时 `child:done` 从未发射，前端面板永远显示"执行中"。修法：`tool_error` 中 `delegate_task` 补 `yield sse_event("child:done", children=[])"

## 验证

- 4 个文件语法全通过 `python3 -m py_compile`
- 防御代码在 args 为 dict（正常情况）时零开销
- 超时数值统一为 300s，直觉可记忆

## 提交

```
ce88a51 fix: delegate_task 子任务卡死/超时/参数崩溃 三重修复
```
