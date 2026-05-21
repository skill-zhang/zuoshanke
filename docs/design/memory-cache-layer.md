# 内存级记忆缓存层 — Memory Cache Layer

## 动机

当前记忆系统每次查询都走 DB：

```
每次构建 LLM Context → MemoryManager(db) → db.query(AgentMemory).all()
                                              → 全量遍历 400+ 条
                                              → 逐条 calc_weight()
                                              → 话题匹配 + 排序
                                              → 取 Top-5
```

400 条时尚可接受，但存在三个问题：

1. **每次请求都拉全量 DB** — 记忆量增长到数千条时 O(n) 扫描不可持续
2. **高频场景反复查** — 同一场景的多次消息/Agent Loop 迭代，记忆集不变却反复查
3. **无变动感知** — 没有主动刷新机制，哪怕 10 秒前刚查过，新请求又查一遍

## 方案：Write-Through 内存缓存

### 总体架构

```
┌─────────────────────────────────────────────────────┐
│                  Memory Cache Layer                  │
│                                                     │
│  ┌──────────────────────────────────────────┐       │
│  │   MemoryCache (进程内单例)               │       │
│  │                                          │       │
│  │  _by_scope（第一级隔离）:                 │       │
│  │  ┌─────────────────────┐                 │       │
│  │  │ "zhu:" (本体)       │  ← 所有场景共享 │       │
│  │  │  ├─ by_topic:tech   │  (weight排序)    │       │
│  │  │  ├─ by_topic:food   │                 │       │
│  │  │  └─ by_topic:...    │                 │       │
│  │  ├─────────────────────┤                 │       │
│  │  │ "scene:abc"         │  ← 场景ABC隔离  │       │
│  │  │  ├─ by_topic:tech   │                 │       │
│  │  │  └─ by_topic:work   │                 │       │
│  │  ├─────────────────────┤                 │       │
│  │  │ "scene:def"         │  ← 场景DEF隔离  │       │
│  │  │  └─ by_topic:tech   │                 │       │
│  │  └─────────────────────┘                 │       │
│  │                                          │       │
│  │  查询 scene_abc 时:                       │       │
│  │  zhu:桶 + scene:abc桶 → 只遍历这两个     │       │
│  └──────────────┬───────────────────────────┘       │
│                 │                                    │
│    write-through │ 每次变更同步写入                   │
│                 ▼                                    │
│  ┌──────────────────────┐                            │
│  │  DB (AgentMemory表)   │                            │
│  │  — 持久层            │                            │
│  │  — 管理视图查询      │                            │
│  └──────────────────────┘                            │
└─────────────────────────────────────────────────────┘
```

### 核心设计

#### 1. 加载时机

| 事件 | 行为 |
|------|------|
| 进程启动（`lifespan` startup） | 全量加载 → 排序 → 就绪 |
| 场景首次 query | 懒加载（尚未加载时触发） |
| 记忆 CRUD 操作 | 写穿透同步更新缓存 |
| 用户明确要求刷新 | `POST /api/memory/refresh-cache` |

#### 2. 读取路径

```text
get_top_for_context(query, max_count, scope, context_id)
  → 从缓存读取（非 DB）
  → 话题检测 → 定位到 by_topic[topic] 分桶
  → 只遍历该分桶（+ personal_info 兜底）→ ~40-80 条
  → 按 weight 排序 → 取 Top-N → return
  → 异步更新 times_accessed（攒批写入 DB）
```

#### 3. 写穿透

所有 CRUD 操作：
```
add()    → DB write + 缓存 insert + 重排序
update() → DB write + 缓存 update + 重排序
delete() → DB delete + 缓存 remove
reinforce() / mark_explicit() / record_correction()
         → DB write + 缓存 update + 重排序
```

**重排序策略**：每条记忆变更后只需要在对应 topic 桶内重新插入排序位置，不影响其他 topic 的桶。

#### 4. 话题匹配预计算

