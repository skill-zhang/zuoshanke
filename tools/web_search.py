"""web_search — 多提供商网络搜索工具（SearXNG → DuckDuckGo → Google 自动降级）

## 架构
1. 主：SearXNG（本地实例，http://localhost:4000）
2. 备选：DuckDuckGo Instant Answer API（免费，无需 key）
3. 兜底：Google Custom Search API（需 GOOGLE_API_KEY + GOOGLE_CSE_ID）

## 使用示例
    from web_search import web_search
    results = web_search("天津天气")
    # → [{"title": "...", "url": "...", "snippet": "...", "source": "searxng"}, ...]
"""

import json
import os
from typing import Optional

import requests

# ── 提供商配置（环境变量可覆盖） ──
SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "http://localhost:9999")
BING_SEARCH_URL = "https://cn.bing.com/search"
DUCKDUCKGO_API_URL = "https://api.duckduckgo.com/"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")

REQUEST_TIMEOUT = 10  # 超时 10 秒（Google、DuckDuckGo）
SEARXNG_TIMEOUT = 5   # SearXNG 超时 5 秒（本地优先，但已不可用时不拖慢）

# ── 内部搜索函数（每个提供商） ──


def _search_searxng(query: str, max_results: int) -> list[dict]:
    """通过 SearXNG 搜索（主提供商）"""
    url = f"{SEARXNG_BASE_URL.rstrip('/')}/search"
    params = {"q": query, "format": "json", "language": "zh-CN"}
    try:
        resp = requests.get(url, params=params, timeout=SEARXNG_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "source": "searxng",
            })
        return _deduplicate(results, max_results)
    except requests.RequestException as e:
        raise RuntimeError(f"SearXNG 不可用: {e}")
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"SearXNG 响应解析失败: {e}")


def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    """通过 DuckDuckGo HTML 搜索（备选，免费无需 key）

    用 https://html.duckduckgo.com/html/ POST 接口获取真实搜索结果。
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.post(url, data={"q": query}, headers=headers,
                             timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        # HTML 解析提取搜索结果
        import re
        results = []
        # 匹配 <a rel="nofollow" class="result__a" href="...">标题</a>
        # 和紧跟的 <a class="result__snippet" ...>摘要</a>
        # 使用简单的正则/字符串解析
        html = resp.text

        # 查找所有 result 块
        for block in re.finditer(
            r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        ):
            url_raw = block.group(1)
            title = re.sub(r'<[^>]+>', '', block.group(2)).strip()

            # 找到对应的 snippet
            snippet_start = block.end()
            snippet_match = re.search(
                r'<a class="result__snippet"[^>]*>(.*?)</a>',
                html[snippet_start:snippet_start + 500], re.DOTALL
            )
            snippet = ""
            if snippet_match:
                snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()

            results.append({
                "title": title or url_raw,
                "url": url_raw,
                "snippet": snippet,
                "source": "duckduckgo",
            })

            if len(results) >= max_results:
                break

        if not results:
            raise RuntimeError("DuckDuckGo 未返回任何搜索结果")

        return _deduplicate(results, max_results)
    except requests.RequestException as e:
        raise RuntimeError(f"DuckDuckGo 不可用: {e}")
    except Exception as e:
        raise RuntimeError(f"DuckDuckGo 响应解析失败: {e}")


def _search_google(query: str, max_results: int) -> list[dict]:
    """通过 Google Custom Search API 搜索（兜底，需 GOOGLE_API_KEY + GOOGLE_CSE_ID）"""
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        raise RuntimeError(
            "Google 搜索未配置：请设置环境变量 GOOGLE_API_KEY 和 GOOGLE_CSE_ID"
        )
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "google",
            })
        return _deduplicate(results, max_results)
    except requests.RequestException as e:
        raise RuntimeError(f"Google 搜索不可用: {e}")
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"Google 响应解析失败: {e}")


def _search_bing(query: str, max_results: int) -> list[dict]:
    """通过 Bing HTML 搜索（中国可访问，无需 API key）"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    params = {"q": query, "count": max_results}
    try:
        resp = requests.get(BING_SEARCH_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        html = resp.text

        results = []
        # 使用正则从 Bing HTML 提取搜索结果
        import re as _re
        # Bing 结果格式: <li class="b_algo"><h2><a href="URL">标题</a></h2><p>摘要</p></li>
        pattern = _re.compile(
            r'<h2[^>]*><a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>.*?<p[^>]*>(.*?)</p>',
            _re.DOTALL,
        )
        for m in pattern.finditer(html):
            url = m.group(1)
            title = _re.sub(r'<[^>]+>', '', m.group(2)).strip()
            snippet = _re.sub(r'<[^>]+>', '', m.group(3)).strip()
            if title and url:
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet[:200],
                    "source": "bing",
                })
            if len(results) >= max_results:
                break

        return _deduplicate(results, max_results) if results else results
    except requests.RequestException as e:
        raise RuntimeError(f"Bing 搜索不可用: {e}")
    except Exception as e:
        raise RuntimeError(f"Bing 响应解析失败: {e}")


# ── 工具函数 ──


def _deduplicate(results: list[dict], max_results: int) -> list[dict]:
    """按 URL 去重（保留首次出现的条目）"""
    seen = set()
    deduped = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(r)
        elif not url:
            # 无 URL 的结果直接跳过（无法去重）
            continue
    return deduped[:max_results]


# ── 公开接口 ──


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """多提供商网络搜索，按优先级自动降级。

    搜索链：SearXNG（主）→ DuckDuckGo（备选）→ Google（兜底）
    当前一个提供商失败或无结果时，自动尝试下一个。

    Args:
        query: 搜索关键词
        max_results: 最大返回结果数（默认 5）

    Returns:
        list[dict]: 搜索结果列表，每条含 {title, url, snippet, source}

    Raises:
        ValueError: query 为空或无效
        RuntimeError: 所有提供商均失败
    """
    if not query or not query.strip():
        raise ValueError("搜索关键词不能为空")

    # ── 提供商搜索链 ──
    providers = [
        ("Bing", _search_bing),        # Bing 优先（中国可访问，稳定）
        ("SearXNG", _search_searxng),  # SearXNG 本地实例（更快但不一定可用）
        ("DuckDuckGo", _search_duckduckgo),
        ("Google", _search_google),
    ]

    last_error = None
    for name, search_func in providers:
        try:
            results = search_func(query, max_results)
            if results:
                return results
        except RuntimeError as e:
            last_error = e
            continue

    raise RuntimeError(
        f"所有搜索提供商均失败，无法完成搜索。"
        f"最后错误: {last_error}"
    )


# ── 独立运行测试 ──
if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "天津亲子景点"
    print(f"🔍 搜索: {query}")
    try:
        results = web_search(query)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\n✅ 共返回 {len(results)} 条结果")
    except Exception as e:
        print(f"❌ 搜索失败: {e}")
