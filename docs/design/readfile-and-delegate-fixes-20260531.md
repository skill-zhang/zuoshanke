# read_file 修复 + 父子 Agent 心跳 (2026-05-31)

## 背景

用户在使用坐山客做项目时发现三个问题：
1. 场景分身反复读同一个文件，直到 LLM 调用失败
2. 父 Agent 派子 Agent 并行干活时 SSE 连接断连
3. 并行子 Agent 上限只有 3 个

## 修复一：read_file 死循环

### 根因

`agent_loop.py` 的滑动窗口压缩（保留最近 3 步完整，旧步骤压缩为摘要）把 `read_file` 的结果截取前 120 字暴露给 LLM：

```
步骤 1: 调用 read_file
  → # 文件标题\n\n正文内容第一段前120字…
```

LLM 看到「…」以为只读了开头，于是反复再调 `read_file` 读"完整内容"→ 压缩截断 → 再读 → 死循环，直到上下文撑爆 LLM 调用失败。

**三个修复点：**

### ① 压缩摘要不暴露 `read_file` 内容前 120 字

在 `agent_loop.py` 压缩逻辑中，构建 `tool_call_id → tool 信息` 映射。对 `read_file` 的结果不以内容前 120 字展示，改为：

```
步骤 1: 调用 read_file
  → 读文件 /path/to/file (15230 字符)
```

LLM 看到（15230 字符）就知道已经完整读过，不再重读。

关键代码逻辑：
- 遍历 assistant 消息的 `tool_calls`，提取 `id` + `function.name`，对 `read_file` 额外解析 `function.arguments` 中的 `path`
- 在 tool result 消息中通过 `tool_call_id` 查映射
- 匹配 `read_file` 且 path 存在 → 显示"读文件 {path} ({len} 字符)"
- 不匹配 → 保持原 120 字截断行为

### ② `read_file` 默认 limit: 500 → 2000 + 字符硬上限 100K

原值 500 行对大文件需要多次分页。新方案：

```
MAX_CHARS = 100000  ← 字符数硬上限（防止压缩 JS 单行长撑爆）
limit = 2000        ← 行数软上限（给 HTML 等短行文件更多空间）
```

实现：逐行累加字符数，超限则 break 并返回 `truncated_char=True` + `next_offset`（供 LLM 继续分页）。

### ③ `read_file` 去重缓存

在 `agent_loop.py` 的 `run_agent_loop()` 开头初始化 `_read_file_cache = {}`。每次 `execute_tool` 前检查：

- 非 `read_file` → 正常执行
- `read_file` + 路径不在缓存 → 执行并缓存 `{lines, chars, step}`
- `read_file` + 路径在缓存 → **跳过执行**，直接返回简短提示 `"(已在第 X 步完整读过: path, N 字符/M 行, 无需重读)"`

缓存 key 是 LLM 传的原始 path 字符串，不做路径解析。

## 修复二：父子 Agent 心跳

### 根因

父 Agent 用 `ThreadPoolExecutor.submit()` 在线程中执行子 Agent，主线程每 10s 轮询 `_fut.result(timeout=10)`。子 Agent 内部调 `call_llm_with_tools()` 可能阻塞 20-30s，期间父 Agent 无心跳输出 → SSE 代理/网关超时断连。

### 修复

**方案：通过线程属性共享 progress dict**

父 Agent：
```python
_child_progress = {"step": 0, "tool": ""}
# 挂到子线程
threading.current_thread()._child_progress = _child_progress
# keepalive 循环中读取
_prog = _child_progress
if _prog["step"]:
    _prog_str = f" (第{_prog['step']}步, {_prog['tool']})"
yield {"type": "keepalive", "message": f"⏳ 子任务执行中...{_prog_str}"}
```

子 Agent（`_run_loop_blocking`）：
```python
_progress = getattr(threading.current_thread(), '_child_progress', None)
if _progress:
    _progress["step"] = step + 1
    _progress["tool"] = "llm_call"
# 执行工具前：
if _progress:
    _progress["tool"] = tool_name
```

**安全：** 每次写入前有 `if _progress:` 守卫，非子 Agent 路径（直接调用、测试）安全跳过。

## 修复三：并行子 Agent 数 3 → 10

| 位置 | 原值 | 新值 |
|------|------|------|
| `delegate_engine.py` `_MAX_WORKERS` | 3 | 10 |
| `delegate_tool.py` schema 描述 | "最多 3 个" | "最多 10 个" |
| `delegate_tool.py` 截断 | `> 3` / `[:3]` | `> 10` / `[:10]` |

## 相关文件

- `backend/agent_core/agent_loop.py` — 压缩摘要、去重缓存、父子心跳
- `tools/file_tools.py` — read_file limit 2000 + MAX_CHARS 100K
- `backend/agent_core/delegate_engine.py` — _MAX_WORKERS、_run_loop_blocking 进度更新
- `tools/delegate_tool.py` — schema 描述、截断阈值

## Commits

```
4e5e32f fix: 压缩摘要不暴露 read_file 内容前120字
4bcbdab chore: read_file 默认 limit 500→2000
52d8e53 feat: read_file 加字符数硬上限 100K
e73ccb5 feat: read_file 去重 — 同一文件只读一次
6fe857a feat: 并行子Agent增至10个 + 子任务进度心跳
```
