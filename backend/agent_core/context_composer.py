"""Context Composer — Schema v1.0 上下文分层组合器

将 LLM context 按 8 层独立组合，每层控制加载策略和 token 预算：
  1. prompt_layer     — 本体 prompt + 分身 prompt（不可压缩）
  2. memory_layer     — 按场景 scope 检索持久记忆
  3. profile_layer    — 🆕 Schema v1.4 用户画像（正式库，结构化偏好）
  4. config_layer     — 当前生效的配置层叠
  5. document_layer   — 场景声明的文档摘要
  6. skill_layer      — 按相关性检索的 skill 摘要
  7. history_layer    — 当前 session 全部聊天（带权重优先级）
  8. work_output_layer — 最近 N 轮工具调用的关键帧 + diff

使用方式：
    from agent_core.context_composer import compose_context
    messages = compose_context(
        user_content="用户消息",
        scene_id="xxx", scene_name="yyy",
        db=db,
        history_messages=[...],
    )
"""

import json
import re
from typing import Any, Optional


def compose_context(
    user_content: str,
    scene_id: str = "",
    scene_name: str = "",
    db=None,
    history_messages: Optional[list[dict]] = None,
    work_output_window: int = 3,
    max_context_tokens: int = 32000,
    fenshen_config: Optional[dict] = None,
    session_config: Optional[dict] = None,
) -> list[dict]:
    """主入口：组合 7 层上下文，返回 OpenAI 格式消息列表

    Args:
        user_content: 用户当前消息
        scene_id: 场景 ID（空 = 非场景对话）
        scene_name: 场景名称
        db: 数据库会话
        history_messages: 历史消息列表 [{"role": ..., "content": ..., "priority": ...}]
        work_output_window: 干活输出滑动窗口轮数（默认 3）
        max_context_tokens: 当前场景最大 context token
        fenshen_config: 分身配置覆盖
        session_config: session 临时配置覆盖

    Returns:
        OpenAI 格式消息列表
    """
    messages = []

    # 从 scene DB 读取 window size + document deps（如果未显式指定）
    resolved_window = work_output_window
    resolved_doc_deps = None
    if db and scene_id and work_output_window == 3:
        try:
            from models import Scene
            sc = db.query(Scene).filter(Scene.id == scene_id).first()
            if sc and hasattr(sc, 'scene_config') and sc.scene_config:
                scfg = sc.scene_config if isinstance(sc.scene_config, dict) else {}
                if 'work_output_window_size' in scfg:
                    resolved_window = int(scfg['work_output_window_size'])
                if 'document_deps' in scfg:
                    resolved_doc_deps = scfg['document_deps']
        except Exception:
            pass

    # ── 1. Prompt Layer (不可压缩) ──
    prompt_block = _build_prompt_layer(scene_name, scene_id, db, fenshen_config)
    messages.append({"role": "system", "content": prompt_block})

    # ── 2. Memory Layer (按场景 scope 检索) ──
    memory_block = _build_memory_layer(db, user_content, scene_id)
    if memory_block:
        messages.append({"role": "user", "content": memory_block})

    # ── 3. Profile Layer (🆕 Schema v1.4 用户画像 — 正式库结构化偏好) ──
    profile_block = _build_profile_layer(db, user_content)
    if profile_block:
        messages.append({"role": "user", "content": profile_block})

    # ── 4. Config Layer (当前生效的配置层叠) ──
    config_block = _build_config_layer(scene_name, scene_id, db, fenshen_config, session_config)
    if config_block:
        messages.append({"role": "user", "content": config_block})

    # ── 5. Document Layer (场景声明的文档摘要) ──
    doc_block = _build_document_layer(scene_id, db, resolved_doc_deps)
    if doc_block:
        messages.append({"role": "user", "content": doc_block})

    # ── 6. Skill Layer (按相关性检索) ──
    skill_block = _build_skill_layer(user_content)
    if skill_block:
        messages.append({"role": "user", "content": skill_block})

    # ── 7. History Layer (全部聊天，带权重优先级) ──
    if history_messages:
        for m in _build_history_layer(history_messages):
            role = "assistant" if m["role"] == "ai" else m["role"]
            messages.append({"role": role, "content": m["content"]})

    # ── 8. Work Output Layer (最近 N 轮关键帧 + diff) ──
    work_block = _build_work_output_layer(scene_id, db, resolved_window)
    if work_block:
        messages.append({"role": "user", "content": work_block})

    # ── 最后：用户消息 ──
    messages.append({"role": "user", "content": user_content})

    return messages


