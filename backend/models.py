"""
SQLAlchemy 模型 — 基于 Schema v0.3
"""
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

    # ── Schema v1.3: 工作台 ──
    show_on_workbench = Column(Boolean, default=False)         # 是否展示在工作台
    workbench_position = Column(Integer, default=0)            # 工作台排序

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
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    status = Column(String, default="editing")  # editing | converged | active
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    scene = relationship("Scene", back_populates="thinking_maps")
    nodes = relationship("ThinkNode", back_populates="map", cascade="all, delete-orphan")


class ThinkNode(Base):
    __tablename__ = "think_nodes"

    id = Column(String, primary_key=True)
    map_id = Column(String, ForeignKey("thinking_maps.id"), nullable=False, index=True)
    parent_id = Column(String, ForeignKey("think_nodes.id"), nullable=True)
    label = Column(String, nullable=False)
    node_type = Column(String, default="leaf")  # root | domain | leaf
    status = Column(String, default="active")   # active | confirmed | abandoned | merged
    priority = Column(String, nullable=True)    # P0 | P1 | P2 | P3
    actionable = Column(Boolean, default=False)
    queue_order = Column(Integer, nullable=True)
    position_x = Column(Integer, nullable=True)
    position_y = Column(Integer, nullable=True)

    map = relationship("ThinkingMap", back_populates="nodes")
    parent = relationship("ThinkNode", remote_side="ThinkNode.id", backref="children")


# ═══ 频道 ═══
class Channel(Base):
    __tablename__ = "channels"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 角色设定
    model = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    messages = relationship("Message", back_populates="channel", cascade="all, delete-orphan")


# ═══ 消息 ═══
class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    channel_id = Column(String, ForeignKey("channels.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    role = Column(String, nullable=False)  # user | ai | system
    content = Column(Text, nullable=False)
    map_ref = Column(String, nullable=True)
    model = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    scene = relationship("Scene", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")


# ═══ 设置 ═══
class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=True)
    description = Column(String, default="")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 优先级队列（收敛产物） ═══
class PriorityQueue(Base):
    __tablename__ = "priority_queue"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    node_id = Column(String, nullable=True)
    label = Column(String, nullable=False)
    priority = Column(String, nullable=True)  # P0 | P1 | P2 | P3
    status = Column(String, default="pending")  # pending | in_progress | done | blocked
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 反思时间线 ═══
class ReflectTimeline(Base):
    __tablename__ = "reflect_timeline"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow)


# ═══ Agent Memory（长期记忆） ═══
class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    scope = Column(String(16), default="scene")  # zhu | scene | channel
    scene_id = Column(String(32), nullable=True, index=True)
    channel_id = Column(String(32), nullable=True, index=True)
    target = Column(String(16), default="memory")  # memory | user
    content = Column(Text, nullable=False)
    strength = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 网关会话 ═══
class GatewaySession(Base):
    """网关会话 — 记录外部平台用户的当前上下文状态"""
    __tablename__ = "gateway_sessions"

    id = Column(String, primary_key=True)
    platform = Column(String, nullable=False, index=True)  # discord | wechat | telegram | terminal | api
    external_user_id = Column(String, nullable=False, index=True)
    scene_id = Column(String, nullable=True)
    channel_id = Column(String, nullable=True)
    session_state = Column(String, default="active")  # active | waiting_input | idle | expired
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ Web 会话 ═══
class WebSession(Base):
    """浏览器 Web 会话 — 状态管理"""
    __tablename__ = "web_sessions"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=True)
    channel_id = Column(String, nullable=True)
    user_context = Column(Text, nullable=True)
    extra = Column(JSON, default=dict)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 对话状态 ═══
class DialogState(Base):
    """对话状态快照 — 用于断线恢复"""
    __tablename__ = "dialog_states"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=True)
    channel_id = Column(String, nullable=True)
    state = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 本体 Agent ═══
class ZhuAgent(Base):
    """坐山客本体 Agent — 每个场景可绑定不同本体"""
    __tablename__ = "zhu_agents"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, unique=True, index=True)
    role = Column(String, default="助手")
    model = Column(String, nullable=True)
    system_prompt = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 场景资源 ═══
class SceneAsset(Base):
    """场景资源 — 每个场景关联的图片/文件等"""
    __tablename__ = "scene_assets"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    asset_type = Column(String, nullable=False)  # image | file | audio | video
    url = Column(String, nullable=False)
    filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)


# ═══ 分类元数据 ═══
class CategoryMeta(Base):
    """场景分类元数据 — 用于场景广场筛选"""
    __tablename__ = "category_meta"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, unique=True, index=True)
    category = Column(String, nullable=False)
    tags = Column(JSON, default=list)
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 项目输出 ═══
class ProjectOutput(Base):
    """项目输出 — 场景中生成的工作产物"""
    __tablename__ = "project_outputs"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    project_id = Column(String, nullable=False, default="")
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    output_type = Column(String, default="text")  # text | code | markdown | image
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 输出项目（分组） ═══
class OutputProject(Base):
    """输出项目分组 — 将多个 ProjectOutput 归组"""
    __tablename__ = "output_projects"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="active")  # active | archived
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 文件快照 ═══
class FileSnapshot(Base):
    """文件快照 — 记录文件在某个时刻的内容"""
    __tablename__ = "file_snapshots"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    file_path = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)


