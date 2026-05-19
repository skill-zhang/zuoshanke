# 坐山客智能召回系统 — 设计与差距分析

> 版本：v1.0 | 日期：2026-05-20
> 对标：Hermes Agent 的 `recall` 流程

---

## 一、要解决的问题

在 Hermes CLI 中，用户发一条消息后，AI 会自动执行一个 **"recall"** 步骤：

```
① 用户消息
② 静默加载持久记忆（MEMORY.md / USER.md）→ 注入 system prompt
③ AI 启动 Agent Loop →
④ AI 自主调用 session_search("关键词") → 终端显示 ┊ 🔍 recall "关键词"
⑤ 搜索结果注入 context
⑥ AI 正常回复
```

核心优势：**关键词由 AI 自主提炼**（利用模型语义理解），而非硬编码词表匹配。

坐山客已有的 Agent Loop 架构类似（LLM 自主调 tools + function calling），但缺失关键的召回能力。

---

## 二、当前坐山客的能力盘点

### 2.1 已具备的能力 ✅

| 能力 | 现状 |
|------|------|
| Agent Loop 执行引擎 | 完整：LLM 自主调工具 → 执行 → 结果喂回 → 继续 |
| function calling 工具列表 | 23 个工具注册在 `registry.json`，转 OpenAI 格式 |
| 持久记忆系统 | `AgentMemory` 权重驱动（P0-P3），有话题检测、自动提取、强化衰减 |
| 搜索引擎 | `session_search()` 函数支持关键词搜索历史消息 |
| `session_search` 已在注册表 | 已注册、未排除，AI 理论上可调 |

### 2.2 差距分析 🔴

| 差距 | Hermes 的做法 | 坐山客现状 | 影响 |
|------|-------------|-----------|------|
| **搜索方式** | FTS5 全文索引（支持中文） | **LIKE %keyword% 模糊匹配** | 中文搜索漏检严重，跨句搜索几乎无效 |
| **AI 主动调用引导** | System prompt 明确教 LLM 什么时候该搜索 | **没提**——LLM 不知道有这个能力 | AI 几乎从不主动调用 `session_search` |
| **记忆注入时机** | `prefetch_all()` 在 AI 思考前静默注入 | `get_top_for_context()` 手动调 | 场景模式下记忆不自动注入 |
| **关键词提取** | AI 模型自己推理 | 硬编码 `TOPIC_KEYWORDS` 字典 | 无法覆盖长尾话题 |

---

## 三、改动方案

### Phase 1 — 搜索升级：LIKE → FTS5 + 中文分词 (✅ 已完成)

`tools/session_search.py`
- ✅ FTS5 虚拟表 `messages_fts(msg_id, content)`，`unicode61` tokenizer
- ✅ jieba 中文分词建索引，首次全量 + 增量同步
- ✅ 搜索用 FTS5 MATCH，`AND` 语义组合分词结果
- ✅ FTS5 失败自动降级为 jieba 多词 OR LIKE 搜索（兜底）
- ✅ 后台线程预热（`main.py` 启动时触发 `_ensure_fts_table()`）
- ✅ 命令行：`python session_search.py search/list/rebuild/status`

### Phase 2 — 系统 prompt 引导 (✅ 已完成)

`backend/agent_core/agent_loop.py` → `build_agent_system_prompt()`
- ✅ 新增「回忆能力」章节，告诉 LLM：
  - 可用 `session_search` 搜索历史内容
  - 用户提到"上次说的"时应该先搜索
  - 利用搜索结果理解上下文再回答

### Phase 3 — AI 自主调用链路验证 (✅ 已完成)

- ✅ `session_search` 已注册在 registry.json（未在 _EXCLUDED_TOOLS 中）
- ✅ `build_tool_definitions()` 正确转换为 OpenAI function calling 格式
- ✅ Agent Loop 14 个可见工具中包含 session_search

---

## 四、相关文件索引

| 文件 | 职责 |
|------|------|
| `tools/session_search.py` | 历史消息搜索（当前 LIKE，待改 FTS5） |
| `tools/registry.json` | 工具注册表（session_search 已注册） |
| `backend/agent_core/agent_loop.py` | Agent Loop 引擎 + system prompt 构建 |
| `backend/agent_core/tool_registry.py` | 基础工具定义 + 注册表加载 |
| `backend/agent_core/tool_executor.py` | 工具执行器（预执行 + 按名调用） |
| `backend/agent_core/memory_manager.py` | 记忆管理器（话题检测 + 权重 + 自动提取） |
| `backend/models.py` | AgentMemory + Message（DB 模型） |
| `backend/router/scenes.py` | 场景路由（调用 Agent Loop） |

---

## 五、白牌工具清单（本地有代码但未注册）

| 文件 | 可注册的函数 | 建议 |
|------|-------------|------|
| `tools/clarify_question.py` | `clarify_ask` | 🔴 可用作 Agent Loop 反问问工具 |
| `tools/hello.py` | — | 🟢 测试文件，忽略 |

---

## 六、已知坑：意图混淆陷阱（2026-05-20）

### 问题描述

当用户说「还记得咱们的 system prompt 分层的事么」，LLM 可能：

```
用户：还记得…system prompt…吗
  ↓
AI 听到"system prompt" → 匹配到「编辑 system prompt」工具
  ↓
AI: 直接开始改 system prompt（而不是去搜历史）
  ↓
用户：？？？我问你还记不记得，没让你改啊
```

**根因**：tool description 中的关键词（如 `system`, `prompt`, `weather`, `file` 等）被 LLM 当作**执行信号**而不是**搜索关键词**。

### 预防方案

**① session_search 的 tool description 加「防污染」措辞**
告知 LLM 这是一个纯搜索工具，查询中出现其他工具名时仅视为搜索关键词。

**② system prompt 加「意图决策树」**
当用户说「还记得」/「之前」/「上次」这类回溯信号时，**必须先回忆再行动**。

### 判断逻辑

```
用户消息
  ├─ 含"还记得"/"之前"/"上次"/"我们说过"/"你记得" → 先 session_search，再综合结果
  ├─ 含"帮我做"/"执行"/"改成"/"写一个" → 直接行动
  └─ 不确定 → 先搜再看：session_search 获取上下文，再决策
```
