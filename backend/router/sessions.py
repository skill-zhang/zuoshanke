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
    context_name: str | None = None


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
    cost_source: str | None = None


# ═══ Helper ═══

def _get_or_create_web_session(
    db: DBSession, context_type: str, context_id: str, context_name: str | None = None
) -> WebSession:
    """获取或创建 Web session（每个上下文唯一一个活跃 session）"""
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
        _backfill_null_session_messages(db, context_type, context_id, session.id)
        return session

    # 创建新 session
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
    _backfill_null_session_messages(db, context_type, context_id, session.id)
    return session


def _backfill_null_session_messages(db, context_type: str, context_id: str, session_id: str):
    """将旧的无 session_id 消息归属到当前 session（一次性 backfill）

    同时继承已销毁 session 的消息，避免 session 超时销毁后消息丢失。
    """
    if context_type != "scene":
        return
    from sqlalchemy import or_
    from models import Message, WebSession
    # 找无归属 + 已销毁 session 的旧消息
    destroyed_sids = [
        r[0] for r in db.query(WebSession.id).filter(
            WebSession.context_id == context_id,
            WebSession.status == "destroyed",
        ).all()
    ]
    filters = [Message.scene_id == context_id]
    if destroyed_sids:
        filters.append(or_(
            Message.session_id.is_(None),
            Message.session_id.in_(destroyed_sids),
        ))
    else:
        filters.append(Message.session_id.is_(None))
    tagged = db.query(Message).filter(*filters).update({"session_id": session_id})
    if tagged:
        db.commit()
        import logging
        logging.getLogger(__name__).info(
            f"[session] backfill: 将 {tagged} 条消息归属到 {session_id}"
        )


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
def list_web_sessions(context_type: str | None = None, status: str | None = None, db: DBSession = Depends(get_db)):
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

    Returns: 销毁的 session 数量
    """
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=SESSION_TIMEOUT_HOURS)
    stale = db.query(WebSession).filter(
        WebSession.status == "active",
        WebSession.last_active_at < cutoff,
    ).all()
    now = datetime.utcnow()
    for s in stale:
        s.status = "destroyed"
        s.ended_at = now
        s.duration_seconds = int((now - s.started_at).total_seconds()) if s.started_at else 0
        s.updated_at = now
    if stale:
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
