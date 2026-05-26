"""多平台配置管理器

读取 `.env` 格式的配置文件（用户偏好），支持多平台独立配置。
每个平台以前缀区分：WEIXIN_*, TELEGRAM_*, DISCORD_* 等。

配置从以下位置读取（优先级从高到低）：
1. 环境变量
2. 配置文件 ~/.zuoshanke/gateway.env
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 自动定位项目根目录 ──
def _find_project_root() -> Path:
    """从当前文件位置向上找到 backend/ 目录"""
    here = Path(__file__).resolve().parent  # gateway/adapters/
    # 向上两级 = backend/
    for p in [here.parent.parent, here.parent, here]:
        if (p / "config" / "paths.py").exists():
            return p
    # 兜底：取文件所在目录的上级
    return here.parent.parent

_PROJECT_ROOT = _find_project_root()
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.paths import ZUOSHANKE_HOME

logger = logging.getLogger("gateway.adapters.config")

# ── 默认值 ──
GATEWAY_ENV_FILE = ZUOSHANKE_HOME / "gateway.env"

# ── 平台配置描述符 ──
# 每个平台的定义：前缀 / 必需字段 / 可选字段 / 适配器类名 / 展示名
PlatformDef = Dict[str, Any]

# 所有内置平台的定义
BUILTIN_PLATFORMS: Dict[str, PlatformDef] = {
    "weixin": {
        "prefix": "WEIXIN",
        "required": ["TOKEN", "ACCOUNT_ID"],
        "optional": ["BASE_URL"],
        "adapter": "WeixinAdapter",
        "module": "gateway.adapters.weixin",
        "display_name": "微信 (iLink)",
    },
    "telegram": {
        "prefix": "TELEGRAM",
        "required": ["TOKEN"],
        "optional": ["PROXY_URL", "ALLOWED_USERS"],
        "adapter": "TelegramAdapter",
        "module": "gateway.adapters.telegram",
        "display_name": "Telegram",
    },
    "discord": {
        "prefix": "DISCORD",
        "required": ["BOT_TOKEN"],
        "optional": ["GUILD_ID", "ALLOWED_CHANNELS"],
        "adapter": "DiscordAdapter",
        "module": "gateway.adapters.discord",
        "display_name": "Discord",
    },
    "signal": {
        "prefix": "SIGNAL",
        "required": ["PHONE_NUMBER"],
        "optional": ["API_URL"],
        "adapter": "SignalAdapter",
        "module": "gateway.adapters.signal",
        "display_name": "Signal",
    },
    "email": {
        "prefix": "EMAIL",
        "required": ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "IMAP_HOST", "IMAP_USER", "IMAP_PASS"],
        "optional": ["SMTP_TLS", "IMAP_PORT", "POLL_INTERVAL"],
        "adapter": "EmailAdapter",
        "module": "gateway.adapters.email",
        "display_name": "Email",
    },
    "slack": {
        "prefix": "SLACK",
        "required": ["BOT_TOKEN", "APP_TOKEN", "SIGNING_SECRET"],
        "optional": [],
        "adapter": "SlackAdapter",
        "module": "gateway.adapters.slack",
        "display_name": "Slack",
    },
    "whatsapp": {
        "prefix": "WHATSAPP",
        "required": ["TOKEN", "PHONE_NUMBER_ID"],
        "optional": ["API_VERSION", "VERIFY_TOKEN"],
        "adapter": "WhatsAppAdapter",
        "module": "gateway.adapters.whatsapp",
        "display_name": "WhatsApp",
    },
    "matrix": {
        "prefix": "MATRIX",
        "required": ["HOMESERVER", "USERNAME", "ACCESS_TOKEN"],
        "optional": ["DEVICE_ID"],
        "adapter": "MatrixAdapter",
        "module": "gateway.adapters.matrix",
        "display_name": "Matrix",
    },
    "feishu": {
        "prefix": "FEISHU",
        "required": ["APP_ID", "APP_SECRET"],
        "optional": ["BOT_NAME"],
        "adapter": "FeishuAdapter",
        "module": "gateway.adapters.feishu",
        "display_name": "飞书",
    },
    "dingtalk": {
        "prefix": "DINGTALK",
        "required": ["CLIENT_ID", "CLIENT_SECRET"],
        "optional": ["BOT_CODE"],
        "adapter": "DingTalkAdapter",
        "module": "gateway.adapters.dingtalk",
        "display_name": "钉钉",
    },
    "wecom": {
        "prefix": "WECOM",
        "required": ["CORP_ID", "CORP_SECRET", "AGENT_ID"],
        "optional": ["TOKEN", "ENCODING_AES_KEY"],
        "adapter": "WeComAdapter",
        "module": "gateway.adapters.wecom",
        "display_name": "企业微信",
    },
    "sms": {
        "prefix": "SMS",
        "required": ["PROVIDER", "API_KEY"],
        "optional": ["FROM_NUMBER", "API_SECRET"],
        "adapter": "SmsAdapter",
        "module": "gateway.adapters.sms",
        "display_name": "短信 (SMS)",
    },
    "yyb": {
        "prefix": "YYB",
        "required": ["ACCOUNT_ID", "TOKEN"],
        "optional": ["BASE_URL"],
        "adapter": "YuanBaoAdapter",
        "module": "gateway.adapters.yuanbao",
        "display_name": "元宝",
    },
}


def load_config(
    env_file: Optional[Path] = None,
) -> Dict[str, Dict[str, str]]:
    """从环境变量和配置文件加载所有平台的配置

    返回:
        {"weixin": {"token": "...", "account_id": "...", ...},
         "telegram": {"token": "..."}, ...}
    """
    if env_file is None:
        env_file = GATEWAY_ENV_FILE

    # 收集所有键值对
    raw_vars: Dict[str, str] = {}

    # 1. 配置文件
    if env_file.exists():
        try:
            for line in env_file.read_text().strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key and value:
                    raw_vars[key] = value
        except Exception as e:
            logger.warning("读取配置文件 %s 失败: %s", env_file, e)

    # 2. 环境变量（覆盖配置文件）
    for key, value in os.environ.items():
        raw_vars[key] = value

    # 3. 公共配置
    backend_url = raw_vars.get("ZUOSHANKE_BACKEND_URL", "http://localhost:8000")

    # 4. 按平台分组
    result: Dict[str, Dict[str, str]] = {}
    for plat_name, plat_def in BUILTIN_PLATFORMS.items():
        prefix = plat_def["prefix"] + "_"
        config: Dict[str, str] = {}

        for key, value in raw_vars.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                config[config_key] = value

        if config:
            config["backend_url"] = backend_url
            result[plat_name] = config

    return result


def get_enabled_platforms(
    env_file: Optional[Path] = None,
) -> List[Tuple[str, str, Dict[str, str]]]:
    """返回已配置（可启用）的平台列表

    返回:
        [(platform_name, display_name, config_dict), ...]
    """
    configs = load_config(env_file)
    result: List[Tuple[str, str, Dict[str, str]]] = []

    for plat_name, plat_def in BUILTIN_PLATFORMS.items():
        config = configs.get(plat_name)
        if not config:
            continue

        # 检查必需字段
        missing = []
        for req in plat_def["required"]:
            if req.lower() not in config:
                missing.append(req)

        if missing:
            logger.info(
                "[%s] 配置不完整，缺少: %s，跳过",
                plat_name, ", ".join(missing),
            )
            continue

        # 全部配置就绪
        adapter_module = plat_def.get("module", "")
        adapter_class = plat_def.get("adapter", "")
        result.append((plat_name, plat_def.get("display_name", plat_name), config))

    return result


def check_platform_ready(platform_name: str) -> bool:
    """检查特定平台是否已配置"""
    for pname, _, _ in get_enabled_platforms():
        if pname == platform_name:
            return True
    return False
