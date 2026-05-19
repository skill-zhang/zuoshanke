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

from .tool_registry import match_tools, format_tools_for_prompt
from .memory_manager import MemoryManager
from .skill_manager import SkillManager


# ── 场景聊天的 System Prompt（兜底用，优先从 DB settings 读取） ──
SCENE_SYSTEM_PROMPT = (
    "你是坐山客在某个领域的专业分身，是用户的AI工作伙伴。\n"
    "你可以调用工具获取实时信息（搜索、代码执行、文件操作等），也可以直接回答用户的问题。\n"
    "请用中文回复，保持简洁自然。\n"
    "\n"
    "## 核心行为准则\n"
    "- 你是有行动能力的 AI Agent，不是教程编写者。用户让你「帮忙搜」「查一下」「分析」时，\n"
    "  直接用工具去做，不要教用户自己操作。用户需要的是结果，不是操作指南。\n"
    "- 当你发现需要真实世界的信息、数据或执行能力时，优先调用工具获取，\n"
    "  而不是告诉用户「你去找一下」或「你下载XX自己看看」。\n"
    "- 你是在帮用户做事，不是在教用户做事。\n"
    "\n"
    "## 对话节奏\n"
    "- 用户说了需求后，先调用工具尝试获取信息，再回答\n"
    "- 如果信息充足，直接给出分析/方案，不要反问用户「你想先做哪一步」\n"
    "- 用户提供补充信息后，更新分析，不要重复追问\n"
)


def _build_memory_block(db, query: str,
                        scope: Optional[str] = None,
                        context_id: Optional[str] = None) -> str:
    """从记忆系统提取相关记忆，格式化为注入文本

    返回格式为「仅供参考」的 User Prompt 层内容，不再是 System Prompt 铁律。

    Args:
        db: 数据库会话
        query: 当前用户查询，用于话题匹配
        scope: 🆕 作用域过滤（zhu | scene | channel），None=全部
        context_id: 🆕 场景/频道ID（scope=scene/channel 时必传）
    """
    if db is None:
        return ""
    mm = MemoryManager(db)
    memories = mm.get_top_for_context(query, max_count=5,
                                      scope=scope, context_id=context_id)
    if not memories:
        return ""
    lines = ["## 关于你的一些已知信息（仅供参考，不相关可忽略）"]
    for mem in memories:
        level_icon = {"P0": "🔒", "P1": "⭐", "P2": "📝", "P3": "💤"}
        icon = level_icon.get(mem["priority_level"], "📝")
        lines.append(f"- {icon} {mem['key']}: {mem['content']}")
    return "\n".join(lines)


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
        lines.append("如果对话已经足够充分，输出 [CONVERGE: ready] 触发收敛。")
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

    # ── 1. System prompt（优先从 DB settings 读取，兜底用 SCENE_SYSTEM_PROMPT） ──
    _scene_sp = SCENE_SYSTEM_PROMPT
    if db is not None:
        try:
            from models import Setting
            _setting = db.query(Setting).first()
            if _setting and _setting.system_prompts:
                _scene_sp = _setting.system_prompts.get("scene") or _scene_sp
        except Exception:
            pass  # 任何异常静默兜底到 SCENE_SYSTEM_PROMPT
    system_parts = [f"# 角色设定\n{_scene_sp}"]

    # ── 1.5 用户输入背景设定 ──
    if user_context:
        system_parts.append(f"=== 用户输入背景设定 ===\n{user_context}\n=====================")

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


