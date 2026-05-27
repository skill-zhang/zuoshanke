"""子 Agent 执行引擎 — 同步阻塞版 _run_loop_blocking + ThreadPoolExecutor

用于 delegate_task 工具的并行子任务执行。

子 Agent 的约束：
  - 不能调 clarify（不能问用户）
  - 不能调 delegate_task（不能递归派任务）
  - 不能调 send_message（没有跨平台权限）
  - 结果返回结构化摘要给父 Agent
"""

import json
import logging
import sys
import os

from typing import Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

logger = logging.getLogger(__name__)

# 确保 tools 目录在 sys.path
_TOOLS_PATH = os.path.expanduser("~/zuoshanke/tools")
if _TOOLS_PATH not in sys.path:
    sys.path.insert(0, _TOOLS_PATH)


def _run_loop_blocking(
    task: str,
    tools: list[dict],
    memory_context: str = "",
    model: str = "flash",
    max_steps: int = 25,
    scene_config: dict | None = None,
) -> dict:
    """同步阻塞版 Agent Loop。

    对比 run_agent_loop()（Generator）：
    - 不产生 SSE 事件（子场景不需要前端展示）
    - 返回结构化 dict 而非 yield 事件
    - 不触发 Avatar 心情更新
    - 命中 clarify 工具时返回错误（子 Agent 不能问用户）

    Returns:
        {"success": bool, "summary": str, "files_created": list[str], "steps": int, "error": str | None}
    """
    from agent_core.agent_loop import (
        build_tool_definitions, build_agent_system_prompt,
        call_llm_with_tools, _safe_parse_tool_args, _EXCLUDED_TOOLS,
    )
    from agent_core.tool_executor import execute_tool, set_tool_context, clear_tool_context

    # 1. 构建工具定义
    if not tools:
        from agent_core.agent_loop import build_tool_definitions
        tools = build_tool_definitions()

    if not tools:
        return {"success": False, "summary": "", "steps": 0,
                "error": "没有可用工具，请检查 registry.json"}

    # 2. 构建消息
    system_prompt = (
        "你是坐山客派出的开发子 Agent。\n"
        "你按本任务的 goal 专注完成自己的工作。\n"
        "你不知道其他子 Agent 的存在，完成工作后汇报结果摘要。\n"
        "不要自行扩展任务范围。\n"
        "如果你需要用户决策，请自行做一个合理的选择——你不能问用户。\n\n"
        f"{memory_context}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    tool_names = [t["function"]["name"] for t in tools]
    consecutive_tool_only = 0

    for step in range(max_steps):
        # 死循环检测
        if consecutive_tool_only >= 6 and consecutive_tool_only % 3 == 0:
            messages.append({
                "role": "user",
                "content": f"[系统提示：你已经连续调用了 {consecutive_tool_only} 次工具。"
                           f"如果已有足够信息，请直接给出你的分析结论。]"
            })

        # 调 LLM
        response = call_llm_with_tools(messages, tools, model=model, scene_config=scene_config)
        if response is None:
            return {"success": False, "summary": "", "steps": step + 1,
                    "error": "LLM 调用失败"}

        try:
            choice = response["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError) as e:
            return {"success": False, "summary": "", "steps": step + 1,
                    "error": f"LLM 返回格式异常: {e}"}

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            # LLM 返回文本 → 完成
            content = msg.get("content", "")
            return {
                "success": True,
                "summary": content or "(无回复)",
                "steps": step + 1,
                "finish_reason": choice.get("finish_reason", "stop"),
            }

        # 有 tool_calls
        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_msg)
        consecutive_tool_only += 1

        for tc in tool_calls:
            try:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                raw_args = func.get("arguments", "{}")

                if isinstance(raw_args, str):
                    args = _safe_parse_tool_args(raw_args)
                else:
                    args = raw_args

                # 子 Agent 不能调 clarify
                if tool_name == "clarify":
                    tool_result_content = json.dumps(
                        {"error": "子 Agent 不能问用户问题，请自行决策"},
                        ensure_ascii=False,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": tool_result_content,
                    })
                    continue

                # 执行工具
                set_tool_context(scene_id="")
                try:
                    result = execute_tool(tool_name, args)
                finally:
                    clear_tool_context()

                tool_result_content = json.dumps(
                    result.get("result") or result.get("error", ""),
                    ensure_ascii=False,
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": tool_result_content,
                })

            except json.JSONDecodeError as e:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps({"error": f"参数解析失败: {e}"}),
                })
            except Exception as e:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps({"error": f"工具执行异常: {e}"}),
                })

    # 超步数限制
    last_content = ""
    for m in reversed(messages):
        if m["role"] == "assistant" and m.get("content"):
            last_content = m["content"]
            break

    return {
        "success": False,
        "summary": f"达到最大步数 ({max_steps})。最后回复: {last_content[:200]}",
        "steps": max_steps,
        "error": "max_steps",
    }


