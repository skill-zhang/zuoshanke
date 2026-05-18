---
name: obsidian
description: Obsidian 笔记库操作 — 读取、搜索、创建、编辑笔记，WikiLinks 使用
version: 1.0
category: reference
triggers: [Obsidian, 笔记, 知识库, 日记, markdown笔记, 文档库]
---

# Obsidian 笔记库

## 本地 Obsidian 路径

Windows 路径：`C:\Users\Administrator\Documents\Obsidian Vault\`
WSL 访问路径：**`/mnt/c/Users/Administrator/Documents/Obsidian Vault/`**

⚠️ 注意：`~/Documents/Obsidian Vault` 是 WSL 独立的目录，Windows 端的 Obsidian **看不到它**。始终使用 `/mnt/c/...` 路径。

## 读取笔记

```python
read_file("/mnt/c/Users/Administrator/Documents/Obsidian Vault/笔记名称.md")
```

⚠️ `read_file` 对 `/mnt/c/` 下的路径或含空格的路径可能报 "File not found"。如果失败，改用 terminal 的 `cat`。

## 列出笔记

```python
search_files("*.md", target="files", path="/mnt/c/Users/Administrator/Documents/Obsidian Vault")
```

## 搜索笔记内容

```python
search_files("关键词", target="content",
    path="/mnt/c/Users/Administrator/Documents/Obsidian Vault",
    file_glob="*.md")
```

## 创建笔记

```python
write_file("/mnt/c/Users/Administrator/Documents/Obsidian Vault/新笔记.md",
    content="# 标题\n\n正文内容...")
```

## 追加/编辑笔记

```python
# 先读取
read_file(".../笔记.md")

# 用 patch 追加（找到稳定锚点）
patch(".../笔记.md",
    old_string="# 标题",  # 替换为锚点文本
    new_string="# 标题\n\n新增内容...")
```

## WikiLinks

Obsidian 用 `[[笔记名称]]` 语法链接笔记。创建笔记时可以用这种方式连接相关内容。

## 现有笔记概览

目前库中有以下笔记：
- `欢迎.md`
- `AI Agent 多Agent协作深度探讨.md`
- `LiveKit 开发环境总览.md`
- `LiveKit 网络配置.md`
- `LiveKit ASR 语音识别.md`
- `LiveKit 故障排查.md`
- `2026-05-13.md`（日记）
