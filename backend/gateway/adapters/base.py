"""坐山客多平台适配器抽象基类

轻量版 BasePlatformAdapter，定义各平台消息适配器的统一接口。
每个平台适配器继承此类，实现平台特定的连接/收发/生命周期管理。
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger("gateway.adapters.base")


# ── 重试/退避常量 ──
RETRY_DELAY_SECONDS = 5        # 普通失败重试间隔
BACKOFF_DELAY_SECONDS = 30     # 连续失败后的退避间隔
MAX_CONSECUTIVE_FAILURES = 5   # 触发退避的连续失败次数


class BasePlatformAdapter(ABC):
    """平台适配器抽象基类

    子类必须实现:
        name          — 适配器名称（class property）
        start()       — 启动监听（连接到平台，开始接收消息）
        stop()        — 停止监听
        send_message() — 发送文本消息到平台用户

    可选实现:
        send_typing() — 发送「正在输入」状态
        send_image()  — 发送图片消息

    内置:
        _route_to_backend() — 将收到的消息发送到坐山客后端 AI 处理
        _run_poll_loop()    — 标准轮询循环（含退避重连）
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._running = False
        self._consecutive_failures = 0
        self._backend_url: str = config.get("backend_url", "http://localhost:8000")
        self._http_session: Optional["aiohttp.ClientSession"] = None

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """返回该适配器对应的平台标识（如 'weixin', 'telegram', 'discord'）"""
        ...

    @abstractmethod
    async def start(self) -> None:
        """启动适配器，连接到平台并开始接收消息"""

    @abstractmethod
    async def stop(self) -> None:
        """停止适配器，断开连接"""

    @abstractmethod
    async def send_message(
        self, to_user_id: str, text: str,
        context_token: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """发送文本消息到平台用户"""

    async def send_typing(self, to_user_id: str) -> None:
        """发送「正在输入」状态（可选重写，默认不实现）"""
        pass

    async def send_image(
        self, to_user_id: str, image_url: str,
        caption: str = "",
        context_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发送图片消息（可选重写，默认降级为文本）"""
        text = f"{caption}\n[图片: {image_url}]" if caption else f"[图片: {image_url}]"
        return await self.send_message(to_user_id, text, context_token)

    # ── 后端通讯 ──

    async def _route_to_backend(
        self,
        platform_user_id: str,
        content: str,
        platform_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """将收到的消息转发到坐山客后端 AI 处理

        返回:
            {"reply": "...", "mode": "channel|scene", "switch_hint": "..."|None}
        """
        from gateway.gateway_client import call_backend_chat

        session = await self._get_http_session()
        return await call_backend_chat(
            session,
            backend_url=self._backend_url,
            platform=self.platform_name,
            platform_user_id=platform_user_id,
            content=content,
            platform_username=platform_username,
        )

    async def _route_switch_scene(
        self,
        platform_user_id: str,
        scene_command: str,
    ) -> Dict[str, Any]:
        """切换场景"""
        from gateway.gateway_client import call_backend_switch_scene

        session = await self._get_http_session()
        return await call_backend_switch_scene(
            session,
            backend_url=self._backend_url,
            platform=self.platform_name,
            platform_user_id=platform_user_id,
            scene_command=scene_command,
        )

    async def _route_back_to_channel(
        self,
        platform_user_id: str,
    ) -> Dict[str, Any]:
        """回到频道模式"""
        from gateway.gateway_client import call_backend_back_to_channel

        session = await self._get_http_session()
        return await call_backend_back_to_channel(
            session,
            backend_url=self._backend_url,
            platform=self.platform_name,
            platform_user_id=platform_user_id,
        )

    async def _route_switch_backend(
        self,
        platform_user_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """根据内容自动判断是场景切换、退出还是普通聊天"""
        text = content.strip()
        from config.matching_rules import EXIT_COMMANDS, SCENE_COMMAND_PREFIXES

        if text.lower() in EXIT_COMMANDS:
            return await self._route_back_to_channel(platform_user_id)

        if any(text.lower().startswith(p) for p in SCENE_COMMAND_PREFIXES):
            return await self._route_switch_scene(platform_user_id, text)

        return await self._route_to_backend(platform_user_id, text)

    # ── HTTP 会话管理 ──

    async def _get_http_session(self) -> "aiohttp.ClientSession":
        """获取或创建 aiohttp 会话"""
        import aiohttp

        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def _close_http_session(self) -> None:
        """关闭 HTTP 会话"""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        self._http_session = None

    # ── 标准轮询循环（用于长轮询型平台，如微信 iLink） ──

    async def _run_poll_loop(
        self,
        poll_coro,
        process_coro,
        poll_timeout_ms: int = 60000,
    ) -> None:
        """标准轮询循环

        poll_coro:    async (session, timeout_ms) -> {"msgs": [...], "ret": 0}
        process_coro: async (message) -> None
        """
        import aiohttp

        assert self._http_session is not None

        timeout_ms = poll_timeout_ms

        while self._running:
            try:
                response = await poll_coro(self._http_session, timeout_ms)

                # 检查服务端建议的超时
                suggested = response.get("longpolling_timeout_ms")
                if isinstance(suggested, int) and suggested > 0:
                    timeout_ms = suggested

                # 检查错误
                ret = response.get("ret", 0)
                errcode = response.get("errcode", 0)
                if ret not in (0, None) or errcode not in (0, None):
                    await self._handle_poll_error(response)
                    continue

                # 成功
                self._consecutive_failures = 0

                # 处理消息
                for message in response.get("msgs") or []:
                    asyncio.create_task(process_coro(message))

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._consecutive_failures += 1
                delay = (
                    BACKOFF_DELAY_SECONDS
                    if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES
                    else RETRY_DELAY_SECONDS
                )
                logger.error(
                    "[%s] 轮询错误 (%d/%d): %s，%.0fs 后重试",
                    self.platform_name,
                    self._consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self._consecutive_failures = 0

    async def _handle_poll_error(self, response: Dict[str, Any]) -> None:
        """处理轮询返回的业务错误"""
        ret = response.get("ret", 0)
        errcode = response.get("errcode", 0)

        # Session 过期（微信 -14）
        if ret == -14 or errcode == -14:
            logger.error("[%s] Session 过期，暂停 10 分钟后重试", self.platform_name)
            await asyncio.sleep(600)
            self._consecutive_failures = 0
            return

        self._consecutive_failures += 1
        delay = (
            BACKOFF_DELAY_SECONDS
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES
            else RETRY_DELAY_SECONDS
        )
        logger.warning(
            "[%s] getUpdates 失败 ret=%s errcode=%s (%d/%d)，%.0fs 后重试",
            self.platform_name, ret, errcode,
            self._consecutive_failures, MAX_CONSECUTIVE_FAILURES,
            delay,
        )
        await asyncio.sleep(delay)
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self._consecutive_failures = 0

    # ── 消息去重 ──

    class MessageDeduplicator:
        """消息去重（基于 message_id 和内容指纹）"""

        def __init__(self, ttl_seconds: int = 300):
            self._seen: Dict[str, float] = {}
            self._ttl = ttl_seconds

        def is_duplicate(self, key: str) -> bool:
            now = time.time()
            self._clean(now)
            if key in self._seen:
                return True
            self._seen[key] = now
            return False

        def _clean(self, now: float) -> None:
            expired = [k for k, ts in self._seen.items() if now - ts > self._ttl]
            for k in expired:
                del self._seen[k]

    # ── 生命周期 ──

    def is_running(self) -> bool:
        return self._running

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.stop()
