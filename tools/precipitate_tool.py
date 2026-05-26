"""Precipitate Tool — 知识沉淀工具

将对话中的关键信息、结论、知识点提取并持久化存储到本地文件。

使用场景：
- 用户说"记一下这个"、"保存这条信息"
- 需要将讨论结论持久化存储
- 知识管理、笔记沉淀

NOTES:
- 沉淀内容存储在 ~/.hermes/precipitate/ 目录下
- 按日期组织文件（YYYY-MM-DD.md）
- 每条沉淀记录包含时间戳、标签和来源
"""

import json
import os
import datetime
from pathlib import Path

# ── 存储路径 ──
PRECIPITATE_DIR = os.path.expanduser("~/.hermes/precipitate")

# ── OpenAI Function-Calling Schema ──

PRECIPITATE_SCHEMA = {
    "name": "precipitate",
    "description": (
        "沉淀知识——将对话中的关键信息、结论、知识点持久化存储到本地笔记。"
        "适合用户说「记一下这个」「保存这条」「记住」时调用。"
        "内容按日期组织，支持标签和来源标记。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "要沉淀的内容，可以是知识点、结论、经验总结等",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签列表，用于分类和检索，如 [\"python\", \"配置\"]",
                "optional": True,
            },
            "source": {
                "type": "string",
                "description": "来源描述，如「用户分享的配置经验」「讨论结论」",
                "optional": True,
            },
        },
        "required": ["content"],
    },
}


def _ensure_dir() -> str:
    """确保沉淀目录存在"""
    os.makedirs(PRECIPITATE_DIR, exist_ok=True)
    return PRECIPITATE_DIR


def _today_file() -> str:
    """获取今日沉淀文件路径"""
    date_str = datetime.date.today().isoformat()
    return os.path.join(PRECIPITATE_DIR, f"{date_str}.md")


def _load_today() -> list[dict]:
    """加载今日已有的沉淀记录"""
    filepath = _today_file()
    if not os.path.exists(filepath):
        return []
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # 简单解析：按 --- 分隔的记录
    blocks = content.split("\n---\n")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        record = {}
        for line in block.split("\n"):
            if line.startswith("- **时间**: "):
                record["time"] = line.replace("- **时间**: ", "")
            elif line.startswith("- **标签**: "):
                record["tags"] = line.replace("- **标签**: ", "")
            elif line.startswith("- **来源**: "):
                record["source"] = line.replace("- **来源**: ", "")
            elif line.startswith("  "):
                record["content"] = line.strip()
        if record:
            records.append(record)
    return records


def precipitate(content: str, tags: list[str] | None = None, source: str = "") -> str:
    """沉淀知识——将内容持久化存储到本地笔记文件

    Args:
        content: 要沉淀的内容
        tags: 标签列表，如 ["python", "配置"]
        source: 来源描述

    Returns:
        JSON 字符串: {success, file_path, summary}
    """
    _ensure_dir()
    filepath = _today_file()

    now = datetime.datetime.now().strftime("%H:%M:%S")
    tag_str = ", ".join(tags) if tags else ""
    source_str = source or ""

    # 组装一条记录
    record_parts = []
    record_parts.append(f"- **时间**: {now}")
    if tag_str:
        record_parts.append(f"- **标签**: {tag_str}")
    if source_str:
        record_parts.append(f"- **来源**: {source_str}")
    record_parts.append(f"  {content}")

    record_block = "\n".join(record_parts)

    # 追加到今日文件
    mode = "a" if os.path.exists(filepath) else "w"
    with open(filepath, "a", encoding="utf-8") as f:
        if mode == "a":
            f.write("\n---\n")
        f.write(record_block)
        f.write("\n")

    summary = content[:60] + "..." if len(content) > 60 else content

    return json.dumps({
        "success": True,
        "file_path": filepath,
        "summary": summary,
        "tags": tags or [],
        "source": source_str or None,
    }, ensure_ascii=False)
