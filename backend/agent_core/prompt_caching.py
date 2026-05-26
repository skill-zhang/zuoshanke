"""Prompt Caching — 坐山客 LLM 调用前缀缓存

减少多轮对话的 input token 成本（~75%）。使用 Anthropic 的 cache_control
机制，通过 OpenRouter 或原生 Anthropic API 向 Claude 模型注入缓存断点。

策略：system_and_3
  断点1: System Prompt（永远命中）
  断点2-4: 最后 3 条非 system 消息（滚动窗口）

检测：model 名含 "claude" 时自动启用。

注：DeepSeek/Qwen 等提供服务端自动前缀缓存（无需客户端注入），
Hermes 代码中通过 prompt_tokens_details.cached_tokens 被动观测，
zuoshanke 目前未做此类观测统计，但缓存本身在服务端自动生效。
"""

import copy
import logging
from typing import Any

_log = logging.getLogger(__name__)


def _model_supports_cache_control(model_name: str) -> bool:
    """判断模型是否支持 cache_control 注入。

    Claude（原生/OpenRouter/兼容网关）和 Qwen（OpenCode/DashScope）
    都认 Anthropic 风格的 cache_control 标记。
    """
    name = model_name.lower().strip()
    return "claude" in name or "qwen" in name


def _apply_cache_to_message(msg: dict, marker: dict) -> None:
    """给单条消息添加 cache_control 标记。

    兼容两种 content 格式：
    - string → 转为 [{"type": "text", "text": "...", "cache_control": ...}]
    - list → 追加到最后一个元素的 dict
    """
    content = msg.get("content")

    if content is None or content == "":
        msg["cache_control"] = marker
        return

    if isinstance(content, str):
        msg["content"] = [
            {"type": "text", "text": content, "cache_control": marker}
        ]
        return

    if isinstance(content, list) and content:
        last = content[-1]
        if isinstance(last, dict):
            last["cache_control"] = marker


def inject_prompt_cache_markers(
    messages: list[dict],
    model_name: str = "",
    cache_ttl: str = "5m",
) -> list[dict]:
    """向消息列表注入 cache_control 断点。

    使用 system_and_3 策略：
    1. System Prompt（首个 system 消息）
    2-4. 最后 3 条非 system 消息（滚动窗口）

    Args:
        messages: OpenAI 格式消息列表
        model_name: 模型名（含 "claude" 时启用）
        cache_ttl: 缓存 TTL，支持 "5m" 和 "1h"

    Returns:
        注入 cache_control 后的消息列表（deep copy）
    """
    if not _model_supports_cache_control(model_name):
        return messages

    msgs = copy.deepcopy(messages)
    if not msgs:
        return msgs

    marker = {"type": "ephemeral", "ttl": cache_ttl} if cache_ttl == "1h" else {"type": "ephemeral"}
    breakpoints_used = 0

    # 断点 1: 首个 system 消息
    first_sys_idx = None
    for i, m in enumerate(msgs):
        if m.get("role") == "system":
            first_sys_idx = i
            break
    if first_sys_idx is not None:
        _apply_cache_to_message(msgs[first_sys_idx], marker)
        breakpoints_used += 1

    # 断点 2-4: 最后 N 条非 system 消息（滚动窗口）
    remaining = 4 - breakpoints_used  # Anthropic 最多 4 个断点
    if remaining > 0:
        non_system_indices = [
            i for i, m in enumerate(msgs) if m.get("role") != "system"
        ]
        # 取最后 remaining 条
        target_indices = []
        # 跳过 last assistant message（可能有 tool_calls，不适合打标记）
        filtered = [i for i in non_system_indices if msgs[i].get("role") != "assistant" or msgs[i].get("content")]
        for idx in filtered[-remaining:]:
            _apply_cache_to_message(msgs[idx], marker)
            target_indices.append(idx)

    _log.info(
        "[PromptCache] model=%s breakpoints=%d (sys + last %d non-sys)",
        model_name,
        breakpoints_used,
        len(target_indices) if breakpoints_used < 4 else 0,
    )

    return msgs
