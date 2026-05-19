#!/usr/bin/env python3
"""跨会话搜索工具 - 搜索用户在所有会话中的历史消息。

基于 SQLite FTS5 + jieba 中文分词，纯标准库 + jieba 实现，只读不写。

数据库路径规则：
  1. 环境变量 ZUOSHANKE_DB_PATH 优先
  2. 默认 ~/zuoshanke/backend/zuoshanke.db

用法：
  # 作为模块导入
  from tools.session_search import session_search, session_list

  results = session_search("上次聊的数据库问题", limit=5)
  sessions = session_list(limit=10)

  # 命令行调用
  python session_search.py search <关键词> [limit]
  python session_search.py list [limit]
"""

import os
import re
import sqlite3
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DB = os.path.expanduser("~/zuoshanke/backend/zuoshanke.db")
_CACHE_FTS_READY = False

# ── jieba 延迟加载（首次搜索时导入） ──
_jieba = None


def _get_jieba():
    global _jieba
    if _jieba is None:
        try:
            import jieba
            _jieba = jieba
        except ImportError:
            logger.warning("jieba 未安装，降级为逐字分词回退")
            _jieba = None
    return _jieba


def _segment(text: str) -> str:
    """对文本进行中文分词，返回空格分隔的 token 序列。"""
    jieba_mod = _get_jieba()
    if jieba_mod:
        words = jieba_mod.lcut(text)
        return " ".join(w.strip() for w in words if w.strip())
    else:
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9_]+', text)
        return " ".join(tokens)


def _get_db_path():
    return os.environ.get("ZUOSHANKE_DB_PATH", DEFAULT_DB)


def _connect(readonly: bool = True):
    db_path = _get_db_path()
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if readonly:
        conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA cache_size=-8000")
    return conn


def _row_to_dict(row):
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, bytes):
            d[k] = v.decode("utf-8", errors="replace")
    return d


# ── FTS5 表管理 ─────────────────────────────────────


def _ensure_fts_table():
    """确保 FTS5 虚拟表存在且数据为最新。

    使用独立的写连接操作建表和插索引，不与只读搜索连接混用。
    """
    global _CACHE_FTS_READY
    if _CACHE_FTS_READY:
        return

    conn = _connect(readonly=False)
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
            USING fts5(msg_id UNINDEXED, content, tokenize='unicode61')
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages_fts_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()

        # 检查已有索引
        cursor = conn.execute("SELECT COUNT(*) AS cnt FROM messages_fts")
        fts_count = cursor.fetchone()["cnt"]

        if fts_count > 0:
            cursor = conn.execute(
                "SELECT value FROM messages_fts_state WHERE key = 'last_indexed_id'"
            )
            row = cursor.fetchone()
            if row:
                last_id = row["value"]
                cursor = conn.execute(
                    "SELECT id, content FROM messages WHERE id > ? ORDER BY id ASC LIMIT 500",
                    (last_id,)
                )
            else:
                cursor = conn.execute(
                    "SELECT id, content FROM messages ORDER BY id ASC"
                )
        else:
            cursor = conn.execute(
                "SELECT id, content FROM messages ORDER BY id ASC"
            )

        new_rows = cursor.fetchall()
        if not new_rows:
            _CACHE_FTS_READY = True
            return

        max_id = last_id if fts_count > 0 and 'last_id' in dir() else ""
        count = 0
        for row in new_rows:
            mid = row["id"]
            content = row["content"] or ""
            segmented = _segment(content)
            if mid > max_id:
                max_id = mid
            try:
                conn.execute(
                    "INSERT INTO messages_fts(msg_id, content) VALUES (?, ?)",
                    (mid, segmented)
                )
                count += 1
            except sqlite3.IntegrityError:
                pass

        conn.execute(
            "INSERT OR REPLACE INTO messages_fts_state (key, value) VALUES ('last_indexed_id', ?)",
            (max_id,)
        )
        conn.commit()
        logger.info(f"FTS5 索引: {count} 条 (last_id={max_id})")
        _CACHE_FTS_READY = True
    finally:
        conn.close()


def rebuild_fts_index():
    """重建 FTS5 全文索引。"""
    global _CACHE_FTS_READY
    conn = _connect(readonly=False)
    try:
        conn.execute("DROP TABLE IF EXISTS messages_fts")
        conn.execute("DROP TABLE IF EXISTS messages_fts_state")
        conn.commit()
        _CACHE_FTS_READY = False
        _ensure_fts_table(conn)
        return True
    except Exception as e:
        logger.error(f"重建 FTS5 索引失败: {e}")
        return False
    finally:
        conn.close()


# ── 搜索 API ────────────────────────────────────────


