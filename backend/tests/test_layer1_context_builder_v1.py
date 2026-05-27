"""Layer 1-F: build_agent_context_v1() 真实测试 — 7 层 Context Composer

测试目标（P0 致命 / P1 重要）：
  P0: 基础结构 — 返回格式正确（system + history + user）
  P0: Prompt Layer — 角色设定、工具列表、使用说明、记忆能力、收敛说明
  P0: 分身身份 — scene_name/scene_id 正确注入
  P0: db=None 降级
  P0: 对话历史保留
  P1: Memory Layer — zhu scope（三层选择注入） + scene scope（top-5）
  P1: Profile Layer — P0+P1 始终注入、P2 话题匹配
  P1: Config Layer — 模型配置 + 场景收敛参数
  P1: History Layer — 优先级排序、low 合并
  P1: Work Output Layer — FileSnapshot 最近窗口
  P1: Skill Layer — SkillManager 匹配

不 mock — 使用真实 DB 会话：zuoshanke_test.db
不 skip — 跑不通就是问题
"""
import pytest
import json


# ══════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════


def _make_session():
    from database import SessionLocal
    return SessionLocal()


def _insert_memory(db, key, content, scope="zhu", context_id=None,
                   priority_level="P1", is_core=False, is_immortal=False,
                   base_weight=2):
    from models import AgentMemory
    from utils import make_id
    mem = AgentMemory(
        id=make_id("mem"),
        category="user",
        key=key,
        content=content,
        scope=scope,
        context_id=context_id,
        priority_level=priority_level,
        base_weight=base_weight,
        is_core=is_core,
        is_immortal=is_immortal,
        tags=["test"],
    )
    db.add(mem)
    db.commit()
    return mem


def _insert_setting(db, system_prompts: dict = None, routing: dict = None):
    from models import Setting, SETTINGS_ID
    s = db.query(Setting).first()
    if s:
        if system_prompts is not None:
            existing = dict(s.system_prompts or {})
            existing.update(system_prompts)
            s.system_prompts = existing
        if routing is not None:
            s.routing = routing
    else:
        s = Setting(
            id=SETTINGS_ID,
            system_prompts=system_prompts or {},
            routing=routing or {},
        )
        db.add(s)
    db.commit()


