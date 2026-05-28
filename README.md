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

## 仓库结构

```
zuoshanke/
├── README.md
├── docs/
│   ├── design/        # 架构决策、设计文档
│   ├── api/           # OpenAPI 定义
│   └── meetings/      # 讨论纪要
├── backend/
│   ├── models.py
│   ├── migrations/    # Alembic 迁移
│   └── ...
├── frontend/
│   └── src/
└── .git/
```

## 快速开始

### 后端

```bash
# 克隆后，进入 backend 目录创建虚拟环境
cd zuoshanke/backend
python3 -m venv venv

# 安装依赖
source venv/bin/activate
pip install -r requirements.txt

# 启动后端
venv/bin/python main.py
```

> **重要**：必须使用 venv，系统 Python 的 SQLAlchemy 版本过旧（1.4.x），代码需要 >= 2.0.36。
> 详见 [docs/design/python-venv-setup.md](docs/design/python-venv-setup.md)

### 前端

```bash
cd zuoshanke/frontend
npm install
npm run dev
```

## 许可证

[Apache 2.0](LICENSE) © 2026 坐山客团队

**创作者：**
- **Administrator (skill-zhang)** — 架构设计、系统实现、法律主体
- **zuoshanke Agent (Nous Research)** — 代码生成、架构建议、协作构建

> zuoshanke Agent 作为 AI 协作伙伴参与本项目开发。所有法律权利、义务与责任由 human 创作者（Administrator）独立承担。
