# 坐山客自开发场景 — 设计文档（Self-Dev Scene v1.0）

_版本: v1.0 | 日期: 2026-05-23 | 状态: 方案_

---

## 1. 问题陈述

目前坐山客的开发完全依赖外部系统（Hermes Agent）：用户通过微信给 Hermes 下指令，Hermes 通过终端读写文件、跑测试、调 API 来开发坐山客。这产生了两个核心矛盾：

1. **坐山客不能开发自己** — 作为 AI 工作台，这是应该具备的自举（Bootstrapping）能力
2. **外部开发 ≠ 内部开发** — Hermes 有的能力（clarify/delegate/session_search），坐山客应该在自己的 Agent Loop 里原生具备

### 目标

在坐山客内创建一个「坐山客自开发」场景，使坐山客能在这个场景里完成：
- 阅读/分析自己的源码
- 讨论设计方案
- 拆分子任务并行开发
- 联调测试
- 提交代码

**最终形态**：用户不需要切出坐山客前端，就能开发坐山客本身。

---

## 2. 核心概念

### 2.1 「先方案再动手」行为模式

自开发场景的 Agent Loop 与传统场景不同——它不是「收到任务→立即执行」，而是「收到需求→讨论方案→用户确认→执行」的四段式：

```
用户需求
  ↓
① 方案阶段: LLM 分析需求、给出设计方案（不调工具，纯思考+提问）
  │  如果方案有多个选项 → 调 clarify 让用户选择
  │  如果需求不明确 → 调 clarify 追问
  ↓
② 确认阶段: 用户确认方案（或提出修改意见）
  │  用户不确认 → 回到①
  ↓
③ 执行阶段: 按确认的方案执行（调工具、改代码、跑测试）
  │  如果发现需要决策 → 调 clarify 暂停等待
  ↓
④ 展示阶段: 展示执行结果（diff/测试报告/运行截图）
  ↓
完成
```

**实现方式**：不是硬编码的阶段机，而是通过 system prompt 的「行为准则」段注入 + tool description 的负向引导，让 LLM 自主判断何时进入执行阶段。

### 2.2 契约先行

当父 Agent 需要拆分子任务时，必须先产出一份 **接口契约文件**，作为所有子 Agent 的共同参照：

```
shared/INTERFACE.md (由父 Agent 撰写)
├─ API 端点定义（method, path, request, response, error）
├─ 数据模型定义（Pydantic schema 级）
├─ 模块边界约定（谁负责什么）
└─ 测试契约（联调时验证的要点）
```

**原则**：契约是子 Agent 之间唯一的共享上下文。子 Agent 不知道其他子 Agent 的存在，只需要遵守契约。

### 2.3 完全隔离并行

子 Agent 之间：
- ❌ 不共享对话历史
- ❌ 不共享记忆
- ❌ 不直接通信
- ✅ 只读共享的契约文件
- ✅ 各自产生独立的代码文件

父 Agent 负责在联调阶段把它们粘合起来。

### 2.4 三层 Context 共享策略

| 层级 | 内容 | 传递方式 | 适用场景 |
|------|------|---------|---------|
| **L1 任务层** | goal + 上下文描述 | goal + context 参数 | 所有子 Agent |
| **L2 契约层** | API 协议/数据 schema/接口定义 | 引用共享文件路径（INTERFACE.md） | 需要联调的子 Agent |
| **L3 项目层** | 编码风格、测试规范、分支策略、技术栈 | 父 Agent 在 context 中声明 | 子 Agent 需要遵守项目约定时 |

**不共享的**：父 Agent 对话历史、其他子 Agent 的中间结果、父 Agent 记忆、执行过程中的思考链。

---

## 3. 系统架构

### 3.1 架构图

