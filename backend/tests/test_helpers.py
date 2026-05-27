"""
坐山客测试辅助库 — LLM mock 工具

用法：
  from test_helpers import mock_llm_response, fake_agent_loop_events

  # 方式 A: mock requests.post → 可控 LLM 回复（让 Agent Loop 真实运行）
  with mock_llm_response([tool_calls_response, text_response]):
      ...

  # 方式 B: mock run_agent_loop → 固定事件序列（测试 SSE 端点格式）
  with fake_agent_loop_events([event1, event2]):
      ...
"""
from unittest.mock import patch, MagicMock, ANY
from typing import Generator, Optional


# ── LLM 响应构建 ──

def _make_choice(content=None, tool_calls=None, finish_reason="stop"):
    """构造 OpenAI-compatible choices[0]"""
    msg = {"role": "assistant"}
    if content is not None:
        msg["content"] = content
    else:
        msg["content"] = None
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "message": msg,
        "finish_reason": finish_reason,
    }


def _make_usage(prompt=50, completion=50):
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


def text_response(text: str):
    """构造一个纯文本回复（无 tool_calls）"""
    return {
        "choices": [_make_choice(content=text)],
        "usage": _make_usage(),
    }


def tool_call_response(tool_name: str, args: dict, tool_id: str = "call_mock"):
    """构造一个有 tool_call 的回复"""
    return {
        "choices": [_make_choice(
            content=None,
            tool_calls=[{
                "id": tool_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": __import__('json').dumps(args),
                },
            }],
            finish_reason="tool_calls",
        )],
        "usage": _make_usage(),
    }


# ── 方式 A: mock requests.post（Agent Loop 真实运行） ──

class MockLlmSequence:
    """按顺序返回预设的 LLM 响应"""

    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.call_count = 0

    def __call__(self, url, **kwargs):
        if self.call_count >= len(self.responses):
            # 超出预设响应 → 返回空文本（防止死循环）
            resp = MagicMock()
            resp.json.return_value = text_response("")
            resp.status_code = 200
            self.call_count += 1
            return resp

        resp = MagicMock()
        resp.json.return_value = self.responses[self.call_count]
        resp.status_code = 200
        self.call_count += 1
        return resp


def mock_llm_response(sequence: list[dict]):
    """
    上下文管理器：mock requests.post 返回预设的 LLM 响应。
    在 agent_core.agent_loop 调用 requests.post 时拦截。
    """
    mock_handler = MockLlmSequence(sequence)
    return patch("requests.post", mock_handler)


# ── 方式 B: mock run_agent_loop（固定事件序列） ──

def fake_done_event(text: str = "mock回复") -> dict:
    """构造一个 done 事件"""
    return {
        "type": "done",
        "content": text,
        "summary": text,
        "steps": 1,
        "finish_reason": "stop",
        "usage": _make_usage(),
    }


def fake_tool_start(tool: str, args: dict = None) -> dict:
    return {"type": "tool_start", "tool": tool, "args": args or {}}


def fake_tool_done(tool: str, result: dict = None) -> dict:
    return {"type": "tool_done", "tool": tool, "result": result or {"ok": True}}


def fake_thinking(text: str) -> dict:
    return {"type": "thinking", "text": text}


def fake_token(text: str) -> dict:
    return {"type": "token", "token": text}


def _fake_loop_generator(events: list[dict]) -> Generator:
    """生成固定事件序列的 generator"""
    for event in events:
        yield event


class MockAgentLoop:
    """替换 run_agent_loop 返回固定事件序列"""

    def __init__(self, events: list[dict]):
        self.events = events

    def __call__(self, **kwargs):
        return _fake_loop_generator(self.events)


def fake_agent_loop_events(events: list[dict]):
    """
    上下文管理器：mock SSE 流式端点需要的所有 LLM 调用。
    """
    from contextlib import ExitStack
    from unittest.mock import patch as _patch

    def _mock_extract(content, complexity=None, constraints=None):
        return {"complexity": "light", "constraints": [], "constraints_locked": False}

    mock_handler = MockAgentLoop(events)

    class _CombinedMock:
        def __enter__(self):
            self._stack = ExitStack()
            # extract_and_classify: 模块级 import in scene_stream
            self._stack.enter_context(_patch("router.scene_stream.extract_and_classify", _mock_extract))
            # run_agent_loop: 函数内 from ... import ... → patch 源模块
            self._stack.enter_context(_patch("agent_core.agent_loop.run_agent_loop", mock_handler))
            return self

        def __exit__(self, *args):
            self._stack.close()

    return _CombinedMock()
