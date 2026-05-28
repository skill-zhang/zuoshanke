"""通用工具函数"""
import os
import uuid
from datetime import datetime, timezone


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_version() -> str:
    """从项目根目录 VERSION 文件读取版本号，无文件时返回 unknown"""
    path = os.path.join(_PROJECT_ROOT, "VERSION")
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "unknown"


def sync_version_from_schema() -> None:
    """启动时自动同步版本号：扫描 docs/design/schema-*.md，取最高版本号写入 VERSION。

    版本规则：文件名 schema-v{major}.{minor}.md → v{major}.{minor}.0
    已废弃：如果 VERSION 当前比 schema 最高版本还高，不降级。
    """
    import re
    schema_dir = os.path.join(_PROJECT_ROOT, "docs", "design")
    version_file = os.path.join(_PROJECT_ROOT, "VERSION")

    if not os.path.isdir(schema_dir):
        return

    highest = (0, 0, 0)  # (major, minor, patch)
    for fname in os.listdir(schema_dir):
        m = re.match(r"schema-v(\d+)\.(\d+)(?:\.(\d+))?\.md", fname)
        if m:
            major, minor = int(m.group(1)), int(m.group(2))
            patch = int(m.group(3)) if m.group(3) else 0
            highest = max(highest, (major, minor, patch))

    if highest == (0, 0, 0):
        return  # 没有 schema 文件

    new_ver = f"{highest[0]}.{highest[1]}.{highest[2]}"

    # 读取当前版本
    current = "0.0.0"
    try:
        with open(version_file) as f:
            current = f.read().strip()
    except FileNotFoundError:
        pass

    # 只有新版本大于当前版本时才更新（不降级）
    def _parse(v: str) -> tuple:
        parts = v.split(".")
        return tuple(int(p) if p.isdigit() else 0 for p in parts[:3])

    if _parse(new_ver) > _parse(current):
        with open(version_file, "w") as f:
            f.write(new_ver + "\n")
        import logging
        logging.getLogger(__name__).info(f"🔄 版本已自动同步: {current} → {new_ver}")


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
