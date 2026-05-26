"""Telegram 平台适配器

使用 python-telegram-bot 库实现消息接收和发送。
支持 polling 模式（开发/轻量部署）和 webhook 模式（生产）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from gateway.adapters.base import BasePlatformAdapter

logger = logging.getLogger("gateway.adapters.telegram")

# ── 检查 python-telegram-bot 是否可用 ──
try:
    from telegram import Update, Bot
    from telegram.ext import (
        Application,
        MessageHandler as TGMessageHandler,
        filters,
    )
    from telegram.constants import ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning(
        "[telegram] python-telegram-bot 未安装，Telegram 适配器不可用。"
        "请执行: pip install python-telegram-bot"
    )


MAX_MESSAGE_LENGTH = 4096  # Telegram 单条消息上限（UTF-16 码元）


def check_requirements() -> bool:
    return TELEGRAM_AVAILABLE


class TelegramAdapter(BasePlatformAdapter):
    """Telegram 适配器 — 使用 python-telegram-bot Application"""

    def __init__(self, config: Dict[str, Any]):
        if not TELEGRAM_AVAILABLE:
            raise RuntimeError("python-telegram-bot 未安装")

        super().__init__(config)
        self._token: str = config.get("token", "")
        self._proxy_url: Optional[str] = config.get("proxy_url")
        self._allowed_users: list = []
        allowed_raw = config.get("allowed_users", "")
        if allowed_raw:
            self._allowed_users = [u.strip() for u in allowed_raw.split(",") if u.strip()]

        self._app: Optional[Application] = None
        self._update_queue: Optional[asyncio.Queue] = None
        self._poll_task: Optional[asyncio.Task] = None

        if not self._token:
            logger.error("[telegram] 未配置 TOKEN，请设置 TELEGRAM_TOKEN")

    @property
    def platform_name(self) -> str:
        return "telegram"

    async def start(self) -> None:
        """启动 Telegram 适配器"""
        if not self._token:
            return

        logger.info("[telegram] 适配器启动中...")

        # 构建 Application
        builder = Application.builder().token(self._token)

        if self._proxy_url:
            from telegram.request import HTTPXRequest
            proxy_request = HTTPXRequest(proxy_url=self._proxy_url)
            builder = builder.request(proxy_request)

        self._app = builder.build()

        # 注册消息处理器
        self._app.add_handler(
            TGMessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        self._app.add_handler(
            TGMessageHandler(filters.COMMAND, self._on_command)
        )

        # 启动 polling（后台任务）
        self._running = True
        self._poll_task = asyncio.create_task(self._run_polling())

        logger.info("[telegram] 适配器已启动")

    async def stop(self) -> None:
        """停止适配器"""
        self._running = False
        if self._app:
            try:
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning("[telegram] 停止时出错: %s", e)
            self._app = None

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        await self._close_http_session()
        logger.info("[telegram] 适配器已停止")

    async def send_message(
        self,
        to_user_id: str,
        text: str,
        context_token: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """发送文本消息到 Telegram"""
        if not text:
            return {"ok": False, "error": "empty text"}

        bot = self._app.bot if self._app else None
        if not bot:
            return {"ok": False, "error": "bot not initialized"}

        try:
            # Telegram 有消息长度限制，超长时截断
            if len(text) > MAX_MESSAGE_LENGTH:
                text = text[: MAX_MESSAGE_LENGTH - 3] + "..."

            sent = await bot.send_message(
                chat_id=to_user_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
            logger.info("[telegram] 已回复 %s: %.40s", to_user_id[:8], text)
            return {"ok": True, "message_id": sent.message_id}
        except Exception as e:
            logger.error("[telegram] 发送失败: %s", e)
            # Markdown 解析失败时降级为纯文本重试
            try:
                sent = await bot.send_message(
                    chat_id=to_user_id,
                    text=text,
                )
                return {"ok": True, "message_id": sent.message_id}
            except Exception as e2:
                return {"ok": False, "error": str(e2)}

    async def send_typing(self, to_user_id: str) -> None:
        """发送 typing 指示器"""
        bot = self._app.bot if self._app else None
        if not bot:
            return
        try:
            await bot.send_chat_action(chat_id=to_user_id, action="typing")
        except Exception:
            pass

    # ── 内部方法 ──

    async def _run_polling(self) -> None:
        """在后台事件循环中运行 polling"""
        assert self._app is not None
        try:
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling()

            # 保持运行直到停止
            while self._running:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[telegram] polling 异常: %s", e)
        finally:
            if self._app:
                try:
                    await self._app.updater.stop()
                except Exception:
                    pass

    async def _on_message(self, update: Update, context) -> None:
        """处理普通文本消息"""
        if not update.message or not update.message.text:
            return
        await self._process_telegram_message(update, update.message.text)

    async def _on_command(self, update: Update, context) -> None:
        """处理命令消息"""
        if not update.message or not update.message.text:
            return
        text = update.message.text.strip()

        user_id = str(update.effective_user.id) if update.effective_user else ""
        chat_id = str(update.effective_chat.id) if update.effective_chat else user_id

        # 命令处理
        if text in ("/start", "/help"):
            reply = (
                "🤖 **坐山客 Telegram 助手**\n\n"
                "我是坐山客，你的 AI 伙伴。\n\n"
                "**使用方式**：\n"
                "• 直接发送消息与我聊天\n"
                "• 发送 `/进入场景名` 切换到特定场景\n"
                "• 发送 `/闲聊` 回到闲聊模式\n"
                "• 发送 `/帮助` 查看此帮助"
            )
            await self.send_message(chat_id, reply)
            return

        if text in ("/闲聊", "/退出"):
            result = await self._route_back_to_channel(chat_id)
            reply = result.get("message", "已回到闲聊模式。")
            await self.send_message(chat_id, reply)
            return

        if text.startswith("/进入"):
            result = await self._route_switch_scene(chat_id, text)
            if result.get("ok"):
                scene_name = result.get("scene_name", "")
                reply = f"已切换到场景「{scene_name}」。发送 /闲聊 回到闲聊模式。"
            else:
                reply = result.get("message", "切换场景失败")
            await self.send_message(chat_id, reply)
            return

        # 未知命令→当普通消息处理
        await self._process_telegram_message(update, text)

    async def _process_telegram_message(
        self, update: Update, text: str,
    ) -> None:
        """将 Telegram 消息转发到后端"""
        user_id = str(update.effective_user.id) if update.effective_user else ""
        chat_id = str(update.effective_chat.id) if update.effective_chat else user_id
        username = update.effective_user.username if update.effective_user else None

        # 群聊/频道中只处理 @bot 消息
        if update.effective_chat and update.effective_chat.type != "private":
            # 不处理非 @bot 消息
            return

        # 发 typing 指示
        asyncio.create_task(self.send_typing(chat_id))

        # 调后端
        result = await self._route_to_backend(
            chat_id, text, platform_username=username,
        )
        reply = result.get("reply", "")
        if reply:
            await self.send_message(chat_id, reply)
