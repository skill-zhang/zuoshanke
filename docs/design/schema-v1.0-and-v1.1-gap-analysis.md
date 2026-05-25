# Schema v1.0 & v1.1 实现差距分析

> 设计日期：2026-05-25
> 背景：在修复 session 隔离 bug 过程中，用户要求重新审阅 schema-v1.0 和 schema-v1.1 设计文档与实际代码的差距。
> 触发事件：[测试2]场景中凌晨1:15的拨测讨论被错误装载到当前 context，导致分身优先做拨测而非回答当前问题。

---

## 用户的原话

```
我建议你再仔细看看 schema-1.0和schema-1.1，再看看代码，咱们现在有啥问题。
```

---

## 发现的问题

### Layer 1 — Prompt Layer
✅ 基本完整。分身意识注入、工具列表、使用说明、思考流指引等都在。

### Layer 2 — Memory Layer
⚠️ 能用但浅。`context_composer.py:_build_memory_layer` 从 `MemoryCache` 取 Top-5，按 weight 排序。但 `query` 参数显式标注了 "保留仅用于未来 embedding 扩展，目前不做语义匹配"——没有语义检索。

### Layer 3 — Document Layer
❌ **死层。** `_build_document_layer` 函数的实现是完整的（读 `scene.scene_config.document_deps` → 查 `document_summarizer`），但没有任何场景声明过 `document_deps`。`document_summarizer` 也没有数据来源。这是个空跑的函数，永远返回空字符串。

### Layer 4 — Config Layer
⚠️ 只读路由配置（model/provider/temperature）和收敛参数。设计说的 **"本体→分身→scene→session 四层配置层叠"没有实现**。`fenshen_config` 和 `session_config` 参数传进来也完全没有使用——`_build_config_layer` 签收了这两个参数但函数体里从未引用它们。

### Layer 5 — Skill Layer
✅ 基本完整。`SkillManager.match_for_context` 按相关性检索 Top-2 skill。

### Layer 6 — History Layer
❌ **核心链路是断的。**

设计说每条消息有 `priority: high/normal/low` 权重（schema-v1.0 §6），`_build_history_layer` 也按 high→normal→low 排序组装了——但是 scene_stream.py 加载 history_messages 时根本没有 priority 字段：

```python
# scene_stream.py:362-364
history_messages = [
    {"role": m.role, "content": m.content}  # ← 没有 priority！
    for m in scene_history if m.id != user_msg.id
]
```

这导致 `_build_history_layer` 的 `m.get("priority")` 永远是 None → 全落成 normal → 优先级排序是死代码。

另外 Messages 表也没有 priority 列，后端存储时也没地方写。`priority_assigner.py` 存在、`PRIORITY_GUIDE` 被注入到 system prompt，但没有任何实际数据流过 priority 系统。

### Layer 7 — Work Output Layer
❌ **断的。** `_build_work_output_layer` 读 `FileSnapshot` 表，但没有任何代码在工具执行后调用 snapshot_manager 写快照。Agent Loop 执行完工具不会创建 FileSnapshot 记录。`diff_extractor` 和 `snapshot_manager` 模块存在但未集成到执行流程中。

---

### 更严重的问题：多个设计功能完全没跑通

| 设计说要 | 代码状态 | 影响 |
|---------|---------|------|
| **消息 priority 权重系统** | Messages 表无 priority 列，scene_stream 不传 priority，`_build_history_layer` 的排序逻辑永不到达 | 所有消息同权，设计里的"高 attention 位置放重要内容"不生效 |
| **Token 核算**（v1.1 §6） | `POST /api/sessions/{id}/token` 端点存在，但前端 SSE 流结束后从不调用 | `prompt_tokens`/`completion_tokens`/`api_calls`/`estimated_cost_usd` 永远是 0 |
| **记忆提取兜底**（v1.1 §5） | `idle_extractor.py` 完整（106行），但 main.py 里启动代码被注释掉，理由"每5分钟无差别提取太激进" | 只有前端 `visibilitychange` 触发提取，没有后端兜底 |
| **工具执行后写 FileSnapshot** | 无集成点 | Work Output Layer 永远返回空，LLM 看不到最近的操作记录 |
| **语义记忆检索** | `query` 参数标注"暂不实现" | Memory Layer 靠 weight 排序，与当前用户 query 无关 |
| **Document Layer 数据源** | 无任何场景声明 `document_deps` | 该层永远空跑，浪费了一次函数调用 |

---

## 当前已修复的底层问题

在这次 session 中已经修了三个阻断 session 管理的 bug：

1. **`setCurrentScene` 不存 session_id**（appStore.ts） — session 隔离层白做
2. **ChatView 不等 session ready 就加载消息**（ChatView.tsx） — 旧消息混入 context
3. **session 超时清理因 aware/naive datetime 类型不匹配静默异常**（sessions.py） — 所有 session 永不销毁

但这些只是让 session 管理"能跑"，不等于 7 层 context 组合"能用"。

---

## 建议修复优先级

1. **Message priority 存储 + 传递** — Messages 表加 priority 列 → scene_stream 传入 → history_layer 排序生效。这是最核心也最简单的改动
2. **Token 核算前端集成** — `sendSceneMsg` 的 SSE 流结束事件处理中调 `accumulateTokens`
3. **提取兜底启动** — `main.py` 取消 `idle_extractor` 注释，或改为 session 销毁时触发（已在本次 session 中部分实现）
4. **Work Output Layer 集成** — Agent Loop 工具执行后调 `snapshot_manager`
5. **语义记忆检索** — 替换 `get_top_for_context` 的 query 逻辑
