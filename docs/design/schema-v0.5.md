# 坐山客架构 Schema v0.5 — Agent Core 纪元

> 版本: 2026-05-17
> 核心变更: 从"Hermes 子进程调度"升级为**自有 Agent Core**，集成工具调用、Memory、Skill 管理、自动造工具闭环
> 哲学基础: LLM 是大脑，Agent Core 是身体。LLM 发号施令，Core 执行、记忆、学习

---

## 目录
1. [Agent Core —— 坐山客自己的执行引擎](#一agent-core--坐山客自己的执行引擎)
2. [工具系统 —— 让 LLM 知道它能用啥](#二工具系统--让-llm-知道它能用啥)
3. [工具调用循环](#三工具调用循环)
4. [工具发现层 —— 先搜再用，不重复造轮子](#四工具发现层--先搜再用不重复造轮子)
5. [工具缺失 → 自动造工具闭环](#五工具缺失--自动造工具闭环)
6. [Memory 系统](#六memory-系统)
7. [Skill 系统](#七skill-系统)
8. [Context 构造 —— 给 LLM 的"世界视图"](#八context-构造--给-llm-的世界视图)
9. [沙箱隔离与并行](#九沙箱隔离与并行)
10. [全局架构流程](#十全局架构流程)
11. [数据结构变更总览](#十一数据结构变更总览)
12. [从 v0.4 到 v0.5 的迁移路径](#十二从-v04-到-v05-的迁移路径)

---

## 一、Agent Core —— 坐山客自己的执行引擎

### 为什么

v0.4 的执行引擎是 Hermes 子进程（`subprocess.Popen("hermes chat -q ...")`）。问题：

| 问题 | 代价 |
|------|------|
| 冷启动 8-12s 每次 | 每个工具调用都要等 |
| 黑盒 | stdout 解析不可靠，错误难排查 |
| 无法深度集成 | memory、skill 都是 Hermes 的，不是我们的 |
| 并行受限 | 进程模型太重 |
| 无工具主动发现 | Hermes 的 function calling 是框架实现的，我们拿不到中间状态 |

### Agent Core 定义

Agent Core 不是 LLM，也不是 API 端点。它是**一个调度器（Loop + Dispatcher）**，运行在 FastAPI 进程中，负责：

```
LLM 输出
   │
Agent Core 拦截
   ├── 是普通文本 → 透传给用户
   ├── 是工具调用意图 → 解析 → 调度 → 执行 → 结果回注 → 继续 LLM
   ├── 是 memory 操作意图 → 读/写 memory 存储
   ├── 是 skill 操作意图 → 加载/更新/创建 skill
   └── 是「缺工具」信号 → 进入造工具循环
```

**核心设计原则：LLM 只负责"想"和"说"，Agent Core 负责"做"和"记"。**

### 和 v0.4 架构关系

```
v0.4                             v0.5
────                             ────
场景分析 → Qwen                  ──→ Agent Core → LLM（Qwen 或 cloud）
Action Map 生成 → Hermes 子进程    ──→ Agent Core → LLM（含 tool calling）
Action Map 执行 → Hermes 子进程    ──→ Agent Core（直接调 Python 函数）
工具生成 → Hermes 子进程            ──→ Agent Core → Tool Maker 调度器
                                   ──→ + Memory/Skill 全由 Agent Core 管理
```

Thinking Map 和 Action Map 保持不动——它们是用户的**可视层**。Agent Core 是背后的**执行层**。

### Agent Core 生命周期

```
启动 → 加载 registry（工具 + skill + memory）
   │
   ▼
等待任务（来自场景聊天 / Action Map 执行 / 用户主动指令）
   │
   ▼
构造 Context（历史 + 工具列表 + 相关 skill + memory 快照）
   │
   ▼
调用 LLM（Qwen 或 cloud 模型，根据路由）
   │
   ▼
解析 LLM 输出 → Agent Core 判断类型
   │
   ├─→ 回复文本 → 透传
   ├─→ 工具调用 → 执行 → 结果回注 → 继续 LLM
   ├─→ memory 操作 → 读写 → 继续 LLM
   ├─→ skill 操作 → 更新 → 继续 LLM
   └─→ 缺工具信号 → 进入 Tool Maker 循环
   │
   ▼
本轮完成 → 写入 memory（学到的东西）→ 等待下一轮
```

---

## 二、工具系统 —— 让 LLM 知道它能用啥

### 工具注册表

`tools/registry.json` 作为所有工具的统一入口。每个工具注册项：

```json
{
  "name": "get_weather",
  "description": "获取城市实时天气及未来预报",
  "file": "tools/weather.py",
  "function": "get_weather",
  "parameters": {
    "city": {"type": "string", "description": "城市名，如'北京'"},
    "forecast_days": {"type": "integer", "description": "预报天数(1-7)", "optional": true}
  },
  "returns": "天气数据（温度、湿度、风力、天气描述）",
  "category": "data",
  "created_at": "2026-05-16T12:00:00Z",
  "verified": true
}
```

| 字段 | 说明 |
|------|------|
| `category` | `data`(数据查询) / `action`(执行操作) / `search`(搜索) / `system`(系统) |
| `verified` | 是否经过至少 2 轮不同场景验证为通用工具 |

### 基础工具（永远注入）

以下工具是 Agent Core 的"本能"，任何时候 LLM 都知道它们存在：

| 工具 | 能力 | 说明 |
|------|------|------|
| `web_search(query)` | 互联网搜索 | 搜索并返回摘要结果 |
| `web_fetch(url)` | 抓取网页内容 | 获取指定 URL 的文本内容 |
| `terminal(command)` | 执行终端命令 | 在沙箱中运行 shell 命令 |
| `read_file(path)` | 读文件 | 读取指定文件内容 |
| `write_file(path, content)` | 写文件 | 写入或覆盖文件 |
| `patch(path, old, new)` | 编辑文件 | 精确替换文本 |
| `search_files(pattern, path)` | 搜索文件 | grep 或文件名匹配 |
| `get_current_time()` | 获取当前时间 | 返回日期和时间 |

基础工具不需要 LLM 学习——每次 Context 构造自动注入。

### 任务工具（按需加载）

根据用户当前任务的复杂度路由：

- **light**: 不注入额外工具，仅基础工具
- **medium/heavy**: 从 registry 中匹配相关工具注入（语义匹配，不是标签匹配）

匹配逻辑：

```python
def match_tools(task_description: str, registry: list) -> list:
    """
    将任务描述与工具 description 做语义匹配。
    返回匹配度 > 阈值的工具列表。
    """
    # 实现思路：embedding 匹配 / 关键词匹配 / LLM 分类
    # v0.5 先走简单策略：LLM 一次判断需要哪些工具
```

### 工具调用协议

LLM 在回复中嵌入结构化工具调用标记，Agent Core 拦截执行：

```
用户: 天津天气怎么样？
   │
LLM 输出:
   我需要查一下天津天气。
   【工具调用】
   {
     "tool": "get_weather",
     "params": {"city": "天津", "forecast_days": 3}
   }
   【/工具调用】
   │
Agent Core 拦截 → 调 weather.get_weather("天津", 3) → 拿结果
   │
   ▼
结果注入回 LLM context:
   【工具结果】
   {"city": "天津", "temp": "22°C", "desc": "晴", ...}
   【/工具结果】
   请基于以上数据回复用户。
   │
   ▼
LLM 输出最终回复（基于真实天气数据）
```

**为什么不直接用 OpenAI-style function calling？**

function calling 是一个具体实现协议。我们的 Agent Core 可以：
1. 初期用自定义标记（`【工具调用】...【/工具调用】`）—— 最快，不依赖模型
2. 后期兼容 OpenAI 的 `tools` 参数格式 —— 与云端模型对接时自然支持
3. 而且 Qwen3.5-9B 的 llama.cpp 端口已经支持 OpenAI 兼容的 `tools` 参数

实现路径：先走自定义标记跑通循环，再升级到原生 function calling。

---

## 三、工具调用循环

一个工具从"LLM 决定用"到"结果回到 LLM"的完整路径：

```
LLM 输出含【工具调用】
   │
Agent Core 拦截
   │
   ├─→ 1. 解析工具名 + 参数
   │
   ├─→ 2. 校验：工具是否在 registry 中，参数是否合法
   │       └─→ 不合法 → 回 LLM：「参数错误，请修正」
   │
   ├─→ 3. 沙箱决策：是否需要隔离执行？
   │       └─→ 普通数据查询 → 当前进程直接执行
   │       └─→ 危险操作（rm, 改系统文件）→ 申请用户确认
   │
   ├─→ 4. 执行工具函数（Python 直接调用）
   │       └─→ 成功 → 格式化结果
   │       └─→ 失败（超时/网络错误）→ 重试 1 次
   │           └─→ 仍失败 → 回 LLM：「工具执行失败，原因: xxx」
   │
   ├─→ 5. 结果注入回 LLM context
   │
   └─→ 6. LLM 基于结果继续输出
```

### 错误处理链

```
工具执行失败
   │
   ├─→ 网络问题 → 重试 1 次 → 再失败 → 告诉 LLM「暂时不可用」
   ├─→ 参数问题 → 回 LLM「参数不对，这是正确的参数格式: ...」
   ├─→ 工具未找到 → 进入 Tool Maker（见下一节）
   └─→ 超时(>30s) → 杀死 → 告诉 LLM「执行超时」
```

---

## 四、工具发现层 —— 先搜再用，不重复造轮子

### 核心理念

> **不是所有轮子都要自己造。在"造"之前，先看看外面有没有。**

LLM 发出【缺工具】信号后，Agent Core 不是立刻进入 Tool Maker，而是先经过**工具发现层**——按成本从低到高搜索工具来源：

```
【缺工具】信号
   │
   ▼
[工具发现层] ← v0.5 新增
   │
   ├── 1. 本地 registry（零成本）→ 有？直接用！
   ├── 2. 本地 skill 依赖索引（零成本）→ 有？加载配套工具！
   ├── 3. GitHub 搜索（搜索成本）→ 有开源项目？提示安装！
   ├── 4. AI 平台工具市场（搜索成本）→ 有现成 API？注册即可！
   └── 5. 互联网搜索（搜索成本）→ 有免费/付费 API？
       │
       └── 以上都找不到 → 进入 Tool Maker 自己造
```

### 工具来源分级

| 优先级 | 来源 | 成本 | 延迟 | 说明 |
|--------|------|------|------|------|
| P0 | **本地 registry** | 零 | <10ms | `tools/registry.json`，自己已有的工具 |
| P0 | **Skill 依赖索引** | 零 | <10ms | 已有 skill 可能已包含所需工具 |
| P1 | **GitHub** | 搜索 | 1-5s | 搜开源项目，找到后自动下载/提示安装 |
| P2 | **AI 平台市场** | 搜索 | 1-5s | Hugging Face Spaces / 各平台工具市场 |
| P3 | **互联网** | 搜索 | 2-10s | 搜免费 API、SaaS 服务 |
| P4 | **Tool Maker 自造** | 生成 | 10-30s | 最后的兜底方案 |

### 各来源实现

#### P0: 本地 registry（已有）

现有 `tools/registry.json`，通过语义匹配工具 description 到任务需求。

扩展 registry 条目，增加 `external_sources` 字段记录工具的外部来源：

```json
{
  "name": "query_weather",
  "description": "获取城市实时天气",
  "source": {
    "type": "local",
    "file": "tools/weather.py"
  }
}
```

#### P0: Skill 依赖索引（新增）

Skill 注册表里记录每个 skill 依赖哪些工具。当 LLM 需要某个能力时，先查 skill 依赖索引：

```json
{
  "skill": "travel_planning",
  "tools_used": ["get_weather", "query_scenic_spots", "trip_budget_calculator"],
  "capabilities": ["天气查询", "景点推荐", "预算计算", "行程编排"]
}
```

如果 LLM 需要"天气查询"能力，而本地 registry 里没有独立 `get_weather` 工具，但 `travel_planning` skill 依赖了它，则**自动加载该 skill 并提取所需工具**。

#### P1: GitHub 搜索

```python
def search_github(capability: str) -> list[dict]:
    """
    在 GitHub 搜索与能力匹配的开源项目。
    返回可能的工具/库列表。
    """
    # 搜索策略：
    # 1. 用 capability 关键词搜索 GitHub repos
    # 2. 筛选 Python 项目、有 API 接口的
    # 3. 返回 {name, url, description, stars, install_command}
    pass
```

匹配到后，Agent Core **不自动安装**——先告知用户，由用户决定：

> 「发现 GitHub 上有 `accident-history-api` 开源项目（⭐ 230），
> 可以查询车辆事故记录。要安装使用吗？」

#### P2: AI 平台工具市场

预留接口，随 AI 平台生态发展接入：

| 平台 | 状态 | 说明 |
|------|------|------|
| Hugging Face Spaces | 🔲 预留 | 可搜索 Spaces 应用作为工具 |
| Dify 工具市场 | 🔲 预留 | Dify 生态的工具插件 |
| LangChain 工具集 | 🔲 预留 | 大量现成工具封装 |
| 其他 | 🔲 预留 | 随行业发展接入 |

#### P3: 互联网搜索

```python
def search_web_for_api(capability: str) -> list[dict]:
    """
    通过互联网搜索可用的 API 服务。
    返回 {name, url, type(免费/付费), auth_required}
    """
    # 搜索 "车辆事故查询 API" "accident history API" 等
    pass
```

#### P4: Tool Maker 自造

见下一章。前面所有来源都找不到时，才进入自造流程。

### 外部来源索引（定期更新）

外部搜索不能每次都实时查——太慢。建立索引层：

```
定时任务（cronjob）:
  ├── 每周: 更新 GitHub 热门工具索引
  ├── 每周: 更新 AI 平台市场索引
  └── 每日: 更新 registry 内的工具健康状态（API 是否可用）

索引存储:
  tools/external_index.json
  └── 在内存中缓存，运行时快速检索
```

```json
{
  "github_index": {
    "last_updated": "2026-05-17T10:00:00Z",
    "tools": [
      {
        "capability": "车辆事故查询",
        "repo": "user/accident-history-api",
        "stars": 230,
        "description": "基于车架号查询事故记录",
        "install": "pip install accident-history-api"
      }
    ]
  },
  "api_index": {
    "last_updated": "2026-05-17T10:00:00Z",
    "apis": [
      {
        "capability": "车辆事故查询",
        "name": "车300 API",
        "url": "https://api.che300.com/...",
        "type": "付费",
        "auth_required": true
      }
    ]
  }
}
```

### 错误处理

```
所有外部来源都搜索失败
   │
   ├─→ 告知用户：「没找到现成的工具/API，要不要我帮你写一个？」
   │
   └─→ 用户同意 → 进入 Tool Maker
       └─→ 用户拒绝 → 告诉 LLM 「这个能力暂时不可用」
```

### 和 LLM 的交互

工具发现层对 LLM 透明——LLM 发出【缺工具】信号后，Agent Core 在后台完成搜索和自造，LLM 只收到最终结果：

```
LLM 发出【缺工具】→ 造天气工具
   ↓
Agent Core 后台：
  ① 查本地 registry → 没有
  ② 查 skill 依赖 → travel_planning 有天气能力 → 加载配套工具
  ③ 发现已有一个 get_weather → 通知 LLM 直接使用

LLM 收到：「get_weather 工具已在 registry 中，可直接调用」
```

---



## 五、工具缺失 → 自动造工具闭环

### 核心命题

> LLM 发现工具列表里没有能做这件事的工具后，接下来做什么？

这是坐山客和普通聊天工具的分水岭。Ans: **LLM 发出"缺工具"信号，Agent Core 进入 Tool Maker 流程。**

### 信号格式

LLM 在回复中标记工具缺失：

```
用户: 查一下这辆二手宝马X5有没有事故记录
   │
LLM 检查工具列表：没有事故查询工具
   │
   ▼
LLM 输出:
   【缺工具】
   {
     "capability": "查询车辆事故历史",
     "description": "根据 VIN 码或车牌号查询车辆事故维修记录、保险出险历史",
     "suggested_name": "query_accident_history",
     "parameters": {
       "vin": "VIN 码",
       "plate": "车牌号（可选）"
     },
     "expected_output": "事故次数、维修记录、定损金额等"
   }
   【/缺工具】
```

### Tool Maker 调度流程

```
Agent Core 收到【缺工具】信号
   │
   ▼
Tool Maker:
   │
   ├── 1. 把"造工具需求"发给 LLM（用更强的模型，如 deepseek-v4-flash）
   │       prompt = "写一个 Python 函数，功能: {capability}，
   │                 参数: {parameters}，输出: {expected_output}
   │                 要求：requests 库，异常处理完善，中文输出"
   │
   ├── 2. LLM 返回工具代码
   │
   ├── 3. 语法校验 + 沙箱测试（调一次试运行）
   │       └─→ 失败 → 回 LLM 修 → 最多 3 轮
   │
   ├── 4. 同名工具查 registry →
   │       ├─→ 有 → 参数对比 →
   │       │       ├─→ 兼容 → 直接复用
   │       │       └─→ 不兼容 → 改名 {name}_v2
   │       └─→ 无 → 新建
   │
   ├── 5. 写入 tools/{name}.py
   │
   ├── 6. 注册到 tools/registry.json
   │
   ├── 7. 标记 verified=false（尚未验证通用性）
   │
   └── 8. 告诉 LLM：「工具已创建，重新执行」
           └─→ LLM 调刚创建的工具 → 拿到结果 → 回复
```

### 涌现工具质量护栏

| 规范 | 强制 | 说明 |
|------|------|------|
| 通用参数化 | ✅ 硬性 | 不准硬编码地名/价格等 |
| 单一职责 | ✅ 硬性 | 一个文件只做一类事 |
| 命名规范 | ✅ 硬性 | 描述能力名：`query_accident_history` 而非 `bmw_x5_check` |
| 异常处理 | ✅ 硬性 | try/except + 网络超时 + 空数据 |
| 无外部依赖 | ✅ 硬性 | 仅 Python 标准库 + requests |
| SKILL.md 生成 | ❌ 非必需 | 仅 verified=true 后才生成 |

### 从"造出来"到"真能用"

```
首次创建 → verified=false → 本次任务能用，但不推荐给其他任务
   │
   ▼
第二次在不同场景被匹配到 → 任务成功 → verified=true
   │
   ▼
生成 SKILL.md → 工具正式入库
```

---

## 六、Memory 系统

### 什么是 Memory

坐山客的 Memory 不是 LLM 的上下文窗口。它是**结构化持久存储**，让 LLM 在跨轮对话和跨会话中记住：

| 类型 | 示例 | 生命周期 |
|------|------|---------|
| **用户事实** | 「用户叫张清泉」/「用户喜欢天津菜」 | 永久 |
| **会话上下文** | 「用户正在看二手车，关注 5 万以下」 | 场景内 |
| **系统经验** | 「腾讯地图 API 的 key 在 .env 里配」 | 永久 |
| **工具使用记录** | 「weather 工具上次查询天津花了 2s」 | 用于优化 |

### Memory CRUD

LLM 可以在回复中用标记操作 memory：

```
【memory write】
{"type": "user_fact", "key": "user_name", "value": "张清泉"}
【/memory write】

【memory read】user_name【/memory read】
→ Agent Core 返回: "张清泉"

【memory search】用户喜欢的菜系【/memory search】
→ Agent Core 返回: "天津菜、鲁菜"
```

### Memory 存储实现

v0.5 先用 SQLite（项目已有），足以支撑：

```sql
CREATE TABLE agent_memory (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,        -- 'user_fact' | 'session' | 'system' | 'tool_stats'
    key TEXT NOT NULL,
    value TEXT NOT NULL,            -- JSON 序列化
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ttl INTEGER DEFAULT NULL       -- NULL=永久，秒数=自动过期（会话级）
);

CREATE INDEX idx_memory_namespace ON agent_memory(namespace);
CREATE UNIQUE INDEX idx_memory_key ON agent_memory(namespace, key);
```

### Memory 注入 Context 策略

不是所有 memory 都塞给 LLM——按场景筛选：

```
构建 context 时：
  1. 当前场景的所有 session memory（最近 20 条）
  2. 所有 user_fact（用户永久偏好）
  3. 匹配当前任务的 system experience（语义匹配）
  4. 总长度限制：不超过 context 的 30%
```

---

## 七、Skill 系统

### 什么是 Skill

Skill 是**可复用的任务执行流程**。区别于工具（一个函数），Skill 是"怎么做一件事"的完整知识。

```
工具: get_weather(city) → 返回天气数据
Skill: "帮用户规划旅行" → 包含：查天气、查景点、算预算、排日程的完整流程
```

### Skill 存储

现有的 `tools/{name}/SKILL.md` 结构不变，Agent Core 增加 skill 注册表：

```json
{
  "name": "travel_planning",
  "description": "帮用户规划旅行，包含天气查询、景点推荐、预算计算、日程编排",
  "tools_used": ["get_weather", "query_scenic_spots", "trip_budget_calculator"],
  "prompt_template": "用户想要去{city}旅行{days}天...",
  "path": "tools/travel_planning/SKILL.md",
  "created_at": "...",
  "usage_count": 3
}
```

### Skill 的加载与更新

```
用户: 帮我规划天津3日游
   │
Agent Core:
   ├── 1. 搜索 skill 匹配（语义匹配 "旅行规划" → travel_planning）
   ├── 2. 加载匹配的 skill prompt → 注入 context
   ├── 3. 加载 skill 依赖的工具列表 → 注入 tool registry
   │
   ▼
LLM 收到的 context 包含：
  - 基础工具（web_search, terminal...）
  - travel_planning 依赖的工具（get_weather, query_scenic_spots...）
  - travel_planning 的执行流程提示
```

### Skill 学习（自动提炼）

执行完成后，Agent Core 判断是否值得提炼为新 skill：

```python
def should_extract_skill(execution_log):
    """
    判断是否从本次执行中提炼 skill
    条件：
    1. 涉及 ≥3 个工具调用
    2. 工具调用序列有重复模式（非一次性任务）
    3. 结果质量好（用户没有纠正性反馈）
    """
    if meets_criteria:
        extract_skill(execution_log)
```

提炼后的 skill 存入注册表，并在类似任务被匹配到时自动加载。

---

## 八、Context 构造 —— 给 LLM 的"世界视图"

### Context 组成

每次调用 LLM 前，Agent Core 构造 context：

```
┌─────────────────────────────────────────────┐
│ SYSTEM PROMPT (角色定义)                     │
│  "你是坐山客，一个有自我认知的 AI 智能体..."  │
├─────────────────────────────────────────────┤
│ MEMORY 快照                                  │
│  - 用户已知事实                              │
│  - 当前场景上下文                            │
│  - 相关系统经验                              │
├─────────────────────────────────────────────┤
│ SKILL 提示（如匹配到）                       │
│  - travel_planning 执行流程                  │
├─────────────────────────────────────────────┤
│ 工具列表（含 description + parameters）      │
│  - 基础工具（永远在）                        │
│  - 任务匹配工具（按需加载）                  │
├─────────────────────────────────────────────┤
│ 对话历史（最近 N 条）                        │
├─────────────────────────────────────────────┤
│ 当前用户消息                                 │
└─────────────────────────────────────────────┘
```

### 工具列表在 Prompt 中的格式

```markdown
## 可用工具

你可以通过【工具调用】标记使用以下工具。格式：
【工具调用】
{"tool": "工具名", "params": {...}}
【/工具调用】

### 基础工具（始终可用）
- `web_search(query)` — 互联网搜索
- `terminal(command)` — 执行终端命令
- `read_file(path)` — 读取文件
- `write_file(path, content)` — 写入文件
- `patch(path, old, new)` — 编辑文件
- `search_files(pattern, path)` — 搜索文件内容/文件名
- `web_fetch(url)` — 抓取网页内容
- `get_current_time()` — 获取当前日期时间

### 任务相关工具
- `get_weather(city)` — 获取城市实时天气

### 如果工具列表里没有你要的
用【缺工具】标记告诉系统你需要什么工具，系统会帮你创建。
```

### Context 长度管理

Qwen3.5-9B context 长度 16384 token，要精打细算：

| 组件 | 预算 | 说明 |
|------|------|------|
| System prompt | ~500 | 角色 + 工具协议 |
| Memory 快照 | ~2000 | 筛选最相关的 |
| Skill 提示 | ~1000 | 如果匹配到 |
| 工具列表 | ~2000 | 基础 + 匹配的 |
| 对话历史 | ~6000 | 最近 10-20 条 |
| 当前消息 + 中间结果 | ~4000 | 含工具结果回注 |
| 预留 | ~1000 | 安全边际 |

---

## 九、沙箱隔离与并行

### 为什么需要沙箱

1. **安全** — LLM 写的工具可能有 bug，不能让它动系统文件
2. **并行** — 多个任务同时执行互不干扰
3. **回滚** — 沙箱内搞坏了，扔掉重建

### 沙箱策略

| 场景 | 沙箱级别 | 说明 |
|------|---------|------|
| 普通工具调用 | 无沙箱，当前进程 | get_weather, web_search 等数据查询 |
| 文件操作 | 限制路径 | 只能读写 tools/ 目录 |
| 终端命令 | 子进程隔离 | `subprocess.Popen(cwd="tools/")` |
| 并行执行 | 独立进程 | 每个任务一个 Python 子进程 |

### 并行执行

```
用户场景分析（串行） ← 保持现有，用户一次只做一件事
   │
   ▼
Action Map 执行 → 可以并行执行叶子节点
   │
   ├── leaf A: 查天气 → 独立进程，2s
   ├── leaf B: 查景点 → 独立进程，3s
   ├── leaf C: 算预算 → 独立进程，1s
   └── 全部完成 → 汇总
```

并行控制参数：

```json
{
  "max_parallel": 3,
  "max_processes": 5,
  "timeout_per_node": 120,
  "memory_limit_mb": 512
}
```

---

## 十、全局架构流程

```
用户浏览器 (localhost:5173)
   │
   ▼
FastAPI (localhost:8000)
   │
   ├── 对话路由（场景/频道/流式）
   │
   ├── Thinking Map & Action Map CRUD（保持不变）
   │
   └── ▶ Agent Core ◀ ──── v0.5 新增核心
         │
         ├── Context 构造器
         │   ├── 加载 memory
         │   ├── 匹配 skill
         │   ├── 加载工具注册表
         │   └── 组装 prompt
         │
         ├── LLM 调度器
         │   ├── 本地 Qwen3.5-9B (llama-server :8083)
         │   ├── deepseek-v4-flash (cloud)
         │   └── deepseek-v4-pro (cloud)
         │
         ├── 工具调度器
         │   ├── 解析【工具调用】
         │   ├── 执行 Python 函数
         │   └── 结果回注
         │
         ├── Tool Maker
         │   ├── 检测【缺工具】信号
         │   ├── 生成工具代码
         │   └── 注册 + 沙箱测试
         │
         ├── Memory 管理器
         │   └── CRUD + 过期 + 筛选注入
         │
         └── Skill 管理器
             ├── 注册表 CRUD
             └── 自动提炼
```

### 和前端的关系

Agent Core 是纯后端组件，前端不受影响：

```
前端看到:
  - 聊天消息（流式/非流式）
  - Thinking Map 更新（如有）
  - Action Map 状态变化

前端不感知:
  - 工具调用过程
  - Memory 读写
  - Skill 加载/提炼
  - 工具创建

前端感知工具调用的方式:
  - 聊天消息中出现「[🔧 正在查天气...]」「[🔧 搜索结果: 3 条]」等状态提示
  - 这些提示由 Agent Core 作为特殊 token 注入流式输出
```

---

## 十一、数据结构变更总览

### 新增

| 项目 | 说明 |
|------|------|
| `agent_tool_registry` | 注册表（现有 tools/registry.json 标准化） |
| `agent_memory` 表 | SQLite 持久化 memory |
| `agent_skills` 表 | Skill 注册表（现有 SKILL.md 的索引） |
| `Agent Core` 调度器 | 核心循环（Python 模块，`agent_core/`） |
| `Tool Discovery` 模块 | 工具发现层（外部来源搜索） |
| `Tool Maker` 模块 | 工具自动生成 |
| `external_index.json` | 外部工具索引（定期更新） |
| 沙箱管理器 | 进程隔离和并行控制 |

### 修改

| 项目 | v0.4 | v0.5 |
|------|------|------|
| 场景 chat 执行 | Qwen 直接输出 | → Agent Core → LLM + 工具循环 |
| Action Map 执行 | Hermes 子进程 | → Agent Core 直接调度 |
| 工具生成 | Hermes 子进程 | → Tool Maker 模块 |
| 工具列表 | 没有任何注入 | → 始终注入基础工具 + 按需加载 |
| LLM context | 仅有 system prompt + 历史 | → 含工具列表、memory、skill |

### 不变

| 项目 | 原因 |
|------|------|
| Thinking Map 数据结构 | 用户可视层不变 |
| Action Map 数据结构 | 节点/边/状态机不变 |
| SSE 流式聊天 | 前端交互不变 |
| 三路路由 (light/medium/heavy) | 复杂度分层不变，但 light 也走 Agent Core |
| 约束提取 + 校验 | 仍在入口执行 |
| tools/ 目录结构 | 现有工具文件不动 |

---

## 十二、从 v0.4 到 v0.5 的迁移路径

### 阶段一：Agent Core 最小闭环（当前重点）

目标：跑通"LLM → 【工具调用】→ Core 执行 → 结果回注"这个最小循环。

```
1. 建 agent_core/ 模块
2. 实现【工具调用】解析器
3. 基础工具注入（先只 web_search + get_weather）
4. 在 light 场景 chat 中接入 Agent Core
5. 验证：问天气 → 自动调 get_weather → 基于真实数据回复
```

### 阶段二：Tool Discovery

```
1. 实现工具发现层
2. GitHub 搜索 + 互联网搜索
3. Skill 依赖索引
4. 外部索引定时更新
5. 验证：问 registry 没有的问题 → 先去搜 → 搜不到再提示用户
```

### 阶段三：Tool Maker

```
1. 【缺工具】信号解析
2. LLM 生成工具代码 → 写入沙箱
3. 注册 registry
4. 验证：搜也搜不到 → 自动造工具
```

### 阶段四：Memory + Skill

```
1. agent_memory 表 + CRUD
2. Memory 注入 context
3. Skill 注册表 + 自动提炼
4. 并行沙箱
```

### 阶段五：替换 Hermes 子进程

```
1. Action Map 执行从 Hermes 子进程切到 Agent Core
2. Action Map 生成从 Hermes 子进程切到 Agent Core
3. 工具生成从 Hermes 子进程切到 Tool Maker
4. 删除 Hermes 子进程相关代码
```
