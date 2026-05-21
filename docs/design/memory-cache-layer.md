# 内存级记忆缓存层 — Memory Cache Layer

> 设计目标：消除 context 压缩触发记忆注入时的 DB 全量查询，实现按需加载与 scope 隔离

## 一、动机

当前记忆系统每次注入都从 DB 全量读取：

```python
# memory_manager.py:288
mems = self.db.query(AgentMemory).all()   # ← 每次全量 O(n)
# → 逐条 calc_weight() → 话题匹配 → 排序 → 取 Top-5
```

400 条时尚可接受，但存在两个问题：

1. **每次注入都拉全量 DB** — 记忆量增长到数千条时 O(n) 扫描不可持续
2. **无变动感知** — context 压缩触发记忆注入时，记忆集没变却要再查一次 DB

## 二、边界定义

本次设计仅解决**记忆的读取性能**问题。以下事项不在本设计范围内：

| 边界外 | 原因 |
|--------|------|
| 分身是否使用本体记忆 | prompt 层决策，非缓存层职责 |
| 记忆的权重公式 | 维持现有 calc_weight 不变 |
| 记忆的生命周期管理 | 维持现有 reinforce / decay / prune 不变 |
| 分身的 prompt 构造 | context_composer 的职责，缓存只提供数据 |
| 记忆的语义过滤 | 已被排除，缓存不做话题预计算 |

## 三、核心设计

### 3.1 设计原则

| 原则 | 说明 |
|------|------|
| **本体永久在线** | 启动时加载 zhu 本体记忆。本体始终在线，供闲聊频道（本体之家）使用 |
| **分身按需加载** | 分身（场景）的记忆在用户点进场景时才加载 |
| **分身 scope 隔离** | 分身只能读到自身 scope 的记忆，看不到其他场景和本体的记忆 |
| **写穿透** | 记忆 CRUD 操作先写 DB，同步更新缓存。进程在两者间崩溃则缓存丢失，下次查 DB 重建 |
| **不做话题预过滤** | 缓存全量存储，不做关键词分组。context composer 取走全部后自行决定哪些注入 |
| **两个层次区分** | 缓存层：**全量存储**该 scope 的全部记忆。注入层：context composer 收到全量后自行截取 weight 最高的前 N 条注入 prompt |
| **懒清理** | 场景切换时旧场景桶保留不删，切回去无需重新查 DB |

### 3.2 加载策略

```
┌─ 进程启动 ─────────────────────────────┐
│  MemoryCache.get_instance()              │
│  └─ load_scope("zhu")                    │
│     └─ DB → ScopeBucket → cache ready   │
└──────────────────────────────────────────┘

┌─ 用户点进场景 A ────────────────────────┐
│  load_scope("scene", context_id="A")      │
│  └─ DB → ScopeBucket → cache ready       │
│  缓存中现在 = [zhu] + [scene_A]          │
└──────────────────────────────────────────┘

┌─ 用户切到场景 B ────────────────────────┐
│  load_scope("scene", context_id="B")      │
│  └─ DB → ScopeBucket → cache ready       │
│  缓存中现在 = [zhu] + [scene_A] + [scene_B] │
│  scene_A 桶保留，不清理                   │
└──────────────────────────────────────────┘

┌─ 查询记忆注入 ──────────────────────────┐
│  get_top_for_context(scope="scene", context_id="A") │
│  └─ 命中 _by_scope["scene:A"]                           │
│  └─ 返回该 scope 全部记忆（按 weight 降序）              │
│  └─ context composer 自行决定注入哪些（通常取 Top-5）    │
│  不会注入 zhu 记忆                                       │
└──────────────────────────────────────────────────────────┘
```

### 3.3 读取路径

```python
get_top_for_context(query, scope, context_id):
  → 构造 scope_key = f"{scope}:{context_id or ''}"
  → 从 _by_scope 中查找对应的 ScopeBucket
  → 未命中 → return []（该 scope 未加载，不自动加载）
  → 命中 → 返回 bucket.memories 全量（已按 weight 降序）
  → 记录访问（累加 _dirty_access_log）
  → return dict 列表
```

缓存全量返回，context composer 自行截取（通常取 weight 最高的 Top-5 注入 prompt）。
不截断的依据：截多少是 context 层的决策，cache 层不应替调用方做。```

注意：**不通过`query`参数做任何语义匹配**。query 保留仅用于未来 embedding 扩展。

### 3.4 写穿透

所有 CRUD 操作保持现有 DB 逻辑不变，尾部追加缓存同步：

```python
# MemoryManager.add()
mem = AgentMemory(...)
self.db.add(mem)
self.db.commit()
# ── 追加 ──
MemoryCache.get_instance().on_memory_created(mem)

# MemoryManager.update()
# DB update + commit
MemoryCache.get_instance().on_memory_updated(mem)

# MemoryManager.delete()
# DB delete + commit
MemoryCache.get_instance().on_memory_deleted(key)
```

`on_memory_created` 内部：
1. 将 DB 记录转为 CachedMemory（含计算 cached_weight）
2. 插入 `_memories` 全局索引
3. 查找或创建对应 scope 的 ScopeBucket
4. 按 weight 插入正确位置

`on_memory_deleted` 内部：
1. 从 `_memories` 移除
2. 从对应 ScopeBucket.memories 移除

**进程崩溃场景**：DB 已写入但缓存未更新。下次触发记忆注入时 `get_top_for_context` 返回为空（因为缓存缺该条），不影响数据完整性。极端情况下用户可以主动 `POST /api/memory/refresh-cache` 重建。

### 3.5 数据结构

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
    scope: str                          # zhu | scene | channel
    context_id: Optional[str]
    is_narrative: bool
    is_immortal: bool
    priority_level: str
    cached_weight: float                # 缓存上一次 calc_weight 的值
                                        # 写入时计算，读取时直接取

    @classmethod
    def from_orm(cls, mem: AgentMemory) -> "CachedMemory":
        """从 DB ORM 对象转换（含 weight 计算）"""
        w = _calc_weight(mem)           # 调用 memory_manager.calc_weight 的纯函数版
        return cls(
            id=mem.id, key=mem.key, content=mem.content,
            ...
            cached_weight=w,
        )


@dataclass
class ScopeBucket:
    """单个 scope + context_id 的记忆分桶"""
    scope_key: str                      # "zhu:" | "scene:abc"
    memories: list[CachedMemory]        # 按 cached_weight 降序（插入排序维护）


class MemoryCache:
    """进程内单例记忆缓存"""

    _instance: Optional["MemoryCache"] = None
    _initialized: bool = False

    _memories: dict[str, CachedMemory]  # id → CachedMemory（全局索引）
    _by_scope: dict[str, ScopeBucket]   # "zhu:" | "scene:abc" → 分桶
    _dirty_access_log: list[tuple[str, int]]  # (memory_id, increment) 待批写入

    # ── 单例 ──

    @classmethod
    def get_instance(cls) -> "MemoryCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """仅测试用"""
        cls._instance = None

    # ── 生命周期 ──

    def initialize(self, db: Session):
        """启动时调用。加载 zhu 本体记忆"""
        if self._initialized:
            return
        self._load_scope(db, "zhu")
        self._initialized = True

    def load_scope(self, db: Session, scope: str, context_id: Optional[str] = None):
        """加载指定 scope 的记忆。启动时 + 点进场景时调用"""
        key = f"{scope}:{context_id or ''}"
        if key in self._by_scope:
            return  # 已加载
        self._load_scope(db, scope, context_id)

    def _load_scope(self, db: Session, scope: str, context_id: Optional[str] = None):
        """从 DB 全量加载一个 scope 的并构建分桶"""
        q = db.query(AgentMemory).filter(AgentMemory.scope == scope)
        if context_id:
            q = q.filter(AgentMemory.context_id == context_id)
        mems = q.all()
        cached = [CachedMemory.from_orm(m) for m in mems]
        cached.sort(key=lambda x: -x.cached_weight)
        key = f"{scope}:{context_id or ''}"
        bucket = ScopeBucket(scope_key=key, memories=cached)
        self._by_scope[key] = bucket
        for cm in cached:
            self._memories[cm.id] = cm

    # ── 读取 ──

    def get_top_for_context(self, query: str = "",
                            scope: str = "zhu",
                            context_id: Optional[str] = None) -> list[dict]:
        """返回该 scope 全部记忆（已按 weight 降序）。query 保留未来扩展不做语义匹配"""
        key = f"{scope}:{context_id or ''}"
        bucket = self._by_scope.get(key)
        if not bucket:
            return []
        # 记录访问次数（异步批量）
        for cm in bucket.memories:
            self._dirty_access_log.append((cm.id, 1))
        return [self._to_dict(cm) for cm in bucket.memories]

    # ── 写穿透回调 ──

    def on_memory_created(self, mem: AgentMemory):
        cm = CachedMemory.from_orm(mem)
        self._memories[cm.id] = cm
        key = f"{cm.scope}:{cm.context_id or ''}"
        bucket = self._by_scope.get(key)
        if bucket:
            self._insert_sorted(bucket.memories, cm)

    def on_memory_updated(self, mem: AgentMemory):
        self.on_memory_created(mem)  # 覆盖重建

    def on_memory_deleted(self, mem_id: str):
        cm = self._memories.pop(mem_id, None)
        if cm:
            key = f"{cm.scope}:{cm.context_id or ''}"
            bucket = self._by_scope.get(key)
            if bucket:
                bucket.memories = [m for m in bucket.memories if m.id != mem_id]

    # ── 刷新 ──

    def rebuild(self, db: Session, scope: str, context_id: Optional[str] = None):
        """丢弃指定 scope 的缓存，从 DB 重建"""
        key = f"{scope}:{context_id or ''}"
        old = self._by_scope.pop(key, None)
        if old:
            for cm in old.memories:
                self._memories.pop(cm.id, None)
        self._load_scope(db, scope, context_id)

    def rebuild_all(self, db: Session):
        """丢弃全部缓存，从 DB 全量重建"""
        self._memories.clear()
        self._by_scope.clear()
        self._load_scope(db, "zhu")

    # ── 内部 ──

    @staticmethod
    def _insert_sorted(lst: list[CachedMemory], item: CachedMemory):
        """按 weight 降序插入"""
        for i, m in enumerate(lst):
            if item.cached_weight > m.cached_weight:
                lst.insert(i, item)
                return
        lst.append(item)

    @staticmethod
    def _to_dict(cm: CachedMemory) -> dict:
        return {
            "id": cm.id, "key": cm.key, "content": cm.content,
            "category": cm.category, "tags": cm.tags,
            "priority_level": cm.priority_level,
            "scope": cm.scope, "context_id": cm.context_id,
            "is_narrative": cm.is_narrative, "is_immortal": cm.is_immortal,
            "weight": round(cm.cached_weight, 2),
        }
```

