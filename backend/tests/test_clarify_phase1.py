"""Phase 1 Clarify 机制 — 单元测试 + 场景测试

测试覆盖：
  1. ClarifyHandler 单元测试：创建请求、等待回复、回复超时、取消
  2. clarify_tool 单元测试：正常调用、空问题、选项截断、无 callback
  3. clarify_router 场景测试：POST 回复、GET pending 轮询
"""

import json
import os
import sys
import threading
import time
import unittest

# 确保能找到 backend 包和 tools 目录
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from utils import make_id, utcnow


# ═══════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════

class TestClarifyHandler(unittest.TestCase):
    """ClarifyHandler 单元测试"""

    def setUp(self):
        from agent_core.clarify_handler import ClarifyHandler
        # 重置单例
        ClarifyHandler._instance = None
        self.handler = ClarifyHandler.get_instance()

    def test_create_request(self):
        """创建请求应返回带 event_id 的对象"""
        req = self.handler.create_request("你选 A 还是 B？", ["A", "B"])
        self.assertTrue(req.event_id.startswith("clar_"))
        self.assertEqual(req.question, "你选 A 还是 B？")
        self.assertEqual(req.choices, ["A", "B"])
        self.assertFalse(req.resolved)

    def test_create_request_open_ended(self):
        """不带选项应创建开放题"""
        req = self.handler.create_request("你觉得怎么样？")
        self.assertIsNone(req.choices)

    def test_wait_and_resolve(self):
        """等待-回复流程"""
        req = self.handler.create_request("继续吗？", ["继续", "取消"])

        # 在另一个线程中回复
        def _respond():
            time.sleep(0.05)
            self.handler.resolve_request(req.event_id, "继续")

        t = threading.Thread(target=_respond, daemon=True)
        t.start()

        result_str = self.handler.wait_for_response(req.event_id, timeout=5)
        result = json.loads(result_str)
        self.assertEqual(result["user_response"], "继续")
        self.assertEqual(result["question"], "继续吗？")

    def test_resolve_invalid_event(self):
        """不存在的 event_id 应返回 False"""
        ok = self.handler.resolve_request("clar_nonexistent", "yes")
        self.assertFalse(ok)

    def test_timeout(self):
        """超时应返回错误"""
        req = self.handler.create_request("测试超时")
        result_str = self.handler.wait_for_response(req.event_id, timeout=0.1)
        result = json.loads(result_str)
        self.assertIn("error", result)
        self.assertIn("超时", result["error"])

    def test_get_pending(self):
        """应有 pending 时返回 event_id"""
        req = self.handler.create_request("测试 pending")
        pending_id = self.handler.get_pending_event_id()
        self.assertEqual(pending_id, req.event_id)

    def test_get_pending_after_resolve(self):
        """解决后不应有 pending"""
        req = self.handler.create_request("测试 resolved")
        self.handler.resolve_request(req.event_id, "ok")
        time.sleep(0.01)  # 让事件传播
        pending_id = self.handler.get_pending_event_id()
        self.assertIsNone(pending_id)

    def test_cancel_request(self):
        """取消应释放等待"""
        req = self.handler.create_request("测试取消")
        self.handler.cancel_request(req.event_id)
        # 解决后 pending 应为空
        pending_id = self.handler.get_pending_event_id()
        self.assertIsNone(pending_id)

    def test_stale_cleanup(self):
        """超过 5 分钟的请求应自动清理"""
        req = self.handler.create_request("旧请求")
        # 手工修改创建时间为 6 分钟前
        import time as _time
        req.created_at = _time.time() - 360  # 6 分钟

        # 记录旧 event_id
        old_eid = req.event_id

        # 创建新请求应触发清理
        req2 = self.handler.create_request("新请求")
        # 旧的应已被清理
        self.assertNotIn(old_eid, self.handler._pending)
        self.assertIn(req2.event_id, self.handler._pending)
        # 清理新请求
        self.handler._pending.pop(req2.event_id, None)


class TestClarifyTool(unittest.TestCase):
    """clarify_tool 工具函数测试"""

    @classmethod
    def setUpClass(cls):
        # 添加 tools 目录到 sys.path
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))

    def test_clarify_with_callback(self):
        """有 callback 时应正常返回"""
        from clarify_tool import clarify_tool

        def mock_callback(q, choices):
            return "我选方案A"

        result_str = clarify_tool("选哪个方案？", ["方案A", "方案B"], callback=mock_callback)
        result = json.loads(result_str)
        self.assertEqual(result["user_response"], "我选方案A")
        self.assertEqual(result["choices_offered"], ["方案A", "方案B"])

    def test_clarify_open_ended(self):
        """开放题应返回用户输入"""
        from clarify_tool import clarify_tool

        def mock_callback(q, choices):
            return "我自己输入的内容"

        result_str = clarify_tool("你的想法是？", callback=mock_callback)
        result = json.loads(result_str)
        self.assertEqual(result["user_response"], "我自己输入的内容")
        self.assertIsNone(result["choices_offered"])

    def test_empty_question(self):
        """空问题应返回错误"""
        from clarify_tool import clarify_tool
        result_str = clarify_tool("", callback=lambda q, c: "ok")
        result = json.loads(result_str)
        self.assertIn("error", result)

    def test_no_callback(self):
        """无 callback 应返回错误"""
        from clarify_tool import clarify_tool
        result_str = clarify_tool("怎么办？")
        result = json.loads(result_str)
        self.assertIn("error", result)
        self.assertIn("无 callback", result["error"])

    def test_choices_truncation(self):
        """超过 4 个选项应截断"""
        from clarify_tool import clarify_tool

        def mock_callback(q, choices):
            return choices[0]

        result_str = clarify_tool("选一个？", ["A", "B", "C", "D", "E", "F"], callback=mock_callback)
        result = json.loads(result_str)
        self.assertEqual(len(result["choices_offered"]), 4)

    def test_invalid_choices_type(self):
        """选项不是列表应返回错误"""
        from clarify_tool import clarify_tool
        result_str = clarify_tool("选？", choices="not_a_list", callback=lambda q, c: "ok")
        result = json.loads(result_str)
        self.assertIn("error", result)

    def test_choices_empty_becomes_open(self):
        """空选项列表应变为开放题"""
        from clarify_tool import clarify_tool
        result_str = clarify_tool("怎么办？", choices=[], callback=lambda q, c: "我自由输入")
        result = json.loads(result_str)
        self.assertIsNone(result["choices_offered"])


