# Agent Loop 执行引擎 — 架构设计

> 坐山客 v0.7 | 2026-05-18

## 背景

坐山客原系统采用"预执行模式"——关键词匹配工具→执行→结果注入→单次 LLM 回复。这种方式对确定性场景（天气、地理、待办）高效，但对需要多步推理和工具调用的复杂任务（编码、文件操作）完全无力。

## 架构

### 双路径路由

```
用户输入
  ↓
[规则层快检] —— 命中？——→ 预执行 + 单次 LLM 回复（<10ms）
                ↓ 不命中
            [Agent Loop] ——→ LLM 自主调工具循环
```

### Agent Loop 循环

```
① 构建消息 [system + user(task)]
  ↓
② 调 LLM(带 tools 参数) → function calling
  ↓
③ 有 tool_calls? ──是──→ ④
  ↓ 否                    ↓
⑤ 返回文本 ←── ④ execute_tool(name, args)
  ↓                    ↓
完成                   结果(assistant→tool 顺序) 喂回消息
                       ↓
                      回到②
```

### 关键文件

| 文件 | 作用 |
|------|------|
| `backend/agent_core/agent_loop.py` | 循环引擎 + tool definitions 转换 |
| `backend/ai_engine.py` | `call_llm_with_tools()` DeepSeek API + function calling |
| `backend/router/scenes.py` | `POST /api/agent-loop/stream` SSE 端点 |
| `tools/file_tools.py` | read_file / write_file / patch / search_files |
| `tools/code_runner.py` | run_code（terminal 执行） |
| `tools/registry.json` | 23 工具注册表 |

## 工具

### 文件操作（新增）

| 工具 | 函数 | 说明 |
|------|------|------|
| `read_file` | `file_tools.read_file(path, offset, limit)` | 读文件，行号+分页 |
| `write_file` | `file_tools.write_file(path, content)` | 覆盖写入，自动创建目录 |
| `patch` | `file_tools.patch(path, old_string, new_string)` | 查找替换，difflib 模糊匹配 |
| `search_files` | `file_tools.search_files(pattern, ...)` | 内容正则搜索 / glob 文件名查找 |

### 代码执行（已有）

| 工具 | 函数 | 说明 |
|------|------|------|
| `run_code` | `code_runner.run_code(code, language)` | Python/Shell(bash)/JS 执行 |
| `web_search` | `web_search.web_search(query)` | 互联网搜索 |

### 工具过滤

Agent Loop 默认排除不适用的工具（天气/装备/地理POI等留给预执行），只给 LLM 自主调以下类别的工具：
- 文件操作（read/write/patch/search）
- 代码执行（run_code）
- 搜索（web_search、session_search）
- 待办（todo_list、todo_add）

## SSE 事件流

端点 `POST /api/agent-loop/stream` 返回标准 SSE：

```json
{"type": "agent_loop:start", "task": "...", "model": "flash"}
{"type": "agent_loop:status", "message": "第 1 步：思考中..."}
{"type": "agent_loop:tool_start", "tool": "write_file", "args": {...}}
{"type": "agent_loop:tool_done", "tool": "write_file", "result": {...}}
{"type": "agent_loop:thinking", "text": "已完成..."}
{"type": "agent_loop:done", "summary": "...", "steps": 2, "finish_reason": "stop"}
```

## 里程碑验证

贪吃蛇游戏全流程验证通过：
1. LLM 自主检查环境（python3 → pip install pygame → write_file → 语法验证）
2. 生成 352 行完整 `snake.py`，支持方向键/WASD/计分/暂停/重新开始
3. 全程无人干预，deepseek-v4-flash function calling 驱动

## 陷阱记录

1. **消息顺序**：`tool` role 必须在 `assistant(tool_calls)` 之后，否则 DeepSeek 400
2. **content 字段**：有 tool_calls 时设 `content: None`，否则 `content: "文本"`
3. **code_runner 语言名**：LLM 倾向传 "bash" 但原来只认 "shell"，已加别名
4. **pip install 慢**：WSL 网络问题，需用国内镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`
