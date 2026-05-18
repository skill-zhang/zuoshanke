"""
坐山客 Gateway — 多平台消息网关独立进程

启动：
    cd ~/zuoshanke/backend
    .venv/bin/python -m backend.gateway.run

依赖：aiohttp, cryptography
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import signal
import sys
from typing import Any, Dict, Optional, Set

# 确保 backend 目录在 sys.path 中
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import aiohttp

from backend.gateway.config import (
    GatewayConfig,
    LONG_POLL_TIMEOUT_MS,
    MAX_CONSECUTIVE_FAILURES,
    RETRY_DELAY_SECONDS,
    BACKOFF_DELAY_SECONDS,
)
from backend.gateway.adapter_weixin import (
    get_updates,
    send_message,
    _extract_text,
    _load_sync_buf,
    _save_sync_buf,
    SESSION_EXPIRED_ERRCODE,
    RATE_LIMIT_ERRCODE,
    ITEM_TEXT,
    ITEM_IMAGE,
    ITEM_VOICE,
    ITEM_FILE,
    ITEM_VIDEO,
)
from backend.gateway.gateway_client import (
    call_backend_chat,
    call_backend_switch_scene,
    call_backend_back_to_channel,
)

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gateway")


# ── 上下文 Token 管理 ──
class ContextTokenStore:
    """每个用户最后一条消息的 context_token（用于回复时回传）"""

    def __init__(self):
        self._tokens: Dict[str, str] = {}

    def get(self, account_id: str, user_id: str) -> Optional[str]:
        return self._tokens.get(f"{account_id}:{user_id}")

    def set(self, account_id: str, user_id: str, token: str) -> None:
        if token:
            self._tokens[f"{account_id}:{user_id}"] = token


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


import time


class WeixinAdapter:
    """微信 iLink 消息适配器 — 长轮询接收 + 发送回复"""

    def __init__(self, config: GatewayConfig):
        self.config = config
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._token_store = ContextTokenStore()
        self._dedup = MessageDeduplicator()
        self._consecutive_failures = 0
        # 已处理的消息 ID 集合（进程内存级，重启后重置不会漏消息因为 iLink 有 buf 游标）
        self._processed_ids: Set[str] = set()

    @property
    def name(self) -> str:
        return f"weixin:{self.config.weixin_account_id[:8]}"

    async def start(self) -> None:
        """启动轮询"""
        if not self.config.is_configured:
            logger.error("[%s] 未配置微信 Token / Account ID，无法启动", self.name)
            logger.error("请设置 WEIXIN_TOKEN 和 WEIXIN_ACCOUNT_ID 环境变量或配置文件")
            return

        self._running = True
        self._session = aiohttp.ClientSession()

        logger.info("[%s] 微信适配器已启动，开始长轮询...", self.name)

        try:
            await self._poll_loop()
        except asyncio.CancelledError:
            logger.info("[%s] 轮询已取消", self.name)
        except Exception as e:
            logger.error("[%s] 轮询异常退出: %s", self.name, e)
        finally:
            if self._session and not self._session.closed:
                await self._session.close()
            self._running = False
            logger.info("[%s] 微信适配器已停止", self.name)

    async def stop(self) -> None:
        """停止轮询"""
        self._running = False

    async def _poll_loop(self) -> None:
        """主轮询循环"""
        assert self._session is not None

        sync_buf = _load_sync_buf(self.config.weixin_account_id)
        timeout_ms = LONG_POLL_TIMEOUT_MS

        while self._running:
            try:
                response = await get_updates(
                    self._session,
                    base_url=self.config.weixin_base_url,
                    token=self.config.weixin_token,
                    sync_buf=sync_buf,
                    timeout_ms=timeout_ms,
                )

                # 检查服务端建议的超时时间
                suggested_timeout = response.get("longpolling_timeout_ms")
                if isinstance(suggested_timeout, int) and suggested_timeout > 0:
                    timeout_ms = suggested_timeout

                # 检查错误
                ret = response.get("ret", 0)
                errcode = response.get("errcode", 0)
                if ret not in (0, None) or errcode not in (0, None):
                    if ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE:
                        logger.error("[%s] Session 过期，暂停 10 分钟后重试", self.name)
                        await asyncio.sleep(600)
                        self._consecutive_failures = 0
                        continue

                    self._consecutive_failures += 1
                    logger.warning(
                        "[%s] getUpdates 失败 ret=%s errcode=%s (%d/%d)",
                        self.name, ret, errcode,
                        self._consecutive_failures, MAX_CONSECUTIVE_FAILURES,
                    )
                    delay = BACKOFF_DELAY_SECONDS if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES else RETRY_DELAY_SECONDS
                    await asyncio.sleep(delay)
                    if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        self._consecutive_failures = 0
                    continue

                # 成功
                self._consecutive_failures = 0

                # 更新同步缓冲区
                new_sync_buf = str(response.get("get_updates_buf") or "")
                if new_sync_buf:
                    sync_buf = new_sync_buf
                    _save_sync_buf(self.config.weixin_account_id, sync_buf)

                # 处理消息
                for message in response.get("msgs") or []:
                    asyncio.create_task(self._process_message(message))

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._consecutive_failures += 1
                logger.error(
                    "[%s] 轮询错误 (%d/%d): %s",
                    self.name, self._consecutive_failures, MAX_CONSECUTIVE_FAILURES, e,
                )
                delay = BACKOFF_DELAY_SECONDS if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES else RETRY_DELAY_SECONDS
                await asyncio.sleep(delay)
                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self._consecutive_failures = 0

    async def _process_message(self, message: Dict[str, Any]) -> None:
        """处理单条消息"""
        assert self._session is not None

        try:
            sender_id = str(message.get("from_user_id") or "").strip()
            if not sender_id:
                return
            if sender_id == self.config.weixin_account_id:
                return  # 忽略自己发的消息

            # 消息去重
            message_id = str(message.get("message_id") or "").strip()
            if message_id:
                if self._dedup.is_duplicate(message_id):
                    return
                self._processed_ids.add(message_id)

            # 提取文本
            item_list = message.get("item_list") or []
            text = _extract_text(item_list)

            # 如果有媒体但没有文本，暂不支持
            if not text:
                has_media = any(
                    item.get("type") in (ITEM_IMAGE, ITEM_VOICE, ITEM_FILE, ITEM_VIDEO)
                    for item in item_list
                )
                if has_media:
                    logger.info("[%s] 收到媒体消息（暂不支持），来自: %s", self.name, sender_id[:8])
                    await self._send_reply(sender_id, "暂时不支持接收图片和文件哦～", None)
                return

            # 保存 context_token
            context_token = str(message.get("context_token") or "").strip()
            if context_token:
                self._token_store.set(self.config.weixin_account_id, sender_id, context_token)

            logger.info("[%s] 收到消息 from=%s: %.40s", self.name, sender_id[:8], text)

            # 处理命令
            if text.startswith("/"):
                await self._handle_command(sender_id, text, context_token)
                return

            # 正常消息 → 调后端 AI
            await self._handle_chat(sender_id, text, context_token)

        except Exception as e:
            logger.error("[%s] 处理消息失败: %s", self.name, e, exc_info=True)

    async def _handle_command(self, sender_id: str, command: str, context_token: Optional[str]) -> None:
        """处理命令消息"""
        assert self._session is not None

        cmd = command.strip().lower()

        from config.matching_rules import EXIT_COMMANDS, SCENE_COMMAND_PREFIXES
        if cmd in EXIT_COMMANDS:
            result = await call_backend_back_to_channel(
                self._session,
                backend_url=self.config.backend_url,
                platform="weixin",
                platform_user_id=sender_id,
            )
            reply = result.get("message", "已回到闲聊模式。")
            await self._send_reply(sender_id, reply, context_token)

        elif any(cmd.startswith(p) for p in SCENE_COMMAND_PREFIXES):
            result = await call_backend_switch_scene(
                self._session,
                backend_url=self.config.backend_url,
                platform="weixin",
                platform_user_id=sender_id,
                scene_command=command,
            )
            if result.get("ok"):
                scene_name = result.get("scene_name", "")
                reply = f"已切换到场景「{scene_name}」。您可以发送「/闲聊」回到闲聊模式。"
            else:
                reply = result.get("message", "切换场景失败")
            await self._send_reply(sender_id, reply, context_token)

        elif cmd == "/help" or cmd == "/帮助":
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
            await self._send_reply(sender_id, reply, context_token)

        elif cmd == "/场景列表" or cmd == "/scenes":
            reply = "📋 可用场景：天气查询、旅游推荐、信息搜索。\n输入 `/进入场景名` 来切换到对应场景。"
            await self._send_reply(sender_id, reply, context_token)

        else:
            # 未知命令 → 当作普通消息处理
            await self._handle_chat(sender_id, command, context_token)

    async def _handle_chat(self, sender_id: str, text: str, context_token: Optional[str]) -> None:
        """处理聊天消息 — 调后端 AI 获取回复"""
        assert self._session is not None

        result = await call_backend_chat(
            self._session,
            backend_url=self.config.backend_url,
            platform="weixin",
            platform_user_id=sender_id,
            content=text,
        )

        reply = result.get("reply", "")
        switch_hint = result.get("switch_hint")

        if reply:
            await self._send_reply(sender_id, reply, context_token)

            # 如果有场景切换提示，再发一条
            if switch_hint:
                await self._send_reply(sender_id, f"\n💡 {switch_hint}", context_token)

    async def _send_reply(self, to_user_id: str, text: str, context_token: Optional[str]) -> None:
        """发送回复到微信"""
        assert self._session is not None

        try:
            # 获取该用户的 context_token
            token = context_token or self._token_store.get(self.config.weixin_account_id, to_user_id)

            await send_message(
                self._session,
                base_url=self.config.weixin_base_url,
                token=self.config.weixin_token,
                to_user_id=to_user_id,
                text=text,
                context_token=token,
                client_id="zuoshanke_gateway",
            )
            logger.info("[%s] 已回复 %s: %.40s", self.name, to_user_id[:8], text)
        except Exception as e:
            logger.error("[%s] 发送回复失败: %s", self.name, e)


# ── Gateway 主程序 ──

def print_banner() -> None:
    print("=" * 50)
    print("  坐山客 Gateway v0.1")
    print("  多平台消息网关")
    print("=" * 50)
    print()


async def main():
    print_banner()

    config = GatewayConfig()

    if not config.is_configured:
        logger.error("⚠️  微信未配置！请设置 WEIXIN_TOKEN 和 WEIXIN_ACCOUNT_ID")
        logger.info("")
        logger.info("配置方式：")
        logger.info(f"  1. 编辑 {GatewayConfig.GATEWAY_ENV_FILE} 文件")
        logger.info("     写入：")
        logger.info("       WEIXIN_TOKEN=your_token")
        logger.info("       WEIXIN_ACCOUNT_ID=your_account_id")
        logger.info("  2. 或设置环境变量：")
        logger.info("       export WEIXIN_TOKEN=your_token")
        logger.info("       export WEIXIN_ACCOUNT_ID=your_account_id")
        return 1

    logger.info(f"微信 Account ID: {config.weixin_account_id[:8]}...")
    logger.info(f"后端地址: {config.backend_url}")
    logger.info("")

    adapter = WeixinAdapter(config)

    # 信号处理
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("收到停止信号，正在关闭...")
        stop_event.set()
        asyncio.ensure_future(adapter.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows 不支持 signal handler
            pass

    # 启动适配器
    logger.info("🚀 微信适配器启动中...")
    adapter_task = asyncio.create_task(adapter.start())

    # 等待停止信号
    await stop_event.wait()

    # 等待适配器结束
    try:
        await asyncio.wait_for(adapter_task, timeout=10)
    except asyncio.TimeoutError:
        adapter_task.cancel()
        try:
            await adapter_task
        except asyncio.CancelledError:
            pass

    logger.info("👋 Gateway 已停止")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
