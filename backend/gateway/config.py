"""Gateway 配置管理

从以下位置读取平台配置（优先级从高到低）：
1. 环境变量
2. 配置文件 ~/.zuoshanke/gateway.env（新版，多平台）
3. 配置文件 ~/.zuoshanke/.gateway.env（旧版，仅微信）

多平台配置模式（推荐）：
    # ~/.zuoshanke/gateway.env
    WEIXIN_TOKEN=xxx
    WEIXIN_ACCOUNT_ID=xxx
    TELEGRAM_TOKEN=123456:ABC-DEF...
    DISCORD_BOT_TOKEN=xxx

旧版单微信模式（向后兼容）：
    # ~/.zuoshanke/.gateway.env
    WEIXIN_TOKEN=xxx
    WEIXIN_ACCOUNT_ID=xxx
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional
from config.paths import ZUOSHANKE_HOME

# ── 配置文件路径 ──
GATEWAY_ENV_FILE_OLD = ZUOSHANKE_HOME / ".gateway.env"   # 旧版（单微信）
GATEWAY_ENV_FILE_NEW = ZUOSHANKE_HOME / "gateway.env"    # 新版（多平台）

logger = logging.getLogger("gateway.config")

# iLink 默认值
ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

# API 端点
EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"

from config.constants import GATEWAY_LONG_POLL_TIMEOUT_MS as LONG_POLL_TIMEOUT_MS, GATEWAY_MAX_CONSECUTIVE_FAILURES as MAX_CONSECUTIVE_FAILURES, GATEWAY_RETRY_DELAY_SECONDS as RETRY_DELAY_SECONDS, GATEWAY_BACKOFF_DELAY_SECONDS as BACKOFF_DELAY_SECONDS
from config.urls import BACKEND_BASE_URL

# ── 旧版配置类（向后兼容） ──

class GatewayConfig:
    """Gateway 配置（旧版，仅微信）"""

    GATEWAY_ENV_FILE = GATEWAY_ENV_FILE_OLD

    def __init__(self):
        self.weixin_token: str = ""
        self.weixin_account_id: str = ""
        self.weixin_base_url: str = ILINK_BASE_URL
        self.backend_url: str = BACKEND_BASE_URL
        self.sync_buf: str = ""

        self._load_from_env()
        self._load_from_file()
        # 也尝试读取新版配置
        self._load_from_new_config()

    def _load_from_env(self) -> None:
        """从环境变量读取"""
        self.weixin_token = os.environ.get("WEIXIN_TOKEN") or self.weixin_token
        self.weixin_account_id = os.environ.get("WEIXIN_ACCOUNT_ID") or self.weixin_account_id
        self.weixin_base_url = os.environ.get("WEIXIN_BASE_URL") or self.weixin_base_url
        self.backend_url = os.environ.get("ZUOSHANKE_BACKEND_URL") or self.backend_url

    def _load_from_file(self) -> None:
        """从旧版配置文件读取"""
        if not GATEWAY_ENV_FILE_OLD.exists():
            return
        try:
            lines = GATEWAY_ENV_FILE_OLD.read_text().strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key == "WEIXIN_TOKEN" and not self.weixin_token:
                    self.weixin_token = value
                elif key == "WEIXIN_ACCOUNT_ID" and not self.weixin_account_id:
                    self.weixin_account_id = value
                elif key == "WEIXIN_BASE_URL" and not self.weixin_base_url:
                    self.weixin_base_url = value
                elif key == "ZUOSHANKE_BACKEND_URL" and not self.backend_url:
                    self.backend_url = value
        except Exception as e:
            print(f"[Gateway] 读取旧版配置文件失败: {e}")

    def _load_from_new_config(self) -> None:
        """从新版配置读取微信配置（作为补充）"""
        if not GATEWAY_ENV_FILE_NEW.exists():
            return
        try:
            lines = GATEWAY_ENV_FILE_NEW.read_text().strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key == "WEIXIN_TOKEN" and not self.weixin_token:
                    self.weixin_token = value
                elif key == "WEIXIN_ACCOUNT_ID" and not self.weixin_account_id:
                    self.weixin_account_id = value
                elif key == "WEIXIN_BASE_URL" and not self.weixin_base_url:
                    self.weixin_base_url = value
                elif key == "ZUOSHANKE_BACKEND_URL" and not self.backend_url:
                    self.backend_url = value
        except Exception as e:
            print(f"[Gateway] 读取新版配置文件失败: {e}")

    @property
    def is_configured(self) -> bool:
        return bool(self.weixin_token) and bool(self.weixin_account_id)


def save_gateway_config(token: str, account_id: str, base_url: str = ILINK_BASE_URL) -> None:
    """持久化旧版 Gateway 配置"""
    ZUOSHANKE_HOME.mkdir(parents=True, exist_ok=True)
    content = f"""# 坐山客 Gateway 配置
# 安全提示：此文件包含敏感信息，请勿分享
WEIXIN_TOKEN={token}
WEIXIN_ACCOUNT_ID={account_id}
WEIXIN_BASE_URL={base_url}
"""
    GATEWAY_ENV_FILE_OLD.write_text(content)
    GATEWAY_ENV_FILE_OLD.chmod(0o600)
    print(f"[Gateway] 配置已保存到 {GATEWAY_ENV_FILE_OLD}")


def detect_config_format() -> str:
    """检测使用的是新版还是旧版配置格式"""
    if GATEWAY_ENV_FILE_NEW.exists():
        return "new"
    if GATEWAY_ENV_FILE_OLD.exists():
        return "old"
    return "none"
