# 记忆作用域设计（Memory Scope Design）

> 日期: 2026-05-27
> 来源: 坐山客与用户张清泉关于记忆跨场景污染的深入讨论
> 关联: `models.py` (AgentMemory), `tools/memory_tool.py`, `agent_core/memory_manager.py`, `agent_core/context_builder.py`, `router/scenes.py`, `tools/registry.json`

---

## 一、背景与问题

### 1.1 当前问题

记忆系统 v2（LLM 自主管理）上线后，所有记忆存在一个全局 `AgentMemory` 表中。`_build_memory_block()` / `get_top_for_context()` 按权重+话题匹配取 Top-N 注入，**不按来源过滤**。

导致**跨场景污染**：

```
场景A「二手车」→ 存了「2019款宝马3系二手价18-22万」
    ↓
场景B「旅游」→ 也被注入这条记忆
    → ❌ 不相关，浪费 token 和注意力
```

但同时有些信息必须是跨场景通用的：

```
闲聊频道「用户偏好冷色系、青蓝霓虹」
    ↓
所有场景分身都应该知道这条
    → ✅ 本体级别的事实
```

### 1.2 核心矛盾

| 信息类别 | 例子 | 应归属 | 跨场景？ |
|---------|------|--------|---------|
| 本体事实 | 用户偏好、习惯、身份信息 | 本体层 | ✅ 全注入 |
| 场景工作记忆 | 宝马价格、数据库选型、行程安排 | 场景层 | ❌ 完全隔离 |
| 频道会话记忆 | 闲聊话题、群聊内容 | 本体层（闲聊即本体住所） | ✅ 全注入 |
| P0 锚定 | 用户强调「这条特别重要」 | 本体层 | ✅ 全注入 |

---

## 二、设计哲学

### 2.1 记忆归属层级（三域模型）

```
┌─────────────────────────────────────────┐
│         本体记忆（scope=zhu）              │
│    闲聊频道写入 / P0 始终注入             │
│  所有场景分身可读（只读）不可写             │
├──────────┬──────────┬────────────────────┤
│ 场景A记忆 │ 场景B记忆 │  场景C记忆          │
│ scope=scene│ scope=scene│ scope=scene     │
│ 读+写     │ 读+写     │  读+写             │
│ 互不可见   │ 互不可见   │  互不可见          │
└──────────┴──────────┴────────────────────┘
```

### 2.2 关键规则

| 规则 | 说明 |
|------|------|
| **本体共享、场景隔离** | scope=zhu 所有分身只读可访问；scope=scene 各自隔离 |
| **分身不写本体** | 场景分身不能写入 scope=zhu（防止低质量信息污染本体记忆） |
| **LLM 自主判断** | LLM 在场景中自主决定写入 scope=scene（默认）或 scope=zhu（受限） |
| **本体全可见** | 本体（主进程）可读取全部 scope 的记忆 |
| **闲聊 = 本体** | 闲聊频道写入 scope=zhu，因为闲聊频道是本体的住所 |

### 2.3 记忆写入权限矩阵

| 写入者 | scope=zhu | scope=scene | scope=channel |
|--------|-----------|-------------|---------------|
| 本体（闲聊频道/仪表盘） | ✅ 读写 | ✅ 只读 | ✅ 只读 |
| 场景分身 A | ❌ 禁止写 | ✅ 读写（仅 scene_id=A） | ❌ |
| 场景分身 B | ❌ 禁止写 | ✅ 读写（仅 scene_id=B） | ❌ |
| 频道分身 | ❌ 禁止写 | ❌ | ✅ 读写（仅 channel_id=当前） |

### 2.4 记忆读取规则

```
当前上下文为【场景A】→ _build_memory_block() 返回：
  ✓ scope=zhu（本体记忆，带「仅供参考」标记）
  ✓ scope=scene AND context_id=场景A_ID
  ✗ scope=scene AND context_id≠场景A_ID（其他场景的完全不可见）

当前上下文为【闲聊频道】→ _build_memory_block() 返回：
  ✓ scope=zhu（本体记忆）
  ✗ 所有 scope=scene 的不注入（场景记忆与本体无关）

当前上下文为【本体】→ _build_memory_block() 返回：
  ✓ scope=zhu（本体记忆）
```

---

## 三、数据模型变更

