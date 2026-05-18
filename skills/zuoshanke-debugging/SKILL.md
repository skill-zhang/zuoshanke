---
name: zuoshanke-debugging
description: 坐山客系统调试手册 — Agent Loop、SSE 流式、工具执行、上下文注入问题排查
version: 1.0
category: development
triggers: [调试, 坐山客, Agent Loop, 流式, SSE, 工具执行, 上下文注入, 后端错误]
---

# 坐山客系统调试手册

## 概述

坐山客的工作台涉及多层系统协同工作。当功能异常时，问题通常位于以下四层之一：

```text
前端 React (channels.tsx / scenes.tsx)
    ↕ SSE 流式连接
后端 FastAPI (main.py / agent_loop.py)
    ↕ 工具调用
Agent Core (agent_core/)
    ↕ 上下文构建
规则引擎 (ai_engine.py / skill_manager.py)
```

## 第一层：后端启动与连接

### 后端没启动
```bash
cd ~/zuoshanke/backend
.venv/bin/python main.py
```

**端口被占用：**
```bash
fuser -k 8000/tcp
```

**启动后验证：**
```bash
curl http://localhost:8000/health
# 预期: {"status": "ok", ...}
```

### SSE 流式连接失败

坐山客的 Agent Loop 通过 `POST /api/agent-loop/stream` 建立 SSE 连接。

**常见问题：**
1. **后端未运行** — 前端显示"连接中…"死循环
2. **端口不通** — WSL mirrored 网络模式下，Windows 浏览器用 `localhost:8000` 直访
3. **消息顺序错误** — SSE 协议要求 `data:` 前缀 + 空行 `\n\n` 结尾。tool_calls 消息必须在 assistant 消息之后

```
✅ 正确顺序:
data: {"role": "assistant", "content": "让我查一下", "tool_calls": [...]}
data: {"role": "tool", "name": "search_files", "content": "结果..."}
data: {"role": "assistant", "content": "总结"}

❌ 错误顺序（导致前端崩溃）:
data: {"role": "tool", ...}   ← 没有前面的 assistant(tool_calls)
```

## 第二层：Agent Loop 执行

### Agent Loop 不响应

检查 `agent_loop.py` 的核心循环逻辑：

1. **规则优先拦截** — `ai_engine.py` 中的 `should_web_search()`、路由判断等规则层可能抢先接管
2. **LLM 超时** — DeepSeek API 超时（默认 30s），检查 `.env` 中的 API 配置
3. **模型路由错误** — 频道走本地Qwen，场景走DeepSeek。检查 `settings` 表路由配置

### 工具执行失败

```python
# 排查：在终端手动触发工具
cd ~/zuoshanke/backend
.venv/bin/python -c "
from tools.file_tools import search_files
result = search_files(pattern='test', path='/tmp')
print(result)
"
```

**常见原因：**
1. **工具路径错误** — tools 目录下的 .py 文件必须有正确的导入路径
2. **依赖缺失** — 工具引入了未在 venv 中安装的包
3. **权限问题** — 读取系统文件没有权限
4. **类型错误** — 工具函数签名与注册表不匹配

**日志必须可见：** 后端错误必须打印到终端日志，不要静默吞掉异常。

### Token 超限

Agent Loop 有上下文 Token 预算。当工具返回大量数据时：
1. Token 用量条在前端底部提示行显示
2. 后端发送 `context_info` / `capacity_warning` SSE 事件
3. Agent Loop 会自动截断过长的工具返回

排查时检查 SSE 事件流中是否有 `capacity_warning` 事件。

## 第三层：上下文注入

### 技能/记忆未生效

Agent Loop 的上下文构建在 `agent_core/context_builder.py`：

1. **技能未匹配** — 检查 `skills/<name>/SKILL.md` 的 `triggers` 字段是否覆盖了用户输入的关键词
2. **记忆未注入** — 记忆通过 `POST /api/memory/match` 匹配，检查 API 是否返回结果
3. **注入溢出** — 默认最多注入 2 个 skill + 若干记忆片段，超限会被截断

手动测试技能匹配：
```bash
curl "http://localhost:8000/api/skills/match?query=今天天气怎么样&max_count=2"
```

## 第四层：前端问题排查

### 角色动画卡住

坐山客角色动画浮在 Topbar 上：
- 25秒无操作 → 自娱动画
- 3分钟无操作 → 自动睡眠
- 点击 → 轮播表情

**排查：** 检查 SSE 事件中是否有 `animation` 事件。角色表情应与系统状态联动——流式时"思考"、回复时"说话"、空闲时"等待"。

### SSE 事件不显示

前端对 SSE 事件的处理在 `channels.tsx` 和 `scenes.tsx` 中：
1. 检查浏览器控制台是否有 SSE 连接日志
2. 检查事件字段名是否前后端一致（如 `type: "token"` vs `event: "token"`）

## 通用排查流程

### 第一步：确认后端运行

```bash
curl http://localhost:8000/health
ps aux | grep main.py
```

### 第二步：检查后端日志

后端输出在终端中可见。查看最近错误：
```bash
cd ~/zuoshanke/backend
grep -i "error\|exception\|traceback" .venv/log.log 2>/dev/null || echo "无专用日志文件，查看终端输出"
```

### 第三步：检查 SSE 事件流

```bash
# 手动触发 Agent Loop 查看 SSE 输出
curl -N -X POST http://localhost:8000/api/agent-loop/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "message": "天气怎么样", "scene": "default"}'
```

### 第四步：检查工具注册

```bash
cd ~/zuoshanke/backend
.venv/bin/python -c "
import json
tools = json.load(open('tools/registry.json'))
for t in tools:
    print(f'{t[\"name\"]:30s} → {t.get(\"path\", \"?\")}')
"
```

### 第五步：检查路由配置

```bash
cd ~/zuoshanke/backend
.venv/bin/python -c "
from config import settings  # 导入settings模块
# 查看渠道和场景的路由配置
import sqlite3
conn = sqlite3.connect('../data.db')
cursor = conn.execute('SELECT key, value FROM settings WHERE key LIKE \"%route%\"')
for row in cursor:
    print(f'{row[0]}: {row[1]}')
"
```

## 常见问题速查

| 症状 | 可能原因 | 排查方向 |
|------|---------|---------|
| 前端白屏/连不上 | 后端未启动 | 检查端口、进程 |
| AI 不响应 | API Key 无效 / 模型路由错了 | 检查 .env 和路由配置 |
| 工具不工作 | 注册表错误 / 导入异常 | 手动执行工具脚本 |
| SSE 流中断 | 网络 / 超时 / 消息格式 | 用 curl 直接测试 SSE |
| 技能没触发 | triggers 不匹配 | 用 match API 测试 |
| 角色动画不动 | SSE animation 事件缺失 | 检查后端是否发送 |
| Token 超限 | 上下文太大 | 检查 capacity_warning 事件 |
| 重启后配置丢了 | 未持久化到 DB settings 表 | 检查 settings 表值 |
