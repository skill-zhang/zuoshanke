"""Layer 1-C3: Channel SSE 端点测试（Channel CRUD + SSE 流式消息流）

测试目标：
  P0-1: Channel CRUD — 创建/列出/更新/删除/清空
  P0-2: SSE 端点 — user_msg / model_info / context_info / token / done 事件
  P0-3: SSE 错误事件 — AI 引擎返回 None 时正确 yield error
  P0-4: 消息持久化 — SSE 流式消息存入 DB
  P1-1: 非流式消息 — POST /messages 正常返回
  P1-2: 上下文压缩 — 空频道 / 有消息频道
"""
import json
import pytest
import threading
from unittest.mock import patch
from fastapi.testclient import TestClient


# ── 辅助函数 ──


def _create_channel(client, name=None) -> str:
    """创建一个测试频道，返回 channel_id"""
    if name is None:
        name = "测试频道_" + __import__('uuid').uuid4().hex[:6]
    resp = client.post("/api/channels", json={"name": name})
    assert resp.status_code == 200, f"创建频道失败: {resp.text}"
    data = resp.json()
    return data.get("id", "")


def _sse_events(resp, timeout_sec=8):
    """从 SSE StreamingResponse 读取所有事件"""
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
                        payload = json.loads(text[6:])
                        events.append(payload)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    stop = True
    return events


# ── LLM Mock 工厂 ──


def _mock_channel_stream(tokens: list[str]):
    """Mock ai_channel_chat_stream 按顺序 yield token"""
    def _gen(*args, **kwargs):
        for t in tokens:
            yield t
    return _gen


def _mock_channel_chat(text: str = "mock回复"):
    """Mock ai_channel_chat 返回固定文本"""
    def _fn(*args, **kwargs):
        return text
    return _fn


# ══════════════════════════════════════════════════
# P0: Channel CRUD
# ══════════════════════════════════════════════════


class TestChannelCRUD:
    """P0: 频道生命周期 — CRUD"""

    def test_list_channels(self, client: TestClient):
        """信道列表端点正常"""
        resp = client.get("/api/channels")
        assert resp.status_code == 200
        channels = resp.json()
        assert isinstance(channels, list)
        # 默认「闲聊」应存在
        names = [c.get("name", "") for c in channels]
        assert "闲聊" in names, f"默认频道不存在: {names}"

    def test_create_channel(self, client: TestClient):
        """创建频道返回正确字段"""
        name = "新频道_" + __import__('uuid').uuid4().hex[:6]
        resp = client.post("/api/channels", json={"name": name})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("name") == name
        assert data.get("id", "").startswith("ch-")
        assert data.get("is_default") is False

    def test_create_duplicate_name(self, client: TestClient):
        """重复名称返回 400"""
        name = "重复名称_" + __import__('uuid').uuid4().hex[:6]
        resp1 = client.post("/api/channels", json={"name": name})
        assert resp1.status_code == 200
        resp2 = client.post("/api/channels", json={"name": name})
        assert resp2.status_code == 400
        assert "已存在" in resp2.text

    def test_update_channel_name(self, client: TestClient):
        """更新频道名称"""
        channel_id = _create_channel(client)
        new_name = "更新后_" + __import__('uuid').uuid4().hex[:6]
        resp = client.patch(f"/api/channels/{channel_id}", json={"name": new_name})
        assert resp.status_code == 200
        assert resp.json().get("name") == new_name

    def test_update_channel_pin(self, client: TestClient):
        """更新频道 pin 状态"""
        channel_id = _create_channel(client)
        resp = client.patch(f"/api/channels/{channel_id}", json={"pinned": True})
        assert resp.status_code == 200
        assert resp.json().get("pinned") is True

    def test_delete_channel(self, client: TestClient):
        """删除创建的频道"""
        channel_id = _create_channel(client)
        resp = client.delete(f"/api/channels/{channel_id}")
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

    def test_cannot_delete_default_channel(self, client: TestClient):
        """默认「闲聊」频道不可删除"""
        resp = client.get("/api/channels")
        channels = resp.json()
        default = [c for c in channels if c.get("is_default")]
        assert len(default) >= 1, "无默认频道"
        default_id = default[0]["id"]
        resp_del = client.delete(f"/api/channels/{default_id}")
        assert resp_del.status_code == 400
        assert "不可删除" in resp_del.text

    def test_clear_channel_messages(self, client: TestClient):
        """清空频道消息"""
        channel_id = _create_channel(client)
        # 清空空频道应正常返回
        resp = client.delete(f"/api/channels/{channel_id}/messages")
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

    def test_list_after_create(self, client: TestClient):
        """创建后列表包含新频道"""
        name = "列表验证_" + __import__('uuid').uuid4().hex[:6]
        channel_id = _create_channel(client, name)
        resp = client.get("/api/channels")
        channels = resp.json()
        ids = [c.get("id") for c in channels]
        assert channel_id in ids, f"新建频道 {channel_id} 不在列表 {ids}"


# ══════════════════════════════════════════════════
# P0: Channel SSE 流式端点
# ══════════════════════════════════════════════════


