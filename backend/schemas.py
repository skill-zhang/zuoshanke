"""Pydantic schemas — API 请求/响应"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ═══ 项目 ═══
class ProjectCreate(BaseModel):
    name: str
    description: str = ""

class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ═══ 场景 ═══
class SceneCreate(BaseModel):
    project_id: str
    name: str

class SceneOut(BaseModel):
    id: str
    project_id: str
    name: str
    pinned: bool = False
    complexity: Optional[str] = None
    constraints: Optional[list] = None
    constraints_locked: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SceneUpdate(BaseModel):
    name: Optional[str] = None
    pinned: Optional[bool] = None


# ═══ Thinking Map ═══
class ThinkNodeCreate(BaseModel):
    id: str
    type: str = "leaf"          # root | domain | leaf
    label: str
    status: str = "discussing"
    parent_id: Optional[str] = None
    actionable: bool = False
    discussion: List[str] = Field(default_factory=list)
    context_ref: Optional[str] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None

class ThinkNodeUpdate(BaseModel):
    label: Optional[str] = None
    status: Optional[str] = None
    actionable: Optional[bool] = None
    discussion: Optional[List[str]] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None

class ThinkNodeOut(BaseModel):
    id: str
    map_id: str
    parent_id: Optional[str]
    type: str
    label: str
    status: str
    actionable: bool
    context_ref: Optional[str]
    discussion: List
    linked_action_map: Optional[str]
    action_status: Optional[str]
    position_x: Optional[int]
    position_y: Optional[int]

    class Config:
        from_attributes = True

class ThinkingMapOut(BaseModel):
    id: str
    scene_id: str
    title: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    nodes: List[ThinkNodeOut] = []

    class Config:
        from_attributes = True


# ═══ 对话 ═══
class MessageCreate(BaseModel):
    scene_id: Optional[str] = None      # 场景消息用
    channel_id: Optional[str] = None    # 频道消息用
    content: str
    channel: str = "main"  # main = AI 更新 Thinking Map, chat = 只聊天

class MessageOut(BaseModel):
    id: str
    scene_id: Optional[str] = None
    channel_id: Optional[str] = None
    role: str
    content: str
    map_ref: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class MessageUpdate(BaseModel):
    content: Optional[str] = None


# ═══ 频道 ═══
class ChannelCreate(BaseModel):
    name: str

class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    pinned: Optional[bool] = None

class ChannelOut(BaseModel):
    id: str
    name: str
    pinned: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ═══ Action Map ═══
class VerificationCheck(BaseModel):
    type: str  # url | command | file
    target: str
    result: Optional[str] = None
    passed: Optional[bool] = None

class VerificationOut(BaseModel):
    status: str = "pending"  # pending | passed | failed
    checks: List[VerificationCheck] = []
    failed_count: int = 0

class ActionNodeCreate(BaseModel):
    id: str
    type: str  # start | exec | decision | milestone | end
    label: str
    requires_approval: bool = False
    timeout: int = 300
    retry: int = 0
    verification: Optional[VerificationOut] = None
    fallback_node: Optional[str] = None
    order_index: int = 0
    position_x: Optional[int] = None
    position_y: Optional[int] = None

class ActionEdgeCreate(BaseModel):
    id: str
    from_node_id: str
    to_node_id: str
    type: str = "flow"  # flow | decision | fallback
    label: Optional[str] = None
    condition: Optional[str] = None

class ActionMapCreate(BaseModel):
    """从 Thinking Map 可执行叶子节点生成 Action Map"""
    think_map_id: str
    think_node_id: str
    title: str
    nodes: List[ActionNodeCreate]
    edges: List[ActionEdgeCreate]

class ActionNodeOut(BaseModel):
    id: str
    map_id: str
    type: str
    label: str
    status: str
    requires_approval: bool
    timeout: int
    retry: int
    retry_count: int
    verification: Optional[dict] = None
    fallback_node: Optional[str] = None
    origin: str
    result_summary: Optional[str] = None
    artifacts: List[str] = []
    context_ref: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    order_index: int
    position_x: Optional[int] = None
    position_y: Optional[int] = None

    class Config:
        from_attributes = True

class ActionEdgeOut(BaseModel):
    id: str
    map_id: str
    from_node_id: str
    to_node_id: str
    type: str
    label: Optional[str] = None
    condition: Optional[str] = None

    class Config:
        from_attributes = True

class ActionMapOut(BaseModel):
    id: str
    think_map_id: str
    think_node_id: str
    title: str
    status: str
    version: int
    replan_count: int
    dynamic_nodes: List[str] = []
    created_at: datetime
    updated_at: datetime
    nodes: List[ActionNodeOut] = []
    edges: List[ActionEdgeOut] = []

    class Config:
        from_attributes = True

class ActionMapStatusUpdate(BaseModel):
    status: str  # ready | running | paused | completed | failed

class ActionNodeStatusUpdate(BaseModel):
    status: str

class ActionMapGenerateRequest(BaseModel):
    think_node_id: str
