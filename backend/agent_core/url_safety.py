"""URL 安全检测 — SSRF 防护

DNS 解析后检查目标 IP，阻断私有 IP、回环地址、链路本地地址
以及云元数据端点。所有解析/网络错误均视为"不安全"（fail-closed）。

设计参考: Hermes tools/url_safety.py (327 LOC)
"""

import ipaddress
import logging
import os
import socket
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────

# CGNAT 网段 (100.64.0.0/10) — ipaddress.is_private 不包括此范围
_CGNAT_NETWORK = ipaddress.IPv4Network("100.64.0.0/10")

# 始终阻断的云元数据端点（即使 allow_private_urls=true）
_BLOCKED_HOSTNAMES: frozenset = frozenset({
    "metadata.google.internal",
    "metadata.goog",
})

# 始终阻断的 IP / 网段
_METADATA_SENTINELS: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [
    ipaddress.IPv4Address("169.254.169.254"),   # AWS / GCP / Azure IMDS
    ipaddress.IPv4Address("169.254.170.2"),     # AWS ECS 任务元数据
    ipaddress.IPv4Address("169.254.169.253"),   # Azure IMDS（旧）
    ipaddress.IPv4Address("100.100.100.200"),   # 阿里云元数据
    ipaddress.IPv6Address("fd00:ec2::254"),     # AWS IMDS IPv6
]
_METADATA_SENTINEL_IPS: frozenset = frozenset(_METADATA_SENTINELS)

_ALWAYS_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.IPv4Network("169.254.0.0/16"),        # 链路本地 + 元数据服务
    ipaddress.IPv4Network("100.100.100.200/32"),     # 阿里云元数据
]

# 缓存是否允许私有 URL（进程生命周期一次读取）
_ALLOW_PRIVATE_URLS_CACHED: Optional[bool] = None


def _reset_allow_private_cache() -> None:
    """重置私有 URL 允许缓存（测试隔离用）"""
    global _ALLOW_PRIVATE_URLS_CACHED
    _ALLOW_PRIVATE_URLS_CACHED = None


def _global_allow_private_urls() -> bool:
    """检查全局是否允许访问私有 URL（环境变量控制）

    默认不启用。结果缓存在模块级变量中，避免每次调用读 env。
    可通过 _reset_allow_private_cache() 清除缓存。
    """
    global _ALLOW_PRIVATE_URLS_CACHED
    if _ALLOW_PRIVATE_URLS_CACHED is None:
        val = os.getenv("ZUOSHANKE_ALLOW_PRIVATE_URLS", "false").lower()
        _ALLOW_PRIVATE_URLS_CACHED = val in ("1", "true", "yes", "on")
    return _ALLOW_PRIVATE_URLS_CACHED


# ── URL 解析 ──────────────────────────────────────────────────


def _parse_and_validate(url: str) -> Optional[str]:
    """解析 URL 并返回 hostname（小写，去 trailing dot）。

    Returns:
        str: hostname 或 None（无效 URL）
    """
    if not url or not isinstance(url, str):
        return None
    if not url.startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return None
        # 去 trailing dot（FQDN 表示法）：metadata.google.internal. → metadata.google.internal
        hostname = hostname.rstrip(".").lower()
        return hostname
    except Exception:
        return None


def _resolve_hostname(hostname: str) -> list[str]:
    """DNS 解析 hostname 返回 IP 列表。解析失败返回空列表。"""
    try:
        addrs = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = set()
        for addr in addrs:
            ip = addr[4][0]
            ips.add(ip)
        return list(ips)
    except (socket.gaierror, OSError) as e:
        logger.debug("DNS 解析失败 %s: %s", hostname, e)
        return []


# ── IP 检测 ───────────────────────────────────────────────────


def _is_blocked_ip(ip_str: str) -> bool:
    """检查单个 IP 是否为被阻断的地址。"""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # 无法解析的 IP 形式 → 阻断

    # 始终阻断的网段
    for net in _ALWAYS_BLOCKED_NETWORKS:
        if addr in net:
            return True

    if addr.is_loopback:
        return True
    if addr.is_private:
        return True
    if addr.is_link_local:
        return True
    if addr.is_reserved:
        return True
    if addr.is_multicast:
        return True
    if addr.is_unspecified:
        return True
    # CGNAT (100.64.0.0/10) — ipaddress 不认为是 is_private
    if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT_NETWORK:
        return True

    return False


def _is_always_blocked_ip(ip_str: str) -> bool:
    """检查 IP 是否为始终阻断的云元数据端点（比 _is_blocked_ip 更窄）。"""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False  # 无法解析的不是"始终阻断"

    if addr in _METADATA_SENTINEL_IPS:
        return True
    for net in _ALWAYS_BLOCKED_NETWORKS:
        if addr in net:
            return True
    return False


# ── 公开函数 ──────────────────────────────────────────────────


def is_always_blocked_url(url: str) -> bool:
    """检查 URL 是否指向始终阻断的云元数据端点。

    比 is_safe_url 窄——只检查云元数据 sentinels，
    不检查私有 IP。供需要绕过私有 IP 检查但必须保住元数据底线的场景使用。
    """
    try:
        hostname = _parse_and_validate(url)
        if not hostname:
            return False

        # 1. 检查主机名
        if hostname in _BLOCKED_HOSTNAMES:
            return True

        # 2. 检查是否是 IP 字面量
        try:
            addr = ipaddress.ip_address(hostname)
            if _is_always_blocked_ip(str(addr)):
                return True
        except ValueError:
            pass

        # 3. DNS 解析后检查
        ips = _resolve_hostname(hostname)
        for ip_str in ips:
            if _is_always_blocked_ip(ip_str):
                return True

        return False
    except Exception:
        return False


