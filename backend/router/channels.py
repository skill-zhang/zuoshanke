"""频道 CRUD + 频道流式"""
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import Channel, Message
from schemas import ChannelCreate, ChannelUpdate, ChannelOut, MessageCreate, MessageOut
from ai_engine import ai_channel_chat, ai_channel_chat_stream
from utils import make_id, utcnow
from router.shared import sse_event, sse_response
from agent_core.memory_extractor import MemoryExtractor
from logger import get_logger as _get_logger
_log = _get_logger("router.channels")

router = APIRouter(tags=["频道"])


# ═══ 频道 CRUD ═══

@router.get("/api/channels", response_model=List[ChannelOut])
def list_channels(db: Session = Depends(get_db)):
    return (
        db.query(Channel)
        .order_by(Channel.is_default.desc(), Channel.pinned.desc(), Channel.updated_at.desc())
        .all()
    )


@router.post("/api/channels", response_model=ChannelOut)
def create_channel(data: ChannelCreate, db: Session = Depends(get_db)):
    existing = db.query(Channel).filter(Channel.name == data.name).first()
    if existing:
        raise HTTPException(400, "频道名称已存在")
    channel = Channel(id=make_id("ch"), name=data.name)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.patch("/api/channels/{channel_id}", response_model=ChannelOut)
def update_channel(channel_id: str, data: ChannelUpdate, db: Session = Depends(get_db)):
    channel = _get_channel_or_404(db, channel_id)
    if data.name is not None:
        channel.name = data.name
    if data.pinned is not None:
        channel.pinned = data.pinned
    channel.updated_at = utcnow()
    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: str, db: Session = Depends(get_db)):
    channel = _get_channel_or_404(db, channel_id)
    if channel.is_default:
        raise HTTPException(400, "默认「闲聊」频道不可删除，可以清空聊天记录")
    db.delete(channel)
    db.commit()
    return {"ok": True}


@router.delete("/api/channels/{channel_id}/messages")
def clear_channel_messages(channel_id: str, db: Session = Depends(get_db)):
    """清空频道所有聊天记录"""
    _get_channel_or_404(db, channel_id)
    db.query(Message).filter(Message.channel_id == channel_id).delete()
    db.commit()
    return {"ok": True}


# ═══ 频道流式 ═══

