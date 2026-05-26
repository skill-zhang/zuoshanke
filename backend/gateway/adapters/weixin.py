"""微信 iLink 平台适配器

基于腾讯 iLink Bot API，实现消息的接收（长轮询）和发送。
使用 adapter_weixin.py 作为底层 iLink 协议库。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from gateway.adapters.base import BasePlatformAdapter
from gateway.adapters.base import (
    RETRY_DELAY_SECONDS,
    BACKOFF_DELAY_SECONDS,
    MAX_CONSECUTIVE_FAILURES,
)
from gateway.adapter_weixin import (
    get_updates,
    send_message,
    _extract_text,
    _load_sync_buf,
    _save_sync_buf,
    SESSION_EXPIRED_ERRCODE,
    ITEM_TEXT,
    ITEM_IMAGE,
    ITEM_VOICE,
    ITEM_FILE,
    ITEM_VIDEO,
)

logger = logging.getLogger("gateway.adapters.weixin")


class WeixinAdapter(BasePlatformAdapter):
    """微信 iLink 适配器 — 长轮询接收 + 发送回复"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._token = config.get("token", "")
        self._account_id = config.get("account_id", "")
        self._base_url = config.get("base_url", "https://ilinkai.weixin.qq.com")
        self._sync_buf: str = ""
        self._token_store = ContextTokenStore()
        self._dedup = BasePlatformAdapter.MessageDeduplicator()

    @property
    def platform_name(self) -> str:
        return "weixin"

    async def start(self) -> None:
        """启动长轮询监听"""
        if not self._token or not self._account_id:
            logger.error("[weixin] 未配置 Token / Account ID，无法启动")
            return

        await self._get_http_session()
        self._sync_buf = _load_sync_buf(self._account_id)
        self._running = True

        logger.info(
            "[weixin] 适配器已启动 (%s...)，开始长轮询...",
            self._account_id[:8],
        )

        try:
            await self._run_poll_loop(
                poll_coro=self._poll_get_updates,
                process_coro=self._process_message,
                poll_timeout_ms=60000,
            )
        except asyncio.CancelledError:
            logger.info("[weixin] 轮询已取消")
        except Exception as e:
            logger.error("[weixin] 轮询异常退出: %s", e)
            raise
        finally:
            await self._close_http_session()
            self._running = False
            logger.info("[weixin] 适配器已停止")

    async def stop(self) -> None:
        self._running = False

    async def send_message(
        self,
        to_user_id: str,
        text: str,
        context_token: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """发送文本消息到微信"""
        if not text or not text.strip():
            return {"ret": -1, "errmsg": "text must not be empty"}

        token = context_token or self._token_store.get(self._account_id, to_user_id)
        session = await self._get_http_session()

        try:
            result = await send_message(
                session,
                base_url=self._base_url,
                token=self._token,
                to_user_id=to_user_id,
                text=text,
                context_token=token,
                client_id="zuoshanke_gateway",
            )
            logger.info("[weixin] 已回复 %s: %.40s", to_user_id[:8], text)
            return result
        except Exception as e:
            logger.error("[weixin] 发送回复失败: %s", e)
            return {"ret": -1, "errmsg": str(e)}

    async def send_typing(self, to_user_id: str) -> None:
        """微信 iLink 暂不支持 typing 指示器"""
        pass

    # ── 内部方法 ──

    async def _poll_get_updates(
        self, session, timeout_ms: int,
    ) -> Dict[str, Any]:
        """调用 iLink get_updates"""
        return await get_updates(
            session,
            base_url=self._base_url,
            token=self._token,
            sync_buf=self._sync_buf,
            timeout_ms=timeout_ms,
        )

    async def _process_message(self, message: Dict[str, Any]) -> None:
        """处理单条微信消息"""
        try:
            sender_id = str(message.get("from_user_id") or "").strip()
            if not sender_id:
                return
            if sender_id == self._account_id:
                return  # 忽略自己发的

            # 消息去重
            msg_id = str(message.get("message_id") or "").strip()
            if msg_id and self._dedup.is_duplicate(msg_id):
                return

            # 提取文本
            item_list = message.get("item_list") or []
            text = _extract_text(item_list)

            # 媒体消息
            if not text:
                has_media = any(
                    item.get("type") in (ITEM_IMAGE, ITEM_VOICE, ITEM_FILE, ITEM_VIDEO)
                    for item in item_list
                )
                if has_media:
                    logger.info(
                        "[weixin] 收到媒体消息（暂不支持），来自: %s",
                        sender_id[:8],
                    )
                    await self.send_message(
                        sender_id, "暂时不支持接收图片和文件哦～",
                    )
                return

            # 保存 context_token
            context_token = str(message.get("context_token") or "").strip()
            if context_token:
                self._token_store.set(self._account_id, sender_id, context_token)

            logger.info("[weixin] 收到消息 from=%s: %.40s", sender_id[:8], text)

            # 更新同步缓冲区（消息成功处理后）
            new_buf = str(message.get("get_updates_buf") or "")
            if new_buf and new_buf != self._sync_buf:
                self._sync_buf = new_buf
                _save_sync_buf(self._account_id, self._sync_buf)

            # 处理命令或聊天
            if text.startswith("/"):
                await self._handle_command(sender_id, text, context_token)
            else:
                await self._handle_chat(sender_id, text, context_token)

        except Exception as e:
            logger.error("[weixin] 处理消息失败: %s", e, exc_info=True)

    async def _handle_command(
        self, sender_id: str, command: str, context_token: Optional[str],
    ) -> None:
        """处理命令消息"""
        cmd = command.strip().lower()

        from config.matching_rules import EXIT_COMMANDS, SCENE_COMMAND_PREFIXES

        if cmd in EXIT_COMMANDS:
            result = await self._route_back_to_channel(sender_id)
            reply = result.get("message", "已回到闲聊模式。")
            await self.send_message(sender_id, reply, context_token)

        elif any(cmd.startswith(p) for p in SCENE_COMMAND_PREFIXES):
            result = await self._route_switch_scene(sender_id, command)
            if result.get("ok"):
                scene_name = result.get("scene_name", "")
                reply = f"已切换到场景「{scene_name}」。发送「/闲聊」回到闲聊模式。"
            else:
                reply = result.get("message", "切换场景失败")
            await self.send_message(sender_id, reply, context_token)

        elif cmd in ("/help", "/帮助"):
            reply = (
                "🤖 **坐山客微信助手**\n\n"
                "**默认模式**：闲聊对话\n\n"
                "**可用命令**：\n"
                "• `/进入天气` — 切换到天气查询场景\n"
                "• `/进入旅游推荐` — 切换到旅游推荐场景\n"
                "• `/闲聊` 或 `/退出` — 回到闲聊模式\n"
                "• `/场景列表` — 查看可用场景\n"
                "• `/帮助` — 显示此帮助\n\n"
                "也可以直接问我问题，我会自动判断是否需要切换场景。"
            )
            await self.send_message(sender_id, reply, context_token)

        elif cmd in ("/场景列表", "/scenes"):
            reply = "📋 可用场景：天气查询、旅游推荐、信息搜索。\n输入 `/进入场景名` 切换到对应场景。"
            await self.send_message(sender_id, reply, context_token)

        else:
            # 未知命令→当普通消息处理
            await self._handle_chat(sender_id, command, context_token)

    async def _handle_chat(
        self, sender_id: str, text: str, context_token: Optional[str],
    ) -> None:
        """处理聊天消息 — 调后端 AI"""
        result = await self._route_to_backend(sender_id, text)
        reply = result.get("reply", "")
        switch_hint = result.get("switch_hint")

        if reply:
            await self.send_message(sender_id, reply, context_token)
            if switch_hint:
                await self.send_message(
                    sender_id, f"\n💡 {switch_hint}", context_token,
                )

    async def _handle_poll_error(self, response: Dict[str, Any]) -> None:
        """微信特有的错误处理"""
        ret = response.get("ret", 0)
        errcode = response.get("errcode", 0)

        if ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE:
            logger.error("[weixin] Session 过期，暂停 10 分钟后重试")
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
            "[weixin] getUpdates 失败 ret=%s errcode=%s (%d/%d)，%.0fs 后重试",
            ret, errcode,
            self._consecutive_failures, MAX_CONSECUTIVE_FAILURES,
            delay,
        )
        await asyncio.sleep(delay)
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self._consecutive_failures = 0


class ContextTokenStore:
    """每个用户最后一条消息的 context_token（用于回复时回传）"""

    def __init__(self):
        self._tokens: Dict[str, str] = {}

    def get(self, account_id: str, user_id: str) -> Optional[str]:
        return self._tokens.get(f"{account_id}:{user_id}")

    def set(self, account_id: str, user_id: str, token: str) -> None:
        if token:
            self._tokens[f"{account_id}:{user_id}"] = token
