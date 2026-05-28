# 坐山客面向普通用户的工具目录

> 2026-05-28 新增，共 10 个工具，4 轮 commit

## 总览

| 工具 | 函数 | icon | 分类 | 依赖 | 网络需求 |
|------|------|------|------|------|---------|
| 翻译 | translate | 🌐 | data | 本地 Qwen LLM | 否 |
| 新闻摘要 | news_summary | 📰 | data | 本地 Qwen LLM | 是（RSS抓取） |
| 二维码生成 | generate_qrcode | 📱 | system | qrcode + Pillow | 否 |
| 每日一言 | daily_quote | 💬 | data | 本地 Qwen LLM / 名言库 | 否 |
| 菜谱推荐 | recipe | 🍳 | data | 本地 Qwen LLM | 否 |
| 计算器 | calculator | 🧮 | data | 纯 Python 标准库 | 否 |
| 百科查询 | baike | 📚 | data | 本地 Qwen LLM + 维基回退 | 否（LLM模式）/ 是（维基模式） |
| 图片生成 | image_gen | 🎨 | data | Pollinations.ai API + Pillow | 是 |
| 邮件发送 | send_email | 📧 | system | smtplib（标准库） | 是（SMTP） |
| 快递查询 | express_tracking | 📦 | data | 快递100 API | 是 |

## 文件结构

```
tools/
├── translate.py           # 翻译，13语言
├── news_summary.py        # 新闻摘要，4分类
├── qrcode_tool.py         # 二维码生成（text/wifi/vcard）
├── daily_quote.py         # 每日一言，7风格+70条名言库
├── recipe.py              # 菜谱推荐，8菜系
├── calculator.py          # 计算器，10类单位+数学+日期
├── baike.py               # 百科查询，本地LLM+维基
├── image_gen.py           # 文生图，Pollinations+Pillow
├── send_email.py          # 邮件发送，SMTP+8预设
├── express_tracking.py    # 快递查询，50+公司
├── registry.json          # 注册表（全部已注册）

skills/
├── translate/SKILL.md
├── news-summary/SKILL.md
├── generate-qrcode/SKILL.md
├── daily-quote/SKILL.md
├── recipe/SKILL.md
├── calculator/SKILL.md
├── baike/SKILL.md
├── image-gen/SKILL.md
├── send-email/SKILL.md
└── express-tracking/SKILL.md

frontend/src/components/ToolsView.tsx  → ICON_MAP（全部已加图标）
```

## 设计决策

### 1. 百科查询 — 本地LLM优先

**背景：** 维基百科在国内网络不可达（Errno 101）。

**方案：** baike 工具先尝试维基百科 REST API（8秒超时），失败则回退到本地 Qwen LLM。LLM 模式下通过精心构造的 system prompt 要求输出结构化 JSON（title/summary/categories/sections/related），确保返回格式与维基模式一致。

**tradeoff：** LLM 模式的知识截止时间和准确性不如维基百科，但胜在不依赖网络、响应速度快。

### 2. 图片生成 — 免费API + 本地备选

**背景：** 无本地 Stable Diffusion，无 ComfyUI，无 API Key。

**方案：** 使用 Pollinations.ai（免费，无需 Key），地址格式 `https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&nologo=true`。含自动重试（最多2次）。全部失败时用 Pillow 生成文字占位图。

**tradeoff：** Pollinations 偶发 402 / 超时，占位图虽丑但保证始终有输出。

### 3. 计算器 — 纯标准库

**背景：** 单位换算需要精确结果，LLM 容易翻车。

**方案：** 全部用 Python 标准库（math/datetime/ast），无任何第三方依赖。10 类单位换算表硬编码 SI 基准系数。温度用精确公式。日期计算考虑闰年/大小月。数学表达式用受限 eval（只开放 abs/sqrt/pow/sin/cos/log 等安全函数）。

### 4. 邮件发送 — SMTP预设优先

**背景：** 每个邮箱的 SMTP 配置不同，普通用户不一定知道。

**方案：** 内置 8 种常见邮箱的 SMTP 预设（QQ/163/126/Gmail/Outlook/Aliyun/Sina）。用户只需选 provider + 填账号密码。密码支持环境变量（ZUOSHANKE_SMTP_*）避免每次重复传参。

## 前端集成

所有工具的 ICON_MAP 条目集中在 `ToolsView.tsx` 第 21-28 行。添加新工具时追加 key-value。

## Commit 历史

```
fb12fad express_tracking  快递查询
336f2e2 send_email        邮件发送
3af8c8e image_gen         文生图
a8562f7 baike             百科查询
3cdae31 calculator        计算器
4b538f2 recipe            菜谱推荐
e5df277 daily_quote       每日一言
773ffba generate_qrcode   二维码
f270367 news_summary      新闻摘要
7019578 translate         翻译
```

## 后续可能的扩展

- **history**: 工具调用历史记录/收藏
- **batch**: 批量处理（多条翻译/多张二维码）
- **template**: 常用参数模板（如定时发送新闻到邮箱 = news_summary + send_email 组合）
- **cron 联动**: 更多定时推送（每日新闻、天气预报、生日提醒等）
