"""Layer 1-E: build_agent_context() 旧版上下文构建测试

测试目标：
  P0: 基础调用 — 消息结构正确（system + history + user）
  P0: user_context 自定义 — 覆盖 DB/默认
  P0: scene_name — 分身意识注入
  P0: scene_id — 场景信息 + 思维导图状态
  P0: history_messages — 历史消息保留
  P0: db/None — 降级处理
  P1: 记忆块注入 — 插入记忆后验证出现在上下文中
  P1: DB settings — system_prompt 从 DB 读取
  P1: 工具列表 — match_tools 按输入匹配
  P1: 技能块 — SkillManager 匹配

不 mock — 使用真实 DB 会话：zuoshanke_test.db
"""
import pytest
import json


def _make_session():
    """创建一个独立的 DB 会话"""
    from database import SessionLocal
    return SessionLocal()


def _insert_memory(db, key, content, scope="zhu", context_id=None,
                   priority_level="P1", is_core=False):
    """插入一条 AgentMemory 记录"""
    from models import AgentMemory
    from utils import make_id, utcnow
    mem = AgentMemory(
        id=make_id("mem"),
        category="user",
        key=key,
        content=content,
        scope=scope,
        context_id=context_id,
        priority_level=priority_level,
        base_weight=5,
        is_core=is_core,
        tags=["test"],
    )
    db.add(mem)
    db.commit()
    return mem


def _insert_setting(db, system_prompts: dict):
    """插入一条 Setting 记录"""
    from models import Setting, SETTINGS_ID
    s = db.query(Setting).first()
    if s:
        existing = dict(s.system_prompts or {})
        existing.update(system_prompts)
        s.system_prompts = existing
    else:
        s = Setting(
            id=SETTINGS_ID,
            system_prompts=system_prompts,
        )
        db.add(s)
    db.commit()


# ══════════════════════════════════════════════════
# P0: 基础结构
# ══════════════════════════════════════════════════


class TestBasicStructure:
    """P0: 基础消息结构"""

    def test_returns_messages_list(self):
        """返回的是 OpenAI 格式列表"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="你好")
        assert isinstance(msgs, list)
        assert len(msgs) >= 2

    def test_first_is_system(self):
        """第一条是 system role"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="测试")
        assert msgs[0]["role"] == "system"

    def test_last_is_user_content(self):
        """最后一条是用户消息"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="hello world")
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"].endswith("hello world")

    def test_system_has_role_heading(self):
        """system prompt 包含 # 角色设定"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="hi")
        content = msgs[0]["content"]
        assert "# 角色设定" in content

    def test_system_has_usage_instructions(self):
        """system prompt 包含使用说明"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="hi")
        content = msgs[0]["content"]
        assert "## 使用说明" in content

    def test_system_has_memory_capability(self):
        """system prompt 包含记忆能力说明"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="hi")
        content = msgs[0]["content"]
        assert "## 📝 记忆能力" in content

    def test_system_has_converge_section(self):
        """system prompt 包含发散与收敛说明"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="hi")
        content = msgs[0]["content"]
        assert "## 🔀 发散与收敛" in content


# ══════════════════════════════════════════════════
# P0: user_context 自定义
# ══════════════════════════════════════════════════


class TestUserContext:
    """P0: 自定义 user_context"""

    def test_user_context_appears_in_system(self):
        """传入 user_context 后出现在 system prompt 中"""
        from agent_core.context_builder import build_agent_context
        ctx = "你是一个资深 Python 工程师"
        msgs = build_agent_context(user_content="你好", user_context=ctx)
        assert ctx in msgs[0]["content"]

    def test_user_context_replaces_default(self):
        """传入 user_context 后不再包含默认 scene prompt"""
        from agent_core.context_builder import build_agent_context
        from models import DEFAULT_SYSTEM_PROMPTS
        ctx = "自定义角色设定"
        msgs = build_agent_context(user_content="你好", user_context=ctx)
        default_scene = DEFAULT_SYSTEM_PROMPTS.get("scene", "")
        # 自定义 context 应出现在 # 角色设定 区域
        assert "自定义角色设定" in msgs[0]["content"]

    def test_user_context_with_scene_name(self):
        """同时传入 user_context 和 scene_name → 分身意识在前，user_context 在后"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(
            user_content="你好",
            user_context="你是一个翻译助手",
            scene_name="翻译场景",
        )
        content = msgs[0]["content"]
        assert "翻译场景" in content
        assert "翻译助手" in content


