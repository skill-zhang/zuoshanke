from typing import Optional
"""Schema v1.1 — Session 管理路由

Web 前端会话（闲聊/频道/场景各自独立）的创建、激活、刷新、销毁。
Gateway (外部平台) session 的扩展由 gateway.py 自身管理。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text

from database import get_db
from models import WebSession, GatewaySession, Channel, Scene
from utils import make_id, utcnow
from config.constants import SESSION_TIMEOUT_HOURS

router = APIRouter(tags=["Web Session"])


# ═══ Pydantic models ═══

class CreateOrActivateRequest(BaseModel):
    context_type: str  # "channel" | "scene"
    context_id: str
    context_name: Optional[str] = None


class TouchSessionRequest(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    api_calls: int = 0
    estimated_cost_usd: float = 0.0
    cost_status: str = "unknown"
    cost_source: Optional[str] = None


# ═══ Helper ═══

def _get_or_create_web_session(
    db: DBSession, context_type: str, context_id: str, context_name: Optional[str] = None
) -> WebSession:
    """获取或创建 Web session（每个上下文唯一一个活跃 session）

    优先复用活跃 session；若无活跃 session，尝试复活已销毁的同上下文 session
    （UNIQUE(context_type, context_id) 约束导致不能创建重复行）；都无则新建。
    """
    # 1. 找活跃 session
    session = db.query(WebSession).filter(
        WebSession.context_type == context_type,
        WebSession.context_id == context_id,
        WebSession.status == "active",
    ).first()

    if session:
        session.last_active_at = utcnow()
        session.updated_at = utcnow()
        if context_name:
            session.context_name = context_name
        db.commit()
        db.refresh(session)
        return session

    # 2. 不超过 UNIQUE 约束：找已销毁的同上下文 session 并复活
    destroyed = db.query(WebSession).filter(
        WebSession.context_type == context_type,
        WebSession.context_id == context_id,
    ).first()

    if destroyed:
        destroyed.status = "active"
        destroyed.started_at = utcnow()
        destroyed.last_active_at = utcnow()
        destroyed.ended_at = None
        destroyed.duration_seconds = None
        if context_name:
            destroyed.context_name = context_name
        db.commit()
        db.refresh(destroyed)
        return destroyed

    # 3. 完全新建
    session = WebSession(
        id=make_id("ws"),
        context_type=context_type,
        context_id=context_id,
        context_name=context_name,
        status="active",
        started_at=utcnow(),
        last_active_at=utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _find_active_web_session(db: DBSession, context_type: str, context_id: str) -> WebSession | None:
    """查找指定上下文的活跃 session"""
    return db.query(WebSession).filter(
        WebSession.context_type == context_type,
        WebSession.context_id == context_id,
        WebSession.status == "active",
    ).first()


def _web_session_to_dict(s: WebSession) -> dict:
    return {
        "id": s.id,
        "context_type": s.context_type,
        "context_id": s.context_id,
        "context_name": s.context_name,
        "status": s.status,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
        "duration_seconds": s.duration_seconds,
        "prompt_tokens": s.prompt_tokens,
        "completion_tokens": s.completion_tokens,
        "total_tokens": s.total_tokens,
        "input_tokens": s.input_tokens,
        "output_tokens": s.output_tokens,
        "cache_read_tokens": s.cache_read_tokens,
        "cache_write_tokens": s.cache_write_tokens,
        "reasoning_tokens": s.reasoning_tokens,
        "api_calls": s.api_calls,
        "estimated_cost_usd": s.estimated_cost_usd,
        "cost_status": s.cost_status,
        "cost_source": s.cost_source,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# ═══ API endpoints ═══


@router.post("/api/sessions/activate")
def create_or_activate_session(req: CreateOrActivateRequest, db: DBSession = Depends(get_db)):
    """创建或激活 Web session（sidebar 点击时调用）

    如果该上下文已有活跃 session → 刷新 last_active_at 并返回
    如果没有 → 创建新 session
    """
    # 验证 context 存在
    if req.context_type == "channel":
        obj = db.query(Channel).filter(Channel.id == req.context_id).first()
    elif req.context_type == "scene":
        obj = db.query(Scene).filter(Scene.id == req.context_id).first()
    else:
        raise HTTPException(400, f"无效的 context_type: {req.context_type}")

    if not obj:
        raise HTTPException(404, f"{req.context_type} 不存在")

    session = _get_or_create_web_session(
        db, req.context_type, req.context_id,
        req.context_name or getattr(obj, "name", None),
    )
    return _web_session_to_dict(session)


@router.get("/api/sessions/active")
def get_active_session(context_type: str, context_id: str, db: DBSession = Depends(get_db)):
    """获取指定上下文的活跃 session"""
    session = _find_active_web_session(db, context_type, context_id)
    if not session:
        return None
    return _web_session_to_dict(session)


@router.post("/api/sessions/{session_id}/touch")
def touch_session(session_id: str, db: DBSession = Depends(get_db)):
    """刷新 session 的 last_active_at（发消息时调用）"""
    session = db.query(WebSession).filter(WebSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session 不存在")
    session.last_active_at = utcnow()
    session.updated_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/api/sessions/{session_id}/token")
def accumulate_tokens(session_id: str, data: TouchSessionRequest, db: DBSession = Depends(get_db)):
    """累加 token 用量（LLM 回复完成后调用）"""
    session = db.query(WebSession).filter(WebSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session 不存在")
    session.prompt_tokens += data.prompt_tokens
    session.completion_tokens += data.completion_tokens
    session.total_tokens += data.total_tokens
    session.input_tokens += data.input_tokens
    session.output_tokens += data.output_tokens
    session.cache_read_tokens += data.cache_read_tokens
    session.cache_write_tokens += data.cache_write_tokens
    session.reasoning_tokens += data.reasoning_tokens
    session.api_calls += data.api_calls
    session.estimated_cost_usd += data.estimated_cost_usd
    if data.cost_status != "unknown":
        session.cost_status = data.cost_status
    if data.cost_source:
        session.cost_source = data.cost_source
    session.last_active_at = utcnow()
    session.updated_at = utcnow()
    db.commit()
    return {"ok": True}


@router.get("/api/sessions")
def list_web_sessions(context_type: Optional[str] = None, status: Optional[str] = None, db: DBSession = Depends(get_db)):
    """列出 Web session，可按 context_type 和 status 筛选"""
    q = db.query(WebSession)
    if context_type:
        q = q.filter(WebSession.context_type == context_type)
    if status:
        q = q.filter(WebSession.status == status)
    sessions = q.order_by(WebSession.last_active_at.desc()).limit(100).all()
    return [_web_session_to_dict(s) for s in sessions]


# ═══ 超时清理 ═══

def destroy_stale_web_sessions(db: DBSession) -> int:
    """销毁所有超过 SESSION_TIMEOUT_HOURS 的活跃 Web session

    销毁前触发记忆提取，将未提取的消息打标 memory_extracted=True，
    确保旧对话的信息被持久化，同时后续新 session 的 context 不混入旧消息。

    Returns: 销毁的 session 数量
    """
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=SESSION_TIMEOUT_HOURS)
    stale = db.query(WebSession).filter(
        WebSession.status == "active",
        WebSession.last_active_at < cutoff,
    ).all()
    if not stale:
        return 0

    # 记忆提取：销毁前处理未提取的消息
    from models import Message
    from agent_core.memory_extractor import extract_from_conversation, save_extracted_memories
    for s in stale:
        if s.context_type != "scene":
            continue
        try:
            unprocessed = db.query(Message).filter(
                Message.scene_id == s.context_id,
                Message.session_id == s.id,
                Message.memory_extracted == False,
                Message.role.in_(["user", "ai"]),
            ).order_by(Message.created_at.asc()).limit(50).all()
            if len(unprocessed) >= 2:
                msgs_dict = [{"role": m.role, "content": m.content} for m in unprocessed]
                entries = extract_from_conversation(msgs_dict, scene_name=s.context_name or "")
                if entries:
                    save_extracted_memories(db, entries, s.context_id, scene_name=s.context_name or "")
                # 打标
                for m in unprocessed:
                    m.memory_extracted = True
                db.commit()
        except Exception:
            db.rollback()

    # 标记销毁
    now = datetime.utcnow()
    for s in stale:
        s.status = "destroyed"
        s.ended_at = now
        s.duration_seconds = int((now - s.started_at).total_seconds()) if s.started_at else 0
        s.updated_at = now
    db.commit()
    return len(stale)


def destroy_stale_gateway_sessions(db: DBSession) -> int:
    """销毁所有超过 SESSION_TIMEOUT_HOURS 的活跃 Gateway session"""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.utcnow() - timedelta(hours=SESSION_TIMEOUT_HOURS)
    stale = db.query(GatewaySession).filter(
        GatewaySession.status == "active",
        GatewaySession.last_active_at < cutoff,
    ).all()
    now = utcnow()
    for s in stale:
        s.status = "destroyed"
        s.ended_at = now
        s.duration_seconds = int((now - s.started_at).total_seconds()) if s.started_at else 0
        s.updated_at = now
    if stale:
        db.commit()
    return len(stale)


def cleanup_all_stale_sessions(db: DBSession) -> dict:
    """清理所有类型的旧 session（启动时 + 定时任务调用）"""
    return {
        "web_sessions_destroyed": destroy_stale_web_sessions(db),
        "gateway_sessions_destroyed": destroy_stale_gateway_sessions(db),
    }
