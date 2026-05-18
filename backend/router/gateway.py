"""多平台网关 — 语境路由

外部平台（微信/Telegram等）消息统一入口，根据 GatewaySession 状态路由到
频道闲聊或场景对话，返回文本回复给 Gateway 进程转发。
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, SessionLocal
from models import Channel, Message, GatewaySession, Scene
from schemas import GatewayChatRequest, GatewayChatResponse
from ai_engine import ai_channel_chat, call_qwen_chat, _build_channel_messages
from utils import make_id, utcnow

# ── 历史消息时间闸（只加载最近 N 小时内的消息） ──
HISTORY_TIME_WINDOW_HOURS = 2

router = APIRouter(tags=["网关"])

SESSION_TIMEOUT_MINUTES = 5  # 场景模式下无消息自动超时回到频道


def _get_or_create_session(db: Session, platform: str, platform_user_id: str,
                           platform_username: str | None = None) -> GatewaySession:
    """查或创建 GatewaySession（同一平台+用户唯一）"""
    session = db.query(GatewaySession).filter(
        GatewaySession.platform == platform,
        GatewaySession.platform_user_id == platform_user_id,
    ).first()

    if not session:
        # 绑定默认「闲聊」频道
        default_channel = db.query(Channel).filter(Channel.is_default == True).first()
        session = GatewaySession(
            id=make_id("gs"),
            platform=platform,
            platform_user_id=platform_user_id,
            platform_username=platform_username,
            mode="channel",
            channel_id=default_channel.id if default_channel else None,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    elif platform_username and session.platform_username != platform_username:
        session.platform_username = platform_username
        db.commit()

    return session


def _check_scene_timeout(db: Session, session: GatewaySession) -> bool:
    """场景模式下超过 SESSION_TIMEOUT_MINUTES 无消息则自动退回到频道"""
    from datetime import datetime, timezone
    if session.mode != "scene" or not session.last_active_at:
        return False

    now = datetime.now(timezone.utc)
    # last_active_at 可能是 naive datetime，需要处理
    last = session.last_active_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    if (now - last).total_seconds() > SESSION_TIMEOUT_MINUTES * 60:
        session.mode = "channel"
        session.scene_id = None
        session.scene_name = None
        db.commit()
        return True
    return False


def _get_channel_history(db: Session, channel_id: str, limit: int = 20) -> list[dict]:
    """取频道最近历史消息（时间闸 2 小时 + 最多 20 条，正序）"""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HISTORY_TIME_WINDOW_HOURS)
    msgs = db.query(Message).filter(
        Message.channel_id == channel_id,
        Message.created_at >= cutoff
    ).order_by(Message.created_at.desc()).limit(limit).all()
    msgs.reverse()
    return [{"role": m.role, "content": m.content} for m in msgs]


def _get_scene_history(db: Session, scene_id: str, limit: int = 20) -> list[dict]:
    """取场景最近历史消息（时间闸 2 小时 + 最多 20 条，正序）"""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HISTORY_TIME_WINDOW_HOURS)
    msgs = db.query(Message).filter(
        Message.scene_id == scene_id,
        Message.created_at >= cutoff
    ).order_by(Message.created_at.desc()).limit(limit).all()
    msgs.reverse()
    return [{"role": m.role, "content": m.content} for m in msgs]


def _detect_scene_switch(content: str) -> str | None:
    """关键词检测用户消息是否意图切换到某个场景

    返回场景名（匹配时）或 None（不匹配）。
    后续可升级为轻量 LLM 判断。
    """
    content_lower = content.lower()

    # 天气场景
    weather_kw = ["天气", "气温", "温度", "下雨", "下雪", "刮风", "台风", "晴", "阴天"]
    if any(kw in content for kw in weather_kw):
        return "天气查询"

    # 景点推荐
    travel_kw = ["去哪玩", "推荐景点", "好玩", "旅游", "景点", "附近"]
    if any(kw in content for kw in travel_kw):
        return "旅游推荐"

    # 搜索 / 查资料
    search_kw = ["搜索", "查一下", "找一下", "百度", "谷歌", "搜一下"]
    if any(kw in content for kw in search_kw):
        return "信息搜索"

    return None


@router.post("/api/gateway/chat", response_model=GatewayChatResponse)
def gateway_chat(data: GatewayChatRequest, db: Session = Depends(get_db)):
    """Gateway 消息入口：语境路由 + AI 回复"""
    session = _get_or_create_session(db, data.platform, data.platform_user_id, data.platform_username)

    # 检查场景超时
    timed_out = _check_scene_timeout(db, session)

    # 更新最后活跃时间
    session.last_active_at = utcnow()
    db.commit()

    if session.mode == "scene" and session.scene_id:
        # ═══ 场景模式 ═══
        scene = db.query(Scene).filter(Scene.id == session.scene_id).first()
        if not scene:
            # 场景已被删除，退回到频道
            session.mode = "channel"
            session.scene_id = None
            session.scene_name = None
            db.commit()
        else:
            history = _get_scene_history(db, scene.id)
            # 构建带场景上下文的 prompt
            scene_context = f"当前场景：{scene.name}\n场景简介：{scene.description or ''}"
            api_msgs = [
                {"role": "system", "content": f"你是Qwen3.5（通义千问），正在处理以下场景中的用户问题。\n{scene_context}\n请用Markdown格式回复，简洁专业。"},
            ]
            api_msgs += [
                {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
                for m in history
            ]
            api_msgs.append({"role": "user", "content": data.content})

            reply = call_qwen_chat(api_msgs, route="scene")
            if reply is None:
                reply = "抱歉，AI 引擎暂时响应缓慢，请稍候重试。"

            return GatewayChatResponse(
                reply=reply,
                mode="scene",
                scene_id=scene.id,
                scene_name=scene.name,
            )

    # ═══ 频道模式（默认闲聊） ═══
    channel_id = session.channel_id
    if not channel_id:
        # 兜底：找默认频道
        default_ch = db.query(Channel).filter(Channel.is_default == True).first()
        if default_ch:
            channel_id = default_ch.id
            session.channel_id = default_ch.id
            db.commit()
        else:
            raise HTTPException(500, "无可用频道")

    history = _get_channel_history(db, channel_id)
    # 加上当前消息做历史
    history.append({"role": "user", "content": data.content})

    reply = ai_channel_chat(history, is_default=True)
    if reply is None:
        reply = "抱歉，AI 引擎暂时响应缓慢，请稍候重试。"

    # ── 自动场景切换检测（仅在频道模式下） ──
    switch_hint = None
    scene_name = _detect_scene_switch(data.content)
    if scene_name:
        switch_hint = f"检测到您可能需要使用「{scene_name}」场景。发送「/进入{scene_name}」可切换到该场景。"

    return GatewayChatResponse(
        reply=reply,
        mode="channel",
        switch_hint=switch_hint,
    )


@router.post("/api/gateway/switch-scene")
def gateway_switch_scene(data: GatewayChatRequest, db: Session = Depends(get_db)):
    """切换 Gateway 会话到指定场景"""
    session = _get_or_create_session(db, data.platform, data.platform_user_id, data.platform_username)

    scene_name = data.content.strip()
    from config.matching_rules import SCENE_NAME_PREFIX, SCENE_SLASH_PREFIX
    if scene_name.startswith(SCENE_NAME_PREFIX):
        scene_name = scene_name[len(SCENE_NAME_PREFIX):].strip()
    elif scene_name.startswith(SCENE_SLASH_PREFIX):
        scene_name = scene_name[1:].strip()

    # 按名称搜索场景（仅 published 的场景）
    scene = db.query(Scene).filter(
        Scene.name.contains(scene_name),
        Scene.version != "0.0",  # 已发布的场景
    ).first()

    if not scene:
        # 也搜草稿场景
        scene = db.query(Scene).filter(
            Scene.name.contains(scene_name),
        ).first()

    if not scene:
        return {"ok": False, "message": f"未找到场景「{scene_name}」"}

    session.mode = "scene"
    session.scene_id = scene.id
    session.scene_name = scene.name
    session.last_active_at = utcnow()
    db.commit()

    return {
        "ok": True,
        "mode": "scene",
        "scene_id": scene.id,
        "scene_name": scene.name,
        "message": f"已切换到场景「{scene.name}」",
    }


@router.post("/api/gateway/back-to-channel")
def gateway_back_to_channel(data: GatewayChatRequest, db: Session = Depends(get_db)):
    """回到频道闲聊模式"""
    session = _get_or_create_session(db, data.platform, data.platform_user_id, data.platform_username)

    default_ch = db.query(Channel).filter(Channel.is_default == True).first()

    session.mode = "channel"
    session.scene_id = None
    session.scene_name = None
    session.channel_id = default_ch.id if default_ch else session.channel_id
    session.last_active_at = utcnow()
    db.commit()

    return {
        "ok": True,
        "mode": "channel",
        "message": "已回到闲聊模式",
    }
