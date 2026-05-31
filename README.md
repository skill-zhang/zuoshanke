# 坐山客（Zuoshanke）

> AI 伙伴工作台 — 把 AI 从工具变成搭档。

## 核心理念

当前 AI Agent（Hermes、Claude Code 等）的问题是：执行前用户看不到规划，执行中用户追踪不到行动，出错后恢复靠蛮力。

坐山客的答案是**双图架构**：

- **Thinking Map（思维导图）**：建立信任的认知同步——让用户看到 AI 是怎么理解需求的
- **Action Map（行动图）**：执行前的契约——让用户看到 AI 打算怎么干

两张图独立但关联，用户可随时暂停行动、修改思考、重新执行。

## 技术栈

| 层 | 选择 |
|---|------|
| 前端 | React + Markmap（思维导图）+ React Flow（行动图） |
| 后端 | Python FastAPI |
| 存储 | SQLite + Alembic |
| 引擎 | DeepSeek v4 Flash / Claude / Qwen（可切换 Provider） |

## 快速开始

### 前置要求

- **Python 3.9+**
- **Node.js 18+**（含 npm）
- **pnpm**（Node 包管理器）

### 一键启动

```bash
git clone https://github.com/skill-zhang/zuoshanke.git
cd zuoshanke
bash scripts/start-zuoshanke.sh
```

启动脚本会自动：

1. ✅ 检查 Python / Node.js / pnpm 是否安装
2. ✅ 自动创建 Python 虚拟环境并安装后端依赖
3. ✅ 自动安装前端依赖
4. ✅ 启动后端（http://localhost:8000）+ 前端（http://localhost:5173）

### 如果缺依赖

脚本会在启动前检测并给出**即贴即用的安装命令**。macOS 上例如：

```bash
# 安装 Homebrew（如果没有）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
source ~/.zshrc

# 安装 Node.js（会自动附带 npm）
brew install node

# 安装 pnpm
npm install -g pnpm
```

### 单独安装依赖

```bash
bash scripts/start-zuoshanke.sh install-deps
```

### 仅启动后端 / 前端

```bash
bash scripts/start-zuoshanke.sh backend
bash scripts/start-zuoshanke.sh frontend
```

### 停止 / 查看状态

```bash
bash scripts/start-zuoshanke.sh stop
bash scripts/start-zuoshanke.sh status
```

## 仓库结构

```
zuoshanke/
├── README.md
├── docs/
│   ├── design/        # 架构决策、设计文档
│   ├── api/           # OpenAPI 定义
│   └── meetings/       # 讨论纪要
├── backend/
│   ├── models.py
│   ├── migrations/    # Alembic 迁移
│   └── ...
├── frontend/
│   └── src/
└── scripts/
    └── start-zuoshanke.sh   # 一键启动脚本
```

## 许可证

[Apache 2.0](LICENSE) © 2026 坐山客团队

**创作者：**
- **Administrator (skill-zhang)** — 架构设计、系统实现、法律主体
- **zuoshanke Agent (Nous Research)** — 代码生成、架构建议、协作构建

> zuoshanke Agent 作为 AI 协作伙伴参与本项目开发。所有法律权利、义务与责任由 human 创作者（Administrator）独立承担。