### 3.1 AgentMemory 表新增字段

```python
class AgentMemory(Base):
    __tablename__ = "agent_memory"

    # ... 现有字段 ...

    # 🆕 记忆作用域（2026-05-27）
    scope = Column(String, default="zhu", nullable=False)      # zhu | scene | channel
    context_id = Column(String, nullable=True, index=True)      # 场景ID/频道ID（scope=zhu时为空）
```

**设计说明**：
- `scope="zhu", context_id=null` → 本体记忆
- `scope="scene", context_id="scene_xxx"` → 场景记忆
- `scope="channel", context_id="channel_xxx"` → 频道记忆
- 两个新字段上**已有数据的默认值**为 `scope="zhu", context_id=null`（向后兼容）
- 新增表字段用 `ALTER TABLE` 手动执行（SQLite 不支持自动加列）

**迁移 SQL**：
```sql
ALTER TABLE agent_memory ADD COLUMN scope VARCHAR(10) NOT NULL DEFAULT 'zhu';
ALTER TABLE agent_memory ADD COLUMN context_id VARCHAR(32);
CREATE INDEX ix_agent_memory_scope ON agent_memory(scope);
CREATE INDEX ix_agent_memory_context_id ON agent_memory(context_id);
```

### 3.2 表级迁移策略

- ✅ 新增列，已有数据全部属于 `scope="zhu"`（向后兼容，不影响现有行为）
- 索引在 `create_all()` 之外手动创建（或用 SQLite 的 `CREATE INDEX IF NOT EXISTS`）
- 零破坏——现有查询不使用这两个新字段就不会受影响

---

## 四、Memory Tool 变更（tools/memory_tool.py）

### 4.1 新增 `scope` 参数

```python
def memory_tool(
    action: str,
    target: str = "memory",
    content: str = None,
    old_text: str = None,
    key: str = None,
    scope: str = None,          # 🆕 可选：zhu | scene | channel
    context_id: str = None,      # 🆕 可选：场景ID/频道ID（通常自动推断）
) -> str:
```

### 4.2 作用域推断逻辑

```
调用 memory_tool(action='add', content='...') 时：
  1. 如果传了 scope → 使用指定 scope
  2. 如果没传 scope → 自动推断：
     a. 当前上下文有 scene_id → scope='scene', context_id=scene_id
     b. 当前上下文有 channel_id → scope='channel', context_id=channel_id
     c. 当前上下文无 scene/channel → scope='zhu'
  3. 如果 scope='zhu' 但当前上下文是 scene/channel → 拒绝并提示
```

### 4.3 安全校验

```python
# 场景/频道分身禁止写 zhu
if scope == "zhu" and _is_fenshen_context():
    return json.dumps({
        "success": False,
        "error": "分身不能直接写入本体记忆（scope=zhu）。"
                 "如需将此信息存储为本体记忆，请在闲聊频道中提及。"
    }, ensure_ascii=False)
```

### 4.4 LLM 自主写入引导

在 memory_tool 的 description 中增加引导：

```
memory_tool 使用说明：
  - 默认为当前上下文绑定的作用域（场景记忆仅限当前场景）
  - 只有当你判断「这条信息是用户的通用偏好/身份信息，
    在所有场景中都应知晓」时，才显式传 scope='zhu'
```

### 4.5 registry.json 更新

```json
{
    "name": "memory",
    "file": "memory_tool.py",
    "function": "memory_tool",
    "preexecute": false,
    "parameters": {
        "action": { "type": "string", "enum": ["add", "reinforce", "read", "replace", "remove"] },
        "target": { "type": "string", "default": "memory" },
        "content": { "type": "string" },
        "old_text": { "type": "string" },
        "key": { "type": "string" },
        "scope": {
            "type": "string",
            "enum": ["zhu", "scene", "channel"],
            "description": "记忆作用域：zhu=本体级(跨场景)，scene=当前场景(隔离)，channel=当前频道(隔离)。不传则自动绑定当前上下文"
        }
    },
    "required": ["action"]
}
```

---

## 五、Context Builder 变更（context_builder.py）

### 5.1 _build_memory_block 增加作用域过滤

