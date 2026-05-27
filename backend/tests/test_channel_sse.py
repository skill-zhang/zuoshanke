"""Channel SSE 端点测试 — FastAPI TestClient + mock 流式

测试覆盖:
  1. 正常 SSE 事件序列（user_msg → model_info → context_info → token[s] → done）
  2. 频道不存在 → 404
  3. AI 流式失败 → error 事件
  4. 心情标签解析与剥离
  5. 带附件消息
  6. context_info 包含 token 计数和历史消息数
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from typing import Generator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SASession

from database import Base
from models import Channel, Message, Setting, SETTINGS_ID
from utils import make_id, utcnow
from router.channels import router as channels_router


_SSE_EVENTS_SEEN: set = set()


def _parse_sse_events(raw: str) -> list[dict]:
    """解析 SSE 响应文本为事件列表"""
    events = []
    for line in raw.strip().split("\n"):
        if not line.startswith("data: "):
            continue
        try:
            events.append(json.loads(line[6:]))
        except json.JSONDecodeError:
            continue
    return events


class TestChannelSseEndpoint(unittest.TestCase):
    """Channel SSE 端点单元测试"""

    @classmethod
    def setUpClass(cls):
        # 使用文件 DB 避免线程隔离问题
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmp.close()
        cls.db_url = f"sqlite:///{cls._tmp.name}"
        cls.engine = create_engine(cls.db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=cls.engine)
        cls.TestSession = sessionmaker(bind=cls.engine)

        # 创建 FastAPI 测试应用
        cls.app = FastAPI()
        cls.app.include_router(channels_router)

        def _override_get_db() -> Generator[SASession, None, None]:
            db = cls.TestSession()
            try:
                yield db
            finally:
                db.close()

        cls.app.dependency_overrides.clear()
        from database import get_db
        cls.app.dependency_overrides[get_db] = _override_get_db

        cls.client = TestClient(cls.app)

    def setUp(self):
        self.db = self.TestSession()
        self.db.add(Channel(
            id="ch-test-1", name="测试频道",
            is_default=False, pinned=False,
        ))
        self.db.add(Message(
            id=make_id("msg"), channel_id="ch-test-1",
            role="user", content="之前聊过的话题",
            created_at=utcnow(),
        ))
        self.db.commit()

        # 清除 ai_engine 缓存
        import ai_engine
        ai_engine._settings_cache = None

    def tearDown(self):
        # 清理数据（不删表）
        for tbl in reversed(Base.metadata.sorted_tables):
            self.db.execute(tbl.delete())
        self.db.commit()
        self.db.close()
        import ai_engine
        ai_engine._settings_cache = None

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()
        if os.path.exists(cls._tmp.name):
            os.unlink(cls._tmp.name)

    # ── 工具方法 ──

    def _sse(self, content: str = "你好") -> tuple[int, list[dict]]:
        resp = self.client.post(
            "/api/channels/ch-test-1/stream",
            json={"content": content},
        )
        if resp.status_code != 200:
            return resp.status_code, []
        return 200, _parse_sse_events(resp.text)

    # ── 测试用例 ──

    @patch("router.channels.ai_channel_chat_stream")
    @patch("router.channels.MemoryExtractor")
    @patch("agent_core.zhu_agent.ZhuAgentManager")
    @patch("router.channels.SessionLocal")
    @patch("router.channels._get_route_cfg")
    def test_sse_normal_flow(self, mock_route, mock_sl, mock_zhu, mock_mem, mock_stream):
        """正常 SSE 事件序列"""
        mock_route.return_value = {
            "model": "qwen3.5-9b", "temperature": 0.7,
            "max_tokens": 8192, "context_length": 32768,
        }
        mock_stream.return_value = iter(["你好", "世界", "！"])

        save_db = self.TestSession()
        mock_sl.return_value = save_db
        mock_mem_instance = MagicMock()
        mock_mem_instance.extract.return_value = []
        mock_mem.return_value = mock_mem_instance
        mock_zhu_instance = MagicMock()
        mock_zhu.return_value = mock_zhu_instance

        status, events = self._sse("测试消息")

        self.assertEqual(status, 200)
        self.assertGreater(len(events), 0)

        types = [e["type"] for e in events]
        self.assertIn("user_msg", types)
        self.assertIn("model_info", types)
        self.assertIn("context_info", types)
        self.assertIn("done", types)

        token_events = [e for e in events if e["type"] == "token"]
        self.assertGreaterEqual(len(token_events), 1)
        self.assertEqual("".join(e["token"] for e in token_events), "你好世界！")

        done_event = [e for e in events if e["type"] == "done"][-1]
        self.assertEqual(done_event["role"], "ai")
        self.assertEqual(done_event["content"], "你好世界！")

        user_msg_events = [e for e in events if e["type"] == "user_msg"]
        self.assertEqual(user_msg_events[0]["content"], "测试消息")

        save_db.close()

    @patch("router.channels.ai_channel_chat_stream")
    @patch("router.channels.MemoryExtractor")
    @patch("agent_core.zhu_agent.ZhuAgentManager")
    @patch("router.channels.SessionLocal")
    @patch("router.channels._get_route_cfg")
    def test_sse_ai_failure(self, mock_route, mock_sl, mock_zhu, mock_mem, mock_stream):
        """AI 流式失败返回 error 事件"""
        mock_route.return_value = {"model": "qwen3.5-9b", "context_length": 32768, "temperature": 0.7, "max_tokens": 8192}
        mock_stream.return_value = iter([None])

        save_db = self.TestSession()
        mock_sl.return_value = save_db
        mock_mem_instance = MagicMock()
        mock_mem_instance.extract.return_value = []
        mock_mem.return_value = mock_mem_instance
        mock_zhu_instance = MagicMock()
        mock_zhu.return_value = mock_zhu_instance

        status, events = self._sse("测试消息")
        self.assertEqual(status, 200)
        types = [e["type"] for e in events]
        self.assertIn("error", types)
        save_db.close()

    @patch("router.channels.ai_channel_chat_stream")
    @patch("router.channels.MemoryExtractor")
    @patch("agent_core.zhu_agent.ZhuAgentManager")
    @patch("router.channels.SessionLocal")
    @patch("router.channels._get_route_cfg")
    def test_sse_mood_stripped(self, mock_route, mock_sl, mock_zhu, mock_mem, mock_stream):
        """带心情标签的回复，done 事件剥离心情"""
        mock_route.return_value = {"model": "qwen3.5-9b", "context_length": 32768, "temperature": 0.7, "max_tokens": 8192}
        mock_stream.return_value = iter(["好的", "来", "了", "\n\n[心情: amused] 哈哈哈开心😄"])

        save_db = self.TestSession()
        mock_sl.return_value = save_db
        mock_mem_instance = MagicMock()
        mock_mem_instance.extract.return_value = []
        mock_mem.return_value = mock_mem_instance
        mock_zhu_instance = MagicMock()
        mock_zhu.return_value = mock_zhu_instance

        status, events = self._sse("讲个笑话")
        self.assertEqual(status, 200)

        done_event = [e for e in events if e["type"] == "done"][-1]
        self.assertNotIn("[心情:", done_event["content"])
        self.assertNotIn("amused", done_event["content"])
        self.assertEqual(done_event["content"].strip(), "好的来了")
        save_db.close()

    def test_channel_not_found_404(self):
        """频道不存在返回 404"""
        resp = self.client.post(
            "/api/channels/nonexistent/stream",
            json={"content": "你好"},
        )
        self.assertEqual(resp.status_code, 404)

    @patch("router.channels.ai_channel_chat_stream")
    @patch("router.channels.MemoryExtractor")
    @patch("agent_core.zhu_agent.ZhuAgentManager")
    @patch("router.channels.SessionLocal")
    @patch("router.channels._get_route_cfg")
    def test_sse_with_attachments(self, mock_route, mock_sl, mock_zhu, mock_mem, mock_stream):
        """带附件的消息，user_msg 事件携带 attachments"""
        mock_route.return_value = {"model": "qwen3.5-9b", "context_length": 32768, "temperature": 0.7, "max_tokens": 8192}
        mock_stream.return_value = iter(["好的"])

        save_db = self.TestSession()
        mock_sl.return_value = save_db
        mock_mem_instance = MagicMock()
        mock_mem_instance.extract.return_value = []
        mock_mem.return_value = mock_mem_instance
        mock_zhu_instance = MagicMock()
        mock_zhu.return_value = mock_zhu_instance

        attachments = [{"type": "image", "url": "http://example.com/img.jpg"}]
        resp = self.client.post(
            "/api/channels/ch-test-1/stream",
            json={"content": "带图消息", "attachments": attachments},
        )
        self.assertEqual(resp.status_code, 200)
        events = _parse_sse_events(resp.text)

        user_events = [e for e in events if e["type"] == "user_msg"]
        self.assertGreaterEqual(len(user_events), 1)
        self.assertEqual(user_events[0]["attachments"], attachments)
        save_db.close()

    @patch("router.channels.ai_channel_chat_stream")
    @patch("router.channels.MemoryExtractor")
    @patch("agent_core.zhu_agent.ZhuAgentManager")
    @patch("router.channels.SessionLocal")
    @patch("router.channels._get_route_cfg")
    def test_sse_context_info(self, mock_route, mock_sl, mock_zhu, mock_mem, mock_stream):
        """context_info 事件包含 token 计数和历史消息数"""
        mock_route.return_value = {"model": "qwen3.5-9b", "context_length": 32768, "temperature": 0.7, "max_tokens": 8192}
        mock_stream.return_value = iter(["ok"])

        save_db = self.TestSession()
        mock_sl.return_value = save_db
        mock_mem_instance = MagicMock()
        mock_mem_instance.extract.return_value = []
        mock_mem.return_value = mock_mem_instance
        mock_zhu_instance = MagicMock()
        mock_zhu.return_value = mock_zhu_instance

        status, events = self._sse("测试")
        self.assertEqual(status, 200)

        ctx = [e for e in events if e["type"] == "context_info"]
        self.assertGreaterEqual(len(ctx), 1)
        c = ctx[0]
        self.assertIn("total_tokens", c)
        self.assertIn("max_tokens", c)
        self.assertIn("percentage", c)
        self.assertIn("history_count", c)
        self.assertIn("usage_str", c)
        self.assertIn("progress_bar", c)
        self.assertGreaterEqual(c["history_count"], 1)
        save_db.close()
