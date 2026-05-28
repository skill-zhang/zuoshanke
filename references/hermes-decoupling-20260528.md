# Zuoshanke↔Hermes 解耦记录

> 日期：2026-05-28
> 目标：zuoshanke 不依赖 Hermes Agent 的任何运行时文件、路径、进程、配置

---

## 动机

zuoshanke 最初从 Hermes 生态长出来，大量工具和脚本直接拷贝/改写了 Hermes 的代码，
路径硬编码指向 `~/.hermes/`。导致：

- 删除/重装 Hermes 会破坏 zuoshanke 运行
- 路径混乱（截图存到 Hermes 目录，环境变量靠 Hermes 的 `.env`）
- 启动脚本启动 Hermes Gateway（纯 Hermes 组件，zuoshanke 不需要）
- CSS 类名和 SSE 事件类型带 `hermes-` 前缀

## 改动全景

### 1. 运行时路径 (`backend/config/paths.py`)

| 旧变量 | 新变量 | 旧路径 | 新路径 |
|--------|--------|--------|--------|
| `HERMES_ENV` | `ZUOSHANKE_ENV` | `~/.hermes/.env` | `~/.zuoshanke/.env` |
| `HERMES_BIN` | `ZUOSHANKE_BIN` | `~/.local/bin/hermes` | `~/.zuoshanke/bin/zuoshanke` |
| `HERMES_LOGS` | `ZUOSHANKE_LOGS` | `~/.hermes/logs` | `~/.zuoshanke/logs` |

引用这些常量的文件同步更新：`main.py`、`tests/conftest.py`、`tests/test_layer1_provider.py`
`ai_engine.py` 中未使用的 `HERMES_BIN` import 已删除。

### 2. Gateway 移除

`start-zuoshanke.sh` 和 `zuoshanke-ctl.sh` 中所有 Gateway 相关代码全部删除：
- `stop_gateway()` 函数
- `start_gateway()` 函数（调 `python3 -m hermes_cli.main gateway`）
- Gateway 状态检测（`pgrep -f "hermes_cli.*gateway"`）
- Gateway 日志查看
- 启动流程中的 `start_gateway` 调用

Gateway 是 Hermes 的消息网关组件，zuoshanke 的 FastAPI 后端 + React 前端
通过 SSE 直接通信，不需要中间网关。

### 3. Node.js/pnpm 路径

`tools/code_runner.py`：
- 旧：`_NODE_PATH` 默认 `~/.hermes/node/bin/node`
- 新：`shutil.which("node") or "node"`（走系统 PATH）
- 新增 `import shutil`

`scripts/start-zuoshanke.sh`：
- 删除 `PNPM="$HOME/.hermes/node/bin/pnpm"` 定义和存在性检查
- 前端启动直接走系统 `node`（原来也是直接调 `node ./node_modules/vite/bin/vite.js`）

`run-tests.sh`：
- 删除 3 处 `export PATH="$PATH:$HOME/.hermes/node/bin"`

`npm config set prefix` 从 `~/.hermes/node` 改到 `~/.local`。

### 4. 前端 CSS 类名

| 旧 | 新 |
|----|----|
| `.hermes-log-panel` | `.zuoshanke-log-panel` |
| `.hermes-log-header` | `.zuoshanke-log-header` |
| `.hermes-log-body` | `.zuoshanke-log-body` |
| `.hermes-log-line` | `.zuoshanke-log-line` |
| `.hermes-error` | `.zuoshanke-error` |

修改文件：`frontend/src/index.css`（定义）、`frontend/src/components/ActionMapDrawer.tsx`（引用）

### 5. SSE 事件类型

`hermes_log` → `zuoshanke_log`

修改文件：
- `frontend/src/api/client.ts` — TypeScript 类型定义（2 处）
- `frontend/src/components/ActionMapDrawer.tsx` — 事件消费（2 处）

后端不发送此事件类型，无需改后端。

### 6. 安全规则

`backend/agent_core/agent_loop.py` — 分身沙箱约束：
- `不要修改 ~/.hermes/ 和系统文件` → `不要修改 ~/.zuoshanke/ 和系统文件`

`tools/file_tools.py` — 文件搜索跳过目录：
- `GITIGNORE_PATTERNS` 中 `.hermes` → `.zuoshanke`

`backend/agent_core/context_composer.py` — 反面案例提示：
- `/tmp/hermes/dial_shots/` → `/tmp/zuoshanke/dial_shots/`

### 7. 描述性文字清理

脚本注释、前端 UI 文本、设计文档中的 "Hermes" 描述性文字已删除或改写。
保留历史架构文档（`schema-v0.2.md`、`architecture.md`）中的 `hermes chat -q` 命令示例，
因为它们是早期架构的真实记录。

## 数据迁移

执行了以下数据迁移（手动，不包含在 git commit 中）：

```bash
cp ~/.hermes/.env ~/.zuoshanke/.env
mv ~/.hermes/dial_shots/* ~/.zuoshanke/dial_shots/
cp ~/.hermes/precipitate/2026-05-26.md ~/.zuoshanke/precipitate/
mkdir -p ~/.zuoshanke/{dial_shots,precipitate,logs,bin}
```

## 包管理器国内源配置

```bash
npm config set registry https://registry.npmmirror.com
npm config set prefix ~/.local
pnpm config set registry https://registry.npmmirror.com
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
npm install -g pnpm
```

## Git 提交

```
fcf0ea3 解耦 Hermes 依赖 — 路径、Gateway、CSS 全量迁移到 zuoshanke 自有空间
21 files changed, 88 insertions(+), 170 deletions(-)
```
