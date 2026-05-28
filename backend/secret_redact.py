"""秘密遮盖系统 — 在日志和输出中自动遮盖敏感信息

用法:
    from secret_redact import redact, SecretRedactFilter

    # 直接遮盖字典
    safe = redact({"api_key": "sk-xxx123", "name": "test"})
    # → {"api_key": "sk-***...***", "name": "test"}

    # 作为日志过滤器
    handler.addFilter(SecretRedactFilter())

启用/禁用: ZUOSHANKE_REDACT_SECRETS 环境变量（默认 true）
    设置为 false / 0 / no 可关闭遮盖（排查问题时用）
"""

import os
import re
import logging
from typing import Any

# ── 环境变量开关（启动时快照，运行时改 env 无效） ──
_REDACT_ENABLED = os.getenv("ZUOSHANKE_REDACT_SECRETS", "true").lower() in (
    "1", "true", "yes", "on"
)

# ── 启动告警（遮盖关闭时打 WARNING） ──
if not _REDACT_ENABLED:
    _warn_logger = logging.getLogger("secret_redact")
    _warn_logger.warning(
        "⚠️ ZUOSHANKE_REDACT_SECRETS 已关闭！API Key/Token 将以明文出现在日志中。"
        " 如需开启，请设置 ZUOSHANKE_REDACT_SECRETS=true 后重启。"
    )

# ── 敏感字段名（大小写不敏感） ──
SENSITIVE_KEYS = frozenset({
    "api_key", "apikey", "api-key",
    "password", "passwd", "pwd",
    "secret", "secret_key", "secretkey",
    "token", "access_token", "refresh_token", "id_token",
    "authorization", "auth", "bearer",
    "private_key", "privatekey",
    "client_secret", "jwt",
})

# ── 已知 API Key 前缀（带边界检测） ──
_PREFIX_PATTERNS = [
    # 云 API 服务
    r"sk-[A-Za-z0-9]{20,}",              # OpenAI / DeepSeek / OpenRouter
    r"sk-[A-Za-z0-9_-]{32,}",            # Anthropic sk-ant-*
    # GitHub
    r"ghp_[A-Za-z0-9]{10,}",             # GitHub PAT (classic)
    r"github_pat_[A-Za-z0-9_]{10,}",     # GitHub PAT (fine-grained)
    r"gho_[A-Za-z0-9]{10,}",             # GitHub OAuth access token
    r"ghu_[A-Za-z0-9]{10,}",             # GitHub user-to-server token
    r"ghs_[A-Za-z0-9]{10,}",             # GitHub server-to-server token
    r"ghr_[A-Za-z0-9]{10,}",             # GitHub refresh token
    # 其他服务
    r"AIza[A-Za-z0-9_-]{30,}",           # Google API Key
    r"xox[baprs]-[A-Za-z0-9-]{10,}",     # Slack tokens
    r"hf_[A-Za-z0-9]{10,}",              # HuggingFace token
    r"gsk_[A-Za-z0-9]{10,}",             # Groq Cloud API key
    r"r8_[A-Za-z0-9]{10,}",              # Replicate API token
    r"pplx-[A-Za-z0-9]{10,}",            # Perplexity
    r"sk_live_[A-Za-z0-9]{10,}",         # Stripe secret key (live)
    r"sk_test_[A-Za-z0-9]{10,}",         # Stripe secret key (test)
    r"rk_live_[A-Za-z0-9]{10,}",         # Stripe restricted key
    r"AKIA[A-Z0-9]{16}",                 # AWS Access Key ID
    r"fal_[A-Za-z0-9_-]{10,}",           # Fal.ai
    r"SG\.[A-Za-z0-9_-]{10,}",           # SendGrid API key
    r"tvly-[A-Za-z0-9]{10,}",            # Tavily search API key
]

# ── 编译前缀正则 ──
_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(" + "|".join(_PREFIX_PATTERNS) + r")(?![A-Za-z0-9_-])"
)

# ── 敏感值模式（正则列表） ──
SENSITIVE_PATTERNS = [
    # Bearer token
    re.compile(r"Bearer\s+[a-zA-Z0-9._-]{20,}"),
    # 通用长 token（40+ 字符 base64）
    re.compile(r"[a-zA-Z0-9_-]{40,}"),
]

# ── 环境变量赋值：XXX_API_KEY=sk-xxx ──
_SECRET_ENV_NAMES = r"(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)"
_ENV_ASSIGN_RE = re.compile(
    rf"([A-Z0-9_]{{0,50}}{_SECRET_ENV_NAMES}[A-Z0-9_]{{0,50}})\s*=\s*(['\"]?)(\S+)\2",
)

