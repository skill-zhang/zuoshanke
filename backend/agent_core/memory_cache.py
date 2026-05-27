"""内存级记忆缓存层 — 按需加载 + Write-Through + Scope 隔离

本体（zhu）永不离线，分身（scene/channel）按需加载。
缓存全量存储，不做话题预过滤，context composer 自行截取注入。
"""

import math
import re
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

# 🆕 v1.5 关键词提取停用词集
STOPWORDS = frozenset({
    '的', '了', '是', '在', '有', '和', '也', '就', '不', '人',
    '都', '一', '个', '上', '很', '到', '说', '要', '去', '你',
    '我', '他', '她', '它', '们', '这', '那', '么', '会', '可',
    '以', '能', '让', '把', '被', '从', '与', '而', '或', '但',
    '所', '为', '对', '等', '之', '中', '还', '没', '又', '再',
    '已', '经', '做', '用', '给', '跟', '比', '于', '向',
    'the', 'a', 'an', 'is', 'are', 'was', 'were',
    'not', 'but', 'for', 'with', 'that', 'this', 'it',
    'and', 'or', 'in', 'on', 'to', 'of', 'be', 'we', 'you',
})


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
    created_at: Optional[datetime]
    scope: str
    context_id: Optional[str]
    is_narrative: bool
    is_immortal: bool
    priority_level: str
    cached_weight: float
    # 🆕 v1.5
    is_core: bool
    compressed: Optional[str]
    keywords: list
    last_injected_at: Optional[datetime]

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
            created_at=mem.created_at,
            scope=mem.scope,
            context_id=mem.context_id,
            is_narrative=mem.is_narrative,
            is_immortal=mem.is_immortal,
            priority_level=mem.priority_level,
            cached_weight=w,
            # 🆕 v1.5
            is_core=mem.is_core or False,
            compressed=mem.compressed,
            keywords=mem.keywords or [],
            last_injected_at=mem.last_injected_at,
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
            # 🆕 v1.5
            "is_core": self.is_core,
            "compressed": self.compressed,
            "keywords": self.keywords,
            "last_injected_at": self.last_injected_at.isoformat() if self.last_injected_at else None,
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
        """返回该 scope 的记忆，按 query 相关性 + weight 综合排序。

        无 query 时按 weight 降序返回全部。
        有 query 时计算关键词重叠分（与 weight 加权），截取前 10 条。
        """
        key = self._make_key(scope, context_id)
        bucket = self._by_scope.get(key)
        if not bucket:
            return []

        if query and bucket.memories:
            # 🆕 Schema v1.0: 语义匹配 — 关键词重叠 + weight 加权排序
            query_words = set(query.lower().split())
            def relevance_score(mem: CachedMemory) -> float:
                content = (mem.key + " " + mem.content).lower()
                mem_words = set(content.split())
                overlap = len(query_words & mem_words)
                # 重叠分 0-1（归一化），组合到 weight 上
                overlap_ratio = overlap / max(len(query_words), 1)
                return mem.cached_weight * (1.0 + overlap_ratio * 2.0)

            scored = sorted(bucket.memories, key=relevance_score, reverse=True)
            return [m.to_dict() for m in scored[:10]]

        return [m.to_dict() for m in bucket.memories]

    # ── 🆕 v1.5 Core Tier ────────────────────────

    def get_core_memories(self, db: Session, max_count: int = 5) -> list[dict]:
        """获取 Core Tier 记忆（is_core=True），按 base_weight 降序

        Core Tier 定义了坐山客「是谁」——设计哲学、铁律、本体 Identity。
        使用 compressed 摘要（如有），原始体积受 800 字符硬预算约束。

        Args:
            db: 数据库会话（fallback 使用）
            max_count: 最多返回条数（默认 5）

        Returns:
            记忆 dict 列表，按 base_weight 降序
        """
        # 优先从缓存读取
        bucket = self._by_scope.get("zhu:")
        if bucket:
            core = [m for m in bucket.memories if m.is_core]
            core.sort(key=lambda x: -x.cached_weight)
            return [m.to_dict() for m in core[:max_count]]

        # 缓存未加载时 fallback
        rows = db.query(AgentMemory).filter(
            AgentMemory.scope == "zhu",
            AgentMemory.is_core == True,
        ).order_by(AgentMemory.base_weight.desc()).limit(max_count).all()

        result = []
        for mem in rows:
            w = calc_weight(
                base_weight=mem.base_weight,
                is_immortal=mem.is_immortal,
                times_accessed=mem.times_accessed or 0,
                explicit_boost=mem.explicit_boost or 1,
                last_accessed_at=mem.last_accessed_at,
                created_at=mem.created_at,
            )
            result.append({
                "id": mem.id,
                "key": mem.key,
                "content": mem.content,
                "compressed": mem.compressed,
                "scope": mem.scope,
                "is_core": True,
                "priority_level": auto_level(w),
                "is_narrative": mem.is_narrative,
                "cached_weight": w,
            })
        return result

    # ── 🆕 v1.5 Context Tier ─────────────────────

    def get_for_context_injection(
        self,
        db: Session,
        scope: str = "zhu",
        query: str = "",
        max_chars: int = 3000,
        max_items: int = 15,
        exclude_keys: Optional[list[str]] = None,
    ) -> list[dict]:
        """本体/分身记忆的选择性注入 —— 三因子排序 + 保底机制

        召回算法：
          1. 关键词重叠（tags + keywords + content） 权重 0.4
          2. 时效性（最近访问时间）                    权重 0.3
          3. 记忆自身重要性（base_weight + boost）    权重 0.3

        Args:
            db: 数据库会话（用于 batch update last_injected_at）
            scope: 作用域（默认 "zhu"）
            query: 用户当前查询，用于关键词匹配
            max_chars: Context Tier 总字符上限（含格式开销，默认 3000）
            max_items: 最多注入条数（默认 15）
            exclude_keys: 已在 Core Tier 中的 key 列表，避免重复

        Returns:
            排序后的记忆 dict 列表
        """
        # ── Step 1: 从缓存取非核心记忆 ──
        bucket = self._by_scope.get(f"{scope}:")
        if not bucket:
            return []

        candidates = [m for m in bucket.memories if not m.is_core]
        if not candidates:
            return []

        query_kw = self._extract_query_keywords(query)
        exclude = set(exclude_keys or [])

        # ── Step 2: 三因子打分 ──
        scored: list[tuple[float, CachedMemory]] = []
        for mem in candidates:
            score = self._calc_injection_score(mem, query_kw)
            if score >= 0.3:  # min_score 阈值
                scored.append((score, mem))

        # 按分数降序，同分按创建时间降序
        scored.sort(key=lambda x: (-x[0], -(x[1].last_accessed_at or x[1].cached_weight)))

        # ── Step 3: 保底机制 —— 最近 3 条（按 updated_at/created_at） ──
        safety_net = sorted(
            [m for m in candidates if m.key not in exclude],
            key=lambda m: m.last_accessed_at or m.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:3]

        safety_keys = {m.key for m in safety_net}

        # ── Step 4: 合并 —— 高分优先，保底兜底 ──
        result: list[CachedMemory] = []
        seen_keys: set[str] = set(exclude)

        # 先取高分
        for _, mem in scored:
            if mem.key in seen_keys:
                continue
            if len(result) >= max_items:
                break
            result.append(mem)
            seen_keys.add(mem.key)

        # 补充保底（不在高分列表中的）
        for mem in safety_net:
            if mem.key in seen_keys:
                continue
            if len(result) >= max_items:
                break
            result.append(mem)
            seen_keys.add(mem.key)

        # ── Step 5: 字符预算检查（至少保留 3 条） ──
        total_chars = 0
        for mem in result:
            total_chars += len(f"- {mem.key}: {mem.content[:150]}")
        while total_chars > max_chars and len(result) > 3:
            removed = result.pop()
            total_chars -= len(f"- {removed.key}: {removed.content[:150]}")

        # ── Step 6: 更新 last_injected_at ──
        injected_keys = [m.key for m in result]
        self._batch_update_injected(db, injected_keys)

        return [m.to_dict() for m in result]

    # ── 🆕 v1.5 注入评分 ────────────────────────

    @staticmethod
    def _calc_injection_score(mem: CachedMemory, query_kw: set[str]) -> float:
        """三因子加权排序

        因子 1：关键词重叠（tags + keywords + content 前 50 字） × 0.4
        因子 2：时效性（最近访问时间）                           × 0.3
        因子 3：记忆重要性（base_weight + explicit_boost）        × 0.3
        """
        score = 0.0

        # —— 因子 1：关键词重叠 0.4 ——
        mem_kw = set(mem.keywords or [])
        # tags 也作为关键词
        if mem.tags:
            mem_kw.update(t.lower() for t in mem.tags if isinstance(t, str))
        # content 前 50 字提取关键词
        content_head = mem.content[:50]
        content_kw = set(re.findall(r'[\u4e00-\u9fff\w]+', content_head)) - STOPWORDS
        mem_kw.update(content_kw)

        if query_kw and mem_kw:
            overlap = len(query_kw & mem_kw)
            score += (overlap / max(len(query_kw), 1)) * 0.4
        elif not query_kw:
            # 无查询时给中性分
            score += 0.2

        # —— 因子 2：时效性 0.3 ——
        if mem.last_accessed_at:
            now = datetime.now(timezone.utc)
            last = mem.last_accessed_at
            if isinstance(last, datetime) and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            days = max(0, (now - last).total_seconds() / 86400.0)
            score += max(0.0, 1.0 - days / 90.0) * 0.3  # 90 天内线性衰减
        elif mem.created_at:
            now = datetime.now(timezone.utc)
            created = mem.created_at
            if isinstance(created, datetime) and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            days = max(0, (now - created).total_seconds() / 86400.0)
            score += max(0.0, 1.0 - days / 90.0) * 0.3
        else:
            score += 0.1  # 无时间信息的默认分

        # —— 因子 3：重要性 0.3 ——
        importance = (mem.base_weight + (mem.explicit_boost or 0)) / 10.0
        score += min(importance, 1.0) * 0.3

        return score

    # ── 🆕 v1.5 关键词提取工具 ──────────────────

    @staticmethod
    def _extract_query_keywords(query: str) -> set[str]:
        """从用户查询提取关键词集合

        提取中文字符、英文单词，去掉停用词。
        """
        if not query:
            return set()
        words = set(re.findall(r'[\u4e00-\u9fff\w]+', query))
        return words - STOPWORDS

    # ── 🆕 v1.5 批量更新注入时间 ───────────────

    @staticmethod
    def _batch_update_injected(db: Session, keys: list[str]):
        """批量更新 last_injected_at（一次 commit）"""
        if not keys or db is None:
            return
        try:
            now = datetime.now(timezone.utc)
            db.query(AgentMemory).filter(
                AgentMemory.key.in_(keys)
            ).update(
                {"last_injected_at": now},
                synchronize_session=False,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("批量更新 last_injected_at 失败（不影响注入流程）")

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
