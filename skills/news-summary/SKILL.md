---
name: news_summary
description: 每日新闻摘要 — 自动抓取主流中文新闻源，生成分类简报。支持要闻/科技/生活/综合分类
version: 1.0
category: data
triggers: [新闻, 今天新闻, 每日新闻, 新闻摘要, 早报, 晚报, 今天发生什么, 有什么新闻, 今日要闻, 科技新闻, 热点, news, 今天有什么新闻, 最新消息, 时事]
---

# 每日新闻摘要

## 配套工具

坐山客内置了 `news_summary` 工具（📊 数据分类），自动抓取主流中文新闻源，生成结构化每日简报：

```bash
# 要闻（默认）
news_summary()

# 科技新闻
news_summary(category="tech")

# 生活效率
news_summary(category="life")

# 综合（全部源）
news_summary(category="all", max_items=5)
```

## 新闻来源

| 分类 | 来源 |
|------|------|
| 📰 要闻 | IT之家 |
| 💻 科技 | 36氪、Solidot |
| 🌿 生活 | 少数派 |
| 📡 综合 | 以上全部 |

## 输出内容

- `summary` — LLM 生成的分类摘要（按主题分组）
- `items` — 原始条目列表（标题 + 链接 + 摘要）
- `sources` — 成功抓取的来源
- `fetched_at` — 抓取时间

## 注意事项

- 基于本地 Qwen LLM 做智能摘要，无需网络
- 但 RSS 抓取需要网络连接
- 某些新闻源可能偶发不可用，工具会自动跳过
- 适合配合 cronjob 实现每日自动推送
