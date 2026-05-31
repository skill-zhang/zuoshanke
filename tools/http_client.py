"""HTTP 请求工具 — 支持 GET/POST/PUT/DELETE，用 urllib 实现

工具名: http_request
功能: 发送 HTTP 请求到任意 URL
参数:
  - url (string, required) — 请求地址
  - method (string, optional, default: GET) — GET/POST/PUT/DELETE
  - headers (object, optional) — 自定义请求头
  - body (string, optional) — 请求体
  - timeout (integer, optional, default: 10) — 超时秒数
返回: {status_code, headers, body, success, error?}
"""

import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)


# ── SSRF 重定向守卫 ──


class _SSRFSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """自定义重定向处理器：跟随前重新检查目标 URL 安全性"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            from agent_core.url_safety import is_safe_url
            if not is_safe_url(newurl):
                logger.warning("SSRF 重定向阻断: %s → %s", req.full_url, newurl)
                return None
        except ImportError:
            pass
        except Exception as e:
            logger.warning("SSRF 重定向检测异常: %s", e)
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = None


def _get_ssrf_safe_opener():
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener(_SSRFSafeRedirectHandler)
    return _opener


def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    body: Optional[str] = None,
    timeout: int = 10,
) -> dict:
    """发送 HTTP 请求到任意 URL

    Args:
        url: 请求地址
        method: HTTP 方法 (GET/POST/PUT/DELETE)
        headers: 自定义请求头
        body: 请求体（GET/DELETE 时忽略）
        timeout: 超时秒数

    Returns:
        {status_code, headers, body, success, error?}
    """
    result = {
        "status_code": None,
        "headers": {},
        "body": "",
        "success": False,
    }

    if not url or not url.startswith(("http://", "https://")):
        result["error"] = "无效的 URL，必须以 http:// 或 https:// 开头"
        return result

    # SSRF 安全检测（fail-closed：安全模块异常也阻断）
    try:
        from agent_core.url_safety import is_safe_url, is_always_blocked_url
        if is_always_blocked_url(url):
            result["error"] = "SSRF 阻断：目标地址为云元数据服务，禁止访问"
            return result
        if not is_safe_url(url):
            parsed = urllib.parse.urlparse(url)
            hostname = parsed.hostname or url
            result["error"] = f"SSRF 阻断：目标地址不安全（私有IP/云元数据/回环地址）: {hostname}"
            return result
    except ImportError:
        logger.warning("SSRF 安全检查不可用：agent_core.url_safety 未导入，已跳过检查")
    except Exception as e:
        logger.warning("SSRF 安全检测异常: %s", e)
        result["error"] = f"安全检测异常，已阻断: {e}"
        return result

    method = method.upper()
    if method not in ("GET", "POST", "PUT", "DELETE"):
        result["error"] = f"不支持的 HTTP 方法: {method}，支持 GET/POST/PUT/DELETE"
        return result

    try:
        opener = _get_ssrf_safe_opener()
        req = urllib.request.Request(url, method=method)

        # 设置请求头
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)

        # 处理请求体
        if body and method in ("POST", "PUT"):
            data = body.encode("utf-8")
            req.data = data
            if headers is None or "Content-Type" not in {k.lower() for k in headers}:
                req.add_header("Content-Type", "application/octet-stream")

        # 发送请求
        response = opener.open(req, timeout=timeout)
        result["status_code"] = response.status
        result["headers"] = dict(response.headers)
        result["body"] = response.read().decode("utf-8", errors="replace")
        result["success"] = True

    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["headers"] = dict(e.headers)
        result["body"] = e.read().decode("utf-8", errors="replace")
        result["error"] = f"HTTP 错误: {e.code} {e.reason}"
        result["success"] = True  # 成功拿到了响应（虽然是错误状态码）

    except urllib.error.URLError as e:
        result["error"] = f"URL 错误: {e.reason}"

    except TimeoutError:
        result["error"] = f"请求超时（{timeout}秒）"

    except Exception as e:
        result["error"] = f"请求异常: {type(e).__name__}: {e}"

    return result
