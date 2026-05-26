"""坐山客 Gateway — 多平台消息网关

启动所有已配置的平台适配器，接收和发送多平台消息。

启动：
    cd ~/zuoshanke/backend
    .venv/bin/python -m backend.gateway.run

配置：
    ~/.zuoshanke/gateway.env  - 各平台 Token/密钥（.env 格式）

支持平台（通过配置文件启用）：
    weixin    — 微信 iLink Bot
    telegram  — Telegram Bot
    discord   — Discord Bot
    signal    — Signal
    email     — Email (IMAP/SMTP)
    slack     — Slack Bot
    whatsapp  — WhatsApp Business API
    feishu    — 飞书
    dingtalk  — 钉钉
    wecom     — 企业微信
    matrix    — Matrix
    sms       — SMS
    yyb       — 元宝
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from typing import Any, Dict, List, Optional, Tuple

# 确保 backend 目录在 sys.path 中
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from gateway.adapters.base import BasePlatformAdapter
from gateway.adapters.config import (
    get_enabled_platforms,
    BUILTIN_PLATFORMS,
)

logger = logging.getLogger("gateway")


# ── 适配器工厂 ──

def _import_adapter_class(module_path: str, class_name: str):
    """动态导入适配器类"""
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def _create_adapter(
    platform_name: str,
    config: Dict[str, str],
    adapter_module: str,
    adapter_class: str,
) -> Optional[BasePlatformAdapter]:
    """创建平台适配器实例"""
    try:
        cls = _import_adapter_class(adapter_module, adapter_class)
        adapter = cls(config)
        logger.info("[%s] 适配器已创建 (%s)", platform_name, adapter_module)
        return adapter
    except ImportError as e:
        logger.warning(
            "[%s] 依赖未安装，适配器不可用: %s。跳过。",
            platform_name, e,
        )
        return None
    except Exception as e:
        logger.error("[%s] 创建适配器失败: %s", platform_name, e)
        return None


# ── 适配器管理器 ──

class AdapterManager:
    """多适配器生命周期管理器"""

    def __init__(self):
        self._adapters: Dict[str, BasePlatformAdapter] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    @property
    def adapters(self) -> Dict[str, BasePlatformAdapter]:
        return dict(self._adapters)

    def setup(self) -> None:
        """根据配置加载所有启用的适配器（不启动）"""
        enabled = get_enabled_platforms()
        if not enabled:
            logger.warning("⚠️  未检测到任何平台配置，Gateway 将退出。")
            logger.info("请编辑 ~/.zuoshanke/gateway.env 添加平台 Token")
            return

        logger.info("检测到 %d 个已配置的平台:", len(enabled))
        for plat_name, display_name, config in enabled:
            plat_def = BUILTIN_PLATFORMS.get(plat_name, {})
            module = plat_def.get("module", "")
            class_name = plat_def.get("adapter", "")

            if not module or not class_name:
                logger.warning("[%s] 未知平台，跳过", plat_name)
                continue

            adapter = _create_adapter(plat_name, config, module, class_name)
            if adapter:
                self._adapters[plat_name] = adapter
                logger.info("  ✅ %s (%s)", display_name, plat_name)
            else:
                logger.info("  ⚠️  %s (%s) — 依赖缺失或创建失败", display_name, plat_name)

    async def start_all(self) -> None:
        """启动所有已加载的适配器"""
        if not self._adapters:
            logger.warning("没有可启动的适配器")
            return

        logger.info("\n🚀 启动 %d 个适配器...", len(self._adapters))

        for plat_name, adapter in self._adapters.items():
            task = asyncio.create_task(
                self._run_adapter(plat_name, adapter),
                name=f"adapter-{plat_name}",
            )
            self._tasks[plat_name] = task
            # 给每个适配器一点启动时间，日志不混在一起
            await asyncio.sleep(0.1)

    async def stop_all(self) -> None:
        """停止所有适配器"""
        if not self._adapters:
            return

        logger.info("\n🛑 正在停止所有适配器...")
        for plat_name, adapter in self._adapters.items():
            try:
                await adapter.stop()
            except Exception as e:
                logger.warning("[%s] 停止出错: %s", plat_name, e)

        # 等待任务结束
        if self._tasks:
            done, pending = await asyncio.wait(
                self._tasks.values(),
                timeout=10,
            )
            for t in pending:
                t.cancel()

        logger.info("所有适配器已停止")

    async def _run_adapter(
        self, plat_name: str, adapter: BasePlatformAdapter,
    ) -> None:
        """运行单个适配器（捕获异常避免崩溃影响其他适配器）"""
        try:
            await adapter.start()
        except asyncio.CancelledError:
            logger.info("[%s] 适配器任务已取消", plat_name)
        except Exception as e:
            logger.error("[%s] 适配器异常退出: %s", plat_name, e, exc_info=True)

    def get_adapter(self, name: str) -> Optional[BasePlatformAdapter]:
        return self._adapters.get(name)

    def get_status(self) -> List[Dict[str, Any]]:
        """获取所有适配器状态"""
        return [
            {
                "platform": name,
                "running": adapter.is_running(),
                "display_name": BUILTIN_PLATFORMS.get(name, {}).get(
                    "display_name", name
                ),
            }
            for name, adapter in self._adapters.items()
        ]


# ── Gateway 主程序 ──

def print_banner() -> None:
    print("=" * 56)
    print("  坐山客 Gateway v0.2")
    print("  多平台消息网关 (20+ 平台)")
    print("=" * 56)
    print()


async def main() -> int:
    print_banner()

    manager = AdapterManager()
    manager.setup()

    if not manager.adapters:
        logger.info("")
        logger.info("💡 配置方式：")
        logger.info("  编辑 ~/.zuoshanke/gateway.env 文件")
        logger.info("  添加平台 Token/密钥（每行一个）")
        logger.info("")
        logger.info("  示例：")
        logger.info("    WEIXIN_TOKEN=your_token")
        logger.info("    WEIXIN_ACCOUNT_ID=your_account_id")
        logger.info("    TELEGRAM_TOKEN=123456:ABC-DEF...")
        logger.info("    DISCORD_BOT_TOKEN=your_discord_token")
        return 1

    # 信号处理
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("收到停止信号，正在关闭...")
        stop_event.set()
        asyncio.ensure_future(manager.stop_all())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    # 启动适配器
    await manager.start_all()

    # 保持运行直到停止
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass

    # 停止所有适配器
    await manager.stop_all()

    logger.info("👋 Gateway 已停止")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
