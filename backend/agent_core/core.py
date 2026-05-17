"""Agent Core — 坐山客的执行引擎

预执行模式（v0.5）：
  1. 规则检测用户意图 → 匹配则直接执行工具
  2. 工具结果注入 context
  3. 单次流式调 LLM 生成回复

不再依赖小模型输出结构化的【工具调用】JSON，
改用规则层做工具发现与执行，LLM 只负责组织语言。
"""

from typing import Generator, Optional


def agent_core_light_stream(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    scene_id: Optional[str] = None,
    db=None,
    user_context: Optional[str] = None,
    tool_results: Optional[list[dict]] = None,
) -> Generator:
    """Agent Core light 路径 —— 预执行模式

    流程：
      1. 规则检测用户意图 → 匹配则直接执行工具
      2. 工具结果注入 context
      3. 单次流式调 LLM 生成回复

    可传入预计算好的 tool_results（由 scenes.py 路由层预执行），
    避免重复执行。不传则内部自动检测执行。

    Yields:
        - str: token 文本
        - dict: {"_done": True, "reply": "..."}
        - dict: {"_error": True, "message": "..."}
    """
    from ai_engine import _stream_qwen
    from agent_core.context_builder import build_light_context
    from agent_core.tool_executor import detect_and_preexecute

    # ── 1. 预执行：规则检测工具意图并执行 ──
    if tool_results is None:
        tool_results = detect_and_preexecute(user_content)

    # ── 2. 构建 context（含工具结果，LLM 基于真实数据回复） ──
    messages = build_light_context(
        user_content=user_content,
        history_messages=history_messages,
        tool_results=tool_results if tool_results else None,
        user_context=user_context,
    )

    # ── 3. 单次流式输出 ──
    full_reply = ""
    for token in _stream_qwen(messages, temperature=0.7):
        if token is None:
            yield {"_error": True, "message": "AI 引擎响应失败"}
            return
        full_reply += token
        yield token

    yield {"_done": True, "reply": full_reply, "changes": []}
