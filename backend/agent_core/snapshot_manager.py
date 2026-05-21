"""
文件快照管理器 — 记录文件的版本历史，用于 diff 提取

每次 write_file 或 patch 操作后调用 snapshot_manager.record()，
记录文件当前内容快照。下次调用 diff_extractor 时拿上次快照对比。
"""

import os
from datetime import datetime, timezone
from typing import Optional


def record(
    file_path: str,
    content: str,
    scene_id: str = "",
    db=None,
) -> Optional[str]:
    """记录文件快照

    Args:
        file_path: 文件路径
        content: 文件当前完整内容
        scene_id: 场景 ID（用于关联）
        db: 数据库会话（None = 仅日志）

    Returns:
        snapshot_id 或 None
    """
    if db is None:
        return _record_fs(file_path, content)

    try:
        from models import FileSnapshot
        snapshot = FileSnapshot(
            id=_make_snapshot_id(),
            scene_id=scene_id or "global",
            file_path=os.path.abspath(file_path),
            snapshot=content,
            created_at=datetime.now(timezone.utc),
        )
        db.add(snapshot)
        db.commit()
        return snapshot.id
    except Exception as e:
        print(f"[snapshot_manager] DB record failed: {e}")
        return _record_fs(file_path, content)


def get_previous(file_path: str, scene_id: str = "", db=None) -> Optional[str]:
    """获取文件上次快照的内容

    Args:
        file_path: 文件路径
        scene_id: 场景 ID
        db: 数据库会话

    Returns:
        上次快照内容，或 None（首次记录）
    """
    if db is not None:
        try:
            from models import FileSnapshot
            from sqlalchemy import desc
            abs_path = os.path.abspath(file_path)
            snapshot = (
                db.query(FileSnapshot)
                .filter(
                    FileSnapshot.file_path == abs_path,
                    FileSnapshot.scene_id == (scene_id or "global"),
                )
                .order_by(desc(FileSnapshot.created_at))
                .first()
            )
            if snapshot:
                return snapshot.snapshot
        except Exception:
            pass

    return _get_fs_previous(file_path)


def _make_snapshot_id() -> str:
    """生成快照 ID"""
    import uuid
    return f"snap_{uuid.uuid4().hex[:12]}"


def _record_fs(file_path: str, content: str) -> Optional[str]:
    """文件系统备选方案：存到 ~/.zuoshanke/snapshots/"""
    home = os.path.expanduser("~")
    snap_dir = os.path.join(home, ".zuoshanke", "snapshots")
    os.makedirs(snap_dir, exist_ok=True)

    safe_name = os.path.abspath(file_path).replace("/", "_").replace("\\", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_path = os.path.join(snap_dir, f"{safe_name}_{timestamp}")

    try:
        with open(snap_path, "w", encoding="utf-8") as f:
            f.write(content)
        return os.path.basename(snap_path)
    except Exception as e:
        print(f"[snapshot_manager] FS record failed: {e}")
        return None


def _get_fs_previous(file_path: str) -> Optional[str]:
    """文件系统备选方案：读取最近快照"""
    home = os.path.expanduser("~")
    snap_dir = os.path.join(home, ".zuoshanke", "snapshots")
    if not os.path.isdir(snap_dir):
        return None

    safe_name = os.path.abspath(file_path).replace("/", "_").replace("\\", "_")
    candidates = [f for f in os.listdir(snap_dir) if f.startswith(safe_name)]
    if not candidates:
        return None

    latest = sorted(candidates)[-1]
    try:
        with open(os.path.join(snap_dir, latest), "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None
