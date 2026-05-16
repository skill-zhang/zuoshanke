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
    role = Column(String, nullable=False)  # user | ai | system
    content = Column(Text, nullable=False)
    map_ref = Column(String, nullable=True)     # 关联的 map node/drawer 操作
    created_at = Column(DateTime, default=utcnow)

    scene = relationship("Scene", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")


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
