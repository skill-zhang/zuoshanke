#!/usr/bin/env python3
"""跨会话搜索工具 - 搜索用户在所有会话中的历史消息。

基于 SQLite，纯标准库实现，只读不写。

数据库路径规则：
  1. 环境变量 ZUOSHANKE_DB_PATH 优先
  2. 默认 ~/zuoshanke/backend/zuoshanke.db

用法：
  # 作为模块导入
  from tools.session_search import session_search, session_list

  results = session_search("旅行", limit=5)
  sessions = session_list(limit=10)

  # 命令行调用
  python session_search.py search <关键词> [limit]
  python session_search.py list [limit]
"""

import os
import sqlite3
from datetime import datetime

DEFAULT_DB = os.path.expanduser("~/zuoshanke/backend/zuoshanke.db")


def _get_db_path():
    """获取数据库路径，环境变量优先。"""
    return os.environ.get("ZUOSHANKE_DB_PATH", DEFAULT_DB)


def _connect():
    """创建只读数据库连接（默认使用 WAL 兼容模式）。"""
    db_path = _get_db_path()
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # 只读模式：不修改数据库
    conn.execute("PRAGMA query_only=ON")
    return conn


def _row_to_dict(row):
    """将 sqlite3.Row 转为普通 dict，datetime 字段转为 ISO 字符串。"""
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, bytes):
            d[k] = v.decode("utf-8", errors="replace")
    return d


def session_search(query: str, limit: int = 5) -> list[dict]:
    """跨会话搜索消息内容。

    使用 LIKE %keyword% 模糊匹配 content 字段，按时间倒序排列。

    Args:
        query:  搜索关键词
        limit:  最多返回条数，默认 5

    Returns:
        匹配的消息字典列表，按 created_at 倒序。
        每项包含：id, scene_id, channel_id, session_id, role, content,
                 map_ref, model, created_at
    """
    if not query or not query.strip():
        return []

    keyword = query.strip()
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, scene_id, channel_id, session_id, role,
                   content, map_ref, model, created_at
            FROM messages
            WHERE content LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"%{keyword}%", limit),
        )
        return [_row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def session_list(limit: int = 10) -> list[dict]:
    """列出最近的会话（按 session_id 分组）。

    每个会话取最新一条消息作为摘要，按 created_at 倒序排列。

    Args:
        limit:  最多返回多少个会话，默认 10

    Returns:
        会话摘要字典列表。
        每项包含：session_id, scene_id, channel_id, latest_role,
                 latest_content, latest_model, message_count, latest_at
    """
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                session_id,
                scene_id,
                channel_id,
                role              AS latest_role,
                content           AS latest_content,
                model             AS latest_model,
                created_at        AS latest_at,
                cnt               AS message_count
            FROM (
                SELECT
                    session_id,
                    scene_id,
                    channel_id,
                    role,
                    content,
                    model,
                    created_at,
                    COUNT(*) OVER (PARTITION BY session_id) AS cnt,
                    ROW_NUMBER() OVER (
                        PARTITION BY session_id
                        ORDER BY created_at DESC
                    ) AS rn
                FROM messages
                WHERE session_id IS NOT NULL
                  AND session_id != ''
            ) sub
            WHERE rn = 1
            ORDER BY latest_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [_row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# ---------- 命令行入口 ----------
if __name__ == "__main__":
    import sys

    def print_result(items):
        if not items:
            print("（无结果）")
            return
        for item in items:
            print(f"── {item.get('session_id', '(无会话)')} ──")
            for key, value in item.items():
                val = str(value)[:120]
                print(f"  {key}: {val}")
            print()

    args = sys.argv[1:]
    if not args:
        print("用法: python session_search.py <命令> [参数...]")
        print("命令:")
        print("  search <关键词> [limit]   跨会话搜索消息")
        print("  list [limit]             列出最近会话")
        sys.exit(1)

    cmd = args[0]

    if cmd == "search":
        if len(args) < 2:
            print("用法: python session_search.py search <关键词> [limit]")
            sys.exit(1)
        query = args[1]
        limit = int(args[2]) if len(args) > 2 else 5
        try:
            results = session_search(query, limit)
        except FileNotFoundError as e:
            print(f"错误: {e}")
            sys.exit(1)
        print(f"搜索「{query}」结果 ({len(results)} 条)：\n")
        print_result(results)

    elif cmd == "list":
        limit = int(args[1]) if len(args) > 1 else 10
        try:
            results = session_list(limit)
        except FileNotFoundError as e:
            print(f"错误: {e}")
            sys.exit(1)
        print(f"最近会话 ({len(results)} 个)：\n")
        print_result(results)

    else:
        print(f"未知命令: {cmd}")
        print("可用命令: search, list")
        sys.exit(1)
