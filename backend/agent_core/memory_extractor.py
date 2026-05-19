"""memory_extractor — 会话结束后异步提取记忆

不再依赖 LLM 在活跃对话中自主调 memory 工具存记忆（那是冗余的）。
改为在会话结束时由后端分析对话历史，提取值得持久化的关键信息。

触发时机（前端信号 + 后端兜底）：
  1. 用户切走场景 → 前端调 POST /api/scenes/{id}/extract-memory
  2. 页面关闭/隐藏 → 前端 visibilitychange 触发同一端点
  3. 后端定时扫描 → 长时空闲场景自动提取（兜底）
"""

import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ── 提取 prompt ──

EXTRACT_SYSTEM_PROMPT = (
    "从对话中提取值得记住的信息，用 JSON 数组格式返回。\n"
    "每条信息的格式：{\"type\": 类型, \"content\": 完整句子}\n"
    "类型取值：user_preference / ai_insight / decision / constraint / key_info / action_item\n"
    "提取范围包括用户说的和 AI 说的。不用开头加「AI」「用户」等前缀。\n"
    "记住：记忆是给下次会话看的。一条信息如果下回用户回来时看到会觉得「对，这个有用」，才值得记。\n"
    "不要记：过渡性对话、即时的操作指令（搜一下、查一下）、客套话、赞同附和。\n"
    "不要记：内容过短、信息量极低的句子。\n"
    "如果没有值得记的返回 []。最多 10 条。只返回 JSON。"
)


def extract_from_conversation(
    messages: list[dict],
    scene_name: str = "",
    model_cfg: Optional[dict] = None,
) -> list[dict]:
    """分析对话历史，提取关键信息

    Args:
        messages: 消息列表 [{"role": "user"|"ai", "content": "..."}, ...]
        scene_name: 场景名称（用于 prompt 上下文）
        model_cfg: 模型路由配置，默认用 "extraction" 路由

    Returns:
        [{"type": str, "content": str}, ...]
    """
    if not messages:
        return []

    if model_cfg is None:
        model_cfg = {
            "model": "qwen3.5-9b",
            "provider": "local",
            "temperature": 0.1,
            "max_tokens": 2048,  # 改大让 AI 输出完整句子
            "context_length": 32768,
        }

    # 拼接对话文本
    dialog_lines = [f"## 【{scene_name}】对话记录"]

    # 跳过前置 AI 消息（开场白/打招呼），从第一条用户消息开始
    first_user_idx = None
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            first_user_idx = i
            break
    if first_user_idx is None:
        logger.info(f"[extractor] {scene_name}: 无用户消息，跳过提取")
        return []
    messages = messages[first_user_idx:]

    for m in messages:
        role_label = "用户" if m["role"] == "user" else "AI"
        content = m.get("content", "")[:1000]  # 单条截断，让 AI 长回复也能被提取
        dialog_lines.append(f"\n{role_label}: {content}")
    dialog_text = "".join(dialog_lines)
    # 截断总体输入
    if len(dialog_text) > 12000:
        dialog_text = "…(前略)\n" + dialog_text[-12000:]

    # 调 LLM
    try:
        result = _call_extraction_llm(dialog_text, model_cfg)
        if isinstance(result, list):
            return result
        logger.warning(f"[extractor] LLM 返回非列表: {result}")
        return []
    except Exception as e:
        logger.error(f"[extractor] 提取失败: {e}")
        return []