class TestClarifyRouter(unittest.TestCase):
    """clarify_router API 端点场景测试"""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from router.clarify_router import router
        from agent_core.clarify_handler import ClarifyHandler

        # 重置 handler 单例
        ClarifyHandler._instance = None

        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_post_clarify_response_ok(self):
        """POST /api/agent-loop/clarify-response 应返回 ok"""
        from agent_core.clarify_handler import ClarifyHandler
        handler = ClarifyHandler.get_instance()
        req = handler.create_request("测试问题")

        resp = self.client.post("/api/agent-loop/clarify-response", json={
            "event_id": req.event_id,
            "response": "用户回复",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_post_clarify_response_nonexistent(self):
        """不存在的 event_id 应返回 404"""
        resp = self.client.post("/api/agent-loop/clarify-response", json={
            "event_id": "clar_nonexistent",
            "response": "test",
        })
        self.assertEqual(resp.status_code, 404)

    def test_get_clarify_pending(self):
        """有 pending 时返回 True"""
        from agent_core.clarify_handler import ClarifyHandler
        handler = ClarifyHandler.get_instance()
        handler.create_request("等待回复的问题", ["A", "B"])

        resp = self.client.get("/api/agent-loop/clarify-pending")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["pending"])
        self.assertIn("event_id", data["info"])

    def test_get_clarify_no_pending(self):
        """无 pending 时返回 False"""
        resp = self.client.get("/api/agent-loop/clarify-pending")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["pending"])

    def test_full_flow_through_api(self):
        """完整流程：创建→pending→回复→无 pending"""
        from agent_core.clarify_handler import ClarifyHandler
        handler = ClarifyHandler.get_instance()
        req = handler.create_request("继续吗？", ["继续", "停止"])

        # 检查 pending
        r1 = self.client.get("/api/agent-loop/clarify-pending")
        self.assertTrue(r1.json()["pending"])

        # 回复
        r2 = self.client.post("/api/agent-loop/clarify-response", json={
            "event_id": req.event_id,
            "response": "继续",
        })
        self.assertTrue(r2.json()["ok"])

        # 短暂等待事件传播
        time.sleep(0.01)

        # 检查不再 pending
        r3 = self.client.get("/api/agent-loop/clarify-pending")
        self.assertFalse(r3.json()["pending"])


class TestClarifyIntegrationWithAgentLoop(unittest.TestCase):
    """Agent Loop 与 Clarify 的集成测试（使用 mock LLM）"""

    def setUp(self):
        from agent_core.clarify_handler import ClarifyHandler
        # 重置 handler
        ClarifyHandler._instance = None

    def test_clarify_in_agent_loop(self):
        """Agent Loop 中调 clarify 应阻塞并返回用户回复"""
        from agent_core.agent_loop import run_agent_loop
        from unittest.mock import patch

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "clarify",
                    "description": "问用户问题",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "choices": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["question"],
                    },
                },
            }
        ]

        def mock_callback(question, choices):
            return "我选方案A"

        tool_callbacks = {"clarify": mock_callback}

        # 模拟 LLM 返回：第一次调 clarify 工具，第二次直接回复
        call_count = [0]

        def mock_llm(messages, tools_list, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "clarify",
                                    "arguments": json.dumps({
                                        "question": "选哪个方案？",
                                        "choices": ["方案A", "方案B"],
                                    }),
                                },
                            }],
                        },
                        "finish_reason": "tool_calls",
                    }],
                }
            return {
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "好的，我们按方案A来实施。",
                    },
                    "finish_reason": "stop",
                }],
            }

        with patch("agent_core.agent_loop.call_llm_with_tools", side_effect=mock_llm):
            events = list(run_agent_loop(
                task="帮我决定选哪个方案",
                tools=tools,
                max_steps=10,
                tool_callbacks=tool_callbacks,
            ))

        # 验证事件序列
        event_types = [e["type"] for e in events]
        self.assertIn("tool_start", event_types)
        self.assertIn("tool_done", event_types)
        self.assertIn("done", event_types)

        # 验证 clarify 工具被调用了
        tool_starts = [e for e in events if e["type"] == "tool_start"]
        tool_names = [e["tool"] for e in tool_starts]
        self.assertIn("clarify", tool_names)
        # 验证 final text 包含方案A
        done_events = [e for e in events if e["type"] == "done"]
        self.assertTrue(len(done_events) >= 1)
        summary = done_events[0].get("summary", "")
        self.assertIn("方案A", summary)


if __name__ == "__main__":
    unittest.main()
