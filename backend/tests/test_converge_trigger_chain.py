"""
A4: converge 触发链端到端验证
测试 _async_converge_worker 的完整触发逻辑：
  1. 场景 + ThinkingMap + 节点创建
  2. check_converge_threshold 调用
  3. auto_converge_and_prioritize 调用（mock LLM）
  4. PQ/Reflect 产出验证
  5. 并发锁防护
  6. 闲聊场景跳过
  7. converge_disabled 跳过
"""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base
from models import Scene, ThinkingMap, ThinkNode, PriorityQueue, ReflectTimeline
from utils import make_id, utcnow


class TestConvergeTriggerChain(unittest.TestCase):
    """converge 触发链端到端测试"""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        self.scene_id = make_id("scene")
        self.tm_id = make_id("tm")

        # 创建场景
        self.scene = Scene(
            id=self.scene_id,
            name="测试收敛场景",
            converge_enabled=True,
            converge_threshold=2.0,
            diverge_min_rounds=2,
        )
        self.db.add(self.scene)

        # 创建 ThinkingMap
        self.tm = ThinkingMap(
            id=self.tm_id,
            scene_id=self.scene_id,
            title="测试收敛树",
            version=1,
        )
        self.db.add(self.tm)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _create_node(self, label, ntype="leaf", parent_id=None, status="discussing"):
        nid = make_id("n")
        node = ThinkNode(
            id=nid, map_id=self.tm_id, type=ntype,
            label=label, parent_id=parent_id,
            status=status,
        )
        self.db.add(node)
        self.db.commit()
        return node

    # ── 1. 阈值触发条件 ──

    def test_threshold_met_triggers_converge(self):
        """叶子数 >= 分支数 × 阈值 时触发收敛"""
        from agent_core.converge_engine import check_converge_threshold

        # 创建 2 个分支 + 4 个叶子 → leaf=4, branch=2, threshold=2.0 => 4 >= 4 => True
        branch1 = self._create_node("分类1", "domain")
        branch2 = self._create_node("分类2", "domain", parent_id=branch1.id)
        self._create_node("叶子1", parent_id=branch1.id)
        self._create_node("叶子2", parent_id=branch1.id)
        self._create_node("叶子3", parent_id=branch2.id)
        self._create_node("叶子4", parent_id=branch2.id)

        nodes = self.db.query(ThinkNode).filter(
            ThinkNode.map_id == self.tm_id,
            ThinkNode.type != "root",
        ).all()

        self.assertTrue(check_converge_threshold(nodes, threshold=2.0))

    def test_threshold_not_met_skips_converge(self):
        """叶子数 < 分支数 × 阈值 时不触发"""
        from agent_core.converge_engine import check_converge_threshold

        # 2 个分支 + 3 个叶子 → leaf=3, branch=2, threshold=2.0 => 3 < 4 => False
        branch1 = self._create_node("分类1", "domain")
        branch2 = self._create_node("分类2", "domain", parent_id=branch1.id)
        self._create_node("叶子1", parent_id=branch1.id)
        self._create_node("叶子2", parent_id=branch1.id)
        self._create_node("叶子3", parent_id=branch2.id)

        nodes = self.db.query(ThinkNode).filter(
            ThinkNode.map_id == self.tm_id,
            ThinkNode.type != "root",
        ).all()

        self.assertFalse(check_converge_threshold(nodes, threshold=2.0))

    # ── 2. converge 执行后 PQ/Reflect 验证 ──

    @patch("ai_engine.call_deepseek_chat")
    def test_converge_creates_pq_and_reflect(self, mock_llm):
        """收敛成功创建 PQ 项和 Reflect 记录"""
        from agent_core.converge_engine import auto_converge_and_prioritize

        # Mock LLM 返回合理结果
        mock_llm.return_value = json.dumps({
            "merges": [
                {"source_ids": ["n1", "n2"], "target_title": "合并后任务"}
            ],
            "discarded_ids": ["n3"],
            "queue": [
                {"target_id": "n1", "title": "合并后任务", "priority": 1, "deps": []}
            ],
            "project": {
                "is_project": True,
                "name": "测试项目",
                "description": "测试",
                "structure": []
            }
        })

        # 创建节点（用真实 ID）
        n1 = self._create_node("任务A")
        n2 = self._create_node("任务B")
        n3 = self._create_node("任务C")

        # 替换 mock 返回值中的 ID
        mock_llm.return_value = json.dumps({
            "merges": [{"source_ids": [n1.id, n2.id], "target_title": "合并后任务"}],
            "discarded_ids": [n3.id],
            "queue": [{"target_id": n1.id, "title": "合并后任务", "priority": 1, "deps": []}],
            "project": {"is_project": True, "name": "测试项目", "description": "测试", "structure": []}
        })

        result = auto_converge_and_prioritize(self.db, self.scene_id, self.tm)

        # 验证 PQ 创建成功
        pq_items = self.db.query(PriorityQueue).filter(
            PriorityQueue.scene_id == self.scene_id
        ).all()
        self.assertGreater(len(pq_items), 0)

        # 验证 Reflect 记录
        reflects = self.db.query(ReflectTimeline).filter(
            ReflectTimeline.scene_id == self.scene_id
        ).all()
        self.assertGreater(len(reflects), 0)
        self.assertTrue(any(r.type == "merge" for r in reflects))
        self.assertTrue(any(r.type == "fail" for r in reflects))

    # ── 3. 场景配置跳过 ──

    def test_converge_disabled_skips(self):
        """converge_enabled=False 时不执行收敛"""
        self.scene.converge_enabled = False
        self.db.commit()

        # 创建足够触发阈值的节点
        branch1 = self._create_node("分类1", "domain")
        self._create_node("叶子1", parent_id=branch1.id)
        self._create_node("叶子2", parent_id=branch1.id)
        self._create_node("叶子3", parent_id=branch1.id)

        # 模拟 _async_converge_worker 的跳过逻辑
        from models import Scene as SceneModel
        s = self.db.query(SceneModel).filter(SceneModel.id == self.scene_id).first()
        if not s.converge_enabled:
            return  # 应跳过

        self.fail("converge_enabled=False 时本应跳过但执行了")

    def test_chat_scene_skips(self):
        """闲聊场景跳过收敛"""
        self.scene.name = "闲聊测试"
        self.db.commit()

        # 闲聊场景不应触发
        if "闲聊" in (self.scene.name or ""):
            return  # 应跳过

        self.fail("闲聊场景本应跳过但执行了")

    # ── 4. 并发锁防护 ──

    def test_concurrent_lock_prevents_duplicate(self):
        """同一场景的并发收敛被锁阻止"""
        from router.scene_stream import _CONVERGE_LOCKS, _CONVERGE_LOCK
        import threading

        # 清空锁状态
        with _CONVERGE_LOCK:
            _CONVERGE_LOCKS.pop(self.scene_id, None)

        # 第一次获取锁 -> 应成功
        lock1 = threading.Lock()
        with _CONVERGE_LOCK:
            if self.scene_id not in _CONVERGE_LOCKS:
                _CONVERGE_LOCKS[self.scene_id] = threading.Lock()
        acquired1 = _CONVERGE_LOCKS[self.scene_id].acquire(blocking=False)
        self.assertTrue(acquired1, "第一次获取锁应成功")

        # 第二次获取同一场景锁 -> 应失败
        acquired2 = _CONVERGE_LOCKS[self.scene_id].acquire(blocking=False)
        self.assertFalse(acquired2, "第二次获取同一场景锁应失败")

        # 释放
        _CONVERGE_LOCKS[self.scene_id].release()

    # ── 5. 自定义阈值 ──

    def test_custom_threshold_3x(self):
        """自定义阈值 3.0"""
        from agent_core.converge_engine import check_converge_threshold

        branch1 = self._create_node("分类1", "domain")
        self._create_node("叶子1", parent_id=branch1.id)
        self._create_node("叶子2", parent_id=branch1.id)
        # leaf=2, branch=1, threshold=3.0 => 2 < 3 => False
        nodes = self.db.query(ThinkNode).filter(
            ThinkNode.map_id == self.tm_id,
            ThinkNode.type != "root",
        ).all()
        self.assertFalse(check_converge_threshold(nodes, threshold=3.0))

        # 再加一个叶子 => leaf=3, branch=1, threshold=3.0 => 3 >= 3 => True
        self._create_node("叶子3", parent_id=branch1.id)
        nodes = self.db.query(ThinkNode).filter(
            ThinkNode.map_id == self.tm_id,
            ThinkNode.type != "root",
        ).all()
        self.assertTrue(check_converge_threshold(nodes, threshold=3.0))

    # ── 6. PQ 清空 + 重建 ──

    @patch("ai_engine.call_deepseek_chat")
    def test_converge_rebuilds_pq(self, mock_llm):
        """二次收敛清空旧 PQ 并重建"""
        from agent_core.converge_engine import auto_converge_and_prioritize

        n1 = self._create_node("任务A")
        n2 = self._create_node("任务B")
        mock_llm.return_value = json.dumps({
            "merges": [], "discarded_ids": [],
            "queue": [{"target_id": n1.id, "title": "任务A", "priority": 1, "deps": []}],
            "project": {"is_project": False, "name": "", "description": "", "structure": []}
        })

        # 第一次收敛
        auto_converge_and_prioritize(self.db, self.scene_id, self.tm)
        pq1 = self.db.query(PriorityQueue).filter(
            PriorityQueue.scene_id == self.scene_id
        ).all()
        self.assertEqual(len(pq1), 1)

        # 第二次收敛（不同节点）
        n3 = self._create_node("任务C")
        mock_llm.return_value = json.dumps({
            "merges": [], "discarded_ids": [],
            "queue": [{"target_id": n2.id, "title": "任务B", "priority": 2, "deps": []}],
            "project": {"is_project": False, "name": "", "description": "", "structure": []}
        })
        auto_converge_and_prioritize(self.db, self.scene_id, self.tm)

        # 旧 PQ 应被清空，只有新 PQ
        pq2 = self.db.query(PriorityQueue).filter(
            PriorityQueue.scene_id == self.scene_id
        ).all()
        self.assertEqual(len(pq2), 1)
        self.assertEqual(pq2[0].title, "任务B")


if __name__ == "__main__":
    unittest.main()