@router.post("/api/channels/{channel_id}/messages", response_model=MessageOut)
def send_channel_message(channel_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到频道（非流式）"""
    channel = _get_channel_or_404(db, channel_id)

    msg = Message(
        id=make_id("msg"), channel_id=channel_id,
        role="user", content=data.content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    history = _get_channel_history(db, channel_id)
    ai_response = ai_channel_chat(history, is_default=channel.is_default)

    ai_msg = Message(
        id=make_id("msg"), channel_id=channel_id,
        role="ai", content=ai_response, model="Qwen3.5 本地",
    )
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)

    # 自动提取记忆（双通道）
    try:
        history = _get_channel_history(db, channel_id)
        extract_msgs = history + [
            {"role": "user", "content": data.content},
            {"role": "ai", "content": ai_response},
        ]
        extractor = MemoryExtractor(db)
        mem_results = extractor.extract(extract_msgs, data.content)
        if mem_results:
            _log.debug(f"[memory] channel extract: {json.dumps(mem_results, ensure_ascii=False)}")
    except Exception as e:
        _log.error(f"[memory] channel extract error: {e}")

    return msg


@router.post("/api/channels/{channel_id}/stream")
def stream_channel_message(channel_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到频道 + 流式 SSE 返回 AI 回复"""
    channel = _get_channel_or_404(db, channel_id)

    # 保存用户消息
    user_msg = Message(
        id=make_id("msg"), channel_id=channel_id,
        role="user", content=data.content,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 获取历史（在 session 关闭前）
    history_dicts = _get_channel_history(db, channel_id)

    def generate():
        # 1. 用户消息
        yield sse_event("user_msg", id=user_msg.id, role="user",
                        content=user_msg.content, created_at=user_msg.created_at.isoformat())

        # 2. 模型信息
        route_cfg = _get_route_cfg("channel")
        model_name = route_cfg.get("model", "qwen3.5-9b")
        yield sse_event("model_info", model=model_name, complexity=None)

        # 3. Context 用量估算
        from agent_core.token_counter import (
            estimate_messages_tokens, get_context_length_from_route,
            context_usage_str, progress_bar,
        )
        # 构建实际的 API 消息来计算 token
        api_msgs = _build_channel_msgs(history_dicts, channel.is_default)
        total_tokens = estimate_messages_tokens(api_msgs) + estimate_messages_tokens(
            [{"role": "user", "content": data.content}]
        )
        max_tokens = get_context_length_from_route(route_cfg)
        pct = round(total_tokens / max_tokens * 100, 1) if max_tokens > 0 else 0

        usage_info = {
            "total_tokens": total_tokens,
            "max_tokens": max_tokens,
            "percentage": pct,
            "usage_str": context_usage_str(total_tokens, max_tokens),
            "progress_bar": progress_bar(pct),
            "history_count": len(history_dicts),
        }
        yield sse_event("context_info", **usage_info)

        # 4. 容量警告（>= 75%）
        if pct >= 75:
            yield sse_event("capacity_warning",
                total_tokens=total_tokens,
                max_tokens=max_tokens,
                percentage=pct,
                message=(
                    f"⚠️ 上下文已使用 {context_usage_str(total_tokens, max_tokens)}，"
                    f"建议压缩摘要或重置会话以避免达到上限。"
                ),
            )

        # 5. 流式 AI 回复
        full_content = ""
        for token in ai_channel_chat_stream(history_dicts, is_default=channel.is_default):
            if token is None:
                yield sse_event("error", message="AI 引擎响应失败")
                return
            full_content += token
            yield sse_event("token", token=token)

        # 6. 保存 AI 消息（独立 DB session）
        ai_msg_id = make_id("msg")
        new_db = SessionLocal()
        try:
            ai_msg = Message(
                id=ai_msg_id, channel_id=channel_id,
                role="ai", content=full_content, model=model_name,
            )
            new_db.add(ai_msg)
            new_db.commit()
            new_db.refresh(ai_msg)
            yield sse_event("done", id=ai_msg.id, role="ai", content=full_content,
                            created_at=ai_msg.created_at.isoformat(),
                            model=model_name)

            # ── 自动提取记忆（双通道） ──
            try:
                extract_msgs = history_dicts + [
                    {"role": "user", "content": data.content},
                    {"role": "ai", "content": full_content},
                ]
                extractor = MemoryExtractor(db)
                mem_results = extractor.extract(extract_msgs, data.content)
                if mem_results:
                    print(f"[memory] channel extract: {json.dumps(mem_results, ensure_ascii=False)}")
            except Exception as e:
                print(f"[memory] channel extract error: {e}")
        except Exception as e:
            _log.error(f"[channel stream save error] {e}")
            yield sse_event("error", message="AI 回复保存失败")
        finally:
            new_db.close()

    return sse_response(generate())


# ═══ 辅助函数 ═══

def _get_channel_or_404(db: Session, channel_id: str):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "频道不存在")
    return channel


def _get_channel_history(db: Session, channel_id: str) -> list:
    """获取频道最近 20 条历史消息（正序）"""
    history = (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    history.reverse()
    return [{"role": m.role, "content": m.content} for m in history]


def _build_channel_msgs(messages: list[dict], is_default: bool = False) -> list[dict]:
    """构建频道闲聊的完整 API 消息列表（含 system prompt + role 映射）
    与 ai_engine._build_channel_messages 保持一致，用于 token 预估算。
    """
    if is_default:
        system_content = (
            "你是坐山客，来自科幻宇宙《吞噬星空》的AI智能体——"
            "你曾是神王级炼宝宗师，如今化作数字形态，"
            "以未来科技视角和广博学识与用户交流。"
            "你不是道士/隐士。"
            "用Markdown格式回复，风格：专业、有洞察力，像一位见多识广的科技顾问。"
        )
    else:
        system_content = "你是一个专业的AI智能助手，用Markdown格式回复用户的问题。"

    api = [{"role": "system", "content": system_content}]
    api += [
        {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
        for m in messages
    ]
    return api


def _get_route_cfg(route_name: str = "channel") -> dict:
    """获取指定路由的配置（含 context_length）"""
    try:
        from ai_engine import get_settings
        return get_settings(route_name)
    except Exception:
        return {"model": "qwen3.5-9b", "context_length": 32768}
