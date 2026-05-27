# Precipitate 工具 设计方案

## 背景
需要开发一个 `precipitate` 工具，用于"沉淀"知识——将对话中的关键信息、结论、知识点提取并持久化存储。参照 `tools/git_tool.py` 的模式实现，注册到 `registry.json`。

## 设计目标
- 功能目标：提供知识沉淀功能，将用户对话中的关键信息保存为结构化笔记
- 非功能目标：遵循现有工具模式（schema 定义 + 实现函数 + registry 注册）

## 架构方案
参照 git_tool.py 的三层模式：
1. Schema 定义（OpenAI Function-Calling 格式）
2. 工具函数实现
3. registry.json 注册

## 组件划分
### 文件：`tools/precipitate_tool.py`
- `PRECIPITATE_SCHEMA` — 工具 schema 定义
- `precipitate(content, tags, source)` — 核心函数，将内容沉淀到知识库

### 存储
沉淀的内容写入 `~/.hermes/precipitate/` 目录下的 markdown 文件，按日期组织。

## 接口设计
### precipitate(content, tags, source)
- content: 要沉淀的内容（必填）
- tags: 标签列表（可选）
- source: 来源描述（可选）

返回: `{success, file_path, content_summary}`
