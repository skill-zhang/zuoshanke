"""测试 — DelegateResult 模型 + API"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/zuoshanke/backend"))


class TestDelegateResultModel(unittest.TestCase):
    """DelegateResult ORM 模型测试"""

    def setUp(self):
        from database import SessionLocal, Base, engine
        from models import DelegateResult
        # 确保表存在
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = SessionLocal
        self.DelegateResult = DelegateResult

    def test_create_and_read(self):
        """写入和读取 DelegateResult"""
        from utils import make_id
        db = self.SessionLocal()
        try:
            dr = self.DelegateResult(
                id=make_id("dres"),
                scene_id="test-scene",
                task="实现用户登录",
                status="success",
                summary="登录功能实现完成，含 JWT 验证",
                steps=5,
            )
            db.add(dr)
            db.commit()

            read = db.query(self.DelegateResult).filter(
                self.DelegateResult.id == dr.id
            ).first()
            self.assertIsNotNone(read)
            self.assertEqual(read.task, "实现用户登录")
            self.assertEqual(read.status, "success")
            self.assertEqual(read.steps, 5)
        finally:
            db.close()

    def test_error_status(self):
        """错误状态的写入"""
        from utils import make_id
        db = self.SessionLocal()
        try:
            dr = self.DelegateResult(
                id=make_id("dres"),
                scene_id="test-scene",
                task="数据库迁移",
                status="error",
                summary="",
                steps=3,
                error="连接超时",
            )
            db.add(dr)
            db.commit()

            read = db.query(self.DelegateResult).filter(
                self.DelegateResult.id == dr.id
            ).first()
            self.assertEqual(read.status, "error")
            self.assertEqual(read.error, "连接超时")
        finally:
            db.close()

    def test_timeout_status(self):
        """超时状态的写入"""
        from utils import make_id
        db = self.SessionLocal()
        try:
            dr = self.DelegateResult(
                id=make_id("dres"),
                scene_id="test-scene",
                task="长时间任务",
                status="timeout",
                summary="",
                steps=0,
                error="超过 300s 限制",
            )
            db.add(dr)
            db.commit()

            read = db.query(self.DelegateResult).filter(
                self.DelegateResult.id == dr.id
            ).first()
            self.assertEqual(read.status, "timeout")
            self.assertEqual(read.steps, 0)
        finally:
            db.close()

    def test_create_at_default(self):
        """created_at 默认值"""
        from utils import make_id
        db = self.SessionLocal()
        try:
            dr = self.DelegateResult(
                id=make_id("dres"),
                scene_id="test-scene",
                task="测试时间",
                status="success",
            )
            db.add(dr)
            db.commit()
            self.assertIsNotNone(dr.created_at)
        finally:
            db.close()


class TestDelegateResultAPI(unittest.TestCase):
    """DelegateResult API 集成测试（需后端运行）"""

    BASE = "http://localhost:8000/api"

    def _fetch(self, url: str) -> dict:
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}

    def test_list_all(self):
        """GET /api/delegate-results 应返回列表"""
        data = self._fetch(f"{self.BASE}/delegate-results")
        if "error" in data and "Connection refused" in str(data):
            self.skipTest("后端未运行")
        self.assertIsInstance(data, list)


if __name__ == "__main__":
    unittest.main()