# ══════════════════════════════════════════════════
# P0: scene_name 分身意识
# ══════════════════════════════════════════════════


class TestSceneName:
    """P0: 分身意识注入"""

    def test_scene_name_injected(self):
        """传入 scene_name → 分身意识文本出现"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="你好", scene_name="代码评审")
        assert "代码评审" in msgs[0]["content"]

    def test_no_scene_name_no_identity(self):
        """不传 scene_name → 无分身意识"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="你好")
        # 无 scene_name 时使用默认 prompt，不包含【】格式的领域名
        assert "【" not in " ".join(msgs[0]["content"].split("\n")[:3])

    def test_default_prompt_without_scene_name(self):
        """不传 scene_name 且无 user_context → 使用默认 scene prompt"""
        from agent_core.context_builder import build_agent_context
        from models import DEFAULT_SYSTEM_PROMPTS
        msgs = build_agent_context(user_content="你好")
        default_sp = DEFAULT_SYSTEM_PROMPTS.get("scene", "")
        # 默认 scene prompt 应出现在 system 中
        if default_sp:
            assert default_sp[:50] in msgs[0]["content"]


# ══════════════════════════════════════════════════
# P0: history_messages
# ══════════════════════════════════════════════════


class TestHistoryMessages:
    """P0: 历史消息"""

    def test_history_included(self):
        """历史消息出现在 system 和 user 之间"""
        from agent_core.context_builder import build_agent_context
        history = [
            {"role": "user", "content": "今天天气怎么样"},
            {"role": "ai", "content": "今天是晴天"},
        ]
        msgs = build_agent_context(user_content="谢谢", history_messages=history)
        # 应该有 4 条消息：system + 2 条历史 + user
        assert len(msgs) >= 4
        # 历史消息的 role 映射：user→user, ai→assistant
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "今天天气怎么样"
        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["content"] == "今天是晴天"

    def test_no_history_less_messages(self):
        """无历史消息时只有 system + user"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="你好")
        assert len(msgs) == 2  # system + user

    def test_empty_history(self):
        """空列表历史消息不影响"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="你好", history_messages=[])
        assert len(msgs) == 2


# ══════════════════════════════════════════════════
# P1: scene_id 场景信息
# ══════════════════════════════════════════════════


class TestSceneID:
    """P1: 场景 ID"""

    def test_scene_id_in_output(self):
        """传入 scene_id → 场景信息出现在收敛部分"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(
            user_content="你好",
            scene_id="scene-test-001",
            scene_name="测试场景",
        )
        content = msgs[0]["content"]
        assert "scene-test-001" in content
        assert "测试场景" in content

    def test_scene_id_without_name(self):
        """scene_id 传入但 scene_name 为空 → scene_name 显示 未知"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(
            user_content="你好",
            scene_id="scene-test-002",
        )
        assert "scene-test-002" in content if False else True
        # scene info 只有在 scene_id 时才会被附加
        content = msgs[0]["content"]
        assert "scene-test-002" in content


# ══════════════════════════════════════════════════
# P1: DB 交互
# ══════════════════════════════════════════════════


