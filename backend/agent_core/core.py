"""Agent Core — 坐山客的执行引擎

核心循环（两步法）：
  1. 构造 context（含工具列表）→ 非流式调 LLM
  2. 解析 LLM 输出：有【工具调用】？执行 → 重新构造 context（结果注入 → 流式输出）
  3. 没有？直接用结果流式输出
"""

import json
from typing import Generator, Optional

import sys as _sys, os as _os
_BACKEND_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _BACKEND_DIR not in _sys.path:
    _sys.path.insert(0, _BACKEND_DIR)

from agent_core.context_builder import build_light_context
from agent_core.tool_executor import detect_and_preexecute, execute_tool, parse_tool_call_markup
from agent_core.tool_registry import match_tools


def agent_core_light_stream(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    scene_id: Optional[str] = None,
    db=None,
) -> Generator:
    """Agent Core light 路径 —— 两步法：先判定要不要工具，再流式输出

    Yields:
        - str: token 文本
        - dict: {"_done": True, "reply": "..."}
        - dict: {"_error": True, "message": "..."}
    """
    from ai_engine import _stream_qwen, call_qwen_chat

    # ── 1. 构建 context（含工具列表） ──
    weather_ctx = _weather_maybe(user_content)
    messages = build_light_context(
        user_content=user_content,
        history_messages=history_messages,
        weather_context=weather_ctx,
    )

    # ── 2. 第一步：非流式，看 LLM 要不要调工具 ──
    first_response = call_qwen_chat(messages, temperature=0.3)
    if first_response is None:
        yield {"_error": True, "message": "AI 引擎响应失败"}
        return

    # ── 3. 解析工具调用 ──
    tool_call = parse_tool_call_markup(first_response)

    if tool_call:
        # ── 有工具调用：执行 → 结果回注 → 流式输出 ──
        tool_name = tool_call.get("tool", "")
        params = tool_call.get("params", {})

        # 执行工具
        result = execute_tool(tool_name, params)

        # 重新构造 context：system(角色+工具) → system(结果) → 历史 → user
        msgs_with_result = _build_messages_with_tool_result(
            user_content=user_content,
            history_messages=history_messages,
            weather_context=weather_ctx,
            tool_name=tool_name,
            tool_params=params,
            tool_result=result,
        )

        # 流式输出最终回复
        full_reply = ""
        for token in _stream_qwen(msgs_with_result, temperature=0.7):
            if token is None:
                yield {"_error": True, "message": "AI 引擎响应失败"}
                return
            full_reply += token
            yield token

        yield {"_done": True, "reply": full_reply, "changes": []}
    else:
        # ── 没有工具调用：直接流式输出第一步的结果 ──
        # 但 first_response 是非流式的，我们直接当流式 yield
        full_reply = first_response
        for token in _simulate_stream(first_response):
            yield token

        yield {"_done": True, "reply": full_reply, "changes": []}


def _build_messages_with_tool_result(
    user_content: str,
    history_messages: Optional[list[dict]],
    weather_context: Optional[str],
    tool_name: str,
    tool_params: dict,
    tool_result: dict,
) -> list[dict]:
    """构造带工具结果的 messages，system 消息必须在最前面"""
    from agent_core.tool_registry import format_tools_for_prompt, match_tools

    # 1. System prompt（角色 + 工具列表）
    system_parts = [
        "你是一个专业的AI架构顾问，同时也是坐山客AI工作台的智能助手。\n"
        "你可以使用工具获取实时数据。当用户需要查天气、搜网页等实时信息时，\n"
        "先用【工具调用】标记调工具获取真实数据，再基于数据回复。\n"
        "用Markdown格式回复，每次回复50-300字，充分且直接。"
    ]
    matched = match_tools(user_content)
    tools_text = format_tools_for_prompt(matched)
    if tools_text:
        system_parts.append(tools_text)

    messages = [{"role": "system", "content": "\n\n".join(system_parts)}]

    # 2. 工具执行结果（用 assistant 角色，llama.cpp 不允许多条 system）
    result_block = f"## 工具执行结果\n工具: {tool_name}\n"
    result_block += f"参数: {json.dumps(tool_params, ensure_ascii=False)}\n"
    if tool_result.get("success"):
        result_str = json.dumps(tool_result["result"], ensure_ascii=False, indent=2)[:2000]
        result_block += f"结果:\n{result_str}"
    else:
        result_block += f"错误: {tool_result.get('error', '未知错误')}"
    messages.append({"role": "assistant", "content": result_block})

    # 3. 历史消息
    if history_messages:
        for m in history_messages:
            role = "assistant" if m["role"] == "ai" else m["role"]
            messages.append({"role": role, "content": m["content"]})

    # 4. 天气桥接 + 用户消息
    user_parts = []
    if weather_context:
        user_parts.append(weather_context)
    user_parts.append(user_content)
    messages.append({"role": "user", "content": "\n\n".join(user_parts)})

    return messages


def _simulate_stream(text: str) -> Generator:
    """模拟流式输出，把完整文本当做一个 token yield"""
    if text:
        yield text


def _weather_maybe(user_text: str) -> Optional[str]:
    """天气桥接"""
    try:
        _tp = _os.path.expanduser("~/zuoshanke/tools")
        if _tp not in _sys.path:
            _sys.path.insert(0, _tp)
        from weather import maybe_weather_context
        return maybe_weather_context(user_text)
    except Exception:
        return None
