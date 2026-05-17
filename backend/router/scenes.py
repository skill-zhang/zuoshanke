"""场景 + Thinking Map CRUD + 场景流式"""
import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import Scene, ThinkingMap, ThinkNode, Message
from schemas import (
    SceneCreate, SceneOut, SceneUpdate,
    ThinkNodeCreate, ThinkNodeUpdate, ThinkNodeOut, ThinkingMapOut,
    MessageCreate,
)
from ai_engine import (
    ai_scene_chat_stream, ai_scene_light_chat_stream,
    ai_scene_ask_missing_stream, extract_and_classify,
)
from agent_core.core import agent_core_light_stream
from utils import make_id, utcnow
from router.shared import sse_event, sse_response

router = APIRouter(tags=["场景"])


# ═══ 场景 CRUD ═══

@router.post("/api/scenes", response_model=SceneOut)
def create_scene(data: SceneCreate, db: Session = Depends(get_db)):
    _get_project_or_404(db, data.project_id)
    scene = Scene(id=make_id("scene"), project_id=data.project_id, name=data.name)
    db.add(scene)
    db.commit()
    db.refresh(scene)

    tmap = ThinkingMap(id=make_id("think"), scene_id=scene.id, title=f"{data.name} · 需求梳理")
    db.add(tmap)
    db.commit()
    db.refresh(tmap)

    root = ThinkNode(
        id=make_id("n"), map_id=tmap.id,
        type="root", label=data.name, status="confirmed",
    )
    db.add(root)
    db.commit()
    return scene


@router.get("/api/scenes", response_model=List[SceneOut])
def list_scenes(project_id: str = None, db: Session = Depends(get_db)):
    q = db.query(Scene)
    if project_id:
        q = q.filter(Scene.project_id == project_id)
    return q.order_by(Scene.pinned.desc(), Scene.updated_at.desc()).all()


@router.get("/api/scenes/{scene_id}", response_model=SceneOut)
def get_scene(scene_id: str, db: Session = Depends(get_db)):
    return _get_scene_or_404(db, scene_id)


@router.patch("/api/scenes/{scene_id}", response_model=SceneOut)
def update_scene(scene_id: str, data: SceneUpdate, db: Session = Depends(get_db)):
    scene = _get_scene_or_404(db, scene_id)
    if data.name is not None:
        scene.name = data.name
    if data.pinned is not None:
        scene.pinned = data.pinned
    scene.updated_at = utcnow()
    db.commit()
    db.refresh(scene)
    return scene


@router.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id: str, db: Session = Depends(get_db)):
    scene = _get_scene_or_404(db, scene_id)
    db.delete(scene)
    db.commit()
    return {"ok": True}


# ═══ Thinking Map ═══

@router.get("/api/scenes/{scene_id}/thinking-map", response_model=ThinkingMapOut)
def get_thinking_map(scene_id: str, db: Session = Depends(get_db)):
    _get_scene_or_404(db, scene_id)
    tmap = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")
    tmap.nodes  # trigger lazy load
    return tmap


@router.post("/api/thinking-maps/{map_id}/nodes", response_model=ThinkNodeOut)
def add_node(map_id: str, data: ThinkNodeCreate, db: Session = Depends(get_db)):
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")
    if data.parent_id:
        parent = db.query(ThinkNode).filter(ThinkNode.id == data.parent_id).first()
        if not parent:
            raise HTTPException(404, "父节点不存在")

    node = ThinkNode(
        id=data.id, map_id=map_id, parent_id=data.parent_id,
        type=data.type, label=data.label, status=data.status,
        actionable=data.actionable, discussion=data.discussion,
        context_ref=data.context_ref,
        position_x=data.position_x, position_y=data.position_y,
    )
    db.add(node)
    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()
    db.refresh(node)
    return node


