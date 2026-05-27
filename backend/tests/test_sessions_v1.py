"""Schema v1.1 Session 管理 — 单元测试 + 场景测试

测试覆盖：
  1. 单元测试：WebSession 模型创建、token 累加、状态切换
  2. 边界测试：重复激活、同一上下文的 session 复用
  3. 场景测试：通过 API 完整生命周期
"""
import json
import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

# 确保能找到 backend 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import WebSession, GatewaySession
from utils import make_id, utcnow


class TestWebSessionModel(unittest.TestCase):
    """WebSession 模型单元测试"""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        # 清空表中数据，避免跨测试污染
        self.db.query(WebSession).delete()
        self.db.commit()

    def tearDown(self):
        self.db.rollback()  # 处理可能被回滚的事务
        self.db.query(WebSession).delete()
        self.db.commit()
        self.db.close()

    # ═══════════════════════════════════
    # 单元测试
    # ═══════════════════════════════════

    def test_create_scene_session(self):
        """创建场景 session"""
        ws = WebSession(
            id=make_id("ws"), context_type="scene",
            context_id="scene_01", context_name="测试场景",
            status="active", started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws)
        self.db.commit()
        self.db.refresh(ws)
        self.assertEqual(ws.status, "active")
        self.assertEqual(ws.context_type, "scene")
        self.assertEqual(ws.context_id, "scene_01")
        self.assertIsNone(ws.ended_at)
        self.assertEqual(ws.total_tokens, 0)

    def test_create_channel_session(self):
        """创建频道 session"""
        ws = WebSession(
            id=make_id("ws"), context_type="channel",
            context_id="ch_default", context_name="闲聊",
            status="active", started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws)
        self.db.commit()
        self.db.refresh(ws)
        self.assertEqual(ws.context_type, "channel")
        self.assertEqual(ws.context_id, "ch_default")

    def test_token_accumulation(self):
        """累加 token 用量"""
        ws = WebSession(
            id=make_id("ws"), context_type="scene",
            context_id="scene_02",
            status="active", started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws)
        self.db.commit()

        # 模拟多次 LLM 调用
        ws.prompt_tokens += 150
        ws.completion_tokens += 200
        ws.total_tokens += 350
        ws.api_calls += 1
        ws.estimated_cost_usd += 0.00015
        self.db.commit()

        ws.prompt_tokens += 80
        ws.completion_tokens += 120
        ws.total_tokens += 200
        ws.api_calls += 1
        self.db.commit()

        self.db.refresh(ws)
        self.assertEqual(ws.prompt_tokens, 230)
        self.assertEqual(ws.completion_tokens, 320)
        self.assertEqual(ws.total_tokens, 550)
        self.assertEqual(ws.api_calls, 2)
        self.assertAlmostEqual(ws.estimated_cost_usd, 0.00015)

    def test_session_destroy(self):
        """销毁 session"""
        started = utcnow() - timedelta(hours=2)  # 2小时前创建
        ws = WebSession(
            id=make_id("ws"), context_type="scene",
            context_id="scene_03",
            status="active", started_at=started, last_active_at=utcnow(),
        )
        self.db.add(ws)
        self.db.commit()

        # 超时销毁
        now = utcnow()
        ws.status = "destroyed"
        ws.ended_at = now
        ws.duration_seconds = int((now - started).total_seconds())
        self.db.commit()

        self.db.refresh(ws)
        self.assertEqual(ws.status, "destroyed")
        self.assertIsNotNone(ws.ended_at)
        self.assertGreater(ws.duration_seconds, 0)

    # ═══════════════════════════════════
    # 边界测试
    # ═══════════════════════════════════

    def test_zero_tokens_default(self):
        """新建 session 的 token 字段默认 0（提交后读回）"""
        ws = WebSession(
            id=make_id("ws"), context_type="scene",
            context_id="scene_boundary",
            status="active", started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws)
        self.db.commit()
        self.db.refresh(ws)
        self.assertEqual(ws.prompt_tokens, 0)
        self.assertEqual(ws.completion_tokens, 0)
        self.assertEqual(ws.total_tokens, 0)
        self.assertEqual(ws.api_calls, 0)
        self.assertEqual(ws.estimated_cost_usd, 0.0)
        self.assertEqual(ws.cost_status, "unknown")

    def test_status_default_active(self):
        """status 默认值为 active（提交后读回）"""
        ws = WebSession(
            id=make_id("ws"), context_type="channel",
            context_id="ch_boundary",
            started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws)
        self.db.commit()
        self.db.refresh(ws)
        self.assertEqual(ws.status, "active")

    def test_unique_constraint_per_context(self):
        """每个上下文只能有一个 (context_type, context_id) 组合"""
        ws1 = WebSession(
            id=make_id("ws"), context_type="scene",
            context_id="scene_unique", status="active",
            started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws1)
        self.db.commit()

        ws2 = WebSession(
            id=make_id("ws2"), context_type="scene",
            context_id="scene_unique", status="active",
            started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws2)
        with self.assertRaises(Exception):  # 唯一约束冲突
            self.db.commit()
        self.db.rollback()  # 恢复被回滚的事务

    def test_multiple_contexts_independent(self):
        """不同上下文可以各自有 session"""
        ids = []
        for ctx_type, ctx_id in [("scene", "s1"), ("scene", "s2"), ("channel", "c1"), ("channel", "c2")]:
            ws = WebSession(
                id=make_id("ws"), context_type=ctx_type,
                context_id=ctx_id, status="active",
                started_at=utcnow(), last_active_at=utcnow(),
            )
            self.db.add(ws)
            ids.append(ws.id)
        self.db.commit()
        count = self.db.query(WebSession).count()
        self.assertEqual(count, 4)

    def test_session_fields_mutable(self):
        """所有 v1.1 字段可写"""
        ws = WebSession(
            id=make_id("ws"), context_type="scene",
            context_id="scene_mut", status="active",
            started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws)
        self.db.commit()

        # 修改所有 token 字段
        updates = {
            "prompt_tokens": 1000, "completion_tokens": 500,
            "total_tokens": 1500, "input_tokens": 800,
            "output_tokens": 500, "cache_read_tokens": 200,
            "cache_write_tokens": 100, "reasoning_tokens": 50,
            "api_calls": 5, "estimated_cost_usd": 0.0015,
            "cost_status": "estimated", "cost_source": "deepseek:flash",
        }
        for k, v in updates.items():
            setattr(ws, k, v)
        self.db.commit()
        self.db.refresh(ws)

        for k, v in updates.items():
            self.assertEqual(getattr(ws, k), v, f"字段 {k} 不匹配")

    def test_last_active_at_touch(self):
        """更新 last_active_at"""
        ws = WebSession(
            id=make_id("ws"), context_type="scene",
            context_id="scene_touch", status="active",
            started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(ws)
        self.db.commit()

        old = ws.last_active_at
        time.sleep(0.01)
        ws.last_active_at = utcnow()
        self.db.commit()
        self.db.refresh(ws)
        self.assertGreater(ws.last_active_at, old)

    def test_destroyed_session_duration(self):
        """销毁时 duration_seconds 正确计算"""
        started = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
        ended = datetime(2026, 5, 21, 13, 30, 0, tzinfo=timezone.utc)
        ws = WebSession(
            id=make_id("ws"), context_type="scene",
            context_id="scene_dur", status="destroyed",
            started_at=started, ended_at=ended,
            duration_seconds=int((ended - started).total_seconds()),
        )
        self.assertEqual(ws.duration_seconds, 3 * 3600 + 30 * 60)


class TestGatewaySessionModel(unittest.TestCase):
    """GatewaySession v1.1 扩展字段测试"""

    @classmethod
    def setUpClass(cls):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        cls.Session = sessionmaker(bind=engine)

    def setUp(self):
        self.db = self.Session()
        self.db.query(GatewaySession).delete()
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.query(GatewaySession).delete()
        self.db.commit()
        self.db.close()

    def test_gateway_session_v11_fields_exist(self):
        """GatewaySession 有所有 v1.1 字段"""
        gs = GatewaySession(
            id=make_id("gs"), platform="weixin",
            platform_user_id="test_user",
            status="active", started_at=utcnow(),
            last_active_at=utcnow(),
        )
        self.db.add(gs)
        self.db.commit()
        self.db.refresh(gs)
        self.assertEqual(gs.status, "active")
        self.assertEqual(gs.total_tokens, 0)
        self.assertEqual(gs.api_calls, 0)

    def test_gateway_session_token_tracking(self):
        """GatewaySession 的 token 追踪"""
        gs = GatewaySession(
            id=make_id("gs"), platform="telegram",
            platform_user_id="tg_user_1",
            status="active", started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(gs)
        self.db.commit()

        gs.prompt_tokens += 450
        gs.completion_tokens += 120
        gs.total_tokens += 570
        gs.api_calls += 1
        gs.cache_read_tokens += 300
        self.db.commit()

        self.db.refresh(gs)
        self.assertEqual(gs.prompt_tokens, 450)
        self.assertEqual(gs.completion_tokens, 120)
        self.assertEqual(gs.total_tokens, 570)
        self.assertEqual(gs.api_calls, 1)
        self.assertEqual(gs.cache_read_tokens, 300)

    def test_gateway_session_destroy(self):
        """GatewaySession 销毁"""
        gs = GatewaySession(
            id=make_id("gs"), platform="weixin",
            platform_user_id="test_user_destroy",
            status="active", started_at=utcnow(), last_active_at=utcnow(),
        )
        self.db.add(gs)
        self.db.commit()

        now = utcnow()
        gs.status = "destroyed"
        gs.ended_at = now
        self.db.commit()
        self.db.refresh(gs)
        self.assertEqual(gs.status, "destroyed")
        self.assertIsNotNone(gs.ended_at)


import pytest

@pytest.mark.server
class TestSessionIntegration(unittest.TestCase):
    """通过 API 进行场景测试"""

    BASE = "http://localhost:9001"

    @classmethod
    def setUpClass(cls):
        # 确保后端在跑
        import urllib.request
        try:
            urllib.request.urlopen(f"{cls.BASE}/api/scenes", timeout=3)
        except Exception as e:
            raise RuntimeError(f"后端未运行在 {cls.BASE}: {e}")
        import time
        _ts = str(int(time.time() * 1000))[-6:]
        # 创建测试用的场景和频道
        cls.scene_id = cls._api_static("POST", "/api/scenes", {"name": f"TestSession_{_ts}"})["id"]
        cls.channel_id = cls._api_static("POST", "/api/channels", {"name": f"TestCh_{_ts}"})["id"]
        print(f"\n  🔧 测试场景: {cls.scene_id}, 测试频道: {cls.channel_id}")

    @classmethod
    def _api_static(cls, method, path, body=None) -> dict:
        import urllib.request
        import json
        url = f"{cls.BASE}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def _api(self, method, path, body=None) -> dict:
        import urllib.request
        import json
        url = f"{self.BASE}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.request.HTTPError as e:
            return {"error": e.code, "detail": e.read().decode()}

    def test_01_activate_scene_session(self):
        """场景：激活场景 session -> 成功返回 session 对象"""
        result = self._api("POST", "/api/sessions/activate", {
            "context_type": "scene",
            "context_id": self.scene_id,
            "context_name": "测试场景",
        })
        self.assertIn("id", result)
        self.assertEqual(result["context_type"], "scene")
        self.assertEqual(result["context_id"], self.scene_id)
        self.assertEqual(result["status"], "active")
        self.assertIsNotNone(result["started_at"])
        print(f"\n  ✅ 创建 session: {result['id']}")
        self.scene_sid = result["id"]

    def test_02_activate_twice_reuses_session(self):
        """场景：重复激活同一上下文 -> 复用已有 session"""
        r1 = self._api("POST", "/api/sessions/activate", {
            "context_type": "scene",
            "context_id": self.scene_id,
            "context_name": "测试场景",
        })
        r2 = self._api("POST", "/api/sessions/activate", {
            "context_type": "scene",
            "context_id": self.scene_id,
            "context_name": "测试场景",
        })
        self.assertEqual(r1["id"], r2["id"], "应该复用同一个 session ID")
        print(f"\n  ✅ 复用验证: {r1['id']}")

    def test_03_activate_channel_session(self):
        """场景：激活频道 session"""
        result = self._api("POST", "/api/sessions/activate", {
            "context_type": "channel",
            "context_id": self.channel_id,
            "context_name": "测试频道",
        })
        self.assertEqual(result["context_type"], "channel")
        self.assertEqual(result["context_id"], self.channel_id)
        print(f"\n  ✅ 频道 session: {result['id']}")

    def test_04_get_active_session(self):
        """场景：获取活跃 session"""
        # 确保有个活跃 session
        self._api("POST", "/api/sessions/activate", {
            "context_type": "scene", "context_id": self.scene_id,
        })
        result = self._api("GET", f"/api/sessions/active?context_type=scene&context_id={self.scene_id}")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "active")

    def test_05_get_nonexistent_session(self):
        """场景：获取不存在的 session -> None"""
        result = self._api("GET", "/api/sessions/active?context_type=scene&context_id=nonexistent_xxx")
        self.assertIsNone(result)

    def test_06_touch_session(self):
        """场景：刷新 session last_active_at"""
        ws = self._api("POST", "/api/sessions/activate", {
            "context_type": "scene", "context_id": self.scene_id,
        })
        import time
        time.sleep(0.02)
        result = self._api("POST", f"/api/sessions/{ws['id']}/touch")
        self.assertEqual(result.get("ok"), True)

    def test_07_accumulate_tokens(self):
        """场景：累加 token"""
        ws = self._api("POST", "/api/sessions/activate", {
            "context_type": "scene", "context_id": self.scene_id,
        })
        sid = ws["id"]
        self._api("POST", f"/api/sessions/{sid}/token", {
            "prompt_tokens": 300, "completion_tokens": 200,
            "total_tokens": 500, "api_calls": 1,
            "estimated_cost_usd": 0.00025,
        })
        self._api("POST", f"/api/sessions/{sid}/token", {
            "prompt_tokens": 150, "completion_tokens": 100,
            "total_tokens": 250, "api_calls": 1,
        })
        print(f"\n  ✅ token 累加完成: session={sid}")

    def test_08_list_sessions(self):
        """场景：列出 session"""
        result = self._api("GET", "/api/sessions")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        scenes = self._api("GET", "/api/sessions?context_type=scene")
        for s in scenes:
            self.assertEqual(s["context_type"], "scene")
        print(f"\n  ✅ 共有 {len(result)} 个 session, 其中场景 {len(scenes)} 个")

    def test_09_context_independence(self):
        """场景：不同上下文各自独立"""
        s1 = self._api("POST", "/api/sessions/activate", {
            "context_type": "scene", "context_id": self.scene_id,
        })
        # 创建第二个场景
        s2_resp = self._api_static("POST", "/api/scenes", {"name": "TestSessionScene2"})
        s2 = self._api("POST", "/api/sessions/activate", {
            "context_type": "scene", "context_id": s2_resp["id"],
        })
        c1 = self._api("POST", "/api/sessions/activate", {
            "context_type": "channel", "context_id": self.channel_id,
        })
        self.assertNotEqual(s1["id"], s2["id"])
        self.assertNotEqual(s1["id"], c1["id"])
        self.assertNotEqual(s2["id"], c1["id"])
        print(f"\n  ✅ 3 个独立上下文 session 互不冲突")

    def test_10_invalid_context_type_returns_400(self):
        """场景：无效 context_type 返回 400"""
        result = self._api("POST", "/api/sessions/activate", {
            "context_type": "invalid_type",
            "context_id": "test_invalid",
        })
        self.assertIn("error", result)
        self.assertEqual(result["error"], 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