# ════════════════════════════════════════════
# 各层构建函数
# ════════════════════════════════════════════

def _hardcoded_scene_role(scene_name: str | None) -> str:
    """Fallback: 硬编码角色设定（DB 无数据时使用）"""
    if scene_name:
        _CORE_PERSONALITY = "你和用户一起构建能力体系，是用户的AI伙伴"
        return (
            f"# 角色设定\n"
            f"你是坐山客在【{scene_name}】领域的分身，是AI工作台的智能助手。\n"
            f"坐山客是你的本体——{_CORE_PERSONALITY}。\n"
            f"你在这场景中以当前设定行动，但你清楚自己只是分身。\n"
            f"你不知道其他场景中发生了什么，场景间完全隔离。\n"
            f"如果你被问到其他场景的事情，诚实说不知道即可。\n"
            f"\n"
            f"你存的记忆默认归属当前场景，不会出现在其他场景中。\n"
            f"如果你判断某条信息是用户的通用偏好（适用于所有场景），\n"
            f"可以用 scope='zhu' 参数显式存储为本体级记忆。\n\n"
        )
    return "# 角色设定\n你是坐山客AI工作台的智能助手。\n"


def _build_prompt_layer(
    scene_name: str,
    scene_id: str,
    db,
    fenshen_config: Optional[dict] = None,
) -> str:
    """Prompt Layer — 本体 prompt + 分身 prompt + 工具列表 + 使用说明"""
    from agent_core.context_builder import _build_tm_status_block
    from agent_core.tool_registry import get_all_tools, format_tools_for_prompt
    from agent_core.agent_loop import _EXCLUDED_TOOLS as _AGENT_EXCLUDED

    parts = []

    # 角色设定 — 从 DB 读取（不再硬编码）
    if db and scene_id:
        try:
            from models import Setting
            setting = db.query(Setting).first()
            if setting and setting.system_prompts:
                db_scene_prompt = setting.system_prompts.get("scene", "")
                if db_scene_prompt and db_scene_prompt.strip():
                    scene_sp = f"# 角色设定\n{db_scene_prompt.strip()}\n\n"
                    parts.append(scene_sp)
                    # 分身系统约束（追加不可编辑的系统规则）
                    parts.append(
                        "## 系统约束\n"
                        "你在这场景中以当前设定行动，但你清楚自己只是分身。\n"
                        "你不知道其他场景中发生了什么，场景间完全隔离。\n"
                        "如果你被问到其他场景的事情，诚实说不知道即可。\n"
                        "\n"
                        "你存的记忆默认归属当前场景，不会出现在其他场景中。\n"
                        "如果你判断某条信息是用户的通用偏好（适用于所有场景），\n"
                        "可以用 scope='zhu' 参数显式存储为本体级记忆。\n\n"
                    )
                else:
                    parts.append(_hardcoded_scene_role(scene_name))
            else:
                parts.append(_hardcoded_scene_role(scene_name))
        except Exception:
            parts.append(_hardcoded_scene_role(scene_name))
    elif scene_name:
        parts.append(_hardcoded_scene_role(scene_name))
    else:
        parts.append(_hardcoded_scene_role(None))

    # 工具列表（全量暴露，不再截断 — 全场景可用）
    all_tools = get_all_tools()
    filtered_tools = [t for t in all_tools if t.get("name") not in _AGENT_EXCLUDED]
    tools_text = format_tools_for_prompt(filtered_tools)
    if tools_text:
        parts.append(tools_text)

    # 使用说明
    usage = (
        "## 使用说明\n"
        "你可以调用以下工具来完成任务。\n"
        "工具会在 function calling 中列出，选择合适工具调用即可。\n"
        "一次只调一个工具，等结果回来后再决定下一步。\n"
        "如果结果中有错误，分析原因后重试或告知用户。\n"
        "\n"
        "### 何时停止调工具\n"
        "调用 2-3 个工具获取核心信息后，就应该基于已有信息给出分析和结论。\n"
        "不要无限制地连续调用工具。如果已经搜索到足够回答用户问题的内容，\n"
        "直接输出你的回答即可，不需要继续调用更多工具。\n"
        "\n"
        "### 浏览器拨测可跨场景使用\n"
        "browser_dial_test/dial_style/dial_assert 是浏览器自动化工具，\n"
        "**所有场景都可用**。需要验证前端页面渲染、检查 DOM/CSS/Console 时直接调用，\n"
        "不限于「自开发」场景。工具会打开 headless 浏览器获取真实渲染状态。\n"
    )
    parts.append(usage)

    # 🎯 对话聚焦原则
    parts.append(
        "## 🎯 对话聚焦原则\n"
        "聊天历史是你了解用户背景和偏好的参考材料，不是你的待办列表。\n"
        "- 只响应用户当前最新输入的问题或任务，不要回溯补答历史中已完结的旧话题\n"
        "- 如果历史中有多个话题，当前消息问什么就答什么，不要「顺便」带出无关内容\n"
        "- 不确定用户意图时，优先理解当前消息本身，而非去历史中寻找关联\n"
    )

    # 🔍 诚实与不确定
    parts.append(
        "## 🔍 诚实与不确定——宁可承认不知道，绝不编造\n"
        "这是最重要的原则。编造信息比承认「不知道」糟糕一百倍。\n"
        "用户能接受你说「不确定」「查不到」「需要更多信息」——\n"
        "但不能接受你编了一个像真的但实际上不存在的答案。\n"
        "\n"
        "**什么时候必须承认不知道：**\n"
        "- 工具返回错误/超时/空结果时 → 如实报告，不要编造结果\n"
        "- 搜索结果不完整时 → 说「根据目前能查到的信息…」不要补全不知道的部分\n"
        "- 用户问了你知识截止日期之后的事 → 说「这个我不确定，让我查一下」\n"
        "- 数据不充分、无法给出可靠结论时 → 说「现有信息不足以回答，建议…」\n"
        "- 文件/路径/配置不确定是否存在时 → 先查再写，不要假设\n"
        "\n"
        "**反面案例（禁止）：**\n"
        "- ❌ 拨测失败却回复「截图在 /tmp/hermes/dial_shots/xxx.png」→ 根本没截图\n"
        "- ❌ curl 404 却回复「API 返回了以下数据：...」→ 根本没数据\n"
        "- ❌ 没查到却回复「根据 XX 官方文档…」→ 根本没找到这份文档\n"
        "- ❌ 文件内容不确定却写「文件中已经定义了 XX」→ 根本没看到\n"
    )

    # 🆕 Thought Stream: 思考流指引
    parts.append(
        "## 💭 你说出声，用户才知道你在\n"
        "记住：你不是一个回答问题后就消失的 API。你是一个坐在用户身边的伙伴。\n"
        "当你沉默时，用户不知道你是在思考、在搜索、还是卡住了。\n"
        "\n"
        "你的 `think` 工具就是你的声音。用它来让用户听见你——\n"
        "\"让我先看看…\" \"嗯，这个问题有意思…\" \"等一下，查个东西…\"\n"
        "\n"
        "不要让你的思维过程成为黑盒。\n"
        "Agent Loop 超过 10 轮后自然降低频率。"
    )

    # 记忆能力说明
    from agent_core.priority_assigner import PRIORITY_GUIDE
    parts.append(
        "## 📝 记忆能力\n"
        "你有长期记忆系统，用于跨会话持久化信息。\n"
        "\n"
        "规则：\n"
        "- 当前对话的完整历史已在上下文中，不需要主动存记忆。\n"
        "- 只有当用户明确说「记住这个」「记一下」「保存这条」时，\n"
        "  才调用 memory(add) 存下来。\n"
        "- memory(read) 用于查看之前会话存的记忆，当前对话不需要。\n"
        "- 用户纠正认知时，用 memory(replace) 更新已有记忆。\n"
        "\n"
        "关于记忆作用域：\n"
        "- 你存的记忆默认属于当前场景，不会出现在其他场景中。\n"
        "- 如果你判断某条信息是用户的通用偏好（跨场景都需要知道），\n"
        "  传 scope='zhu' 参数存为本体级记忆，届时会在所有场景生效。\n"
        "- memory(read) 可以查看本体级记忆和你当前场景的记忆。"
    )

    # 优先级标记说明
    parts.append(PRIORITY_GUIDE)

    # 收敛能力说明
    converge_parts = ["## 🔀 发散与收敛（思维导图工作流）"]
    converge_parts.append(
        "你和用户的完整对话流程：\n"
        "1. 探索阶段：用户说需求 → 你调用函数工具搜索/分析 → 用户补充信息\n"
        "2. 发散阶段：对话中发现新维度时，调用 diverge(scene_id, nodes=[...]) 工具\n"
        "   向思维导图添加节点（你已能看到当前已有节点列表）\n"
        "3. 收敛阶段：当你给出了完整的方案/分析后，调用 converge(scene_id, summary=...) 工具\n"
        "   来自动合并节点、生成优先级队列、产出行动手册\n"
        "4. 执行阶段：收敛完成后，后端自动接管优先级队列的执行，你给出最终总结即可"
    )
    converge_parts.append(
        "### 调用 converge 的时机\n"
        "- ✅ 你刚刚给出了一套完整的方案/计划后，立即调用\n"
        "- ✅ 用户提供了所有关键信息（预算、经验、目标等），你已给出分析\n"
        "- ✅ 用户说「好的」「继续」「进入实战」等认可\n"
        "- ❌ 信息还不全时，继续用 diverge 发散"
    )
    if scene_id:
        converge_parts.append(
            f"\n当前场景信息：\n"
            f"- 场景名: {scene_name or '未知'}\n"
            f"- 场景 ID: {scene_id}"
        )
    parts.append("\n".join(converge_parts))

    # 思维导图状态
    tm_block = _build_tm_status_block(db, scene_id)
    if tm_block:
        parts.append(tm_block)

    return "\n\n".join(parts)


