"""坐山客多平台网关

支持 20+ 消息平台的一站式消息网关。
每个平台实现为一个适配器（继承 BasePlatformAdapter），
由 AdapterManager 统一管理生命周期。

支持的平台（通过配置启用）：
    weixin, telegram, discord, signal, email, slack, whatsapp,
    matrix, feishu, dingtalk, wecom, sms, yyb 等

启动:
    python -m backend.gateway.run
"""

from .adapters.base import BasePlatformAdapter, RETRY_DELAY_SECONDS, BACKOFF_DELAY_SECONDS, MAX_CONSECUTIVE_FAILURES
from .adapters.config import get_enabled_platforms, check_platform_ready
from .run import AdapterManager, main

__version__ = "0.2.0"
