"""📚 百科查询 — 知识问答（基于本地 Qwen LLM + 维基百科回退）

优先使用本地 Qwen LLM 回答百科类问题（不依赖网络），
当网络可达时自动补充维基百科的结构化信息。

## 用法
    from tools.baike import baike
    r = json.loads(baike("人工智能"))
    r = json.loads(baike("Python", lang="en"))
"""

import json
import traceback
import urllib.request
import urllib.parse
import urllib.error

# ── Qwen LLM API ──
LLM_URL = "http://localhost:8083/v1/chat/completions"

# ── 维基百科 API（回退/补充用） ──
WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
USER_AGENT = "Zuoshanke/1.0 Baike"

TIMEOUT = 15


def _call_llm(query: str, lang: str) -> dict:
    """调用本地 Qwen LLM 生成百科条目"""

    lang_prompt = {
        "zh": "你是一个知识渊博的百科全书。请用中文回答以下查询，提供准确、客观、结构化的知识信息。\n",
        "en": "You are a knowledgeable encyclopedia. Answer the following query in English with accurate, objective, structured information.\n",
        "ja": "あなたは知識豊富な百科事典です。以下の質問に日本語で正確で客観的な情報を提供してください。\n",
    }.get(lang, "")

    system_prompt = lang_prompt + (
        "请按以下 JSON 格式输出（不要 markdown，只输出纯 JSON）：\n"
        "{\n"
        '  "title": "条目标题",\n'
        '  "summary": "详细摘要（300-500字，分段落、全面覆盖）",\n'
        '  "categories": ["分类1", "分类2", "分类3"],\n'
        '  "sections": ["基本概念", "发展历史", "主要应用", "相关领域"],\n'
        '  "related": ["相关条目1", "相关条目2", "相关条目3"]\n'
        "}\n"
        "要求：\n"
        "1. 如果不知道或不确定，title 返回 '未知' 并在 summary 中说明\n"
        "2. 摘要要全面、准确、客观\n"
        "3. 分类、章节、相关条目要合理\n"
        "4. 只输出 JSON，不要任何额外文字"
    )

    payload = json.dumps({
        "model": "Qwen3.5-9B-Q4_K_M.gguf",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }).encode("utf-8")

    req = urllib.request.Request(
        LLM_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    text = data["choices"][0]["message"]["content"].strip()

    # 解析 JSON
    import re
    # 尝试从 markdown 代码块提取
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if json_match:
        text = json_match.group(1)
    else:
        # 直接尝试从花括号提取
        brace_match = re.search(r'\{[\s\S]*\}', text)
        if brace_match:
            text = brace_match.group()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 如果 LLM 返回非 JSON，直接当摘要用
        return {"title": query, "summary": text, "categories": [], "sections": [], "related": []}


def baike(query: str, lang: str = "zh", summary_only: bool = False) -> str:
    """百科知识查询，返回 JSON 字符串

    Args:
        query:         搜索关键词（必填）
        lang:          语言，zh(中文)/en(英文)/ja(日文)，默认 zh
        summary_only:  是否仅返回摘要（更快），默认 false

    Returns:
        JSON string:
        {
            "success": true/false,
            "title": "条目标题",
            "summary": "详细摘要",
            "categories": [...],
            "sections": [...],
            "related": [...],
            "url": "百科页面URL(如有)",
            "source": "llm" or "wikipedia",
            "error": "..."
        }
    """
    try:
        if not query or not query.strip():
            return json.dumps({"success": False, "error": "搜索关键词不能为空"}, ensure_ascii=False)

        query = query.strip()
        if len(query) > 200:
            query = query[:200]

        if lang not in ("zh", "en", "ja"):
            lang = "zh"

        # 先尝试维基百科（仅当网络可达）
        wiki_success = False
        wiki_data = None

        try:
            wiki_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 1,
                "srprop": "",
                "format": "json",
                "origin": "*",
            }
            wiki_url = f"{WIKI_API.format(lang=lang)}?{urllib.parse.urlencode(wiki_params)}"
            wiki_req = urllib.request.Request(wiki_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(wiki_req, timeout=8) as resp:
                content = resp.read()
                search_result = json.loads(content.decode("utf-8", errors="replace"))

            search_items = search_result.get("query", {}).get("search", [])
            if search_items:
                page_title = search_items[0]["title"]

                # 获取摘要
                extract_params = {
                    "action": "query",
                    "titles": page_title,
                    "prop": "extracts",
                    "exintro": True,
                    "explaintext": True,
                    "exchars": 500 if summary_only else 1000,
                    "redirects": 1,
                    "format": "json",
                    "origin": "*",
                }
                extract_url = f"{WIKI_API.format(lang=lang)}?{urllib.parse.urlencode(extract_params)}"
                extract_req = urllib.request.Request(extract_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(extract_req, timeout=8) as resp2:
                    content2 = resp2.read()
                    extract_result = json.loads(content2.decode("utf-8", errors="replace"))

                pages = extract_result.get("query", {}).get("pages", {})
                page_id = list(pages.keys())[0] if pages else "-1"
                if page_id != "-1":
                    page_data = pages[page_id]
                    summary = page_data.get("extract", "") or "（暂无摘要）"
                    resolved_title = page_data.get("title", page_title)
                    encoded_title = urllib.parse.quote(resolved_title.replace(" ", "_"))
                    wiki_url_out = f"https://{lang}.wikipedia.org/wiki/{encoded_title}"

                    wiki_data = {
                        "title": resolved_title,
                        "summary": summary.strip(),
                        "url": wiki_url_out,
                        "lang": lang,
                        "source": "wikipedia",
                    }

                    if not summary_only:
                        # 分类
                        try:
                            cat_params = {"action": "query", "titles": resolved_title, "prop": "categories", "cllimit": 8, "format": "json", "origin": "*"}
                            cat_url = f"{WIKI_API.format(lang=lang)}?{urllib.parse.urlencode(cat_params)}"
                            cat_req = urllib.request.Request(cat_url, headers={"User-Agent": USER_AGENT})
                            with urllib.request.urlopen(cat_req, timeout=5) as resp3:
                                cat_result = json.loads(resp3.read().decode("utf-8", errors="replace"))
                            cat_pages = cat_result.get("query", {}).get("pages", {})
                            cat_data = cat_pages.get(page_id, {}) if page_id in cat_pages else {}
                            categories = []
                            for cat in cat_data.get("categories", []):
                                ct = cat.get("title", "")
                                if ct and "隐藏" not in ct and "维基" not in ct:
                                    categories.append(ct.split(":")[-1] if ":" in ct else ct)
                            wiki_data["categories"] = categories[:8]
                        except Exception:
                            wiki_data["categories"] = []

                    wiki_success = True

        except Exception:
            pass  # 维基不可达，回退 LLM

        if wiki_success and wiki_data:
            result = {"success": True, **wiki_data}
            return json.dumps(result, ensure_ascii=False)

        # 回退：本地 LLM
        llm_data = _call_llm(query, lang)
        if llm_data.get("title") == "未知":
            return json.dumps({
                "success": False,
                "error": f"未找到「{query}」的相关信息",
                "query": query,
                "lang": lang,
            }, ensure_ascii=False)

        result = {
            "success": True,
            "title": llm_data.get("title", query),
            "summary": llm_data.get("summary", ""),
            "categories": llm_data.get("categories", []),
            "sections": llm_data.get("sections", []),
            "related": [{"title": r} for r in llm_data.get("related", [])],
            "source": "llm",
        }

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"百科查询失败: {str(e)}",
            "detail": traceback.format_exc(),
        }, ensure_ascii=False)