def _call_extraction_llm(dialog_text: str, cfg: dict) -> list:
    """调 LLM 提取记忆"""
    provider = cfg.get("provider", "local")
    temperature = cfg.get("temperature", 0.1)
    max_tokens = cfg.get("max_tokens", 1024)

    if provider == "local":
        # 本地 Qwen
        api_url = "http://localhost:8083/v1/chat/completions"
        payload = {
            "model": cfg.get("model", "qwen3.5-q4"),
            "messages": [
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": dialog_text},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(api_url, json=payload, timeout=30)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
    elif provider == "deepseek":
        import os
        from config.urls import DEEPSEEK_BASE_URL

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        api_url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        payload = {
            "model": cfg.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": dialog_text},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(
            api_url, json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
    else:
        logger.warning(f"[extractor] 不支持的 provider: {provider}")
        return []

    # 解析 JSON
    return _parse_extraction_result(raw)


def _parse_extraction_result(raw: str) -> list:
    """从 LLM 输出解析 JSON 数组

    兼容三种格式：
    1. [{"type": "...", "content": "..."}, ...]  (标准格式)
    2. [{"自定义键": "值"}, ...]                    (Qwen 对象格式)
    3. ["内容1", "内容2", ...]                    (Qwen 字符串格式)
    """
    text = raw.strip()

    # 去掉 ```json ... ``` 代码块
    if text.startswith("```"):
        start = text.find("\n")
        end = text.rfind("```")
        if start != -1 and end != -1:
            text = text[start:end].strip()

    # 尝试找 JSON 数组
    arr_start = text.find("[")
    arr_end = text.rfind("]")
    if arr_start != -1 and arr_end != -1:
        text = text[arr_start : arr_end + 1]

    try:
        result = json.loads(text)
        if isinstance(result, list):
            valid = []
            for item in result:
                if isinstance(item, dict) and "content" in item:
                    # 格式1: 标准格式 {type, content}
                    valid.append({
                        "type": item.get("type", "key_info"),
                        "content": item["content"].strip(),
                    })
                elif isinstance(item, dict):
                    # 格式2: 自定义键名 {用户资金: "30万"} (Qwen 风格)
                    for k, v in item.items():
                        if isinstance(v, str) and v.strip():
                            valid.append({
                                "type": "key_info",
                                "content": v.strip(),
                            })
                elif isinstance(item, str) and item.strip():
                    # 格式3: 纯字符串 (Qwen 风格)
                    valid.append({"type": "key_info", "content": item.strip()})
            return valid
    except json.JSONDecodeError:
        pass

    logger.warning(f"[extractor] JSON 解析失败, raw={text[:200]}")
    return []


# ── 保存记忆 ──

def save_extracted_memories(
    db,
    entries: list[dict],
    scene_id: str,
    scene_name: str = "",
) -> int:
    """将提取的记忆批量写入 DB

    Args:
        db: DB session
        entries: [{"type": str, "content": str}, ...]
        scene_id: 场景 ID
        scene_name: 场景名称

    Returns:
        实际写入条数
    """
    from agent_core.memory_manager import MemoryManager

    if not entries:
        return 0

    mm = MemoryManager(db)
    saved = 0

    for entry in entries:
        content = entry.get("content", "").strip()
        entry_type = entry.get("type", "key_info")
        if not content:
            continue

        # 自动去重（Jaccard 相似度检查）
        existing = mm.find_similar_content(
            content,
            scope="scene",
            context_id=scene_id,
            threshold=0.50,
        )
        if existing:
            # 已存在 → 强化权重（不创建副本）
            mm.reinforce(existing.key)
            continue

        # 生成 key
        import re
        clean = re.sub(r'[^\w\u4e00-\u9fff]', '_', content[:20]).strip('_').lower()
        key = f"scene_{clean}" if clean else f"scene_{entry_type}_{saved}"

        try:
            mm.add(
                category="memory",
                key=key,
                content=content,
                tags=[entry_type],
                base_weight=3,
                scope="scene",
                context_id=scene_id,
            )
            saved += 1
        except Exception as e:
            logger.warning(f"[extractor] 保存失败 {key}: {e}")

    logger.info(f"[extractor] {scene_name}: 提取并保存了 {saved}/{len(entries)} 条记忆")
    return saved


# ── 类接口（兼容 scenes.py 已有 import: from agent_core.memory_extractor import MemoryExtractor） ──
class MemoryExtractor:
    """静态接口，包装核心函数"""

    @staticmethod
    def extract(db, scene_id: str, messages: list[dict]) -> list[dict]:
        return extract_from_conversation(messages, scene_name=scene_id)

    @staticmethod
    def save(db, entries: list[dict], scene_id: str) -> int:
        return save_extracted_memories(db, entries, scene_id)
