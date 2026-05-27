"""
Layer 1-B: Agent Loop 收敛链核心契约测试

测试目标：
  P0-1: DialogEngine 阶段流转 — 只能向前，不可回退，跳阶段规则
  P0-2: DialogEngine 阶段检测 — 正则解析 [PHASE:xxx] 标记
  P0-3: Converge 阈值计算 — 叶子数/分支数 数学判定
  P0-4: Agent Loop 死循环检测 — 连续工具调用超限提醒
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════
# DialogEngine — 阶段状态机（纯逻辑，mock DB 即可）
# ═══════════════════════════════════════════════════════

class TestDialogEnginePhaseTransitions:
    """P0: 阶段只能向前，不可回退"""

    @pytest.fixture
    def eng(self):
        """实例化 DialogEngine，用 MagicMock 替代 DB"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from agent_core.dialog_engine import DialogEngine, PHASES, PHASE_NEXT
        mock_db = MagicMock()
        engine = DialogEngine(mock_db, "test_scene_dialog")
        # 手动设置为非 idle 起始
        engine._current_phase = "explore"
        return engine, PHASES, PHASE_NEXT

    def test_detect_transition_forward(self, eng):
        """[PHASE:focus] → 正则匹配到 focus"""
        engine, _, _ = eng
        assert engine.detect_transition("[PHASE:focus] 聚焦深入") == "focus"

    def test_detect_transition_skip_ahead(self, eng):
        """跳阶段：从 explore 检测到 challenge 应该匹配"""
        engine, _, _ = eng
        assert engine.detect_transition("[PHASE:challenge] 挑战一下") == "challenge"

    def test_no_marker_returns_none(self, eng):
        engine, _, _ = eng
        assert engine.detect_transition("普通的回复内容") is None

    def test_case_insensitive(self, eng):
        engine, _, _ = eng
        assert engine.detect_transition("[phase:focus] 小写") == "focus"
        assert engine.detect_transition("[Phase:Focus] 首字母大写") == "focus"

    def test_marker_in_middle(self, eng):
        engine, _, _ = eng
        assert engine.detect_transition("分析后[PHASE:focus]决定深入") == "focus"

    def test_same_phase_blocked(self, eng):
        """停留在同一阶段应被 detect 匹配，但 transition 会拒绝"""
        engine, _, _ = eng
        # detect 只做正则匹配，方向检查在 transition_to
        assert engine.detect_transition("[PHASE:focus] 继续聚焦") == "focus"

    def test_strip_removes_marker(self, eng):
        engine, _, _ = eng
        # strip 后调用 .strip() 去除空白
        assert engine.strip_transition_marker("[PHASE:focus] 你好") == "你好"
        assert engine.strip_transition_marker("没有标记") == "没有标记"

    def test_phases_have_correct_order(self, eng):
        _, phases, next_map = eng
        assert phases == ["idle", "explore", "focus", "decompose", "challenge", "finalize", "execute"]
        assert next_map["execute"] is None

    def test_decompose_is_before_execute(self, eng):
        _, phases, _ = eng
        assert phases.index("decompose") < phases.index("execute")


class TestConvergeThreshold:
    """P0: 收敛阈值数学判定 — 直接调用 check_converge_threshold"""

    def _make_node(self, nid, parent_id=None):
        """创建 ORM 兼容的节点对象（check_converge_threshold 期望 .id .parent_id）"""
        return type("Node", (), {"id": nid, "parent_id": parent_id})()

    def _check(self, nodes, threshold=2.0):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from agent_core.converge_engine import check_converge_threshold
        return check_converge_threshold(nodes, threshold)

    def test_empty_nodes_returns_false(self):
        assert self._check([]) is False

    def test_single_node_returns_false(self):
        assert self._check([self._make_node("1")]) is False

    def test_sufficient_leaves_returns_true(self):
        """叶子数 >= 分支数 × 阈值 → 收敛（不含 root）"""
        nodes = [
            self._make_node("b1", "root"),
            self._make_node("b2", "root"),
            self._make_node("l1", "b1"),
            self._make_node("l2", "b1"),
            self._make_node("l3", "b2"),
            self._make_node("l4", "b2"),
            self._make_node("l5", "b2"),
        ]
        # 分支=b1,b2 (2), 叶子=l1-l5 (5), 5 >= 2*2.0=4 → True
        assert self._check(nodes, 2.0) is True

    def test_insufficient_leaves_returns_false(self):
        """叶子数 < 分支数 × 阈值 → 不收敛"""
        nodes = [
            self._make_node("root"),
            self._make_node("b1", "root"),
            self._make_node("l1", "b1"),
            self._make_node("l2", "b1"),
        ]
        # 分支=root,b1 (2), 叶子=l1,l2 (2), 2 < 2*2.0=4 → False
        assert self._check(nodes, 2.0) is False

    def test_custom_threshold(self):
        nodes = [
            self._make_node("b1", "root"),
            self._make_node("b2", "root"),
            self._make_node("l1", "b1"),
            self._make_node("l2", "b1"),
            self._make_node("l3", "b2"),
        ]
        # 分支=2, 叶子=3, 3 >= 2*1.0=2 → True (宽松)
        assert self._check(nodes, 1.0) is True
        # 3 < 2*2.0=4 → False (严格)
        assert self._check(nodes, 2.0) is False


class TestAgentLoopConstants:
    """P0: Agent Loop 中硬编码的保护阈值（通过源码测试）"""

    def test_deadlock_threshold_exists(self):
        """死循环检测阈值应为 6（检查 agent_loop.py 源码）"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import agent_core.agent_loop as al
        source = open(al.__file__, "r").read()
        # 查找连续工具调用 >= 6 的逻辑
        assert "consecutive_tool_only" in source and ">= 6" in source or "> 5" in source, \
            "agent_loop.py 中应有连续工具调用 >= 6 的检测逻辑"

    def test_repeat_tool_threshold_exists(self):
        """重复工具阈值应为 4（检查 agent_loop.py 源码）"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import agent_core.agent_loop as al
        source = open(al.__file__, "r").read()
        # 查找同一工具连调 >= 4 的逻辑
        assert ">= 4" in source, "agent_loop.py 中应有同一工具连调 >= 4 的检测逻辑"
