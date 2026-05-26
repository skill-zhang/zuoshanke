"""频道 CRUD + 频道流式"""
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import Channel, Message
from schemas import ChannelCreate, ChannelUpdate, ChannelOut, MessageCreate, MessageOut
from ai_engine import ai_channel_chat, ai_channel_chat_stream
from utils import make_id, utcnow, iso_utc
from router.shared import sse_event, sse_response
from agent_core.memory_extractor import MemoryExtractor
from logger import get_logger as _get_logger

# ── 历史消息时间闸（只加载最近 N 小时内的消息） ──
HISTORY_TIME_WINDOW_HOURS = 2

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
    # 进入频道 → 按需加载频道记忆
    from agent_core.memory_cache import MemoryCache
    MemoryCache.get_instance().load_scope(db, "channel", channel_id)
    """发送消息到频道（非流式）"""
    channel = _get_channel_or_404(db, channel_id)

    msg = Message(
        id=make_id("msg"), channel_id=channel_id,
        role="user", content=data.content,
    )
    if data.attachments:
        msg.file_attachments = json.dumps(data.attachments, ensure_ascii=False)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    history = _get_channel_history(db, channel_id)
    attachments_json = json.loads(msg.file_attachments) if msg.file_attachments else None
    ai_response = ai_channel_chat(history, is_default=channel.is_default, db=db, attachments=attachments_json)

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
    if data.attachments:
        user_msg.file_attachments = json.dumps(data.attachments, ensure_ascii=False)
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 获取历史（在 session 关闭前）
    history_dicts = _get_channel_history(db, channel_id)

    # 🆕 Schema v1.1: 确保 Web session 存在并更新 last_active_at
    from router.scene_stream import _ensure_web_session
    ws = _ensure_web_session(db, "channel", channel_id, channel.name)
    ws.last_active_at = utcnow()
    ws.updated_at = utcnow()
    db.commit()

    def generate():
        # 🆕 Schema v0.8: 本体观察 — 频道对话启动
        from agent_core.zhu_agent import ZhuAgentManager
        _zhu_ch = ZhuAgentManager(db)
        _zhu_ch.observe_fenshen_event("fenshen:started", channel.name or "闲聊")

        # 1. 用户消息
        attachments_json = json.loads(user_msg.file_attachments) if user_msg.file_attachments else None
        yield sse_event("user_msg", id=user_msg.id, role="user",
                        content=user_msg.content, created_at=iso_utc(user_msg.created_at),
                        attachments=attachments_json)

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
        api_msgs = _build_channel_msgs(history_dicts, channel.is_default, db=db)
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
        attachments_json = json.loads(user_msg.file_attachments) if user_msg.file_attachments else None
        for token in ai_channel_chat_stream(history_dicts, is_default=channel.is_default, db=db, attachments=attachments_json):
            if token is None:
                yield sse_event("error", message="AI 引擎响应失败")
                return
            full_content += token
            yield sse_event("token", token=token)

        # 6. 保存 AI 消息（独立 DB session）
        ai_msg_id = make_id("msg")
        new_db = SessionLocal()
        try:
            # 🆕 Schema v0.8: 本体观察 — 频道回复完成（基础反应，先执行）
            try:
                _zhu_ch.observe_fenshen_event("fenshen:done", channel.name or "闲聊")
            except Exception:
                pass

            # 🆕 Schema v0.8+: 从 LLM 回复中解析心情表达（覆盖基础反应）
            def _parse_mood_from_reply(reply: str, ch_name: str):
                """从回复末尾解析 [心情: 情绪词] 内心独白，提取 LLM 自然表达的心情"""
                import re
                m = re.search(r'\[心情:\s*(\w+)\]\s*(.+?)\s*$', reply, re.DOTALL)
                if not m:
                    return
                mood_word = m.group(1).strip().lower()
                comment = m.group(2).strip()
                try:
                    from database import SessionLocal as SL
                    from agent_core.zhu_agent import ZhuAgentManager
                    zhu_db = SL()
                    try:
                        zhu_mgr = ZhuAgentManager(zhu_db)
                        zhu_mgr.update_mood(mood_word, f"【{ch_name}】{comment}")
                    finally:
                        zhu_db.close()
                except Exception:
                    pass

            # 解析心境 → 覆盖 avatar 状态（用含心情标签的原始文本）
            _parse_mood_from_reply(full_content, channel.name or "闲聊")

            # 剥离心情标签，得到干净回复
            import re as _re
            clean_content = _re.sub(r'\s*\[心情:\s*\w+\]\s*.+?\s*$', '', full_content, flags=_re.DOTALL).strip()

            ai_msg = Message(
                id=ai_msg_id, channel_id=channel_id,
                role="ai", content=clean_content, model=model_name,
            )
            new_db.add(ai_msg)
            new_db.commit()
            new_db.refresh(ai_msg)
            yield sse_event("done", id=ai_msg.id, role="ai", content=clean_content,
                            created_at=iso_utc(ai_msg.created_at),
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

            # 🆕 Schema v1.1: 累加 token 用量
            from models import WebSession as _WS
            _ws = db.query(_WS).filter(
                _WS.context_type == "channel",
                _WS.context_id == channel_id,
                _WS.status == "active",
            ).first()
            if _ws:
                _ws.prompt_tokens += total_tokens
                _ws.completion_tokens += estimate_messages_tokens([{"role": "assistant", "content": clean_content}])
                _ws.total_tokens = _ws.prompt_tokens + _ws.completion_tokens
                _ws.api_calls += 1
                _ws.last_active_at = utcnow()
                _ws.updated_at = utcnow()
                db.commit()

        except Exception as e:
            _log.error(f"[channel stream save error] {e}")
            yield sse_event("error", message="AI 回复保存失败")
        finally:
            new_db.close()

    return sse_response(generate())


# ═══ 上下文压缩 ═══

@router.post("/api/channels/{channel_id}/compress")
def compress_channel_history(channel_id: str, db: Session = Depends(get_db)):
    """压缩频道历史消息为摘要，替换原始对话"""
    channel = _get_channel_or_404(db, channel_id)

    # 1. 获取全部历史（突破时间闸，取所有消息）
    all_msgs = (
        db.query(Message)
        .filter(Message.channel_id == channel_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    if not all_msgs:
        return {"ok": True, "summary": "", "deleted": 0}

    # 2. 构建压缩 prompt
    dialogue_lines = []
    for m in all_msgs:
        label = "用户" if m.role == "user" else "AI"
        dialogue_lines.append(f"{label}: {m.content}")
    dialogue_text = "\n\n".join(dialogue_lines)

    compress_prompt = (
        "你是一个对话总结助手。请总结以下对话的核心内容，\n"
        "保留所有重要的用户偏好、决策、已确定的事实信息和未完成事项。\n"
        "不要遗漏关键信息，也不要添加新的内容。\n"
        "根据内容丰富程度自行决定摘要长度——可以是一段话，也可以是多段。\n\n"
        "--- 对话记录 ---\n"
        f"{dialogue_text}\n\n"
        "---\n"
        "请输出摘要："
    )

    # 3. 调用 LLM 压缩（用 extraction 路由，轻量模型）
    from ai_engine import call_qwen_chat
    summary = call_qwen_chat(
        [{"role": "user", "content": compress_prompt}],
        route="extraction",
    )
    if not summary or summary.strip() == "":
        # LLM 调用失败，回退
        return {"ok": False, "error": "AI 压缩失败", "summary": None, "deleted": 0}

    summary = summary.strip()

    # 4. 删除所有旧消息
    deleted = db.query(Message).filter(Message.channel_id == channel_id).delete()
    db.commit()

    # 5. 创建摘要消息（system 角色，在 _get_channel_history 中会被加载）
    summary_msg = Message(
        id=make_id("msg"),
        channel_id=channel_id,
        role="system",
        content=f"【历史摘要】{summary}",
    )
    db.add(summary_msg)
    db.commit()

    _log.info(f"[compress] channel={channel_id} deleted={deleted} summary_len={len(summary)}")
    return {"ok": True, "summary": summary, "deleted": deleted}


# ═══ 辅助函数 ═══

def _get_channel_or_404(db: Session, channel_id: str):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "频道不存在")
    return channel


def _get_channel_history(db: Session, channel_id: str) -> list:
    """获取频道最近的历史消息（时间闸 2 小时 + 最多 20 条，正序）"""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HISTORY_TIME_WINDOW_HOURS)
    history = (
        db.query(Message)
        .filter(Message.channel_id == channel_id, Message.created_at >= cutoff)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    history.reverse()
    return [{"role": m.role, "content": m.content} for m in history]


def _build_channel_msgs(messages: list[dict], is_default: bool = False, db=None) -> list[dict]:
    """构建频道闲聊的完整 API 消息列表（含 system prompt + role 映射）
    与 ai_engine._build_channel_messages 保持一致，用于 token 预估算。
    """
    from prompts import get_channel_prompt
    system_content = get_channel_prompt(is_default, db)

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
