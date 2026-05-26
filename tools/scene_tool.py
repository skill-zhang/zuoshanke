"""Scene Tool — Agent Loop 的场景管理工具

提供 list_scenes 接口，供 LLM 查询所有场景列表。

使用场景：
- 查看当前所有场景及其状态
- 按分类或状态过滤场景
- 了解场景的版本、图标、描述等信息
"""

import json
import os
import sqlite3
from datetime import datetime


# ── 默认数据库路径 ──
DEFAULT_DB = os.path.expanduser("~/zuoshanke/backend/zuoshanke.db")

# ── OpenAI Function-Calling Schema ──

LIST_SCENES_SCHEMA = {
    "name": "list_scenes",
    "description": (
        "列出所有场景，支持按分类和状态过滤。"
        "返回每个场景的 id/name/icon/description/category/version/pinned/created_at/updated_at。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "分类过滤（如 dev/life/work/learn/create/finance/media/other），不传则不过滤",
                "optional": True,
            },
            "status": {
                "type": "string",
                "description": "状态过滤：draft（草稿 version=0.0）/ published（已发布 version!=0.0）/ all（全部，默认）",
                "optional": True,
            },
        },
    },
}


def _parse_datetime(val):
    """将日期时间值转为字符串"""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def list_scenes(category: str = "", status: str = "all") -> str:
    """查询场景列表

    Args:
        category: 分类过滤（如 dev/life/work/learn/create/finance/media/other），空字符串=不限制
        status: 状态过滤，all=全部, draft=仅草稿, published=仅已发布

    Returns:
        JSON 字符串，包含 scenes 列表和 total 计数
    """
    db_path = DEFAULT_DB
    if not os.path.isfile(db_path):
        return json.dumps({
            "success": False,
            "error": f"数据库文件不存在: {db_path}",
        }, ensure_ascii=False)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 构建查询
        conditions = []
        params = []

        if category:
            conditions.append("category = ?")
            params.append(category)

        if status == "draft":
            conditions.append("version = '0.0'")
        elif status == "published":
            conditions.append("version != '0.0'")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = (
            f"SELECT id, name, icon, description, category, version, "
            f"pinned, created_at, updated_at "
            f"FROM scenes {where_clause} "
            f"ORDER BY pinned DESC, updated_at DESC"
        )

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        scenes = []
        for r in rows:
            d = dict(r)
            d["created_at"] = _parse_datetime(d.get("created_at"))
            d["updated_at"] = _parse_datetime(d.get("updated_at"))
            scenes.append(d)

        conn.close()

        return json.dumps({
            "success": True,
            "total": len(scenes),
            "scenes": scenes,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)