当前 `_detect_topic` 每次都在内存中跑关键词扫描。改成：

- 创建记忆时**预计算 topic** 并缓存为 `mem.cached_topic`
- 查询时只做一次 query 的话题检测，然后直接跟缓存里的 topic 做集合匹配

### 数据结构

```python
@dataclass
class CachedMemory:
    id: str
    key: str
    content: str
    category: str
    tags: list[str]
    base_weight: int
    explicit_boost: int
    times_accessed: int
    last_accessed_at: Optional[datetime]
    last_reinforced_at: Optional[datetime]
    scope: str
    context_id: Optional[str]
    is_narrative: bool
    is_immortal: bool
    priority_level: str
    # ── 预计算（创建时算好，不每次扫描）──
    cached_topic: str     # personal_info / tech / food / general ...
    cached_weight: float  # 实时计算，缓存到下一次变更


class MemoryCache:
    _memories: dict[str, CachedMemory]                      # id → CachedMemory
    _by_scope: dict[str, "ScopeBucket"]                      # "zhu:" | "scene:xxx" → 分桶
    _dirty_access_log: list[tuple[str, datetime]]            # 待批量写入的访问记录


class ScopeBucket:
    """单个 scope + context_id 的记忆分桶"""
    scope: str
    context_id: Optional[str]
    by_topic: dict[str, list[CachedMemory]]                  # topic → [mem...] 按 weight 降序
```

### API 变更

| 端点 | 变更 |
|------|------|
| `GET /api/memory/inject` | 不再创建 MemoryManager(db)，直接从缓存读取 |
| `POST /api/memory` | 创建 → 写 DB + 同步缓存 |
| `PATCH /api/memory/{id}` | 更新 → 写 DB + 同步缓存 |
| `DELETE /api/memory/{id}` | 删除 → 写 DB + 移除缓存 |
| `POST /api/memory/{key}/reinforce` | 强化 → 写 DB + 同步缓存 |
| `POST /api/memory/refresh-cache` | 强制从 DB 重建缓存 |

### 边界 & 异常

| 场景 | 处理 |
|------|------|
| 缓存因 OOM/GC 被清除 | `get_top_for_context` 检测到缓存为空 → 懒加载重建 |
| DB 数据被外部修改（手动 SQL） | 下次写操作时检测 `cache_version` 不一致 → 提示刷新 |
| 批量写入（初始化/迁移） | 批量操作后调用 `rebuild()` 全量重建 |
| 多进程/多 Worker | 内存缓存仅适用于单进程（当前 FastAPI + uvicorn 单进程模式）。后续多 Worker 需加 Redis 层 |

### 与现有系统的关系

```
context_composer.py / context_builder.py
    ↓ (移除 MemoryManager(db) 调用)
memory_cache.get_top_for_context(query, scope, context_id)
    ↓
memory_manager.py 保持不变（作为 CRUD 操作 DB 的接口）
    ↓ 但 memory_cache 接管了记忆管理器的读取路径
```

### 性能预期

| 场景 | 当前（全量 DB） | 优化后（缓存 + topic 分组） |
|------|----------------|---------------------------|
| 400 条记忆 / 仅遍历匹配 topic（~60条） | ~5ms | <0.1ms |
| 4000 条记忆 / 遍历 topic 桶（~200条） | ~50ms（可感知） | <0.3ms |
| 高频场景（10轮迭代） | 500ms 花在记忆查询上 | <3ms |

### 实施步骤

1. 新建 `agent_core/memory_cache.py` — `MemoryCache` 类
2. `get_top_for_context` 改造为从缓存读取
3. `MemoryManager` 的 CRUD 方法改造为写穿透
4. `context_composer.py` 和 `context_builder.py` 改为使用缓存
5. 异步批处理 `times_accessed` 写入
6. 缓存预热（lifespan startup）
7. 管理端 `POST /api/memory/refresh-cache` 端点
