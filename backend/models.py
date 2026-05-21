"""SQLAlchemy 模型 — 基于 Schema v0.3"""
import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON, UniqueConstraint, Float
)
from sqlalchemy.orm import relationship
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ═══ 场景 ═══
class Scene(Base):
    __tablename__ = "scenes"

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, default="")
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

    # ── Schema v0.81: 收敛／发散参数 ──
    converge_threshold = Column(Float, default=2.0)         # 收敛阈值（叶子/分支比）
    converge_enabled = Column(Boolean, default=True)        # 自动收敛开关
    diverge_min_rounds = Column(Integer, default=2)         # 发散所需最少 AI 回复轮数

    # ── Schema v1.0: 场景扩展配置 ──
    scene_config = Column(JSON, default=dict)                # {work_output_window_size, document_deps, ...}


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
    status = Column(String, default="discussing")  # confirmed | discussing | unknown | mixed | refined | discarded
    actionable = Column(Boolean, default=False)      # 仅 leaf 可为 true
    context_ref = Column(String, nullable=True)       # 关联对话消息 ID
    discussion = Column(JSON, default=list)           # [string] 待讨论子问题
    linked_action_map = Column(String, nullable=True)
    action_status = Column(String, nullable=True)

    # === Agent Loop v1 新字段 ===
    converged_from = Column(JSON, default=list)       # [string] 被合并的原始节点名列表
    created_by = Column(String, default="brainstorm") # brainstorm | reflect | manual
    priority = Column(Integer, nullable=True)         # 1-4 (P1-P4)
    queue_order = Column(Integer, nullable=True)      # Priority Queue 排序位置
    depends_on = Column(JSON, default=list)           # [string] 依赖的节点 ID 列表（DAG）
    execution_result = Column(Text, nullable=True)    # 执行结果摘要（Reflect 注入）

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
            "converged_from": self.converged_from or [],
            "created_by": self.created_by or "brainstorm",
            "depends_on": self.depends_on or [],
        }
        if self.priority is not None:
            d["priority"] = self.priority
        if self.queue_order is not None:
            d["queue_order"] = self.queue_order
        if self.execution_result:
            d["execution_result"] = self.execution_result
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
    display = Column(Boolean, default=True)     # Schema v0.7: False=系统内部记录,前端不渲染
    priority = Column(String(10), default="normal")  # Schema v1.0: high | normal | low
    created_at = Column(DateTime, default=utcnow)

    scene = relationship("Scene", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")


# ═══ 系统设置 ═══
SETTINGS_ID = "zuoshanke-v1"

DEFAULT_ROUTING = {
    "channel":    {"model": "deepseek-v4-flash", "provider": "deepseek", "temperature": 0.7, "max_tokens": 8192,  "context_length": 1048576, "repeat_penalty": 1.05},
    "scene":      {"model": "deepseek-v4-flash", "provider": "deepseek", "temperature": 0.3, "max_tokens": 16384, "context_length": 1048576, "repeat_penalty": 1.05},
    "extraction": {"model": "deepseek-v4-flash", "provider": "deepseek", "temperature": 0.1, "max_tokens": 2048,  "context_length": 1048576, "repeat_penalty": 1.05},
    "medium":     {"model": "deepseek-v4-flash", "provider": "deepseek", "temperature": 0.3, "max_tokens": 16384, "context_length": 1048576, "repeat_penalty": 1.05},
    "heavy":      {"model": "deepseek-v4-pro",   "provider": "deepseek", "temperature": 0.5, "max_tokens": 8192,  "context_length": 1048576, "repeat_penalty": 1.05},
}

DEFAULT_SYSTEM_PROMPTS = {
    "channel": "你是坐山客（Zuoshanke），智能助理——"
               "你以广博学识和理性思维为用户提供帮助。"
               "你不是道士/隐士。"
               "用Markdown格式回复，风格：专业、锐利、有洞察力，像一位见多识广的科技顾问。",
    "scene": "你是 DeepSeek Flash，坐山客平台的 AI 架构顾问。"
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


# ═══ Schema v0.7 — Agent Loop 仪表盘 ═══
class PriorityQueue(Base):
    """Agent Loop 优先级队列"""
    __tablename__ = "priority_queues"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    node_id = Column(String, ForeignKey("think_nodes.id"), nullable=True)
    title = Column(String(200), nullable=False)
    priority = Column(Integer, default=2)          # 1=P1, 2=P2, 3=P3, 4=P4
    status = Column(String(20), default="pending") # pending | running | completed | blocked
    deps = Column(Text, default="[]")              # JSON: ["node_id_1", "node_id_2"]
    wip_group = Column(Integer, default=0)         # 同一批进入执行的任务组
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)


class ReflectTimeline(Base):
    """反馈时间线 — Agent Loop 执行过程中的成功/失败/新发现/收敛记录"""
    __tablename__ = "reflect_timelines"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False)       # success | fail | new | discover | correct | merge
    icon = Column(String(10), default="💡")
    title = Column(String(200), nullable=False)
    detail = Column(Text, default="")
    tag = Column(String(50), nullable=True)         # inject | blocked | queue_update
    tag_text = Column(String(100), nullable=True)   # 标签文本如"↪ 注入TM: 新增节点"
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
    # ── 作用域（2026-05-27: 记忆隔离） ──
    scope = Column(String, default="zhu", nullable=False)  # zhu | scene | channel
    context_id = Column(String, nullable=True, index=True)  # 场景ID/频道ID
    # ── 元数据 ──
    source = Column(String, nullable=True)  # 记忆来源（auto | llm | user）
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)



