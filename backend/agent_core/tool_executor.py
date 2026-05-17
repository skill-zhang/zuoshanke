"""工具执行器 — 执行工具函数并返回结果

Pre-execution 模式：在调用 LLM 之前，检测用户查询中是否涉及已注册工具，
如果匹配则先执行工具，将结果注入 context。

v0.5 通用预执行：
  - 从 registry.json 读取所有 verified 工具的 preexecute 配置
  - 按触发器关键词匹配用户查询
  - 提取参数并执行
  - 支持链式工具（装备检查依赖天气分类）

支持两种匹配模式：
  1. 注册表驱动预执行（自动 — 根据 preexecute 配置）
  2. 【工具调用】标记（LLM 在流式输出中发出的 — 兜底）
"""

import importlib
import json
import os
import re
import sys
from typing import Optional

from .tool_registry import get_all_tools, get_tool_by_name

TOOLS_DIR = os.path.expanduser("~/zuoshanke/tools")

# ── 常见城市列表（参数提取用） ──
CITIES = ["北京", "天津", "上海", "广州", "深圳", "杭州", "成都",
          "武汉", "南京", "重庆", "西安", "苏州", "长沙", "青岛", "大连",
          "昆明", "厦门", "哈尔滨", "乌鲁木齐", "拉萨",
          "天通苑", "昌平", "海淀", "朝阳", "丰台", "通州", "大兴",
          "沈阳", "济南", "宁波", "福州", "合肥", "郑州", "贵阳", "东莞",
          "石家庄", "太原", "海口", "三亚", "桂林", "丽江"]


def _ensure_path():
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)


