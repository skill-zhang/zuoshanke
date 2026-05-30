---
title: Schema v1.8.1 — ChatView 性能优化（组件隔离 + 虚拟列表）+ 前端质量第四层
description: ChatView 拆解为 ChatView（消息列表）+ ChatInputArea（独立输入区），引入 react-window v2 虚拟列表根治消息多卡顿，新增 Layer 2.5（tsc 单文件类型检查）堵住类型错误漏洞。
tags:
  - schema
  - performance
  - frontend
  - virtual-list
  - quality
---

# Schema v1.8.1 — ChatView 性能优化 + 前端质量第四层

## 摘要

v1.8.1 聚焦两个用户可见的性能问题和一个工程流程漏洞：

| 问题 | 根因 | 修复 |
|------|------|------|
| 消息多时输入框打字卡顿 | `input` 状态与消息列表在同一组件 → 每次按键触发全量重渲染 | 提取 ChatInputArea 独立组件 |
| 消息列表滚动/渲染卡顿 | `displayMessages.map(...)` 全量渲染所有 DOM 节点 | react-window v2 虚拟列表 |
| 类型错误漏检到运行时 | 三层防御链缺失类型检查环节 | 新增 Layer 2.5（tsc 单文件检查） |

## 1. ChatInputArea 组件隔离

### 问题

ChatView 是 ~1500 行的重型组件，包含消息列表、多选、会话面板、记录浏览器、AgentLoopDashboard、错误横幅、**输入区**（textarea + 发送按钮 + 文件上传 + 附件预览 + 容量警告 + Token 用量）。

`input` 状态（`useState('')`）和消息列表在同一组件中。每次按键：

```
setInput(e.target.value) → ChatView 重渲染
  → 30+ hooks 重新评估
  → displayMessages.map(...) 全量 MessageBubble 重渲染（含 ReactMarkdown）
  → 消息越多 → 协调器对比越多 → 输入框越卡
```

### 修复

将输入区所有状态和 JSX 提取到 **ChatInputArea.tsx**（338 行独立组件）。ChatView 只渲染 `<ChatInputArea />`，`input` 状态变化只重渲染 tiny 的输入区组件。

| 指标 | 之前 | 之后 |
|------|:----:|:----:|
| ChatView 行数 | ~1514 | ~1430 |
| ChatInputArea 行数 | — | 338 |
| 输入区重渲染范围 | 整个 ChatView | 仅 ChatInputArea |

### 改动文件

| 文件 | 操作 | 说明 |
|------|:----:|------|
| `frontend/src/components/ChatView.tsx` | 删改 | 移除 ~330 行输入相关代码，改为 `<ChatInputArea />` |
| `frontend/src/components/ChatInputArea.tsx` | **新建** | 独立的输入区组件 |

### 排坑

提取过程中发生过 `currentModelName is not defined` ReferenceError——`currentModelName` 从 store destructuring 移除后，ChatView 残留了一段 `displayModel = currentModelName || defaultModel` 派生计算未被清理。教训：store destructuring 字段移除后必须 grep 全文件确认无残留引用。

## 2. 虚拟列表 (react-window v2)

### 问题

消息列表使用 `displayMessages.map(...)` 全量渲染，200 条消息就是 200 个 MessageBubble DOM 节点（每条含 ReactMarkdown + 工具卡片 + 工具日志）。随着消息累积，列表滚动和新消息出现时的 UI 卡顿逐渐加重。

### 修复

用 **react-window v2.2.7 的 `List`** 组件替代全量 map，只有可视区域附近（~30 个节点）的 DOM 存在。

| 指标 | 之前 | 之后 |
|------|:----:|:----:|
| 200 条消息的 DOM 数 | 200+ MessageBubble | ~30 个 |
| 1000 条消息 | 1000+ | ~30 个 |
| 滚动帧率 | 随消息数下降 | 恒定 |

### react-window v2 API 适配

本次安装的是 **react-window v2.2.7**，其 API 与网上流行的 v1.x 不兼容。关键差异：

| 功能 | v1（网上搜到的示例） | v2（实际安装的 2.2.7） |
|------|---|---|
| 导出名 | `FixedSizeList` | `List` |
| 行数 | `itemCount` | `rowCount` |
| 行高 | `itemSize` | `rowHeight` |
| 行渲染 | `children` render prop | `rowComponent={Comp}` + `rowProps={data}` |
| 关联 ref | `ref={listRef}` | `listRef={ref}`（内部 `useImperativeHandle`） |
| 滚动到行 | `scrollToItem(idx, align)` | `scrollToRow({index, align, behavior})` |
| 滚动到位置 | `scrollTo(px)` | 不支持（需换算为行索引 `scrollToRow`） |
| 容器高度 | 传 `height` prop | 自动填父容器 + `defaultHeight` 初始值 |

### 改动文件

| 文件 | 操作 | 说明 |
|------|:----:|------|
| `frontend/package.json` | 依赖 | 新增 `react-window@2.2.7`、`@types/react-window` |

### 排坑

1. **v2 的 `List` 而不是 `FixedSizeList`**：import 写错直接运行时 SyntaxError
2. **`rowComponent` 必须稳定引用**：不能 inline arrow，必须 `useCallback([], [])`，数据通过 `rowProps` 传递
3. **v2 不支持 `scrollTo(px)`**：加载更早消息后滚动位置恢复需换算行索引
4. **`onScroll` 是原生 HTML 事件**：接收 `React.UIEvent<HTMLDivElement>` 而非 v1 的 `{scrollOffset}`
5. **`overflow: visible` 必须显式设置**：v2 默认 `overflow: hidden` 在行 style 上

## 3. 前端质量第四层（Layer 2.5 类型检查）

### 问题

原三层防御链漏掉了两个常见错误类型：

| 错误类型 | 漏检原因 | 本次翻车实例 |
|----------|---------|-------------|
| 未定义变量 | ESLint 在 TS 项目中默认关闭 `no-undef` | `currentModelName is not defined` |
| 导入名不存在 | ESLint 无法跨模块推断 | `Module 'react-window' has no exported member 'FixedSizeList'` |

### 修复

在 Layer 1（语法）和 Layer 2（ESLint）之间插入 **Layer 2.5：单文件 tsc 类型检查**：

```bash
cd frontend
npx tsc --noEmit --skipLibCheck 2>&1 | grep "src/components/修改的文件.tsx"
# 无输出 = 类型通过
# 有输出 = 类型错误
```

### 生效范围

- 写入 SKILL.md（zuoshanke-frontend）的固定流程
- 写入 `references/frontend-code-quality.md`
- 写入 memory 防止遗漏

## 改动文件一览

| 文件 | 操作 | 类别 |
|------|:----:|:----:|
| `frontend/src/components/ChatInputArea.tsx` | **新建** | 组件隔离 |
| `frontend/src/components/ChatView.tsx` | 删改 | 组件隔离 + 虚拟列表 |
| `frontend/package.json` | 依赖变更 | 虚拟列表 |
| `docs/design/schema-v1.8.1.md` | **新建** | 本文档 |

## 回滚指南

```bash
# ChatInputArea 提取 + 虚拟列表
git revert HEAD --no-commit
# 或选择性回滚
git checkout HEAD~1 -- frontend/src/components/ChatView.tsx
git checkout HEAD~1 -- frontend/src/components/ChatInputArea.tsx  # 删除
git checkout HEAD~1 -- frontend/package.json  # 恢复依赖
```