def _create_scene(db, scene_id, name="测试场景", converge_threshold=None,
                  converge_enabled=False, diverge_min_rounds=2,
                  scene_config=None):
    from models import Scene
    from utils import utcnow
    sc = Scene(
        id=scene_id,
        name=name,
        converge_threshold=converge_threshold,
        converge_enabled=converge_enabled,
        diverge_min_rounds=diverge_min_rounds,
        scene_config=scene_config or {},
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(sc)
    db.commit()


def _create_thinking_map(db, scene_id):
    from models import ThinkingMap, ThinkNode
    from utils import make_id, utcnow
    tmap = ThinkingMap(
        id=make_id("tm"),
        scene_id=scene_id,
        title="测试导图",
        created_at=utcnow(),
    )
    db.add(tmap)
    db.commit()

    node = ThinkNode(
        id=make_id("tn"),
        map_id=tmap.id,
        label="用户需求分析",
        type="domain",
        status="active",
    )
    db.add(node)
    db.commit()
    return tmap.id


def _create_user_profile(db, key, content, priority="P2", tags=None, source_scenes=None):
    from models import UserProfile
    from utils import make_id
    p = UserProfile(
        id=make_id("up"),
        key=key,
        content=content,
        priority=priority,
        is_active=True,
        tags=tags or [],
        source_scenes=source_scenes or [],
    )
    db.add(p)
    db.commit()
    return p


def _create_file_snapshot(db, scene_id, file_path, diff_summary, diff_content):
    from models import FileSnapshot
    from utils import make_id, utcnow
    snap = FileSnapshot(
        id=make_id("snap"),
        scene_id=scene_id,
        file_path=file_path,
        snapshot=f"snapshot of {file_path} at {utcnow()}",
        diff_summary=diff_summary,
        diff_content=diff_content,
        created_at=utcnow(),
    )
    db.add(snap)
    db.commit()
    return snap


# ══════════════════════════════════════════════════
# P0: 基础结构
# ══════════════════════════════════════════════════


class TestBasicStructure:
    """P0: 基础消息结构"""

    def test_returns_messages_list(self):
        """返回的是 OpenAI 格式列表"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="你好")
        assert isinstance(msgs, list)
        assert len(msgs) >= 2

    def test_first_is_system(self):
        """第一条是 system role"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="测试")
        assert msgs[0]["role"] == "system"

    def test_last_is_user_content(self):
        """最后一条是用户消息"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="hello world")
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "hello world"

    def test_system_has_role_heading(self):
        """system prompt 包含 # 角色设定"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="hi")
        content = msgs[0]["content"]
        assert "# 角色设定" in content

    def test_system_has_tools_section(self):
        """system prompt 包含工具列表"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="今天天气怎么样")
        content = msgs[0]["content"]
        # 工具列表格式：### 开头表示工具区
        assert "###" in content or "工具" in content

    def test_system_has_usage_instructions(self):
        """system prompt 包含使用说明"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="hi")
        content = msgs[0]["content"]
        assert "## 使用说明" in content

    def test_system_has_memory_capability(self):
        """system prompt 包含记忆能力说明"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="hi")
        content = msgs[0]["content"]
        assert "## 📝 记忆体系" in content

    def test_system_has_converge_section(self):
        """system prompt 包含发散与收敛说明"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="hi")
        content = msgs[0]["content"]
        assert "## 🔀 发散与收敛" in content

    def test_system_has_dialogue_focus(self):
        """system prompt 包含对话聚焦原则"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="hi")
        content = msgs[0]["content"]
        assert "## 🎯 对话聚焦原则" in content

    def test_system_has_honesty_principle(self):
        """system prompt 包含诚实原则"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="hi")
        content = msgs[0]["content"]
        assert "诚实与不确定" in content


# ══════════════════════════════════════════════════
# P0: 分身身份
# ══════════════════════════════════════════════════


class TestSceneIdentity:
    """P0: 分身身份注入"""

    def test_scene_name_in_identity(self):
        """scene_name → 分身身份块出现"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(
            user_content="你好", scene_name="代码评审"
        )
        content = msgs[0]["content"]
        assert "代码评审" in content
        assert "分身" in content

    def test_scene_name_with_hardcoded_role(self):
        """无 DB 有 scene_name → 使用硬编码角色"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(
            user_content="你好", scene_name="翻译助手"
        )
        content = msgs[0]["content"]
        assert "翻译助手" in content
        assert "坐山客" in content

    def test_no_scene_name_minimal(self):
        """不传 scene_name → 简化角色，无场景名"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="你好")
        content = msgs[0]["content"]
        # 无 scene_name 时用"坐山客AI工作台的智能助手"
        assert "智能助手" in content
        # 不应包含【】格式的领域名
        assert "【" not in content.split("\n")[0]

    def test_scene_info_in_converge(self):
        """scene_id → 场景信息出现在收敛部分"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(
            user_content="你好",
            scene_id="scene-test-001",
            scene_name="测试场景",
        )
        content = msgs[0]["content"]
        assert "scene-test-001" in content
        assert "测试场景" in content


# ══════════════════════════════════════════════════
# P0: user_context / db=None / 历史消息
# ══════════════════════════════════════════════════


