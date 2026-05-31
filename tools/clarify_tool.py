"""Clarify Tool — Agent Loop 的阻塞式追问工具

LLM 在开发场景中调用此工具来问用户问题、做决策确认。
本质是 Agent Loop 内部的同步阻塞调用——callback 函数由外部注入。

使用场景：
- 需求不明确时问用户「你倾向方案 A 还是 B？」
- 写完代码问用户「需要提交吗？」
- 发现冲突问用户「这条规则和那条规则矛盾，怎么处理？」

NOTES:
- 不在开发场景中的 LLM 不应该看到此工具
- 子 Agent 的 toolset 排除了 clarify（子 Agent 不能问用户）
"""

import json
from typing import Callable, Optional

# ── OpenAI Function-Calling Schema ──

CLARIFY_SCHEMA = {
    "name": "clarify",
    "description": (
        "向用户提问，获取确认或选择后再继续。开发场景专用。\n\n"
        "两种模式：\n"
        "1. 多选题 — 提供最多 4 个选项，用户选一个或手动输入\n"
        "2. 开放题 — 不给选项，用户自由输入\n\n"
        "🛡️ **必须用 clarify 的场景**：\n"
        "- 涉及系统级操作（kill 进程、systemctl 停服务、重启后端等）\n"
        "- 有破坏性后果的操作（删除文件/目录、格式化、清空数据）\n"
        "- 需要做重要但不可逆的决策\n"
        "- 需求不明确、有多条可行路径你不知道用户倾向于哪个\n\n"
        "❌ **不需要用 clarify 的场景**：\n"
        "- 纯粹的执行工作（读写文件、搜索、写代码）\n"
        "- 用户已经明确指定了怎么做\n"
        "- 简单的技术选择，两种方案差别不大"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "要向用户提出的问题",
            },
            "choices": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 4,
                "description": (
                    "最多 4 个预设选项。省略此参数则设为开放题（用户自由输入）。"
                    "前端会自动追加「其他（手动输入）」选项。"
                ),
            },
        },
        "required": ["question"],
    },
}


def clarify_tool(
    question: str,
    choices: Optional[list[str]] = None,
    callback: Optional[Callable] = None,
) -> str:
    """执行 clarify 追问。

    Args:
        question: 问题文本
        choices: 可选的多选题选项（最多 4 个）
        callback: 外部注入的阻塞回调函数 callback(question, choices) -> str

    Returns:
        JSON 字符串 {question, choices_offered, user_response}
        或 error 信息
    """
    if not question or not question.strip():
        return json.dumps({"error": "问题文本不能为空"}, ensure_ascii=False)

    question = question.strip()

    # 校验选项
    if choices is not None:
        if not isinstance(choices, list):
            return json.dumps({"error": "choices 必须是字符串列表"}, ensure_ascii=False)
        choices = [str(c).strip() for c in choices if str(c).strip()]
        if not choices:
            choices = None  # 空列表→开放题
        if choices and len(choices) > 4:
            choices = choices[:4]

    if callback is None:
        return json.dumps({
            "error": "Clarify 工具在当前执行上下文不可用（无 callback 注入）"
        }, ensure_ascii=False)

    try:
        user_response = callback(question, choices)
    except Exception as exc:
        return json.dumps({
            "error": f"获取用户输入失败: {exc}"
        }, ensure_ascii=False)

    return json.dumps({
        "question": question,
        "choices_offered": choices,
        "user_response": str(user_response).strip(),
    }, ensure_ascii=False)
