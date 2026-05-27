"""
Layer 1-C2: SSE 消息流测试（带 LLM mock）

测试目标：
  P0-1: user_msg 事件回显（content + attachments）
  P0-2: agent_stream 事件被正确转为 SSE 事件
  P0-3: done 事件包含回复内容
  P0-4: 消息保存到 DB（即使 SSE 流式处理）
"""
import json
import pytest
from fastapi.testclient import TestClient
from test_helpers import (
    fake_agent_loop_events, fake_tool_start, fake_tool_done,
    fake_thinking, fake_done_event,
)


def _create_scene(client, name="SSE测试"):
    resp = client.post("/api/scenes", json={"name": name, "category": "life"})
    assert resp.status_code == 200
    return resp.json().get("id", "")


def _sse_events(resp, timeout_sec=5):
    """从 SSE StreamingResponse 读取所有事件"""
    import threading
    events = []
    stop = False

    def read():
        nonlocal stop
        try:
            for line in resp.iter_lines():
                if stop:
                    break
                if not line:
                    continue
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                if text.startswith("data: "):
                    try:
                        events.append(json.loads(text[6:]))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    stop = True
    return events


class TestSSEWithMock:
    """P0: SSE 消息流（mock Agent Loop，不调真实 LLM）"""

    def test_user_msg_event(self, client: TestClient):
        """user_msg 事件携带正确的 content"""
        scene_id = _create_scene(client, "SSE_user_msg")
        msg_text = "mock测试消息"

        with fake_agent_loop_events([
            fake_thinking("mock思考"),
            fake_done_event("mock回复"),
        ]):
            resp = client.post(
                f"/api/scenes/{scene_id}/stream",
                json={"content": msg_text, "channel": "chat"},
            )

        assert resp.status_code == 200
        events = _sse_events(resp)

        user_msgs = [e for e in events if e.get("type") == "user_msg"]
        assert len(user_msgs) >= 1, f"未收到 user_msg 事件: {[e.get('type') for e in events]}"
        assert user_msgs[0].get("content") == msg_text

    def test_done_event_has_content(self, client: TestClient):
        """done 事件携带 AI 回复内容"""
        scene_id = _create_scene(client, "SSE_done")

        with fake_agent_loop_events([
            fake_thinking("分析中..."),
            fake_done_event("这是AI的mock回复"),
        ]):
            resp = client.post(
                f"/api/scenes/{scene_id}/stream",
                json={"content": "帮我分析", "channel": "chat"},
            )

        events = _sse_events(resp)
        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) >= 1, f"未收到 done 事件: {[e.get('type') for e in events]}"

        content = dones[0].get("content") or dones[0].get("summary", "")
        assert "mock回复" in content, f"done 内容不符: {dones[0]}"

    def test_event_sequence(self, client: TestClient):
        """事件序列包含预期的事件类型"""
        scene_id = _create_scene(client, "SSE_sequence")

        with fake_agent_loop_events([
            fake_tool_start("think", {"content": "思考中"}),
            fake_tool_done("think", {"ok": True}),
            fake_thinking("最终结论"),
            fake_done_event("结论"),
        ]):
            resp = client.post(
                f"/api/scenes/{scene_id}/stream",
                json={"content": "序列测试", "channel": "chat"},
            )

        events = _sse_events(resp)
        types = [e.get("type") for e in events]
        assert "user_msg" in types, f"缺 user_msg: {types}"
        assert "done" in types, f"缺 done: {types}"
        assert len(types) >= 3, f"事件太少: {types}"

    def test_message_saved_to_db(self, client: TestClient):
        """发送的消息保存到 DB（消息列表可查）"""
        scene_id = _create_scene(client, "SSE_db_persist")
        msg_text = "持久化测试@" + __import__('uuid').uuid4().hex[:6]

        with fake_agent_loop_events([
            fake_thinking("ok"),
            fake_done_event("ok"),
        ]):
            client.post(
                f"/api/scenes/{scene_id}/stream",
                json={"content": msg_text, "channel": "chat"},
            )

        # 验证消息已写入 DB
        resp = client.get(f"/api/scenes/{scene_id}/messages")
        assert resp.status_code == 200
        msgs = resp.json().get("messages") or resp.json().get("items") or []
        contents = [m.get("content", "") for m in msgs]
        assert msg_text in contents, f"消息未持久化到 DB。内容: {contents[:5]}"
