---
name: translate
description: 多语言翻译工具 — 基于本地 Qwen LLM，13种语言互译，自动检测源语言、双语对照、例句模式
version: 1.0
category: data
triggers: [翻译, 翻一下, 译, 英译中, 中译英, 怎么读, 什么意思, 英文怎么说, 中文意思, 翻译成, translate, translation, 翻成, 帮我翻译, 把这段话翻译]
---

# 多语言翻译

## 配套工具

坐山客内置了 `translate` 工具（📊 数据分类），基于本地 Qwen LLM 进行高质量翻译，无需网络连接：

```bash
# 自动检测源语言，翻译成英语（默认）
translate(text="你好，今天天气真好")

# 指定源语言和目标语言
translate(text="Hello, nice to meet you", source="en", target="zh-CN")

# 双语对照
translate(text="Life is what happens when you're busy making other plans", target="zh-CN", format_mode="dual")

# 译文+例句
translate(text="Serendipity", target="zh-CN", format_mode="examples")

# 日译中
translate(text="こんにちは", target="zh-CN")

# 法译英
translate(text="Bonjour le monde", source="fr", target="en")
```

## 支持的语言

| 代码 | 语言 | 代码 | 语言 |
|------|------|------|------|
| zh-CN | 🇨🇳 中文 | en | 🇬🇧 英语 |
| ja | 🇯🇵 日语 | ko | 🇰🇷 韩语 |
| fr | 🇫🇷 法语 | de | 🇩🇪 德语 |
| es | 🇪🇸 西班牙语 | ru | 🇷🇺 俄语 |
| pt | 🇵🇹 葡萄牙语 | it | 🇮🇹 意大利语 |
| th | 🇹🇭 泰语 | vi | 🇻🇳 越南语 |
| ar | 🇸🇦 阿拉伯语 | | |

## 输出模式

| 模式 | 说明 |
|------|------|
| `normal` | 仅输出译文（默认） |
| `dual` | 原文 + 译文双语对照 |
| `examples` | 译文 + 典型用法例句 |

## 注意事项

- 使用本地 Qwen LLM，无需网络连接
- 支持自动检测源语言（`source="auto"`）
- 保留代码/HTML 结构，只翻译自然语言
- 文本最多 8000 字符
