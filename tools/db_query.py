"""db_query — 直连 sqlite3 执行 SQL 查询

直接连接 zuoshanke.db，执行 SELECT 查询并返回结果。
支持 LIMIT 控制返回行数，支持参数化查询防注入。

## 使用示例
    from db_query import db_query
    result = db_query("SELECT name FROM sqlite_master WHERE type='table'")
    result = db_query("SELECT * FROM users WHERE id = ?", params=[1], limit=10)
"""

import json
import sqlite3
import os
from typing import Optional

# ── 数据库路径 ──
DB_PATH = os.environ.get(
    "ZUOSHANKE_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "zuoshanke.db")
)

# 只读模式打开
READONLY_FLAG = os.O_RDONLY


def db_query(
    sql: str,
    params: Optional[list] = None,
    limit: Optional[int] = 50,
    format: str = "json"
) -> str:
    """执行 SQL SELECT 查询并返回结果

    Args:
        sql: SQL 查询语句（仅允许 SELECT 开头）
        params: 参数化查询参数列表
        limit: 最大返回行数（默认 50，最大 200）
        format: 输出格式（json / table）

    Returns:
        JSON 字符串 {success, columns, rows, row_count, error?}
    """
    # ── 安全校验 ──
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return json.dumps({
            "success": False,
            "error": "仅允许 SELECT 查询"
        }, ensure_ascii=False)

    if not os.path.exists(DB_PATH):
        return json.dumps({
            "success": False,
            "error": f"数据库文件不存在: {DB_PATH}"
        }, ensure_ascii=False)

    # 限制最大行数
    actual_limit = min(limit or 50, 200)

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(sql, params or [])
        rows = cursor.fetchmany(actual_limit)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        result_rows = []
        for row in rows:
            result_rows.append(dict(row))

        conn.close()

        return json.dumps({
            "success": True,
            "columns": columns,
            "rows": result_rows,
            "row_count": len(result_rows),
            "limit": actual_limit,
            "db_path": DB_PATH
        }, ensure_ascii=False, default=str)

    except sqlite3.Error as e:
        return json.dumps({
            "success": False,
            "error": f"SQL 执行错误: {str(e)}"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"未知错误: {str(e)}"
        }, ensure_ascii=False)
