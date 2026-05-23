"""Delegate Task 工具 — Agent Loop 调用并行子 Agent

注意：子 Agent 的 toolset 排除 clarify 和 delegate_task。
子 Agent 不能问用户，不能递归派任务。
"""

import json
from typing import Optional

# ── OpenAI Function-Calling Schema ──

DELEGATE_SCHEMA = {
    "name": "delegate_task",
    "description": (
        "派一个或多个子 Agent 并行执行任务。子 Agent 有独立的上下文和工具集，"
        "父 Agent 等待所有子任务完成后拿到结果摘要。\n\n"
        "**两种模式**：\n"
        "1. **单任务** — 提供 goal + context\n"
        "2. **批量（并行）** — 提供 tasks 数组，最多 3 个同时执行\n\n"
        "**何时用**：\n"
        "- 需要同时做多件事（如后端+前端并行开发）\n"
        "- 子任务逻辑独立，无需互相通信\n"
        "- 需要对比不同方案的结果\n\n"
        "**何时不用**：\n"
        "- 逻辑串联的任务（A→B→C）\n"
        "- 需要你亲自做的核心设计决策\n"
        "- 不需要并行加速的简单任务"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "单任务模式下：子任务的目标描述",
            },
            "context": {
                "type": "string",
                "description": "单任务模式下：传递给子任务的上下文信息（文件路径、约束等）",
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "子任务目标"},
                        "context": {"type": "string", "description": "子任务上下文"},
                        "contract_path": {"type": "string", "description": "共享契约文件路径（如 shared/INTERFACE.md），子 Agent 据此实现接口"},
                        "project_rules": {"type": "string", "description": "项目约定（如编码风格、测试规范、分支策略等）"},
                    },
                    "required": ["goal"],
                },
                "description": "批量模式：最多 3 个子任务，并行执行。提供此参数时忽略 goal/context。",
            },
            "contract_path": {
                "type": "string",
                "description": "单任务模式下的共享契约文件路径",
            },
            "project_rules": {
                "type": "string",
                "description": "单任务模式下的项目约定规范",
            },
        },
    },
}


def delegate_task(
    goal: str = "",
    context: str = "",
    tasks: Optional[list[dict]] = None,
    contract_path: str = "",
    project_rules: str = "",
) -> str:
    """执行子任务委派。

    Args:
        goal: 单任务的目标描述
        context: 单任务的上下文
        tasks: 批量模式的任务列表 [{goal, context, contract_path?, project_rules?}, ...]
        contract_path: 单任务模式的共享契约文件路径
        project_rules: 单任务模式的项目约定规范

    Returns:
        JSON 字符串: [{"task": str, "status": str, "summary": str, "steps": int, "error": str|None}, ...]
    """
    from agent_core.delegate_engine import run_delegate_tasks, run_delegate_single

    if tasks:
        # 批量模式
        if len(tasks) > 3:
            tasks = tasks[:3]
        return run_delegate_tasks(tasks)
    else:
        # 单任务模式：透传契约字段
        task = {"goal": goal, "context": context}
        if contract_path:
            task["contract_path"] = contract_path
        if project_rules:
            task["project_rules"] = project_rules
        return run_delegate_single(task)