### 3.6 写穿透位置

在 `MemoryManager` 的每个 CRUD 方法尾部追加单例调用：

| 方法 | 追加调用 |
|------|---------|
| `add()` | `get_instance().on_memory_created(mem)` |
| `update()` | `get_instance().on_memory_updated(mem)` |
| `delete()` | `get_instance().on_memory_deleted(mem_id)` |
| `reinforce()` | `get_instance().on_memory_updated(mem)` |
| `mark_explicit()` | `get_instance().on_memory_updated(mem)` |
| `record_correction()` | `get_instance().on_memory_updated(mem)` |

### 3.7 缓存预热（启动流程）

```python
# main.py lifespan startup

@app.on_event("startup")
async def startup():
    db = next(get_db())
    MemoryCache.get_instance().initialize(db)  # 加载 zhu
    db.close()
```

### 3.8 场景加载入口

```python
# router/scenes.py 场景详情接口

@router.get("/api/scenes/{scene_id}")
def get_scene(scene_id: str, db: Session = Depends(get_db)):
    cache = MemoryCache.get_instance()
    cache.load_scope(db, "scene", scene_id)  # 首次点进时触发
    ...
```

### 3.9 管理端接口

| 端点 | 功能 |
|------|------|
| `GET /api/memory/status` | 返回缓存状态：已加载的 scope 数量、记忆总数、内存估算 |
| `POST /api/memory/refresh-cache` | 全量重建缓存 |
| `POST /api/memory/refresh-scope` | 重建指定 scope 的缓存（body: `{scope, context_id}`） |

