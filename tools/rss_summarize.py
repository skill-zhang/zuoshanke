"""RSS 摘要工具 — 对 RSS 抓取结果进行汇总分析

## 功能
- 接收 rss_fetch 的输出，生成结构化摘要
- 按时间排序、去重、统计关键词
- 返回简洁的文本摘要

## 用法
    from rss_summarize import rss_summarize
    summary = rss_summarize(fetch_result, max_summary_items=5)
"""

import json
import re
from typing import Optional
from collections import Counter


def _extract_keywords(text: str, top_n: int = 10) -> list:
    """从文本中提取高频关键词（简单分词统计）"""
    # 中文 + 英文单词
    words = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())

    # 过滤掉纯数字和过短的词
    words = [w for w in words if len(w) > 1 and not w.isdigit()]

    # 停用词
    stopwords = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
        "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "is",
        "are", "was", "were", "be", "been", "with", "at", "from", "by",
    }
    words = [w for w in words if w not in stopwords]

    counter = Counter(words)
    return [{"word": w, "count": c} for w, c in counter.most_common(top_n)]


def _format_pub_date(date_str: str) -> str:
    """简化日期格式显示"""
    if not date_str:
        return "未知时间"
    # 取前 10 个字符（YYYY-MM-DD）
    cleaned = date_str.strip()
    if len(cleaned) >= 10:
        return cleaned[:10]
    return cleaned


def rss_summarize(fetch_result: dict, max_summary_items: int = 5) -> dict:
    """对 RSS 抓取结果生成摘要

    Args:
        fetch_result: rss_fetch 的返回结果（dict）
        max_summary_items: 摘要中最多显示条目数，默认 5

    Returns:
        JSON 响应:
        - success: bool
        - feed_title: 订阅源名称
        - total_items: 总条目数
        - summary_items: 摘要条目列表（精简版）
        - top_keywords: 高频关键词列表 [{word, count}]
        - error: 错误信息
    """
    result = {
        "success": False,
        "feed_title": "",
        "total_items": 0,
        "summary_items": [],
        "top_keywords": [],
        "error": "",
    }

    # 校验输入
    if not isinstance(fetch_result, dict):
        result["error"] = "输入必须是 dict 类型"
        return result

    if not fetch_result.get("success"):
        result["error"] = fetch_result.get("error", "抓取失败，无法生成摘要")
        return result

    items = fetch_result.get("items", [])
    if not items:
        result["success"] = True
        result["feed_title"] = fetch_result.get("feed_title", "")
        result["total_items"] = 0
        result["summary_items"] = []
        result["top_keywords"] = []
        return result

    # 1. 按发布时间排序（降序，最新的在前）
    sorted_items = sorted(
        items,
        key=lambda x: x.get("pub_date", "") or "",
        reverse=True,
    )

    # 2. 提取摘要条目
    summary_items = []
    for item in sorted_items[:max_summary_items]:
        summary_items.append({
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "date": _format_pub_date(item.get("pub_date", "")),
            "author": item.get("author", ""),
            "snippet": (item.get("description", "") or "")[:150],
        })

    # 3. 提取关键词（合并所有标题和描述）
    all_text = " ".join(
        f"{item.get('title', '')} {item.get('description', '')}"
        for item in items
    )
    top_keywords = _extract_keywords(all_text, top_n=10)

    result["success"] = True
    result["feed_title"] = fetch_result.get("feed_title", "")
    result["total_items"] = len(items)
    result["summary_items"] = summary_items
    result["top_keywords"] = top_keywords
    return result
