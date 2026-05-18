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


# ── 场景聊天的 System Prompt（v0.5 预执行模式） ──
SCENE_SYSTEM_PROMPT = (
    "你是一个专业的AI架构顾问，同时也是坐山客AI工作台的智能助手。\n"
    "系统已自动为你获取了实时数据（天气、景点推荐、装备建议等），数据附在下方。\n"
    "请基于提供的真实数据回复用户，不要编造或猜测数据。\n"
    "用Markdown格式回复，每次回复50-300字，充分且直接。\n"
    "不要拆解任务、不需要创建思维导图。"
)


def _build_memory_block(db, query: str) -> str:
    """从记忆系统提取相关记忆，格式化为注入文本

    返回格式为「仅供参考」的 User Prompt 层内容，不再是 System Prompt 铁律。
    """
    if db is None:
        return ""
    mm = MemoryManager(db)
    memories = mm.get_top_for_context(query, max_count=5)
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
    return "\n".join(lines)


def build_scene_context(
    user_content: str,
    history_messages: Optional[list[dict]] = None,
    matched_tools: Optional[list[dict]] = None,
    tool_results: Optional[list[dict]] = None,
    weather_context: Optional[str] = None,
    user_context: Optional[str] = None,
    db=None,  # 🆕 数据库会话，用于加载记忆
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

    Returns:
        OpenAI 格式的消息列表
    """
    messages = []

    # ── 1. System prompt ──
    system_parts = [SCENE_SYSTEM_PROMPT]

    # ── 1.5 用户输入背景设定 ──
    if user_context:
        system_parts.append(f"=== 用户输入背景设定 ===\n{user_context}\n=====================")

    # ── 2. 记忆块 — 从 system 移到 user prompt（见下方 #8） ──
    memory_block = _build_memory_block(db, user_content)

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
