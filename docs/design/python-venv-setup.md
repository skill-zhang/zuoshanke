---
title: Python 虚拟环境与依赖安装
description: 坐山客后端必须通过 venv 隔离运行，避免系统 Python 包版本冲突
tags:
  - 安装
  - 部署
  - 后端
  - SQLAlchemy
---

# Python 虚拟环境与依赖安装

## 问题背景

坐山客后端（FastAPI + SQLAlchemy）依赖于特定版本的 Python 包。Ubuntu/Debian 系统 Python（`apt` 安装的 python3-* 包）提供的版本往往过旧，导致运行时出错。

典型错误：

```
ImportError: cannot import name 'DeclarativeBase' from 'sqlalchemy.orm'
```

或（作为连锁反应表现为）：

```
NameError: name 'Optional' is not defined
```

**根因**：系统 SQLAlchemy 为 1.4.x（Ubuntu 24.04 默认），但代码需要 SQLAlchemy >= 2.0.36。`DeclarativeBase` 是 SQLAlchemy 2.0 引入的 API，1.4 时代用的是 `declarative_base()` 工厂函数。

这种问题同样可能出现在其他依赖上（fastapi、pydantic 等），因此必须使用虚拟环境隔离项目依赖。

## 解决方案

### 第一步：创建虚拟环境

在 `backend/` 目录下创建 venv：

```bash
cd zuoshanke/backend
python3 -m venv venv
```

> **注意**：`venv` 目录已加入 `.gitignore`，不会被提交到仓库。

### 第二步：安装依赖

```bash
# 激活 venv
source venv/bin/activate

# 安装项目依赖
pip install -r requirements.txt
```

`requirements.txt` 内容：

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
sqlalchemy>=2.0.36
pydantic>=2.10.0
openai>=1.0.0
```

> 需要额外依赖时，先加到 `requirements.txt`，再 `pip install -r requirements.txt` 同步安装。

### 第三步：验证

```bash
source venv/bin/activate
python -c "
from sqlalchemy.orm import DeclarativeBase
from fastapi import FastAPI
print('核心依赖安装正确')
"
```

### 第四步：启动后端

```bash
# 方式一：先激活 venv 再启动
source venv/bin/activate
cd zuoshanke/backend
python main.py

# 方式二：直接使用 venv 的 Python 启动
cd zuoshanke/backend
venv/bin/python main.py
```

**不要**直接使用系统 Python 启动——否则 venv 形同虚设。

## 常见问题

### Q: 系统已有 SQLAlchemy，为什么还要装？

系统 SQLAlchemy（Ubuntu 24.04）是 1.4.50，而 `DeclarativeBase` 需要 2.0+。pip 安装到 venv 后，系统级包和项目级包互不干扰。

### Q: pip install 遇到超时怎么办？

国内网络建议配置镜像：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: 为什么不用 Poetry / Conda？

venv 是 Python 内置方案，零额外依赖、学习成本最低。坐山客保持最小外部工具链依赖。

## 历史记录

- **2026-05-28**：首次编写。发现系统 SQLAlchemy 1.4.50 不支持 `DeclarativeBase`，导致后端无法启动。创建 venv 并安装 SQLAlchemy 2.0.36 后修复。
