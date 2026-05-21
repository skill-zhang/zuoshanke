"""内存级记忆缓存层 — 按需加载 + Write-Through + Scope 隔离

本体（zhu）永不离线，分身（scene/channel）按需加载。
缓存全量存储，不做话题预过滤，context composer 自行截取注入。
"""

import math
import logging
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from models import AgentMemory
from config.constants import (
    MEMORY_DEFAULT_BASE_WEIGHT,
    MEMORY_DECAY_HALF_LIFE,
)

logger = logging.getLogger(__name__)

# ── 权重常量 ──
P0_THRESHOLD = 8.0
P1_THRESHOLD = 4.0
P2_THRESHOLD = 2.0


# ════════════════════════════════════════════════════════
# 纯函数：calc_weight（提取自 memory_manager，供双方复用）
# ════════════════════════════════════════════════════════


def calc_weight(
    base_weight: int,
    is_immortal: bool,
    times_accessed: int,
    explicit_boost: int,
    last_accessed_at: Optional[datetime],
    created_at: Optional[datetime],
) -> float:
    """计算记忆实时权重（纯函数，不依赖 DB Session）

    公式: weight = base × recency × frequency × boost
    """
    # recency
    if is_immortal:
        recency = 1.0
    else:
        now = datetime.now(timezone.utc)
        last = last_accessed_at or created_at or now
        if isinstance(last, datetime) and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days_since = max(0, (now - last).total_seconds() / 86400.0)
        recency = math.pow(2, -days_since / MEMORY_DECAY_HALF_LIFE)

    # frequency
    frequency = 1 + math.log2(max(times_accessed, 0) + 1)

    # boost
    boost = max(explicit_boost, 1)

    return base_weight * recency * frequency * boost


def auto_level(weight: float) -> str:
    """根据权重自动计算等级"""
    if weight >= P0_THRESHOLD:
        return "P0"
    if weight >= P1_THRESHOLD:
        return "P1"
    if weight >= P2_THRESHOLD:
        return "P2"
    return "P3"


# ════════════════════════════════════════════════════════
# 内存数据结构
# ════════════════════════════════════════════════════════


@dataclass
class CachedMemory:
    """内存中的一条记忆（从 DB ORM 转换）"""

    id: str
    key: str
    content: str
    category: str
    tags: list
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
    cached_weight: float

    @classmethod
    def from_orm(cls, mem: "AgentMemory") -> "CachedMemory":
        """从 DB ORM 对象转换，同时计算 weight"""
        w = calc_weight(
            base_weight=mem.base_weight,
            is_immortal=mem.is_immortal,
            times_accessed=mem.times_accessed or 0,
            explicit_boost=mem.explicit_boost or 1,
            last_accessed_at=mem.last_accessed_at,
            created_at=mem.created_at,
        )
        return cls(
            id=mem.id,
            key=mem.key,
            content=mem.content,
            category=mem.category,
            tags=mem.tags or [],
            base_weight=mem.base_weight,
            explicit_boost=mem.explicit_boost or 1,
            times_accessed=mem.times_accessed or 0,
            last_accessed_at=mem.last_accessed_at,
            last_reinforced_at=mem.last_reinforced_at,
            scope=mem.scope,
            context_id=mem.context_id,
            is_narrative=mem.is_narrative,
            is_immortal=mem.is_immortal,
            priority_level=mem.priority_level,
            cached_weight=w,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "content": self.content,
            "category": self.category,
            "tags": self.tags,
            "priority_level": self.priority_level,
            "scope": self.scope,
            "context_id": self.context_id,
            "is_narrative": self.is_narrative,
            "is_immortal": self.is_immortal,
            "base_weight": self.base_weight,
            "explicit_boost": self.explicit_boost,
            "times_accessed": self.times_accessed,
            "weight": round(self.cached_weight, 2),
        }


@dataclass
class ScopeBucket:
    """单个 scope + context_id 的记忆分桶（全量）"""

    scope_key: str
    memories: list[CachedMemory]  # 按 cached_weight 降序


# ════════════════════════════════════════════════════════
# MemoryCache（进程内单例）
# ════════════════════════════════════════════════════════


