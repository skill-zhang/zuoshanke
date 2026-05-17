"""工具执行器 — 执行工具函数并返回结果

Pre-execution 模式：在调用 LLM 之前，检测用户查询中是否涉及已注册工具，
如果匹配则先执行工具，将结果注入 context。

支持两种匹配模式：
  1. 注册表匹配（自动）
  2. 【工具调用】标记（LLM 在流式输出中发出的）
"""

import importlib
import json
import os
import sys
from typing import Optional

from .tool_registry import get_tool_by_name, match_tools

TOOLS_DIR = os.path.expanduser("~/zuoshanke/tools")


def _ensure_path():
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)


def execute_tool(name: str, params: dict) -> dict:
    """执行指定工具

    Args:
        name: 工具名（与 registry 中的 name 一致）
        params: 参数 dict

    Returns:
        {"success": bool, "result": any, "error": str | None}
    """
    tool_def = get_tool_by_name(name)
    if not tool_def:
        return {"success": False, "result": None, "error": f"工具 '{name}' 未注册"}

    file_path = tool_def.get("file", "")
    func_name = tool_def.get("function", name)

    try:
        _ensure_path()
        # 动态导入工具模块
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        if module_name.endswith(".py"):
            module_name = module_name[:-3]
        module = importlib.import_module(module_name)

        func = getattr(module, func_name, None)
        if func is None:
            return {"success": False, "result": None, "error": f"函数 '{func_name}' 未在 {file_path} 中找到"}

        result = func(**params)
        return {"success": True, "result": result, "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def try_execute_weather(city: str, forecast_days: int = 3) -> Optional[dict]:
    """快捷执行天气查询"""
    return execute_tool("get_weather", {"city": city, "forecast_days": forecast_days})


def detect_and_preexecute(query: str) -> list[dict]:
    """检测用户查询并提前执行匹配的工具

    在调用 LLM 之前先执行。返回工具结果列表，供 context 注入。

    返回:
        [{"tool": "get_weather", "params": {...}, "result": ..., "success": bool}, ...]
    """
    results = []

    # ── 天气检测 ──
    weather_match = _detect_weather_query(query)
    if weather_match:
        r = execute_tool("get_weather", weather_match)
        results.append({
            "tool": "get_weather",
            "params": weather_match,
            "result": r.get("result") if r.get("success") else r.get("error"),
            "success": r.get("success", False),
        })

    # ── 更多工具类型在后续阶段扩展 ──
    # - web_search: 当用户明确要求搜索时
    # - recommend_attractions: 当用户要求推荐景点时

    return results


_CITIES = ["北京", "天津", "上海", "广州", "深圳", "杭州", "成都",
           "武汉", "南京", "重庆", "西安", "苏州", "长沙", "青岛", "大连",
           "昆明", "厦门", "哈尔滨", "乌鲁木齐", "拉萨",
           "天通苑", "昌平", "海淀", "朝阳", "丰台", "通州", "大兴"]


def _detect_weather_query(query: str) -> Optional[dict]:
    """检测用户消息是否涉及天气查询，返回参数或 None"""
    q = query.strip()
    # 天气关键词
    weather_kw = ["天气", "温度", "下雨", "下雪", "刮风", "气温",
                  "晴", "阴", "雨", "雪", "风", "weather", "temp"]
    has_weather_kw = any(kw in q for kw in weather_kw)

    if not has_weather_kw:
        return None

    # 提取城市名
    city = None
    for c in _CITIES:
        if c in q:
            city = c
            break

    if not city:
        return None

    # 尝试提取预报天数
    forecast_days = 3
    import re
    days_match = re.search(r'(\d+)\s*天', q)
    if days_match:
        forecast_days = min(int(days_match.group(1)), 7)

    return {"city": city, "forecast_days": forecast_days}


def parse_tool_call_markup(text: str) -> Optional[dict]:
    """解析 LLM 输出中的【工具调用】标记

    格式:
        【工具调用】
        {"tool": "get_weather", "params": {"city": "天津"}}
        【/工具调用】

    返回:
        {"tool": str, "params": dict} 或 None
    """
    import re
    pattern = r"【工具调用】\s*(\{.*?\})\s*【/工具调用】"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
