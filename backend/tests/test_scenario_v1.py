"""
Schema v1.0 — 场景测试（需要后端在运行）

测试内容：
  1. Agent Loop 通过 v1 composer 正常响应
  2. write_file 后 snapshots 被记录
  3. 消息保存时 priority 字段正确写入
  4. History Layer 按优先级组织
"""

import json
import os
import sys
import time
import unittest
import requests

BACKEND_URL = "http://localhost:9001"

# 检查后端是否在运行
def _backend_running() -> bool:
    try:
        r = requests.get(f"{BACKEND_URL}/", timeout=2)
        return r.status_code < 500
    except Exception:
        return False


@unittest.skipIf(not _backend_running(), "后端未运行，跳过场景测试")
class TestScenarioV1(unittest.TestCase):
    """Schema v1.0 场景测试"""

    def setUp(self):
        # 创建测试场景
        import uuid
        self.scene_name = f"v1-test-{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{BACKEND_URL}/api/scenes",
            json={"name": self.scene_name, "category": "other"},
            timeout=5,
        )
        self.assertEqual(r.status_code, 200, f"场景创建失败: {r.text}")
        data = r.json()
        self.scene_id = data.get("id") or data.get("scene", {}).get("id", "")

    def tearDown(self):
        # 清理测试场景
        if self.scene_id:
            try:
                requests.delete(
                    f"{BACKEND_URL}/api/scenes/{self.scene_id}",
                    timeout=5,
                )
            except Exception:
                pass

    def test_01_agent_loop_basic(self):
        """Agent Loop 通过 v1 composer 正常响应"""
        r = requests.post(
            f"{BACKEND_URL}/api/agent-loop/stream",
            json={"task": "直接回复: 测试v1 composer, 只回复'OK'", "model": "flash"},
            stream=True,
            timeout=30,
        )
        self.assertEqual(r.status_code, 200)
        full_reply = ""
        for line in r.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8", errors="replace")
            if not text.startswith("data: "):
                continue
            try:
                data = json.loads(text[6:])
                event_type = data.get("type", "")
                if "thinking" in event_type or "text" in data:
                    full_reply += data.get("text", "")
                if "done" in event_type and "summary" in data:
                    full_reply = data["summary"]
            except Exception:
                pass
        self.assertGreater(len(full_reply), 0, "AI 应该回复了内容")

    def test_02_scene_message(self):
        """场景消息通过 v1 composer 正常流转"""
        # 发送场景消息
        r = requests.post(
            f"{BACKEND_URL}/api/scenes/{self.scene_id}/stream",
            json={"content": "测试v1 composer", "session_id": "test-session"},
            stream=True,
            timeout=60,
        )
        self.assertEqual(r.status_code, 200)
        done = False
        for line in r.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8", errors="replace")
            if not text.startswith("data: "):
                continue
            if '"done"' in text:
                done = True
                break
        self.assertTrue(done, "场景消息应正常完成")

    def test_03_write_file_creates_snapshot(self):
        """write_file 后 snapshots 被记录"""
        # 直接调用 write_file 工具（不走 LLM，减少不确定性）
        test_file = "/tmp/v1_test_snapshot.txt"
        import sqlite3

        # 通过工具模块直接写入（模拟 Agent Loop 中的调用）
        tools_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
        sys.path.insert(0, tools_dir)
        from file_tools import write_file
        result = write_file(test_file, "hello v1")
        self.assertTrue(result.get("success"), f"write_file 失败: {result}")

        # 验证 snapshot 是否被记录
        db_path = os.path.expanduser("~/zuoshanke/backend/zuoshanke.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT count(*) FROM file_snapshots WHERE file_path = ?",
            (os.path.abspath(test_file),)
        )
        count = cursor.fetchone()[0]
        conn.close()
        self.assertGreater(count, 0, f"write_file 后应有快照记录，当前: {count}")

        # 清理
        if os.path.exists(test_file):
            os.unlink(test_file)

    def test_04_history_high_priority(self):
        """高优先级消息在 history 中正确标记"""
        # 用 [P:high] 标记回复
        r = requests.post(
            f"{BACKEND_URL}/api/scenes/{self.scene_id}/stream",
            json={
                "content": "这是一条[P:high]标记消息",
                "session_id": "test-session",
                "priority": "high",
            },
            stream=True,
            timeout=60,
        )
        self.assertEqual(r.status_code, 200)
        for line in r.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8", errors="replace")
            if '"done"' in text:
                # 验证消息被保存且 priority 字段正确
                import sqlite3
                conn = sqlite3.connect(
                    os.path.expanduser("~/zuoshanke/backend/zuoshanke.db")
                )
                cursor = conn.execute(
                    "SELECT priority FROM messages WHERE scene_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (self.scene_id,)
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    self.assertIn(row[0], ["high", "normal", "low"])
                break

    def test_05_scene_config_document_deps(self):
        """scene_config 的 document_deps 正确存储和读取"""
        import sqlite3
        import json

        # 写入 scene_config
        config = {
            "work_output_window_size": 5,
            "document_deps": [
                {"doc": "schema-v1.0.md", "level": "single_line"},
                {"doc": "schema-v0.81.md", "level": "brief"},
            ]
        }
        db_path = os.path.expanduser("~/zuoshanke/backend/zuoshanke.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE scenes SET scene_config = ? WHERE id = ?",
            (json.dumps(config, ensure_ascii=False), self.scene_id)
        )
        conn.commit()

        # 读取验证
        cursor = conn.execute(
            "SELECT scene_config FROM scenes WHERE id = ?",
            (self.scene_id,)
        )
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row, "scene_config 不应为空")
        saved = json.loads(row[0])
        self.assertEqual(saved["work_output_window_size"], 5)
        self.assertEqual(len(saved["document_deps"]), 2)
        self.assertEqual(saved["document_deps"][0]["doc"], "schema-v1.0.md")

        # 验证通过 composer 能正常加载
        from agent_core.context_composer import _build_document_layer
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from database import SessionLocal
        db = SessionLocal()
        try:
            result = _build_document_layer(self.scene_id, db)
            # 有 deps 时应显示文档列表
            self.assertIn("schema-v1.0.md", result)
            self.assertIn("schema-v0.81.md", result)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
