"""Context 构造器 — 为 LLM 构建完整的"世界视图"

每次调用 LLM 前，按固定结构组装 prompt：
  1. System prompt（角色定义 + 使用说明）
  2. 工具列表
  3. 工具执行结果（如已预执行）
  4. 对话历史（最近 N 条 + role 映射）
  5. 当前用户消息

预执行模式：工具结果先于历史消息注入，LLM 直接基于真实数据回复。
"""

import json
from typing import Optional

from .tool_registry import match_tools, format_tools_for_prompt


# ── 场景聊天的 System Prompt（v0.5 预执行模式） ──
SCENE_SYSTEM_PROMPT = (
    "你是一个专业的AI架构顾问，同时也是坐山客AI工作台的智能助手。\n"
    "系统已自动为你获取了实时数据（天气、景点推荐、装备建议等），数据附在下方。\n"
    "请基于提供的真实数据回复用户，不要编造或猜测数据。\n"
    "用Markdown格式回复，每次回复50-300字，充分且直接。\n"
    "不要拆解任务、不需要创建思维导图。"
)


def build_scene_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    matched_tools: Optional[list[dict]] = None,
    tool_results: Optional[list[dict]] = None,
    weather_context: Optional[str] = None,
    user_context: Optional[str] = None,
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

    # ── 1.5 用户输入背景设定 ──
    if user_context:
        system_parts.append(f"=== 用户输入背景设定 ===\n{user_context}\n=====================")

    # ── 2. 工具列表 ──
    if matched_tools is None:
        matched_tools = match_tools(user_content)
    tools_text = format_tools_for_prompt(matched_tools)
    if tools_text:
        system_parts.append(tools_text)

    # ── 3. 使用说明 ──
    system_parts.append("## 使用说明\n"
        "系统已自动执行了相关工具并附上结果。\n"
        "你无需输出【工具调用】标记，只需基于提供的真实数据回复用户。\n"
        "如果结果中有错误，如实告知用户即可。\n"
        "天气数据建议用表格呈现，并用 ☀/🌧/☁/🌤 等 emoji 图标代替纯文字描述。"
    )

    messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # ── 4. 工具结果上下文（用 assistant 角色，llama.cpp 不允许多条 system） ──
    if tool_results:
        results_block = "## 以下是已执行的工具返回结果，请基于这些数据回复用户：\n"
        for r in tool_results:
            results_block += f"\n### 工具: {r.get('tool', 'unknown')}"
            results_block += f"\n参数: {json.dumps(r.get('params', {}), ensure_ascii=False)}"
            if r.get("success"):
                results_block += f"\n结果: {json.dumps(r.get('result', ''), ensure_ascii=False)[:2000]}"
            else:
                results_block += f"\n错误: {json.dumps(r.get('result', '未知错误'), ensure_ascii=False)}"
        messages.append({"role": "assistant", "content": results_block})

    # ── 5. 对话历史（role 映射） ──
    if history_messages:
        for m in history_messages:
            role = "assistant" if m["role"] == "ai" else m["role"]
            messages.append({"role": role, "content": m["content"]})

    # ── 6. 天气桥接上下文 ──
    user_parts = []
    if weather_context:
        user_parts.append(weather_context)
    user_parts.append(user_content)
    user_msg = "\n\n".join(user_parts)

    messages.append({"role": "user", "content": user_msg})

    return messages


def build_light_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    weather_context: Optional[str] = None,
    tool_results: Optional[list[dict]] = None,
    user_context: Optional[str] = None,
) -> list[dict]:
    """构建 light 路径的简化 context（用于场景快速直答）"""
    matched = match_tools(user_content)
    return build_scene_context(
        user_content=user_content,
        history_messages=history_messages,
        matched_tools=matched,
        tool_results=tool_results,
        weather_context=weather_context,
        user_context=user_context,
    )