```python
def _build_memory_block(
    db,
    query: str,
    scope: Optional[str] = None,         # 🆕
    context_id: Optional[str] = None,    # 🆕
) -> str:
    if db is None:
        return ""
    mm = MemoryManager(db)
    memories = mm.get_top_for_context(
        query,
        max_count=5,
        scope=scope,          # 🆕
        context_id=context_id # 🆕
    )
    if not memories:
        return ""
    # ... 格式化逻辑 ...
```

### 5.2 build_scene_context 增加 scene_id 传播

```python
def build_scene_context(
    user_content: str,
    history_messages: Optional[list] = None,
    matched_tools: Optional[list] = None,
    tool_results: Optional[list] = None,
    weather_context: Optional[str] = None,
    user_context: Optional[str] = None,
    db=None,
    scene_id: Optional[str] = None,    # 🆕
) -> list[dict]:
    # ... 现有逻辑 ...
    
    # 记忆块注入 → 传入作用域
    memory_block = _build_memory_block(
        db, user_content,
        scope="scene" if scene_id else "zhu",
        context_id=scene_id
    )
    
    # ... 后续逻辑 ...
```

### 5.3 get_top_for_context 增加作用域过滤

```python
def get_top_for_context(
    self,
    query: str = "",
    max_count: int = MAX_INJECT_COUNT,
    scope: Optional[str] = None,          # 🆕
    context_id: Optional[str] = None,     # 🆕
) -> list[dict]:
    """获取应注入到上下文的 Top-N 条记忆

    作用域过滤（新增）:
      - scope=None → 兼容旧调用，返回全部（不限制）
      - scope="zhu" → 只返回 scope="zhu" 的
      - scope="scene", context_id=xxx → 返回 scope=zhu + 匹配context_id的
    """
    mems = self.db.query(AgentMemory).all()
    if not mems:
        return []

    # 🆕 作用域过滤
    if scope == "zhu":
        mems = [m for m in mems if m.scope == "zhu"]
    elif scope == "scene" and context_id:
        mems = [m for m in mems
                if m.scope == "zhu" or
                   (m.scope == "scene" and m.context_id == context_id)]
    elif scope == "channel" and context_id:
        mems = [m for m in mems
                if m.scope == "zhu" or
                   (m.scope == "channel" and m.context_id == context_id)]

    # ... 现有的话题匹配 + 权重排序 + Top-N ...
```

---

## 六、前端调用方变更（router/scenes.py）

### 6.1 场景流式路由调用链

```python
# scenes.py -> build_scene_context() 调用处
# 当前
messages = build_scene_context(
    user_content=msg,
    history_messages=history,
    db=db,
)

# 改为
messages = build_scene_context(
    user_content=msg,
    history_messages=history,
    db=db,
    scene_id=scene.id,   # 🆕 传入场景ID
)
```

### 6.2 本体视图（仪表盘/闲聊频道）调用链

不传 `scene_id` → `_build_memory_block` 走默认 `scope="zhu"` 路由，只读本体记忆。

---

## 七、Agent Loop 集成

### 7.1 工具调用上下文注入

Agent Loop 执行工具时，需要把当前 `scene_id` / `channel_id` 传递给 `memory_tool`。方式：在 `tool_executor.py` 中，调用工具函数前注入上下文变量：

```python
# tool_executor.py
import threading

_tool_context = threading.local()

def set_tool_context(scene_id=None, channel_id=None):
    _tool_context.scene_id = scene_id
    _tool_context.channel_id = channel_id

def get_tool_context():
    return {
        "scene_id": getattr(_tool_context, "scene_id", None),
        "channel_id": getattr(_tool_context, "channel_id", None),
    }

def clear_tool_context():
    _tool_context.scene_id = None
    _tool_context.channel_id = None
```

memory_tool 通过 `get_tool_context()` 获取当前上下文实现自动推断。

### 7.2 场景 Agent Loop 初始化

```python
# router/scenes.py 中调用 run_agent_loop 前
set_tool_context(scene_id=scene.id)
try:
    for event in run_agent_loop(...):
        yield event
finally:
    clear_tool_context()
```

---

## 八、迁移路径

### Phase 1（🟢 零风险）

| 步骤 | 文件 | 说明 |
|------|------|------|
| ① 改模型 | `models.py` | AgentMemory 加 scope + context_id 字段 |
| ② 迁移数据 | `ALTER TABLE` | 已有数据 scope='zhu' |
| ③ 改 Manager | `memory_manager.py` | `get_top_for_context()` 加 scope 过滤 |