# ── JSON 敏感字段："apiKey": "sk-xxx" ──
_JSON_KEY_NAMES = r"(?:api_?[Kk]ey|token|secret|password|access_token|refresh_token|auth|bearer|private_key)"
_JSON_FIELD_RE = re.compile(
    rf'("{_JSON_KEY_NAMES}")\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)

# ── URL 用户信息（非 DB 协议）：https://user:password@host ──
_URL_USERINFO_RE = re.compile(
    r"(https?|wss?|ftp)://([^/\s:@]+):([^/\s@]+)@",
)

# ── Form-urlencoded body 检测（纯 k=v&k=v 无换行） ──
_FORM_BODY_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_.-]*=[^&\s]*(?:&[A-Za-z_][A-Za-z0-9_.-]*=[^&\s]*)+$"
)

# ── 私钥块 ──
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----"
)

# ── 数据库连接串 — 遮盖密码 ──
_DB_CONNSTR_RE = re.compile(
    r"((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:]+:)([^@]+)(@)",
    re.IGNORECASE,
)

# ── JWT token — eyJ 开头 ──
_JWT_RE = re.compile(
    r"eyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_=-]{4,}){0,2}"
)

# ── URL query 参数（?key=value&...） ──
_SENSITIVE_QUERY_PARAMS = frozenset({
    "access_token", "refresh_token", "id_token", "token",
    "api_key", "apikey", "api-key",
    "client_secret", "password", "secret",
    "auth", "jwt", "code", "signature",
    "key", "private_key",
})
_URL_WITH_QUERY_RE = re.compile(
    r"(https?|wss?)://([^\s/?#]+)([^\s?#]*)\?([^\s#]+)(#\S*)?",
)

# ── E.164 手机号 ──
_PHONE_RE = re.compile(r"(\+[1-9]\d{6,14})(?![A-Za-z0-9])")

# ── 遮盖占位符 ──
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


def _mask_secret(value: str, head: int = 4, tail: int = 4, floor: int = 12) -> str:
    """遮盖密钥，保留首尾字符（类似 mask_secret）

    Args:
        value: 原始密钥字符串
        head: 开头保留字符数（默认 4）
        tail: 结尾保留字符数（默认 4）
        floor: 短于此值则完全遮盖（默认 12）

    Returns:
        遮盖后的字符串，短值返回 REDACTED_PLACEHOLDER
    """
    if not value:
        return ""
    if len(value) < floor:
        return REDACTED_PLACEHOLDER
    return f"{value[:head]}...{value[-tail:]}"


def _redact_url_query(text: str) -> str:
    """遮盖 URL query 中的敏感参数值"""
    def _sub(m: re.Match) -> str:
        scheme, authority, path, query = m.group(1), m.group(2), m.group(3), m.group(4)
        fragment = m.group(5) or ""
        # 逐个参数检查
        parts = []
        for pair in query.split("&"):
            if "=" not in pair:
                parts.append(pair)
                continue
            key, _, val = pair.partition("=")
            if key.lower() in _SENSITIVE_QUERY_PARAMS:
                parts.append(f"{key}=***")
            else:
                parts.append(pair)
        return f"{scheme}://{authority}{path}?{'&'.join(parts)}{fragment}"
    return _URL_WITH_QUERY_RE.sub(_sub, text)


def _redact_url_userinfo(text: str) -> str:
    """遮盖非 DB URL 中的 user:password@ 部分"""
    return _URL_USERINFO_RE.sub(
        lambda m: f"{m.group(1)}://{m.group(2)}:***@",
        text,
    )


def _redact_form_body(text: str) -> str:
    """遮盖 form-urlencoded body 中的敏感参数值

    只在纯 k=v&k=v 格式且无换行时触发
    """
    if not text or "\n" in text or "&" not in text:
        return text
    stripped = text.strip()
    if not _FORM_BODY_RE.match(stripped):
        return text
    parts = []
    for pair in stripped.split("&"):
        if "=" not in pair:
            parts.append(pair)
            continue
        key, _, val = pair.partition("=")
        if key.lower() in _SENSITIVE_QUERY_PARAMS:
            parts.append(f"{key}=***")
        else:
            parts.append(pair)
    return "&".join(parts)


def _redact_phone(text: str) -> str:
    """遮盖 E.164 手机号"""
    def _sub(m: re.Match) -> str:
        phone = m.group(1)
        if len(phone) <= 8:
            return phone[:2] + "****" + phone[-2:]
        return phone[:4] + "****" + phone[-4:]
    return _PHONE_RE.sub(_sub, text)


