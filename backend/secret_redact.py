"""秘密遮盖系统 — 在日志和输出中自动遮盖敏感信息

用法:
    from secret_redact import redact, SecretRedactFilter

    # 直接遮盖字典
    safe = redact({"api_key": "sk-xxx123", "name": "test"})
    # → {"api_key": "sk-***...***", "name": "test"}

    # 作为日志过滤器
    handler.addFilter(SecretRedactFilter())
"""

import re
import logging
from typing import Any

# ── 敏感字段名（大小写不敏感） ──
SENSITIVE_KEYS = {
    "api_key", "apikey", "api-key",
    "password", "passwd", "pwd",
    "secret", "secret_key", "secretkey",
    "token", "access_token", "refresh_token",
    "authorization", "auth",
    "private_key", "privatekey",
}

# ── 敏感值模式（正则） ──
SENSITIVE_PATTERNS = [
    # OpenAI / DeepSeek 风格 API Key
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),
    re.compile(r'sk-[a-zA-Z0-9_-]{32,}'),
    # Bearer token
    re.compile(r'Bearer\s+[a-zA-Z0-9._-]{20,}'),
    # 通用 token（长串 base64 风格）
    re.compile(r'[a-zA-Z0-9_-]{40,}'),
]

REDACTED_PLACEHOLDER = "***...***"


def _is_sensitive_key(key: str) -> bool:
    """判断字段名是否敏感（大小写不敏感）"""
    return key.lower() in SENSITIVE_KEYS


def _redact_value(value: str, max_keep: int = 4) -> str:
    """遮盖敏感字符串值

    Args:
        value: 原始字符串
        max_keep: 保留前 N 个字符用于识别，其余遮盖

    Returns:
        遮盖后的字符串
    """
    if not value or len(value) < max_keep + 4:
        return REDACTED_PLACEHOLDER
    return value[:max_keep] + REDACTED_PLACEHOLDER


def _redact_string(text: str) -> str:
    """对字符串中的敏感模式进行遮盖"""
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub(
            lambda m: _redact_value(m.group(0)),
            text
        )
    return text


def redact(obj: Any, depth: int = 0, max_depth: int = 20) -> Any:
    """递归遮盖对象中的敏感信息

    支持 dict / list / str / 基本类型。
    字典按 key 名匹配敏感字段；字符串按正则匹配敏感模式。

    Args:
        obj: 要遮盖的对象
        depth: 当前递归深度（内部使用）
        max_depth: 最大递归深度，防止无限递归

    Returns:
        遮盖后的对象副本（不修改原始对象）
    """
    if depth > max_depth:
        return obj

    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if _is_sensitive_key(k) and isinstance(v, (str, bytes)):
                # 敏感字段名 → 遮盖值
                result[k] = _redact_value(str(v))
            elif isinstance(v, str):
                # 字符串值 → 检查敏感模式
                result[k] = _redact_string(v)
            else:
                result[k] = redact(v, depth + 1, max_depth)
        return result

    elif isinstance(obj, list):
        return [redact(item, depth + 1, max_depth) for item in obj]

    elif isinstance(obj, str):
        return _redact_string(obj)

    return obj


class SecretRedactFilter(logging.Filter):
    """日志过滤器 — 自动遮盖日志消息中的敏感信息

    用法:
        handler.addFilter(SecretRedactFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录，遮盖敏感信息"""
        if isinstance(record.msg, str):
            record.msg = _redact_string(record.msg)

        # 处理 args 中的敏感信息
        if record.args:
            try:
                new_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        new_args.append(_redact_string(arg))
                    elif isinstance(arg, dict):
                        new_args.append(redact(arg))
                    elif isinstance(arg, (list, tuple)):
                        new_args.append(redact(arg))
                    else:
                        new_args.append(arg)
                record.args = tuple(new_args) if isinstance(record.args, tuple) else new_args
            except Exception:
                pass

        return True  # 不过滤任何记录，只做遮盖


def redact_headers(headers: dict) -> dict:
    """专门遮盖 HTTP 请求头中的 Authorization

    Args:
        headers: 请求头字典

    Returns:
        遮盖后的请求头副本
    """
    result = dict(headers)
    for key in result:
        if key.lower() in ("authorization", "x-api-key", "api-key"):
            val = str(result[key])
            if len(val) > 10:
                result[key] = val[:8] + REDACTED_PLACEHOLDER
            else:
                result[key] = REDACTED_PLACEHOLDER
    return result