**影响**：表结构变化 + Manager 新增参数，但旧调用方传 `scope=None` 时行为不变。

### Phase 2（🟢 低风险）

| 步骤 | 文件 | 说明 |
|------|------|------|
| ④ 改 Context | `context_builder.py` | `_build_memory_block()` 传 scope/context_id |
| ⑤ 改 Scene | `router/scenes.py` | 传 scene_id 给 context builder |

**影响**：实际启用场景过滤。此时场景记忆已经隔离，旧数据（scope='zhu'）仍然跨场景注入。

### Phase 3（🟡 中风险）

| 步骤 | 文件 | 说明 |
|------|------|------|
| ⑥ 改 Tool | `tools/memory_tool.py` | 加 scope 参数 + 自动推断 |
| ⑦ Agent Loop | `tool_executor.py` | 增加线程上下文注入 |
| ⑧ Registry | `tools/registry.json` | memory 工具加 scope 参数描述 |

**影响**：LLM 开始有 scope 意识。关键点——分身写 zhu 的被拒绝，需要 LLM 适应。

---

## 九、边界情况

### 9.1 旧数据兼容

未迁移的旧数据全部 `scope="zhu"`。Phase 2 上线后，旧数据会继续跨场景注入——行为不变。只有当新工具存了 `scope="scene"` 的数据后才真正隔离。**零破坏**。

### 9.2 场景被删除时

场景被删除，对应的 `scope="scene"` 记忆不会被自动清除：
- 读取时，因为场景 ID 不再存在，context builder 不会再请求该 context_id
- 但这些记忆记录在表中形成**孤儿记录**
- 可选的 GC 策略：场景删除时 **不自动清理记忆**（本体可能还想看），提供手动清理按钮
- scope=zhu 的记忆永远不被清理（除非用户主动删除）

### 9.3 分身日志记录

每当分身向本体记忆写入（被拒绝）时，记录一条日志供调试：
```python
logger.info(
    f"[memory-scope] 分身尝试写 zhu 被拒绝: "
    f"scene={_tool_context.scene_id}, content={content[:50]}"
)
```

### 9.4 本体全量查看

本体通过 UI（MemoryView）查看记忆时，增加 scope 过滤 tab：
- 「全部」(默认)
- 「本体记忆」(scope=zhu)
- 「场景A记忆」(scope=scene, context_id=A)
- 「场景B记忆」(scope=scene, context_id=B)

每种记忆在卡片上标作用域标签（`🏠 本体` / `📦 场景A`）。

---

## 十、与 Schema v0.8 的一致性校验

| Schema v0.8 原则 | 对应设计 | 状态 |
|-----------------|---------|------|
| 本我不可篡改 | 分身不能写 scope=zhu | ✅ |
| 分身知道自己是分身 | memory 工具 description 明确说明 scope 含义 | ✅ |
| 主进程不 micromanage | LLM 自主判断是否写 scope=zhu，不手动触发 | ✅ |
| 闲聊频道=本体住所 | 闲聊频道写入自动 scope=zhu | ✅ |
| LLM 是能力引擎 | memory 工具只是工具，LLM 自主决定存什么 | ✅ |

---

## 十一、相关文件

| 文件 | 角色 |
|------|------|
| `backend/models.py` | AgentMemory 模型定义 |
| `backend/agent_core/memory_manager.py` | Manager CRUD + 相关性匹配 |
| `backend/agent_core/context_builder.py` | 上下文构建 + 记忆块注入 |
| `tools/memory_tool.py` | memory 工具（LLM 调用的入口） |
| `tools/registry.json` | 工具注册表 |
| `backend/tool_executor.py` | 工具执行器 + 线程上下文 |
| `backend/router/scenes.py` | 场景路由（调用 context builder） |
| `references/memory-philosophy.md` | 记忆系统哲学 |
| `docs/design/schema-v0.6.md` | 记忆系统 v2 改造 |
| `docs/design/schema-v0.8.md` | 坐山客身份架构（本尊/分身） |

---

## 改动记录

| 日期 | 改动 |
|------|------|
| 2026-05-27 | 初版 — 基于与张清泉的深入讨论设计 |
