---
name: skill-authoring
description: 坐山客技能编写指南 — SKILL.md 格式规范、触发词设计、CRUD API 操作
version: 1.0
category: development
triggers: [技能编写, SKILL.md, 技能格式, 创建技能, 技能管理]
---

# 坐山客技能编写指南

## 概述

坐山客的「技能（Skill）」是纯文本知识文件，存储在 `~/zuoshanke/skills/<name>/SKILL.md`。技能不含可执行代码（那是工具 Tool 的事），只记录「怎么写」的方法论知识。

当用户对话命中技能的触发词时，坐山客的 Agent Loop 会自动将技能正文注入上下文窗口，指导 AI 的行为。

## 技能 vs 工具

| | 技能 (Skill) | 工具 (Tool) |
|---|---|---|
| 本质 | 纯文本知识 | 可执行代码 |
| 存储 | `~/zuoshanke/skills/<name>/SKILL.md` | `~/zuoshanke/tools/<name>.py` |
| 用途 | 指导 AI「怎么做」 | 让 AI 能执行操作 |
| 触发 | 关键词匹配（triggers） | 函数注册表 |
| 管理界面 | SkillsDrawer | ToolsDrawer |

## SKILL.md 格式

```markdown
---
name: my-skill-name
description: 简短的说明（200字以内）
version: 1.0
category: development        # 分类：development / reference / formatting / workflow
triggers: [关键词1, 关键词2, 关键词3, 别太长]
---

# 正文标题

正文内容，Markdown 格式。
```

### 前注字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 小写英文+数字+下划线，最长64字符 |
| `description` | 是 | 一句话说明（≤200字符），出现在技能列表 |
| `version` | 是 | 版本号，如 "1.0" |
| `category` | 是 | 分类：`development` / `reference` / `formatting` / `workflow` / `general` |
| `triggers` | 否 | 触发词数组，Agent Loop 检测到这些词时自动注入技能 |

## 触发词设计原则

触发词是坐山客 Agent Loop 匹配用户消息的依据：

1. **覆盖常用表达** — 比如天气技能设 `[天气, 气温, 温度, 预报]`，用户说"今天多少度"就能命中
2. **精准不等于稀疏** — 设得太少可能漏命中，设得太泛可能误命中。每个技能4-8个词合适
3. **中英文混合** — 中文词优先（因为用户大概率说中文），英文术语也补充（如 `[TDD, 测试驱动]`）
4. **避免通用词** — 如 `[文件, 代码, 函数]` 太泛，几乎每条消息都触发

## 使用 API 管理技能

### 列表（不含正文）
```bash
GET /api/skills
GET /api/skills?category=development
```

### 查看（含正文）
```bash
GET /api/skills/{name}
```

### 创建
```bash
POST /api/skills
{
    "name": "my-skill",
    "description": "说明",
    "content": "正文...",
    "triggers": ["触发词"],
    "category": "development",
    "version": "1.0"
}
```

### 更新
```bash
PUT /api/skills/{name}
{
    "description": "新说明",
    "content": "新正文...",
    "triggers": ["新触发词"]
}
```

### 删除
```bash
DELETE /api/skills/{name}
```

### 触发器匹配
```bash
GET /api/skills/match?query=用户说的内容&max_count=2
```

## 使用 SkillsDrawer UI 管理

前端侧边栏 SkillsDrawer 提供图形化界面，支持：
- **刷新列表** — 查看所有技能
- **新建技能** — 填写名称、说明、正文、触发词、分类
- **查看详情** — 点击技能条目展开完整内容
- **编辑技能** — 修改元信息或正文
- **删除技能** — 确认后删除

## 最佳实践

1. **正文不要太长** — 太长会占用上下文 Token。控制在2000字以内，需要详细说明的可以拆分为多个技能
2. **举例胜过说教** — 用代码块或实际案例演示使用方法
3. **版本管理** — 每次更新递增版本号，旧版本保留在 `references/` 下用于对比
4. **触发词要与正文相关** — 不要让用户提 A 问题时命中 B 技能的正文
5. **定期清理** — 不再适用的技能及时删除，避免污染上下文