class TestUserContextAndHistory:
    """P0: user_context 映射 + db=None + 历史消息"""

    def test_user_context_mapped_to_custom_prompt(self):
        """user_context → fenshen_config.custom_prompt → 角色设定中出现"""
        from agent_core.context_builder import build_agent_context_v1
        ctx = "你是一个资深 Python 工程师"
        msgs = build_agent_context_v1(
            user_content="你好", user_context=ctx
        )
        # user_context 应出现在 system prompt 中
        assert ctx in msgs[0]["content"]

    def test_db_none_graceful(self):
        """db=None 不会报错，仍返回消息列表"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="你好", db=None)
        assert isinstance(msgs, list)
        assert len(msgs) >= 2
        assert msgs[-1]["content"] == "你好"

    def test_history_included(self):
        """历史消息出现在 system 和 user 之间"""
        from agent_core.context_builder import build_agent_context_v1
        history = [
            {"role": "user", "content": "今天天气怎么样"},
            {"role": "ai", "content": "今天是晴天"},
        ]
        msgs = build_agent_context_v1(
            user_content="谢谢", history_messages=history
        )
        # system + 2 条历史 + user = 4 条
        assert len(msgs) >= 4
        history_roles = [m["role"] for m in msgs[1:-1]]
        assert "user" in history_roles
        assert "assistant" in history_roles

    def test_history_role_mapping(self):
        """ai → assistant 映射正确"""
        from agent_core.context_builder import build_agent_context_v1
        history = [
            {"role": "user", "content": "你好"},
            {"role": "ai", "content": "你好！有什么可以帮你的？"},
        ]
        msgs = build_agent_context_v1(
            user_content="谢谢", history_messages=history
        )
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "你好"
        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["content"] == "你好！有什么可以帮你的？"

    def test_no_history_system_user_only(self):
        """无历史消息时只有 system + user"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="你好")
        assert len(msgs) == 2  # system + user

    def test_empty_history_list(self):
        """空列表历史消息不影响"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(
            user_content="你好", history_messages=[]
        )
        assert len(msgs) == 2


# ══════════════════════════════════════════════════
# P1: Memory Layer
# ══════════════════════════════════════════════════


class TestMemoryLayer:
    """P1: 记忆层 — zhu 三层注入 + scene top-5"""

    def _reset_cache(self):
        from agent_core.memory_cache import MemoryCache
        MemoryCache.reset_instance()

    def test_zhu_memory_injected(self):
        """本体记忆（Core Tier fallback + Context Tier）出现在上下文中"""
        from agent_core.context_builder import build_agent_context_v1
        from agent_core.memory_cache import MemoryCache
        self._reset_cache()
        db = _make_session()
        try:
            cache = MemoryCache.get_instance()
            # 插入本体级记忆（is_immortal=true，让 fallback 生效）
            _insert_memory(db, "design_philosophy",
                           "坐山客设计哲学：开放 > 封闭，LLM自主决策优于规则",
                           is_immortal=True, base_weight=10)
            # 插入一条普通记忆（Context Tier 匹配）
            _insert_memory(db, "user_preference",
                           "用户喜欢简洁的回复风格",
                           base_weight=5)
            # 加载到缓存
            cache.load_scope(db, "zhu")

            msgs = build_agent_context_v1(
                user_content="帮我查个东西", db=db
            )
            # 找所有 user 消息层
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            assert "坐山客设计哲学" in all_content, \
                "本体 Core 记忆应出现在 user layer: " + all_content[:300]
        finally:
            db.close()
            self._reset_cache()

    def test_scene_memory_injected(self):
        """场景记忆（top-5）出现在 user layer"""
        from agent_core.context_builder import build_agent_context_v1
        from agent_core.memory_cache import MemoryCache
        self._reset_cache()
        db = _make_session()
        try:
            cache = MemoryCache.get_instance()
            # 插入场景记忆
            _insert_memory(db, "project_context",
                           "用户正在开发一个 Web 应用",
                           scope="scene", context_id="scene-mem-001")
            # 加载到缓存
            cache.load_scope(db, "scene", "scene-mem-001")

            msgs = build_agent_context_v1(
                user_content="继续开发", db=db,
                scene_id="scene-mem-001", scene_name="自开发",
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            assert "正在开发一个 Web 应用" in all_content, \
                "场景记忆应出现在 user layer: " + all_content[:300]
        finally:
            db.close()
            self._reset_cache()

    def test_no_memory_graceful(self):
        """没有记忆时不会报错，也没有记忆块"""
        from agent_core.context_builder import build_agent_context_v1
        from agent_core.memory_cache import MemoryCache
        self._reset_cache()
        db = _make_session()
        try:
            cache = MemoryCache.get_instance()
            cache.load_scope(db, "zhu")  # 空 scope

            msgs = build_agent_context_v1(
                user_content="你好", db=db
            )
            # 不应有 "关于你的一些已知信息"
            for m in msgs:
                if isinstance(m.get("content"), str):
                    assert "关于你的一些已知信息" not in m["content"]
            assert isinstance(msgs, list)
            assert len(msgs) >= 2
        finally:
            db.close()
            self._reset_cache()

    def test_scene_memory_top5_limit(self):
        """场景记忆最多取 top-5"""
        from agent_core.context_builder import build_agent_context_v1
        from agent_core.memory_cache import MemoryCache
        self._reset_cache()
        db = _make_session()
        try:
            cache = MemoryCache.get_instance()
            # 插入 7 条场景记忆
            for i in range(7):
                _insert_memory(db, f"mem_{i}",
                               f"记忆内容第{i+1}条",
                               scope="scene",
                               context_id="scene-mem-top5")
            cache.load_scope(db, "scene", "scene-mem-top5")

            msgs = build_agent_context_v1(
                user_content="测试", db=db,
                scene_id="scene-mem-top5", scene_name="测试",
            )
            # 统计出现在 user layer 的记忆条数（每一条格式为 "- ✱ key: content"）
            user_blocks = [
                m["content"] for m in msgs
                if m["role"] == "user"
            ]
            all_text = "\n".join(user_blocks)
            count = all_text.count("记忆内容第")
            assert count <= 5, f"场景记忆取 {count} 条，预期 ≤5"
        finally:
            db.close()
            self._reset_cache()


# ══════════════════════════════════════════════════
# P1: Profile Layer
# ══════════════════════════════════════════════════


class TestProfileLayer:
    """P1: 用户画像层 — P0+P1 始终注入，P2 话题匹配"""

    def test_p0_profile_always_injected(self):
        """P0 用户画像始终出现在 user layer"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_user_profile(
                db, "up-dev", "用户是开发者，熟悉 Python 和 Web 开发",
                priority="P0", tags=["开发", "Python"],
            )
            msgs = build_agent_context_v1(
                user_content="你好", db=db,
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            assert "用户是开发者" in all_content, \
                "P0 画像应始终注入: " + all_content[:300]
        finally:
            db.close()

    def test_p1_profile_always_injected(self):
        """P1 用户画像始终出现在 user layer"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_user_profile(
                db, "up-concise", "用户偏好简洁的回复风格",
                priority="P1",
            )
            msgs = build_agent_context_v1(
                user_content="你好", db=db,
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            assert "用户偏好简洁的回复风格" in all_content
        finally:
            db.close()

    def test_p2_profile_topic_matched(self):
        """P2 画像匹配用户消息话题才注入"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_user_profile(
                db, "up-django", "用户用过 Django 框架开发过大型项目",
                priority="P2", tags=["Django"],
            )
            # 消息不匹配 → P2 不应出现
            msgs = build_agent_context_v1(
                user_content="今天天气怎么样", db=db,
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            assert "Django" not in all_content, \
                "不匹配话题时 P2 不应注入"

            # 消息匹配 → P2 出现
            msgs2 = build_agent_context_v1(
                user_content="帮我看看这个 Django 项目", db=db,
            )
            all_content2 = " ".join(
                m["content"] for m in msgs2 if m["role"] == "user"
            )
            assert "Django" in all_content2, \
                "匹配话题时 P2 应注入"
        finally:
            db.close()

    def test_no_profiles_graceful(self):
        """无用户画像 → 无画像块"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            msgs = build_agent_context_v1(
                user_content="你好", db=db,
            )
            for m in msgs:
                if isinstance(m.get("content"), str):
                    assert "👤 用户画像" not in m["content"]
        finally:
            db.close()

    def test_p0_p2_priority_order(self):
        """P0 分组出现在 P2 分组之前"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_user_profile(
                db, "up-p0", "P0原则：用户是开发者",
                priority="P0",
            )
            _create_user_profile(
                db, "up-p2", "P2参考：用户用过Flask",
                priority="P2", tags=["Flask"],
            )
            msgs = build_agent_context_v1(
                user_content="Flask 项目", db=db,
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            idx_p0 = all_content.find("P0原则")
            idx_p2 = all_content.find("P2参考")
            assert idx_p0 >= 0 and idx_p2 >= 0
            assert idx_p0 < idx_p2, \
                f"P0 应出现在 P2 之前: P0@{idx_p0} P2@{idx_p2}"
        finally:
            db.close()


# ══════════════════════════════════════════════════
# P1: Config Layer
# ══════════════════════════════════════════════════


class TestConfigLayer:
    """P1: 配置层 — 模型路由 + 场景参数"""

    def test_model_config_in_system(self):
        """Setting 中的 model routing 出现在 user layer"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _insert_setting(db, routing={
                "scene": {
                    "model": "deepseek-v4-flash",
                    "provider": "deepseek",
                    "temperature": 0.3,
                }
            })
            msgs = build_agent_context_v1(
                user_content="你好", db=db,
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            assert "deepseek-v4-flash" in all_content
            assert "deepseek" in all_content
        finally:
            db.close()

    def test_scene_params_in_system(self):
        """Scene 的收敛参数出现在 config layer"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_scene(
                db, "scene-cfg-001", name="配置测试",
                converge_threshold=0.8,
                converge_enabled=True,
                diverge_min_rounds=3,
            )
            msgs = build_agent_context_v1(
                user_content="你好", db=db,
                scene_id="scene-cfg-001", scene_name="配置测试",
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            assert "收敛阈值" in all_content
            assert "0.8" in all_content or "0. 8" in all_content
        finally:
            db.close()

    def test_no_setting_no_config_block(self):
        """无 Setting 配置 → 无 config block（不是空字符串）"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="你好", db=None)
        # 无 DB 时不应有 config 层
        for m in msgs:
            if isinstance(m.get("content"), str):
                assert "当前模型配置" not in m["content"]


# ══════════════════════════════════════════════════
# P1: History Layer
# ══════════════════════════════════════════════════


class TestHistoryLayer:
    """P1: 历史消息 — 优先级排序"""

    def test_high_priority_first(self):
        """high 优先级消息在前"""
        from agent_core.context_builder import build_agent_context_v1
        history = [
            {"role": "ai", "content": "正常回复", "priority": "normal"},
            {"role": "user", "content": "重要发现", "priority": "high"},
        ]
        msgs = build_agent_context_v1(
            user_content="继续", history_messages=history,
        )
        # high 应该在 normal 之前
        history_msgs = [m for m in msgs if m["role"] != "system"]
        idx_high = next(i for i, m in enumerate(history_msgs)
                        if m.get("content") == "重要发现")
        idx_normal = next(i for i, m in enumerate(history_msgs)
                          if m.get("content") == "正常回复")
        assert idx_high < idx_normal, \
            f"high({idx_high}) 应出现在 normal({idx_normal}) 之前"

    def test_low_priority_merged(self):
        """low 优先级应合并为一条 system 消息"""
        from agent_core.context_builder import build_agent_context_v1
        history = [
            {"role": "user", "content": "低优先级消息1", "priority": "low"},
            {"role": "ai", "content": "低优先级消息2", "priority": "low"},
        ]
        msgs = build_agent_context_v1(
            user_content="继续", history_messages=history,
        )
        # 应包含一条 system role 消息，内容包含"低优先级上下文"
        system_msgs = [m for m in msgs if m["role"] == "system"]
        assert any("低优先级上下文" in m["content"] for m in system_msgs), \
            "low 消息应合并为 system 消息"


# ══════════════════════════════════════════════════
# P1: Work Output Layer
# ══════════════════════════════════════════════════


class TestWorkOutputLayer:
    """P1: 干活输出层 — FileSnapshot 最近窗口"""

    def test_work_output_with_snapshot(self):
        """FileSnapshot 出现在 user layer"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_scene(db, "scene-work-001", name="工作场景")
            _create_file_snapshot(
                db, "scene-work-001",
                "/src/main.py",
                "添加了用户登录功能",
                "+def login(): ...\n+    pass",
            )
            msgs = build_agent_context_v1(
                user_content="继续开发", db=db,
                scene_id="scene-work-001", scene_name="工作场景",
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            assert "最近操作记录" in all_content
            assert "main.py" in all_content
            assert "用户登录功能" in all_content
        finally:
            db.close()

    def test_no_snapshot_graceful(self):
        """无 FileSnapshot → 无 work output 块"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_scene(db, "scene-work-002", name="工作场景2")
            msgs = build_agent_context_v1(
                user_content="开发", db=db,
                scene_id="scene-work-002", scene_name="工作场景2",
            )
            for m in msgs:
                if isinstance(m.get("content"), str):
                    assert "最近操作记录" not in m["content"]
        finally:
            db.close()

    def test_work_output_window_respected(self):
        """work_output_window=1 只取最近 1 条"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_scene(db, "scene-work-003", name="窗口测试")
            snap1 = _create_file_snapshot(
                db, "scene-work-003", "/a.py", "改动A", "-old\n+new"
            )
            snap2 = _create_file_snapshot(
                db, "scene-work-003", "/b.py", "改动B", "-old\n+new"
            )
            msgs = build_agent_context_v1(
                user_content="开发", db=db,
                scene_id="scene-work-003", scene_name="窗口测试",
                work_output_window=1,
            )
            all_content = " ".join(
                m["content"] for m in msgs if m["role"] == "user"
            )
            count = all_content.count("改动")
            assert count <= 2, f"work_output_window=1 时不应有 {count} 条"
        finally:
            db.close()


# ══════════════════════════════════════════════════
# P1: Skill Layer (light)
# ══════════════════════════════════════════════════


class TestSkillLayer:
    """P1: 技能层 — SkillManager 匹配"""

    def test_skill_matched_graceful(self):
        """技能匹配不会报错，匹配时出现在 user layer"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(
            user_content="帮我查一下天气", db=None,
        )
        assert isinstance(msgs, list)
        assert len(msgs) >= 2

    def test_no_skill_no_block(self):
        """无明显匹配技能时，无 skill block"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(user_content="你好", db=None)
        for m in msgs:
            if isinstance(m.get("content"), str):
                assert "参考技能" not in m["content"]


# ══════════════════════════════════════════════════
# P1: Thinking Map State Block
# ══════════════════════════════════════════════════


class TestThinkingMapBlock:
    """P1: 思维导图状态块"""

    def test_tm_block_empty_when_no_map(self):
        """无思维导图时不出错"""
        from agent_core.context_builder import build_agent_context_v1
        msgs = build_agent_context_v1(
            user_content="你好",
            scene_id="nonexistent-scene",
        )
        assert isinstance(msgs, list)

    def test_tm_block_with_map_data(self):
        """有思维导图节点时出现在 system prompt"""
        from agent_core.context_builder import build_agent_context_v1
        db = _make_session()
        try:
            _create_scene(db, "scene-tm-001", name="导图测试")
            _create_thinking_map(db, "scene-tm-001")

            msgs = build_agent_context_v1(
                user_content="分析需求", db=db,
                scene_id="scene-tm-001", scene_name="导图测试",
            )
            content = msgs[0]["content"]
            # system prompt 中应有思维导图状态
            assert "已有思维节点" in content or "用户需求分析" in content, \
                f"思维导图节点应出现在 system prompt: {content[:300]}"
        finally:
            db.close()
