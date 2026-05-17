"""微信 iLink 协议适配器

基于腾讯 iLink Bot API，实现消息的接收（长轮询）和发送。

本模块是坐山客 Gateway 的一部分，保持轻量，仅处理文本消息。
媒体消息（图片/文件/语音）暂不支持，后续可扩展。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("gateway.weixin")


# ── iLink API 常量 ──
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

# 消息类型
ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

MSG_TYPE_USER = 1
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2

# 错误码
SESSION_EXPIRED_ERRCODE = -14
RATE_LIMIT_ERRCODE = -2


def _random_wechat_uin() -> str:
    """生成随机 X-WECHAT-UIN header"""
    import struct
    import secrets
    import base64
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _base_info() -> Dict[str, Any]:
    return {"channel_version": CHANNEL_VERSION}


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _make_headers(token: str, body: str) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_text(item_list: list) -> str:
    """从消息 item_list 中提取文本内容"""
    texts = []
    for item in item_list:
        if item.get("type") == ITEM_TEXT:
            text = (item.get("text_item") or {}).get("text", "")
            if text:
                texts.append(text)
    return "\n".join(texts)


# ── 同步缓冲区管理 ──

SYNC_BUF_DIR = Path.home() / ".zuoshanke" / "gateway"


def _sync_buf_path(account_id: str) -> Path:
    SYNC_BUF_DIR.mkdir(parents=True, exist_ok=True)
    return SYNC_BUF_DIR / f"sync_buf_{account_id}.txt"


def _load_sync_buf(account_id: str) -> str:
    path = _sync_buf_path(account_id)
    if path.exists():
        return path.read_text().strip()
    return ""


def _save_sync_buf(account_id: str, sync_buf: str) -> None:
    path = _sync_buf_path(account_id)
    path.write_text(sync_buf)


# ── API 调用 ──

async def _api_post(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    token: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    """调用 iLink API（通用 POST）"""
    import aiohttp
    body = _json_dumps({**payload, "base_info": _base_info()})
    url = f"{base_url.rstrip('/')}/{endpoint}"
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.post(url, data=body, headers=_make_headers(token, body), timeout=timeout) as response:
        raw = await response.text()
        if not response.ok:
            raise RuntimeError(f"iLink POST {endpoint} HTTP {response.status}: {raw[:200]}")
        return json.loads(raw)


async def get_updates(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    sync_buf: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    """长轮询获取消息"""
    import aiohttp
    try:
        return await _api_post(
            session,
            base_url=base_url,
            endpoint="ilink/bot/getupdates",
            payload={"get_updates_buf": sync_buf},
            token=token,
            timeout_ms=timeout_ms,
        )
    except asyncio.TimeoutError:
        return {"ret": 0, "msgs": [], "get_updates_buf": sync_buf}


async def send_message(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    to_user_id: str,
    text: str,
    context_token: Optional[str] = None,
    client_id: str = "",
) -> Dict[str, Any]:
    """发送文本消息到微信"""
    if not text or not text.strip():
        raise ValueError("send_message: text must not be empty")

    message: Dict[str, Any] = {
        "from_user_id": "",
        "to_user_id": to_user_id,
        "client_id": client_id,
        "message_type": MSG_TYPE_BOT,
        "message_state": MSG_STATE_FINISH,
        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
    }
    if context_token:
        message["context_token"] = context_token

    return await _api_post(
        session,
        base_url=base_url,
        endpoint="ilink/bot/sendmessage",
        payload={"msg": message},
        token=token,
        timeout_ms=15_000,
    )
