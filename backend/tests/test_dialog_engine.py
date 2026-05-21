"""
dialog_engine.py 单元测试
测试 6 阶段状态机（加 decompose + challenge）的核心逻辑
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_core.dialog_engine import (
    DialogEngine,
    PHASES,
    PHASE_ORDER,
    PHASE_NEXT,
    PHASE_DESCRIPTIONS,
    PHASE_ROLES,
    PHASE_TRANSITION_RE,
)


class FakeDialogState:
    """模拟 DialogState 对象（避免依赖真实数据库）"""
    def __init__(self, phase="idle", summary="", decisions=None, context=None):
        self.scene_id = "test_scene"
        self.phase = phase
        self.summary = summary
        self.decisions = decisions or []
        self.context = context or {}
        self.created_at = None
        self.updated_at = None


def _make_engine(phase="idle", context=None):
    """辅助：创建一个使用 Mock DB 的 DialogEngine，并预设阶段。"""
    state = FakeDialogState(
        phase=phase,
        summary="",
        decisions=[],
        context=context or {},
    )
    db = MagicMock()
    query_mock = MagicMock()
    filter_mock = MagicMock()
    filter_mock.first.return_value = state
    query_mock.filter.return_value = filter_mock
    db.query.return_value = query_mock

    engine = DialogEngine(db, "test_scene")
    # 覆盖加载的状态为我们的 FakeDialogState
    engine._state = state
    return engine


# ════════════════════════════════════════════════════
# 基础定义测试
# ════════════════════════════════════════════════════

class TestPhaseDefinitions(unittest.TestCase):
    """阶段列表和常量定义"""

    def test_phases_include_decompose_and_challenge(self):
        """PHASES 列表包含新阶段 decompose 和 challenge"""
        self.assertIn("decompose", PHASES)
        self.assertIn("challenge", PHASES)

    def test_phases_has_7_elements(self):
        """总共 7 个阶段"""
        self.assertEqual(len(PHASES), 7)

    def test_phase_order_correct(self):
        """阶段顺序正确"""
        expected = ["idle", "explore", "focus", "decompose", "challenge", "finalize", "execute"]
        self.assertEqual(PHASES, expected)

    def test_phase_descriptions_contains_all(self):
        """每个阶段都有中文描述"""
        for p in PHASES:
            self.assertIn(p, PHASE_DESCRIPTIONS)
            self.assertTrue(len(PHASE_DESCRIPTIONS[p]) > 0)

    def test_phase_roles_contains_all(self):
        """每个阶段都有角色名"""
        for p in PHASES:
            self.assertIn(p, PHASE_ROLES)

    def test_phase_next_mapping(self):
        """PHASE_NEXT 推荐映射完整"""
        self.assertEqual(PHASE_NEXT["idle"], "explore")
        self.assertEqual(PHASE_NEXT["explore"], "focus")
        self.assertEqual(PHASE_NEXT["focus"], "decompose")
        self.assertEqual(PHASE_NEXT["decompose"], "challenge")
        self.assertEqual(PHASE_NEXT["challenge"], "finalize")
        self.assertEqual(PHASE_NEXT["finalize"], "execute")
        self.assertIsNone(PHASE_NEXT["execute"])


# ════════════════════════════════════════════════════
# 阶段转移检测
# ════════════════════════════════════════════════════

class TestDetectTransition(unittest.TestCase):
    """detect_transition 方法"""

    def test_no_marker_returns_none(self):
        """无 [PHASE:] 标记返回 None"""
        engine = _make_engine("explore")
        self.assertIsNone(engine.detect_transition("普通回复内容"))

    def test_empty_content_returns_none(self):
        """空内容返回 None"""
        engine = _make_engine("explore")
        self.assertIsNone(engine.detect_transition(""))
        self.assertIsNone(engine.detect_transition(None))

    def test_forward_sequential(self):
        """合法的顺序前进（idle → explore → focus）"""
        engine = _make_engine("idle")
        self.assertEqual(engine.detect_transition("[PHASE:explore]"), "explore")

        engine = _make_engine("explore")
        self.assertEqual(engine.detect_transition("[PHASE:focus]"), "focus")

    def test_forward_skip_ahead(self):
        """允许跳阶段向前（explore → challenge）"""
        engine = _make_engine("explore")
        result = engine.detect_transition("[PHASE:challenge]")
        self.assertEqual(result, "challenge")

    def test_forward_skip_to_execute_without_decompose_blocked(self):
        """跳过 decompose 直接进入 execute 被拦截"""
        engine = _make_engine("focus", context={})
        result = engine.detect_transition("[PHASE:execute]")
        self.assertIsNone(result)

    def test_forward_to_execute_after_decompose_allowed(self):
        """经过 decompose 后可以进入 execute"""
        engine = _make_engine("finalize", context={"decompose_completed": True})
        result = engine.detect_transition("[PHASE:execute]")
        self.assertEqual(result, "execute")

    def test_backward_blocked(self):
        """回退阶段被拦截（focus → idle）"""
        engine = _make_engine("focus")
        self.assertIsNone(engine.detect_transition("[PHASE:idle]"))

    def test_backward_also_blocked_for_adjacent(self):
        """回退相邻阶段也被拦截（finalize → focus）"""
        engine = _make_engine("finalize")
        self.assertIsNone(engine.detect_transition("[PHASE:focus]"))

    def test_same_phase_blocked(self):
        """原地不动（当前阶段 == 目标阶段）被拦截"""
        engine = _make_engine("focus")
        self.assertIsNone(engine.detect_transition("[PHASE:focus]"))

    def test_invalid_phase_name(self):
        """无效阶段名被拦截"""
        engine = _make_engine("explore")
        self.assertIsNone(engine.detect_transition("[PHASE:invalid]"))

    def test_marker_in_middle_of_text(self):
        """标记出现在回复中间也能正确解析"""
        engine = _make_engine("explore")
        result = engine.detect_transition(
            "好的，我已经了解了你的需求。[PHASE:focus] 接下来我们聚焦一下。"
        )
        self.assertEqual(result, "focus")

    def test_case_insensitive_marker(self):
        """标记大小写不敏感"""
        engine = _make_engine("explore")
        self.assertEqual(engine.detect_transition("[PHASE:FOCUS]"), "focus")
        self.assertEqual(engine.detect_transition("[PHASE:Focus]"), "focus")


# ════════════════════════════════════════════════════
# 标记剥离
# ════════════════════════════════════════════════════

class TestStripTransitionMarker(unittest.TestCase):
    """strip_transition_marker 方法"""

    def test_strip_removes_marker(self):
        """移除 [PHASE:xxx] 标记"""
        engine = _make_engine("explore")
        cleaned = engine.strip_transition_marker(
            "好的，开始探索。[PHASE:focus]"
        )
        self.assertEqual(cleaned, "好的，开始探索。")

    def test_strip_multiple_markers(self):
        """移除多个标记（保留单空格）"""
        engine = _make_engine("explore")
        cleaned = engine.strip_transition_marker(
            "[PHASE:explore] 先探索 [PHASE:focus] 再聚焦"
        )
        self.assertEqual(cleaned, "先探索  再聚焦")

    def test_strip_no_marker(self):
        """无标记时内容不变"""
        engine = _make_engine("explore")
        cleaned = engine.strip_transition_marker("普通内容")
        self.assertEqual(cleaned, "普通内容")


# ════════════════════════════════════════════════════
# 阶段转移执行
# ════════════════════════════════════════════════════

class TestTransitionTo(unittest.TestCase):
    """transition_to 方法"""

    def test_transition_to_valid_phase(self):
        """合法转移成功"""
        engine = _make_engine("idle")
        result = engine.transition_to("explore")
        self.assertTrue(result)
        self.assertEqual(engine.phase, "explore")

    def test_transition_to_invalid_phase(self):
        """无效阶段返回 False"""
        engine = _make_engine("idle")
        result = engine.transition_to("invalid_phase")
        self.assertFalse(result)
        self.assertEqual(engine.phase, "idle")  # 不应改变

    def test_transition_marks_decompose_completed(self):
        """进入 decompose 时标记 decompose_completed = True"""
        engine = _make_engine("focus")
        engine.transition_to("decompose")
        self.assertEqual(engine._state.context.get("decompose_completed"), True)

    def test_transition_preserves_existing_context(self):
        """转移到 decompose 不覆盖已有 context"""
        engine = _make_engine("focus", context={"user_goal": "test"})
        engine.transition_to("decompose")
        self.assertEqual(engine._state.context.get("user_goal"), "test")
        self.assertEqual(engine._state.context.get("decompose_completed"), True)

    def test_transition_merges_new_context(self):
        """传递新 context 参数时合并"""
        engine = _make_engine("focus", context={"old_key": "old_value"})
        engine.transition_to("decompose", context={"new_key": "new_value"})
        self.assertEqual(engine._state.context.get("old_key"), "old_value")
        self.assertEqual(engine._state.context.get("new_key"), "new_value")

    def test_transition_appends_decisions(self):
        """决策追加到已有列表前面"""
        engine = _make_engine("explore", context={})
        engine._state.decisions = ["old_decision"]
        engine.transition_to("focus", decisions=["new_decision"])
        self.assertEqual(engine._state.decisions, ["new_decision", "old_decision"])

    def test_transition_updates_summary(self):
        """转移时更新摘要"""
        engine = _make_engine("explore")
        engine.transition_to("focus", summary="聚焦在需求确认上")
        self.assertEqual(engine._state.summary, "聚焦在需求确认上")


# ════════════════════════════════════════════════════
# decompose 前置条件综合测试
# ════════════════════════════════════════════════════

class TestDecomposePrerequisite(unittest.TestCase):
    """decompose 是 execute 前置条件"""

    def test_execute_without_decompose_detected_blocked(self):
        """detect_transition: 未经过 decompose 时阻止 execute"""
        for start in ("explore", "focus", "challenge", "finalize"):
            with self.subTest(start=start):
                engine = _make_engine(start, context={})
                result = engine.detect_transition("[PHASE:execute]")
                self.assertIsNone(result, f"{start} → execute 应被拦截")

    def test_execute_after_decompose_allowed(self):
        """detect_transition: 经过 decompose 后 execute 允许"""
        for start in ("finalize", "challenge", "decompose", "explore", "focus"):
            with self.subTest(start=start):
                engine = _make_engine(start, context={"decompose_completed": True})
                result = engine.detect_transition("[PHASE:execute]")
                self.assertIsNotNone(result, f"{start} → execute 应通过")


# ════════════════════════════════════════════════════
# 提示 / 指令测试
# ════════════════════════════════════════════════════

class TestPhasePrompt(unittest.TestCase):
    """get_phase_prompt / get_transition_instruction"""

    def test_get_phase_prompt_format(self):
        """阶段提示包含角色、阶段名和描述"""
        engine = _make_engine("decompose")
        prompt = engine.get_phase_prompt()
        self.assertIn("架构师", prompt)
        self.assertIn("decompose", prompt)
        self.assertIn("任务分解", prompt)

    def test_get_phase_prompt_all_phases(self):
        """每个阶段都能生成提示"""
        for p in PHASES:
            engine = _make_engine(p)
            prompt = engine.get_phase_prompt()
            self.assertIn(p, prompt)
            self.assertTrue(len(prompt) > 10)

    def test_transition_instruction_mentions_all_phases(self):
        """转移指令包含所有可用阶段"""
        engine = _make_engine("idle")
        instruction = engine.get_transition_instruction()
        for p in ("explore", "focus", "decompose", "challenge", "finalize", "execute"):
            self.assertIn(p, instruction)

    def test_transition_instruction_skip_ahead(self):
        """转移指令提到可以跳过中间阶段"""
        engine = _make_engine("idle")
        instruction = engine.get_transition_instruction()
        self.assertIn("跳过", instruction)


# ════════════════════════════════════════════════════
# is_active / is_complex
# ════════════════════════════════════════════════════

class TestProperties(unittest.TestCase):
    """is_active, is_complex, phase 属性"""

    def test_phase_property(self):
        """phase 属性返回当前阶段"""
        engine = _make_engine("decompose")
        self.assertEqual(engine.phase, "decompose")

    def test_is_active_true_non_idle(self):
        """非 idle 时 is_active 为 True"""
        for p in ("explore", "focus", "decompose", "challenge", "finalize", "execute"):
            engine = _make_engine(p)
            self.assertTrue(engine.is_active)

    def test_is_active_false_when_idle(self):
        """idle 时 is_active 为 False"""
        engine = _make_engine("idle")
        self.assertFalse(engine.is_active)

    def test_is_complex_matches_active(self):
        """is_complex 类似 is_active"""
        engine = _make_engine("idle")
        self.assertFalse(engine.is_complex)
        engine = _make_engine("decompose")
        self.assertTrue(engine.is_complex)


# ════════════════════════════════════════════════════
# reset
# ════════════════════════════════════════════════════

class TestReset(unittest.TestCase):
    """reset 方法"""

    def test_reset_sets_idle(self):
        """重置后阶段为 idle"""
        engine = _make_engine("decompose", context={"decompose_completed": True})
        engine.reset()
        self.assertEqual(engine.phase, "idle")
        # 上下文和摘要也清空
        self.assertEqual(engine._state.summary, "")
        self.assertEqual(engine._state.decisions, [])
        self.assertEqual(engine._state.context, {})


# ════════════════════════════════════════════════════
# update_from_conversation 集成
# ════════════════════════════════════════════════════

class TestUpdateFromConversation(unittest.TestCase):
    """update_from_conversation 集成测试"""

    def test_no_transition(self):
        """无转移信号时返回当前阶段"""
        engine = _make_engine("explore")
        result = engine.update_from_conversation("用户消息", "好的回复")
        self.assertFalse(result["transited"])
        self.assertEqual(result["phase"], "explore")
        self.assertEqual(result["content"], "好的回复")

    def test_with_transition_and_strip(self):
        """有转移信号时剥离标记并切换阶段"""
        engine = _make_engine("explore")
        result = engine.update_from_conversation(
            "用户消息",
            "我们已经探索完了。[PHASE:focus]"
        )
        self.assertTrue(result["transited"])
        self.assertEqual(result["phase"], "focus")
        self.assertEqual(result["content"], "我们已经探索完了。")
        self.assertEqual(engine.phase, "focus")


# ════════════════════════════════════════════════════
# load_state 静态方法
# ════════════════════════════════════════════════════

class TestLoadState(unittest.TestCase):
    """load_state 静态方法"""

    def test_load_state_returns_none_when_idle(self):
        """idle 阶段返回 None"""
        state = FakeDialogState(phase="idle")
        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = state
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        result = DialogEngine.load_state(db, "test_scene")
        self.assertIsNone(result)

    def test_load_state_returns_dict_when_active(self):
        """非 idle 阶段返回状态摘要"""
        state = FakeDialogState(
            phase="decompose",
            summary="分解任务",
            decisions=["决策1"],
        )
        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = state
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        result = DialogEngine.load_state(db, "test_scene")
        self.assertIsNotNone(result)
        self.assertEqual(result["phase"], "decompose")
        self.assertEqual(result["summary"], "分解任务")
        self.assertEqual(result["decisions"], ["决策1"])


# ════════════════════════════════════════════════════
# 正则表达式测试
# ════════════════════════════════════════════════════

class TestTransitionRegex(unittest.TestCase):
    """PHASE_TRANSITION_RE 正则"""

    def test_match_standard(self):
        """标准格式匹配"""
        m = PHASE_TRANSITION_RE.search("[PHASE:focus]")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "focus")

    def test_match_with_spaces(self):
        """含空格格式匹配"""
        m = PHASE_TRANSITION_RE.search("[PHASE: focus]")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "focus")

    def test_match_with_trailing_spaces(self):
        """尾部空格匹配"""
        m = PHASE_TRANSITION_RE.search("[PHASE:focus ]")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "focus")

    def test_no_match_without_brackets(self):
        """无方括号不匹配"""
        self.assertIsNone(PHASE_TRANSITION_RE.search("PHASE:focus"))

    def test_match_only_first(self):
        """多个标记只匹配第一个"""
        m = PHASE_TRANSITION_RE.search("[PHASE:focus] and [PHASE:execute]")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "focus")


if __name__ == "__main__":
    unittest.main()
