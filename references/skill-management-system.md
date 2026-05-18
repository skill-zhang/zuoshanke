# 技能管理系统设计文档

## 架构概览

坐山客的技能系统是纯文本知识管理系统，区别于工具（Tool）的可执行代码体系。

```
前端 SkillsView (React卡片网格)
    ↕ API: GET/POST/PUT/DELETE /api/skills/{name}
后端 SkillManager (文件式)
    ↕ ～/zuoshanke/skills/<name>/SKILL.md
Agent Loop → context_builder → match_for_context(query) → 注入技能
```

## 文件存储格式

每个技能一个独立目录：`~/zuoshanke/skills/<name>/SKILL.md`

```markdown
---
name: skill-name
description: 说明文字
version: 1.0
category: development     # development/reference/formatting/workflow/general
triggers: [关键词1, 关键词2]
---

正文内容（Markdown）
```

## 触发器匹配机制

SkillManager.match_for_context(query)：
1. 对用户输入分词（CJK字符 + 字母数字单词）
2. 每个 skill 的 triggers 与 query 做子串匹配
3. 按命中数降序排序，取 Top-2
4. 注入到 Agent Loop 的上下文系统提示层

## 前端视图演变

| 阶段 | 实现 | 说明 |
|------|------|------|
| v1 | SkillsDrawer（右侧抽屉） | 空间受限，功能有限 |
| v2 | SkillsView（全页卡片网格） | 同ToolsView风格，分类动态生成 |

## 分类动态化

分类不再硬编码。前端组件从 loaded skills 数据中提取 unique categories：
- 已知分类（development/reference/formatting/workflow/general）按固定顺序显示
- 额外分类自动追加
- 「全部」tab 显示总数

## 导出/导入

技能本质是 SKILL.md 文件（YAML前注+Markdown正文），天然可移植。

**导出：**
- 单技能：详情弹窗「📤 导出」或卡片 ⬇️ 按钮
- 全部：工具栏「📤 导出全部」

**导入：**
- 工具栏「📥 导入」→ 文件选择器
- 前端解析 `---` 前注 → 调用 createSkill API
- 支持多文件选择

## 统计刷新

侧边栏 skillsCount 使用 `useEffect(() => ..., [view])` 依赖，切换视图时自动刷新。
