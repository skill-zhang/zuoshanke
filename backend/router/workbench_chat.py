"""工作台对话 SSE 端点 — Avatar 对话回应（Phase 1）

接收用户输入 → 轻量 LLM 调用 → 流式返回 speech 事件 → 更新 ZhuAgent 状态

Phase 2 扩展：speech:done 后 yield action:xxx 事件调用场景 API
"""
import json
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from agent_core.zhu_agent import ZhuAgentManager
from ai_engine import call_llm_stream, get_settings
from router.shared import sse_event, sse_response

_log = logging.getLogger(__name__)

router = APIRouter(tags=["工作台"])


class WorkbenchChatRequest(BaseModel):
    content: str
    scene_ids: list[str] = []


def _generate_speech(req: WorkbenchChatRequest, db: Session):
    """生成工作台 Avatar 对话 SSE 流

    事件序列：
      speech:token  — 逐 token 或整体推送（打字机效果）
      speech:done   — 说话完成
      done          — 全流程完成
    """
    _log.info(f"[workbench_chat] content={req.content[:60]}")
    zhu = ZhuAgentManager(db)

    # 1. 设置本体为说话状态
    zhu.update_mood("speaking", "")

    # 2. 轻量 LLM 调用（走 channel 路由，温度稍低，简短回复）
    route_cfg = get_settings("channel")
    prompt = (
        "你是坐山客，用户的 AI 伙伴。\n\n"
        f"用户在工作台对你说：{req.content}\n\n"
        "生成一句简短自然的回复（不超过 50 字），"
        "表示已收到用户的请求。"
        "⚠️ 重要：不要声称已经完成了任何操作——"
        "你只是收到了请求，后续会由系统执行。"
        "例如，用户说「调整顺序」，回复「好的，我来调整一下顺序」"
        "而不是「已经调整好了」。"
    )
    messages = [{"role": "user", "content": prompt}]

    reply = ""
    try:
        for token in call_llm_stream(messages, route_cfg, temperature=0.5, max_tokens=200):
            if token is None:
                break
            reply += token
            yield sse_event("speech:token", text=reply)
    except Exception as e:
        _log.error(f"[workbench_chat] LLM error: {e}")
        reply = "好的，收到。"
        yield sse_event("speech:token", text=reply)

    # 3. 说话完成（不设 observation，避免空间气泡干扰）
    yield sse_event("speech:done", text=reply)
    zhu.update_mood("amused", "")

    # 4. Phase 2 在此处延伸：解析意图 → yield action:xxx 事件
    yield sse_event("done")


@router.post("/api/workbench/chat")
def workbench_chat(req: WorkbenchChatRequest, db: Session = Depends(get_db)):
    """工作台聊天 — SSE 流式返回 Avatar 回应"""
    return sse_response(_generate_speech(req, db))
