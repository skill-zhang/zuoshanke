"""记忆管理器 — 权重驱动的跨会话记忆系统

核心哲学：
  记忆不是"存了就永远在那"，而是像人一样——
    - 反复提及的会强化（frequency）
    - 最近提过的更容易想起（recency）
    - 你说"记住这个"会加倍权重（explicit_boost）
    - 不重要的会自然淡出（decay）

用法:
    mm = MemoryManager(db)
    mm.add("user", "name", "用户叫张清泉", tags=["个人信息"])
    top = mm.get_top_for_context("天气怎么样")  # 返回 Top-5 相关记忆
"""

import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import AgentMemory
from config.constants import (
    MEMORY_DEFAULT_BASE_WEIGHT as DEFAULT_BASE_WEIGHT,
    MEMORY_DECAY_HALF_LIFE as DECAY_HALF_LIFE,
    MEMORY_MAX_INJECT_COUNT as MAX_INJECT_COUNT,
    MEMORY_REINFORCE_BOOST as REINFORCE_BOOST,
    MEMORY_EXPLICIT_BOOST as EXPLICIT_BOOST,
)

# ── 权重常量 ──
P0_THRESHOLD = 8.0
P1_THRESHOLD = 4.0
P2_THRESHOLD = 2.0

# ── 话题检测关键词（用于当前查询的话题匹配） ──
TOPIC_KEYWORDS = {
    "entertainment": ["电影", "电视剧", "综艺", "小说", "动漫", "音乐",
                      "游戏", "好看", "好玩", "追剧", "推荐", "影视"],
    "food": ["吃", "饭", "菜", "美食", "餐厅", "好吃", "点餐", "外卖"],
    "travel": ["旅游", "旅行", "景点", "出行", "酒店", "机票", "去玩"],
    "work": ["工作", "项目", "任务", "需求", "代码", "开发", "部署", "需求"],
    "tech": ["技术", "编程", "配置", "安装", "调试", "工具", "API"],
    "shopping": ["买", "购物", "价格", "多少钱", "贵"],
    "health": ["健康", "运动", "减肥", "健身", "锻炼", "体检"],
    "education": ["学习", "学", "课程", "教学", "培训", "考试"],
    "habit": ["习惯", "通常", "一般", "经常", "每天", "每次"],
    "personal_info": ["我叫", "我是", "我住", "我的名字"],
    "preference": ["喜欢", "偏爱", "偏好", "爱", "讨厌", "不喜欢"],
    "social": ["朋友", "社交", "聚会", "认识"],
}


def _fmt_time(dt=None):
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt


class MemoryManager:
    """记忆管理器 — CRUD + 权重 + 相关性匹配 + 自动提取"""

    def __init__(self, db: Session):
        self.db = db

    # ── 权重计算 ──────────────────────────────────

    def calc_weight(self, mem: AgentMemory) -> float:
        """计算记忆的实时权重

        v2: is_immortal 跳过 recency 衰减（本体记忆永久保留）

        公式:
            weight = base × recency × frequency × boost

        其中:
            recency   = 2^(-days_since_last_access / half_life)
                        若 is_immortal=True 则 recency=1（不衰减）
            frequency = 1 + log₂(times_accessed + 1)
            boost     = explicit_boost (用户强调倍率)
        """
        # 🆕 v2: 不朽记忆不衰减
        if mem.is_immortal:
            recency = 1.0
        else:
            now = datetime.now(timezone.utc)
            # recency: 按 last_accessed_at 衰减
            last = mem.last_accessed_at or mem.created_at or now
            if isinstance(last, datetime) and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            days_since = max(0, (now - last).total_seconds() / 86400.0)
            recency = math.pow(2, -days_since / DECAY_HALF_LIFE)

        # frequency: 被访问次数越多，权重越高
        frequency = 1 + math.log2(max(mem.times_accessed, 0) + 1)

        # boost
        boost = max(mem.explicit_boost, 1)

        return mem.base_weight * recency * frequency * boost

    def auto_level(self, mem: AgentMemory) -> str:
        """根据权重自动计算等级"""
        w = self.calc_weight(mem)
        if w >= P0_THRESHOLD:
            return "P0"
        if w >= P1_THRESHOLD:
            return "P1"
        if w >= P2_THRESHOLD:
            return "P2"
        return "P3"

    # ── CRUD ──────────────────────────────────────

    def add(self, category: str, key: str, content: str,
            tags: Optional[list] = None,
            base_weight: int = DEFAULT_BASE_WEIGHT,
            source: str = "auto",
            explicit_boost: int = 1,
            scope: str = "zhu",             # 🆕 作用域
            context_id: Optional[str] = None,  # 🆕 场景/频道ID
            is_narrative: bool = False,       # 🆕 v2 叙事型记忆
            ) -> AgentMemory:
        """新建记忆

        Args:
            category: user | agent
            key: 唯一标识，如 'name', 'preference_weather'
            content: 记忆内容
            tags: 标签列表，用于相关性匹配
            base_weight: 基础权重 (2 默认 P2, 4 默认 P1, 8 默认 P0)
            source: auto | llm | user
            explicit_boost: 用户强调倍率
            scope: zhu | scene | channel（2026-05-27: 记忆隔离）
            context_id: 场景ID/频道ID（scope=zhu 时传 None）
            is_narrative: 🆕 v2 标记为叙事型关系记忆

        Returns:
            新建的 AgentMemory 实例
        """
        mem = AgentMemory(
            id=f"mem-{uuid.uuid4().hex[:8]}",
            category=category,
            key=key,
            content=content,
            tags=tags or [],
            base_weight=base_weight,
            explicit_boost=explicit_boost,
            times_accessed=0,
            source=source,
            scope=scope,           # 🆕
            context_id=context_id, # 🆕
            is_narrative=is_narrative,  # 🆕 v2
            is_immortal=(scope == "zhu"),  # 🆕 v2: scope=zhu 自动不朽
        )
        # 初始等级推算
        w = self.calc_weight(mem)
        mem.priority_level = self.auto_level(mem)

        self.db.add(mem)
        self.db.flush()  # 让 SQLAlchemy 赋上 default 值（created_at）
        # 初始等级推算
        w = self.calc_weight(mem)
        mem.priority_level = self.auto_level(mem)
        self.db.commit()
        return mem

    def get(self, key: str) -> Optional[AgentMemory]:
        """按 key 获取记忆"""
        return self.db.query(AgentMemory).filter(AgentMemory.key == key).first()

    def get_by_id(self, mem_id: str) -> Optional[AgentMemory]:
        return self.db.query(AgentMemory).filter(AgentMemory.id == mem_id).first()

    def update(self, key: str, **kwargs) -> Optional[AgentMemory]:
        """更新记忆（自动重新计算等级）"""
        mem = self.get(key)
        if not mem:
            return None
        for k, v in kwargs.items():
            if hasattr(mem, k):
                setattr(mem, k, v)
        # 重新计算等级
        mem.priority_level = self.auto_level(mem)
        self.db.commit()
        return mem

    def delete(self, key: str) -> bool:
        """删除记忆"""
        mem = self.get(key)
        if not mem:
            return False
        self.db.delete(mem)
        self.db.commit()
        return True

    def list_all(self, category: Optional[str] = None,
                 limit: int = 50, offset: int = 0,
                 scope: Optional[str] = None,
                 context_id: Optional[str] = None,
                 scope_only: bool = False) -> list[dict]:
        """列出所有记忆（降序按权重排序）

        Args:
            category: user | agent 筛选
            limit: 最大返回条数
            offset: 分页偏移
            scope: 🆕 作用域过滤（zhu | scene | channel），None=不限制
            context_id: 🆕 场景/频道ID（scope=scene/channel 时有效）
            scope_only: 🆕 仅该作用域，不包含 zhu（记忆视图用）
        """
        q = self.db.query(AgentMemory)
        if category:
            q = q.filter(AgentMemory.category == category)
        # 🆕 作用域过滤
        if scope == "zhu":
            q = q.filter(AgentMemory.scope == "zhu")
        elif scope in ("scene", "channel") and context_id:
            if scope_only:
                q = q.filter(
                    (AgentMemory.scope == scope) & (AgentMemory.context_id == context_id)
                )
            else:
                q = q.filter(
                    (AgentMemory.scope == "zhu") |
                    ((AgentMemory.scope == scope) & (AgentMemory.context_id == context_id))
                )
        mems = q.order_by(AgentMemory.created_at.desc()).all()
        # 计算实时权重并排序
        scored = [(self.calc_weight(m), m) for m in mems]
        scored.sort(key=lambda x: -x[0])
        result = []
        for w, m in scored[offset:offset + limit]:
            d = self._to_dict(m)
            d["weight"] = round(w, 2)
            result.append(d)
        return result

    # ── 话题检测 ────────────────────────────────

    def _detect_topic(self, query: str) -> str:
        """根据用户查询关键词推断当前话题域

        返回匹配得分最高的话题，如果没有匹配则返回 "general"
        """
        if not query:
            return "general"
        tokens = self._tokenize(query)
        query_lower = query.lower()

        scores = {}
        for topic, keywords in TOPIC_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw in query_lower or kw in query:
                    score += 1
            if score > 0:
                scores[topic] = score

        if not scores:
            return "general"

        # 返回得分最高的话题
        best = max(scores, key=scores.get)
        return best

    # ── 相关性匹配（用于 context 注入） ────────────

    def get_top_for_context(self, query: str = "",
                            max_count: int = MAX_INJECT_COUNT,
                            scope: Optional[str] = None,          # 🆕
                            context_id: Optional[str] = None,     # 🆕
                            ) -> list[dict]:
        """获取应注入到上下文的 Top-N 条记忆

        三层筛选:
          0. 作用域过滤（新增）— 按 scope + context_id 隔离
          1. 话题匹配 — 检测当前查询的话题，只取 topic 匹配的记忆
             （P0 级别的个人信息仍然注入）
          2. 按 weight 排序
          3. 取 Top-N

        P0 特殊: 始终保留 1 个名额（但 personal_info 类 P0 只在查询
                 话题相关或没有话题匹配时注入）
        """
        mems = self.db.query(AgentMemory).all()
        if not mems:
            return []

        # 🆕 作用域过滤
        if scope == "zhu":
            mems = [m for m in mems if m.scope == "zhu"]
        elif scope in ("scene", "channel") and context_id:
            mems = [m for m in mems
                    if m.scope == "zhu" or
                       (m.scope == scope and m.context_id == context_id)]
        # scope=None: 返回全部（向后兼容）

        # 检测当前查询的话题
        current_topic = self._detect_topic(query)

        # 计算分数
        query_keywords = set(self._tokenize(query))
        scored = []
        for m in mems:
            w = self.calc_weight(m)

            # 获取记忆的话题（tags[0] 是 topic）
            mem_topic = (m.tags or ["general"])[0]
            # 向后兼容：旧记忆的 tags=["自动提取"] → 视为 general
            if mem_topic not in TOPIC_KEYWORDS:
                mem_topic = "general"

            # ── 话题匹配过滤 ──
            topic_match = False
            if current_topic == "general":
                # 当前没有明确话题 → 只注入 personal_info（身份信息）
                topic_match = (mem_topic == "personal_info")
            else:
                # 有明确话题 → 只注入话题匹配 + personal_info 兜底
                topic_match = (mem_topic == current_topic
                               or mem_topic == "personal_info")

            # 如果是 P0 且未匹配，也保留（P0 是最重要的）
            is_p0 = (m.priority_level == "P0")

            if not topic_match and not is_p0:
                continue  # 既不是当前话题又不是 P0，跳过

            # 相关性加分（保留原有的 tag 匹配和内容匹配）
            relevance = 1.0
            if query_keywords and m.tags:
                tag_match = len(query_keywords & set(m.tags))
                if tag_match > 0:
                    relevance += 0.5 * tag_match
            # 内容关键词匹配
            if query_keywords:
                content_kw = set(self._tokenize(m.content))
                match = len(query_keywords & content_kw)
                if match > 0:
                    relevance += 0.3 * match

            scored.append((w * relevance, w, m))

        if not scored:
            # 没有任何记忆匹配，返回空
            return []

        scored.sort(key=lambda x: -x[0])

        # 选取 Top-N
        selected = []
        for _, _, m in scored:
            if m in selected:
                continue
            selected.append(m)
            if len(selected) >= max_count:
                break

        # 记录访问
        for m in selected:
            m.times_accessed = (m.times_accessed or 0) + 1
            m.last_accessed_at = datetime.now(timezone.utc)
        self.db.commit()

        return [self._to_dict(m) for m in selected]

    # ── 强化与衰减 ────────────────────────────────

    def reinforce(self, key: str, boost: float = REINFORCE_BOOST) -> bool:
        """强化记忆（用户反复提及同一话题时调用）
        boost: 权重乘数，默认 2x
        """
        mem = self.get(key)
        if not mem:
            return False
        mem.explicit_boost = (mem.explicit_boost or 0) + int(boost)
        mem.last_reinforced_at = datetime.now(timezone.utc)
        mem.priority_level = self.auto_level(mem)
        self.db.commit()
        return True

    def mark_explicit(self, key: str) -> bool:
        """标记为"用户明确要求记住"（×3 倍率）"""
        return self.reinforce(key, boost=EXPLICIT_BOOST)

    # ── 🆕 v2: 修正轨迹 ──────────────────────────

    def record_correction(self, key: str, new_content: str, reason: str = "") -> bool:
        """记录修正轨迹 — 用户纠正记忆内容时的标准化操作

        1. 保存旧内容到 correction_trail
        2. 更新为 new_content
        3. explicit_boost += 2（修正即强化）
        4. 自动标记 is_immortal 如果 scope=zhu
        """
        import json
        mem = self.get(key)
        if not mem:
            return False
        trail = json.loads(mem.correction_trail or "[]")
        trail.append({
            "old": (mem.content or "")[:300],
            "new": (new_content or "")[:300],
            "reason": reason,
            "timestamp": str(datetime.now(timezone.utc)),
        })
        mem.correction_trail = json.dumps(trail, ensure_ascii=False)
        mem.content = new_content
        mem.explicit_boost = (mem.explicit_boost or 0) + 2  # 修正即强化
        # 本体记忆自动不朽
        if mem.scope == "zhu" and not mem.is_immortal:
            mem.is_immortal = True
        mem.priority_level = self.auto_level(mem)
        self.db.commit()
        return True

    def prune(self, max_count: int = 500):
        """淘汰低权重记忆 — 超过 max_count 时清理 P3
        🆕 v2: 跳过 is_immortal 记忆（本体记忆永不清理）
        """
        mems = self.db.query(AgentMemory).all()
        # 排除 immortal 记忆后再判断是否超量
        mortal_count = sum(1 for m in mems if not m.is_immortal)
        if mortal_count <= max_count:
            return 0

        # 只排序 mortal 记忆，immortal 不动
        mortal = [(self.calc_weight(m), m) for m in mems if not m.is_immortal]
        mortal.sort(key=lambda x: x[0])  # 升序，最差放前面
        to_delete = []
        kept_count = 0
        for w, m in mortal:
            if kept_count >= max_count:
                to_delete.append(m.id)
            else:
                kept_count += 1

        deleted = 0
        for mid in to_delete:
            self.db.query(AgentMemory).filter(AgentMemory.id == mid).delete()
            deleted += 1
        if deleted:
            self.db.commit()
        return deleted

    # ── 自动对话提取（会话后沉淀） ─────────────────

    MEMORY_SIGNALS_REMEMBER = ["记住", "别忘了", "牢记", "很重要", "非常重要",
                                "以后都这样", "记住了", "记牢"]
    MEMORY_SIGNALS_CORRECTION = ["不是", "不对", "错了", "不是这样", "纠正",
                                  "更正", "我说的是"]
    MEMORY_SIGNALS_REPEAT = ["再说一次", "再说一遍", "我刚刚说的", "我刚说过",
                              "如我所言", "如我之前所说"]

    def auto_extract_from_conversation(self, messages: list[dict]) -> list[dict]:
        """从对话中自动提取记忆

        扫描本回合所有 user/ai 消息，检测三种模式：

        1. 显式标记（"记住"、"很重要"）→ 创建/强化记忆，×3 boost
        2. 用户纠正（"不是A是B"）→ 更新已存记忆
        3. 重复主题（同一话题出现 3 次以上）→ 强化记忆，×2 boost

        Args:
            messages: 本回合的消息列表 [{"role": "user"/"ai", "content": "..."}]

        Returns:
            提取摘要 [{"action": "create"|"reinforce"|"update",
                       "key": "...", "content": "...", "boost": 2.0}]
        """
        results = []

        # 只分析用户消息
        user_msgs = [m for m in messages if m.get("role") in ("user", "human")]
        all_text = "\n".join(m.get("content", "") for m in user_msgs)
        if not all_text.strip():
            return results

        # ── 模式 1：显式 "记住这个" ──
        for signal in self.MEMORY_SIGNALS_REMEMBER:
            if signal in all_text:
                # 尝试从该句提取 key 和 content
                # 在"记住"前后找关键词——"我叫XX"、"我喜欢XX"、"我需要XX"
                extracted = self._extract_fact(all_text)
                if extracted:
                    key, content = extracted
                    existing = self.get(key)
                    if existing:
                        self.mark_explicit(key)
                        self.update(key, content=content)
                        results.append({"action": "reinforce_pin",
                                        "key": key, "content": content, "boost": 3.0})
                    else:
                        self.add("user", key, content, tags=["自动提取"],
                                 source="llm", base_weight=4)
                        self.mark_explicit(key)
                        results.append({"action": "create",
                                        "key": key, "content": content, "boost": 3.0})

        # ── 模式 2：用户纠正 ──
        for signal in self.MEMORY_SIGNALS_CORRECTION:
            if signal in all_text:
                # 找"不是X是Y"模式
                import re
                patterns = [
                    r"不是(.+?)(?:[,，就是]+)(.+?)(?:\n|$)",
                    r"不是(.+?)(?:[,，]是)(.+?)(?:\n|$)",
                    r"错了[,，]应该是(.+?)(?:\n|$)",
                    r"更正[：:](.+?)(?:\n|$)",
                ]
                for pat in patterns:
                    match = re.search(pat, all_text)
                    if match:
                        corrected = match.group(1).strip() if match.lastindex == 2 else ""
                        correct_value = match.group(2).strip() if match.lastindex == 2 else match.group(1).strip()
                        # 尝试匹配已存在的记忆
                        for existing_key in ["name", "city", "preference_*"]:
                            mem = self.get(existing_key)
                            if mem and mem.key not in ("name", "city"):
                                continue
                        # 如果没有精确匹配，以纠正内容为 key 创建一条
                        key = f"corrected_{correct_value[:8]}"
                        self.add("user", key, f"纠正：{corrected} → {correct_value}",
                                 tags=["纠正"], source="auto", base_weight=3)
                        results.append({"action": "update",
                                        "key": key, "content": correct_value, "boost": 2.0})
                        break
                break  # 只处理第一个纠正信号

        # ── 模式 3：重复主题检测 ──
        # 统计关键词频次
        all_tokens = self._tokenize(all_text)
        from collections import Counter
        freq = Counter(all_tokens)
        # 出现 3 次以上的长词（≥2字）可能是主题
        common = [(word, count) for word, count in freq.most_common(20)
                  if count >= 3 and len(word) >= 2]
        for word, count in common:
            # 检查是否已存在相关记忆
            existing = self.db.query(AgentMemory).filter(
                AgentMemory.tags.contains(word) |
                AgentMemory.content.contains(word)
            ).first()
            if existing:
                # 已有记忆 → 强化
                self.reinforce(existing.key)
                results.append({"action": "reinforce",
                                "key": existing.key,
                                "content": f"（重复提及「{word}」{count}次）",
                                "boost": 2.0})

        return results

    def _extract_fact(self, text: str) -> Optional[tuple[str, str]]:
        """尝试从文本中提取出可记忆的事实

        返回 (key, content) 或 None

        识别的语句模式：
          - "我叫/是/叫 XX"
          - "我喜欢/爱/偏爱 XX"
          - "我在/住/居住在 XX"
          - "我的 XX 是 YY"
          - "我习惯/通常/一般/总是 XX"
        """
        import re
        patterns = [
            # 姓名
            (r"(?:我叫|我是|我的名字叫|名字叫|英文名|英文名叫|英文名字叫)\s*(.+?)(?:[,，。！\!\n]|$)",
             "name", lambda m: f"用户名叫{m.group(1).strip()}"),
            # 居住地
            (r"(?:我[住在]|我居住在|我家在|居住在|家住)\s*(.+?)(?:[,，。！\!\n]|$)",
             "city", lambda m: f"用户在{m.group(1).strip()}"),
            # 偏好
            (r"(?:我喜欢|我爱|我偏爱|我倾向于|偏好|偏爱)\s*(.+?)(?:[,，。！\!\n]|$)",
             "preference", lambda m: f"用户喜欢{m.group(1).strip()}"),
            # 习惯
            (r"(?:我(?:的)?(?:习惯|通常|一般|总是|经常)\s*(.+?)(?:[,，。！\!\n]|$))",
             "habit", lambda m: f"用户习惯{m.group(1).strip()}"),
            # 我的 X 是 Y
            (r"我的(.+?)是\s*(.+?)(?:[,，。！\!\n]|$)",
             None, lambda m: (f"my_{m.group(1).strip()}", f"用户的{m.group(1).strip()}是{m.group(2).strip()}")),
        ]

        for pat, default_key, content_fn in patterns:
            match = re.search(pat, text)
            if match:
                result = content_fn(match)
                if isinstance(result, tuple):
                    return result  # (key, content) 完整返回
                key = default_key
                content = result
                return (key, content)

        return None

    # ── 工具函数 ──────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """分词（支持中英文混排）"""
        if not text:
            return []
        import re
        # 中文单字、英文单词、数字
        tokens = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', text)
        return [t for t in tokens if len(t) >= 1]

    def find_similar_content(self, content: str,
                              scope: Optional[str] = None,
                              context_id: Optional[str] = None,
                              threshold: float = 0.50) -> Optional[AgentMemory]:
        """查找内容相似的已有记忆 — Jaccard 相似度 + 作用域感知

        Args:
            content: 要查找的内容
            scope: 限定作用域（None=不限制）
            context_id: 场景/频道ID
            threshold: Jaccard 相似度阈值（0.0~1.0），默认 0.50

        Returns:
            最相似的记忆（若无则 None）
        """
        import re
        content_tokens = set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', content))
        if not content_tokens:
            return None

        query = self.db.query(AgentMemory)
        if scope:
            query = query.filter(AgentMemory.scope == scope)
            if context_id:
                query = query.filter(AgentMemory.context_id == context_id)
        all_mems = query.all()

        best_match = None
        best_score = 0.0
        for mem in all_mems:
            mem_tokens = set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', mem.content))
            if not mem_tokens:
                continue
            intersection = content_tokens & mem_tokens
            union = content_tokens | mem_tokens
            score = len(intersection) / len(union)
            if score > best_score:
                best_score = score
                best_match = mem

        if best_score >= threshold:
            return best_match
        return None

    def _to_dict(self, m: AgentMemory) -> dict:
        return {
            "id": m.id,
            "category": m.category,
            "key": m.key,
            "content": m.content,
            "tags": m.tags,
            "priority_level": m.priority_level,
            "base_weight": m.base_weight,
            "explicit_boost": m.explicit_boost,
            "times_accessed": m.times_accessed,
            "source": m.source,
            "scope": m.scope,
            "context_id": m.context_id,
            "is_narrative": m.is_narrative,         # 🆕 v2
            "is_immortal": m.is_immortal,            # 🆕 v2
            "correction_trail": json.loads(m.correction_trail or "[]"),  # 🆕 v2
            "last_accessed_at": m.last_accessed_at.isoformat() if m.last_accessed_at else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
