from __future__ import annotations
"""
Agent Loop 执行追踪日志 — 写穿透 + 3 天轮转 + DB 批量插入

三层记录体系：
1. agent.log (JSONL) — 实时落盘，yield SSE 前写入
2. agent_loop_traces (SQLite) — 每步批量 flush，独立表供复盘
3. 前端 SSE 分流 — 由前端 traceStore 处理

写穿透原则：先写文件/DB，再 yield SSE。即使下一步进程崩溃，
最后一行已落盘，不会丢失关键证据。
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, date

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── 日志目录 ──
LOG_DIR = os.path.expanduser("~/zuoshanke/logs")
LOG_FILE = os.path.join(LOG_DIR, "agent.log")
MAX_LOG_DAYS = 3


def _ensure_log_dir():
    """确保日志目录存在"""
    os.makedirs(LOG_DIR, exist_ok=True)


def _rotate_logs():
    """天级轮转，保留 MAX_LOG_DAYS 天

    策略：检查 agent.log 的 mtime，不是今天则轮转。
    使用模块级缓存避免每次写入都 stat。
    """
    global _last_rotate_check
    today = datetime.now().date()
    if _last_rotate_check == today:
        return
    _last_rotate_check = today

    if not os.path.exists(LOG_FILE):
        return

    mtime = datetime.fromtimestamp(os.path.getmtime(LOG_FILE)).date()
    if mtime == today:
        return  # 今天已轮转过

    _ensure_log_dir()

    # 删除最旧的
    oldest = os.path.join(LOG_DIR, f"agent.log.{MAX_LOG_DAYS}")
    if os.path.exists(oldest):
        os.remove(oldest)

    # 后缀 +1 移位
    for i in range(MAX_LOG_DAYS - 1, 0, -1):
        src = os.path.join(LOG_DIR, f"agent.log.{i}")
        dst = os.path.join(LOG_DIR, f"agent.log.{i + 1}")
        if os.path.exists(src):
            os.rename(src, dst)

    # 当前文件 → .1
    os.rename(LOG_FILE, os.path.join(LOG_DIR, "agent.log.1"))


_last_rotate_check: date | None = None


def _format_ts() -> str:
    """ISO 8601 毫秒级时间戳"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def write_trace(
    scene_id: str | None = None,
    session_id: str | None = None,
    step: int | None = None,
    event_type: str = "",
    tool: str | None = None,
    args: dict | None = None,
    result: dict | None = None,
    error: str | None = None,
    thinking_text: str | None = None,
    summary: str | None = None,
    duration_ms: int | None = None,
    metadata: dict | None = None,
    **kwargs,
):
    """写入一条 trace 到 agent.log（JSONL）

    写穿透：先写文件，再 yield SSE。即使下一步进程崩溃，最后一行已落盘。
    """
    _ensure_log_dir()
    _rotate_logs()

    record = {
        "ts": _format_ts(),
        "scene": scene_id or "",
        "session": session_id or "",
        "step": step,
        "type": event_type,
        "tool": tool or "",
    }

    if args is not None:
        record["args"] = _serialize_for_log(args)
    if result is not None:
        record["result"] = _serialize_for_log(result)
    if error is not None:
        record["error"] = error
    if thinking_text is not None:
        record["text"] = thinking_text
    if summary is not None:
        record["summary"] = summary
    if duration_ms is not None:
        record["duration_ms"] = duration_ms
    if metadata:
        record["meta"] = _serialize_for_log(metadata)

    # 额外 kwargs 中的字段合并到 record
    for k, v in kwargs.items():
        if v is not None and k not in record:
            record[k] = v

    line = json.dumps(record, ensure_ascii=False)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())  # 强制刷盘，保证崩溃不丢
    except OSError as e:
        logger.error(f"[trace_logger] 写入 agent.log 失败: {e}")


def _serialize_for_log(obj) -> str | dict:
    """安全序列化日志对象 — 处理不可 JSON 序列化的类型"""
    if obj is None:
        return ""
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except (TypeError, ValueError):
        return str(obj)


# ── DB trace 批量写入 ──


def bulk_insert_traces(db, traces: list[dict]):
    """批量写入 agent_loop_traces 表

    Args:
        db: SQLAlchemy session
        traces: list of dict, 每步收集的所有 trace 记录
    """
    if not traces or db is None:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    values = []
    for t in traces:
        values.append((
            t.get("scene_id", ""),
            t.get("session_id"),
            t.get("step"),
            t.get("event_type", ""),
            t.get("tool_name"),
            _json_or_none(t.get("args_text")),
            _json_or_none(t.get("result_text")),
            t.get("error_text"),
            t.get("thinking_text"),
            t.get("summary"),
            t.get("duration_ms"),
            _json_or_none(t.get("metadata")),
            now_str,
        ))

    try:
        db.execute(
            text("""
                INSERT INTO agent_loop_traces
                    (scene_id, session_id, step, event_type,
                     tool_name, args_text, result_text, error_text,
                     thinking_text, summary, duration_ms, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """),
            values,
        )
        db.commit()
    except Exception as e:
        logger.error(f"[trace_logger] 批量写入 DB trace 失败: {e}")
        db.rollback()


def _json_or_none(val):
    """将 dict/list 转 JSON 字符串，None 则返回 None"""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    try:
        return json.dumps(val, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(val)


# ── 过期清理 ──


def clean_expired_traces(db):
    """删除超过 3 天的 trace 记录

    后端启动时 + 每次写入后调用。
    """
    if db is None:
        return
    try:
        cutoff = (datetime.now() - timedelta(days=MAX_LOG_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        result = db.execute(
            text("DELETE FROM agent_loop_traces WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        db.commit()
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"[trace_logger] 清理过期 trace {deleted} 条")
    except Exception as e:
        logger.warning(f"[trace_logger] 过期清理失败: {e}")


# ── 查询 ──


def query_traces(db, scene_id: str, limit: int = 200, offset: int = 0) -> list[dict]:
    """按场景查询 trace 记录，按时间倒序"""
    try:
        rows = db.execute(
            text("""
                SELECT id, scene_id, session_id, step, event_type,
                       tool_name, args_text, result_text, error_text,
                       thinking_text, summary, duration_ms, metadata, created_at
                FROM agent_loop_traces
                WHERE scene_id = :scene_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"scene_id": scene_id, "limit": limit, "offset": offset},
        ).fetchall()

        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[trace_logger] 查询 trace 失败: {e}")
        return []


def _row_to_dict(row) -> dict:
    """把 SQLAlchemy RowProxy 转 dict"""
    keys = [
        "id", "scene_id", "session_id", "step", "event_type",
        "tool_name", "args_text", "result_text", "error_text",
        "thinking_text", "summary", "duration_ms", "metadata", "created_at",
    ]
    result = {}
    for i, key in enumerate(keys):
        val = row[i]
        if val is not None:
            # 尝试解析 JSON 字符串
            if key in ("args_text", "result_text", "metadata") and isinstance(val, str):
                try:
                    result[key] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    result[key] = val
            else:
                result[key] = val
    return result
