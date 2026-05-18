---
name: spike
description: 快速验证实验 — 在投入正式开发前用一次性代码验证想法可行性
version: 1.0
category: development
triggers: [原型, 实验, 验证, spike, 可行性, 尝试, 对比方案, PoC]
---

# Spike — 快速验证实验

## 核心理念

在投入正式开发前，用一次性代码快速验证想法的可行性。Spike 是消耗品，验证完就扔掉。

## 核心流程

```
分解 → 调研 → 构建 → 裁决
 ↑________________________↓
       基于发现迭代
```

### 1. 分解

把想法拆成 **2-5 个独立的可行性问题**。每个问题是一个 spike。

| # | Spike | 验证什么 | 风险 |
|---|-------|---------|------|
| 001 | websocket-streaming | WebSocket连接后LLM流式输出，客户端<100ms收到 | 高 |
| 002a | pdf-parse-pdfjs | 用pdfjs解析多页PDF，提取结构化文本 | 中 |
| 002b | pdf-parse-camelot | 用camelot解析多页PDF，提取结构化文本 | 中 |

**按风险排序。** 最可能导致想法被否定的 spike 先跑。

### 2. 对齐（多spike场景）

展示 spike 表格，问用户："按这个顺序全部做，还是调整？"

### 3. 调研（每个spike开始前）

每个 spike 先做简短调研：
1. **简要说明：** 2-3句：这个 spike 是什么，为什么重要，关键风险
2. **列出候选方案**（如果有真正的选择）
3. **选一个。** 说明理由。

跳过纯逻辑问题（无外部依赖）的调研。

### 4. 构建

每个 spike 一个独立目录：

```
spikes/
├── 001-websocket-streaming/
│   ├── README.md
│   └── main.py
├── 002a-pdf-parse-pdfjs/
│   ├── README.md
│   └── parse.js
└── 002b-pdf-parse-camelot/
│   ├── README.md
│   └── parse.py
```

**偏向能让用户交互的东西。** Spike 失败的时候通常是因为唯一的输出是一行"it works"日志。默认选择（按偏好排序）：
1. 可运行的 CLI，接受输入并打印可观察的输出
2. 最小的 HTML 页面展示行为
3. 小 web 服务，暴露一个端点
4. 单元测试，用可识别的断言验证问题

**深度胜过速度。** 走完一个 happy-path 就说"它工作了"是不够的。测试边界情况。跟随令人惊讶的发现。

**避免** 除非 spike 特别需要：复杂的包管理、构建工具、Docker、环境文件、配置系统。硬编码一切——这是 spike。

### 5. 裁决

每个 spike 的 README.md 以评估结尾：

```markdown
## 裁决：VALIDATED | PARTIAL | INVALIDATED

### 什么有效
- ...

### 什么无效
- ...

### 意外发现
- ...

### 对正式构建的建议
- ...
```

**VALIDATED** = 核心问题被肯定回答，有证据
**PARTIAL** = 在约束条件 X,Y,Z 下可用——记录它们
**INVALIDATED** = 不可行，原因是这个。这是一个成功的 spike

## 对比型 Spike

当两种方案回答同一问题（002a / 002b），做完后做头对头对比：

```markdown
## 头对头：pdfjs vs camelot

| 维度 | pdfjs (002a) | camelot (002b) |
|------|--------------|----------------|
| 提取质量 | 9/10 结构化 | 7/10 仅表格 |
| 设置复杂度 | npm install, 1行 | pip + ghostscript |
| 100页PDF性能 | 3s | 18s |
| 处理旋转文字 | 否 | 是 |

**赢家：** 对我们的用例选 pdfjs。
```

## 输出

- 在项目根目录创建 `spikes/` 目录
- 每个 spike 一个子目录：`NNN-descriptive-name/`
- 每个 spike 的 `README.md` 包含问题、方法、结果、裁决
- 代码保持消耗品性质——一个需要花2天"清理才能上线"的 spike 是失败的 spike
