"""Gateway 配置管理

从以下位置读取微信配置（优先级从高到低）：
1. 环境变量 WEIXIN_TOKEN, WEIXIN_ACCOUNT_ID, WEIXIN_BASE_URL
2. 配置文件 ~/.zuoshanke/.gateway.env
3. 硬编码默认值
"""
import os
import json
from pathlib import Path
from config.paths import ZUOSHANKE_HOME

GATEWAY_ENV_FILE = ZUOSHANKE_HOME / ".gateway.env"


# iLink 默认值
ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

# API 端点
EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"

from config.constants import GATEWAY_LONG_POLL_TIMEOUT_MS, GATEWAY_MAX_CONSECUTIVE_FAILURES, GATEWAY_RETRY_DELAY_SECONDS, GATEWAY_BACKOFF_DELAY_SECONDS
from config.urls import BACKEND_BASE_URL

# 后端 API
# ── 轮询参数（微信 iLink） ──


class GatewayConfig:
    """Gateway 配置"""

    def __init__(self):
        self.weixin_token: str = ""
        self.weixin_account_id: str = ""
        self.weixin_base_url: str = ILINK_BASE_URL
        self.backend_url: str = BACKEND_BASE_URL
        self.sync_buf: str = ""

        self._load_from_env()
        self._load_from_file()

    def _load_from_env(self) -> None:
        """从环境变量读取"""
        self.weixin_token = os.environ.get("WEIXIN_TOKEN") or self.weixin_token
        self.weixin_account_id = os.environ.get("WEIXIN_ACCOUNT_ID") or self.weixin_account_id
        self.weixin_base_url = os.environ.get("WEIXIN_BASE_URL") or self.weixin_base_url
        self.backend_url = os.environ.get("ZUOSHANKE_BACKEND_URL") or self.backend_url

    def _load_from_file(self) -> None:
        """从配置文件读取"""
        if not GATEWAY_ENV_FILE.exists():
            return
        try:
            lines = GATEWAY_ENV_FILE.read_text().strip().split("\n")
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
            print(f"[Gateway] 读取配置文件失败: {e}")

    @property
    def is_configured(self) -> bool:
        """是否已配置（有 token 和 account_id）"""
        return bool(self.weixin_token) and bool(self.weixin_account_id)


def save_gateway_config(token: str, account_id: str, base_url: str = ILINK_BASE_URL) -> None:
    """持久化 Gateway 配置"""
    ZUOSHANKE_HOME.mkdir(parents=True, exist_ok=True)
    content = f"""# 坐山客 Gateway 配置
# 安全提示：此文件包含敏感信息，请勿分享
WEIXIN_TOKEN={token}
WEIXIN_ACCOUNT_ID={account_id}
WEIXIN_BASE_URL={base_url}
"""
    GATEWAY_ENV_FILE.write_text(content)
    GATEWAY_ENV_FILE.chmod(0o600)
    print(f"[Gateway] 配置已保存到 {GATEWAY_ENV_FILE}")
