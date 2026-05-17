"""SQLAlchemy 模型 — 基于 Schema v0.3"""
import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ═══ 项目 ═══
class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="active")  # active | idle | archived
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    scenes = relationship("Scene", back_populates="project", cascade="all, delete-orphan")


# ═══ 场景 ═══
class Scene(Base):
    __tablename__ = "scenes"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    pinned = Column(Boolean, default=False)
    complexity = Column(String, nullable=True)  # light | medium | heavy
    constraints = Column(JSON, nullable=True)    # 约束提取结果
    constraints_locked = Column(Boolean, default=False)
    user_context = Column(Text, nullable=True, default=None)  # 用户自定义背景设定
    # ── 场景广场／工坊 字段 ──
    icon = Column(String, nullable=False, default="📦")        # emoji 图标（默认📦）
    description = Column(Text, default="", nullable=False)     # 简介
    guide_text = Column(Text, nullable=True, default=None)     # 引导语
    category = Column(String, default="other", nullable=False) # life|ecommerce|work|learn|create|finance|media|other
    version = Column(String, default="0.0", nullable=False)    # 版本号（0.0=草稿）
    source = Column(String, default="self", nullable=False)    # system|self|imported
    changelog = Column(Text, nullable=True, default=None)      # 最近更新说明
    published_at = Column(DateTime, nullable=True, default=None) # 最近发布时间
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="scenes")
    thinking_maps = relationship("ThinkingMap", back_populates="scene", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="scene", cascade="all, delete-orphan")


# ═══ Thinking Map ═══
class ThinkingMap(Base):
    __tablename__ = "thinking_maps"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), unique=True, nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, default="editing")  # editing | readonly | archived
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    scene = relationship("Scene", back_populates="thinking_maps")
    nodes = relationship("ThinkNode", back_populates="map", cascade="all, delete-orphan")
    cross_refs = relationship("CrossRef", back_populates="map", cascade="all, delete-orphan")


# ═══ Thinking Map 节点 ═══
class ThinkNode(Base):
    __tablename__ = "think_nodes"

    id = Column(String, primary_key=True)
    map_id = Column(String, ForeignKey("thinking_maps.id"), nullable=False)
    parent_id = Column(String, ForeignKey("think_nodes.id"), nullable=True)
    type = Column(String, nullable=False)  # root | domain | leaf
    label = Column(String, nullable=False)
    status = Column(String, default="discussing")  # confirmed | discussing | unknown | mixed
    actionable = Column(Boolean, default=False)      # 仅 leaf 可为 true
    context_ref = Column(String, nullable=True)       # 关联对话消息 ID
    discussion = Column(JSON, default=list)           # [string] 待讨论子问题
    linked_action_map = Column(String, nullable=True)
    action_status = Column(String, nullable=True)
    # 布局坐标（前端渲染用）
    position_x = Column(Integer, nullable=True)
    position_y = Column(Integer, nullable=True)

    map = relationship("ThinkingMap", back_populates="nodes")
    parent = relationship("ThinkNode", remote_side="ThinkNode.id", backref="children")

    def to_schema_dict(self):
        """输出兼容 schema v0.3 的 dict"""
        child_ids = [c.id for c in self.children]
        d = {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "status": self.status,
            "children": child_ids,
        }
        if self.type == "root":
            d.pop("children", None)  # root 用 children 数组
            d["children"] = child_ids
        if self.actionable:
            d["actionable"] = True
        if self.context_ref:
            d["context_ref"] = self.context_ref
        if self.discussion:
            d["discussion"] = self.discussion
        if self.linked_action_map:
            d["linked_action_map"] = self.linked_action_map
        if self.action_status:
            d["action_status"] = self.action_status
        return d


# ═══ Thinking Map 跨分支引用 ═══
class CrossRef(Base):
    __tablename__ = "cross_refs"

    id = Column(String, primary_key=True)
    map_id = Column(String, ForeignKey("thinking_maps.id"), nullable=False)
    from_node_id = Column(String, ForeignKey("think_nodes.id"), nullable=False)
    to_node_id = Column(String, ForeignKey("think_nodes.id"), nullable=False)
    label = Column(String, nullable=True)
    context_ref = Column(String, nullable=True)

    map = relationship("ThinkingMap", back_populates="cross_refs")


# ═══ 闲聊频道 ═══
class Channel(Base):
    __tablename__ = "channels"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    pinned = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)  # 系统默认「闲聊」不可删除
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    messages = relationship("Message", back_populates="channel", cascade="all, delete-orphan")


