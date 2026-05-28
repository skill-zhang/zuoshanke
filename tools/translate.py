"""🌐 翻译工具 — 基于本地 Qwen LLM 的中英互译（免费，无需 API Key）

利用坐山客本地的 Qwen LLM 进行高质量翻译，支持自动检测源语言、
保留格式（HTML/JSON/代码不翻译结构）、双语对照输出。
不需要外部 API，不依赖网络连接。

## 用法
    from tools.translate import translate
    r = json.loads(translate("你好，世界"))
    r = json.loads(translate("Hello world", source="en", target="zh-CN"))
"""

import json
import re
import traceback
import urllib.request
import urllib.error

# ── Qwen LLM API ──
LLM_URL = "http://localhost:8083/v1/chat/completions"

# ── 语言名称映射 ──
LANG_NAMES = {
    "zh-CN": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "it": "意大利语",
    "th": "泰语",
    "vi": "越南语",
    "ar": "阿拉伯语",
}


def _lang_name(code: str) -> str:
    """语言代码转显示名称"""
    return LANG_NAMES.get(code, code)


def _call_llm(system_prompt: str, user_text: str, max_tokens: int = 1024) -> str:
    """调用本地 Qwen LLM，返回文本响应"""
    payload = json.dumps({
        "model": "Qwen3.5-9B-Q4_K_M.gguf",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        LLM_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data["choices"][0]["message"]["content"]
    return content.strip()


def translate(
    text: str,
    source: str = "auto",
    target: str = "en",
    format_mode: str = "normal",
) -> str:
    """翻译文本，返回 JSON 字符串

    Args:
        text:        要翻译的文本（必填）
        source:      源语言代码，默认 auto（自动检测）
        target:      目标语言代码，默认 en（英语）
        format_mode: 输出模式，normal=仅译文，dual=双语对照，examples=译文+例句

    支持的语言代码:
        zh-CN(中文), en(英语), ja(日语), ko(韩语), fr(法语),
        de(德语), es(西班牙语), ru(俄语), pt(葡萄牙语),
        it(意大利语), th(泰语), vi(越南语), ar(阿拉伯语)

    Returns:
        JSON string:
        {
            "success": true/false,
            "text": "翻译后的文本",
            "source_lang": "zh-CN",
            "source_label": "中文",
            "target_lang": "en",
            "target_label": "英语",
            "format": "normal",
            "detected": true,    // 是否自动检测了源语言
            "error": "错误信息"   // 失败时
        }
    """
    try:
        if not text or not text.strip():
            return json.dumps({"success": False, "error": "文本不能为空"}, ensure_ascii=False)

        if len(text) > 8000:
            text = text[:8000]

        # 生成本地语言名称
        target_name = _lang_name(target)
        is_auto = source == "auto"

        # 构建 system prompt
        if is_auto:
            system_prompt = (
                "你是一个专业翻译助手。请将用户输入的文本翻译为目标语言。\n"
                f"目标语言：{target_name}（语言代码 {target}）\n"
                "规则：\n"
                "1. 先自动检测源语言\n"
                "2. 只输出翻译结果，不要解释\n"
                "3. 如果原文包含代码（HTML/JSON/python等），保持代码结构不变，只翻译注释和字符串中的自然语言\n"
                "4. 保持原文的格式（换行、段落、列表等）\n"
                "5. 用语自然流畅，不要字对字直译\n"
                "6. 最开头的第一行必须是：DETECTED:<语言代码>\n"
                "7. 第二行开始是翻译结果"
            )
        else:
            source_name = _lang_name(source)
            system_prompt = (
                "你是一个专业翻译助手。请将用户输入的文本从源语言翻译为目标语言。\n"
                f"源语言：{source_name}（语言代码 {source}）\n"
                f"目标语言：{target_name}（语言代码 {target}）\n"
                "规则：\n"
                "1. 只输出翻译结果，不要解释\n"
                "2. 如果原文包含代码（HTML/JSON/python等），保持代码结构不变，只翻译注释和字符串中的自然语言\n"
                "3. 保持原文的格式（换行、段落、列表等）\n"
                "4. 用语自然流畅，不要字对字直译\n"
                "5. 最开头的第一行必须是：DETECTED:<源语言代码>\n"
                "6. 第二行开始是翻译结果"
            )

        if format_mode == "dual":
            system_prompt += (
                "\n\n输出格式要求：\n"
                "先输出『原文：』开头的一行，然后空一行，再输出『译文：』开头的翻译结果。"
            )
        elif format_mode == "examples":
            system_prompt += (
                "\n\n输出格式要求：\n"
                "先输出翻译结果，然后空一行，再输出两个『例句：』开头的典型用法例句。"
            )

        user_msg = text.strip()

        response_text = _call_llm(system_prompt, user_msg)

        # 解析检测到的语言
        detected_lang = source
        # 清理 DETECTED 标记（可能在任意位置）
        detected_matches = re.findall(r'^DETECTED:(\S+)', response_text, re.MULTILINE)
        if detected_matches:
            detected_lang = detected_matches[0]
        # 移除所有 DETECTED: 行
        translation_body = re.sub(r'^DETECTED:\S+\s*\n?', '', response_text, flags=re.MULTILINE).strip()

        result = {
            "success": True,
            "translation": translation_body,
            "source_lang": detected_lang,
            "source_label": _lang_name(detected_lang),
            "target_lang": target,
            "target_label": target_name,
            "format": format_mode,
            "detected": is_auto,
            "text_length": len(text),
        }

        return json.dumps(result, ensure_ascii=False)

    except urllib.error.URLError as e:
        return json.dumps({
            "success": False,
            "error": f"无法连接本地 LLM 服务: {e.reason}。请确认 Qwen 正在运行",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"翻译失败: {str(e)}",
            "detail": traceback.format_exc(),
        }, ensure_ascii=False)