@router.patch("/api/think-nodes/{node_id}", response_model=ThinkNodeOut)
def update_node(node_id: str, data: ThinkNodeUpdate, db: Session = Depends(get_db)):
    node = db.query(ThinkNode).filter(ThinkNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    for field in ("label", "status", "actionable", "discussion", "position_x", "position_y"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(node, field, val)

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == node.map_id).first()
    if tmap:
        tmap.version += 1
        tmap.updated_at = utcnow()
    db.commit()
    db.refresh(node)
    return node


@router.delete("/api/think-nodes/{node_id}")
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(ThinkNode).filter(ThinkNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    db.delete(node)
    db.commit()
    return {"ok": True}


# ═══ 场景流式 ═══

@router.post("/api/scenes/{scene_id}/stream")
def stream_scene_message(scene_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到场景 + 流式 SSE 返回 AI 回复"""
    scene = _get_scene_or_404(db, scene_id)

    user_msg = Message(
        id=make_id("msg"), scene_id=scene_id,
        role="user", content=data.content, session_id=data.session_id,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    def generate():
        nonlocal scene
        # 1. 用户消息事件
        yield sse_event("user_msg", id=user_msg.id, role="user",
                        content=user_msg.content, created_at=user_msg.created_at.isoformat())

        # 2. 历史消息（session 隔离）
        q = db.query(Message).filter(Message.scene_id == scene_id)
        if data.session_id:
            q = q.filter(Message.session_id == data.session_id)
        scene_history = q.order_by(Message.created_at.desc()).limit(20).all()
        scene_history.reverse()
        history_messages = [
            {"role": m.role, "content": m.content}
            for m in scene_history if m.id != user_msg.id
        ]

        # 3. 约束提取 + 路由
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        need_extraction = scene.constraints is None or not scene.constraints_locked
        if need_extraction:
            result = extract_and_classify(data.content, scene.complexity, scene.constraints)
            scene.constraints = result["constraints"]
            scene.complexity = result["complexity"]
            scene.constraints_locked = result["constraints_locked"]
            db.commit()
            complexity, constraints_ok = result["complexity"], result["constraints_locked"]
            missing_info = result.get("missing_info", [])
        else:
            complexity, constraints_ok = scene.complexity or "medium", True
            missing_info = []

        MODEL_MAP = {"light": "Qwen3.5 本地", "medium": "DeepSeek Flash", "heavy": "DeepSeek Pro"}
        if need_extraction and not constraints_ok and missing_info:
            ai_stream = ai_scene_ask_missing_stream(scene_id, data.content, missing_info, history_messages, db)
            model_name = "Qwen3.5 本地"
        elif complexity == "light":
            ai_stream = agent_core_light_stream(data.content, history_messages, scene_id, db)
            model_name = "Qwen3.5 本地 + Agent Core"
        else:
            ai_stream = ai_scene_chat_stream(scene_id, data.content, db, complexity, history_messages)
            model_name = MODEL_MAP.get(complexity, "Qwen3.5 本地")

        yield sse_event("model_info", model=model_name, complexity=complexity)

        # 4. 流式收回复
        full_reply, changes = "", []
        for token in ai_stream:
            if isinstance(token, dict):
                if token.get("_error"):
                    yield sse_event("error", message=token["message"])
                    return
                if token.get("_done"):
                    full_reply = token["reply"]
                    changes = token.get("changes", [])
                break
            full_reply += token
            yield sse_event("token", token=token)

        # 5. 保存 AI 消息（独立 DB session）
        ai_msg_id = make_id("msg")
        new_db = SessionLocal()
        try:
            ai_msg = Message(
                id=ai_msg_id, scene_id=scene_id,
                role="ai", content=full_reply,
                session_id=data.session_id, model=model_name,
            )
            new_db.add(ai_msg)
            new_db.commit()
            new_db.refresh(ai_msg)
            yield sse_event("done", id=ai_msg.id, role="ai", content=full_reply,
                            created_at=ai_msg.created_at.isoformat(),
                            changes=changes, model=model_name)
        except Exception as e:
            print(f"[scene stream save error] {e}")
            yield sse_event("error", message="AI 回复保存失败")
        finally:
            new_db.close()

    return sse_response(generate())


# ═══ 会话管理 ═══

@router.post("/api/scenes/{scene_id}/new-session")
def new_scene_session(scene_id: str, db: Session = Depends(get_db)):
    _get_scene_or_404(db, scene_id)
    session_id = f"ses-{uuid.uuid4().hex[:12]}"
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    scene.constraints = None
    scene.constraints_locked = False
    scene.complexity = None
    db.commit()
    return {"session_id": session_id}


@router.get("/api/scenes/{scene_id}/sessions")
def list_scene_sessions(scene_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import func
    _get_scene_or_404(db, scene_id)
    rows = (
        db.query(Message.session_id, func.max(Message.created_at), func.count(Message.id))
        .filter(Message.scene_id == scene_id, Message.session_id.isnot(None))
        .group_by(Message.session_id)
        .order_by(func.max(Message.created_at).desc())
        .all()
    )
    return [
        {"session_id": r[0], "last_active": r[1].isoformat() if r[1] else None, "message_count": r[2]}
        for r in rows
    ]


# ═══ 辅助函数 ═══

def _get_project_or_404(db: Session, project_id: str):
    from models import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


def _get_scene_or_404(db: Session, scene_id: str):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    return scene