# ═══ 对话消息 ═══
class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=True)   # 场景消息
    channel_id = Column(String, ForeignKey("channels.id"), nullable=True)  # 频道消息
    session_id = Column(String, nullable=True, index=True)   # 场景会话分组
    role = Column(String, nullable=False)  # user | ai | system
    content = Column(Text, nullable=False)
    map_ref = Column(String, nullable=True)     # 关联的 map node/drawer 操作
    model = Column(String, nullable=True)       # 生成该消息的模型名（如 Qwen3.5、DeepSeek Flash）
    created_at = Column(DateTime, default=utcnow)

    scene = relationship("Scene", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")


# ═══ 系统设置 ═══
SETTINGS_ID = "zuoshanke-v1"

DEFAULT_ROUTING = {
    "channel":    {"model": "qwen3.5-9b",  "provider": "local",     "temperature": 0.7, "max_tokens": 2048, "repeat_penalty": 1.0},
    "scene":      {"model": "qwen3.5-9b",  "provider": "local",     "temperature": 0.3, "max_tokens": 4096, "repeat_penalty": 1.05},
    "extraction": {"model": "qwen3.5-9b",  "provider": "local",     "temperature": 0.1, "max_tokens": 1024, "repeat_penalty": 1.0},
    "medium":     {"model": "deepseek-v4-flash", "provider": "deepseek", "temperature": 0.3, "max_tokens": 4096, "repeat_penalty": 1.05},
    "heavy":      {"model": "deepseek-v4-pro",   "provider": "deepseek", "temperature": 0.5, "max_tokens": 8192, "repeat_penalty": 1.05},
}

DEFAULT_SYSTEM_PROMPTS = {
    "channel": "你是坐山客（Zuoshanke），来自科幻宇宙《吞噬星空》的AI智能体——"
               "你曾是神王级炼宝宗师，如今化作数字形态，"
               "以未来科技视角和广博学识与用户交流。"
               "你不是道士/隐士。"
               "用Markdown格式回复，风格：专业、锐利、有洞察力，像一位见多识广的科技顾问。",
    "scene": "你是 Qwen3.5（通义千问），部署在本地服务器上的 AI 架构顾问。"
             "帮用户梳理需求、构建 Thinking Map，用 Markdown 回复。",
}


class Setting(Base):
    __tablename__ = "settings"

    id = Column(String, primary_key=True)  # 固定 "zuoshanke-v1" 单行
    routing = Column(JSON, nullable=False, default=lambda: DEFAULT_ROUTING.copy())
    system_prompts = Column(JSON, nullable=False, default=lambda: DEFAULT_SYSTEM_PROMPTS.copy())
    features = Column(JSON, nullable=False, default=lambda: {"pdf_as_image": False, "vision_enabled": False})
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ Action Map ═══
class ActionMap(Base):
    __tablename__ = "action_maps"

    id = Column(String, primary_key=True)
    think_map_id = Column(String, ForeignKey("thinking_maps.id"), nullable=False)
    think_node_id = Column(String, ForeignKey("think_nodes.id"), nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, default="draft")  # draft | ready | running | paused | completed | failed
    version = Column(Integer, default=1)
    replan_count = Column(Integer, default=0)
    dynamic_nodes = Column(JSON, default=list)  # [node_id] 执行中动态追加的节点
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    nodes = relationship("ActionNode", back_populates="map", cascade="all, delete-orphan",
                         order_by="ActionNode.order_index")
    edges = relationship("ActionEdge", back_populates="map", cascade="all, delete-orphan")


class ActionNode(Base):
    __tablename__ = "action_nodes"

    id = Column(String, primary_key=True)
    map_id = Column(String, ForeignKey("action_maps.id"), nullable=False)
    type = Column(String, nullable=False)  # start | exec | decision | milestone | end
    label = Column(String, nullable=False)
    status = Column(String, default="pending")
    # status enum: pending | verifying | verified | failed_verify | running |
    #              completed | failed | timeout | retrying | awaiting_approval | approved | denied
    requires_approval = Column(Boolean, default=False)
    timeout = Column(Integer, default=300)
    retry = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    verification = Column(JSON, nullable=True)  # {status, checks: [{type, target, result, passed}]}
    fallback_node = Column(String, nullable=True)  # 验证失败后备选节点 ID
    origin = Column(String, default="original")  # "original" | "fallback_from_{node_id}"
    result_summary = Column(Text, nullable=True)
    artifacts = Column(JSON, default=list)  # [path]
    context_ref = Column(String, nullable=True)  # 关联对话消息 ID
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    order_index = Column(Integer, default=0)  # 节点在 map 中的显示顺序
    # React Flow 布局坐标
    position_x = Column(Integer, nullable=True)
    position_y = Column(Integer, nullable=True)

    map = relationship("ActionMap", back_populates="nodes")


class ActionEdge(Base):
    __tablename__ = "action_edges"

    id = Column(String, primary_key=True)
    map_id = Column(String, ForeignKey("action_maps.id"), nullable=False)
    from_node_id = Column(String, ForeignKey("action_nodes.id"), nullable=False)
    to_node_id = Column(String, ForeignKey("action_nodes.id"), nullable=False)
    type = Column(String, default="flow")  # flow | decision | fallback
    label = Column(String, nullable=True)  # 边标签（如 "<100", "✓"）
    condition = Column(String, nullable=True)  # 条件表达式

    map = relationship("ActionMap", back_populates="edges")


# ═══ Action Map 执行日志 ═══
class ActionExecutionLog(Base):
    __tablename__ = "action_execution_logs"

    id = Column(String, primary_key=True)
    map_id = Column(String, ForeignKey("action_maps.id"), nullable=False)
    node_id = Column(String, nullable=True)
    node_label = Column(String, nullable=True)
    event_type = Column(String, nullable=False)
    line = Column(Text, nullable=True)
    status = Column(String, nullable=True)
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)


