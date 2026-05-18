"""Agent Loop — LLM 自主调工具的执行引擎

核心流程：
  1. 把 registry.json 工具定义转成 OpenAI function calling 格式
  2. 循环：调 LLM(带 tools) → 解析 tool_calls → 执行工具 → 结果喂回 → 继续
  3. 直到 LLM 返回文本（不再调工具）→ 完成

使用方式：
    from agent_core.agent_loop import run_agent_loop

    for event in run_agent_loop("写一个贪吃蛇游戏", memory_context="..."):
        yield sse_event(...)
"""

import json
import os
import logging
from typing import Generator, Optional

logger = logging.getLogger(__name__)

TOOLS_DIR = os.path.expanduser("~/zuoshanke/tools")
REGISTRY_PATH = os.path.join(TOOLS_DIR, "registry.json")

# ── 这些工具只给预执行用，不给 LLM 自主调用 ──
# 原因：它们需要城市名/场景等上下文参数，预执行通过关键词提取参数更准
_EXCLUDED_TOOLS = {
    "get_weather",           # 预执行 + requires_city
    "recommend_attractions", # 预执行 + 需要天气分类链式调用
    "get_equipment_checklist", # 预执行 + 链式
    "geo_search_poi",        # 预执行 + requires_city
    "geo_route",             # 预执行 + requires_city
    "session_list",          # 预执行触发
    "todo_stats",            # 预执行触发
    "analyze_image",         # 视觉能力，LLM 不需要自主调
    "extract_text",          # 被 read_file 替代
    "extract_text_from_pdf", # 被 read_file 替代
    "todo_update",           # 需要 task_id，LLM 难准确给
    "todo_delete",           # 同上
}

# ── 参数类型映射 ──
_TYPE_MAP = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


def load_registry() -> list[dict]:
    """读取 registry.json 中的所有工具定义"""
    if not os.path.isfile(REGISTRY_PATH):
        logger.warning(f"registry.json 不存在: {REGISTRY_PATH}")
        return []
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tools", [])
    except Exception as e:
        logger.error(f"读取 registry.json 失败: {e}")
        return []


def build_tool_definitions(include_all: bool = False) -> list[dict]:
    """将 zuoshanke 工具注册表转为 OpenAI function calling 格式。

    Args:
        include_all: 为 True 时包含所有工具（含被排除的）

    Returns:
        OpenAI tools 格式列表：
        [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
    """
    tools = load_registry()
    definitions = []

    for t in tools:
        name = t.get("name", "")
        if not include_all and name in _EXCLUDED_TOOLS:
            continue
        if not include_all and name.startswith("todo_"):
            # 只留 todo_list 和 todo_add 给 LLM
            if name not in ("todo_list", "todo_add"):
                continue

        # 转换 parameters
        params = t.get("parameters", {})
        properties = {}
        required = []

        for pname, pinfo in params.items():
            ptype = _TYPE_MAP.get(pinfo.get("type", "string"), "string")
            desc = pinfo.get("description", "")
            optional = pinfo.get("optional", False)

            prop = {
                "type": ptype,
                "description": desc,
            }
            # 枚举类型如果有
            if "enum" in pinfo:
                prop["enum"] = pinfo["enum"]

            properties[pname] = prop
            if not optional:
                required.append(pname)

        definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": t.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })

    return definitions


