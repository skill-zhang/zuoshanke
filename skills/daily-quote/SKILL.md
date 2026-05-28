---
name: daily_quote
description: 每日一言 — 励志/哲思/治愈/人生/幽默/爱情/智慧 语录，LLM 生成或名人名言库回退
version: 1.0
category: data
triggers: [每日一言, 早安, 晚安, 励志, 名言, 鸡汤, 语录, 一句话, 暖心, 正能量, 座右铭, quote, 哲思, 治愈, 感悟, 哲理]
---

# 每日一言

## 配套工具

坐山客内置了 `daily_quote` 工具（📊 数据分类），一条语录温暖你的一天：

```bash
# 每日励志（默认）
daily_quote()

# 治愈风格
daily_quote(category="healing")

# 幽默一下
daily_quote(category="humor")

# 从名言库随机选取（不调用 LLM）
daily_quote(category="wisdom", source="curated")
```

## 支持分类

| 分类 | 说明 |
|------|------|
| motivation | 💪 励志 |
| philosophy | 🤔 哲思 |
| healing | 🫂 治愈 |
| life | 🌊 人生 |
| humor | 😂 幽默 |
| love | ❤️ 爱情 |
| wisdom | 🧠 智慧 |

## 来源

- `auto`（默认）— 优先 LLM 创作，失败回退名言库
- `curated` — 仅从内置 70 条名言库随机选取
- `llm` — 仅用本地 Qwen LLM 实时生成

## 定时推送

配合 cronjob 可实现每日自动推送：

```
# 每天早上 8 点推送早安语录
cronjob(
  action="create",
  schedule="0 8 * * *",
  prompt="用 daily_quote 工具生成一条励志语录送给我",
  skills=["daily_quote"]
)
```