```
┌────────────────────────────────────────────────────────────────┐
│                    自开发场景（场景类型: dev）                      │
│                                                                │
│  System Prompt: 坐山客在【自开发】领域的分身                      │
│  + 「先方案再动手」行为准则                                       │
│  + 项目自省信息（架构文档、代码统计）                              │
│  + 用户记忆（设计哲学+铁律+偏好）全量注入                          │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Agent Loop (扩展版)                                      │  │
│  │                                                          │  │
│  │  标准工具集 + 🆕 开发专用工具:                               │  │
│  │  ├─ clarify          阻塞式追问（新增）                      │  │
│  │  ├─ delegate_task    并行子 Agent（新增）                    │  │
│  │  ├─ git_commit       提交代码（新增）                        │  │
│  │  ├─ browser_dial_test 浏览器拨测（新增·核心能力⭐）           │  │
│  │  ├─ run_tests        跑测试（已有→固化）                     │  │
│  │  ├─ write_design_doc 写设计文档（已有→固化）                  │  │
│  │  └─ 标准工具: file_tools/code_runner/session_search/...    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  上下文构建:                                                    │
│  ├─ 全量本体记忆注入（设计哲学+用户偏好）                          │
│  ├─ 项目层级注入（docs/design/ 目录摘要）                        │
│  └─ 当前场景状态（已确认方案/待执行任务/执行进度）                  │
└────────────────────────────────────────────────────────────────┘
          │
          │ ── 调 clarify ───────────────────→ 前端弹窗（等用户回复）
          │
          │ ── 调 delegate_task ──→ ThreadPoolExecutor
          │                            ├── Child A（后端模块）
          │                            ├── Child B（前端模块）
          │                            └── Child C（联调测试）
          │
          │ ── 调 file_tools/code_runner ──→ 文件系统 + 终端
          │
          └── SSE 事件流 ──→ 前端实时展示
```

### 3.2 文件变更总览

| 文件 | 动作 | 说明 |
|------|------|------|
| `agent_core/agent_loop.py` | 改 | 抽 `_run_loop_blocking()`，支持同步调用作为子 Agent |
| `agent_core/delegate_engine.py` | **新** | 子 Agent 调度器（ThreadPoolExecutor + 结果收集） |
| `agent_core/clarify_handler.py` | **新** | Clarify 阻塞式 callback + SSE Event + threading.Event |
| `tools/clarify_tool.py` | 改 | 自开发场景的 clarify 工具定义（堵塞式） |
| `tools/delegate_tool.py` | **新** | delegate_task 工具定义 |
| `tools/git_tool.py` | **新** | Git 提交/状态工具 |
| `router/scene_stream.py` | 改 | 新增 SSE 事件类型（clarify/child/integration） |
| `tools/browser_dial_test.py` | **新** | 浏览器拨测工具（Playwright 无头浏览器 + DOM快照 + Console + 瀑布） |
| `frontend/src/components/ClarifyDialog.tsx` | **新** | Clarify 弹窗组件 |
| `frontend/src/components/DelegationMonitor.tsx` | **新** | 子 Agent 进度监视组件 |
| `frontend/src/stores/appStore.ts` | 改 | 新增 clarify/delegate 状态 |
| `scripts/seed_dev_scene.py` | **新** | 创建自开发场景 + 注入设计哲学记忆 |
| `docs/design/self-dev-scene.md` | **新** | 本文档 |

---

### 3.3 Browser Dial Test — 浏览器拨测工具 ⭐ 核心能力

**定位**：这不是自开发场景的「附属工具」，是坐山客和 Hermes 拉开差距的关键能力——Hermes 没有浏览器，看不到它产出的 UI。坐山客有了 Browser Dial Test，就能像后端测试一样**自主验证前端代码正确性**，不再依赖用户人肉 reload + 肉眼报告。

#### 3.3.1 什么是「给 AI 用的拨测」

传统拨测（听云/博睿）返回的是性能数据给人看。坐山客的拨测返回的是**浏览器内部状态的结构化数据给 AI 读**：

