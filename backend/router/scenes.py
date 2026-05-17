"""场景 + Thinking Map CRUD + 场景流式 + 场景广场/工坊/发布/导入导出"""
import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import Scene, ThinkingMap, ThinkNode, Message
from schemas import (
    SceneCreate, SceneOut, SceneUpdate, ScenePublishRequest,
    SceneExportOut, SceneImportIn,
    ThinkNodeCreate, ThinkNodeUpdate, ThinkNodeOut, ThinkingMapOut,
    MessageCreate,
)
from ai_engine import (
    ai_scene_chat_stream, ai_scene_light_chat_stream,
    ai_scene_ask_missing_stream, extract_and_classify,
)
from agent_core.core import agent_core_light_stream
from agent_core.tool_executor import detect_and_preexecute
from utils import make_id, utcnow
from router.shared import sse_event, sse_response

router = APIRouter(tags=["场景"])


# ═══ 场景 CRUD ═══

@router.post("/api/scenes", response_model=SceneOut)
def create_scene(data: SceneCreate, db: Session = Depends(get_db)):
    _get_project_or_404(db, data.project_id)
    scene = Scene(
        id=make_id("scene"),
        project_id=data.project_id,
        name=data.name,
        icon=data.icon or None,
        description=data.description or "",
        category=data.category or "other",
        guide_text=data.guide_text or None,
    )
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
    if data.user_context is not None:
        scene.user_context = data.user_context.strip() or None
    if data.icon is not None:
        scene.icon = data.icon or None
    if data.description is not None:
        scene.description = data.description or ""
    if data.category is not None:
        scene.category = data.category or "other"
    if data.guide_text is not None:
        scene.guide_text = data.guide_text or None
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


# ═══ 场景广场 ═══

@router.get("/api/scenes/plaza", response_model=List[SceneOut])
def list_plaza_scenes(
    category: str = None,
    q: str = None,
    db: Session = Depends(get_db),
):
    """场景广场 — 仅返回已发布场景，支持分类过滤和搜索"""
    query = db.query(Scene).filter(Scene.version != "0.0")
    if category:
        query = query.filter(Scene.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.query(Scene).filter(
                Scene.name.ilike(like) | Scene.description.ilike(like)
            ).exists()
        )
    return query.order_by(Scene.published_at.desc(), Scene.updated_at.desc()).all()


# ═══ 发布 / 版本更新 ═══

@router.post("/api/scenes/{scene_id}/publish", response_model=SceneOut)
def publish_scene(scene_id: str, data: ScenePublishRequest, db: Session = Depends(get_db)):
    """发布场景或更新版本。校验 version 必须大于当前版本"""
    scene = _get_scene_or_404(db, scene_id)

    # 版本号比较（语义化：1.0 < 1.1 < 2.0）
    def _parse_version(v: str) -> tuple:
        try:
            parts = v.strip().split(".")
            return tuple(int(x) for x in parts)
        except (ValueError, AttributeError):
            raise HTTPException(400, f"版本号格式无效: {v}（请使用 x.y 格式）")

    new_ver = _parse_version(data.version)
    cur_ver = _parse_version(scene.version)
    if new_ver <= cur_ver:
        raise HTTPException(400, f"新版本 {data.version} 必须大于当前版本 {scene.version}")

    scene.version = data.version
    scene.changelog = data.changelog or None
    scene.published_at = utcnow()
    scene.updated_at = utcnow()
    db.commit()
    db.refresh(scene)
    return scene


# ═══ 导入 / 导出 ═══

@router.get("/api/scenes/{scene_id}/export", response_model=SceneExportOut)
def export_scene(scene_id: str, db: Session = Depends(get_db)):
    """导出场景为 JSON（不含消息记录）"""
    scene = _get_scene_or_404(db, scene_id)
    return SceneExportOut(
        name=scene.name,
        icon=scene.icon,
        description=scene.description or "",
        category=scene.category or "other",
        guide_text=scene.guide_text,
        user_context=scene.user_context,
        complexity=scene.complexity,
        constraints=scene.constraints,
        constraints_locked=scene.constraints_locked,
        version="0.0" if scene.version == "0.0" else scene.version,
    )


@router.post("/api/scenes/import", response_model=SceneOut)
def import_scene(data: SceneImportIn, db: Session = Depends(get_db)):
    """从 JSON 导入场景"""
    _get_project_or_404(db, data.project_id)
    s = data.scene
    scene = Scene(
        id=make_id("scene"),
        project_id=data.project_id,
        name=s.name,
        icon=s.icon or None,
        description=s.description or "",
        category=s.category or "other",
        guide_text=s.guide_text,
        user_context=s.user_context,
        complexity=s.complexity,
        constraints=s.constraints,
        constraints_locked=s.constraints_locked,
        version="0.0",  # 导入后变为草稿
        source="imported",
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)

    tmap = ThinkingMap(id=make_id("think"), scene_id=scene.id, title=f"{s.name} · 需求梳理")
    db.add(tmap)
    db.commit()
    db.refresh(tmap)

    root = ThinkNode(
        id=make_id("n"), map_id=tmap.id,
        type="root", label=s.name, status="confirmed",
    )
    db.add(root)
    db.commit()
    return scene


