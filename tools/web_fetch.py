"""web_fetch — 抓取网页文本内容

抓取指定 URL 的网页，提取正文文本（去除 HTML 标签、脚本、样式）。
"""

import json
import logging
import re
from html import unescape
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener, install_opener
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── SSRF 重定向守卫 ──
# 阻止 urllib 自动跟随重定向到私有/元数据地址


class _SSRFSafeRedirectHandler(HTTPRedirectHandler):
    """自定义重定向处理器：跟随前重新检查目标 URL 安全性"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 在跟随重定向前检查目标 URL
        try:
            from agent_core.url_safety import is_safe_url
            if not is_safe_url(newurl):
                logger.warning("SSRF 重定向阻断: %s → %s", req.full_url, newurl)
                return None  # 返回 None = 不跟随，urllib 返回原始 3xx 响应
        except ImportError:
            pass
        except Exception as e:
            logger.warning("SSRF 重定向检测异常: %s", e)
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)

_opener = None


def _get_ssrf_safe_opener():
    """获取配置了 SSRF 重定向守卫的 opener（单例）"""
    global _opener
    if _opener is None:
        _opener = build_opener(_SSRFSafeRedirectHandler)
    return _opener

# 常见非正文标签
_SKIP_TAGS = re.compile(
    r'<(script|style|noscript|nav|footer|header|aside|iframe|svg|canvas|'
    r'form|select|option|button)[^>]*>.*?</\1>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_CLEAN = re.compile(r'<[^>]+>')
_WHITESPACE = re.compile(r'\s{2,}')
_ENTITY = re.compile(r'&[a-zA-Z]+;')


def _clean_html(html: str) -> str:
    """从 HTML 中提取纯文本正文"""
    # 去掉非正文标签
    text = _SKIP_TAGS.sub(' ', html)
    # 去掉所有 HTML 标签
    text = _TAG_CLEAN.sub(' ', text)
    # 解码 HTML 实体
    text = unescape(text)
    # 合并空白
    text = _WHITESPACE.sub(' ', text)
    return text.strip()


def web_fetch(url: str, max_chars: int = 3000) -> str:
    """抓取指定 URL 的网页文本内容

    Args:
        url: 网页 URL（http/https）
        max_chars: 返回文本最大字符数，默认 3000

    Returns:
        JSON 字符串 {success, url, title, text, length}
    """
    # 校验 URL
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return json.dumps({
            "success": False, "url": url,
            "error": f"不支持的协议: {parsed.scheme}，仅支持 http/https",
        }, ensure_ascii=False)

    # SSRF 安全检测（fail-closed：安全模块异常也阻断）
    try:
        from agent_core.url_safety import is_safe_url
        if not is_safe_url(url):
            hostname = parsed.hostname or url
            return json.dumps({
                "success": False, "url": url,
                "error": f"SSRF 阻断：目标地址不安全（私有IP/云元数据/回环地址）: {hostname}",
            }, ensure_ascii=False)
    except ImportError:
        logger.warning("SSRF 安全检查不可用：agent_core.url_safety 未导入，已跳过检查")
    except Exception as e:
        logger.warning("SSRF 安全检测异常: %s", e)
        return json.dumps({
            "success": False, "url": url,
            "error": f"安全检测异常，已阻断: {e}",
        }, ensure_ascii=False)

    try:
        opener = _get_ssrf_safe_opener()
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Zuoshanke/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with opener.open(req, timeout=10) as resp:
            # 只处理 HTML
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return json.dumps({
                    "success": False, "url": url,
                    "error": f"非 HTML 内容: {content_type[:80]}",
                }, ensure_ascii=False)

            raw = resp.read()
            # 尝试解码
            charset = "utf-8"
            for part in content_type.split(";"):
                if "charset" in part.lower():
                    charset = part.split("=")[-1].strip()
                    break
            try:
                html = raw.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                html = raw.decode("utf-8", errors="replace")

        text = _clean_html(html)
        if len(text) > max_chars:
            text = text[:max_chars] + "…"

        # 提取标题
        title = ""
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = _TAG_CLEAN.sub('', title_match.group(1)).strip()[:200]

        return json.dumps({
            "success": True,
            "url": url,
            "title": title,
            "text": text,
            "length": len(text),
        }, ensure_ascii=False)

    except HTTPError as e:
        return json.dumps({
            "success": False, "url": url,
            "error": f"HTTP {e.code}: {e.reason}",
        }, ensure_ascii=False)
    except URLError as e:
        return json.dumps({
            "success": False, "url": url,
            "error": f"请求失败: {e.reason}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False, "url": url,
            "error": str(e)[:200],
        }, ensure_ascii=False)
