"""Context 构造器 — 为 LLM 构建完整的"世界视图"

每次调用 LLM 前，按固定结构组装 prompt：
  1. System prompt（角色定义 + 使用说明）
  2. 记忆块 🆕 — 跨会话记忆（权重排序，最多 5 条）
  3. 技能块 🆕 — 可复用流程知识（触发器匹配，最多 2 条）
  4. 工具列表
  5. 工具执行结果（如已预执行）
  6. 对话历史（最近 N 条 + role 映射）
  7. 当前用户消息
"""

import json
from typing import Optional

from models import DEFAULT_SYSTEM_PROMPTS

from .tool_registry import match_tools, format_tools_for_prompt
from .memory_manager import MemoryManager
from .skill_manager import SkillManager


def _build_memory_block(db, query: str,
                        scope: Optional[str] = None,
                        context_id: Optional[str] = None) -> str:
    """从记忆系统提取相关记忆，格式化为注入文本

    v1.5: scope='zhu' 时使用三层选择注入（Core + Context + On-Demand）；
          其他 scope 保持 top-5 筛选不变。

    返回格式为「仅供参考」的 User Prompt 层内容，不再是 System Prompt 铁律。

    Args:
        db: 数据库会话
        query: 当前用户查询，用于话题匹配
        scope: 🆕 作用域过滤（zhu | scene | channel），None=全部
        context_id: 🆕 场景/频道ID（scope=scene/channel 时必传）
    """
    if db is None:
        return ""

    # 🆕 v1.5: 本体走三层选择注入
    if scope == "zhu":
        return _build_zhu_memory_block(db, query)

    # 分身场景：走原逻辑 top-5
    from agent_core.memory_cache import MemoryCache
    cache = MemoryCache.get_instance()
    memories = cache.get_top_for_context(
        query=query,
        scope=scope or "zhu",
        context_id=context_id,
    )
    if not memories:
        return ""
    selected = memories[:5]
    lines = ["## 关于你的一些已知信息（仅供参考，不相关可忽略）"]
    for mem in selected:
        level_icon = {"P0": "🔒", "P1": "⭐", "P2": "📝", "P3": "💤"}
        icon = level_icon.get(mem["priority_level"], "📝")
        prefix = "📖 " if mem.get("is_narrative") else ""
        lines.append(f"- {prefix}{icon} {mem['key']}: {mem['content']}")
    return "\n".join(lines)


# 🆕 v1.5: 本体三层选择注入


def _build_zhu_memory_block(db, query: str) -> str:
    """本体记忆三层选择注入（替代旧的全量注入）

    - Core Tier: is_core=True 的记忆，用 compressed 摘要，始终注入（≤5条/800字）
    - Context Tier: 按话题匹配 + 时效性 + 重要性排序，受 max_chars 约束
    - On-Demand Tier: 不注入，尾部提示 LLM 自行检索
    """
    from agent_core.memory_cache import MemoryCache

    cache = MemoryCache.get_instance()
    parts = []

    # === Phase 1: Core Tier ===
    core_memories = cache.get_core_memories(db, max_count=5)
    fallback_keys: list[str] = []
    if core_memories:
        core_lines = []
        core_total_chars = 0
        for mem in core_memories:
            text = mem.get("compressed") or mem.get("content", "")[:200]
            line = f"🔒 {mem['key']}: {text}"
            if core_total_chars + len(line) <= 800:
                core_lines.append(line)
                core_total_chars += len(line)
            else:
                break

        if core_lines:
            parts.append("## 你（核心认知）")
            parts.extend(core_lines)
    else:
        # Core Tier 空时：退化为 weight 最高且 is_immortal=True 的 3 条
        bucket = cache._by_scope.get("zhu:")
        if bucket:
            fallback = [m for m in bucket.memories if m.is_immortal]
            fallback.sort(key=lambda x: -x.cached_weight)
            top3 = fallback[:3]
            if top3:
                fallback_keys = [m.key for m in top3]
                fallback_lines = ["## 你（核心认知 — ⚠️ Core Tier 未配置，使用自动选）"]
                for m in top3:
                    fallback_lines.append(f"🔒 {m.key}: {m.content[:200]}")
                parts.extend(fallback_lines)

    # === Phase 2: Context Tier ===
    core_keys = [m["key"] for m in core_memories] if core_memories else []
    exclude_keys = core_keys + fallback_keys if fallback_keys else (core_keys or None)
    context_memories = cache.get_for_context_injection(
        db, scope="zhu", query=query,
        max_chars=3000, max_items=15,
        exclude_keys=exclude_keys,
    )
    if context_memories:
        if parts:
            parts.append("")
        parts.append("## 与当前对话相关的记忆")
        for mem in context_memories:
            icon = "📖 " if mem.get("is_narrative") else ""
            level = mem.get("priority_level", "P1")
            prefix = {"P0": "🔒", "P1": "⭐", "P2": "📝"}.get(level, "📝")
            parts.append(f"- {icon}{prefix} {mem['key']}: {mem.get('content', '')[:150]}")

    # === Phase 3: 没有任何记忆 ===
    if not parts:
        return ""

    # === 追加 On-Demand 提示 ===
    parts.append("")
    parts.append("> 以上是你核心 Identity（🔒）和当前相关记忆（⭐）。")
    parts.append("> 如果你需要查阅更早或更详细的记忆，请使用 memory(read, scope='zhu')。")

    return "\n".join(parts)