```json
{
  "url": "http://localhost:5173/scenes",
  "viewport": {"width": 1440, "height": 900},
  "screenshot": "/tmp/screenshots/dial_abc123.png",
  "dom": {
    "elements": [
      {
        "selector": "div.sidebar",
        "tag": "aside",
        "rect": {"x": 0, "y": 0, "w": 240, "h": 900},
        "computed_style": {
          "font-size": "13px",
          "overflow-y": "auto",
          "background": "rgba(30, 30, 45, 1)"
        },
        "children": 12
      },
      {
        "selector": "div.card-grid",
        "tag": "main",
        "rect": {"x": 240, "y": 56, "w": 1200, "h": 844},
        "computed_style": {"overflow": "hidden auto"},
        "scroll": {"height": 2400, "client_height": 844},
        "children": [
          {"selector": "div.card:nth-child(1)", "rect": {"x": 252, "y": 68, "w": 372, "h": 186}},
          {"selector": "div.card:nth-child(2)", "rect": {"x": 636, "y": 68, "w": 372, "h": 186}}
        ]
      }
    ]
  },
  "console": {
    "errors": [],
    "warnings": ["[HMR] Waiting for update signal from WDS..."],
    "count": { "error": 0, "warning": 1 }
  },
  "network": {
    "waterfall": [
      {"url": "/api/scenes", "status": 200, "type": "xhr", "duration_ms": 127, "size": 8472},
      {"url": "/src/main.tsx", "status": 304, "type": "script", "duration_ms": 2},
      {"url": "/assets/Logo-BH7k-4XF.js", "status": 200, "type": "script", "duration_ms": 34}
    ],
    "total_requests": 23,
    "total_duration_ms": 843
  },
  "performance": {
    "fcp_ms": 867,
    "lcp_ms": 1243,
    "cls": 0.02,
    "ttfb_ms": 127
  },
  "assertions": [
    {"name": "无控制台错误", "passed": true},
    {"name": "CLS < 0.1", "passed": true},
    {"name": "卡片数量 >= 3", "passed": true, "actual": 6}
  ]
}
```

#### 3.3.2 三个工具接口

工具注册在 `registry.json` 中，供 Agent Loop 自主调：

| 函数签名 | 用途 | 典型场景 |
|---------|------|---------|
| `dial_test(url, viewport="1440x900")` | 完整拨测：DOM快照 + Console + Network + 性能 | 前端开发后全面验证 |
| `dial_style(url, selectors=["...", "..."])` | 只取特定元素的 computedStyle | 快速排查 CSS 问题 |
| `dial_assert(url, rules=[{selector, style, ...}])` | 断言式检查，返回 pass/fail | 自动化 CI 检查 |

#### 3.3.3 Agent Loop 中的用法示例

**场景：自开发场景里 Agent 改了前端卡片列表样式**

```python
# Agent 调代码写完后，不让你 reload，自己验证：

# Step 1: 完整拨测
report = dial_test("http://localhost:5173/scenes")
# → DOM 中 .card-grid: rect={x:240, y:56, w:1200, h:844}, scroll={height:844, client_height:844}
# → 内容高度正好等于容器高度 → 没有滚动条 → 说明内容被截断了

# Step 2: 分析问题
# LLM 推理：scroll_height(844) == client_height(844)，说明内容没有溢出
# 但按设计应该有很多卡片，6张卡高度合计应该 ~1200px
# → 问题出在 .card-grid 的 overflow 或卡片渲染

# Step 3: 检查计算样式
style = dial_style("http://localhost:5173/scenes",
                   selectors=[".card-grid", ".card"])
# → .card-grid: overflow:"hidden"（缺少 auto）
# → .card: display:none（CSS 选择器冲突导致某些卡片不渲染）

# Step 4: 修复后断言
result = dial_assert("http://localhost:5173/scenes",
    rules=[
        {"selector": ".card-grid", "style": {"overflow": "hidden auto"}},
        {"selector": ".card", "count": {"gte": 3}},
        {"condition": "console_errors == 0"}
    ])
# → 断言通过
```

#### 3.3.4 技术栈

| 层 | 选型 | 原因 |
|----|------|------|
| 浏览器引擎 | Playwright (Chromium headless) | 成熟、Python 原生、pip install 即可 |
| 截图分析 | `tools/analyze_image.py`（已有 Qwen 视觉） | 截图后丢给视觉模型做「人工复查」 |
| 安装 | `pip install playwright` + `playwright install chromium` | 一行安装 |
| 后端集成 | FastAPI 后台异步执行 | 拨测可能耗时 2-5 秒，不阻塞主线程 |

**接口详情**见 `docs/references/browser-dial-test-api.md`，包含：
- Pydantic 响应模型（`DialTestReport` / `DialStyleReport` / `DialAssertResult`）
- 三工具完整签名（`dial_test` / `dial_style` / `dial_assert`）
- 断言规则语法（style / count / console / condition 四类型 + 运算符）
- LLM summary 生成策略
- registry.json 注册格式
- 错误处理表

