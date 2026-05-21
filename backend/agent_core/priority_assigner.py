"""
优先级解析器 — 从 LLM 回复中解析 [P:high/normal/low] 标记

标记格式（在回复开头）：
    [P:high] 这是高优先级决策内容...
    [P:normal] 这是普通回复...（默认）
    [P:low] 这是低优先级内容...

规则：
    - 标记必须位于回复的最开头（允许前导空白）
    - 解析后从内容中剥离标记
    - 无标记时默认为 "normal"
"""

import re

_PRIORITY_PATTERN = re.compile(r'^\s*\[P:(high|normal|low)\]\s*')

# 注入 system prompt 中的指引
PRIORITY_GUIDE = (
    "## 回复优先级标注\n"
    "你可以在每轮回复开头加一个权重标记（可选），帮助系统组织上下文：\n"
    "- `[P:high]` — 包含重要决策、用户核心指示、关键结论\n"
    "- `[P:normal]` — 常规回复（默认，可省略标记）\n"
    "- `[P:low]` — 发散内容、试探性信息、闲聊\n"
    "\n"
    "标记格式示例：\n"
    "  [P:high] 根据分析，建议采用方案B...\n"
    "  [P:low] 这个方向很有意思，不过可以先放一放...\n"
    "\n"
    "不带标记的回复默认为 normal。不要在非回复场景（如工具调用）中使用此标记。\n"
)


def extract_priority(text: str) -> tuple[str, str]:
    """解析文本中的优先级标记

    Args:
        text: LLM 回复文本

    Returns:
        (cleaned_text, priority) — priority 为 "high" | "normal" | "low"
    """
    m = _PRIORITY_PATTERN.match(text)
    if m:
        priority = m.group(1)
        cleaned = text[m.end():].lstrip()
        return cleaned, priority
    return text, "normal"
