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
import threading
from typing import Optional

from .tool_registry import get_all_tools, get_tool_by_name

TOOLS_DIR = os.path.expanduser("~/zuoshanke/tools")

# ── 工具执行线程上下文（用于注入 scene/channel ID 给工具函数） ──
_tool_ctx = threading.local()


def set_tool_context(scene_id: str = "", channel_id: str = ""):
    """设置当前线程的工具执行上下文"""
    _tool_ctx.scene_id = scene_id
    _tool_ctx.channel_id = channel_id


def get_tool_context() -> dict:
    """获取当前线程的工具执行上下文"""
    return {
        "scene_id": getattr(_tool_ctx, "scene_id", ""),
        "channel_id": getattr(_tool_ctx, "channel_id", ""),
    }


def clear_tool_context():
    """清除当前线程的工具执行上下文"""
    _tool_ctx.scene_id = ""
    _tool_ctx.channel_id = ""

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


def execute_tool(name: str, params: dict, extra_kwargs: dict | None = None, max_result_len: int = 3000) -> dict:
    """执行指定工具

    Args:
        name: 工具名（与 registry 中的 name 一致）
        params: 参数 dict
        extra_kwargs: 额外关键字参数（用于注入回调等，如 clarify callback）
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

        # 执行工具函数，传入 params + 可能的额外 kwargs
        if extra_kwargs:
            result = func(**params, **extra_kwargs)
        else:
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

    # ── 兜底：所有数据工具都返回了空数据或错误 → 用 web_search 做最后尝试 ──
    if results and not _has_useful_data(results):
        # 全部数据工具无有效数据 → web_search 兜底
        ws_result = execute_tool("web_search", {"query": query, "max_results": 5})
        if ws_result.get("success"):
            results.append({
                "tool": "web_search",
                "params": {"query": query, "max_results": 5},
                "result": ws_result["result"],
                "success": True,
            })

    return results


def _has_useful_data(results: list[dict]) -> bool:
    """检查预执行结果中是否有有效数据

    判断标准（任一条满足即可）：
    1. 工具成功且 result 中有非空的 items/总结果数 > 0
    2. 工具成功且 result 中不包含 error 字段
    3. web_search 已有结果（避免重复兜底）
    """
    # web_search 已有结果 → 不需要再兜底
    if any(r.get("tool") == "web_search" for r in results):
        return True

    data_tools = {"get_weather", "recommend_attractions", "get_equipment_checklist",
                   "geo_search_poi", "geo_route", "web_search"}
    for r in results:
        if r.get("tool") not in data_tools:
            continue
        if r.get("success"):
            result = r.get("result", {})
            # 纯字符串结果 > 0 字符 → 有用
            if isinstance(result, str) and len(result) > 20:
                return True
            # dict 结果：没有 error 字段且有内容 → 有用
            if isinstance(result, dict):
                if "error" not in result and len(str(result)) > 50:
                    return True
                # 有 items 字段且非空 → 有用
                items = result.get("items", []) if isinstance(result, dict) else []
                if len(items) > 0:
                    return True
            # list 结果有内容 → 有用
            if isinstance(result, list) and len(result) > 0:
                return True
    return False


def _matches_triggers(query: str, triggers: list[str]) -> bool:
    """检查用户查询是否匹配触发关键词"""
    for kw in triggers:
        if kw in query:
            return True
    return False


def _extract_params(tool_name: str, query: str) -> Optional[dict]:
    """根据工具名从查询中提取参数

    v0.6 增强：支持通用参数提取。
    对于已知工具做精确参数提取；未知工具尝试从 registry 参数定义自动提取。

    Returns:
        dict: 参数字典，或 None（表示参数不足，跳过预执行）
    """
    # ── 已知工具的精确提取 ──
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
        weather_cat = None
        city = _extract_city(query)
        if city:
            weather_cat = _get_weather_category_for_city(city)
        if not weather_cat:
            return None
        scene_type = _extract_scene_type(query)
        params = {"weather_category": weather_cat}
        if scene_type:
            params["scene_type"] = scene_type
        return params

    elif tool_name == "geo_search_poi":
        city = _extract_city(query)
        if not city:
            return None
        # 推断分类
        cat_map = {
            "吃": "restaurant", "餐厅": "restaurant", "美食": "restaurant",
            "买": "shop", "购物": "shop", "逛": "shop",
            "住": "hotel", "酒店": "hotel",
            "玩": "attraction", "景点": "attraction", "公园": "park",
        }
        category = None
        for kw, cat in cat_map.items():
            if kw in query:
                category = cat
                break
        params = {"city": city}
        if category:
            params["category"] = category
        return params

    elif tool_name == "geo_route":
        # 尝试提取两个地点
        parts = [p.strip() for p in re.split(r'[到至去>]', query, maxsplit=1)]
        if len(parts) >= 2 and parts[0] and parts[1]:
            origin, dest = parts[0], parts[1]
            # 去掉工具名关键词
            from config.matching_rules import ROUTE_KEYWORDS
            for kw in ROUTE_KEYWORDS:
                dest = dest.replace(kw, "").strip()
            if origin and dest:
                # 推断出行方式
                from config.matching_rules import MODE_KEYWORDS
                mode = "driving"
                for m, kws in MODE_KEYWORDS.items():
                    if any(kw in query for kw in kws):
                        mode = m
                        break
                return {"origin": origin, "destination": dest, "mode": mode}
        return None

    elif tool_name == "todo_add":
        # 提取任务内容 — 去掉触发关键词后的剩余文本
        from config.matching_rules import TODO_TRIGGERS
        content = query
        for t in TODO_TRIGGERS:
            content = content.replace(t, "").strip()
        if not content:
            return None
        return {"content": content}

    elif tool_name == "todo_list":
        # 提取状态过滤
        status = None
        if "已完成" in query or "完成" in query:
            status = "completed"
        elif "进行中" in query or "正在进行" in query:
            status = "in_progress"
        elif "待办" in query or "未完成" in query:
            status = "pending"
        if status:
            return {"status": status}
        return {}  # 无参数也允许（列出全部）

    elif tool_name == "session_list":
        return {}  # 无参数，直接返回

    # ── 通用提取：读取 registry 定义，尝试自动匹配参数 ──
    return _generic_extract_params(tool_name, query)


def _generic_extract_params(tool_name: str, query: str) -> Optional[dict]:
    """通用参数提取 — 根据 registry 参数定义自动匹配

    遍历工具的 parameters 定义，对每个参数尝试从 query 中提取：
    - type=string → 取参数名或 description 中含有的关键词
    - type=integer → 从 query 中提取数字
    - type=number → 提取浮点数
    """
    from .tool_registry import get_tool_by_name

    tool_def = get_tool_by_name(tool_name)
    if not tool_def:
        return None

    params_def = tool_def.get("parameters", {})
    if not params_def:
        return {}  # 无参数工具

    extracted = {}
    all_found = True

    for param_name, param_info in params_def.items():
        optional = param_info.get("optional", False)
        param_type = param_info.get("type", "string")

        if param_type == "string":
            # 尝试从 query 中匹配参数名或描述关键词
            desc = param_info.get("description", "")
            # 检查描述中的关键词是否在 query 中
            for kw in [param_name, desc[:10]]:
                if isinstance(kw, str) and kw and kw in query:
                    # 找到匹配，但无法精确提取值，跳过预执行
                    pass
        elif param_type in ("integer", "number"):
            nums = re.findall(r'(\d+)', query)
            if nums:
                extracted[param_name] = int(nums[0])

        # 必填参数无法提取 → 跳过
        if not optional and param_name not in extracted:
            # 检查是否是"可选"的（带"optional"标记）
            desc = param_info.get("description", "")
            if "optional" not in desc.lower():
                # 不确定的可选性，保守跳过
                all_found = False

    if not all_found and not extracted:
        return None

    return extracted if extracted else {}


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
