"""think 工具 — Thought Stream 思考流

让 LLM 外化思考过程。LLM 通过调用此工具，以内心独白的方式向用户展示当前思考状态。
不做任何实际操作，纯展示层工具。后端通过 registry.json 中的 stream_as: "thought" 标记
将输出转为 SSE thought 事件，而非普通 tool_call 事件。
"""

def think(content: str) -> dict:
    """输出思考过程——像自言自语一样展示正在想什么。

    Args:
        content: 思考内容，1-3句话，内心独白风格

    Returns:
        {"ok": True, "content": "..."}
    """
    return {"ok": True, "content": content}