**为什么 Playwright 而非 Puppeteer**：Playwright 天然支持 Python，API 设计更现代，内置 auto-wait，DOM 结构提取更友好。和坐山客的技术栈（Python + FastAPI）对齐。

#### 3.3.5 成为核心工具的理由

这不是一个「前端调试小工具」，它是一个**改变 Agent 能力边界**的工具：

| 之前（无拨测） | 之后（有拨测） |
|---------------|--------------|
| 写前端代码=猜盲盒 | 写前端代码=可验证的闭环 |
| 前端 bug 依赖用户报告 | 前端 bug 可以自主检测 |
| CSS 问题无法量化 | computedStyle 给出精确值 |
| 布局溢出只能「看着感觉不对」 | scroll_height > client_height 是精确的数值断言 |
| 控制台报错需要用户告诉我 | 自己读取 Console 日志 |
| Network 错误无声无息 | 能看到失败的请求和状态码 |

**更深远的价值**：当拨测工具成为坐山客的核心工具后，**任何一个分身场景**都可以用它——不只是自开发场景。二手车分身可以拨测页面显示效果，旅游分身可以验证景点卡片渲染正确性。它打破了 AI「不知道你做的东西长什么样」的根本限制。

## 4. Clarify 机制设计

### 4.1 阻塞式 Callback 模式

核心设计：Clarify 不是「暂停循环然后恢复」，而是「同步阻塞直到用户回答」。

```
Agent Loop 线程:
  LLM 调 clarify(question, choices)
    → clarify_tool() 调 callback(question, choices)
      → callback 内部:
        ① SSE 发送 zhu:clarify {question, choices, event_id}
        ② 创建 threading.Event()
        ③ 阻塞: event.wait(timeout=300)
        ④ 前端用户回复 → POST /api/agent-loop/clarify-response {event_id, response}
        ⑤ 后端收到 → event.set() + 存 response
        ⑥ event.wait() 返回 → callback 返回 response
    → clarify_tool() 返回 response 给 LLM
  LLM 看到用户选择 → 继续执行
```

### 4.2 数据结构

```python
# agent_core/clarify_handler.py

import threading
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ClarifyRequest:
    event_id: str       # 唯一 ID
    question: str
    choices: Optional[list[str]]
    event: threading.Event = field(default_factory=threading.Event)
    response: str = ""
    created_at: float = 0.0


class ClarifyHandler:
    """全局单例：管理正在等待用户回复的 clarify 请求"""

    _instance = None
    _pending: dict[str, ClarifyRequest] = {}

    @classmethod
    def get_instance(cls) -> "ClarifyHandler":
        ...

    def create_request(self, question: str, choices: list[str] | None) -> ClarifyRequest:
        """创建请求 → 返回 event_id（SSE 发送用）"""

    def wait_for_response(self, event_id: str, timeout: int = 300) -> str:
        """阻塞等待用户回复，返回用户输入"""

    def resolve_request(self, event_id: str, response: str) -> bool:
        """前端调用的 API 端点 → 解锁等待的线程"""

    def cancel_request(self, event_id: str):
        """超时/取消 → 清理"""
```

### 4.3 API 端点

```http
POST /api/agent-loop/clarify-response
  body: {event_id: string, response: string}
  响应: {ok: true}

GET /api/agent-loop/clarify-pending
  响应: {event_id: string | null}
```

### 4.4 SSE 事件

```json
{
  "event": "zhu:clarify",
  "data": {
    "event_id": "clar_abc123",
    "question": "先改 CI 还是先改代码？",
    "choices": ["先修 CI", "先改功能", "两个都做"]
  }
}
```

### 4.5 前端 ClarifyDialog 组件

- 使用已有的 Dialog 组件（`Dialog.tsx`）展示
- 多选题：带编号的按钮组（最多 4 个）+ 「其他（手动输入）」选项
- 开放题：文本输入框
- 用户回复后 → POST /api/agent-loop/clarify-response
- 加载状态：显示「等待 LLM 处理...」

---

## 5. Delegate（子 Agent）机制设计

### 5.1 架构

