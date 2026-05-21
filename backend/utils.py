"""通用工具函数"""
import uuid
from datetime import datetime, timezone


def make_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:8]
    return f"{prefix}-{short}" if prefix else short


def utcnow():
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime) -> str:
    """datetime → UTC ISO 8601 字符串，始终带 Z 后缀。

    SQLite 回读 datetime 会丢失时区信息（变成 naive），
    直接 .isoformat() 出的字符串没有时区标记，浏览器会误判为本地时间。
    此函数保证输出始终以 Z 结尾，让 JS 正确识别为 UTC。
    """
    if dt.tzinfo is None:
        # naive datetime：SQLite 回读的 UTC 时间，补 Z
        return dt.isoformat() + 'Z'
    return dt.astimezone(timezone.utc).isoformat()
