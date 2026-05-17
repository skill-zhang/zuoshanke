"""Context 构造器 — 为 LLM 构建完整的"世界视图"

每次调用 LLM 前，按固定结构组装 prompt：
  1. System prompt（角色定义 + 工具协议说明）
  2. 工具列表（基础工具 + 匹配工具）
  3. 对话历史（最近 N 条 + role 映射）
  4. 当前用户消息
  5. 工具执行结果（如果在循环中）
"""

import json
from typing import Optional

from .tool_registry import match_tools, format_tools_for_prompt


# ── 场景聊天的 System Prompt（区别于频道闲聊） ──
SCENE_SYSTEM_PROMPT = (
    "你是一个专业的AI架构顾问，同时也是坐山客AI工作台的智能助手。\n"
    "你可以使用工具获取实时数据。当用户需要查天气、搜网页等实时信息时，\n"
    "先用【工具调用】标记调工具获取真实数据，再基于数据回复。\n"
    "用Markdown格式回复，每次回复50-300字，充分且直接。\n"
    "不要拆解任务、不需要创建思维导图。"
)


def build_scene_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    matched_tools: Optional[list[dict]] = None,
    tool_results: Optional[list[dict]] = None,
    weather_context: Optional[str] = None,
) -> list[dict]:
    """构建场景聊天的 LLM 消息列表

    Args:
        user_content: 用户当前消息
        history_messages: 历史消息列表 [{"role": ..., "content": ...}, ...]
        matched_tools: 匹配到的工具列表（None 则自动匹配）
        tool_results: 已执行的工具结果列表
        weather_context: 天气桥接上下文（向后兼容）

    Returns:
        OpenAI 格式的消息列表
    """
    messages = []

    # ── 1. System prompt ──
    system_parts = [SCENE_SYSTEM_PROMPT]

    # ── 2. 工具列表 ──
    if matched_tools is None:
        matched_tools = match_tools(user_content)
    tools_text = format_tools_for_prompt(matched_tools)
    if tools_text:
        system_parts.append(tools_text)

    # ── 3. 工具调用协议说明 ──
    system_parts.append(
        "## 工具调用说明\n"
        "当你需要获取实时数据时，请先调用工具，拿到结果后再回复。\n"
        "示例：用户问「北京天气」→ 你输出【工具调用】→ 系统执行 → 你基于结果回复。\n"
        "不要假装知道实时数据，先调工具。"
    )

    messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # ── 4. 对话历史（role 映射） ──
    if history_messages:
        for m in history_messages:
            role = "assistant" if m["role"] == "ai" else m["role"]
            messages.append({"role": role, "content": m["content"]})

    # ── 5. 天气桥接上下文 ──
    user_parts = []
    if weather_context:
        user_parts.append(weather_context)
    user_parts.append(user_content)
    user_msg = "\n\n".join(user_parts)

    # ── 6. 工具结果上下文 ──
    if tool_results:
        results_block = "## 以下是已执行的工具返回结果，请基于这些数据回复用户：\n"
        for r in tool_results:
            results_block += f"\n### 工具: {r.get('tool', 'unknown')}"
            results_block += f"\n参数: {json.dumps(r.get('params', {}), ensure_ascii=False)}"
            results_block += f"\n结果: {json.dumps(r.get('result', ''), ensure_ascii=False)[:2000]}"
        messages.append({"role": "system", "content": results_block})

    messages.append({"role": "user", "content": user_msg})

    return messages


def build_light_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    weather_context: Optional[str] = None,
) -> list[dict]:
    """构建 light 路径的简化 context（用于场景快速直答）"""
    # 自动匹配工具
    matched = match_tools(user_content)
    return build_scene_context(
        user_content=user_content,
        history_messages=history_messages,
        matched_tools=matched,
        tool_results=None,
        weather_context=weather_context,
    )