```
delegate_task(goal, context, toolsets, tasks=[...])
  ↓
DelegateEngine.run()
  ├─ 单任务模式 → 1 个子 Agent
  └─ 批量模式 → ThreadPoolExecutor(max_workers=3)
                    ├─ Thread: Child A
                    │   ├─ 构建 context（goal + context + 契约引用）
                    │   ├─ 创建子 Agent 实例
                    │   │   └─ _run_loop_blocking(task, tools, ...)
                    │   └─ 收集结果（文本摘要）
                    ├─ Thread: Child B
                    │   └─ ...
                    └─ 主线程等待所有 futures 完成
                        ├─ 全部成功 → 合并摘要返回
                        └─ 有失败 → 返回失败信息
```

### 5.2 子 Agent 的 context 构建

```python
class DelegateEngine:
    def _build_child_context(self, task: dict, parent_context: str) -> str:
        parts = []

        # L1: 任务层
        parts.append(f"## 任务\n{task['goal']}\n")
        if task.get("context"):
            parts.append(f"## 上下文\n{task['context']}\n")

        # L2: 契约层（如有共享契约文件）
        if task.get("contract_path"):
            parts.append(f"## 接口契约\n请参照 {task['contract_path']} 中的定义实现\n")

        # L3: 项目层（父 Agent 声明）
        if task.get("project_rules"):
            parts.append(f"## 项目约定\n{task['project_rules']}\n")

        # 身份声明：子 Agent 知道自己是被派来的
        parts.append("## 身份\n你是坐山客派出的开发子 Agent。")
        parts.append("你不知道其他子 Agent 的存在，按本任务的 goal 专注完成自己的工作。")
        parts.append("完成工作后汇报结果摘要，不要自行扩展任务范围。")

        return "\n".join(parts)
```

### 5.3 _run_loop_blocking() — 子 Loop

从 `run_agent_loop()` 中提取可复用的 loop 体：

```python
def _run_loop_blocking(
    task: str,
    tools: list[dict],
    memory_context: str = "",
    scene_config: dict | None = None,
    max_steps: int = 25,
) -> str:
    """同步版本：按 Agent Loop 执行直到返回最终文本。

    对比 run_agent_loop()（Generator）：
    - 不产生 SSE 事件（子场景不需要前端展示）
    - 返回最终文本（不 yield 事件）
    - 不触发 Avatar 心情更新
    - 命中 clarify 工具时立刻失败（子 Agent 不能问用户）
    """
    messages = [{"role": "system", "content": build_child_prompt(task, memory_context, tools)}]
    messages.append({"role": "user", "content": task})

    for _ in range(max_steps):
        response = call_llm_with_tools(messages, tools, ...)

        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc["name"] == "clarify":
                    return json.dumps({"error": "子 Agent 不能问用户问题，请自行决策"})
                result = execute_tool(tc["name", tc["args"]])
                messages.append(...)
        else:
            return response["content"]
    return "已达最大执行步数，任务可能未完成"
```

### 5.4 结果收集

每个子 Agent 返回结构化摘要：

```json
{
  "task": "实现订单 API",
  "status": "success",
  "files_created": ["backend/routes/orders.py", "backend/models/order.py"],
  "test_results": "6/6 测试通过",
  "summary": "实现了 CRUD 订单接口，含输入校验和库存检查"
}
```

父 Agent 拿到后，决定是否需要联调或修复。

### 5.5 SSE 事件（前端监控）

```json
// 子 Agent 开始
{"event": "child:started", "data": {"task_id": "child_1", "goal": "实现订单API"}}

// 子 Agent 完成
{"event": "child:done", "data": {"task_id": "child_1", "status": "success", "files": [...]}}

// 子 Agent 失败
{"event": "child:error", "data": {"task_id": "child_1", "error": "..."}}
```

---

## 6. 协作模型：契约 → 隔离 → 联调

### 6.1 完整流程示例

场景：坐山客需要新增一个「项目管理」页面（前端+后端）