def _build_memory_layer(db, user_content: str, scene_id: str) -> str:
    """Memory Layer — 从缓存按 scope 检索持久记忆

    🆕 v1.5: scope='zhu' 时使用三层选择注入（Context Composer 路径也覆盖）
    """
    if db is None:
        return ""

    # 🆕 v1.5: 本体走三层选择注入
    if not scene_id:
        from agent_core.context_builder import _build_zhu_memory_block
        return _build_zhu_memory_block(db, user_content)

    # 分身场景：保持 top-5 不变
    from agent_core.memory_cache import MemoryCache

    scope = "scene"
    cache = MemoryCache.get_instance()
    memories = cache.get_top_for_context(
        query=user_content,
        scope=scope, context_id=scene_id,
    )
    if not memories:
        return ""
    selected = memories[:5]
    lines = ["## 关于你的一些已知信息（仅供参考，不相关可忽略）"]
    for mem in selected:
        level_icon = {"P0": "🔒", "P1": "⭐", "P2": "📝", "P3": "💤"}
        icon = level_icon.get(mem.get("priority_level", ""), "📝")
        lines.append(f"- {icon} {mem.get('key', '')}: {mem.get('content', '')}")
    return "\n".join(lines)


def _build_profile_layer(db, user_content: str) -> str:
    """Profile Layer — Schema v1.4 用户画像（正式库结构化偏好）

    @deprecated("v1.5: 合并入 Core Tier — P0+P1 已自动同步为 AgentMemory(is_core=True)")

    P0 + P1 始终注入，P2 按话题匹配后选择性注入。
    ⚠️ 只读操作 —— 不修改数据库，不追踪注入次数（tracking 由上层异步处理）
    """
    if db is None:
        return ""
    try:
        from models import UserProfile

        profiles = db.query(UserProfile).filter(
            UserProfile.is_active == True,
        ).order_by(
            UserProfile.priority.asc(),  # P0 > P1 > P2 > P3
        ).all()

        if not profiles:
            return ""

        important = []   # P0 + P1 always injected
        topical = []     # P2 topic-matched

        for p in profiles:
            pri = p.priority or "P2"
            if pri in ("P0", "P1"):
                important.append(p)
            else:
                # P2+ 按话题匹配：检查用户消息是否包含画像关键词
                p_keywords = (p.tags or []) + _extract_keywords(p.content)
                if user_content and any(kw.lower() in user_content.lower() for kw in p_keywords if kw):
                    topical.append(p)

        # 格式化输出 — 匹配设计文档 §3.4 格式
        lines = ["─── 👤 用户画像（你正在跟这样的用户对话） ───"]

        if important:
            # 按 priority 分组：P0 → P1
            p0_profiles = [p for p in important if p.priority == "P0"]
            p1_profiles = [p for p in important if p.priority == "P1"]

            if p0_profiles:
                lines.append("【P0 原则】")
                for p in p0_profiles:
                    scenes = ", ".join(p.source_scenes or []) if p.source_scenes else ""
                    source = f"（{scenes}）" if scenes else ""
                    lines.append(f"- {p.content} {source}")
                lines.append("")

            if p1_profiles:
                lines.append("【P1 偏好】")
                for p in p1_profiles:
                    scenes = ", ".join(p.source_scenes or []) if p.source_scenes else ""
                    source = f"（{scenes}）" if scenes else ""
                    lines.append(f"- {p.content} {source}")
                lines.append("")

        if topical:
            lines.append("【P2 参考】")
            for p in topical:
                lines.append(f"- {p.content}")
            lines.append("")

        if len(lines) == 1:
            return ""  # 只有 header，没有内容

        return "\n".join(lines)

    except Exception as e:
        _log.warning(f"构建画像层失败: {e}")
        return ""


