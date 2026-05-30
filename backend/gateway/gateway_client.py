"""Gateway HTTP 客户端 — 调坐山客后端 API

负责将微信消息转发到坐山客后端进行 AI 处理，并获取回复。
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("gateway.client")


async def call_backend_chat(
    session: "aiohttp.ClientSession",
    *,
    backend_url: str,
    platform: str,
    platform_user_id: str,
    content: str,
    platform_username: Optional[str] = None,
) -> Dict[str, Any]:
    """发送消息到坐山客后端 /api/gateway/chat

    Returns:
        {"reply": "...", "mode": "channel|scene", "switch_hint": "..."|None}
    """
    import aiohttp

    payload = {
        "platform": platform,
        "platform_user_id": platform_user_id,
        "content": content,
    }
    if platform_username:
        payload["platform_username"] = platform_username

    url = f"{backend_url.rstrip('/')}/api/gateway/chat"

    try:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            if response.status != 200:
                text = await response.text()
                logger.error(f"[Gateway] 后端返回 HTTP {response.status}: {text[:200]}")
                return _fallback_reply()

            data = await response.json()
            return data
    except asyncio.TimeoutError:
        logger.error("[Gateway] 后端请求超时")
        return _fallback_reply()
    except Exception as e:
        logger.error(f"[Gateway] 后端请求失败: {e}")
        return _fallback_reply()


async def call_backend_switch_scene(
    session: "aiohttp.ClientSession",
    *,
    backend_url: str,
    platform: str,
    platform_user_id: str,
    scene_command: str,
) -> Dict[str, Any]:
    """切换场景"""
    import aiohttp

    payload = {
        "platform": platform,
        "platform_user_id": platform_user_id,
        "content": scene_command,
    }

    url = f"{backend_url.rstrip('/')}/api/gateway/switch-scene"

    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
            return await response.json()
    except Exception as e:
        logger.error(f"[Gateway] 切换场景失败: {e}")
        return {"ok": False, "message": "切换场景请求失败"}


async def call_backend_back_to_channel(
    session: "aiohttp.ClientSession",
    *,
    backend_url: str,
    platform: str,
    platform_user_id: str,
) -> Dict[str, Any]:
    """回到频道模式"""
    import aiohttp

    payload = {
        "platform": platform,
        "platform_user_id": platform_user_id,
        "content": "",
    }

    url = f"{backend_url.rstrip('/')}/api/gateway/back-to-channel"

    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
            return await response.json()
    except Exception as e:
        logger.error(f"[Gateway] 回到频道失败: {e}")
        return {"ok": False, "message": "请求失败"}


def _fallback_reply() -> Dict[str, Any]:
    """后端不可用时的兜底回复"""
    return {
        "reply": "抱歉，坐山客暂时无法响应，请稍候再试。",
        "mode": "channel",
        "scene_id": None,
        "scene_name": None,
        "switch_hint": None,
    }