# ═══ 工坊 — 全部场景（含草稿） ═══

@router.get("/api/scenes/workshop", response_model=List[SceneOut])
def list_workshop_scenes(
    category: str = None,
    project_id: str = None,
    db: Session = Depends(get_db),
):
    """工坊 — 自己创作的所有场景（含草稿和已发布）"""
    q = db.query(Scene)
    if project_id:
        q = q.filter(Scene.project_id == project_id)
    if category:
        q = q.filter(Scene.category == category)
    return q.order_by(Scene.pinned.desc(), Scene.updated_at.desc()).all()


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


# ═══ 工具卡片 ═══

def _build_tool_cards(tool_results: list[dict]) -> list[dict]:
    """将预执行工具结果转为前端可渲染的卡片数据

    Returns:
        [{"type": "weather"|"attractions"|"equipment", "data": {...}}, ...]
    """
    cards = []
    for r in tool_results:
        if not r.get("success") or not r.get("result"):
            continue
        tool = r["tool"]
        res = r["result"]

        if tool == "get_weather" and isinstance(res, dict):
            cards.append({
                "type": "weather",
                "data": {
                    "city": res.get("city", ""),
                    "desc": res.get("desc", ""),
                    "temp": res.get("temp", ""),
                    "humidity": res.get("humidity", ""),
                    "wind": res.get("wind", ""),
                    "forecast": res.get("forecast", []),
                    "hourly": res.get("hourly", []),
                },
            })

        elif tool == "recommend_attractions" and isinstance(res, dict):
            cards.append({
                "type": "attractions",
                "data": {
                    "city": res.get("city", ""),
                    "category_label": res.get("category_label", ""),
                    "default_category": res.get("default_category", ""),
                    "total_matched": res.get("total_matched", 0),
                    "items": [
                        {
                            "name": it.get("name", ""),
                            "category": it.get("category", ""),
                            "tags": it.get("tags", []),
                            "indoor": it.get("indoor", False),
                            "note": it.get("note", ""),
                            "score": it.get("score", 0),
                        }
                        for it in (res.get("items", []) or [])
                    ],
                },
            })

        elif tool == "get_equipment_checklist" and isinstance(res, dict):
            items = res.get("items", []) or []
            cards.append({
                "type": "equipment",
                "data": {
                    "label": res.get("label", ""),
                    "icon": res.get("icon", ""),
                    "default_category": res.get("default_category", ""),
                    "total": res.get("total", 0),
                    "must_have": res.get("must_have", 0),
                    "recommended": res.get("recommended", 0),
                    "optional": res.get("optional", 0),
                    "items": [
                        {
                            "name": it.get("name", ""),
                            "necessity": it.get("necessity", ""),
                            "note": it.get("note", ""),
                        }
                        for it in items
                    ],
                },
            })

    return cards


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
        user_ctx = scene.user_context

        # ── 预执行：在路由决策前先检测工具意图 ──
        tool_results = detect_and_preexecute(data.content)

        # ── 路由决策 ──
        if tool_results:
            # 有预执行结果 → 直接走 Light 路由（系统数据够用，无需追问）
            ai_stream = agent_core_light_stream(
                data.content, history_messages, scene_id, db,
                user_context=user_ctx, tool_results=tool_results,
            )
            model_name = "Qwen3.5 本地 + Agent Core"
        elif need_extraction and not constraints_ok and missing_info:
            ai_stream = ai_scene_ask_missing_stream(scene_id, data.content, missing_info, history_messages, db, user_context=user_ctx)
            model_name = "Qwen3.5 本地"
        elif complexity == "light":
            ai_stream = agent_core_light_stream(data.content, history_messages, scene_id, db, user_context=user_ctx)
            model_name = "Qwen3.5 本地 + Agent Core"
        else:
            ai_stream = ai_scene_chat_stream(scene_id, data.content, db, complexity, history_messages, user_context=user_ctx)
            model_name = MODEL_MAP.get(complexity, "Qwen3.5 本地")

        # ── 工具卡片：将预执行结果转为前端可渲染的结构化数据 ──
        tool_cards = _build_tool_cards(tool_results) if tool_results else []
        if tool_cards:
            yield sse_event("tool_cards", cards=tool_cards)

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
