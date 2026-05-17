#!/usr/bin/env python3
"""任务管理工具 - 基于 JSON 文件存储，纯标准库实现。"""

import json
import os
import uuid
from datetime import datetime

DATA_DIR = os.path.expanduser("~/zuoshanke/data")
DATA_FILE = os.path.join(DATA_DIR, "todos.json")

VALID_STATUSES = ("pending", "in_progress", "completed")
VALID_PRIORITIES = ("high", "medium", "low")


def _ensure_data_file():
    """确保数据文件和目录存在。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_todos(todos):
    """安全写入数据文件。"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def _now_str():
    """返回当前时间的 ISO 格式字符串。"""
    return datetime.now().isoformat()


def _find_task(todos, task_id):
    """按 id 查找任务，返回 (index, task) 或 (None, None)。"""
    for i, t in enumerate(todos):
        if t["id"] == task_id:
            return i, t
    return None, None


def todo_list(status=None):
    """列出所有任务，可按状态过滤。

    Args:
        status: 可选过滤值 - "pending" / "in_progress" / "completed"

    Returns:
        包含任务信息的列表，每个任务为字典格式。
    """
    todos = _ensure_data_file()
    if status:
        if status not in VALID_STATUSES:
            return f"错误：无效的状态值 '{status}'，有效值为：{', '.join(VALID_STATUSES)}"
        filtered = [t for t in todos if t["status"] == status]
        if not filtered:
            return f"暂无状态为「{status}」的任务。"
        return filtered
    if not todos:
        return "暂无任何任务。"
    return todos


def todo_add(content, priority="medium"):
    """添加一条新任务。

    Args:
        content: 任务内容（必填）
        priority: 优先级，可选 high / medium / low，默认为 medium

    Returns:
        创建成功的任务字典。
    """
    if not content or not content.strip():
        return "错误：任务内容不能为空。"

    priority = priority.lower()
    if priority not in VALID_PRIORITIES:
        return f"错误：无效的优先级 '{priority}'，有效值为：{', '.join(VALID_PRIORITIES)}"

    now = _now_str()
    task = {
        "id": str(uuid.uuid4())[:8],
        "content": content.strip(),
        "status": "pending",
        "priority": priority,
        "created_at": now,
        "updated_at": now,
    }

    todos = _ensure_data_file()
    todos.append(task)
    _save_todos(todos)

    return task


def todo_update(task_id, **updates):
    """更新任务信息。

    支持更新的字段：content, status, priority。
    不区分大小写。

    Args:
        task_id: 任务 ID
        **updates: 要更新的字段键值对

    Returns:
        更新后的任务字典。
    """
    todos = _ensure_data_file()
    idx, task = _find_task(todos, task_id)

    if idx is None:
        return f"错误：未找到 ID 为「{task_id}」的任务。"

    allowed_fields = {"content", "status", "priority"}
    changed = False

    for key, value in updates.items():
        if key not in allowed_fields:
            return f"错误：不支持更新字段 '{key}'，仅支持：{', '.join(sorted(allowed_fields))}"

        if key == "status" and value not in VALID_STATUSES:
            return f"错误：无效的状态值 '{value}'，有效值为：{', '.join(VALID_STATUSES)}"

        if key == "priority" and value not in VALID_PRIORITIES:
            return f"错误：无效的优先级 '{value}'，有效值为：{', '.join(VALID_PRIORITIES)}"

        if key == "content" and (not value or not value.strip()):
            return "错误：任务内容不能为空。"

        if key == "content":
            value = value.strip()

        if task[key] != value:
            task[key] = value
            changed = True

    if changed:
        task["updated_at"] = _now_str()
        todos[idx] = task
        _save_todos(todos)

    return task


def todo_delete(task_id):
    """删除指定任务。

    Args:
        task_id: 任务 ID

    Returns:
        成功返回 True，失败返回错误描述字符串。
    """
    todos = _ensure_data_file()
    idx, task = _find_task(todos, task_id)

    if idx is None:
        return f"错误：未找到 ID 为「{task_id}」的任务。"

    todos.pop(idx)
    _save_todos(todos)
    return True


def todo_stats():
    """获取任务统计信息。

    Returns:
        包含统计信息的字典，各字段均为中文含义。
    """
    todos = _ensure_data_file()
    total = len(todos)
    pending = sum(1 for t in todos if t["status"] == "pending")
    in_progress = sum(1 for t in todos if t["status"] == "in_progress")
    completed = sum(1 for t in todos if t["status"] == "completed")

    return {
        "总任务数": total,
        "待办": pending,
        "进行中": in_progress,
        "已完成": completed,
    }


# ---------- 命令行入口 ----------
if __name__ == "__main__":
    import sys

    def main():
        args = sys.argv[1:]
        if not args:
            print("用法: python todo_manager.py <命令> [参数...]")
            print("命令: list, add, update, delete, stats")
            return

        cmd = args[0]

        if cmd == "list":
            status = args[1] if len(args) > 1 else None
            result = todo_list(status)
            if isinstance(result, list):
                if not result:
                    print("暂无任务。")
                else:
                    for t in result:
                        print(f"[{t['id']}] {t['content']}")
                        print(f"    状态: {t['status']}  优先级: {t['priority']}")
                        print(f"    创建: {t['created_at']}  更新: {t['updated_at']}")
                        print()
            else:
                print(result)

        elif cmd == "add":
            if len(args) < 2:
                print("用法: python todo_manager.py add <内容> [优先级]")
                return
            content = args[1]
            priority = args[2] if len(args) > 2 else "medium"
            result = todo_add(content, priority)
            if isinstance(result, dict):
                print(f"任务已创建：")
                print(f"  ID:       {result['id']}")
                print(f"  内容:     {result['content']}")
                print(f"  状态:     {result['status']}")
                print(f"  优先级:   {result['priority']}")
            else:
                print(result)

        elif cmd == "update":
            if len(args) < 2:
                print("用法: python todo_manager.py update <任务ID> [字段=值 ...]")
                return
            task_id = args[1]
            updates = {}
            for kv in args[2:]:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    updates[k] = v
            if not updates:
                print("未提供更新字段。")
                return
            result = todo_update(task_id, **updates)
            if isinstance(result, dict):
                print(f"任务已更新：")
                print(f"  ID:       {result['id']}")
                print(f"  内容:     {result['content']}")
                print(f"  状态:     {result['status']}")
                print(f"  优先级:   {result['priority']}")
            else:
                print(result)

        elif cmd == "delete":
            if len(args) < 2:
                print("用法: python todo_manager.py delete <任务ID>")
                return
            result = todo_delete(args[1])
            if result is True:
                print(f"任务「{args[1]}」已删除。")
            else:
                print(result)

        elif cmd == "stats":
            stats = todo_stats()
            print("任务统计：")
            for k, v in stats.items():
                print(f"  {k}: {v}")

        else:
            print(f"未知命令: {cmd}")
            print("可用命令: list, add, update, delete, stats")

    main()