class TestChannelSSEStream:
    """P0: Channel SSE 流式消息（mock LLM）"""

    SSE_EVENT_TYPES = {"user_msg", "model_info", "context_info", "token", "done", "error"}

    def test_channel_stream_returns_200(self, client: TestClient):
        """SSE 端点返回 200"""
        channel_id = _create_channel(client)
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["mock"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "hello"},
            )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")

    def test_channel_stream_events_sequence(self, client: TestClient):
        """事件序列包含所有预期事件类型"""
        channel_id = _create_channel(client)
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["这是", " mock", "回复"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "测试消息"},
            )
        events = _sse_events(resp, timeout_sec=10)
        types = [e.get("type") for e in events]
        assert "user_msg" in types, f"缺 user_msg: {types}"
        assert "model_info" in types, f"缺 model_info: {types}"
        assert "context_info" in types, f"缺 context_info: {types}"
        assert "token" in types, f"缺 token: {types}"
        assert "done" in types, f"缺 done: {types}"

    def test_user_msg_has_content(self, client: TestClient):
        """user_msg 事件携带用户发送的内容"""
        channel_id = _create_channel(client)
        msg_text = "频道测试消息@" + __import__('uuid').uuid4().hex[:6]
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["ok"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": msg_text},
            )
        events = _sse_events(resp, timeout_sec=10)
        user_msgs = [e for e in events if e.get("type") == "user_msg"]
        assert len(user_msgs) >= 1, f"未收到 user_msg 事件: {[e.get('type') for e in events]}"
        assert user_msgs[0].get("content") == msg_text

    def test_user_msg_has_attachments(self, client: TestClient):
        """user_msg 事件携带附件信息"""
        channel_id = _create_channel(client)
        attachments = [{"url": "/uploads/test.png", "file_type": "image", "filename": "test.png"}]
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["ok"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "有附件", "attachments": attachments},
            )
        events = _sse_events(resp, timeout_sec=10)
        user_msgs = [e for e in events if e.get("type") == "user_msg"]
        assert len(user_msgs) >= 1
        att = user_msgs[0].get("attachments")
        assert att is not None, f"user_msg 无 attachments: {user_msgs[0]}"
        assert att[0].get("filename") == "test.png"

    def test_model_info_has_model_name(self, client: TestClient):
        """model_info 事件包含模型名称"""
        channel_id = _create_channel(client)
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["ok"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "模型信息"},
            )
        events = _sse_events(resp, timeout_sec=10)
        models = [e for e in events if e.get("type") == "model_info"]
        assert len(models) >= 1
        assert models[0].get("model") is not None

    def test_context_info_has_usage(self, client: TestClient):
        """context_info 事件包含 token 用量信息"""
        channel_id = _create_channel(client)
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["ok"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "上下文信息"},
            )
        events = _sse_events(resp, timeout_sec=10)
        contexts = [e for e in events if e.get("type") == "context_info"]
        assert len(contexts) >= 1
        info = contexts[0]
        assert "total_tokens" in info and "max_tokens" in info
        assert "percentage" in info and "history_count" in info

    def test_token_events_aggregate_to_done_content(self, client: TestClient):
        """所有 token 拼接起来等于 done 事件的 content"""
        channel_id = _create_channel(client)
        tokens = ["hello", " ", "world", "!"]
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(tokens)):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "拼接测试"},
            )
        events = _sse_events(resp, timeout_sec=10)

        # 收集所有 token
        token_texts = [e.get("token", "") for e in events if e.get("type") == "token"]
        assert len(token_texts) == len(tokens), f"token 数量不符: {len(token_texts)} vs {len(tokens)}"

        # done 事件的内容 = token 拼接
        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) >= 1, f"未收到 done 事件: {[e.get('type') for e in events]}"
        done_content = dones[0].get("content", "")
        assert done_content == "".join(tokens), f"done content 不符: '{done_content}' vs '{''.join(tokens)}'"

    def test_done_event_has_model_and_id(self, client: TestClient):
        """done 事件包含模型名和消息 ID"""
        channel_id = _create_channel(client)
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["回复"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "完成信息"},
            )
        events = _sse_events(resp, timeout_sec=10)
        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) >= 1
        assert dones[0].get("id", "").startswith("msg-"), f"done 缺 id: {dones[0]}"
        assert dones[0].get("model") is not None, f"done 缺 model: {dones[0]}"
        assert dones[0].get("role") == "ai"
        assert dones[0].get("created_at") is not None

    def test_user_msg_is_first_event(self, client: TestClient):
        """user_msg 必须是第一个事件"""
        channel_id = _create_channel(client)
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["回复"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "首个事件"},
            )
        events = _sse_events(resp, timeout_sec=10)
        assert len(events) >= 1
        assert events[0].get("type") == "user_msg", f"首个事件不是 user_msg: {events[0]}"

    def test_channel_stream_error_event(self, client: TestClient):
        """AI 引擎返回 None → yield error 事件"""
        channel_id = _create_channel(client)
        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream([None])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": "错误测试"},
            )
        events = _sse_events(resp, timeout_sec=10)
        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) >= 1, f"未收到 error 事件: {[e.get('type') for e in events]}"
        assert "失败" in errors[0].get("message", "")

    def test_channel_stream_messages_saved(self, client: TestClient):
        """SSE 流式消息保存到 DB"""
        channel_id = _create_channel(client)
        msg_text = "保存测试@" + __import__('uuid').uuid4().hex[:6]

        # 手动创建频道消息，让 SSE 端点有 history
        with patch("router.channels.ai_channel_chat", _mock_channel_chat("前置回复")):
            pre_resp = client.post(
                f"/api/channels/{channel_id}/messages",
                json={"content": "前置消息"},
            )
        assert pre_resp.status_code == 200

        with patch("router.channels.ai_channel_chat_stream", _mock_channel_stream(["AI回复内容"])):
            resp = client.post(
                f"/api/channels/{channel_id}/stream",
                json={"content": msg_text},
            )
        assert resp.status_code == 200
        # 消费完 SSE 确保所有 DB 操作完成
        _sse_events(resp, timeout_sec=10)

        # 验证消息在 DB 中 — 通过查询频道消息列表
        # 注意：channels.py 没有暴露 GET /api/channels/{id}/messages，
        # 但我们通过验证 SSE 的 done 事件包含消息已保存来间接验证
        # 或者检查 messages 表
        from database import SessionLocal
        from models import Message
        db = SessionLocal()
        try:
            msgs = db.query(Message).filter(
                Message.channel_id == channel_id
            ).order_by(Message.created_at.asc()).all()
            contents = [m.content for m in msgs]
            assert msg_text in contents, f"用户消息未持久化到 DB: {contents}"
            # AI 回复也应保存
            has_ai = any("AI回复内容" in c for c in contents)
            assert has_ai, f"AI 回复未持久化到 DB: {contents}"
        finally:
            db.close()