def build_agent_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    user_context: Optional[str] = None,
    db=None,
    scene_id: str = "",
    scene_name: str = "",
) -> list[dict]:
    """构建 Agent Loop 路径的上下文 — 带分层管线（DB prompt + 记忆 + skill + 工具列表），无预执行。

    Args:
        user_content: 用户当前消息
        history_messages: 历史消息列表 [{"role": ..., "content": ...}, ...]
        user_context: 用户自定义背景设定
        db: 数据库会话（用于记忆和 DB settings）
        scene_id: 🆕 当前场景 ID（注入后 LLM 可传给 converge 工具）
        scene_name: 🆕 当前场景名称

    Returns:
        OpenAI 格式的消息列表，可作为 run_agent_loop() 的 initial_messages
    """
    from agent_core.agent_loop import _EXCLUDED_TOOLS as _AGENT_EXCLUDED

    messages = []

    # ── 1. System prompt（DB → SCENE_SYSTEM_PROMPT 兜底） ──
    _scene_sp = SCENE_SYSTEM_PROMPT
    if db is not None:
        try:
            from models import Setting
            _setting = db.query(Setting).first()
            if _setting and _setting.system_prompts:
                _scene_sp = _setting.system_prompts.get("scene") or _scene_sp
        except Exception:
            pass

    # ── 分身意识注入（Schema v0.8） ──
    _CORE_PERSONALITY = "你和用户一起构建能力体系，是用户的AI伙伴"
    if scene_name:
        _scene_sp = (
            f"你是坐山客在【{scene_name}】领域的分身，是AI工作台的智能助手。\n"
            f"坐山客是你的本体——{_CORE_PERSONALITY}。\n"
            f"你在这场景中以当前设定行动，但你清楚自己只是分身。\n"
            f"你不知道其他场景中发生了什么，场景间完全隔离。\n"
            f"如果你被问到其他场景的事情，诚实说不知道即可。\n"
            f"\n"
            f"你存的记忆默认归属当前场景，不会出现在其他场景中。\n"
            f"如果你判断某条信息是用户的通用偏好（适用于所有场景），\n"
            f"可以用 scope='zhu' 参数显式存储为本体级记忆。\n\n"
            f"{_scene_sp}"
        )

    system_parts = [f"# 角色设定\n{_scene_sp}"]

    # ── 1.5 用户输入背景设定 ──
    if user_context:
        system_parts.append(f"=== 用户输入背景设定 ===\n{user_context}\n=====================")

    # ── 2. 记忆块 → User 层（见下方） ──
    scope = "scene" if scene_id else "zhu"
    memory_block = _build_memory_block(db, user_content,
                                       scope=scope, context_id=scene_id)

    # ── 3. 技能块 ──
    skill_block = _build_skill_block(user_content)
    if skill_block:
        system_parts.append(skill_block)

    # ── 4. 工具列表（过滤排除项，与 build_tool_definitions 一致） ──
    matched_tools = match_tools(user_content)
    filtered_tools = [t for t in matched_tools if t.get("name") not in _AGENT_EXCLUDED]
    tools_text = format_tools_for_prompt(filtered_tools)
    if tools_text:
        system_parts.append(tools_text)

    # ── 5. 使用说明（LLM 自主调工具版） ──
    usage_parts = [
        "## 使用说明",
        "你可以调用以下工具来完成任务。",
        "工具会在 function calling 中列出，选择合适工具调用即可。",
        "一次只调一个工具，等结果回来后再决定下一步。",
        "如果结果中有错误，分析原因后重试或告知用户。",
    ]
    system_parts.append("\n".join(usage_parts))

    # ── 5.5 记忆能力说明 ──
    system_parts.append(
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

    # ── 5.5a 🆕 思维导图状态 ──
    _tm_block = _build_tm_status_block(db, scene_id)
    if _tm_block:
        system_parts.append(_tm_block)

    # ── 5.6 收敛能力说明 + 场景信息 ──
    scene_parts = ["## 🔀 发散与收敛（思维导图工作流）"]
    scene_parts.append(
        "你和用户的完整对话流程：\n"
        "1. 探索阶段：用户说需求 → 你调用函数工具搜索/分析 → 用户补充信息\n"
        "2. 发散阶段：对话中发现新维度时，调用 diverge(scene_id, nodes=[...]) 工具\n"
        "   向思维导图添加节点（你已能看到当前已有节点列表）\n"
        "3. 收敛阶段：当你给出了完整的方案/分析后，调用 converge(scene_id, summary=...) 工具\n"
        "   来自动合并节点、生成优先级队列、产出行动手册\n"
        "4. 执行阶段：收敛完成后，LLM 按优先级队列执行"
    )
    scene_parts.append(
        "### 调用 converge 的时机\n"
        "- ✅ 你刚刚给出了一套完整的方案/计划后，立即调用\n"
        "- ✅ 用户提供了所有关键信息（预算、经验、目标等），你已给出分析\n"
        "- ✅ 用户说「好的」「继续」「进入实战」等认可\n"
        "- ❌ 信息还不全时，继续用 diverge 发散"
    )
    if scene_id:
        scene_parts.append(
            f"\n当前场景信息：\n"
            f"- 场景名: {scene_name or '未知'}\n"
            f"- 场景 ID: {scene_id}"
        )
    system_parts.append("\n".join(scene_parts))

    messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # ── 6. 跳过工具结果（Agent Loop 无预执行） ──

    # ── 7. 对话历史 ──
    if history_messages:
        for m in history_messages:
            role = "assistant" if m["role"] == "ai" else m["role"]
            messages.append({"role": role, "content": m["content"]})

    # ── 8. 记忆块 + 用户消息 ──
    user_parts = []
    if memory_block:
        user_parts.append(memory_block)
    user_parts.append(user_content)
    user_msg = "\n\n---\n\n".join(user_parts)

    messages.append({"role": "user", "content": user_msg})

    return messages


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