def _redact_string(text: str, code_file: bool = False) -> str:
    """对字符串中的敏感模式进行遮盖

    Args:
        text: 原始字符串
        code_file: 为 True 时跳过 JSON/env 正则（防源码误报）
    """
    # 已知前缀
    text = _PREFIX_RE.sub(lambda m: _redact_value(m.group(0)), text)

    # Bearer / 通用长 token
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub(lambda m: _redact_value(m.group(0)), text)

    # 环境变量赋值（源码模式跳过）
    if not code_file:
        def _redact_env(m):
            name, quote, value = m.group(1), m.group(2), m.group(3)
            return f"{name}={quote}{_redact_value(value)}{quote}"
        text = _ENV_ASSIGN_RE.sub(_redact_env, text)

    # JSON 敏感字段（源码模式跳过）
    if not code_file:
        def _redact_json(m):
            key, value = m.group(1), m.group(2)
            return f'{key}: "{_redact_value(value)}"'
        text = _JSON_FIELD_RE.sub(_redact_json, text)

    # 私钥块
    text = _PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", text)

    # 数据库连接串密码
    text = _DB_CONNSTR_RE.sub(lambda m: f"{m.group(1)}***{m.group(3)}", text)

    # JWT token
    text = _JWT_RE.sub(lambda m: _redact_value(m.group(0)), text)

    # URL query 参数
    text = _redact_url_query(text)

    # E.164 手机号
    text = _redact_phone(text)

    # URL userinfo（非 DB 协议）
    text = _redact_url_userinfo(text)

    # Form-urlencoded body
    text = _redact_form_body(text)

    return text


def redact(obj: Any, depth: int = 0, max_depth: int = 20,
           *, force: bool = False, code_file: bool = False) -> Any:
    """递归遮盖对象中的敏感信息

    支持 dict / list / str / 基本类型。
    字典按 key 名匹配敏感字段；字符串按正则匹配敏感模式。

    Args:
        obj: 要遮盖的对象
        depth: 当前递归深度（内部使用）
        max_depth: 最大递归深度，防止无限递归
        force: 为 True 时忽略 ZUOSHANKE_REDACT_SECRETS 开关，强制遮盖
        code_file: 为 True 时跳过 env/JSON 正则（防源码误报）

    Returns:
        遮盖后的对象副本（不修改原始对象）
    """
    # 检查开关（force 跳过）
    if not force and not _REDACT_ENABLED:
        return obj

    if depth > max_depth:
        return obj

    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if _is_sensitive_key(k) and isinstance(v, (str, bytes)):
                result[k] = _redact_value(str(v))
            elif isinstance(v, str):
                result[k] = _redact_string(v, code_file=code_file)
            else:
                result[k] = redact(v, depth + 1, max_depth,
                                   force=force, code_file=code_file)
        return result

    elif isinstance(obj, list):
        return [redact(item, depth + 1, max_depth,
                       force=force, code_file=code_file) for item in obj]

    elif isinstance(obj, str):
        return _redact_string(obj, code_file=code_file)

    return obj


def redact_text(text: str, *, force: bool = False, code_file: bool = False) -> str:
    """直接遮盖纯文本字符串（外部便利入口）

    Args:
        text: 原始文本
        force: 强制遮盖（忽略开关）
        code_file: 源码模式（跳过 env/JSON 正则）

    Returns:
        遮盖后的文本
    """
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text
    if not (force or _REDACT_ENABLED):
        return text
    return _redact_string(text, code_file=code_file)


class SecretRedactFilter(logging.Filter):
    """日志过滤器 — 自动遮盖日志消息中的敏感信息

    用法:
        handler.addFilter(SecretRedactFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not _REDACT_ENABLED:
            return True

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


class RedactingFormatter(logging.Formatter):
    """日志格式器 — 在最终格式化字符串上做遮盖（双保险）

    Filter 在格式化前修改 record.msg，Formatter 在格式化后修改最终字符串。
    两者同时使用，覆盖 Filter 可能的遗漏路径。

    用法:
        handler.setFormatter(RedactingFormatter(fmt="%(asctime)s %(message)s"))
    """

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return _redact_string(original)


def redact_headers(headers: dict) -> dict:
    """专门遮盖 HTTP 请求头中的 Authorization

    Args:
        headers: 请求头字典

    Returns:
        遮盖后的请求头副本
    """
    if not _REDACT_ENABLED:
        return dict(headers)

    result = dict(headers)
    for key in result:
        if key.lower() in ("authorization", "x-api-key", "api-key"):
            val = str(result[key])
            if len(val) > 10:
                result[key] = val[:8] + REDACTED_PLACEHOLDER
            else:
                result[key] = REDACTED_PLACEHOLDER
    return result
