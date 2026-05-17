"""消息 CRUD（场景消息列表、批量删除、重新生成等）"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Message, Scene, Channel
from schemas import MessageCreate, MessageOut
from ai_engine import ai_process_message, ai_channel_chat
from utils import make_id

router = APIRouter(tags=["消息"])


# ═══ 旧版非流式场景消息 ═══

@router.post("/api/messages", response_model=MessageOut)
def send_message(data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到场景（非流式，旧版）"""
    if not data.scene_id:
        raise HTTPException(400, "scene_id 必填")
    scene = db.query(Scene).filter(Scene.id == data.scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    msg = Message(id=make_id("msg"), scene_id=data.scene_id, role="user", content=data.content)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    ai_response = ai_process_message(data.scene_id, data.content, data.channel, db)
    ai_msg = Message(
        id=make_id("msg"), scene_id=data.scene_id,
        role="ai", content=ai_response, model="Qwen3.5 本地",
    )
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)
    return msg


# ═══ 场景消息列表 / 清空 ═══

@router.get("/api/scenes/{scene_id}/messages", response_model=List[MessageOut])
def list_scene_messages(scene_id: str, session_id: Optional[str] = Query(None),
                         db: Session = Depends(get_db)):
    q = db.query(Message).filter(Message.scene_id == scene_id)
    if session_id:
        q = q.filter(Message.session_id == session_id)
    return q.order_by(Message.created_at.asc()).all()


@router.delete("/api/scenes/{scene_id}/messages")
def clear_scene_messages(scene_id: str, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    deleted = db.query(Message).filter(Message.scene_id == scene_id).delete()
    db.commit()
    return {"ok": True, "deleted": deleted}


# ═══ 频道消息列表 ═══

@router.get("/api/channels/{channel_id}/messages", response_model=List[MessageOut])
def list_channel_messages(channel_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .order_by(Message.created_at.asc())
        .all()
    )


# ═══ 单条消息删除 / 批量删除 ═══

@router.delete("/api/messages/{message_id}")
def delete_message(message_id: str, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(404, "消息不存在")
    db.delete(msg)
    db.commit()
    return {"ok": True}


@router.post("/api/messages/batch-delete")
def batch_delete_messages(data: dict, db: Session = Depends(get_db)):
    ids = data.get("ids", [])
    if not ids:
        return {"ok": True, "deleted": 0}
    deleted = db.query(Message).filter(Message.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": deleted}


# ═══ 重新生成 AI 回复 ═══

@router.post("/api/messages/{message_id}/regenerate", response_model=MessageOut)
def regenerate_message(message_id: str, db: Session = Depends(get_db)):
    """重新生成 AI 回复（删除原 AI 消息后重新生成）"""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(404, "消息不存在")
    if msg.role != "ai":
        raise HTTPException(400, "只能重新生成 AI 回复")

    # 找到上一条用户消息
    prev_user = _find_prev_user_message(db, msg)
    if not prev_user:
        raise HTTPException(400, "找不到对应的用户消息")

    # 删除旧 AI 回复
    db.delete(msg)
    db.commit()

    # 重新生成（场景 vs 频道）
    if msg.scene_id:
        ai_response = ai_process_message(msg.scene_id, prev_user.content, "main", db)
        ai_msg = Message(
            id=make_id("msg"), scene_id=msg.scene_id,
            role="ai", content=ai_response, model="Qwen3.5 本地",
        )
    else:
        channel = db.query(Channel).filter(Channel.id == msg.channel_id).first()
        history = _get_channel_history(db, msg.channel_id)
        ai_response = ai_channel_chat(history, is_default=channel.is_default if channel else False)
        ai_msg = Message(
            id=make_id("msg"), channel_id=msg.channel_id,
            role="ai", content=ai_response, model="Qwen3.5 本地",
        )

    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)
    return ai_msg


# ═══ 辅助函数 ═══

def _find_prev_user_message(db: Session, msg: Message):
    """找到指定 AI 消息之前的最后一条用户消息"""
    from sqlalchemy import and_
    filters = [Message.role == "user", Message.created_at < msg.created_at]
    if msg.scene_id:
        filters.append(Message.scene_id == msg.scene_id)
    if msg.channel_id:
        filters.append(Message.channel_id == msg.channel_id)
    return db.query(Message).filter(and_(*filters)).order_by(Message.created_at.desc()).first()


def _get_channel_history(db: Session, channel_id: str) -> list:
    """获取频道最近 20 条历史（正序 dict 列表）"""
    history = (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    history.reverse()
    return [{"role": m.role, "content": m.content} for m in history]
