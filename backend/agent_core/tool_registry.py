"""工具注册表 — 管理基础工具 + registry.json 中的动态工具

职责:
  1. 定义基础工具（永远可用）
  2. 读取 tools/registry.json 中的注册工具
  3. 按需匹配工具（根据用户查询语义匹配）
  4. 提供格式化工具列表供 context 注入

v0.5：预执行模式 — LLM 不再需要手动输出【工具调用】标记，
工具由系统在回答前自动执行。
"""

import json
import os
import sys
from typing import Optional

# ── 基础工具（永远注入） ──
BASE_TOOLS = [
    {
        "name": "web_fetch",
        "description": "抓取指定 URL 的网页文本内容",
        "parameters": {
            "url": {"type": "string", "description": "网页 URL"}
        },
        "returns": "网页正文文本",
        "category": "search",
    },
    {
        "name": "get_current_time",
        "description": "获取当前日期和时间",
        "parameters": {},
        "returns": "当前日期和时间字符串",
        "category": "system",
    },
]

# ── 动态工具缓存 ──
_registry_cache = None
_registry_mtime = 0

from config.paths import TOOLS_DIR
REGISTRY_PATH = os.path.join(TOOLS_DIR, "registry.json")


def _add_tools_to_path():
    """确保 tools/ 目录在 sys.path 中，以便动态 import"""
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)


def _load_registry() -> list[dict]:
    """读取 registry.json，带缓存（文件 mtime 检测）"""
    global _registry_cache, _registry_mtime
    try:
        mtime = os.path.getmtime(REGISTRY_PATH)
        if _registry_cache is not None and mtime == _registry_mtime:
            return _registry_cache
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        tools = data.get("tools", [])
        _registry_cache = tools
        _registry_mtime = mtime
        return tools
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def register_tool(name: str, description: str, file: str, function: str,
                  parameters: dict, returns: str = "", category: str = "data",
                  verified: bool = False) -> bool:
    """注册一个新工具到 registry.json"""
    entry = {
        "name": name,
        "description": description,
        "file": file,
        "function": function,
        "parameters": parameters,
        "returns": returns,
        "category": category,
        "verified": verified,
    }
    tools = _load_registry()
    # 同名去重
    tools = [t for t in tools if t.get("name") != name]
    tools.append(entry)
    try:
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump({"tools": tools}, f, ensure_ascii=False, indent=2)
        global _registry_cache, _registry_mtime
        _registry_cache = tools
        _registry_mtime = os.path.getmtime(REGISTRY_PATH)
        return True
    except Exception:
        return False


def get_all_tools() -> list[dict]:
    """获取全部工具（基础工具 + 注册工具）"""
    return BASE_TOOLS + _load_registry()


def match_tools(query: str, max_tools: int = 5) -> list[dict]:
    """根据用户查询匹配相关工具

    v0.5 Phase 1 用简单关键词匹配，后续升级为语义匹配。
    """
    tools = get_all_tools()
    if not query:
        return tools[:max_tools]

    query_lower = query.lower()
    scored = []
    for t in tools:
        score = 0
        desc = (t.get("description", "") + " " + t.get("name", "")).lower()
        params_desc = " ".join(
            p.get("description", "") for p in t.get("parameters", {}).values()
        ).lower()

        # 关键词匹配
        for kw in query_lower.split():
            if len(kw) < 2:
                continue
            if kw in desc or kw in params_desc:
                score += 1

        # 城市名检测（天气工具的强信号）
        if t["name"] == "get_weather":
            from config.matching_rules import WEATHER_CITIES
            if any(city in query for city in WEATHER_CITIES):
                score += 3

        if score > 0:
            scored.append((score, t))

    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:max_tools]]


def get_tool_by_name(name: str) -> Optional[dict]:
    """按名称查找工具"""
    for t in get_all_tools():
        if t["name"] == name:
            return t
    return None


def format_tools_for_prompt(tools: list[dict]) -> str:
    """将工具列表格式化为 prompt 可读文本

    预执行模式：工具由系统自动执行，LLM 只需基于结果回复即可。
    """
    if not tools:
        return ""

    lines = [
        "## 可用工具",
        "",
        "以下工具系统会在需要时自动执行，你无需输出【工具调用】标记：",
        "",
    ]

    # 分组
    base_names = {t["name"] for t in BASE_TOOLS}
    base = [t for t in tools if t["name"] in base_names]
    extra = [t for t in tools if t["name"] not in base_names]

    if base:
        lines.append("### 基础工具（始终可用）")
        for t in base:
            params_desc = ", ".join(
                f'{k}({v.get("type","str")})' for k, v in t.get("parameters", {}).items()
            )
            lines.append(f"- `{t['name']}({params_desc})` - {t['description']}")
        lines.append("")

    if extra:
        lines.append("### 任务相关工具")
        for t in extra:
            params_desc = ", ".join(
                f'{k}({v.get("type","str")})' for k, v in t.get("parameters", {}).items()
            )
            lines.append(f"- `{t['name']}({params_desc})` - {t['description']}")
        lines.append("")

    lines.append("### 注意事项")
    lines.append("- 所有数据工具（天气、推荐、装备清单等）由系统自动执行并附上结果。")
    lines.append("- 你只需基于系统提供的真实数据回复用户，不需要自己编造数据。")
    lines.append("- 如果系统没有提供所需数据，如实告知用户即可。")
    lines.append("")

    return "\n".join(lines)
