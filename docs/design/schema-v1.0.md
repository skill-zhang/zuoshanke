# Schema v1.0 — Context Composition Architecture

> **里程碑说明：** Schema v1.0 是对 Context 管理的彻底重构。从"全文注入"模式升级为"分层精炼"模式，每一层独立控制加载策略、优先级权重、token 预算。这是坐山客从 v0.x 系列（原型验证阶段）进入 v1.0（生产级架构）的标志性设计。
>
> 设计日期：2026-05-21
> 核心贡献者：张清泉（需求设计）、坐山客（架构设计）

---

## 目录

1. [问题陈述](#1-问题陈述)
2. [核心指标](#2-核心指标)
3. [架构总览](#3-架构总览)
4. [七层定义](#4-七层定义)
5. [两层滑动窗口](#5-两层滑动窗口)
6. [权重优先级系统](#6-权重优先级系统)
7. [Diff 独立提取机制](#7-diff-独立提取机制)
8. [Memory Extraction Layer](#48-memory-extraction-layer-新增)
9. [配置与技能的分离](#8-配置与技能的分离)
10. [场景文档声明机制](#9-场景文档声明机制)
11. [Scene Config 参数扩展](#10-scene-config-参数扩展)
12. [后端实现策略](#11-后端实现策略)
13. [与 Schema v0.81 的兼容与迁移](#12-与-schema-v081-的兼容与迁移)

---

## 1. 问题陈述

### 1.1 LLM 的先天缺陷

LLM 是纯粹的无状态函数：`LLM(prompt) -> output`。每一轮调用都是"全新开始"——

- 它不知道用户是谁 → 需要 **Memory**
- 它不知道刚才说了什么 → 需要 **Context/History**
- 它不知道怎么干活 → 需要 **Skill/Prompt Engineering**

这三个补偿方式的核心手段都是**把信息塞进 prompt**。而 prompt 是 transformer 架构的接口瓶颈。

### 1.2 暴力注入的三个问题

**问题 A：上下文线性增长，世界平方级增长**

每轮对话 + 每步工具输出，全部 append 进历史。编码任务 5 轮下来，context 轻松破 50K token。

**问题 B：注意力在长上下文中被稀释**

positional encoding 在 32K+ 窗口下，"开头和结尾最强，中间是黑洞"。多轮对话中段的关键决策会被压扁。

**问题 C：工具输出无差别注入**

`search_files` 的 50 行匹配结果、`terminal` 的 500 行编译日志——只有其中 2 行有用，但 500 行全进了 context。

### 1.3 基于真实数据的诊断

实测一组任务后：

| 指标 | 数值 |
|---|---|
| 输入命中 token (cache hit) | 457,634,048 |
| 输入未命中 token (cache miss) | 23,954,484 |
| 输出 token | 1,645,200 |
| cache hit rate | ~95% |
| miss-to-output ratio | **14.7:1** |

**解读：**
- 95% cache hit 说明 system prompt、skill、memory 这些不变部分效率良好
- 但每一轮输出 1 个 token，平均需要带 15 个"新"的上下文 token
- 输出仅占总消耗的 3.4%——96% 的 token 花在"记住刚才说了什么"上
- 24M miss token 几乎全是增长的对话历史 + 工具输出，每轮都是新的，cache 无法命中

**结论：暴力注入方案已到边际效益递减拐点，必须从源头控制膨胀。**

---

## 2. 核心指标

| 指标 | 当前 (v0.x) | 目标 (v1.0) |
|---|---|---|
| 纯沟通 session 平均 context | — | < 30K token |
| 编码 session 平均 context | 100K+ token | < 50K token |
| miss-to-output ratio | 14.7:1 | < 5:1 |
| 聊天历史保留 | 滑动窗口 N 轮 | 全部保留，按权重组织 |
| 工具输出保留 | 全部 | 最近 N 轮关键帧 |
| Diff 提取 | 无 | 自动独立提取 |

---

## 3. 架构总览

### 3.1 核心范式：分层组合

每一轮 context 不再是一锅炖，而是由 **Composer** 按规则组装：

```
Composer(user_input, scene, fenshen, session)
  │
  ├── prompt_layer()        ─── 本体 prompt + 分身 prompt
  ├── memory_layer()        ─── 场景相关的持久记忆（DB 检索）
  ├── document_layer()      ─── 场景声明的文档摘要（DB 检索）
  ├── config_layer()        ─── 当前生效的配置层叠
  ├── skill_layer()         ─── 按相关性检索的 skill 摘要
  ├── history_layer()       ─── 当前 session 全部聊天（带权重）
  └── work_output_layer()   ─── 最近 N 轮工具调用的关键帧 + diff
       │
       └── → 组合为最终 prompt → 送入 LLM
```

每一层独立控制：
- `enabled: bool` — 是否加载
- `mode: "full"|"summary"|"none"` — 加载级别
- `max_tokens: int` — 最大 token 预算

### 3.2 数据流

```
用户输入
  │
  ▼
┌────────────────────────────────────┐
│        Context Composer            │
│                                    │
│  ┌──────┐ ┌──────┐ ┌───────────┐  │
│  │prompt│ │memory│ │document   │  │
│  │layer │ │layer │ │layer      │  │
│  └──┬───┘ └──┬───┘ └─────┬─────┘  │
│     │        │           │        │
│  ┌──▼───┐ ┌──▼───┐ ┌────▼────┐  │
│  │config│ │skill │ │history  │  │
│  │layer │ │layer │ │layer    │  │
│  └──┬───┘ └──┬───┘ └────┬─────┘  │
│     │        │           │        │
│  ┌──▼────────▼───────────▼─────┐  │
│  │    work_output_layer        │  │
│  │  (滑动窗口 + diff 提取)     │  │
│  └──────────────┬──────────────┘  │
└─────────────────│────────────────┘
                  │
                  ▼
           Assembled Prompt
                  │
                  ▼
               LLM
                  │
                  ▼
            LLM Output
                  │
                  ▼
    ┌──────────────────────────┐
    │ Processors               │
    │                          │
    │  • diff_extractor()      │
    │  • summary_extractor()   │
    │  • skill_suggester()     │
    │  • history_saver()       │
    └──────────────────────────┘
                  │
                  ▼
              DB / Context Store
```

---

## 4. 七层定义

### 4.1 Prompt Layer

**内容：** 本体 system prompt + 分身自定义 prompt

**规则：**
- 不可压缩（全文加载，token 预算最高优先级）
- 由 scene_name + fenshen_type 决定拉取哪份
- 分身 prompt 覆盖/扩展本体 prompt

**token 预算：** 无上限约束（通常 2-5K）

---

### 4.2 Memory Layer

**内容：** 持久化的记忆条目（用户偏好、环境事实、约定）

**规则：**
- 按场景 scope 检索（不是全量 memory 注入）
- 默认 `max_tokens: 2000`
- 模式：默认 `summary`（取 Top K 最相关），可切换 `full`

**核心改变：** 从"全量注入"变为"按场景检索"。闲聊场景不注入 coding 相关的记忆。

---

### 4.3 Document Layer 【新增】

**内容：** 场景声明依赖的知识文档的摘要

**规则：**
- 每个 scene 声明 `depends_documents: []`
- 文档存储在知识库（DB 或文件），摘要预生成
- 三级摘要：
  - `single_line` (50 chars) — 最低成本
  - `brief` (500 chars) — 默认
  - `full` (5000 chars) — 需要时才加载
- 默认模式 `brief`

**示例：**

```yaml
scene "code_review":
  depends_documents:
    - doc: "schema-v0.81.md"
      level: "brief"
    - doc: "converge-and-project.md"
      level: "single_line"
```

---

### 4.4 Config Layer 【新增，从 Skill 分离】

**内容：** 当前生效的运行配置

**规则：**
- 配置层叠：本体配置 → 分身配置 → scene 配置 → session 临时覆写
- 只注入**当前生效的层叠结果**，不是完整 yaml
- 仅输出差分：如果分身只改了 prompt，只写 prompt 的不同
- 由 `config_injector` 统一管理，不从 skill 目录读取

**配置分类：**

| 类别 | 例子 | 注入时机 |
|---|---|---|
| 系统配置 | 数据库路径、API endpoint | 启动时注入一次 |
| 模型配置 | provider、model、temperature | 每轮注入 |
| 服务配置 | llama 启动参数、ComfyUI 地址 | 相关场景触发时注入 |
| Skill 配置 | 干活工作流、排坑指南 | 按相关性检索 |

---

### 4.5 Skill Layer

**内容：** 干活用的工作流知识、排坑指南、代码示例

**规则：**
- 按语义相关性检索 Top K 个 skill
- 每个 skill 注入摘要 + （可选）关键代码段
- 默认 `max_tokens: 2000`

**核心改变：** Skill 不再混入配置类条目。配置文件有独立 store。

---

### 4.6 History Layer

**内容：** 当前 session 的完整聊天记录

**规则：**
- 保留当前 session 会话有效期内的全部聊天内容，不做截断处理
- 每条消息标记权重：`high` / `normal` / `low`
- 输出按权重排序组装
- token 预算：按 scene 配置（纯聊天场景可给更多，编码场景可压缩）

**权重分配方式：**
- 用户核心指示、重要结论 → `high`
- 常规对话、确认信息 → `normal`
- 废话、试探性内容、发散过程 → `low`

**实现方式：** 后端每轮对话存储时附带 `priority` 字段，或由 LLM 在回复时自标记。

---

### 4.7 Work Output Layer 【分离独立】

**内容：** 工具调用的产出记录（terminal 输出、文件操作、工具调用结果）

**规则：**
- 与聊天历史独立管理
- 使用**滑动窗口**，默认保留最近 N 轮（N=3，可调参）
- 每轮产出提取**关键帧**：
  - 编码：文件级 diff（新增行、删除行、hunks）
  - 测试：测试用例、测试结果
  - Debug：完整错误信息
  - 其他：摘要
- 关键帧包含**文件路径标注** → 构造引导文本：
  ```
  == 文件: /path/to/file.py ==
  这是最近改动过的代码。如果用户报告了 bug，优先检查此区域：
  - 第 10-13 行: 新增代码
  - 第 8 行: 删除代码
  @@ -8,6 +10,7 @@ ...
  ```
- 非关键帧的工具输出不注入，仅保存到 DB 供检索

---

## 4.8 Memory Extraction Layer 【新增】

**职责：** 将聊天记录（messages）转化为持久记忆（agent_memory）——从 History Layer 到 Memory Layer 的单向沉淀通道

**说明：** 本层不参与每次 context 组装，而是在后台异步运行，产出由 Memory Layer (4.2) 消费。

### 4.8.1 数据流

```
对话进行中
  │
  ├── messages 表写入（每轮对话）
  │     priority: high/normal/low
  │     memory_extracted: false（默认）
  │
  ▼
触发条件
  ├── 页面关闭：visibilitychange → POST /api/scenes/{id}/extract-memory
  └── 兜底：见 schema-v1.1 记忆提取兜底策略
  
  ▼
LLM 提取（只处理 memory_extracted=false 的消息）
  │
  ├── 成功 → save_extracted_memories() 写入 agent_memory（scope=scene, context_id=当前场景）
  │         → 标记所有输入消息为 memory_extracted=true
  │
  └── 失败或无值得提取的内容 → 仍然标记为 memory_extracted=true
                              （防止反复尝试同一批消息）
```

### 4.8.2 触发规则

| 规则 | 说明 |
|------|------|
| 只提一次 | 每条消息的 `memory_extracted` 标记防止重复提取 |
| 批量处理 | 每次取最多 30 条未提取消息送 LLM |
| 最小要求 | 至少 2 条消息（user + ai）才触发 |
| 场景专属 | 只提取当前场景的消息，存入同 scope+context_id |
| 前端触发 | 页面关闭时触发，切场景不触发（避免冗余） |
| 兜底 | 见 schema-v1.1 — session 状态驱动的记忆提取兜底 |

### 4.8.3 去重策略

内容级去重，防止相同信息反复存多条：

- **算法：** Jaccard 相似度（中文单字 + 英文单词 + 数字）
- **阈值：** 0.50（50%）
- **范围：** 同 scope + context_id 内
- **命中：** 不创建新记忆，改为 reinforce 已有记忆（权重 +1）
- **未命中：** 创建新记忆，base_weight=3

### 4.8.4 与各层的关系

| 相关层 | 关系 |
|--------|------|
| History Layer (4.6) | 消费 messages 的未标记记录，提取后标记 memory_extracted=true，消息本身不受影响 |
| Memory Layer (4.2) | 产出写入 agent_memory，是 Memory Layer 的数据来源 |
| Memory Cache | 通过写穿透（on_memory_created）同步至缓存 |
| Schema v1.1 (Session) | 兜底策略依赖 session 状态：不活跃 session + 未提取消息 → 触发提取 |

---

## 5. 两层滑动窗口

核心设计：聊天历史和干活输出使用**两个独立的滑动窗口**。

### 5.1 聊天历史窗口

| 属性 | 值 |
|------|------|
| 窗口范围 | 当前 session 全部聊天内容 |
| 保留策略 | 全部保留，按 priority 排序组装 |
| 权重分布 | high/normal/low 三级 |
| 截断策略 | 不做截断（见 4.6） |
| 参数 | 无 |

### 5.2 干活输出窗口

| 属性 | 值 |
|---|---|
| 窗口范围 | 最近 N 轮工具调用记录 |
| 保留策略 | 仅保留关键帧（diff/用例/错误信息） |
| 默认 N | 3 |
| 可调参 | 是，存于 scene.scene_config |
| 过期策略 | 超出窗口的清除出 context，保留在 DB |

---

## 6. 权重优先级系统

### 6.1 消息权重等级

```
priority_high   → 必须全文加载，高 attention 位置
priority_normal → 全文加载，中等 attention 位置
priority_low    → 可压缩/摘要，置于 context 尾部
```

### 6.2 权重判定规则

| 内容类型 | 默认权重 | 说明 |
|---|---|---|
| 用户明确指示、任务分配 | high | "帮我改X"、"去做Y" |
| 重要的结论、决策 | high | "我们决定用A方案" |
| 核心设计思路 | high | "我的想法是..." → 用户划重点 |
| 常规技术讨论 | normal | 日常对话 |
| 确认信息 | normal | "好的"、"明白了" |
| 发散、开玩笑 | low | 题外话 |
| 工具调用中间输出 | low → 存 DB | 超出干活窗口后降为low |
| 系统通知 | low | 状态更新 |

### 6.3 实现策略

Option A：**后端显式赋值**。每个 chat message 表加 `priority` 字段，后端/LLM 写入时指定。

Option B：**LLM 自标记**。system prompt 要求输出时自标记权重 `[P:high]` `[P:normal]` `[P:low]`。

推荐 Option A + 初始默认 normal，由后续处理逻辑修正。

---

## 7. Diff 独立提取机制

### 7.1 触发条件

每次工具调用后，如果涉及文件修改（write_file、patch、terminal 中执行了 git 操作），自动触发 diff_extractor。

### 7.2 Diff Extractor 接口

```
diff_extractor(
    file_path: str,
    current_content: str,
    previous_snapshot: str
) → {
    "file_path": str,
    "added_lines": [int],      # 行号列表
    "removed_lines": [int],    # 行号列表
    "hunks": [{
        "old_start": int,
        "old_count": int,
        "new_start": int,
        "new_count": int,
        "content": str          # unified diff 格式的行
    }],
    "summary": str             # "新增了 X 行，删除了 Y 行"
}
```

### 7.3 Context 中的 Diff 块格式

每次注入时，diff 块放在 Work Output Layer 的最高 attention 位置：

```
== 文件: /home/administrator/zuoshanke/frontend/src/components/CardView.tsx ==
这是最近改动过的代码。如果用户报告了 bug，优先检查此区域：

【改动摘要】新增 3 行，删除 1 行

【改动详情】
  @@ -45,7 +45,9 @@ export function CardView({ items }) {
   const style = {
     display: 'grid',
  -  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
  +  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  +  gap: '16px',
  +  padding: '12px',
   };

【活跃改动列表】
  • file.py:10-13 — 新增代码
  • file.py:8 — 删除代码
```

### 7.4 文件快照管理

文件快照由 `snapshot_manager` 维护：

- 每个 session 记录每个受控文件的最新快照
- 快照存于 DB（或文件系统 `~/.zuoshanke/snapshots/`）
- 超出窗口的快照可清理，保留最近 5 次版本

---

## 8. 配置与技能的分离

### 8.1 当前问题

现有实现将以下内容混在 skill 目录：

```
skills/
├── llama-inference.md     ← 这是配置，不是 skill
├── deploy-guide.md         ← 这是 skill
├── pydantic-errors.md      ← 这是 skill
├── api-config.yaml         ← 这是配置
```

### 8.2 分离方案

```
context_store/
├── skills/                 # 干活工作流、排坑指南
│   ├── deploy-guide.md
│   └── pydantic-errors.md
│
├── configs/                # 系统配置
│   ├── zuoshanke.yaml      # 坐山根本体配置
│   ├── model.yaml          # 当前模型配置
│   └── llama.yaml          # llama 服务配置
│
├── documents/              # 知识文档
│   ├── schema-v1.0.md
│   └── converge-and-project.md
│
└── index.json              # 全文检索索引
```

### 8.3 Config Store 的注入规则

| 配置项 | 注入时机 | 注入级别 |
|---|---|---|
| `zuoshanke.yaml` | session 启动时一次 | full |
| `model.yaml` | 每轮 | full |
| `llama.yaml` | 仅当场景="llama 编程"时 | full |
| 其他 service config | 仅当相关场景被激活 | brief |

---

## 9. 场景文档声明机制

### 9.1 Scene Config 扩展

每个 scene 在其 `scene_config` 中声明依赖：

```json
{
  "scene_name": "code_review",
  "scene_config": {
    "converge_threshold": 0.7,
    "converge_enabled": true,
    "diverge_min_rounds": 3,
    "work_output_window_size": 3,
    
    "document_deps": [
      {"doc": "schema-v1.0.md", "level": "brief"},
      {"doc": "coding-style.md", "level": "full"}
    ],
    
    "skill_deps": [
      "code-review-checklist",
      "python-common-pitfalls"
    ],
    
    "config_deps": [
      "model.yaml",
      "zuoshanke.yaml"
    ],
    
    "max_context_tokens": 32000,
    "history_weight_default": "normal"
  }
}
```

### 9.2 Document Pre-caching

- 系统启动时预加载所有声明的文档摘要（三级）
- 运行时按 scene 切换动态注入
- 文档更新后自动重新生成摘要

---

## 10. Scene Config 参数扩展

### 10.1 新增参数清单

| 参数名 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `work_output_window_size` | int | 3 | 干活输出滑动窗口轮数 |
| `max_context_tokens` | int | 32000 | 当前场景最大 context token |
| `history_weight_default` | enum | "normal" | 聊天历史默认权重 |
| `document_deps` | array | [] | 依赖的文档声明 |
| `skill_deps` | array | [] | 依赖的 skill 声明 |
| `config_deps` | array | ["model.yaml"] | 依赖的配置声明 |
| `memory_scope` | enum | "scene" | 记忆检索范围 |

### 10.2 参数继承链

```
zuoshanke default
  → scene config (覆盖)
    → fenshen config (覆盖)
      → session override (临时)
```

---

## 11. 后端实现策略

### 11.1 新增模块

| 模块 | 职责 |
|---|---|
| `context_composer.py` | 核心组合器，按规则组装各层 |
| `diff_extractor.py` | 文件 diff 提取和格式化 |
| `snapshot_manager.py` | 文件快照管理 |
| `config_injector.py` | 配置层叠和注入 |
| `document_summarizer.py` | 文档摘要生成（预计算） |
| `priority_assigner.py` | 消息权重分配 |

### 11.2 数据库变更

**可能的表新增：**

```sql
-- 文档摘要缓存
CREATE TABLE document_summaries (
    id INTEGER PRIMARY KEY,
    doc_name TEXT UNIQUE,
    single_line TEXT,
    brief TEXT,
    full TEXT,
    updated_at TIMESTAMP
);

-- 配置存储
CREATE TABLE config_entries (
    id INTEGER PRIMARY KEY,
    config_name TEXT UNIQUE,
    content TEXT,          -- json/yaml
    category TEXT,         -- system/model/service
    updated_at TIMESTAMP
);

-- 文件快照
CREATE TABLE file_snapshots (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    file_path TEXT,
    snapshot TEXT,
    created_at TIMESTAMP
);

-- 消息权重（chat_messages 扩展）
-- 在现有 chat_messages 表加 priority 字段
ALTER TABLE chat_messages ADD COLUMN priority TEXT DEFAULT 'normal';
```

### 11.3 组合器核心逻辑

```
def compose_context(user_input, scene, fenshen, session):
    layers = []
    
    # 1. Prompt Layer (不可压缩)
    layers.append(prompt_layer.get(scene, fenshen))
    
    # 2. Memory Layer (按场景 scope)
    layers.append(memory_layer.get(scene.scene_config.memory_scope, 
                    max_tokens=scene.scene_config.max_context_tokens * 0.1))
    
    # 3. Document Layer (按声明)
    for dep in scene.scene_config.document_deps:
        layers.append(document_summarizer.get(dep.doc, dep.level))
    
    # 4. Config Layer (层叠)
    layers.append(config_injector.get_cascade(scene, fenshen))
    
    # 5. Skill Layer (按相关性)
    skills = skill_retriever.search(user_input + scene.prompt, top_k=5)
    layers.append(format_skills(skills))
    
    # 6. History Layer (全部聊天带权重)
    history = chat_history.get_session(session.id)
    layers.append(format_history_weighted(history))
    
    # 7. Work Output Layer (滑动窗口关键帧)
    outputs = work_output.get_recent(session.id, 
                    window=scene.scene_config.work_output_window_size)
    layers.append(format_work_output(outputs))
    
    return "\n\n".join(layers)
```

### 11.4 启动优先级

1. Snapshot Manager 初始化
2. Config Store 加载层叠
3. Document Summarizer 预缓存
4. Context Composer 启动
5. 进入正常对话循环

---

## 12. 与 Schema v0.81 的兼容与迁移

### 12.1 向后兼容

- 所有 v0.81 的 scene config 字段保持不变
- 新增字段提供默认值，未显式声明的用默认值
- 旧 skill 目录中的配置文件仍可被读取（fallback 模式），但触发 warning

### 12.2 迁移步骤

| 步骤 | 操作 | 影响 |
|---|---|---|
| 1 | 新增 context_composer.py | 无，新模块 |
| 2 | 新增 diff_extractor.py + snapshot_manager.py | 无，新模块 |
| 3 | chat_messages 加 priority 列 | 已有数据为 NULL → 前端默认 normal |
| 4 | 创建 document_summaries 表 | 空表，按需填充 |
| 5 | 创建 config_entries 表 + 将配置从 skill 迁移 | 旧 skill 路径保留为 fallback |
| 6 | scene 声明 document_deps | 可选，不声明则跳过 |
| 7 | 逐步淘汰旧 context 构建 | 完全兼容 |

### 12.3 风险控制

- **因果链断裂风险：** 通过 diff 独立提取 + 高 attention 位置补偿
- **信息漏检风险：** 滑动窗口外旧数据可通过检索访问
- **工程复杂度风险：** 渐进式迁移，逐层上线

---

## 附录 A：Token 预算分配建议

| 层 | 预算占比 | 优先级 |
|---|---|---|
| Prompt Layer | 10% | P0（必须） |
| Memory Layer | 5% | P1（重要） |
| Document Layer | 10% | P2（按场景） |
| Config Layer | 3% | P1（重要） |
| Skill Layer | 5% | P2（按场景） |
| History Layer | 50% | P0（必须） |
| Work Output Layer | 17% | P1（重要） |

以 32K context 为例：
- History: ~16K
- Work Output: ~5.5K
- Prompt: ~3.2K
- Document: ~3.2K
- 其他: ~4.1K

## 附录 B：Schema 文档演化史

| 版本 | 日期 | 核心变更 |
|---|---|---|
| v0.1 | 2026-05-15 | 初始 schema 设计 |
| v0.2 | 2026-05-15 | 分身概念引入 |
| v0.3 | 2026-05-15 | 场景/频道设计 |
| v0.4 | 2026-05-17 | Avatar 联动、记忆系统 |
| v0.5 | 2026-05-17 | 完整 DB schema、Agent Loop |
| v0.6 | 2026-05-19 | Output Gallery、记忆管理 |
| v0.7 | 2026-05-19 | mood 系统、观察通道 |
| v0.8 | 2026-05-19 | 本我/分身身份体系定型 |
| v0.81 | 2026-05-20 | converge/diverge 机制 |
| v0.9 | 2026-05-19 | (中间版本) |
| **v1.0** | **2026-05-21** | **Context 组合架构 — 彻底重构上下文管理** |
| **v1.0+** | **2026-05-21** | **Memory Extraction Layer 补丁 — 定义消息→记忆的沉淀通道** |
