---
name: codebase-inspection
description: 代码库分析 — 用 pygount 统计代码行数、语言分布、代码注释比
version: 1.0
category: development
triggers: [代码统计, LOC, 代码行数, 语言分布, 代码库分析, pygount, 项目规模]
---

# 代码库分析（pygount）

## 概述

用 `pygount` 分析代码仓库：行数统计、语言分布、文件数量、代码/注释比率。

## 安装

```bash
pip install pygount
```

## 使用

### 基础汇总

```bash
cd /path/to/repo
pygount --format=summary \
  --folders-to-skip=".git,node_modules,venv,.venv,__pycache__,.cache,dist,build,.next,.tox,.eggs,*.egg-info" \
  .
```

**重要：** 总是使用 `--folders-to-skip` 排除依赖/构建目录，否则 pygount 会遍历它们导致卡死。

### 按语言过滤

```bash
# 只统计 Python 文件
pygount --suffix=py --format=summary .

# 只统计 Python 和 YAML
pygount --suffix=py,yaml,yml --format=summary .
```

### 按项目类型排除

```bash
# Python 项目
--folders-to-skip=".git,venv,.venv,__pycache__,.cache,dist,build,.tox,.eggs,.mypy_cache"

# JS/TS 项目
--folders-to-skip=".git,node_modules,dist,build,.next,.cache,.turbo,coverage"

# 通用
--folders-to-skip=".git,node_modules,venv,.venv,__pycache__,.cache,dist,build,.next,.tox,vendor,third_party"
```

### JSON 输出

```bash
pygount --format=json .
```

## 结果解读

汇总表字段：
- **Language** — 编程语言
- **Files** — 该语言文件数
- **Code** — 实际代码行数
- **Comment** — 注释/文档行数
- **%** — 占比

伪语言：
- `__empty__` — 空文件
- `__binary__` — 二进制文件（图片、编译产物）
- `__generated__` — 自动生成的文件
- `__duplicate__` — 内容完全相同的文件
- `__unknown__` — 无法识别的文件类型

## 坑

1. **始终排除 .git, node_modules, venv** — 否则会遍历整个依赖树
2. **Markdown 显示 0 代码行** — pygount 把 Markdown 全部归类为注释，这是预期行为
3. **大单体仓库** — 考虑用 `--suffix` 指定语言范围，不要全量扫描
