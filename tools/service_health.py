"""服务健康检查工具 — 一键检查后端/前端/Qwen/SearXNG

工具名: check_services
功能: 一键检查后端(:8000)/前端(:5173)/Qwen(:8083)/SearXNG(:8081)
参数: 无
返回: [{name, port, status, response_time_ms}]
实现: 并发检查，总超时 10 秒
"""

import time
import urllib.request
import urllib.error
import concurrent.futures


SERVICES = [
    {"name": "后端", "port": 8000, "url": "http://localhost:8000/api/health"},
    {"name": "前端", "port": 5173, "url": "http://localhost:5173"},
    {"name": "Qwen", "port": 8083, "url": "http://localhost:8083/health"},
    {"name": "SearXNG", "port": 8081, "url": "http://localhost:8081"},
]

TOTAL_TIMEOUT = 10  # 总超时 10 秒


def _check_one(service: dict) -> dict:
    """检查单个服务"""
    name = service["name"]
    port = service["port"]
    url = service["url"]
    start = time.time()
    result = {
        "name": name,
        "port": port,
        "status": "down",
        "response_time_ms": None,
    }
    try:
        req = urllib.request.Request(url, method="GET")
        response = urllib.request.urlopen(req, timeout=TOTAL_TIMEOUT)
        elapsed = (time.time() - start) * 1000
        result["status_code"] = response.status
        result["status"] = "up" if response.status < 500 else "degraded"
        result["response_time_ms"] = round(elapsed, 1)
    except urllib.error.HTTPError as e:
        elapsed = (time.time() - start) * 1000
        result["status_code"] = e.code
        result["status"] = "degraded" if e.code < 500 else "down"
        result["response_time_ms"] = round(elapsed, 1)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        result["status"] = "down"
        result["error"] = str(e)
    except Exception as e:
        result["status"] = "down"
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def check_services() -> list[dict]:
    """一键检查所有服务状态

    Returns:
        [{name, port, status, response_time_ms, error?}]
    """
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(SERVICES)) as executor:
        future_to_service = {
            executor.submit(_check_one, svc): svc for svc in SERVICES
        }
        try:
            for future in concurrent.futures.as_completed(
                future_to_service, timeout=TOTAL_TIMEOUT
            ):
                try:
                    result = future.result()
                    results.append(result)
                except concurrent.futures.TimeoutError:
                    svc = future_to_service[future]
                    results.append({
                        "name": svc["name"],
                        "port": svc["port"],
                        "status": "timeout",
                        "response_time_ms": None,
                        "error": "超时",
                    })
                except Exception as e:
                    svc = future_to_service[future]
                    results.append({
                        "name": svc["name"],
                        "port": svc["port"],
                        "status": "error",
                        "response_time_ms": None,
                        "error": str(e),
                    })
        except concurrent.futures.TimeoutError:
            # as_completed 总超时 → 返回已收集的部分结果
            pass

    # 按端口排序返回
    results.sort(key=lambda x: x["port"])
    return results