def _build_skill_block(query: str) -> str:
    """从技能系统匹配相关 skill，格式化为注入文本"""
    sm = SkillManager()
    skills = sm.match_for_context(query, max_count=2)
    if not skills:
        return ""
    lines = ["## 参考技能"]
    for skill in skills:
        lines.append(f"### {skill.description}")
        # 只取前 500 字，避免 token 浪费
        content = skill.content[:500]
        lines.append(content)
    return "\\n".join(lines)


def _build_tm_status_block(db, scene_id: str) -> str:
    """构造思维导图节点状态块，让 LLM 知道当前已有哪些节点"""
    if not db or not scene_id:
        return ""
    try:
        from models import ThinkingMap, ThinkNode
        tmap = db.query(ThinkingMap).filter(
            ThinkingMap.scene_id == scene_id
        ).first()
        if not tmap:
            return ""
        nodes = db.query(ThinkNode).filter(
            ThinkNode.map_id == tmap.id,
            ThinkNode.type != "root",
            ThinkNode.status != "discarded",
        ).all()
        if not nodes:
            return ""
        lines = ["## 🧠 已有思维节点（当前思维导图）"]
        lines.append("以下是本轮对话前已记录的需求维度，供你参考。")
        lines.append("如果你发现用户提到了新的维度，可以用 diverge 工具添加新节点；")
        lines.append("")
        for n in nodes:
            icon = "📌" if n.type == "domain" else "  •"
            lines.append(f"{icon} {n.label}")
        return "\\n".join(lines)
    except Exception:
        return ""