def execute_tool(name: str, params: dict, max_result_len: int = 3000) -> dict:
    """执行指定工具

    Args:
        name: 工具名（与 registry 中的 name 一致）
        params: 参数 dict
        max_result_len: 结果最大截断长度（防 context 撑爆）

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
            return {"success": False, "result": None,
                    "error": f"函数 '{func_name}' 未在 {file_path} 中找到"}

        result = func(**params)
        # 截断超大结果（安全截断，不破坏 JSON）
        result = _safe_truncate_result(result, max_result_len)
        return {"success": True, "result": result, "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def _safe_truncate_result(result, max_len: int):
    """安全截断工具结果：对 dict/list 做深度截断，避免 JSON 解析错误"""
    result_str = json.dumps(result, ensure_ascii=False)
    if len(result_str) <= max_len:
        return result

    if isinstance(result, dict):
        # 截断长文本字段
        truncated = {}
        for k, v in result.items():
            if isinstance(v, str) and len(v) > 200:
                truncated[k] = v[:200] + "..."
            elif isinstance(v, list) and len(v) > 8:
                truncated[k] = v[:8] + ["..."]
            else:
                truncated[k] = v
        # 如果截断后还是太长，只保留关键字段
        result_str2 = json.dumps(truncated, ensure_ascii=False)
        if len(result_str2) > max_len:
            # 关键字段优先
            key_fields = ["city", "category", "label", "desc", "temp", "total",
                          "items", "must_have", "recommended"]
            minimal = {k: truncated[k] for k in key_fields if k in truncated}
            return minimal
        return truncated
    elif isinstance(result, list):
        return result[:5] + ["..."]
    else:
        # 兜底：返回摘要
        return {"summary": result_str[:max_len]}


# ═══════════════════════════════════════════
#  参数提取工具函数
# ═══════════════════════════════════════════

def _extract_city(query: str) -> Optional[str]:
    """从查询中提取城市名"""
    for c in CITIES:
        if c in query:
            return c
    return None


def _extract_forecast_days(query: str) -> int:
    """从查询中提取预报天数（默认 3）"""
    days_match = re.search(r'(\d+)\s*天', query)
    if days_match:
        return min(int(days_match.group(1)), 7)
    return 3


def _extract_scene_type(query: str) -> Optional[str]:
    """从查询中提取场景类型（装备清单用）"""
    scene_map = {
        "滨水": "滨水", "海边": "滨水", "河边": "滨水", "水上": "滨水",
        "山": "山地", "登山": "山地", "徒步": "山地", "爬山": "山地",
        "公园": "公园", "野餐": "公园", "露营": "公园",
        "休闲": "休闲", "咖啡馆": "休闲", "看书": "休闲",
    }
    for kw, scene in scene_map.items():
        if kw in query:
            return scene
    return None


def _get_weather_category_for_city(city: str) -> Optional[str]:
    """获取某个城市当前的天气分类（供链式工具使用）"""
    try:
        _ensure_path()
        from weather import get_weather
        from recommend import classify_weather
        weather_data = get_weather(city)
        return classify_weather(weather_data)
    except Exception:
        return None


def _get_weather_data_for_city(city: str) -> Optional[dict]:
    """获取某个城市的原始天气数据"""
    try:
        _ensure_path()
        w = execute_tool("get_weather", {"city": city, "forecast_days": 3})
        if w.get("success"):
            return w["result"]
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════
#  预执行 — 注册表驱动
# ═══════════════════════════════════════════

def _get_preexecutable_tools() -> list[dict]:
    """获取所有启用了预执行的已验证工具"""
    all_tools = get_all_tools()
    return [
        t for t in all_tools
        if t.get("verified") and t.get("preexecute", {}).get("enabled")
    ]


def detect_and_preexecute(query: str) -> list[dict]:
    """检测用户查询并提前执行匹配的工具

    在调用 LLM 之前先执行。返回工具结果列表，供 context 注入。

    Returns:
        [{"tool": str, "params": {...}, "result": ..., "success": bool}, ...]
    """
    results = []

    if not query or not query.strip():
        return results

    # ── 遍历所有启用了预执行的工具 ──
    for tool in _get_preexecutable_tools():
        tool_name = tool["name"]
        triggers = tool.get("preexecute", {}).get("triggers", [])
        requires_city = tool.get("preexecute", {}).get("requires_city", False)

        # 检查触发器关键词
        if not _matches_triggers(query, triggers):
            continue

        # ── 按工具类型提取参数 ──
        params = _extract_params(tool_name, query)
        if params is None:
            continue  # 参数不足，跳过

        # ── 执行工具 ──
        r = execute_tool(tool_name, params)
        results.append({
            "tool": tool_name,
            "params": params,
            "result": r.get("result") if r.get("success") else r.get("error"),
            "success": r.get("success", False),
        })

    # ── 链式工具：如果触发了装备清单但没有天气数据，先查天气 ──
    _maybe_chain_weather_for_equipment(results, query)

    return results


def _matches_triggers(query: str, triggers: list[str]) -> bool:
    """检查用户查询是否匹配触发关键词"""
    for kw in triggers:
        if kw in query:
            return True
    return False


def _extract_params(tool_name: str, query: str) -> Optional[dict]:
    """根据工具名从查询中提取参数

    Returns:
        dict: 参数字典，或 None（表示参数不足，跳过预执行）
    """
    if tool_name == "get_weather":
        city = _extract_city(query)
        if not city:
            return None
        return {"city": city, "forecast_days": _extract_forecast_days(query)}

    elif tool_name == "recommend_attractions":
        city = _extract_city(query)
        if not city:
            return None
        return {"city": city}

    elif tool_name == "get_equipment_checklist":
        # 先从已有weather结果或查询中获取天气分类
        weather_cat = None
        city = _extract_city(query)
        if city:
            weather_cat = _get_weather_category_for_city(city)
        if not weather_cat:
            # 用户可能直接问装备，没问天气，尝试拿当前城市天气
            return None  # 没有天气分类，跳过（后续链式补偿）
        scene_type = _extract_scene_type(query)
        params = {"weather_category": weather_cat}
        if scene_type:
            params["scene_type"] = scene_type
        return params

    return None


def _maybe_chain_weather_for_equipment(results: list[dict], query: str):
    """如果触发了装备清单但没有天气数据，自动补查天气"""
    has_equipment = any(r["tool"] == "get_equipment_checklist" for r in results)
    if not has_equipment:
        return

    # 检查装备清单结果是否成功（需要weather_category） 
    equip_result = next((r for r in results if r["tool"] == "get_equipment_checklist"), None)
    if equip_result and equip_result.get("success"):
        return  # 已有成功结果

    # 检查是否已经有天气结果
    has_weather = any(r["tool"] == "get_weather" for r in results)
    if not has_weather:
        city = _extract_city(query)
        if city:
            w = execute_tool("get_weather", {"city": city, "forecast_days": 3})
            results.append({
                "tool": "get_weather",
                "params": {"city": city, "forecast_days": 3},
                "result": w.get("result") if w.get("success") else w.get("error"),
                "success": w.get("success", False),
            })

    # 拿天气分类重新执行装备工具
    weather_result = next((r for r in results if r["tool"] == "get_weather"), None)
    if weather_result and weather_result.get("success"):
        try:
            _ensure_path()
            from recommend import classify_weather
            wd = weather_result["result"]
            weather_cat = classify_weather(wd)
            scene_type = _extract_scene_type(query)
            params = {"weather_category": weather_cat}
            if scene_type:
                params["scene_type"] = scene_type
            r = execute_tool("get_equipment_checklist", params)
            results.append({
                "tool": "get_equipment_checklist",
                "params": params,
                "result": r.get("result") if r.get("success") else r.get("error"),
                "success": r.get("success", False),
            })
        except Exception as e:
            pass  # 链式失败不影响其他工具结果


# ═══════════════════════════════════════════
#  快捷执行（兼容旧接口）
# ═══════════════════════════════════════════

def try_execute_weather(city: str, forecast_days: int = 3) -> Optional[dict]:
    """快捷执行天气查询"""
    return execute_tool("get_weather", {"city": city, "forecast_days": forecast_days})


def try_execute_recommend(city: str) -> Optional[dict]:
    """快捷执行景点推荐"""
    return execute_tool("recommend_attractions", {"city": city})


# ═══════════════════════════════════════════
#  解析 LLM 输出的【工具调用】标记（兜底）
# ═══════════════════════════════════════════

def parse_tool_call_markup(text: str) -> Optional[dict]:
    """解析 LLM 输出中的【工具调用】或【缺工具】标记

    格式:
        【工具调用】
        {"tool": "get_weather", "params": {"city": "天津"}}
        【/工具调用】

    也兼容:
        【缺工具】
        {"capability": "...", "suggested_name": "...", "parameters": {...}}
        【/缺工具】
        → 转为 {"tool": suggested_name, "params": parameters}

    返回:
        {"tool": str, "params": dict} 或 None
    """
    # 匹配 【工具调用】
    pattern1 = r"【工具调用】\s*(\{.*?\})\s*【/工具调用】"
    match = re.search(pattern1, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 匹配 【缺工具】→ 转为 tool 调用
    pattern2 = r"【缺工具】\s*(\{.*?\})\s*【/缺工具】"
    match = re.search(pattern2, text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            tool_name = data.get("suggested_name", "")
            if not tool_name:
                return None
            return {"tool": tool_name, "params": data.get("parameters", {})}
        except json.JSONDecodeError:
            pass

    return None
