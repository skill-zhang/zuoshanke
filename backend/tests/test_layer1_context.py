"""
Layer 1-D: Context Composer — 8 层上下文构建测试

测试目标：verify compose_context() 的每一层输出格式正确、关键逻辑生效。
不 mock DB，使用真实数据库会话（zuoshanke_test.db）验证完整链路。
"""
import pytest
from fastapi.testclient import TestClient


# ── 辅助 ──

def _count_layer(msg: str, header: str) -> bool:
    """检查消息中是否包含指定层 header"""
    return header in msg


def _layer_content(messages: list[dict], keyword: str) -> list[str]:
    """提取包含特定关键字的层内容"""
    return [m["content"] for m in messages if keyword in m.get("content", "")]


# ═══════════════════════════════════════════════════════
# 1. 整体结构 — 8 层是否都存在
# ═══════════════════════════════════════════════════════

class TestComposeContextStructure:
    """验证 8 层上下文的整体结构"""

    def test_returns_messages_list(self):
        """返回的是 OpenAI 格式消息列表"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="你好", scene_id="")
        assert isinstance(msgs, list)
        assert len(msgs) >= 2  # 至少 system + user

    def test_first_message_is_system(self):
        """第一条消息是 system role"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="你好", scene_id="")
        assert msgs[0]["role"] == "system"

    def test_last_message_is_user_content(self):
        """最后一条消息是用户输入"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="这是一条测试消息", scene_id="")
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "这是一条测试消息"

    def test_with_scene_name_has_scene_info(self):
        """带 scene_name → system prompt 包含场景名称"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="hi", scene_id="scene-test", scene_name="测试场景")
        system = msgs[0]["content"]
        assert "测试场景" in system, f"system prompt 应包含场景名: {system[:200]}"

    def test_multiple_layers_are_separate_messages(self):
        """各层作为独立 message，而非合并到 system"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="测试", scene_id="scene-layers")
        roles = [m["role"] for m in msgs]
        # 至少 system + 若干 user 层 + 最终 user
        user_layers = [r for r in roles if r == "user"]
        assert len(user_layers) >= 2, f"应有多层 user role: {roles}"


# ═══════════════════════════════════════════════════════
# 2. Prompt Layer — 系统提示
# ═══════════════════════════════════════════════════════

class TestPromptLayer:
    """Layer 1: system prompt"""

    def test_contains_role_heading(self):
        """包含 # 角色设定"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="hi", scene_id="scene-p1")
        assert "# 角色设定" in msgs[0]["content"]

    def test_contains_usage_instructions(self):
        """包含使用说明"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="hi", scene_id="scene-p2")
        assert "## 使用说明" in msgs[0]["content"]

    def test_contains_memory_instructions(self):
        """包含记忆能力说明"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="hi", scene_id="scene-p3")
        assert "## 📝 记忆体系" in msgs[0]["content"]

    def test_contains_honesty_principle(self):
        """包含诚实原则"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="hi", scene_id="scene-p4")
        assert "诚实与不确定" in msgs[0]["content"]

    def test_no_scene_name_uses_generic_role(self):
        """无 scene_name → 通用角色设定"""
        from agent_core.context_composer import compose_context
        msgs = compose_context(user_content="hi", scene_id="")
        assert "智能助手" in msgs[0]["content"]


# ═══════════════════════════════════════════════════════
# 3. Memory Layer — 持久记忆
# ═══════════════════════════════════════════════════════

class TestMemoryLayer:
    """Layer 2: 持久记忆"""

    def test_memory_layer_format(self, client: TestClient):
        """写入记忆后 → memory layer 包含记忆内容"""
        # 先写一条记忆
        client.post("/api/memory", json={
            "category": "user",
            "key": "ctx_test_key",
            "content": "上下文构建测试记忆",
        })

        from agent_core.context_composer import compose_context
        from agent_core.memory_cache import MemoryCache
        from database import SessionLocal
        db = SessionLocal()
        try:
            # 初始化 MemoryCache（预热本体记忆）
            MemoryCache.get_instance().initialize(db)
            msgs = compose_context(user_content="测试记忆测试", scene_id="", db=db)
            # memory layer 是 user role 消息
            user_msgs = [m["content"] for m in msgs if m["role"] == "user"]
            user_text = " ".join(user_msgs)
            assert "ctx_test_key" in user_text or "上下文构建测试记忆" in user_text, \
                f"记忆应出现在 user 层消息中，共 {len(user_msgs)} 条 user 消息"
        finally:
            db.close()


# ═══════════════════════════════════════════════════════
# 4. History Layer — 优先级排序
# ═══════════════════════════════════════════════════════

class TestHistoryLayer:
    """Layer 7: 历史消息优先级排序"""

    def test_high_priority_first(self):
        """high 优先级的消息排在 normal 之前"""
        from agent_core.context_composer import _build_history_layer
        history = [
            {"role": "user", "content": "normal消息", "priority": "normal"},
            {"role": "ai", "content": "high消息", "priority": "high"},
        ]
        result = _build_history_layer(history)
        content_order = [m["content"] for m in result]
        high_idx = content_order.index("high消息")
        normal_idx = content_order.index("normal消息")
        assert high_idx < normal_idx, "high 应在 normal 之前"

    def test_low_compressed_to_system(self):
        """low 优先级被合并为一条 system 消息"""
        from agent_core.context_composer import _build_history_layer
        history = [
            {"role": "user", "content": "低优先级1", "priority": "low"},
            {"role": "ai", "content": "低优先级2", "priority": "low"},
        ]
        result = _build_history_layer(history)
        # low 消息被合并为一条 system
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1, f"low 应合并为一条 system: {result}"
        assert "低优先级1" in system_msgs[0]["content"]
        assert "低优先级2" in system_msgs[0]["content"]

    def test_messages_preserved_in_priority_order(self):
        """high → normal → low, 每种组内保留原顺序"""
        from agent_core.context_composer import _build_history_layer
        history = [
            {"role": "user", "content": "普通1", "priority": "normal"},
            {"role": "user", "content": "低1", "priority": "low"},
            {"role": "ai", "content": "高1", "priority": "high"},
            {"role": "user", "content": "普通2", "priority": "normal"},
        ]
        result = _build_history_layer(history)
        roles_content = [(m["role"], m["content"]) for m in result]
        # high 在前
        assert ("ai", "高1") in roles_content[:2]
        # normal 在中间
        assert ("user", "普通1") in roles_content[1:4]
        assert ("user", "普通2") in roles_content[1:4]


# ═══════════════════════════════════════════════════════
# 5. Profile Layer — 用户画像
# ═══════════════════════════════════════════════════════

class TestProfileLayer:
    """Layer 3: 用户画像"""

    def test_no_profiles_returns_empty(self):
        """profile 表为空 → 空字符串"""
        from agent_core.context_composer import _build_profile_layer
        result = _build_profile_layer(db=None, user_content="test")
        assert result == ""

    def test_keyword_extraction(self):
        """_extract_keywords 提取关键词（整句去重）"""
        from agent_core.context_composer import _extract_keywords
        keywords = _extract_keywords("我喜欢编程和机器学习")
        assert len(keywords) >= 1
        assert any("编程" in kw for kw in keywords), f"关键词应包含编程: {keywords}"

    def test_empty_text_returns_empty_list(self):
        from agent_core.context_composer import _extract_keywords
        assert _extract_keywords("") == []


# ═══════════════════════════════════════════════════════
# 6. Work Output Layer — 文件快照
# ═══════════════════════════════════════════════════════

class TestWorkOutputLayer:
    """Layer 8: 最近操作记录"""

    def test_no_scene_id_returns_empty(self):
        from agent_core.context_composer import _build_work_output_layer
        result = _build_work_output_layer(scene_id="", db=None, window=3)
        assert result == ""

    def test_no_snapshots_returns_empty(self):
        """存在场景但无快照 → 空"""
        from agent_core.context_composer import _build_work_output_layer
        from database import SessionLocal
        db = SessionLocal()
        try:
            result = _build_work_output_layer(scene_id="nonexistent_999", db=db, window=3)
            assert result == ""
        finally:
            db.close()
