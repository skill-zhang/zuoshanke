---
name: baike
description: 百科知识查询 — 基于本地 Qwen LLM + 维基百科回退。查概念、人物、事件、技术术语
version: 1.0
category: data
triggers: [百科, 维基百科, 是什么, 什么意思, 谁, 什么是, 介绍, 解释, 概念, 术语, 知识, 查询, 定义, 意思, 指的是, 百科知识, 知识查询, who, what, wikipedia, 百度百科, 定义]
---

# 百科知识查询

## 配套工具

坐山客内置了 `baike` 工具（📊 数据分类），随时随地查知识：

```bash
# 中文查询
baike(query="人工智能")

# 英文查询
baike(query="Python", lang="en")

# 快速摘要（不返回分类/相关条目）
baike(query="机器学习", summary_only=True)
```

## 输出内容

| 字段 | 说明 |
|------|------|
| `title` | 条目标题 |
| `summary` | 详细摘要（300-500字） |
| `categories` | 分类标签 |
| `sections` | 章节结构 |
| `related` | 相关条目链接 |
| `source` | 数据来源（llm / wikipedia） |

## 工作原理

1. **优先尝试维基百科** — 网络可达时获取结构化百科数据
2. **回退本地 LLM** — 维基不可达时，用本地 Qwen LLM 生成百科条目
3. 两种来源都保证有结构化输出（摘要+分类+章节+相关条目）

## 注意事项

- 无需 API Key，无需注册
- 国内网络环境下维基百科可能不可达，自动回退本地 LLM
- 本地 LLM 模式下所有数据实时生成，准确性参考 LLM 知识范围