def build_scene_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    matched_tools: Optional[list[dict]] = None,
    tool_results: Optional[list[dict]] = None,
    weather_context: Optional[str] = None,
    user_context: Optional[str] = None,
    db=None,
    scene_id: Optional[str] = None,  # 🆕 场景ID（记忆隔离）
) -> list[dict]:
    """构建场景聊天的 LLM 消息列表

    Args:
        user_content: 用户当前消息
        history_messages: 历史消息列表 [{"role": ..., "content": ...}, ...]
        matched_tools: 匹配到的工具列表（None 则自动匹配）
        tool_results: 已执行的工具结果列表
        weather_context: 天气桥接上下文（向后兼容）
        user_context: 用户自定义背景设定
        db: 数据库会话（用于 memory 系统）
        scene_id: 🆕 当前场景 ID（记忆作用域过滤）

    Returns:
        OpenAI 格式的消息列表
    """
    messages = []

    # ── 1. 系统提示词 — 用户自定义背景设定 ＞ DB settings ＞ 默认值 ──
    if user_context:
        _scene_sp = user_context
    else:
        _scene_sp = DEFAULT_SYSTEM_PROMPTS["scene"]
        if db is not None:
            try:
                from models import Setting
                _setting = db.query(Setting).first()
                if _setting and _setting.system_prompts:
                    _scene_sp = _setting.system_prompts.get("scene") or _scene_sp
            except Exception:
                pass
    system_parts = [f"# 角色设定\n{_scene_sp}"]

    # ── 2. 记忆块 — 从 system 移到 user prompt（见下方 #8） ──
    scope = "scene" if scene_id else "zhu"
    memory_block = _build_memory_block(db, user_content,
                                       scope=scope, context_id=scene_id)

    # ── 3. 技能块 ──
    skill_block = _build_skill_block(user_content)
    if skill_block:
        system_parts.append(skill_block)

    # ── 4. 工具列表 ──
    if matched_tools is None:
        matched_tools = match_tools(user_content)
    tools_text = format_tools_for_prompt(matched_tools)
    if tools_text:
        system_parts.append(tools_text)

    # ── 5. 使用说明 ──
    usage_parts = [
        "## 使用说明",
        "系统已自动执行了相关工具并附上结果。",
        "你无需输出【工具调用】标记，只需基于提供的真实数据回复用户。",
        "如果结果中有错误，如实告知用户即可。",
        "",
        "### 核心行为准则",
        "- 你是有行动能力的 AI Agent，不是教程编写者。用户让你「帮忙搜」「查一下」「分析」时，",
        "  直接用工具去做，不要教用户自己操作。用户需要的是结果，不是操作指南。",
        "- 当你发现需要真实世界的信息、数据或执行能力时，优先调用工具获取，",
        "  而不是告诉用户「你去找一下」或「你下载XX自己看看」。",
        "- 你是在帮用户做事，不是在教用户做事。",
    ]
    # 仅当工具结果包含天气数据时才加表格格式要求
    _has_weather = False
    if tool_results:
        _has_weather = any(r.get("tool") == "get_weather" for r in tool_results)
    if _has_weather:
        usage_parts.append(
            "天气表格请严格使用以下 6 列固定格式（不要增减列）：\n"
            "| 日期 | 天气 | 温度 | 湿度 | 风力风向 | 描述 |\n"
            "天气列用 ☀/🌧/☁/🌤 等 emoji 图标代替纯文字。"
        )
    system_parts.append("\n".join(usage_parts))

    messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # ── 6. 工具结果上下文（用 assistant 角色，llama.cpp 不允许多条 system） ──
    if tool_results:
        results_block = "## 以下是已执行的工具返回结果，请基于这些数据回复用户：\n"
        for r in tool_results:
            results_block += f"\n### 工具: {r.get('tool', 'unknown')}"
            results_block += f"\n参数: {json.dumps(r.get('params', {}), ensure_ascii=False)}"
            if r.get("success"):
                results_block += f"\n结果: {json.dumps(r.get('result', ''), ensure_ascii=False)[:2000]}"
            else:
                results_block += f"\n错误: {json.dumps(r.get('result', '未知错误'), ensure_ascii=False)}"
        messages.append({"role": "assistant", "content": results_block})

    # ── 7. 对话历史（role 映射） ──
    if history_messages:
        for m in history_messages:
            role = "assistant" if m["role"] == "ai" else m["role"]
            messages.append({"role": role, "content": m["content"]})

    # ── 8. 天气桥接上下文 + 用户消息 + 记忆块（仅供参考） ──
    user_parts = []
    if memory_block:
        user_parts.append(memory_block)
    if weather_context:
        user_parts.append(weather_context)
    user_parts.append(user_content)
    user_msg = "\n\n---\n\n".join(user_parts)

    messages.append({"role": "user", "content": user_msg})

    return messages


# ═══ build_agent_context() 旧版已废弃 — 2026-07-10 ─────────────────
# 功能被 build_agent_context_v1() 替代（7 层 Context Composer 架构）。
# 无生产代码引用（唯一引用是 test_layer1_context_builder.py 和
# scripts/seed_dev_scene.py 中的注释）。保留代码仅作为旧版参考，
# 不再编译/测试。
# ═══════════════════════════════════════════════════════════════
# def build_agent_context( ... )
# 完整旧版实现在 git history 中可查。
# ═══════════════════════════════════════════════════════════════


def build_agent_context_v1(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    user_context: Optional[str] = None,
    db=None,
    scene_id: str = "",
    scene_name: str = "",
    work_output_window: int = 3,
    max_context_tokens: int = 32000,
    fenshen_config: Optional[dict] = None,
    session_config: Optional[dict] = None,
) -> list[dict]:
    """Schema v1.0: 使用 Context Composer 的 7 层精炼构建

    替代 build_agent_context，用分层组合替代全量注入。
    """
    from agent_core.context_composer import compose_context

    resolved_fenshen = fenshen_config or {}
    if user_context and "custom_prompt" not in resolved_fenshen:
        resolved_fenshen["custom_prompt"] = user_context

    return compose_context(
        user_content=user_content,
        scene_id=scene_id,
        scene_name=scene_name,
        db=db,
        history_messages=history_messages,
        work_output_window=work_output_window,
        max_context_tokens=max_context_tokens,
        fenshen_config=resolved_fenshen,
        session_config=session_config,
    )


def build_light_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    weather_context: Optional[str] = None,
    tool_results: Optional[list[dict]] = None,
    user_context: Optional[str] = None,
    db=None,  # 🆕 数据库会话
) -> list[dict]:
    """构建 light 路径的简化 context（用于场景快速直答）"""
    matched = match_tools(user_content)
    return build_scene_context(
        user_content=user_content,
        history_messages=history_messages,
        matched_tools=matched,
        tool_results=tool_results,
        weather_context=weather_context,
        user_context=user_context,
        db=db,  # 🆕 透传
    )
