"""Clarify 路由 — 阻塞式追问的 SSE 事件发射 + 用户回复入口

提供两个端点：
  1. SSE 事件发射：由 scene_stream.py 在 Agent Loop 中调 clarify_handler 创建请求，
     然后通过 generate() yield sse_event("zhu:clarify", ...)
  2. POST /api/agent-loop/clarify-response：前端弹窗选择后调用
"""

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from agent_core.clarify_handler import ClarifyHandler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agent Loop Clarify"])

# ── Pydantic 请求模型 ──

class ClarifyResponseIn(BaseModel):
    event_id: str
    response: str


# ── 工具函数（给 scene_stream.py 用） ──

# 全局缓存：当前 SSE 生成器正在等待的同步回调函数
# 每次 Agent Loop 调 clarify_tool 时，scene_stream 注册一个回调在这里
# 回调内部创建 ClarifyRequest, 发射 SSE, wait, 返回
_pending_callbacks: dict[str, callable] = {}


def make_clarify_callback(scene_id: str, event_yield_func: callable) -> callable:
    """构建一个给 clarify_tool 用的阻塞回调。

    Args:
        scene_id: 当前场景 ID（用于日志）
        event_yield_func: 闭包函数，接收 {event_id, question, choices} 后 yield SSE

    Returns:
        callback(question, choices) -> str 的同步阻塞函数
    """
    def _callback(question: str, choices: Optional[list[str]]) -> str:
        handler = ClarifyHandler.get_instance()
        req = handler.create_request(question, choices)

        # 发射 SSE 事件给前端
        try:
            event_yield_func(req.to_dict())
        except Exception as e:
            logger.warning(f"[clarify] SSE 发射失败: {e}")

        logger.info(f"[clarify] 等待用户回复: scene={scene_id}, event_id={req.event_id}")
        # 同步阻塞
        result = handler.wait_for_response(req.event_id, timeout=300)
        logger.info(f"[clarify] 收到用户回复: scene={scene_id}, event_id={req.event_id}")
        return result

    return _callback


# ═══ API 端点 ═══


@router.post("/api/agent-loop/clarify-response")
def handle_clarify_response(data: ClarifyResponseIn):
    """前端提交用户对 clarify 问题的回复。

    用户在前端弹窗中选择了选项或输入了文本后，前端调此端点。
    """
    handler = ClarifyHandler.get_instance()
    ok = handler.resolve_request(data.event_id, data.response)
    if not ok:
        raise HTTPException(404, f"Clarify 请求 {data.event_id} 不存在或已过期")
    return {"ok": True}


@router.get("/api/agent-loop/clarify-pending")
def get_clarify_pending():
    """获取当前是否有 pending 的 clarify 请求（前端轮询或恢复时检查）"""
    handler = ClarifyHandler.get_instance()
    event_id = handler.get_pending_event_id()
    if not event_id:
        return {"pending": False}
    info = handler.get_pending_info(event_id)
    return {"pending": True, "event_id": event_id, "info": info}
