"""通用工具函数"""
import uuid
from datetime import datetime, timezone


def make_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:8]
    return f"{prefix}-{short}" if prefix else short


def utcnow():
    return datetime.now(timezone.utc)