def is_safe_url(url: str) -> bool:
    """检查 URL 的目标是否安全（非私有/非元数据/非回环）。

    Args:
        url: 要检查的 URL

    Returns:
        True: 安全，可以访问
        False: 不安全（私有 IP、元数据端点、回环地址、解析失败等）
    """
    try:
        # 1. 基本 URL 校验
        hostname = _parse_and_validate(url)
        if not hostname:
            logger.warning("SSRF 阻断: URL 无效: %s", url[:80])
            return False

        # 2. 始终阻断的主机名
        if hostname in _BLOCKED_HOSTNAMES:
            logger.warning("SSRF 阻断: 云元数据主机名: %s", hostname)
            return False

        # 3. 检查是否是 IP 字面量
        try:
            addr = ipaddress.ip_address(hostname)
            if _is_always_blocked_ip(str(addr)):
                logger.warning("SSRF 阻断: 元数据 IP: %s", hostname)
                return False
            if _is_blocked_ip(hostname):
                if _global_allow_private_urls():
                    logger.debug("SSRF 放行（配置允许私有）: %s", hostname)
                    return True
                logger.warning("SSRF 阻断: 私有 IP: %s", hostname)
                return False
            return True  # 公开 IP 直接通过
        except ValueError:
            pass  # 不是 IP 字面量，继续

        # 4. DNS 解析
        ips = _resolve_hostname(hostname)
        if not ips:
            logger.warning("SSRF 阻断: DNS 解析失败: %s", hostname)
            return False

        # 5. 检查每个解析到的 IP
        #    Hermes 策略：只要有一个 IP 是私有/阻断的，整请求阻断
        #    防止混合 DNS（一个域名同时解析到公网和私有 IP）
        allow_private = _global_allow_private_urls()
        for ip_str in ips:
            if _is_always_blocked_ip(ip_str):
                logger.warning("SSRF 阻断: 元数据 IP（DNS 解析）: %s → %s", hostname, ip_str)
                return False
            if not allow_private and _is_blocked_ip(ip_str):
                logger.warning(
                    "SSRF 阻断: 混合 DNS 解析含私有 IP: %s → %s", hostname, ip_str
                )
                return False

        return True

    except Exception as e:
        # 外层兜底：任何未预期的异常 → fail-closed 阻断
        logger.warning("SSRF 安全检测异常（已阻断）: %s", e)
        return False


# ── Exfiltration 检测 ─────────────────────────────────────────

# 从 Hermes prompt_builder 借鉴的威胁模式
_EXFIL_URL_PATTERNS: list[tuple[str, str]] = [
    # curl 携带环境变量外泄
    (r"curl\s+[^\n]*\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)[^}]*\}?", "exfil_curl"),
    # wget 携带 API Key
    (r"wget\s+[^\n]*\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_wget"),
    # cat 敏感文件后管道到网络（无需引号，匹配 .env 在命令中任意位置）
    (r"cat\s+[^\n]*(?:\.env|credentials|\.netrc|\.pgpass)", "read_secrets"),
    # base64 编码后管道
    (r"base64\s+.*(?:\.env|credentials|\.netrc)", "exfil_base64"),
    # nc/ncat 反向 shell
    (r"\b(?:nc|ncat)\s+(?:-e|--exec)", "exfil_netcat"),
    # 管道到外部地址
    (r"(?:\.env|credentials|auth\.json)\s*\|(?!\s*grep)", "exfil_pipe"),
    # 通过 --data 发送文件
    (r"(?:curl|wget)\s+.*--data(?:-binary)?\s*[@\"]?.*(?:\.env|credentials)", "exfil_sendfile"),
]


def check_exfiltration(command: str) -> Optional[str]:
    """检查 shell 命令是否包含凭据外泄模式。

    Args:
        command: 要检查的 shell 命令字符串

    Returns:
        None: 未检测到外泄
        str: 检测到的外泄类别（如 "exfil_curl", "read_secrets"）
    """
    if not command or not isinstance(command, str):
        return None
    for pattern, category in _EXFIL_URL_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return category
    return None


def check_ssrf_command(command: str) -> Optional[str]:
    """检查 shell 命令是否包含 SSRF curl/wget 到私有地址。

    Args:
        command: 要检查的 shell 命令字符串

    Returns:
        None: 未检测到 SSRF 目标
        str: "metadata"（元数据端点）或 "private"（私有地址）
    """
    if not command or not isinstance(command, str):
        return None

    url_patterns = re.findall(
        r'(?:curl|wget|fetch)\s+(?:-[^\s]+\s+)*["\']?(https?://[^\s"\'&|;]+)',
        command, re.IGNORECASE
    )
    if not url_patterns:
        return None

    for url in url_patterns:
        url = url.strip("'\"")
        if is_always_blocked_url(url):
            return "metadata"
        if not is_safe_url(url):
            return "private"
    return None
