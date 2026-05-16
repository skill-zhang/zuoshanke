"""坐山客 API — FastAPI 应用"""
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db, init_db, SessionLocal
from models import Project, Scene, ThinkingMap, ThinkNode, CrossRef, Message, Channel, ActionMap, ActionNode, ActionEdge, ActionExecutionLog
from ai_engine import ai_process_message, ai_channel_chat, ai_channel_chat_stream, ai_scene_chat_stream, ai_scene_light_chat_stream, ai_scene_ask_missing_stream, extract_and_classify, ai_generate_action_map, call_hermes_action_map, call_hermes_execute_node, scan_and_document_tools, call_qwen_chat
from schemas import (
    ProjectCreate, ProjectOut,
    SceneCreate, SceneOut, SceneUpdate,
    ThinkNodeCreate, ThinkNodeUpdate, ThinkNodeOut, ThinkingMapOut,
    MessageCreate, MessageOut, MessageUpdate,
    ChannelCreate, ChannelUpdate, ChannelOut,
    ActionMapCreate, ActionMapOut, ActionNodeOut, ActionEdgeOut,
    ActionMapStatusUpdate, ActionNodeStatusUpdate, ActionMapGenerateRequest,
)

app = FastAPI(title="坐山客 API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def make_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:8]
    return f"{prefix}-{short}" if prefix else short


def utcnow():
    return datetime.now(timezone.utc)


# ═══ 健康检查 ═══
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zuoshanke", "version": "0.2.0"}


# ═══ 项目 CRUD ═══
# ═══════════════════════════════════════
@app.post("/api/projects", response_model=ProjectOut)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        id=make_id("proj"),
        name=data.name,
        description=data.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.get("/api/projects", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.updated_at.desc()).all()


@app.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    db.delete(project)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════
#  场景 CRUD
# ═══════════════════════════════════════
@app.post("/api/scenes", response_model=SceneOut)
def create_scene(data: SceneCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    scene = Scene(
        id=make_id("scene"),
        project_id=data.project_id,
        name=data.name,
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)

    # 自动创建 Thinking Map
    tmap = ThinkingMap(
        id=make_id("think"),
        scene_id=scene.id,
        title=f"{data.name} · 需求梳理",
    )
    db.add(tmap)
    db.commit()
    db.refresh(tmap)

    # 创建根节点
    root = ThinkNode(
        id=make_id("n"),
        map_id=tmap.id,
        type="root",
        label=data.name,
        status="confirmed",
    )
    db.add(root)
    db.commit()

    return scene


@app.get("/api/scenes", response_model=List[SceneOut])
def list_scenes(project_id: str = None, db: Session = Depends(get_db)):
    q = db.query(Scene)
    if project_id:
        q = q.filter(Scene.project_id == project_id)
    return q.order_by(Scene.pinned.desc(), Scene.updated_at.desc()).all()


@app.get("/api/scenes/{scene_id}", response_model=SceneOut)
def get_scene(scene_id: str, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    return scene


@app.patch("/api/scenes/{scene_id}", response_model=SceneOut)
def update_scene(scene_id: str, data: SceneUpdate, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    if data.name is not None:
        scene.name = data.name
    if data.pinned is not None:
        scene.pinned = data.pinned
    scene.updated_at = utcnow()
    db.commit()
    db.refresh(scene)
    return scene


@app.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id: str, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    db.delete(scene)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════
#  Thinking Map CRUD
# ═══════════════════════════════════════
@app.get("/api/scenes/{scene_id}/thinking-map", response_model=ThinkingMapOut)
def get_thinking_map(scene_id: str, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    tmap = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    tmap.nodes  # trigger lazy load
    return tmap


@app.post("/api/thinking-maps/{map_id}/nodes", response_model=ThinkNodeOut)
def add_node(map_id: str, data: ThinkNodeCreate, db: Session = Depends(get_db)):
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    if data.parent_id:
        parent = db.query(ThinkNode).filter(ThinkNode.id == data.parent_id).first()
        if not parent:
            raise HTTPException(404, "父节点不存在")

    node = ThinkNode(
        id=data.id,
        map_id=map_id,
        parent_id=data.parent_id,
        type=data.type,
        label=data.label,
        status=data.status,
        actionable=data.actionable,
        discussion=data.discussion,
        context_ref=data.context_ref,
        position_x=data.position_x,
        position_y=data.position_y,
    )
    db.add(node)
    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()
    db.refresh(node)
    return node


@app.patch("/api/think-nodes/{node_id}", response_model=ThinkNodeOut)
def update_node(node_id: str, data: ThinkNodeUpdate, db: Session = Depends(get_db)):
    node = db.query(ThinkNode).filter(ThinkNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")

    if data.label is not None:
        node.label = data.label
    if data.status is not None:
        node.status = data.status
    if data.actionable is not None:
        node.actionable = data.actionable
    if data.discussion is not None:
        node.discussion = data.discussion
    if data.position_x is not None:
        node.position_x = data.position_x
    if data.position_y is not None:
        node.position_y = data.position_y

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == node.map_id).first()
    if tmap:
        tmap.version += 1
        tmap.updated_at = utcnow()

    db.commit()
    db.refresh(node)
    return node


@app.delete("/api/think-nodes/{node_id}")
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(ThinkNode).filter(ThinkNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    db.delete(node)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════
#  频道 CRUD
# ═══════════════════════════════════════
@app.get("/api/channels", response_model=List[ChannelOut])
def list_channels(db: Session = Depends(get_db)):
    return (
        db.query(Channel)
        .order_by(Channel.is_default.desc(), Channel.pinned.desc(), Channel.updated_at.desc())
        .all()
    )


@app.post("/api/channels", response_model=ChannelOut)
def create_channel(data: ChannelCreate, db: Session = Depends(get_db)):
    existing = db.query(Channel).filter(Channel.name == data.name).first()
    if existing:
        raise HTTPException(400, "频道名称已存在")

    channel = Channel(
        id=make_id("ch"),
        name=data.name,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@app.patch("/api/channels/{channel_id}", response_model=ChannelOut)
def update_channel(channel_id: str, data: ChannelUpdate, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "频道不存在")
    if data.name is not None:
        channel.name = data.name
    if data.pinned is not None:
        channel.pinned = data.pinned
    channel.updated_at = utcnow()
    db.commit()
    db.refresh(channel)
    return channel


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: str, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "频道不存在")
    if channel.is_default:
        raise HTTPException(400, "默认「闲聊」频道不可删除，可以清空聊天记录")
    db.delete(channel)
    db.commit()
    return {"ok": True}


@app.delete("/api/channels/{channel_id}/messages")
def clear_channel_messages(channel_id: str, db: Session = Depends(get_db)):
    """清空频道所有聊天记录"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "频道不存在")
    db.query(Message).filter(Message.channel_id == channel_id).delete()
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════
#  对话消息（场景 + 频道通用）
# ═══════════════════════════════════════
@app.post("/api/messages", response_model=MessageOut)
def send_message(data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到场景（工作模式）"""
    if not data.scene_id:
        raise HTTPException(400, "scene_id 必填")

    scene = db.query(Scene).filter(Scene.id == data.scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    msg = Message(
        id=make_id("msg"),
        scene_id=data.scene_id,
        role="user",
        content=data.content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # AI 引擎处理
    ai_response = ai_process_message(data.scene_id, data.content, data.channel, db)

    ai_msg = Message(
        id=make_id("msg"),
        scene_id=data.scene_id,
        role="ai",
        content=ai_response,
    )
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)

    return msg


@app.post("/api/scenes/{scene_id}/stream")
def stream_scene_message(scene_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到场景 + 流式 SSE 返回 AI 回复

    事件类型（与频道流式一致）:
    - user_msg: 用户消息已保存
    - token: AI 回复的单个 token
    - done: AI 回复完成（含 Thinking Map 更新信息）
    - error: 发生错误
    """
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    # 1. 保存用户消息
    user_msg = Message(
        id=make_id("msg"),
        scene_id=scene_id,
        role="user",
        content=data.content,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    user_msg_json = json.dumps({
        "type": "user_msg",
        "id": user_msg.id,
        "role": "user",
        "content": user_msg.content,
        "created_at": user_msg.created_at.isoformat(),
    }, ensure_ascii=False)

    def generate():
        yield f"data: {user_msg_json}\n\n"

        # ═══ v0.4 约束提取 + 复杂度判定 + 路由 ═══
        nonlocal scene
        scene = db.query(Scene).filter(Scene.id == scene_id).first()

        # 判断是否需要约束提取
        need_extraction = scene.constraints is None or not scene.constraints_locked

        if need_extraction:
            result = extract_and_classify(
                data.content,
                scene.complexity,
                scene.constraints,
            )
            scene.constraints = result["constraints"]
            scene.complexity = result["complexity"]
            scene.constraints_locked = result["constraints_locked"]
            db.commit()
            complexity = result["complexity"]
            constraints_ok = result["constraints_locked"]
            missing_info = result.get("missing_info", [])
        else:
            complexity = scene.complexity or "medium"
            constraints_ok = True
            missing_info = []

        # 选路
        full_reply = ""
        changes = []
        if need_extraction and not constraints_ok and missing_info:
            ai_stream = ai_scene_ask_missing_stream(scene_id, data.content, missing_info, db)
        elif complexity == "light":
            ai_stream = ai_scene_light_chat_stream(scene_id, data.content, db)
        else:
            ai_stream = ai_scene_chat_stream(scene_id, data.content, db, complexity)
        for token in ai_stream:
            if isinstance(token, dict):
                if token.get("_error"):
                    yield f"data: {json.dumps({'type': 'error', 'message': token['message']}, ensure_ascii=False)}\n\n"
                    return
                if token.get("_done"):
                    full_reply = token["reply"]
                    changes = token.get("changes", [])
                break
            full_reply += token
            yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"

        # 保存 AI 消息（用新 session）
        ai_msg_id = make_id("msg")
        new_db = SessionLocal()
        try:
            ai_msg = Message(
                id=ai_msg_id,
                scene_id=scene_id,
                role="ai",
                content=full_reply,
            )
            new_db.add(ai_msg)
            new_db.commit()
            new_db.refresh(ai_msg)
            done_json = json.dumps({
                "type": "done",
                "id": ai_msg.id,
                "role": "ai",
                "content": full_reply,
                "created_at": ai_msg.created_at.isoformat(),
                "changes": changes,
            }, ensure_ascii=False)
            yield f"data: {done_json}\n\n"
        except Exception as e:
            print(f"[scene stream save error] {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI 回复保存失败'}, ensure_ascii=False)}\n\n"
        finally:
            new_db.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/channels/{channel_id}/messages", response_model=MessageOut)
def send_channel_message(channel_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到频道（闲聊模式）"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "频道不存在")

    msg = Message(
        id=make_id("msg"),
        channel_id=channel_id,
        role="user",
        content=data.content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # 获取频道历史
    history = (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    history.reverse()  # 时间正序

    # AI 聊天回复
    ai_response = ai_channel_chat(
        [{"role": m.role, "content": m.content} for m in history],
        is_default=channel.is_default,
    )

    ai_msg = Message(
        id=make_id("msg"),
        channel_id=channel_id,
        role="ai",
        content=ai_response,
    )
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)

    return msg


@app.post("/api/channels/{channel_id}/stream")
def stream_channel_message(channel_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到频道 + 流式 SSE 返回 AI 回复

    事件类型:
    - user_msg: 用户消息已保存（包含服务器 ID）
    - token: AI 回复的单个 token
    - done: AI 回复完成（包含完整消息 ID 和内容）
    - error: 发生错误
    """
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "频道不存在")

    # 1. 保存用户消息
    user_msg = Message(
        id=make_id("msg"),
        channel_id=channel_id,
        role="user",
        content=data.content,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 2. 获取频道历史（在 session 关闭前）
    history = (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    history.reverse()
    history_dicts = [{"role": m.role, "content": m.content} for m in history]

    # 3. 准备用户消息 SSE 数据
    user_msg_json = json.dumps({
        "type": "user_msg",
        "id": user_msg.id,
        "role": "user",
        "content": user_msg.content,
        "created_at": user_msg.created_at.isoformat(),
    }, ensure_ascii=False)

    # 4. 同步生成器（StreamingResponse 在 thread pool 中运行）
    def generate():
        # 先推送用户消息
        yield f"data: {user_msg_json}\n\n"

        # 流式调用 Qwen
        full_content = ""
        for token in ai_channel_chat_stream(history_dicts, is_default=channel.is_default):
            if token is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'AI 引擎响应失败'}, ensure_ascii=False)}\n\n"
                return
            full_content += token
            yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"

        # 保存 AI 消息到 DB（新 session）
        ai_msg_id = make_id("msg")
        new_db = SessionLocal()
        try:
            ai_msg = Message(
                id=ai_msg_id,
                channel_id=channel_id,
                role="ai",
                content=full_content,
            )
            new_db.add(ai_msg)
            new_db.commit()
            new_db.refresh(ai_msg)
            done_json = json.dumps({
                "type": "done",
                "id": ai_msg.id,
                "role": "ai",
                "content": full_content,
                "created_at": ai_msg.created_at.isoformat(),
            }, ensure_ascii=False)
            yield f"data: {done_json}\n\n"
        except Exception as e:
            print(f"[stream save error] {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI 回复保存失败'}, ensure_ascii=False)}\n\n"
        finally:
            new_db.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/scenes/{scene_id}/messages", response_model=List[MessageOut])
def list_scene_messages(scene_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Message)
        .filter(Message.scene_id == scene_id)
        .order_by(Message.created_at.asc())
        .all()
    )


@app.get("/api/channels/{channel_id}/messages", response_model=List[MessageOut])
def list_channel_messages(channel_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .order_by(Message.created_at.asc())
        .all()
    )


@app.delete("/api/messages/{message_id}")
def delete_message(message_id: str, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(404, "消息不存在")
    db.delete(msg)
    db.commit()
    return {"ok": True}


@app.post("/api/messages/{message_id}/regenerate", response_model=MessageOut)
def regenerate_message(message_id: str, db: Session = Depends(get_db)):
    """重新生成 AI 回复（删除原 AI 消息后重新生成）"""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(404, "消息不存在")
    if msg.role != "ai":
        raise HTTPException(400, "只能重新生成 AI 回复")

    # 找到这条 AI 消息之前的最后一条用户消息
    prev_user = (
        db.query(Message)
        .filter(
            Message.scene_id == msg.scene_id if msg.scene_id is not None else True,
            Message.channel_id == msg.channel_id if msg.channel_id is not None else True,
            Message.role == "user",
            Message.created_at < msg.created_at,
        )
        .order_by(Message.created_at.desc())
        .first()
    )

    if not prev_user:
        raise HTTPException(400, "找不到对应的用户消息")

    # 删除旧 AI 回复
    db.delete(msg)
    db.commit()

    # 重新生成
    if msg.scene_id:
        ai_response = ai_process_message(msg.scene_id, prev_user.content, "main", db)
        ai_msg = Message(
            id=make_id("msg"),
            scene_id=msg.scene_id,
            role="ai",
            content=ai_response,
        )
    else:
        channel_id = msg.channel_id
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        history = (
            db.query(Message)
            .filter(Message.channel_id == channel_id)
            .order_by(Message.created_at.desc())
            .limit(20)
            .all()
        )
        history.reverse()
        ai_response = ai_channel_chat(
            [{"role": m.role, "content": m.content} for m in history],
            is_default=channel.is_default if channel else False,
        )
        ai_msg = Message(
            id=make_id("msg"),
            channel_id=channel_id,
            role="ai",
            content=ai_response,
        )

    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)
    return ai_msg


# ═══════════════════════════════════════
#  Action Map CRUD
# ═══════════════════════════════════════
@app.post("/api/action-maps", response_model=ActionMapOut)
def create_action_map(data: ActionMapCreate, db: Session = Depends(get_db)):
    """从一个 Thinking Map 可执行叶子节点创建 Action Map"""
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == data.think_map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    node = db.query(ThinkNode).filter(ThinkNode.id == data.think_node_id).first()
    if not node:
        raise HTTPException(404, "ThinkNode 不存在")
    if not node.actionable:
        raise HTTPException(400, "此节点未标记为可执行")

    # 创建 Action Map
    amap = ActionMap(
        id=make_id("action"),
        think_map_id=data.think_map_id,
        think_node_id=data.think_node_id,
        title=data.title,
        status="draft",
    )
    db.add(amap)
    db.flush()

    # 批量创建节点
    for n in data.nodes:
        an = ActionNode(
            id=n.id,
            map_id=amap.id,
            type=n.type,
            label=n.label,
            requires_approval=n.requires_approval,
            timeout=n.timeout,
            retry=n.retry,
            verification=n.verification.model_dump() if n.verification else None,
            fallback_node=n.fallback_node,
            order_index=n.order_index,
            position_x=n.position_x,
            position_y=n.position_y,
        )
        db.add(an)

    # 批量创建边
    for e in data.edges:
        ae = ActionEdge(
            id=e.id,
            map_id=amap.id,
            from_node_id=e.from_node_id,
            to_node_id=e.to_node_id,
            type=e.type,
            label=e.label,
            condition=e.condition,
        )
        db.add(ae)

    # 更新 ThinkNode 关联
    node.linked_action_map = amap.id
    node.action_status = "draft"

    db.commit()
    db.refresh(amap)
    amap.nodes
    amap.edges
    return amap


@app.post("/api/action-maps/generate")
def generate_action_map_stream(data: ActionMapGenerateRequest):
    """调用 Hermes 子进程生成 Action Map（SSE 流式，含日志观察）"""
    def event_stream():
        db = SessionLocal()
        try:
            node = db.query(ThinkNode).filter(ThinkNode.id == data.think_node_id).first()
            if not node:
                yield f"data: {json.dumps({'type': 'error', 'message': 'ThinkNode 不存在'}, ensure_ascii=False)}\n\n"
                return
            if not node.actionable:
                yield f"data: {json.dumps({'type': 'error', 'message': '此节点未标记为可执行'}, ensure_ascii=False)}\n\n"
                return

            tmap = db.query(ThinkingMap).filter(ThinkingMap.id == node.map_id).first()
            if not tmap:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Thinking Map 不存在'}, ensure_ascii=False)}\n\n"
                return

            # 流式调用 Hermes
            action_map_json = None
            for event in call_hermes_action_map(data.think_node_id, db):
                if event["type"] == "hermes_log":
                    yield f"data: {json.dumps({'type': 'hermes_log', 'line': event['line']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "status":
                    yield f"data: {json.dumps({'type': 'status', 'line': event['line']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "result":
                    action_map_json = event.get("action_map")
                elif event["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': event['message']}, ensure_ascii=False)}\n\n"
                    db.close()
                    return

            if not action_map_json or not action_map_json.get("nodes"):
                yield f"data: {json.dumps({'type': 'error', 'message': '生成的节点为空'}, ensure_ascii=False)}\n\n"
                db.close()
                return

            # 保存到数据库 — 先重映射节点 ID，避免重复
            base_title = action_map_json.get("title", f"{node.label} · 行动计划")
            # 标题去重：同一 think_node 下已有同名 Action Map 则追加 _N
            existing_count = db.query(ActionMap).filter(
                ActionMap.think_node_id == node.id
            ).count()
            title = f"{base_title}_{existing_count + 1}" if existing_count > 0 else base_title
            gen_nodes = action_map_json.get("nodes", [])
            gen_edges = action_map_json.get("edges", [])

            # ID 映射：Hermes 的泛用 ID → 唯一 ID
            id_map = {}
            for n in gen_nodes:
                old_id = n.get("id", "")
                new_id = make_id("an")
                id_map[old_id] = new_id
                n["_new_id"] = new_id

            amap = ActionMap(
                id=make_id("action"),
                think_map_id=tmap.id,
                think_node_id=node.id,
                title=title,
                status="draft",
            )
            db.add(amap)
            db.flush()

            for n in gen_nodes:
                an = ActionNode(
                    id=n["_new_id"],
                    map_id=amap.id,
                    type=n.get("type", "exec"),
                    label=n.get("label", ""),
                    requires_approval=n.get("requires_approval", False),
                    timeout=n.get("timeout", 300),
                    retry=n.get("retry", 0),
                    verification=n.get("verification"),
                    fallback_node=id_map.get(n.get("fallback_node")) if n.get("fallback_node") else None,
                    order_index=n.get("order_index", 0),
                    position_x=n.get("position_x"),
                    position_y=n.get("position_y"),
                )
                db.add(an)

            for e in gen_edges:
                ae = ActionEdge(
                    id=make_id("ae"),
                    map_id=amap.id,
                    from_node_id=id_map.get(e.get("from_node_id", ""), e.get("from_node_id", "")),
                    to_node_id=id_map.get(e.get("to_node_id", ""), e.get("to_node_id", "")),
                    type=e.get("type", "flow"),
                    label=e.get("label"),
                    condition=e.get("condition"),
                )
                db.add(ae)

            # 更新 ThinkNode 关联
            node.linked_action_map = amap.id
            node.action_status = "draft"

            db.commit()
            db.refresh(amap)
            # 预加载关系
            amap.nodes
            amap.edges

            # 序列化返回
            result = {
                "id": amap.id,
                "think_map_id": amap.think_map_id,
                "think_node_id": amap.think_node_id,
                "title": amap.title,
                "status": amap.status,
                "replan_count": amap.replan_count,
                "dynamic_nodes": amap.dynamic_nodes,
                "created_at": amap.created_at.isoformat() if amap.created_at else None,
                "updated_at": amap.updated_at.isoformat() if amap.updated_at else None,
                "nodes": [
                    {
                        "id": n.id, "map_id": n.map_id, "type": n.type, "label": n.label,
                        "status": n.status,
                        "requires_approval": n.requires_approval, "timeout": n.timeout, "retry": n.retry,
                        "retry_count": n.retry_count, "origin": n.origin,
                        "verification": n.verification, "fallback_node": n.fallback_node,
                        "result_summary": n.result_summary, "artifacts": n.artifacts,
                        "order_index": n.order_index, "position_x": n.position_x, "position_y": n.position_y,
                        "started_at": n.started_at.isoformat() if n.started_at else None,
                        "completed_at": n.completed_at.isoformat() if n.completed_at else None,
                    }
                    for n in amap.nodes
                ],
                "edges": [
                    {
                        "id": e.id, "map_id": e.map_id,
                        "from_node_id": e.from_node_id, "to_node_id": e.to_node_id,
                        "type": e.type, "label": e.label, "condition": e.condition,
                    }
                    for e in amap.edges
                ],
            }
            yield f"data: {json.dumps({'type': 'result', 'action_map': result}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'服务器异常: {e}'}, ensure_ascii=False)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/action-maps", response_model=List[ActionMapOut])
def list_action_maps(
    think_map_id: Optional[str] = None,
    think_node_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """列出 Action Map（可按 Thinking Map 或节点过滤）"""
    q = db.query(ActionMap)
    if think_map_id:
        q = q.filter(ActionMap.think_map_id == think_map_id)
    if think_node_id:
        q = q.filter(ActionMap.think_node_id == think_node_id)
    results = q.order_by(ActionMap.updated_at.desc()).all()
    for am in results:
        am.nodes
        am.edges
    return results


@app.get("/api/action-maps/{action_map_id}", response_model=ActionMapOut)
def get_action_map(action_map_id: str, db: Session = Depends(get_db)):
    """获取单个 Action Map 的完整结构（含节点和边）"""
    amap = db.query(ActionMap).filter(ActionMap.id == action_map_id).first()
    if not amap:
        raise HTTPException(404, "Action Map 不存在")
    amap.nodes
    amap.edges
    return amap


@app.patch("/api/action-maps/{action_map_id}/status")
def update_action_map_status(
    action_map_id: str,
    data: ActionMapStatusUpdate,
    db: Session = Depends(get_db),
):
    """更新 Action Map 状态（draft→ready→running→paused/completed/failed）"""
    amap = db.query(ActionMap).filter(ActionMap.id == action_map_id).first()
    if not amap:
        raise HTTPException(404, "Action Map 不存在")
    amap.status = data.status
    amap.updated_at = utcnow()

    # 同步更新关联的 ThinkNode
    node = db.query(ThinkNode).filter(ThinkNode.id == amap.think_node_id).first()
    if node:
        node.action_status = data.status

    db.commit()
    return {"ok": True, "status": data.status}


@app.patch("/api/action-maps/{action_map_id}/nodes/{node_id}")
def update_action_node(
    action_map_id: str,
    node_id: str,
    data: ActionNodeStatusUpdate,
    db: Session = Depends(get_db),
):
    """更新单个 Action Node 的状态"""
    node = db.query(ActionNode).filter(
        ActionNode.id == node_id,
        ActionNode.map_id == action_map_id,
    ).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    node.status = data.status
    if data.status == "running":
        node.started_at = utcnow()
    elif data.status in ("completed", "failed", "timeout"):
        node.completed_at = utcnow()
    db.commit()
    return {"ok": True}


@app.delete("/api/action-maps/{action_map_id}")
def delete_action_map(action_map_id: str, db: Session = Depends(get_db)):
    """删除 Action Map"""
    amap = db.query(ActionMap).filter(ActionMap.id == action_map_id).first()
    if not amap:
        raise HTTPException(404, "Action Map 不存在")

    # 清除 ThinkNode 关联
    node = db.query(ThinkNode).filter(ThinkNode.id == amap.think_node_id).first()
    if node and node.linked_action_map == amap.id:
        node.linked_action_map = None
        node.action_status = None

    db.delete(amap)
    db.commit()
    return {"ok": True}


@app.post("/api/action-maps/{action_map_id}/execute")
def execute_action_map(action_map_id: str):
    """执行 Action Map 全部节点（SSE 流式，含日志持久化 + 聊天消息）"""
    def _log(db, mid, nid, nlabel, etype, line=None, status=None, result=None):
        db.add(ActionExecutionLog(
            id=make_id("aelog"), map_id=mid, node_id=nid,
            node_label=nlabel, event_type=etype,
            line=line, status=status, result=result,
        ))
        db.commit()  # 立即持久化，防止中途崩溃丢失日志

    def event_stream():
        db = SessionLocal()
        try:
            amap = db.query(ActionMap).filter(ActionMap.id == action_map_id).first()
            if not amap:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Action Map 不存在'}, ensure_ascii=False)}\n\n"
                db.close()
                return

            nodes = db.query(ActionNode).filter(
                ActionNode.map_id == action_map_id
            ).order_by(ActionNode.order_index).all()

            if not nodes:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Action Map 无节点'}, ensure_ascii=False)}\n\n"
                db.close()
                return

            amap.status = "running"
            db.commit()
            yield f"data: {json.dumps({'type': 'map_status', 'status': 'running'}, ensure_ascii=False)}\n\n"

            failed = False
            node_results = []  # 收集节点结果用于聊天消息

            for node in nodes:
                if failed:
                    break

                # 跳过已完成的节点（支持暂停→继续，不重复执行）
                if node.status == "completed":
                    node_results.append({"label": node.label, "result": node.result_summary or "", "status": "completed"})
                    continue

                ntype = node.type

                if ntype in ("start", "milestone", "end"):
                    node.status = "completed"
                    node.completed_at = utcnow()
                    db.commit()
                    _log(db, action_map_id, node.id, node.label, "node_done", status="completed")
                    yield f"data: {json.dumps({'type': 'node_done', 'node_id': node.id, 'status': 'completed', 'label': node.label}, ensure_ascii=False)}\n\n"
                    continue

                if ntype == "decision":
                    node.status = "completed"
                    node.completed_at = utcnow()
                    db.commit()
                    _log(db, action_map_id, node.id, node.label, "node_done", status="completed")
                    yield f"data: {json.dumps({'type': 'node_done', 'node_id': node.id, 'status': 'completed', 'label': node.label}, ensure_ascii=False)}\n\n"
                    continue

                if ntype == "exec":
                    max_attempts = (node.retry or 0) + 1
                    result_text = ""
                    exec_ok = False

                    for attempt in range(1, max_attempts + 1):
                        if attempt > 1:
                            # 真·重试：重新调 Hermes 子进程执行
                            node.retry_count = attempt - 1
                            node.status = "running"
                            node.started_at = utcnow()
                            db.commit()
                            _log(db, action_map_id, node.id, node.label, "node_retry",
                                 line=f"重试第 {attempt - 1} 次（共 {max_attempts - 1} 次）")
                            yield f"data: {json.dumps({'type': 'node_retry', 'node_id': node.id, 'label': node.label, 'retry': attempt - 1}, ensure_ascii=False)}\n\n"
                        else:
                            # 首次执行
                            node.status = "running"
                            node.started_at = utcnow()
                            db.commit()
                            _log(db, action_map_id, node.id, node.label, "node_start")
                            yield f"data: {json.dumps({'type': 'node_start', 'node_id': node.id, 'label': node.label}, ensure_ascii=False)}\n\n"

                        result_text = ""
                        exec_ok = False

                        for event in call_hermes_execute_node(
                            node_id=node.id, node_label=node.label,
                            node_type=node.type, verification=node.verification,
                            timeout=node.timeout or 300,
                        ):
                            if event["type"] in ("hermes_log", "status"):
                                _log(db, action_map_id, node.id, node.label, "hermes_log", line=event["line"])
                                yield f"data: {json.dumps({'type': 'hermes_log', 'node_id': node.id, 'line': event['line']}, ensure_ascii=False)}\n\n"
                            elif event["type"] == "result":
                                result_text = event["text"]
                                exec_ok = True
                            elif event["type"] == "error":
                                result_text = event["message"]
                                exec_ok = False
                                break

                        if exec_ok:
                            # 成功 → 退出重试循环
                            node.status = "completed"
                            node.result_summary = result_text
                            node.completed_at = utcnow()
                            db.commit()
                            node_results.append({"label": node.label, "result": result_text, "status": "completed"})
                            _log(db, action_map_id, node.id, node.label, "node_done", status="completed", result=result_text[:500])
                            yield f"data: {json.dumps({'type': 'node_done', 'node_id': node.id, 'status': 'completed', 'label': node.label, 'result': result_text[:200]}, ensure_ascii=False)}\n\n"
                            break
                    else:
                        # 所有重试次数耗尽
                        node.status = "failed"
                        node.retry_count = max_attempts - 1
                        node.result_summary = result_text or f"重试 {max_attempts - 1} 次后仍失败"
                        node.completed_at = utcnow()
                        db.commit()
                        failed = True
                        node_results.append({"label": node.label, "result": node.result_summary, "status": "failed"})
                        _log(db, action_map_id, node.id, node.label, "node_done", status="failed", result=(result_text or "")[:500])
                        yield f"data: {json.dumps({'type': 'node_done', 'node_id': node.id, 'status': 'failed', 'label': node.label, 'result': (result_text or '')[:200]}, ensure_ascii=False)}\n\n"

            # 更新 map 最终状态
            amap.status = "completed" if not failed else "failed"
            db.commit()
            _log(db, action_map_id, None, None, "map_done", status=amap.status)
            yield f"data: {json.dumps({'type': 'map_done', 'status': amap.status}, ensure_ascii=False)}\n\n"

            # ═══ 工具自文档化钩子 ═══
            new_tools = []
            if amap.status == "completed":
                try:
                    new_tools = scan_and_document_tools(action_map_id)
                    if new_tools:
                        tools_data = [{"name": t["name"], "description": t.get("description", "")} for t in new_tools]
                        _log(db, action_map_id, None, None, "tools_documented",
                             line=f"新增 {len(new_tools)} 个工具: {', '.join(t['name'] for t in new_tools)}")
                        yield f"data: {json.dumps({'type': 'tools_documented', 'count': len(new_tools), 'tools': tools_data}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    print(f"[ToolDocs hook] {e}")

            # ═══ 创建聊天消息 ═══
            try:
                # 查 scene_id: ActionMap → ThinkingMap → Scene
                tmap = db.query(ThinkingMap).filter(ThinkingMap.id == amap.think_map_id).first()
                if tmap:
                    scene = db.query(Scene).filter(Scene.id == tmap.scene_id).first()
                    if scene:
                        completed_count = sum(1 for r in node_results if r["status"] == "completed")
                        failed_count = sum(1 for r in node_results if r["status"] == "failed")
                        total_count = len(node_results)

                        # ═══ 统计表格 ═══
                        lines = [f"⚡ **Action Map 执行完成** — {amap.title}\n"]
                        lines.append("| Action | ✅ 成功 | ❌ 失败 | 📊 总计 |")
                        lines.append("|--------|--------|--------|--------|")
                        lines.append(f"| {amap.title} | {completed_count} | {failed_count} | {total_count} |")
                        lines.append("")

                        # ═══ Qwen 整理调研成果 ═══
                        qwen_report = ""
                        if node_results:
                            # 获取 action 目的（从 ThinkNode label）
                            think_node = db.query(ThinkNode).filter(ThinkNode.id == amap.think_node_id).first()
                            purpose = think_node.label if think_node else amap.title

                            # 收集所有节点的完整结果（不截断，全部交给 LLM）
                            all_results = "\n\n".join(
                                f"## {r['label']}（{r['status']}）\n{r['result'] or '(无输出)'}"
                                for r in node_results
                            )

                            qwen_messages = [
                                {"role": "system", "content": "你是一个专业的执行结果整理助手。请把执行结果整理成简洁的报告。"},
                                {"role": "user", "content": f"""请将以下 Action Map 执行结果整理成一份报告。

## Action 目的
{purpose}

## 执行统计
- 总节点: {total_count}
- 成功: {completed_count}
- 失败: {failed_count}

## 各节点执行结果
{all_results}

请用 Markdown 格式整理，包含：
1. **总体概述**（1-2 句，说明完成了什么）
2. **关键产出**（每个成功节点的核心成果，提炼要点）
3. **问题与建议**（如有失败节点，简要说明并给出建议）

保持简洁，300-500 字。直接输出内容，不要用代码块包裹。"""}
                            ]

                            try:
                                qwen_report = call_qwen_chat(qwen_messages, temperature=0.3) or ""
                            except Exception as e:
                                print(f"[Qwen report] 整理失败: {e}")

                        if qwen_report:
                            lines.append("### 📊 执行报告\n")
                            lines.append(qwen_report)
                            lines.append("")
                        elif node_results:
                            # Qwen 失败则回退到直接展示每个节点的结果
                            lines.append("---\n")
                            for r in node_results:
                                icon = "✅" if r["status"] == "completed" else "❌"
                                lines.append(f"**{icon} {r['label']}**\n{r['result'] or '(无输出)'}\n")

                        # ═══ 约束校验 ═══
                        if scene.constraints and scene.constraints_locked:
                            try:
                                c_json = json.dumps(scene.constraints, ensure_ascii=False, indent=2)
                                all_results_text = "\n\n".join(
                                    f"## {r['label']}（{r['status']}）\n{r['result'] or '(无输出)'}"
                                    for r in node_results
                                ) if node_results else "(无执行结果)"
                                verify_msg = [
                                    {"role": "system", "content": "你是一个约束校验引擎。检查执行结果是否满足原始约束条件，逐条输出校验结果。"},
                                    {"role": "user", "content": f"""## 原始约束
{c_json}

## 执行结果摘要
{all_results_text[:3000]}

请逐条检查每条约束是否被满足，输出格式（Markdown）：
✅ 约束名称：结论（证据）
❌ 约束名称：问题说明"""},
                                ]
                                vr = call_qwen_chat(verify_msg, temperature=0.3)
                                if vr and vr.strip():
                                    lines.append("")
                                    lines.append("### ✅ 约束校验\n")
                                    lines.append(vr.strip())
                                    lines.append("")
                            except Exception as e:
                                print(f"[Constraint verify] 失败: {e}")

                        if new_tools:
                            tool_names = " · ".join(f"`{t['name']}`" for t in new_tools)
                            lines.append(f"\n🔧 新增 {len(new_tools)} 个工具: {tool_names}")

                        content = "\n".join(lines)
                        msg = Message(
                            id=make_id("msg"),
                            scene_id=scene.id, channel_id=None,
                            role="ai", content=content,
                            map_ref=action_map_id,
                        )
                        db.add(msg)
                        db.commit()
            except Exception as e:
                print(f"[ChatMsg] 创建聊天消息失败: {e}")

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'执行异常: {e}'}, ensure_ascii=False)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/action-maps/{action_map_id}/logs")
def get_action_map_logs(action_map_id: str, db: Session = Depends(get_db)):
    """获取 Action Map 的执行日志"""
    logs = db.query(ActionExecutionLog).filter(
        ActionExecutionLog.map_id == action_map_id
    ).order_by(ActionExecutionLog.created_at).all()
    return [
        {
            "id": log.id,
            "node_id": log.node_id,
            "node_label": log.node_label,
            "event_type": log.event_type,
            "line": log.line,
            "status": log.status,
            "result": log.result,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@app.get("/api/tools/{tool_name}/skill")
def get_tool_skill(tool_name: str):
    """读取工具的 SKILL.md，返回 markdown 原文"""
    import os
    skill_path = os.path.expanduser(f"~/zuoshanke/tools/{tool_name}/SKILL.md")
    if not os.path.isfile(skill_path):
        raise HTTPException(404, f"工具 '{tool_name}' 的文档不存在")
    with open(skill_path, "r") as f:
        content = f.read()
    return {"name": tool_name, "content": content}


# ═══ 启动 ═══
if __name__ == "__main__":
    import uvicorn
    init_db()
    print("✅ 数据库已初始化")
    uvicorn.run(app, host="0.0.0.0", port=8000)