### 3.10 边界 & 异常

| 场景 | 处理 |
|------|------|
| scope 尚未加载时查询 | 返回空列表，不自动加载（避免副作用） |
| DB 被外部修改 | `POST /api/memory/refresh-cache` 全量重建 |
| CRUD 后进程崩溃 | DB 数据不丢，缓存下次加载时重建 |
| 场景删除后残留桶 | `rebuild_all()` 时自然消失 |
| 多进程部署 | 当前单进程模型。多 Worker 时需加 Redis 层或关闭缓存 |
| 场景数过多（>20） | 暂不处理。达到这个量级时再加 LRU 淘汰策略 |

## 四、需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `agent_core/memory_cache.py` | **新建** — MemoryCache 类 |
| `agent_core/memory_manager.py` | CRUD 尾部追加写穿透调用。删除 `_detect_topic` + `TOPIC_KEYWORDS` 及所有话题匹配逻辑 |
| `agent_core/context_composer.py` | `MemoryManager(db)` → `MemoryCache.get_instance()` |
| `agent_core/context_builder.py` | 同上 |
| `router/memory.py` | 管理端列表查询仍走 DB。注入接口改用缓存 |
| `router/scenes.py` | 场景详情入口触发 `load_scope` |
| `router/channels.py` | 频道入口触发 `load_scope` |
| `main.py` | lifespan startup 中 `initialize()` |

## 五、话题匹配删除说明

当前 `MemoryManager` 中有 `_detect_topic()` 方法和 `TOPIC_KEYWORDS` 字典（约 50 行关键词匹配逻辑），以及 `get_top_for_context` 中的话题过滤分支。全部删除。

理由是系统不应在缓存层做语义理解。未来如需语义过滤，应走 embedding 向量匹配，而非关键词枚举。

`calc_weight` 的纯函数版（`_calc_weight`）保持原权重计算逻辑不变，提取到单独函数供 `CachedMemory.from_orm` 复用。

## 六、性能预期

| 场景 | 当前 | 优化后 |
|------|------|--------|
| 首次进入场景（全量加载） | — | 1 次 DB 查询（不可避免） |
| context 压缩触发注入（zhu ~100条） | ~3ms | <0.05ms |
| context 压缩触发注入（zhu+scene ~300条） | ~5ms | <0.1ms |
| 写穿透（CRUD 尾部） | — | <0.01ms |
| 场景切换 | — | 1 次 DB 查询（新场景） |

## 七、实施步骤

1. **新建** `agent_core/memory_cache.py` — MemoryCache 完整实现
2. **提取** `calc_weight` 纯函数 — 供 `CachedMemory.from_orm` 使用
3. **删除** `_detect_topic` 和 `TOPIC_KEYWORDS` — 清理 memory_manager.py
4. **修改** `MemoryManager` — CRUD 尾部追加写穿透
5. **修改** `context_composer.py` / `context_builder.py` — 从缓存读取
6. **修改** `router/scenes.py` — 场景入口触发 `load_scope`
7. **修改** `main.py` — lifespan startup `initialize()`
8. **新增** 管理端端点 — status / refresh-cache / refresh-scope
9. **测试** — 单元 + 手动场景测试