class MemoryCache:
    """内存级记忆缓存 — 按需加载 + 写穿透 + scope 隔离

    使用方式:
        cache = MemoryCache.get_instance()
        cache.initialize(db)              # 启动时加载 zhu
        cache.load_scope(db, "scene", id) # 点进场景时加载
        mems = cache.get_top_for_context(scope="scene", context_id=id)
    """

    _instance: Optional["MemoryCache"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._memories: dict[str, CachedMemory] = {}
        self._by_scope: dict[str, ScopeBucket] = {}
        self._initialized = False

    # ── 单例 ──────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "MemoryCache":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """仅测试用"""
        cls._instance = None

    # ── 生命周期 ──────────────────────────────────────

    def initialize(self, db: Session):
        """启动时调用。加载 zhu 本体记忆"""
        if self._initialized:
            logger.debug("MemoryCache 已初始化，跳过")
            return
        self._load_scope(db, "zhu")
        self._initialized = True
        count = len(self._by_scope.get("zhu:", ScopeBucket("zhu:", [])).memories)
        logger.info(f"MemoryCache 初始化完成，已加载本体记忆 {count} 条")

    def load_scope(self, db: Session, scope: str, context_id: Optional[str] = None):
        """加载指定 scope 的记忆。已有则跳过。

        启动时 + 点进场景/频道时调用。
        """
        key = self._make_key(scope, context_id)
        if key in self._by_scope:
            logger.debug(f"Scope {key} 已缓存，跳过")
            return
        self._load_scope(db, scope, context_id)

    def _load_scope(self, db: Session, scope: str, context_id: Optional[str] = None):
        """从 DB 全量加载一个 scope 并构建分桶"""
        q = db.query(AgentMemory).filter(AgentMemory.scope == scope)
        if context_id:
            q = q.filter(AgentMemory.context_id == context_id)

        rows = q.all()
        cached = [CachedMemory.from_orm(m) for m in rows]
        cached.sort(key=lambda x: -x.cached_weight)

        key = self._make_key(scope, context_id)
        bucket = ScopeBucket(scope_key=key, memories=cached)
        self._by_scope[key] = bucket
        for cm in cached:
            self._memories[cm.id] = cm

        logger.debug(f"已加载 scope {key}: {len(cached)} 条")

    # ── 读取 ──────────────────────────────────────────

    def get_top_for_context(self,
                            query: str = "",
                            scope: str = "zhu",
                            context_id: Optional[str] = None) -> list[dict]:
        """返回该 scope 全部记忆（已按 weight 降序）。

        query 保留仅用于未来 embedding 扩展，目前不做语义匹配。
        """
        key = self._make_key(scope, context_id)
        bucket = self._by_scope.get(key)
        if not bucket:
            return []
        return [cm.to_dict() for cm in bucket.memories]

    # ── 写穿透回调 ────────────────────────────────────

    def on_memory_created(self, mem: AgentMemory):
        """记忆创建后同步更新缓存"""
        cm = CachedMemory.from_orm(mem)
        self._memories[cm.id] = cm
        key = self._make_key(cm.scope, cm.context_id)
        bucket = self._by_scope.get(key)
        if bucket:
            self._insert_sorted(bucket.memories, cm)

    def on_memory_updated(self, mem: AgentMemory):
        """记忆更新后同步更新缓存"""
        self._remove_from_bucket(mem.id)
        self.on_memory_created(mem)

    def on_memory_deleted(self, mem_id: str):
        """记忆删除后从缓存移除"""
        self._remove_from_bucket(mem_id)
        self._memories.pop(mem_id, None)

    # ── 刷新 ──────────────────────────────────────────

    def rebuild(self, db: Session, scope: str, context_id: Optional[str] = None):
        """丢弃指定 scope 的缓存，从 DB 重建"""
        key = self._make_key(scope, context_id)
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
        logger.info("MemoryCache 已全量重建")

    # ── 状态查询 ──────────────────────────────────────

    def get_status(self) -> dict:
        """返回缓存状态"""
        loaded_scopes = list(self._by_scope.keys())
        total_mems = len(self._memories)
        per_scope = {k: len(b.memories) for k, b in self._by_scope.items()}
        return {
            "initialized": self._initialized,
            "loaded_scopes": loaded_scopes,
            "total_memories": total_mems,
            "per_scope": per_scope,
        }

    # ── 内部工具方法 ──────────────────────────────────

    @staticmethod
    def _make_key(scope: str, context_id: Optional[str] = None) -> str:
        return f"{scope}:{context_id or ''}"

    def _remove_from_bucket(self, mem_id: str):
        cm = self._memories.get(mem_id)
        if not cm:
            return
        key = self._make_key(cm.scope, cm.context_id)
        bucket = self._by_scope.get(key)
        if bucket:
            bucket.memories = [m for m in bucket.memories if m.id != mem_id]

    @staticmethod
    def _insert_sorted(lst: list[CachedMemory], item: CachedMemory):
        """按 weight 降序插入"""
        for i, m in enumerate(lst):
            if item.cached_weight > m.cached_weight:
                lst.insert(i, item)
                return
        lst.append(item)