def build_agent_system_prompt(memory_context: str = "") -> str:
    """构建 Agent 系统提示词"""
    prompt = """你是坐山客 AI 工作台的自主执行引擎。你可以调用工具来完成任务。

## 工作方式
1. 分析用户的任务需求
2. 按需调用工具一步一步执行
3. **一次只调一个工具**，等结果回来后再决定下一步
4. 完成时输出最终回复给用户

## 工具使用原则
- **先查再用**：编码前先用 search_files/read_file 了解项目结构
- **小步快跑**：每次改动后用 run_code 验证，而不是一口气改很多
- **读文件只读必要的部分**：用 offset/limit 参数控制，不要一次性读大文件
- **写文件先检查路径**：确保不会覆盖重要文件
- **遇到错误告诉我**：如果工具执行失败，分析原因再重试

## 编码任务规范
- 创建新文件用 write_file
- 修改已有文件用 patch（支持模糊匹配）
- 执行 shell 命令用 run_code(language="bash")
- 执行 Python 脚本用 run_code(language="python")

## 回复格式
- 每一步简要说明你在做什么
- 完成后用中文总结做了什么、结果如何
- 保持简洁，不要过度解释

## 沙箱约束
- 所有新建文件必须在 ~/zuoshanke/ 目录下
- 不要修改 ~/.hermes/ 和系统文件
- 不要执行危险命令（rm -rf、shutdown 等）"""

    if memory_context:
        prompt += f"\n\n## 对话上下文\n{memory_context}"

    return prompt


def call_llm_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str = "flash",
    temperature: float = 0.3,
) -> dict | None:
    """调 DeepSeek API，支持 function calling。

    Args:
        messages: OpenAI 格式消息列表
        tools: OpenAI 格式工具定义
        model: 'flash' 或 'pro'

    Returns:
        OpenAI 格式的完整 response dict（含 tool_calls 或 content）
        失败返回 None
    """
    from ai_engine import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL_MAP
    from ai_engine import get_settings
    import requests

    if not DEEPSEEK_API_KEY:
        logger.warning("[AgentLoop] DeepSeek API key 未配置")
        return None

    try:
        route_cfg = get_settings("medium")
        _model = DEEPSEEK_MODEL_MAP.get(model, "deepseek-chat")
        temp = route_cfg.get("temperature", temperature)
        mt = route_cfg.get("max_tokens", 8192)

        payload = {
            "model": _model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": mt,
            "tools": tools,
            "tool_choice": "auto",
        }

        # Debug: log message count per role
        role_counts = {}
        for m in messages:
            r = m.get("role", "?")
            role_counts[r] = role_counts.get(r, 0) + 1
        has_tool_calls = any("tool_calls" in m for m in messages)
        logger.info(
            f"[AgentLoop] LLM 请求: roles={role_counts} "
            f"msgs={len(messages)} tools={len(tools)} "
            f"has_tool_call_msg={has_tool_calls}"
        )

        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if hasattr(e, 'response') else 0
        detail = ""
        try:
            detail = e.response.text[:500]
        except Exception:
            pass
        logger.error(f"[AgentLoop] LLM HTTP {status}: {detail}")
        return None
    except requests.exceptions.Timeout:
        logger.error("[AgentLoop] LLM 请求超时")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[AgentLoop] LLM 连接失败: {e}")
        return None
    except Exception as e:
        logger.error(f"[AgentLoop] LLM 调用异常: {e}")
        return None