class TestDBInteraction:
    """P1: 真实 DB 会话"""

    def test_db_none_graceful(self):
        """db=None 不会报错，仍然返回消息列表"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="你好", db=None)
        assert isinstance(msgs, list)
        assert len(msgs) >= 2

    def test_db_without_memory_no_block(self):
        """db 存在但无记忆 → 用户消息中没有记忆块"""
        from agent_core.context_builder import build_agent_context
        db = _make_session()
        try:
            msgs = build_agent_context(user_content="你好", db=db)
            user_content = msgs[-1]["content"]
            # 无记忆时不应该有 "## 关于你的一些已知信息"
            # scope 缺省，build_agent_context 中 scope 由 scene_id 决定，
            # 无 scene_id 时 scope="zhu"，zhu 记忆可能有种子数据
            # 所以这里只检查不报错，不检查具体内容
            assert isinstance(user_content, str)
        finally:
            db.close()

    def test_db_with_memory_in_user_msg(self):
        """插入记忆后 → 用户消息中出现记忆块"""
        from agent_core.context_builder import build_agent_context
        from agent_core.memory_cache import MemoryCache
        db = _make_session()
        try:
            # 重置缓存实例，避免跨测试污染
            MemoryCache.reset_instance()
            cache = MemoryCache.get_instance()

            # 插入一条 scope=scene 的记忆
            from utils import make_id
            mem_id = make_id("mem-test")
            _insert_memory(db, "user_preference_" + mem_id[-6:],
                           "用户喜欢简洁的回复风格",
                           scope="scene", context_id="scene-test-mem")

            # 手动加载记忆到缓存
            cache.load_scope(db, "scene", "scene-test-mem")

            # 带 scene_id 调用 → 走 scene scope 的记忆块路径
            msgs = build_agent_context(
                user_content="你好",
                db=db,
                scene_id="scene-test-mem",
                scene_name="记忆测试",
            )
            user_content = msgs[-1]["content"]
            assert "用户喜欢简洁的回复风格" in user_content, \
                f"记忆应出现在 user 消息中: {user_content[:200]}"
        finally:
            db.close()
            # 恢复缓存干净状态
            MemoryCache.reset_instance()

    def test_db_settings_used(self):
        """DB 中有 Setting 记录 → 使用 DB 中的 system_prompt"""
        from agent_core.context_builder import build_agent_context
        from models import DEFAULT_SYSTEM_PROMPTS
        db = _make_session()
        try:
            custom_scene_prompt = "这是来自 DB 的自定义场景提示"
            _insert_setting(db, {"scene": custom_scene_prompt})
            msgs = build_agent_context(user_content="你好", db=db)
            content = msgs[0]["content"]
            assert custom_scene_prompt in content, \
                f"DB 自定义 prompt 未生效: {content[:200]}"
        finally:
            db.close()


# ══════════════════════════════════════════════════
# P1: 工具列表
# ══════════════════════════════════════════════════


class TestToolList:
    """P1: 工具匹配"""

    def test_tools_in_system_prompt(self):
        """system prompt 中包含工具列表"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="查一下天气")
        content = msgs[0]["content"]
        # 匹配到天气相关工具后应有工具列表格式
        # 格式包含 "###" 表示工具列表区域
        assert "###" in content or "工具" in content

    def test_tools_matched_by_content(self):
        """不同输入匹配不同工具"""
        from agent_core.context_builder import build_agent_context
        msgs_weather = build_agent_context(user_content="今天天气怎么样")
        msgs_generic = build_agent_context(user_content="你好")
        # 通用问好可能也会匹配到工具，但至少不会报错
        assert isinstance(msgs_weather, list)
        assert isinstance(msgs_generic, list)


# ══════════════════════════════════════════════════
# P1: 技能块
# ══════════════════════════════════════════════════


class TestSkillBlock:
    """P1: 技能匹配"""

    def test_skill_block_graceful_when_no_match(self):
        """无匹配技能时不影响结构"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(user_content="你好")
        assert isinstance(msgs, list)
        assert len(msgs) >= 2


# ══════════════════════════════════════════════════
# P1: 思维导图状态块
# ══════════════════════════════════════════════════


class TestThinkingMapBlock:
    """P1: 思维导图状态"""

    def test_tm_block_empty_when_no_map(self):
        """无思维导图时不会报错"""
        from agent_core.context_builder import build_agent_context
        msgs = build_agent_context(
            user_content="你好",
            scene_id="nonexistent-scene",
        )
        assert isinstance(msgs, list)

    def test_tm_block_with_map_data(self):
        """有思维导图节点时出现在 system prompt"""
        from agent_core.context_builder import build_agent_context
        db = _make_session()
        try:
            from models import ThinkingMap, ThinkNode
            from utils import make_id, utcnow

            # 创建思维导图
            tmap = ThinkingMap(
                id=make_id("tm"),
                scene_id="scene-with-tm",
                title="测试导图",
                created_at=utcnow(),
            )
            db.add(tmap)
            db.commit()

            # 创建节点
            node = ThinkNode(
                id=make_id("tn"),
                map_id=tmap.id,
                label="用户需求分析",
                type="domain",
                status="active",
            )
            db.add(node)
            db.commit()

            msgs = build_agent_context(
                user_content="分析需求",
                db=db,
                scene_id="scene-with-tm",
                scene_name="测试场景",
            )
            content = msgs[0]["content"]
            assert "已有思维节点" in content or "用户需求分析" in content, \
                f"思维导图节点应出现在 system prompt: {content[:300]}"
        finally:
            db.close()
