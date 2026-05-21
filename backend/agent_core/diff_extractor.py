"""
Diff 提取器 — 从文件变更中提取结构化 Diff

每轮工具调用后，如果涉及文件修改（write_file、patch），
自动触发 diff_extractor 计算与上次快照的差异。

输出格式：
    {
        "file_path": str,
        "added_lines": [int],
        "removed_lines": [int],
        "hunks": [{"old_start": int, "old_count": int,
                    "new_start": int, "new_count": int,
                    "content": str}],
        "summary": str
    }
"""

import difflib
from typing import Optional


def extract_diff(
    file_path: str,
    current_content: str,
    previous_snapshot: Optional[str] = None,
) -> dict:
    """提取文件当前内容与上次快照的差异

    Args:
        file_path: 文件路径
        current_content: 文件当前内容
        previous_snapshot: 文件上次快照内容（None = 首次写入，无 diff）

    Returns:
        结构化 diff 字典，含 hunks、added_lines、removed_lines、summary
    """
    if previous_snapshot is None:
        return {
            "file_path": file_path,
            "added_lines": list(range(1, len(current_content.splitlines()) + 1)),
            "removed_lines": [],
            "hunks": [],
            "summary": f"首次创建，共 {len(current_content.splitlines())} 行",
        }

    old_lines = previous_snapshot.splitlines(keepends=True)
    new_lines = current_content.splitlines(keepends=True)

    differ = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    )
    diff_text = "\n".join(differ)

    # 没有差异
    if not diff_text:
        return {
            "file_path": file_path,
            "added_lines": [],
            "removed_lines": [],
            "hunks": [],
            "summary": "无变化",
        }

    # 解析 hunks
    hunks = []
    added_lines = []
    removed_lines = []
    current_hunk = None

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            # @@ -old_start,old_count +new_start,new_count @@
            import re
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                current_hunk = {
                    "old_start": int(m.group(1)),
                    "old_count": int(m.group(2) or 1),
                    "new_start": int(m.group(3)),
                    "new_count": int(m.group(4) or 1),
                    "content": line + "\n",
                }
            else:
                current_hunk = {"old_start": 0, "old_count": 0,
                                "new_start": 0, "new_count": 0,
                                "content": line + "\n"}
        elif current_hunk is not None:
            # 跳过 ---/+++ 头
            if line.startswith("--- ") or line.startswith("+++ "):
                continue
            current_hunk["content"] += line + "\n"
            if line.startswith("+"):
                added_lines.append(current_hunk["new_start"] + len(added_lines) - len(removed_lines))
            elif line.startswith("-"):
                removed_lines.append(current_hunk["old_start"] + len(removed_lines))

    if current_hunk:
        hunks.append(current_hunk)

    total_added = len(added_lines)
    total_removed = len(removed_lines)

    return {
        "file_path": file_path,
        "added_lines": added_lines,
        "removed_lines": removed_lines,
        "hunks": hunks,
        "summary": f"新增 {total_added} 行，删除 {total_removed} 行",
    }


def format_diff_block(diff_result: dict) -> str:
    """将 diff 结果格式化为注入 context 的引导文本

    输出格式：
        == 文件: /path/to/file.py ==
        这是最近改动过的代码。如果用户报告了 bug，优先检查此区域：
        - 第 10-13 行: 新增代码
        - 第 8 行: 删除代码
        @@ -8,6 +10,7 @@ ...
    """
    lines = []
    lines.append(f"== 文件: {diff_result['file_path']} ==")
    lines.append("这是最近改动过的代码。如果用户报告了 bug，优先检查此区域：")

    if diff_result["added_lines"]:
        added_groups = _group_consecutive(diff_result["added_lines"])
        for group in added_groups:
            if len(group) == 1:
                lines.append(f"- 第 {group[0]} 行: 新增代码")
            else:
                lines.append(f"- 第 {group[0]}-{group[-1]} 行: 新增代码")

    if diff_result["removed_lines"]:
        removed_groups = _group_consecutive(diff_result["removed_lines"])
        for group in removed_groups:
            if len(group) == 1:
                lines.append(f"- 第 {group[0]} 行: 删除代码")
            else:
                lines.append(f"- 第 {group[0]}-{group[-1]} 行: 删除代码")

    if diff_result["hunks"]:
        lines.append(f"\n改动详情({diff_result['summary']}):")
        for hunk in diff_result["hunks"]:
            lines.append(hunk["content"])

    return "\n".join(lines)


def _group_consecutive(nums: list[int]) -> list[list[int]]:
    """将连续整数分组： [1,2,3,5,6] → [[1,2,3], [5,6]] """
    if not nums:
        return []
    groups = [[nums[0]]]
    for n in nums[1:]:
        if n == groups[-1][-1] + 1:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups
