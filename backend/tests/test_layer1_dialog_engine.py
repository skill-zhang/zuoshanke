"""
Layer 1-B2: DialogEngine 状态机核心逻辑测试

测试目标：覆盖 transition_to() 的每一行实际代码逻辑，包括：
  - 阶段转移（正常/回退/跳阶段）
  - decompose 前置条件
  - 决策追加与合并
  - DB 持久化
  - 状态恢复
"""
import pytest
from unittest.mock import MagicMock, patch


# ── 测试用 DB 引擎 ──
@pytest.fixture(scope="module")
def tables():
    """确保 dialog_states 表存在"""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from database import engine, Base
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield
    # 不清理，由 conftest 的 _db_cleanup 处理


@pytest.fixture
def db(tables):
    """每个测试一个独立 DB session"""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from database import SessionLocal
    from sqlalchemy import text as sa_text
    db = SessionLocal()
    yield db
    # 清理 dialog_states
    try:
        db.execute(sa_text("DELETE FROM dialog_states"))
        db.commit()
    except Exception:
        pass
    db.close()


@pytest.fixture
def engine(db):
    """DialogEngine 实例（新场景，自动创建 idle）"""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from agent_core.dialog_engine import DialogEngine
    eng = DialogEngine(db, "test_scene_dialog")
    return eng


@pytest.fixture
def engine_explore(db):
    """DialogEngine 实例，已迁移到 explore"""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from agent_core.dialog_engine import DialogEngine
    eng = DialogEngine(db, "scene_explore")
    eng.transition_to("explore", summary="进入探索")
    return eng


@pytest.fixture
def engine_decomposed(db):
    """已进入 decompose 且 decompose_completed=True 的场景"""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from agent_core.dialog_engine import DialogEngine
    eng = DialogEngine(db, "scene_decomposed")
    eng.transition_to("explore")
    eng.transition_to("focus")
    eng.transition_to("decompose", context={"plan": "拆分步骤"})
    return eng


# ═══════════════════════════════════════════════════════
# 构造函数与状态加载
# ═══════════════════════════════════════════════════════

class TestConstructor:
    """基础构造与状态加载"""

    def test_new_scene_creates_idle(self, db):
        """新场景 → 自动创建 phase=idle"""
        from agent_core.dialog_engine import DialogEngine
        eng = DialogEngine(db, "new_scene")
        assert eng.phase == "idle"
        assert eng.is_active is False
        assert eng.is_complex is False

    def test_existing_scene_loads_state(self, db):
        """已有状态 → 恢复之前的 phase"""
        from agent_core.dialog_engine import DialogEngine
        eng1 = DialogEngine(db, "existing_scene")
        eng1.transition_to("focus", summary="已有记录")
        eng1.db.flush()

        eng2 = DialogEngine(db, "existing_scene")
        assert eng2.phase == "focus"
        assert eng2.is_active is True


# ═══════════════════════════════════════════════════════
# detect_transition — 阶段信号检测
# ═══════════════════════════════════════════════════════

class TestDetectTransition:
    """阶段转移信号检测的各种边界"""

    def test_no_marker_returns_none(self, engine):
        assert engine.detect_transition("普通回复") is None

    def test_empty_content_returns_none(self, engine):
        assert engine.detect_transition("") is None
        assert engine.detect_transition(None) is None

    def test_forward_from_idle(self, engine):
        """idle → explore: 允许"""
        assert engine.detect_transition("[PHASE:explore] 开始") == "explore"

    def test_skip_ahead_allowed(self, engine_explore):
        """explore → challenge: 跳阶段允许"""
        assert engine_explore.detect_transition("[PHASE:challenge] 直接挑战") == "challenge"

    def test_backward_blocked(self, engine_explore):
        """explore → idle: 回退不允许"""
        assert engine_explore.detect_transition("[PHASE:idle] 回去") is None

    def test_same_phase_blocked(self, engine_explore):
        """explore → explore: 相同阶段不允许"""
        assert engine_explore.detect_transition("[PHASE:explore] 继续探索") is None

    def test_invalid_phase_name(self, engine):
        """无效阶段名 → None"""
        assert engine.detect_transition("[PHASE:nonexistent] 不存在") is None

    def test_case_insensitive(self, engine):
        """大小写不敏感"""
        assert engine.detect_transition("[phase:explore] 小写") == "explore"
        assert engine.detect_transition("[Phase:Explore] 混写") == "explore"

    def test_marker_in_middle_of_text(self, engine):
        """标记在文本中间"""
        assert engine.detect_transition("我分析完了[PHASE:focus]聚焦") == "focus"

    def test_execute_without_decompose_blocked(self, engine_focus):
        """未经过 decompose 不能进入 execute"""
        result = engine_focus.detect_transition("[PHASE:execute] 执行")
        assert result is None, "跳过 decompose 应被阻止"

    def test_execute_after_decompose_allowed(self, engine_decomposed):
        """经过 decompose 后能进入 execute"""
        result = engine_decomposed.detect_transition("[PHASE:execute] 执行")
        assert result == "execute", "经过 decompose 后应允许进入 execute"


@pytest.fixture
def engine_focus(db):
    """在 focus 阶段（未 decompose）"""
    from agent_core.dialog_engine import DialogEngine
    eng = DialogEngine(db, "scene_focus")
    eng.transition_to("explore")
    eng.transition_to("focus")
    return eng


# ═══════════════════════════════════════════════════════
# strip_transition_marker
# ═══════════════════════════════════════════════════════

class TestStripTransitionMarker:
    """标记剥离"""

    def test_removes_marker(self, engine):
        assert engine.strip_transition_marker("[PHASE:explore] 你好") == "你好"

    def test_no_marker(self, engine):
        assert engine.strip_transition_marker("普通回复") == "普通回复"

    def test_multiple_markers(self, engine):
        """多个标记全部剥离"""
        result = engine.strip_transition_marker("[PHASE:explore] 分析[PHASE:focus] 聚焦")
        assert "[PHASE:" not in result
        assert "分析" in result
        assert "聚焦" in result

    def test_empty_content(self, engine):
        assert engine.strip_transition_marker("") == ""


# ═══════════════════════════════════════════════════════
# transition_to — 状态转移（核心）
# ═══════════════════════════════════════════════════════

class TestTransitionTo:
    """阶段转移执行"""

    def test_transition_to_valid_phase(self, engine):
        """有效阶段 → True, phase 更新"""
        assert engine.transition_to("explore") is True
        assert engine.phase == "explore"

    def test_transition_to_invalid_phase(self, engine):
        """无效阶段 → False, phase 不变"""
        assert engine.transition_to("invalid_phase") is False
        assert engine.phase == "idle"

    def test_transition_updates_summary(self, engine):
        """传递 summary → 持久化"""
        engine.transition_to("explore", summary="讨论了用户需求")
        assert engine._state.summary == "讨论了用户需求"

    def test_transition_appends_decisions(self, engine):
        """首次添加决策"""
        engine.transition_to("explore", decisions=["明确目标"])
        assert "明确目标" in (engine._state.decisions or [])

    def test_transition_merges_decisions(self, engine):
        """多次添加决策：新决策排在前面"""
        engine.transition_to("explore", decisions=["第一轮决策"])
        engine.transition_to("focus", decisions=["第二轮决策"])
        dec = engine._state.decisions or []
        assert dec[0] == "第二轮决策", f"新决策应在前面: {dec}"
        assert dec[1] == "第一轮决策", f"旧决策应在后面: {dec}"

    def test_transition_merges_new_context(self, engine):
        """传递 context → 合并到已有 context"""
        engine.transition_to("explore", context={"key1": "val1"})
        engine.transition_to("focus", context={"key2": "val2"})
        ctx = engine._state.context or {}
        assert ctx["key1"] == "val1"
        assert ctx["key2"] == "val2"

    def test_transition_preserves_existing_context(self, engine):
        """新 context 不覆盖旧 context"""
        engine.transition_to("explore", context={"key1": "val1"})
        engine.transition_to("focus", context={"key2": "val2"})
        ctx = engine._state.context or {}
        assert ctx["key1"] == "val1"

    def test_decompose_sets_flag(self, engine):
        """进入 decompose → context.decompose_completed=True"""
        engine.transition_to("explore")
        engine.transition_to("focus")
        engine.transition_to("decompose")
        ctx = engine._state.context or {}
        assert ctx.get("decompose_completed") is True

    def test_transition_updates_updated_at(self, engine):
        """转移后 updated_at 更新"""
        old = engine._state.updated_at
        import time
        time.sleep(0.01)
        engine.transition_to("explore")
        assert engine._state.updated_at != old, "转移后 updated_at 应更新"


# ═══════════════════════════════════════════════════════
# reset
# ═══════════════════════════════════════════════════════

class TestReset:
    """重置到 idle"""

    def test_reset_sets_idle(self, engine):
        engine.transition_to("explore", summary="有历史", decisions=["决定"])
        engine.reset()
        assert engine.phase == "idle"
        assert engine._state.summary == ""
        assert engine._state.decisions == []
        assert engine._state.context == {}


# ═══════════════════════════════════════════════════════
# update_from_conversation
# ═══════════════════════════════════════════════════════

class TestUpdateFromConversation:
    """完整会话更新"""

    def test_no_transition(self, engine):
        """无标记 → transited=False"""
        result = engine.update_from_conversation("你好", "我很好")
        assert result["transited"] is False
        assert result["phase"] == "idle"
        assert result["content"] == "我很好"

    def test_with_transition_and_strip(self, engine):
        """有标记 → transited=True, 内容已剥离"""
        result = engine.update_from_conversation("我们来探索", "[PHASE:explore] 好的开始探索")
        assert result["transited"] is True
        assert result["phase"] == "explore"
        assert "[PHASE:" not in result["content"]
        assert "好的开始探索" in result["content"]

    def test_strip_removes_only_marker(self, engine):
        """不会影响标记外的其他格式"""
        result = engine.update_from_conversation("测试", "回复内容[PHASE:explore] 包含普通文本\n**加粗**")
        assert "**加粗**" in result["content"]
        assert "[PHASE:" not in result["content"]


# ═══════════════════════════════════════════════════════
# load_state — 静态加载
# ═══════════════════════════════════════════════════════

class TestLoadState:
    """跨会话状态恢复"""

    def test_load_state_returns_dict_when_active(self, db):
        """非 idle → 返回状态 dict"""
        from agent_core.dialog_engine import DialogEngine
        eng = DialogEngine(db, "load_active")
        eng.transition_to("focus", summary="聚焦记录", decisions=["决策1"])

        state = DialogEngine.load_state(db, "load_active")
        assert state is not None
        assert state["phase"] == "focus"
        assert "聚焦记录" in state["summary"]
        assert "决策1" in state["decisions"]

    def test_load_state_returns_none_when_idle(self, db):
        """idle → None"""
        from agent_core.dialog_engine import DialogEngine
        DialogEngine(db, "load_idle")  # 创建但未转移
        state = DialogEngine.load_state(db, "load_idle")
        assert state is None

    def test_load_state_returns_none_when_not_exist(self, db):
        """不存在 → None"""
        from agent_core.dialog_engine import DialogEngine
        state = DialogEngine.load_state(db, "nonexistent")
        assert state is None