def run_agent_loop(
    task: str,
    memory_context: str = "",
    tools: Optional[list[dict]] = None,
    model: str = "flash",
    max_steps: int = 25,
) -> Generator[dict, None, None]:
    """运行 Agent Loop：LLM 自主调工具直到完成任务。

    Args:
        task: 用户任务描述
        memory_context: 记忆/上下文信息
        tools: 工具定义列表（None 则自动构建）
        model: 模型名
        max_steps: 最大循环步数（防止死循环）

    Yields:
        dict: 事件对象，格式：
            {"type": "status", "message": "..."}           — 状态更新
            {"type": "tool_start", "tool": "...", "args": {...}}  — 开始调工具
            {"type": "tool_done", "tool": "...", "result": {...}} — 工具执行完成
            {"type": "tool_error", "tool": "...", "error": "..."}  — 工具出错
            {"type": "thinking", "text": "..."}            — LLM 思考过程
            {"type": "token", "text": "..."}               — 最终回复 token
            {"type": "done", "summary": "..."}             — 完成
            {"type": "error", "message": "..."}            — 致命错误
    """
    # 1. 构建工具定义
    if tools is None:
        tools = build_tool_definitions()

    if not tools:
        yield {"type": "error", "message": "没有可用工具，请检查 registry.json"}
        return

    # 2. 构建消息
    system_prompt = build_agent_system_prompt(memory_context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    # 工具名列表（用于日志）
    tool_names = [t["function"]["name"] for t in tools]

    # 3. 执行循环
    from agent_core.tool_executor import execute_tool

    for step in range(max_steps):
        yield {"type": "status", "message": f"第 {step + 1} 步：思考中...（可用工具: {len(tools)} 个）"}

        # 3a. 调 LLM
        response = call_llm_with_tools(messages, tools, model=model)

        if response is None:
            yield {"type": "error", "message": "LLM 调用失败，请检查 API 配置"}
            return

        try:
            choice = response["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError) as e:
            yield {"type": "error", "message": f"LLM 返回格式异常: {e}"}
            return

        # 3b. 检查是否有 tool_calls
        tool_calls = msg.get("tool_calls")

        if not tool_calls:
            # LLM 返回文本 → 完成
            content = msg.get("content", "")
            if content:
                # 流式输出最终回复
                yield {"type": "thinking", "text": content}

            finish_reason = choice.get("finish_reason", "stop")
            yield {
                "type": "done",
                "summary": content or "(无回复)",
                "steps": step + 1,
                "finish_reason": finish_reason,
            }
            return

        # 3c. 有 tool_calls → 先把 assistant 消息加入（含 tool_calls）
        #     再逐个执行工具，结果用 tool role 追加
        #     顺序必须：assistant(tool_calls) → tool → assistant(tool_calls) → tool → ...
        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_msg)

        for tc in tool_calls:
            try:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                raw_args = func.get("arguments", "{}")

                # 解析参数
                if isinstance(raw_args, str):
                    args = json.loads(raw_args)
                else:
                    args = raw_args

                yield {
                    "type": "tool_start",
                    "tool": tool_name,
                    "args": args,
                    "tool_call_id": tc.get("id", ""),
                }

                # 执行工具
                result = execute_tool(tool_name, args)

                if result.get("success"):
                    yield {
                        "type": "tool_done",
                        "tool": tool_name,
                        "result": result.get("result", ""),
                        "tool_call_id": tc.get("id", ""),
                    }
                else:
                    yield {
                        "type": "tool_error",
                        "tool": tool_name,
                        "error": result.get("error", "执行失败"),
                        "tool_call_id": tc.get("id", ""),
                    }

                # 将结果加入对话
                tool_result_content = json.dumps(
                    result.get("result") or result.get("error", ""),
                    ensure_ascii=False,
                )
                # 截断过长结果
                if len(tool_result_content) > 5000:
                    tool_result_content = tool_result_content[:5000] + "\n...(结果过长已截断)"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": tool_result_content,
                })

            except json.JSONDecodeError as e:
                yield {
                    "type": "tool_error",
                    "tool": tool_name if 'tool_name' in locals() else "?",
                    "error": f"参数解析失败: {e}",
                }
            except Exception as e:
                yield {
                    "type": "tool_error",
                    "tool": tool_name if 'tool_name' in locals() else "?",
                    "error": f"工具执行异常: {e}",
                }

        yield {"type": "status", "message": f"第 {step + 1} 步完成，继续..."}

    # 超步数限制
    # 把当前对话摘要给用户
    last_content = ""
    for m in reversed(messages):
        if m["role"] == "assistant" and m.get("content"):
            last_content = m["content"]
            break

    yield {
        "type": "done",
        "summary": f"达到最大步数 ({max_steps})。最后回复: {last_content[:200]}",
        "steps": max_steps,
        "finish_reason": "max_steps",
    }