# ── Delegate Engine ──


_MAX_WORKERS = 3  # 最大并行子 Agent 数
_CHILD_TIMEOUT = 300  # 每个子 Agent 超时秒数


def _build_child_prompt(task: dict) -> str:
    """构建子 Agent 的完整 prompt（L1 任务层 + L2 契约层 + L3 项目层）

    设计文档 §5.2：
      三层 Context 共享策略确保子 Agent 拿到所需信息但不会接触无关上下文。
    """
    parts = []

    # L1: 任务层
    parts.append(f"## 任务\n{task.get('goal', '')}\n")
    if task.get("context"):
        parts.append(f"## 上下文\n{task['context']}\n")

    # L2: 契约层（如有共享契约文件）
    if task.get("contract_path"):
        parts.append(
            f"## 接口契约\n"
            f"请参照 {task['contract_path']} 中的定义实现接口。\n"
            f"契约文件定义了 API 端点、数据模型和模块边界，是你的核心参照。\n"
        )

    # L3: 项目层
    if task.get("project_rules"):
        parts.append(f"## 项目约定\n{task['project_rules']}\n")

    # 身份声明
    parts.append(
        "## 身份\n"
        "你是坐山客派出的开发子 Agent。\n"
        "你不知道其他子 Agent 的存在，按本任务的 goal 专注完成自己的工作。\n"
        "完成工作后汇报结果摘要，不要自行扩展任务范围。\n"
        "如果你需要用户决策，请自行做一个合理的选择——你不能问用户。"
    )

    return "\n".join(parts)


def _run_single_child(task: dict, tools: list[dict], model: str) -> dict:
    """运行单个子 Agent，返回结构化结果

    task 支持字段：
        goal: str — 任务目标（必需）
        context: str — 上下文信息
        contract_path: str — 共享契约文件路径（L2）
        project_rules: str — 项目约定规范（L3）
    """
    child_prompt = _build_child_prompt(task)
    result = _run_loop_blocking(child_prompt, tools=tools, model=model)
    return {
        "task": task.get("goal", ""),
        "status": "success" if result.get("success") else "error",
        "summary": result.get("summary", ""),
        "steps": result.get("steps", 0),
        "error": result.get("error"),
    }


def run_delegate_tasks(
    tasks: list[dict],
    tools: list[dict] | None = None,
    model: str = "flash",
) -> str:
    """并行执行多个子任务。

    Args:
        tasks: [{"goal": str, "context": str, ...}, ...]
        tools: 子 Agent 可用的工具列表（None=自动构建）
        model: 模型名

    Returns:
        JSON 字符串: [{"task": ..., "status": ..., "summary": ..., "steps": ..., "error": ...}, ...]
    """
    from agent_core.agent_loop import build_tool_definitions
    if tools is None:
        tools = build_tool_definitions()

    # 子 Agent 不允许调的工具
    blocked = {"clarify", "delegate_task", "send_message"}
    child_tools = [t for t in tools if t.get("function", {}).get("name") not in blocked]

    results = []
    if len(tasks) == 1:
        # 单任务 → 直接在当前线程执行
        r = _run_single_child(
            tasks[0],
            child_tools,
            model,
        )
        results.append(r)
    else:
        # 多任务 → ThreadPoolExecutor 并行
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(tasks))) as pool:
            futures = {}
            for task in tasks:
                fut = pool.submit(
                    _run_single_child,
                    task,
                    child_tools,
                    model,
                )
                futures[fut] = task.get("goal", "?")

            for fut in futures:
                goal = futures[fut]
                try:
                    r = fut.result(timeout=_CHILD_TIMEOUT)
                    results.append(r)
                except FuturesTimeoutError:
                    results.append({
                        "task": goal,
                        "status": "timeout",
                        "summary": "",
                        "steps": 0,
                        "error": f"子任务超时 ({_CHILD_TIMEOUT}s)",
                    })
                except Exception as e:
                    results.append({
                        "task": goal,
                        "status": "error",
                        "summary": "",
                        "steps": 0,
                        "error": str(e),
                    })

    # 按输入顺序排序
    goal_order = [t.get("goal", "") for t in tasks]
    ordered = []
    for goal in goal_order:
        for r in results:
            if r["task"] == goal:
                ordered.append(r)
                break
    results = ordered

    return json.dumps(results, ensure_ascii=False)


def run_delegate_single(
    task: dict,
    tools: list[dict] | None = None,
    model: str = "flash",
) -> str:
    """单个子任务模式（便捷接口）

    Args:
        task: 任务 dict，含 goal/context/contract_path/project_rules
        tools: 子 Agent 可用的工具列表

    Returns:
        JSON 字符串: [{"task": ..., "status": ..., "summary": ..., ...}]
    """
    return run_delegate_tasks([task], tools, model)