# ═══ 文档摘要 ═══
class DocumentSummary(Base):
    """文档摘要 — 文档/URL 的摘要缓存"""
    __tablename__ = "document_summaries"

    id = Column(String, primary_key=True)
    url_or_path = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, default="")
    summary = Column(Text, default="")
    word_count = Column(Integer, default=0)
    language = Column(String, default="zh")
    source = Column(String, default="web")  # web | local
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 配置项 ═══
class ConfigEntry(Base):
    """系统配置项 — key-value 持久化"""
    __tablename__ = "config_entries"

    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=True)
    description = Column(String, default="")
    category = Column(String, default="system")  # system | user | scene
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ AI Provider ═══
class AiProvider(Base):
    """AI 服务提供商 — 含 API 地址、密钥、模型列表"""
    __tablename__ = "ai_providers"

    id = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False)
    api_base = Column(String(500), nullable=False)
    api_key = Column(String(500), nullable=True)
    models = Column(JSON, default=list)       # 支持的模型列表
    default_model = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)     # 优先级（数值越高越优先）
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ AI 模型 ═══
class AiModel(Base):
    """AI 模型 — 绑定到 Provider，带默认参数和能力声明"""
    __tablename__ = "ai_models"

    id = Column(String(32), primary_key=True)
    provider_id = Column(String(32), ForeignKey("ai_providers.id"), nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    model_name = Column(String(200), nullable=False)       # 实际传给 API 的 model 参数
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=4096)
    capabilities = Column(JSON, default=list)               # ["function_calling", "vision", ...]
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 子 Agent 执行结果 ═══
class DelegateResult(Base):
    """子 Agent 执行结果 — 持久化到 DB，供前端独立展示"""
    __tablename__ = "delegate_results"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    session_id = Column(String, nullable=True)              # 关联会话 ID
    parent_message_id = Column(String, nullable=True)       # 触发 delegate_task 的消息 ID
    task = Column(String(500), nullable=False)              # 任务目标
    status = Column(String(20), nullable=False)             # success / error / timeout
    summary = Column(Text, default="")                      # 结果摘要
    steps = Column(Integer, default=0)                      # 执行步数
    error = Column(String(500), nullable=True)              # 错误信息
    created_at = Column(DateTime, default=utcnow)


# ═══ 🆕 起居室消息 ═══
class GardenMessage(Base):
    """秘密花园聊天消息 — 用户与本体直接在起居室对话"""
    __tablename__ = "garden_messages"

    id = Column(String, primary_key=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)


# ═══ 🆕 场景自省地图 ═══
class SceneSelfMap(Base):
    """每个场景一张自省架构图 — LLM 通过 function calling 声明"""
    __tablename__ = "scene_self_maps"

    id = Column(String(32), primary_key=True)
    scene_id = Column(String(32), ForeignKey("scenes.id"), nullable=False, unique=True, index=True)
    title = Column(String(200), default="")
    tree = Column(JSON, default=list)          # 左侧导航树 [{id, icon, label, children?, detail?, hasDiagram?}]
    diagrams = Column(JSON, default=dict)       # 流程图 {nodeId: {title, nodes, edges}}
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 🆕 Schema v1.4 Phase 1 — 用户画像 ═══

class PendingUserTrait(Base):
    """用户画像暂存区 — 分身提取的用户特征，待人工确认后合入正式库"""
    __tablename__ = "pending_user_traits"

    id = Column(String, primary_key=True)
    content = Column(Text, nullable=False)           # 分身提取的描述
    source_scene = Column(String, nullable=True)     # 来源场景名称
    source_scene_id = Column(String, nullable=True)  # 来源场景ID
    confidence = Column(String, default="medium")    # high / medium / low
    context_snippet = Column(Text, nullable=True)    # 触发对话片段
    status = Column(String, default="pending")       # pending / merged / rejected
    merged_into = Column(String, nullable=True)      # 合入哪条正式画像的 key
    created_at = Column(DateTime, default=utcnow)


class UserProfile(Base):
    """用户画像正式库 — 沉淀后的用户偏好/原则/习惯/上下文"""
    __tablename__ = "user_profiles"

    id = Column(String, primary_key=True)
    key = Column(String, unique=True, index=True, nullable=False)  # 唯一标识
    content = Column(Text, nullable=False)                          # 画像内容
    category = Column(String, default="preference")                 # principle / preference / habit / context
    priority = Column(String, default="P2")                        # P0 / P1 / P2 / P3
    tags = Column(JSON, default=list)
    source_scenes = Column(JSON, default=list)
    merged_from = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    deprecated_by = Column(String, nullable=True)
    correction_trail = Column(JSON, default=list)
    total_injections = Column(Integer, default=0)
    last_injected_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══ 已废弃的表（代码中已删除，DB 中保留供历史数据查询） ═══
