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
BASE_TOOLS: list[dict] = []

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

    在 context_composer 中，紧随此块之后的「使用说明」会指导 LLM
    通过 function calling 自主调工具，因此这里只做信息性列举。
    """
    if not tools:
        return ""

    lines = [
        "## 可用工具",
        "",
        "以下是当前可调用的所有工具分类列表：",
        "",
    ]

    # 分组：基础 / 搜索 / 浏览器 / 文件 / 数据 / 任务管理 / Agent / 其他
    base_names = {t["name"] for t in BASE_TOOLS}

    categories = {
        "基础（始终可用）": [t for t in tools if t["name"] in base_names],
        "🔍 搜索": [t for t in tools if t.get("category") == "search" and t["name"] not in base_names],
        "🌐 浏览器拨测": [t for t in tools if t.get("category") == "browser"],
        "📁 文件操作": [t for t in tools if t["name"] in ("read_file", "write_file", "patch", "search_files")],
        "🛠 代码执行": [t for t in tools if t["name"] == "run_code"],
        "📊 数据工具": [t for t in tools if t.get("category") == "data" and t["name"] not in base_names and t.get("category") != "browser" and t["name"] not in ("read_file", "write_file", "patch", "search_files", "run_code")],
        "🤖 Agent 工具": [t for t in tools if t.get("category") in ("tools", "agent", "interaction")],
        "🗺 思维导图": [t for t in tools if t["name"] in ("diverge", "converge")],
        "📝 记忆工具": [t for t in tools if t["name"] == "memory"],
        "🐙 Git 工具": [t for t in tools if t["name"].startswith("git_")],
    }

    for category_label, cat_tools in categories.items():
        if not cat_tools:
            continue
        lines.append(f"### {category_label}")
        for t in cat_tools:
            params_desc = ", ".join(
                f'{k}({v.get("type","str")})' for k, v in t.get("parameters", {}).items()
            )
            lines.append(f"- `{t['name']}({params_desc})` — {t['description']}")
        lines.append("")

    lines.append("### 浏览器拨测说明")
    lines.append("browser_dial_test/dial_style/dial_assert 是浏览器自动化工具，")
    lines.append("可用于验证前端页面的 DOM 结构、CSS 样式、Console 日志和 Network 信息。")
    lines.append("**所有场景都可用**——涉及前端验证、页面渲染检查、UI 调试时直接调用。")
    lines.append("")

    return "\n".join(lines)