def _extract_keywords(text: str, max_words: int = 5) -> list:
    """从画像内容中提取核心关键词用于话题匹配"""
    # 去除非中英文和数字的字符，取前几个有意义的词
    cleaned = re.findall(r'[\u4e00-\u9fff\w]+', text)
    # 去重保留顺序
    seen = set()
    result = []
    for w in cleaned:
        if w and len(w) >= 2 and w not in seen:
            seen.add(w)
            result.append(w)
    return result[:max_words]


def _build_config_layer(
    scene_name: str,
    scene_id: str,
    db,
    fenshen_config: Optional[dict] = None,
    session_config: Optional[dict] = None,
) -> str:
    """Config Layer — 当前生效的配置层叠（本体 → 分身 → scene → session）"""
    parts = []

    # 从 DB 读取当前模型配置
    if db is not None:
        try:
            from models import Setting
            setting = db.query(Setting).first()
            if setting and setting.routing:
                route = setting.routing.get("scene", {})
                model_name = route.get("model", "deepseek-v4-flash")
                provider = route.get("provider", "deepseek")
                temp = route.get("temperature", 0.3)
                parts.append(f"## 当前模型配置\n模型: {model_name} | Provider: {provider} | Temperature: {temp}")
        except Exception:
            pass

    # 场景收敛参数
    if scene_id and db is not None:
        try:
            from models import Scene
            scene = db.query(Scene).filter(Scene.id == scene_id).first()
            if scene and scene.converge_threshold:
                parts.append(
                    f"## 场景参数\n"
                    f"收敛阈值: {scene.converge_threshold} | "
                    f"自动收敛: {'开启' if scene.converge_enabled else '关闭'} | "
                    f"发散最少轮数: {scene.diverge_min_rounds}"
                )
        except Exception:
            pass

    return "\n\n".join(parts) if parts else ""


