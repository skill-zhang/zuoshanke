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
import urllib.request
import urllib.error
import urllib.parse


def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
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

    method = method.upper()
    if method not in ("GET", "POST", "PUT", "DELETE"):
        result["error"] = f"不支持的 HTTP 方法: {method}，支持 GET/POST/PUT/DELETE"
        return result

    try:
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
        response = urllib.request.urlopen(req, timeout=timeout)
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