def session_search(query: str, limit: int = 5) -> list[dict]:
    """跨会话搜索消息内容。

    使用 FTS5 全文索引 + jieba 中文分词，按时间倒序排列。

    Args:
        query:  搜索关键词
        limit:  最多返回条数，默认 5

    Returns:
        匹配的消息字典列表，按 created_at 倒序。
    """
    if not query or not query.strip():
        return []

    q = query.strip()
    conn = _connect()
    try:
        # 确保 FTS5 表就绪（独立写连接）
        try:
            _ensure_fts_table()
        except Exception as e:
            logger.warning(f"FTS5 初始化失败 ({e})，降级为 LIKE 搜索")
            return _search_like(conn, q, limit)

        # jieba 分词构建 FTS5 查询
        seg = _segment(q).strip()
        if not seg:
            return _search_like(conn, q, limit)

        # 每个词用 + 前缀（AND 语义），引号包裹避免特殊字符问题
        terms = seg.split()
        fts_query = " AND ".join(f'"{t}"' for t in terms if t.strip())

        if not fts_query:
            return _search_like(conn, q, limit)

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.id, m.scene_id, m.channel_id, m.session_id, m.role,
                   m.content, m.map_ref, m.model, m.created_at
            FROM messages_fts fts
            JOIN messages m ON m.id = fts.msg_id
            WHERE messages_fts MATCH ?
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (fts_query, limit),
        )
        results = [_row_to_dict(row) for row in cursor.fetchall()]

        # 无结果时降级 LIKE 兜底
        if not results:
            return _search_like(conn, q, limit)

        return results

    except sqlite3.OperationalError as e:
        logger.warning(f"FTS5 查询失败 ({e})，降级为 LIKE 搜索")
        return _search_like(conn, q, limit)
    finally:
        conn.close()


def _search_like(conn, query: str, limit: int = 5) -> list[dict]:
    """降级搜索：jieba 分词后多词 OR LIKE 组合。"""
    jieba_mod = _get_jieba()
    if jieba_mod:
        words = jieba_mod.lcut(query)
        words = [w.strip() for w in words if len(w.strip()) >= 2]
    else:
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}', query)

    if not words:
        words = [query]

    conditions = " OR ".join(["m.content LIKE ?" for _ in words])
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT m.id, m.scene_id, m.channel_id, m.session_id, m.role,
               m.content, m.map_ref, m.model, m.created_at
        FROM messages m
        WHERE {conditions}
        ORDER BY m.created_at DESC
        LIMIT ?
        """,
        [f"%{w}%" for w in words] + [limit],
    )
    return [_row_to_dict(row) for row in cursor.fetchall()]


def session_list(limit: int = 10) -> list[dict]:
    """列出最近的会话（按 session_id 分组）。"""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                session_id, scene_id, channel_id,
                role AS latest_role,
                content AS latest_content,
                model AS latest_model,
                created_at AS latest_at,
                cnt AS message_count
            FROM (
                SELECT session_id, scene_id, channel_id, role, content, model,
                       created_at,
                       COUNT(*) OVER (PARTITION BY session_id) AS cnt,
                       ROW_NUMBER() OVER (
                           PARTITION BY session_id ORDER BY created_at DESC
                       ) AS rn
                FROM messages
                WHERE session_id IS NOT NULL AND session_id != ''
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


# ── 工具函数 ────────────────────────────────────────


def get_index_status() -> dict:
    """获取 FTS5 索引状态。"""
    conn = _connect()
    try:
        try:
            _ensure_fts_table()
        except Exception as e:
            return {"error": f"FTS5 未初始化: {e}"}

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM messages_fts")
        indexed = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM messages")
        total = cursor.fetchone()["cnt"]

        cursor.execute(
            "SELECT value FROM messages_fts_state WHERE key = 'last_indexed_id'"
        )
        row = cursor.fetchone()
        last_id = row["value"] if row else "N/A"

        return {"indexed_count": indexed, "total_messages": total, "last_indexed_id": last_id}
    finally:
        conn.close()


# ── 命令行入口 ──────────────────────────────────────

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
        print("  search <关键词> [limit]   跨会话搜索消息（FTS5+jieba 分词）")
        print("  list [limit]             列出最近会话")
        print("  rebuild                  重建 FTS5 索引")
        print("  status                   索引状态")
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

    elif cmd == "rebuild":
        ok = rebuild_fts_index()
        print("✅ FTS5 索引重建完成" if ok else "❌ 重建失败")

    elif cmd == "status":
        status = get_index_status()
        if "error" in status:
            print(f"❌ {status['error']}")
        else:
            print(f"📊 FTS5 索引状态:")
            print(f"  已索引: {status['indexed_count']} 条消息")
            print(f"  总消息: {status['total_messages']} 条")
            print(f"  最近索引 ID: {status['last_indexed_id']}")

    else:
        print(f"未知命令: {cmd}")
        print("可用命令: search, list, rebuild, status")
        sys.exit(1)