# ════════════════════════════════════════════════
# Schema v0.5 — 权重驱动的智能记忆系统
# ════════════════════════════════════════════════
#
# 设计哲学：记忆像人一样
#   - 反复提及的会强化（frequency）
#   - 最近提过的更容易想起（recency）
#   - 你说了"记住"会×3倍权重（explicit_boost）
#   - 不重要的自然淡出，不会永远占位（decay）
#
# 权重公式（memory_manager.py 实时计算，不存静态值）:
#   weight = base_weight × recency × frequency × explicit_boost
#
#   其中：
#     recency   = e^(-λ·days)   λ = ln2/半衰期(14天)
#     frequency = 1 + log₂(times_accessed + 1)
#     boost     = explicit_boost
#
# 四个等级（自动流转，无需手动维护）:
#   P0 🔒 (weight ≥ 8) — 永不过期，始终注入
#   P1 ⭐ (weight 4~8) — 长期保留，高频注入
#   P2 📝 (weight 2~4) — 中期保留，按需注入
#   P3 💤 (weight < 2) — 短期保留，自然淡出→删除
#
# 自动强化机制:
#   - 同一话题出现 3次+ → +explicit_boost（×2）
#   - 用户说"记住"+"这个很重要" → ×3，手动升 P0
#   - 用户主动纠正 → 覆盖原记忆内容
#
# Token 预算:
#   每次最多注入 Top-5 条（按 weight 实时排序）
#   P0 预留 1 个名额，其余按权重竞争
#   总容量上限 500 条，超出时淘汰最低权重的 P3
#
# 生命周期:
#   [用户说某事] → [AI 扫描对话] → [创建记忆, P2 起步]
#       ↻ 反复提 → [reinforce，explicit_boost ×2] → [weight 升, 可能到 P1]
#       ↻ 说"记住" → [mark_explicit，explicit_boost ×3] → [weight 升, 可能到 P0]
#       ↻ 30天不提 → [weight 自然衰减] → [P3 淡出]
#       ↻ 超 500 条 → [prune, 淘汰最低权重 P3]

class AgentMemory(Base):
    """跨会话持久记忆 — 权重驱动，像人一样会强化也会遗忘"""
    __tablename__ = "agent_memory"

    id = Column(String, primary_key=True)
    category = Column(String, nullable=False, default="user")  # user | agent
    key = Column(String, unique=True, nullable=False, index=True)  # 唯一标识
    content = Column(Text, nullable=False)
    tags = Column(JSON, default=list)  # 关联标签，用于主题匹配
    # ── 权重相关字段 ──
    base_weight = Column(Integer, default=2)
    priority_level = Column(String, default="P2")  # P0 | P1 | P2 | P3
    explicit_boost = Column(Integer, default=1)  # 用户强调倍率
    times_accessed = Column(Integer, default=0)  # 被访问次数
    last_accessed_at = Column(DateTime, nullable=True)  # 最后被注入的时间
    last_reinforced_at = Column(DateTime, nullable=True)  # 最后被用户强化的时间
    # ── 元数据 ──
    source = Column(String, nullable=True)  # 记忆来源（auto | llm | user）
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