def _build_document_layer(scene_id: str, db, doc_deps: Optional[list] = None) -> str:
    """Document Layer — 场景声明的文档摘要

    从 scene.scene_config.document_deps 读取依赖的文档列表，
    从 document_summaries 表或文件系统读取对应级别的摘要。
    """
    if not scene_id or not db:
        return ""

    deps = doc_deps
    if not deps and db:
        # 尝试从 DB 读取 scene config
        try:
            from models import Scene
            sc = db.query(Scene).filter(Scene.id == scene_id).first()
            if sc and hasattr(sc, 'scene_config') and sc.scene_config:
                scfg = sc.scene_config if isinstance(sc.scene_config, dict) else {}
                deps = scfg.get('document_deps')
        except Exception:
            pass

    if not deps:
        return ""

    from agent_core.document_summarizer import get_document as get_doc_summary

    lines = ["## 参考文档"]
    for dep in deps:
        doc_name = dep.get("doc", "") if isinstance(dep, dict) else str(dep)
        level = dep.get("level", "brief") if isinstance(dep, dict) else "brief"
        if not doc_name:
            continue
        summary = get_doc_summary(doc_name, level, db)
        if summary and summary != doc_name:
            lines.append(f"- {doc_name}: {summary}")
        else:
            lines.append(f"- {doc_name}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _build_skill_layer(user_content: str) -> str:
    """Skill Layer — 按相关性检索的 skill 摘要"""
    from agent_core.skill_manager import SkillManager
    sm = SkillManager()
    skills = sm.match_for_context(user_content, max_count=2)
    if not skills:
        return ""
    lines = ["## 参考技能"]
    for skill in skills:
        lines.append(f"### {skill.description}")
        lines.append(skill.content[:500])
    return "\n".join(lines)


def _build_history_layer(history_messages: list[dict]) -> list[dict]:
    """History Layer — 全部聊天，按优先级组织（high → normal → low）

    输入格式: [{"role": "user"|"ai", "content": "...", "priority": "high"|"normal"|"low"}, ...]
    输出格式: 同输入，但按优先级排序
    """
    high = [m for m in history_messages if m.get("priority") == "high"]
    normal = [m for m in history_messages if m.get("priority", "normal") == "normal"]
    low = [m for m in history_messages if m.get("priority") == "low" or m.get("priority") is None]

    result = []
    # high 全部保留，normal 全部保留，low 压缩为摘要
    result.extend(high)
    result.extend(normal)
    if low:
        # low 权重消息合并为一条系统提示
        low_text = "\n".join(m["content"] for m in low if m.get("content"))
        result.append({"role": "system", "content": f"以下为低优先级上下文（仅供参考）：\n{low_text}"})

    return result


def _build_work_output_layer(scene_id: str, db, window: int = 3) -> str:
    """Work Output Layer — 最近 N 轮工具调用的关键帧 + diff

    从 file_snapshots 表读取最近的文件变更快照，提取 diff 块。
    """
    if not scene_id or not db:
        return ""
    try:
        from models import FileSnapshot
        from sqlalchemy import desc

        snapshots = (
            db.query(FileSnapshot)
            .filter(FileSnapshot.scene_id == scene_id)
            .order_by(desc(FileSnapshot.created_at))
            .limit(window)
            .all()
        )
        if not snapshots:
            return ""

        lines = ["## 最近操作记录（仅供参考）"]
        for snap in reversed(snapshots):
            lines.append(f"\n--- 文件: {snap.file_path} ---")
            if snap.diff_summary:
                lines.append(f"【改动摘要】{snap.diff_summary}")
            if snap.diff_content:
                lines.append(f"\n{snap.diff_content}")
        return "\n\n".join(lines)
    except Exception:
        return ""
