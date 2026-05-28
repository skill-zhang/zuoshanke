# 坐山客高可靠架构设计 Schema v1.7

## 1. 问题背景

坐山客支持「自开发」——分身通过 Agent Loop 自主修改项目源码。这带来了独特的高可用挑战：

1. **自修改崩自己**：分身 `write_file` / `patch` 写了语法错误的 .py 文件 → 下次重启后端直接起不来
2. **自残杀进程**：分身 `run_code(language="bash")` 执行 `kill -9` / `fuser -k 8000/tcp` 等命令误杀后端
3. **雪崩效应**：后端挂了 → 前端 SSE 断开 → 显示"网络请求失败" → 再次请求依然失败
4. **单体单点**：单 worker 进程，挂了就全挂
5. **开发效率**：改 .py 需要手动重启后端

## 2. 设计目标

1. **零感知**：分身改代码出问题时，前端用户不感知
2. **自动恢复**：进程挂了能自动恢复或自动重试
3. **写前保护**：坏代码写不进磁盘
4. **版本锚点**：任何时候可以回滚到上一个稳定状态
5. **开发友好**：改代码自动生效，无需手动重启

## 3. 架构设计

### 3.1 三层防护模型

```
┌─────────────────────────────────────────────────┐
│                 第三层: 用户无感                  │
│   前端自动重试 (SSE 超时 180s → 探测 → 重发)    │
├─────────────────────────────────────────────────┤
│                 第二层: 进程级保护                │
│   Git 快照 (改 .py 前自动 commit)               │
│   热加载 reload_delay=3 (防连环重启)             │
├─────────────────────────────────────────────────┤
│                 第一层: 写入级保护                │
│   write_file → py_compile / json.loads / node --check  │
│   patch → 同上 + 回滚原内容                      │
│   语法错误 → 阻止写入 + 返回错误消息             │
└─────────────────────────────────────────────────┘
```

### 3.2 组件关系图

```
┌─────────┐   write_file(.py)   ┌──────────────┐
│  Agent  │ ──────────────────►  │   write_file  │
│  Loop   │                     │   校验函数     │
│ (分身)   │   patch(.py)       │              │
│         │ ──────────────────►  │ 1. Git 快照   │
└─────────┘                     │ 2. 写文件     │
                                │ 3. 语法校验   │
                                │ 4. 失败回滚   │
                                └──────┬───────┘
                                       │ 写成功
                                       ▼
                                ┌──────────────┐
                                │  uvicorn      │
                                │  reload       │
                                │  delay=3s     │
                                └──────┬───────┘
                                       │ 检测到 .py 变化
                                       ▼
                                ┌──────────────┐
                                │  新 worker    │
                                │  启动 → 接客  │
                                └──────────────┘

  ┌──────────┐   SSE 断开       ┌──────────────┐
  │ 前端     │ ──────────────►  │  自动重试      │
  │ ChatView │                  │  1. 显示"🔄"  │
  │          │  ◄────────────── │  2. 等 3s     │
  └──────────┘  重发成功        │  3. ping /health │
                                │  4. 重发请求   │
                                │  5. 最多重试3次 │
                                └──────────────┘
```

## 4. 详细设计

### 4.1 写入校验 (`tools/file_tools.py`)

```python
def _validate_file_content(resolved: str, content: str) -> Optional[str]:
    """写后静态校验：阻止语法错误写入。
    
    支持的格式与校验方式:
    - .py      → py_compile.compile(doraise=True)
    - .json    → json.loads() 
    - .js/.jsx → node --check <tempfile>
    - .yaml/.yml → yaml.safe_load()
    - .ts/.tsx → 不强制校验（需要 tsconfig 环境）
    """
```

**调用路径**：`write_file()` 和 `patch()` 在写文件后立即调用。校验失败则回滚（删除文件或恢复原内容）。

**回滚策略**：
- `write_file`：删除已写文件，返回 `{"error": "...已阻止写入并回滚..."}`
- `patch`：用内存中的原内容覆盖回去，返回 `{"error": "...已阻止 patch 并回滚..."}`

### 4.2 Git 自动快照 (`tools/file_tools.py`)

```python
def _git_snapshot(resolved: str) -> None:
    """在修改代码文件前，自动 git commit 当前版本。
    
    触发条件：write_file/patch 的目标是 .py/.ts/.tsx/.js/.jsx
    行为：git add <file> → git commit -m "🛡 auto-snapshot before modify: <file>"
    失败处理：静默失败，不中断主流程
    """
```

### 4.3 热加载配置 (`backend/main.py`)

```python
uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True,
            reload_delay=3, reload_includes=["*.py"])
```

**说明**：
- `reload=True`：改 .py 文件自动重启 worker
- `reload_delay=3`：文件变更后等待 3 秒再重启，防止连环写入导致频繁重启
- `reload_includes=["*.py"]`：只监听 Python 文件

### 4.4 SSE 超时兜底 (`frontend/src/api/client.ts`)

两个 SSE stream 函数均增加 180 秒读取超时：
- `sendSceneMessageStream()`
- `sendChannelMessageStream()`

**实现**：`Promise.race([reader.read(), timeoutPromise])`，每次 read 都起新的 180s 定时器。超时后 `reject` → 上游 catch 捕获。

### 4.5 前端自动重试 (`frontend/src/stores/appStore.ts`)

```
sendSceneMsg/catch(SSE错误)
  │
  ├─ 判断: 错误包含"超时"|"Failed to fetch"|"NetworkError"?
  │    是 → 进入 _retryStream
  │    否 → 显示 "❌ ${错误消息}"
  │
  └─ _retryStream(maxRetries=3)
       │
       ├─ 显示 "🔄 后端热更新中，自动重试..."
       ├─ 等 3 秒
       ├─ fetch('/api/health') 探测后端
       │    ├─ 失败 → 递归重试 (attempt++)
       │    └─ 成功 → 清除旧 AI 消息 → 重新发送
       └─ attempt > 3 → 显示 "❌ 后端服务不稳定"
```

**并发安全**：`_retryCount[entityId]` 记录重试次数，场景和频道共享一套逻辑。

### 4.6 think 工具容错 (`tools/think_tool.py`)

```python
def think(content: str, **kwargs) -> dict:
```

当 LLM 错误传入 `old_string`、`new_string` 等 patch 工具的参数时，**kwargs 吞掉多余参数并打 warning 日志。

## 5. 边界情况与处理

| 场景 | 处理 |
|------|------|
| 分身写 .py 文件语法错误 | `_validate_file_content` 拦截 + 回滚 |
| 分身写 .json 文件格式错误 | `json.loads` 校验失败 + 回滚 |
| 分身 kill 后端进程 | 旧日志被覆盖；新启动后前端自动重试恢复 |
| 分身连环写入多个 .py | `reload_delay=3` 防频繁重启 |
| 前端 SSE 断连但后端活着 | 180s 内恢复则无感重连 |
| 后端彻底崩了 | 3 次重试后显示 "❌ 后端服务不稳定" |
| 分身改了文件但代码逻辑错 | 靠 Git 快照回滚 (`git log` 找 auto-snapshot) |

## 6. 后续可能的方向

1. **启动自检**：新 worker 启动时 self-check，如果关键模块加载失败则退出
2. **进程树白名单**：`run_code` 限制可 kill 的 PID 范围
3. **优雅降级**：后端挂了一半功能时，前端降级显示只读模式
4. **代码审查 Agent**：分身产出先经过一个校验 Agent 审查再落地
