"""RSS 抓取工具 — 用 urllib + xml.etree 解析 RSS/Atom 源

## 功能
- 通过 urllib 请求 RSS/Atom 订阅源
- 用 xml.etree.ElementTree 解析 XML
- 支持 RSS 2.0 和 Atom 1.0 格式
- 返回结构化条目列表（标题、链接、发布时间、摘要）

## 用法
    from rss_fetch import rss_fetch
    items = rss_fetch("https://example.com/feed.xml", max_items=10)
"""

import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import time
from typing import Optional

TIMEOUT = 15  # 秒

# ── 命名空间 ──
ATOM_NS = "http://www.w3.org/2005/Atom"


def _parse_rss_item(item_elem) -> dict:
    """解析 RSS 2.0 的 <item> 元素"""
    def _get(tag: str, ns: str = "") -> str:
        elem = item_elem.find(f"{ns}{tag}")
        return elem.text.strip() if elem is not None and elem.text else ""

    return {
        "title": _get("title"),
        "link": _get("link"),
        "description": _get("description"),
        "pub_date": _get("pubDate"),
        "author": _get("author"),
        "guid": _get("guid"),
    }


def _parse_atom_entry(entry_elem) -> dict:
    """解析 Atom 1.0 的 <entry> 元素"""
    def _get(tag: str) -> str:
        elem = entry_elem.find(f"{{{ATOM_NS}}}{tag}")
        return elem.text.strip() if elem is not None and elem.text else ""

    # Atom 的 link 在 <link href="..." /> 属性中
    link = ""
    link_elem = entry_elem.find(f"{{{ATOM_NS}}}link")
    if link_elem is not None:
        link = link_elem.get("href", "")

    # Atom 的发布时间
    published = _get("published") or _get("updated")

    # Atom 的 author
    author = ""
    author_elem = entry_elem.find(f"{{{ATOM_NS}}}author/{{{ATOM_NS}}}name")
    if author_elem is not None and author_elem.text:
        author = author_elem.text.strip()

    return {
        "title": _get("title"),
        "link": link,
        "description": _get("summary") or _get("content"),
        "pub_date": published,
        "author": author,
        "guid": _get("id"),
    }


def rss_fetch(feed_url: str, max_items: int = 10) -> dict:
    """抓取并解析 RSS/Atom 订阅源

    Args:
        feed_url: RSS/Atom 订阅源 URL
        max_items: 最大返回条目数，默认 10

    Returns:
        JSON 响应:
        - success: bool
        - feed_title: 订阅源标题
        - feed_link: 订阅源链接
        - items: 条目列表 [{title, link, description, pub_date, author, guid}]
        - total: 总条目数
        - error: 错误信息（失败时）
    """
    result = {
        "success": False,
        "feed_title": "",
        "feed_link": "",
        "items": [],
        "total": 0,
        "error": "",
    }

    # 1. 请求 RSS 源
    req = urllib.request.Request(
        feed_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RSSMonitor/1.0)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}: {e.reason}"
        return result
    except urllib.error.URLError as e:
        result["error"] = f"URL 错误: {e.reason}"
        return result
    except Exception as e:
        result["error"] = f"请求失败: {str(e)}"
        return result

    # 2. 解析 XML
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        result["error"] = f"XML 解析失败: {str(e)}"
        return result

    # 3. 判断格式并提取
    # RSS 2.0: <rss><channel><item>...
    # Atom 1.0: <feed><entry>...
    is_atom = root.tag == f"{{{ATOM_NS}}}feed"

    try:
        if is_atom:
            # ── Atom 格式 ──
            title_elem = root.find(f"{{{ATOM_NS}}}title")
            result["feed_title"] = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

            link_elem = root.find(f"{{{ATOM_NS}}}link")
            result["feed_link"] = link_elem.get("href", "") if link_elem is not None else ""

            entries = root.findall(f"{{{ATOM_NS}}}entry")
            for entry in entries[:max_items]:
                result["items"].append(_parse_atom_entry(entry))

        else:
            # ── RSS 2.0 格式 ──
            channel = root.find("channel")
            if channel is None:
                result["error"] = "未找到 <channel> 元素，可能不是标准 RSS 格式"
                return result

            title_elem = channel.find("title")
            result["feed_title"] = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

            link_elem = channel.find("link")
            result["feed_link"] = link_elem.text.strip() if link_elem is not None and link_elem.text else ""

            items = channel.findall("item")
            for item in items[:max_items]:
                result["items"].append(_parse_rss_item(item))

    except Exception as e:
        result["error"] = f"解析失败: {str(e)}"
        return result

    result["success"] = True
    result["total"] = len(result["items"])
    return result
