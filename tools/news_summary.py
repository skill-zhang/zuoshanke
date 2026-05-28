"""📰 新闻摘要 — 抓取主流中文新闻源，生成结构化每日简报

内置国内主流新闻 RSS 源（澎湃新闻、36氪、cnBeta、Solidot 等），
调用本地 Qwen LLM 做智能摘要，输出分类排版好的每日简报。

## 用法
    from tools.news_summary import news_summary
    r = json.loads(news_summary())
    r = json.loads(news_summary(category="tech", max_items=10))
"""

import json
import traceback
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import time

# ── Qwen LLM API ──
LLM_URL = "http://localhost:8083/v1/chat/completions"

# ── 预置新闻源 ──
# 按分类组织，确保可靠性
NEWS_FEEDS = {
    "headline": [
        {"name": "IT之家 - 综合", "url": "https://www.ithome.com/rss/", "lang": "zh-CN"},
        {"name": "知乎 - 每日精选", "url": "https://www.zhihu.com/rss", "lang": "zh-CN"},
    ],
    "tech": [
        {"name": "36氪 - 快讯", "url": "https://36kr.com/feed", "lang": "zh-CN"},
        {"name": "Solidot", "url": "https://www.solidot.org/index.rss", "lang": "zh-CN"},
    ],
    "life": [
        {"name": "少数派 - 效率生活", "url": "https://sspai.com/feed", "lang": "zh-CN"},
    ],
}

# 分类说明
CATEGORY_LABELS = {
    "headline": "📰 要闻",
    "tech": "💻 科技",
    "life": "🌿 生活",
    "all": "📡 综合",
}

TIMEOUT = 20


def _fetch_rss(feed_url: str, max_items: int = 15) -> list[dict]:
    """抓取单个 RSS 源，返回条目列表"""
    try:
        req = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Zuoshanke/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()

        root = ET.fromstring(raw)
        items = []

        # RSS 2.0
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            if not title:
                continue
            items.append({
                "title": title,
                "link": link,
                "summary": desc[:300] if desc else "",
                "time": pub_date,
            })
            if len(items) >= max_items:
                break

        # Atom 1.0
        if not items:
            ns = "http://www.w3.org/2005/Atom"
            for entry in root.iter(f"{{{ns}}}entry"):
                title = entry.findtext(f"{{{ns}}}title", "").strip()
                link_elem = entry.find(f"{{{ns}}}link")
                link = link_elem.get("href", "") if link_elem is not None else ""
                desc = entry.findtext(f"{{{ns}}}summary", "") or entry.findtext(f"{{{ns}}}content", "")
                desc = desc.strip()[:300] if desc else ""
                pub = entry.findtext(f"{{{ns}}}published", "") or entry.findtext(f"{{{ns}}}updated", "")
                if not title:
                    continue
                items.append({
                    "title": title,
                    "link": link,
                    "summary": desc,
                    "time": pub.strip(),
                })
                if len(items) >= max_items:
                    break

        return items
    except Exception:
        return []


def _call_llm(system_prompt: str, user_text: str, max_tokens: int = 2048) -> str:
    """调用本地 Qwen LLM"""
    payload = json.dumps({
        "model": "Qwen3.5-9B-Q4_K_M.gguf",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        LLM_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def news_summary(category: str = "headline", max_items: int = 10) -> str:
    """获取新闻摘要，返回 JSON 字符串

    Args:
        category:  新闻分类。headline(要闻) / tech(科技) / life(生活) / all(综合)，默认 headline
        max_items: 每条源最多抓取条目数，默认 10

    Returns:
        JSON string:
        {
            "success": true/false,
            "category": "headline",
            "category_label": "📰 要闻",
            "sources": ["澎湃新闻 - 头条", ...],  // 成功抓取的源
            "items": [...],                      // 原始条目（标题+链接+摘要）
            "summary": "LLM 生成的摘要文本",      // LLM 智能摘要
            "fetched_at": "2025-01-01 12:00:00",
            "total_items": 15,
            "error": "错误信息"                   // 失败时
        }
    """
    try:
        if category not in NEWS_FEEDS and category != "all":
            category = "headline"

        # 选择要抓取的源
        if category == "all":
            feeds = []
            for cat_feeds in NEWS_FEEDS.values():
                feeds.extend(cat_feeds)
        else:
            feeds = NEWS_FEEDS[category]

        # 抓取所有 RSS 源
        all_items = []
        sources_ok = []
        sources_fail = []

        for feed in feeds:
            items = _fetch_rss(feed["url"], max_items)
            if items:
                all_items.extend(items)
                sources_ok.append(feed["name"])
            else:
                sources_fail.append(feed["name"])

        if not all_items:
            return json.dumps({
                "success": False,
                "category": category,
                "error": "所有新闻源均抓取失败，请稍后重试",
                "sources_ok": sources_ok,
                "sources_fail": sources_fail,
            }, ensure_ascii=False)

        # 去重（按标题）
        seen = set()
        unique_items = []
        for item in all_items:
            key = item["title"].strip()[:40]
            if key not in seen:
                seen.add(key)
                unique_items.append(item)

        # 截取最多 30 条
        top_items = unique_items[:30]

        # 用 LLM 生成摘要
        category_label = CATEGORY_LABELS.get(category, "综合")

        items_text = "\n".join(
            f"{i+1}. [{item['title']}] {item['summary'][:100]}"
            for i, item in enumerate(top_items)
        )

        llm_prompt = (
            "你是一个专业的新闻摘要助手。请基于以下原始新闻条目，生成一份结构清晰的每日简报。\n"
            f"分类：{category_label}\n"
            "要求：\n"
            "1. 将新闻按主题归类（3-5个类别）\n"
            "2. 每个类别下列出 1-3 条最重要的新闻\n"
            "3. 每条新闻写一句话的关键点\n"
            "4. 开头发一段简短的今日概览（1-2句）\n"
            "5. 语言简洁、客观\n"
            "6. 输出纯文本，不要 markdown 格式"
        )

        llm_summary = _call_llm(llm_prompt, items_text)

        # 构造返回
        fetched_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = {
            "success": True,
            "category": category,
            "category_label": category_label,
            "sources": sources_ok,
            "sources_failed": sources_fail,
            "summary": llm_summary,
            "items": top_items[:15],  # 原始条目给前 15 条
            "fetched_at": fetched_at,
            "total_items": len(top_items),
        }

        return json.dumps(result, ensure_ascii=False)

    except urllib.error.URLError as e:
        return json.dumps({
            "success": False,
            "error": f"网络连接失败: {e.reason}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"新闻摘要生成失败: {str(e)}",
            "detail": traceback.format_exc(),
        }, ensure_ascii=False)
