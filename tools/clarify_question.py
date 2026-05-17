"""追问询问工具 — 当工具参数不足或信息缺失时，向用户追问

功能：
- clarify_check_params: 检查工具参数是否完整，返回缺失信息
- clarify_ask: 生成标准的追问文本
- clarify_format_missing: 格式化缺失信息为可读追问

使用场景：
在预执行或工具调用时发现参数不足（如查天气没有城市名），
使用此工具生成友好追问，让 AI 回复告知用户缺什么信息。
"""


def clarify_check_params(params: dict, required: list[str]) -> list[str]:
    """检查必填参数，返回缺失字段列表

    Args:
        params: 用户已提供的参数字典
        required: 必填字段名列表

    Returns:
        缺失的字段名列表（空 = 全齐）
    """
    missing = []
    for field in required:
        val = params.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)
    return missing


def clarify_ask(missing_fields: list[str], tool_name: str = "",
                context: str = "", extra_hints: dict = None) -> str:
    """生成标准化的追问文本

    Args:
        missing_fields: 缺失参数列表（如 ["city", "date"]）
        tool_name: 工具名（可选）
        context: 上下文补充说明
        extra_hints: 额外提示 {字段名: 说明}

    Returns:
        追问文本（中文）
    """
    if not missing_fields:
        return ""

    # 字段名称映射（英文→中文）
    FIELD_CN = {
        "city": "城市",
        "date": "日期",
        "start_date": "出发日期",
        "end_date": "返回日期",
        "location": "地点",
        "query": "搜索词",
        "keyword": "关键词",
        "url": "链接地址",
        "file_path": "文件路径",
        "max_results": "结果数量",
        "category": "分类",
        "destination": "目的地",
        "origin": "出发地",
        "budget": "预算",
        "days": "天数",
        "people": "人数",
        "scene_type": "场景类型",
        "weather_category": "天气类型",
        "code": "代码内容",
        "language": "编程语言",
    }

    parts = []

    if tool_name:
        parts.append(f"为了{'使用「' + tool_name + '」功能' if tool_name else ''}")

    parts.append("请告诉我以下信息：")

    for field in missing_fields:
        cn = FIELD_CN.get(field, field)
        hint = ""
        if extra_hints and field in extra_hints:
            hint = f"（{extra_hints[field]}）"
        parts.append(f"- **{cn}**{hint}")

    if context:
        parts.append(f"\n💡 {context}")

    return "\n".join(parts)


def clarify_format_missing(params: dict, required: list[str],
                           tool_name: str = "", param_labels: dict = None) -> str | None:
    """一站式检查+生成追问

    先检查必填参数是否缺失，如果有缺失直接生成追问文本。

    Args:
        params: 用户已提供的参数
        required: 必填字段列表
        tool_name: 工具名
        param_labels: 自定义字段标签 {字段名: 中文名}

    Returns:
        None（参数齐全）或追问文本字符串
    """
    missing = clarify_check_params(params, required)
    if not missing:
        return None

    return clarify_ask(missing, tool_name, extra_hints=param_labels)


# CLI 测试入口
if __name__ == "__main__":
    import sys

    # 测试 1：检查参数
    missing = clarify_check_params({"city": "北京"}, ["city", "date"])
    print(f"测试1 - 缺失字段: {missing}")

    # 测试 2：生成追问
    if missing:
        print(f"\n测试2 - 追问:\n{clarify_ask(missing, 'get_weather')}")

    # 测试 3：一键式
    result = clarify_format_missing({"city": "北京"}, ["city", "date"],
                                     "get_weather", {"date": "格式如 2026-05-18"})
    print(f"\n测试3 - 一键式:\n{result}")