```
用户: "加一个项目管理页面，能查看所有场景的使用统计"

━━━ ① 方案阶段 ━━━
LLM 分析需求:
  - 后端: GET /api/scenes/stats + GET /api/scenes/{id}/stats
  - 前端: ProjectStatsPage.tsx + StatsCard.tsx
  - 数据模型: SceneStats 表（复用已有模型？）
  → LLM 调 clarify: "方案 A: 新表存储统计。方案 B: 实时聚合已有数据。你倾向哪个？"
  → 用户选 A
  → LLM 写方案摘要

━━━ ② 契约阶段 ━━━
LLM 写 shared/INTERFACE.md:
  # 场景统计接口契约
  ## GET /api/scenes/stats
    响应: { total_scenes, by_category: [...], daily_active: int }
  ## GET /api/scenes/{id}/stats
    响应: { scene_id, message_count, avg_duration, last_active }

━━━ ③ 执行阶段 ━━━
LLM 调 delegate_task(tasks=[
  {goal: "实现 POST /api/scenes/stats 端点", ...},
  {goal: "实现 GET /api/scenes/{id}/stats 端点", ...},
  {goal: "实现 ProjectStatsPage 组件", ...},
])
  → Child A: 写后端路由 + 模型
  → Child B: 写查询逻辑
  → Child C: 写前端组件 + mock 测试
  → 并行执行，各自汇报

━━━ ④ 联调阶段 ━━━
LLM 分析所有汇报:
  - 后端已实现，测试通过
  - 前端已实现，mock 测试通过
  → 启动后端 → 发 curl 验证真实 API → 验证前端 mock 数据格式匹配
  → 全部通过 → 调 clarify 问用户:
     "后端和前端都实现了，联调通过。需要提交代码吗？"
  → 用户确认 → git commit
```

### 6.2 联调 Agent 模式

当下场景复杂时，父 Agent 也可以派一个专门的**联调子 Agent**：

```python
delegate_task(goal="完成联调测试",
    context=f"""
    接口契约: shared/INTERFACE.md
    后端文件: {child_a.files}
    前端文件: {child_b.files}
    后端启动命令: uvicorn backend.main:app --port 8000
    联调步骤:
      1. 启动后端
      2. curl 验证 API
      3. 检查前端 API 调用是否匹配契约
    """)
```

联调 Agent 的 context 包含双方文件路径和契约，但它本身不受前后端 Agent 的干扰。

---

## 7. 增量实施路线

### Phase 1（P0）：Clarify 循环 + 自开发场景基础

**核心价值**：能在这个场景里讨论方案、确认后执行

| 步骤 | 改动 | 依赖 |
|------|------|------|
| 1.1 | `agent_core/clarify_handler.py` — 阻塞 Event 模式 | 无 |
| 1.2 | `tools/clarify_tool.py` — 改造支持 callback 注入 | 1.1 |
| 1.3 | `router/scene_stream.py` — 新增 `zhu:clarify` 事件处理 | 1.2 |
| 1.4 | `router/scene_stream.py` — 新增 `POST /api/agent-loop/clarify-response` | 1.3 |
| 1.5 | `frontend/src/components/ClarifyDialog.tsx` — 弹窗 + 选择 | 1.4 |
| 1.6 | `scripts/seed_dev_scene.py` — 创建「坐山客自开发」场景 + 注入设计哲学记忆 | 无 |
| 1.7 | `agent_core/context_builder.py` — 自开发场景 prompt 含「先方案再动手」准则 | 1.6 |

**验证**：在自开发场景输入「我想加个新功能」→ 看到 LLM 先问方案 → 选择后执行。

### Phase 2（P1）：Browser Dial Test + Delegate 子 Agent

**核心价值**：前端开发可自主验证 + 能并行拆分子任务

| 步骤 | 改动 | 依赖 |
|------|------|------|
| 2.1 | `tools/browser_dial_test.py` — dial_test / dial_style / dial_assert 三个工具接口 | 无（pip install playwright） |
| 2.2 | `agent_core/agent_loop.py` — 抽 `_run_loop_blocking()` | 无 |
| 2.3 | `agent_core/delegate_engine.py` — ThreadPoolExecutor + 子 Agent 创建 | 2.2 |
| 2.4 | `tools/delegate_tool.py` — delegate_task 工具定义 | 2.3 |
| 2.5 | `router/scene_stream.py` — 新增 `child:*` SSE 事件 | 2.4 |
| 2.6 | `frontend/src/components/DelegationMonitor.tsx` — 子 Agent 进度展示 | 2.5 |

**验证**：在自开发场景说「拆两个子任务做 A 和 B」→ 看到并行子 Agent 进度。

### Phase 3（P2）：契约 + 联调完善

**核心价值**：完整协作开发闭环