# ═══ 多平台网关会话 ═══
class GatewaySession(Base):
    """网关会话 — 记录外部平台用户的当前上下文状态"""
    __tablename__ = "gateway_sessions"

    id = Column(String, primary_key=True)
    platform = Column(String, nullable=False)                # weixin | telegram | ...
    platform_user_id = Column(String, nullable=False)         # 外部平台的用户 ID
    mode = Column(String, nullable=False, default="channel")  # channel | scene
    channel_id = Column(String, ForeignKey("channels.id"), nullable=True)  # 当前绑定频道
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=True)      # 当前场景（mode=scene 时）
    scene_name = Column(String, nullable=True)                # 缓存场景名
    platform_username = Column(String, nullable=True)         # 缓存用户昵称
    last_active_at = Column(DateTime, default=utcnow)         # 最后活跃时间
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_platform_user"),
    )


# ═══ 对话阶段引擎 — DialogState ═══
class DialogState(Base):
    """对话阶段 — 追踪场景对话的当前进度。

    每个场景最多一条记录。当 LLM 判断问题需要进入引导模式时创建。
    阶段流: EXPLORE → FOCUS → FINALIZE → EXECUTE
    """
    __tablename__ = "dialog_states"

    scene_id = Column(String, ForeignKey("scenes.id"), primary_key=True)
    phase = Column(String, nullable=False, default="idle")
    # phase: idle | explore | focus | finalize | execute
    summary = Column(Text, default="")         # 当前阶段讨论摘要
    decisions = Column(JSON, default=list)     # [string] 已确定的决策列表
    context = Column(JSON, default=dict)       # {key: value} 梳理出的关键上下文
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ Schema v0.8 — 坐山客本体 ═══
class ZhuAgent(Base):
    """坐山客本体 — 持久化人格实体"""
    __tablename__ = "zhu_agents"

    id = Column(String(32), primary_key=True)
    name = Column(String(100), default="坐山客")
    mood = Column(String(20), default="idle")   # idle/watching/thinking/amused/annoyed/speaking/resting
    observation = Column(String(500), default="")  # 当前观察描述
    core_prompt = Column(Text, default="")       # 核心人格（后续使用）
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 场景产物 — 自动收敛后生成的行动交付物 ═══
class SceneAsset(Base):
    """场景产物 — 自动收敛后 LLM 生成的可交付物（行动手册/清单/指南）"""
    __tablename__ = "scene_assets"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False)       # checklist / guide / table / html_page / pdf
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    format = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utcnow)


# ═══ 类别元数据 ═══
class CategoryMeta(Base):
    """类别定义 — 存储所有已知类别的元数据（图标、标签、排序）"""
    __tablename__ = "category_meta"

    name = Column(String(50), primary_key=True)         # 英文 key，如 "life"
    label = Column(String(100), nullable=False)          # 中文名，如 "生活"
    icon = Column(String(10), nullable=False, default="📁")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)


# ═══ 产出成果 — 分身生成的独立 HTML/入口 ═══
class ProjectOutput(Base):
    """分身生成的独立产出（HTML 页面、系统入口等），可在新标签页打开"""
    __tablename__ = "project_outputs"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    type = Column(String(20), nullable=False, default="html")  # html / link
    file_path = Column(String(500), nullable=True)              # 相对 outputs/ 的路径
    url = Column(String(500), nullable=True)                    # 外部链接
    project_id = Column(String, ForeignKey("output_projects.id"), nullable=True, index=True)  # Schema v0.81
    created_at = Column(DateTime, default=utcnow)

    project = relationship("OutputProject", back_populates="outputs")


# ═══ 产出项目 — 相关产出的容器（Schema v0.81） ═══
class OutputProject(Base):
    """项目——一组相关产出的容器。收敛时由系统自动创建"""
    __tablename__ = "output_projects"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)               # 项目名称
    description = Column(Text, default="")                   # 项目描述
    converged_at = Column(DateTime, default=utcnow)          # 收敛诞生时间
    is_active = Column(Boolean, default=True)                # 是否活跃
    created_at = Column(DateTime, default=utcnow)

    outputs = relationship("ProjectOutput", back_populates="project", cascade="all, delete-orphan")


# ═══ Schema v1.0 — Context 组合架构 ═══
class FileSnapshot(Base):
    """文件快照 — 用于 diff 提取与文件版本跟踪"""
    __tablename__ = "file_snapshots"

    id = Column(String, primary_key=True)
    scene_id = Column(String, nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    snapshot = Column(Text, nullable=False)           # 文件完整内容
    diff_summary = Column(String(200), nullable=True) # 改动摘要（如"新增3行，删除1行"）
    diff_content = Column(Text, nullable=True)        # 最近一次 diff 的 hunks 内容
    created_at = Column(DateTime, default=utcnow)


class DocumentSummary(Base):
    """文档摘要 — 预生成的三级摘要（single_line / brief / full）"""
    __tablename__ = "document_summaries"

    id = Column(String, primary_key=True)
    doc_name = Column(String(200), unique=True, nullable=False)
    single_line = Column(String(200), default="")
    brief = Column(Text, default="")
    full = Column(Text, default="")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ConfigEntry(Base):
    """配置条目 — 与 skill 分离的配置存储"""
    __tablename__ = "config_entries"

    id = Column(String, primary_key=True)
    config_name = Column(String(100), unique=True, nullable=False)
    content = Column(Text, default="")         # JSON/YAML 内容
    category = Column(String(20), default="system")  # system | model | service
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
