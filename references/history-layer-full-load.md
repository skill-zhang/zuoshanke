# Schema v1.0 全文加载实现记录

> 2026-05-28 — gap analysis 修复 · 9895be2

## 边界定义

**"全文加载，不可压缩"** 在 Schema v1.0 中指：

- **范围**：当前活跃 session 的全部聊天消息（user + ai）
- **行为**：全部原样注入 LLM context，不做条数截断
- **例外**：priority=low 的消息合并为一条摘要，不逐条注入
- **隔离**：其他 session 的消息不进当前 context（session 严格隔离）
- **非全历史**：只限当前 session 内，不是场景全部历史

## 违规的旧实现

`backend/router/scene_stream.py:421`：

```python
# ❌ 违规：截断到最近 20 条
scene_history = q.order_by(Message.created_at.desc()).limit(20).all()
scene_history.reverse()
```

如果 session 有 50 条消息，前 30 条被丢弃，LLM 看不到上下文前段。

## 修复

```python
# ✅ Schema v1.0: 全文加载 — 当前 session 全部消息，不做截断
scene_history = q.order_by(Message.created_at.asc()).all()
```

同时改 `desc() + reverse()` 为直接 `asc()`，减少一次内存反转。

## 配套的 gap analysis 修复（同一 commit）

| 断裂点 | 修复 | 文件 |
|--------|------|------|
| History priority 字段缺失 | 补 `"priority": m.priority or "normal"` | scene_stream.py:424 |
| Token 核算未触发 | ChatView SSE done 调 `accumulateTokens()` | ChatView.tsx, client.ts, appStore.ts |
| Work Output Layer 空跑 | agent_loop 工具成功后写 `snapshot_manager.record()` | agent_loop.py |
| idle_extractor 旁路 | 改为 session 状态驱动（destroyed + memory_extracted） | idle_extractor.py, main.py |
| Memory 语义检索缺失 | 加关键词重叠分 ×2 + weight 加权 | memory_cache.py |

## 数据流验证

```
用户发消息
  → scene_stream 查 Message WHERE scene_id=X AND session_id=Y → .all()
  → build history_messages [{role, content, priority}]
  → compose_context → _build_history_layer
    → high: 全文保留
    → normal: 全文保留
    → low: 合并为一条 system 消息
  → 注入 LLM context
```

## 相关文件

- 设计：`docs/design/schema-v1.0.md` §4.6, §6.1
- 实现：`backend/agent_core/context_composer.py` `_build_history_layer()`
- 调用：`backend/router/scene_stream.py:417-426`