| 步骤 | 改动 | 依赖 |
|------|------|------|
| 3.1 | `tools/git_tool.py` — git add/commit/status | 无 |
| 3.2 | 父 Agent prompt 补充「契约先行」行为指引 | Phase 2 |
| 3.3 | 联调 Agent 模式支持（`_run_loop_blocking` 传 context 含双方文件路径） | Phase 2 |
| 3.4 | `scripts/seed_dev_scene.py` 补全自开发场景工具集 | Phase 2 |

**验证**：完整流程：需求→方案→拆任务→并行开发→前端拨测验证→联调→提交。

---

## 8. 边界情况

### 8.1 子 Agent 超时

```python
# child 默认 300 秒超时
future.result(timeout=300)
# 超时 → future.cancel() → 汇报 "子任务超时，请考虑拆分或增加资源"
```

### 8.2 子 Agent 需要 clarify

子 Agent 的 toolset 里排除 clarify 工具。如果 LLM 坚持要问，返回错误信息：「子 Agent 不能问用户问题，请自行决策」。子 Agent 通常会在下一条回复中自己做决定。

### 8.3 多个用户同时操作自开发场景

当前 zuoshanke 的场景是单用户模式（超级租户），无需考虑并发冲突。如果以后引入多用户，每个用户的自开发场景独立、记忆隔离。

### 8.4 子 Agent 破坏父 Agent 的文件

所有子 Agent 通过文件工具写入文件，和父 Agent 在同一个文件系统上。不存在「子 Agent 特别权限」的问题——工具执行器的权限是一样的。父 Agent 在联调阶段会核对文件变更。

### 8.5 当前场景 Frontend SSE 混淆

子 Agent 的 SSE 事件需要和父 Agent 的 SSE 事件区分：
- 父 Agent 走原有的 SSE 通道（`POST /api/scenes/{id}/stream`）
- 子 Agent 的 `child:*` 事件也通过**同一条 SSE 连接**发送（父 Agent 是这场的唯一 holder）
- 前端 `DelegationMonitor` 独立渲染 `child:*` 事件，不影响 ChatView 的主消息流

---

## 9. 未解决问题

1. **子 Agent 的 LLM 模型** — 子 Agent 复用父 Agent 的 DeepSeek Flash 还是可以用本地 Qwen3 节省成本？建议默认复用，可配置
2. **最大并行数** — 当前确定 3 个（和 Hermes 一致），后期可通过场景配置调整
3. **子 Agent 的失败传播** — 一个子任务失败，其他并行子任务是否继续？建议继续（完成的任务结果仍然有价值），父 Agent 汇报时说明
4. **契约文件的位置** — 放 `shared/INTERFACE.md` 还是按场景放在 `docs/dev/{timestamp}-contract.md`？倾向于后者，避免冲突
5. **契约文件版本管理** — 是否需要保留历史契约？建议用 git 管理，每次联调完成后契约文件随代码一起提交
6. **Browser Dial Test 的资源消耗** — Playwright Chromium headless 约 200MB 内存，拨测一次 2-5 秒。是否要限制并发拨测？建议每个场景最多 1 个并发拨测
7. **拨测是否接入 Auto-converge** — 拨测发现前端 bug 时，是否自动写入 ThinkingMap？建议作为收敛检测的补充信号，但优先由 LLM 自主决定
8. **拨测的截图存留策略** — `/tmp/screenshots/` 下的截图自动清理还是手动？建议 LRU 清理，保留最近 50 张

---

## 10. 相关文档

- `docs/design/schema-v1.0.md` — 7 层 Context 组合架构
- `docs/design/schema-v1.1.md` — Session 管理
- `docs/design/dual-memory-pool-v2.md` — 双重记忆池
- `agent_core/agent_loop.py` — 当前 Agent Loop（需要抽取 `_run_loop_blocking`）
- `agent_core/tool_executor.py` — 工具执行器
- `tools/clarify_question.py` — 现有 clarify 雏形（需改造）
- `tools/diverge_tool.py` — 现有发散工具（参考注册模式）
- `devops/zuoshanke-agent-loop` — Agent Loop 技能（含已知排坑）
- `devops/zuoshanke-identity-architecture` — 身份架构（含分身 context 构建）
- `tools/browser_dial_test.py` — 浏览器拨测工具（设计参考，Phase 2 实现）
- `Playwright Python 文档` — https://playwright.dev/python/ （安装及 DOM 提取 API）