# ══════════════════════════════════════════════════
# P1: Channel 非流式消息 / 压缩
# ══════════════════════════════════════════════════


class TestChannelNonStreamMessage:
    """P1: 非流式消息发送 + 压缩"""

    def test_send_message_non_stream(self, client: TestClient):
        """POST /messages 非流式发送返回消息对象"""
        channel_id = _create_channel(client)
        msg_text = "非流式测试@" + __import__('uuid').uuid4().hex[:6]
        with patch("router.channels.ai_channel_chat", _mock_channel_chat("非流式回复")):
            resp = client.post(
                f"/api/channels/{channel_id}/messages",
                json={"content": msg_text},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("role") == "user"
        assert data.get("content") == msg_text

    def test_send_message_saves_ai_reply(self, client: TestClient):
        """非流式消息的 AI 回复保存到 DB"""
        channel_id = _create_channel(client)
        msg_text = "保存AI@" + __import__('uuid').uuid4().hex[:6]
        with patch("router.channels.ai_channel_chat", _mock_channel_chat("AI非流式回复")):
            resp = client.post(
                f"/api/channels/{channel_id}/messages",
                json={"content": msg_text},
            )
        assert resp.status_code == 200

        from database import SessionLocal
        from models import Message
        db = SessionLocal()
        try:
            msgs = db.query(Message).filter(
                Message.channel_id == channel_id
            ).order_by(Message.created_at.asc()).all()
            contents = [m.content for m in msgs]
            assert "AI非流式回复" in contents, f"AI 回复未保存: {contents}"
        finally:
            db.close()

    def test_send_message_with_attachment(self, client: TestClient):
        """非流式消息携带附件"""
        channel_id = _create_channel(client)
        attachments = [{"url": "/uploads/doc.pdf", "file_type": "document", "filename": "doc.pdf"}]
        with patch("router.channels.ai_channel_chat", _mock_channel_chat("附件回复")):
            resp = client.post(
                f"/api/channels/{channel_id}/messages",
                json={"content": "带附件", "attachments": attachments},
            )
        assert resp.status_code == 200

    def test_compress_empty_channel(self, client: TestClient):
        """压缩空频道直接返回 ok"""
        channel_id = _create_channel(client)
        resp = client.post(f"/api/channels/{channel_id}/compress")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("deleted") == 0

    def test_compress_with_messages(self, client: TestClient):
        """压缩有消息的频道"""
        channel_id = _create_channel(client)
        # 先发几个消息
        client.post(
            f"/api/channels/{channel_id}/messages",
            json={"content": "第一条消息"},
        )
        client.post(
            f"/api/channels/{channel_id}/messages",
            json={"content": "第二条消息"},
        )
        # 压缩
        resp = client.post(f"/api/channels/{channel_id}/compress")
        assert resp.status_code == 200
        data = resp.json()
        # 由于调用真实 LLM，可能成功或失败
        if data.get("ok"):
            assert data.get("deleted", 0) >= 2
            assert data.get("summary") and len(data["summary"]) > 0
        else:
            # LLM 调用失败（测试环境可能无真实 API key）
            assert data.get("error") is not None
