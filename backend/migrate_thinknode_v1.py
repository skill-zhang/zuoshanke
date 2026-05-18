"""
ThinkNode 模型 v1 迁移 — Agent Loop 新字段
安全地给 think_nodes 表添加新列（SQLite ALTER TABLE ADD COLUMN 兼容）
"""
import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)

NEW_COLUMNS = [
    ("converged_from", "JSON DEFAULT '[]'"),
    ("created_by", "TEXT DEFAULT 'brainstorm'"),
    ("priority", "INTEGER"),
    ("queue_order", "INTEGER"),
    ("depends_on", "JSON DEFAULT '[]'"),
    ("execution_result", "TEXT"),
]


def run_thinknode_v1_migration(engine):
    """安全添加 think_nodes 表新列（幂等：已存在则跳过）"""
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("think_nodes")}

    with engine.begin() as conn:  # auto-commit
        for col_name, col_type in NEW_COLUMNS:
            if col_name in existing:
                logger.info(f"[migrate] think_nodes.{col_name} 已存在，跳过")
                continue
            sql = text(f"ALTER TABLE think_nodes ADD COLUMN {col_name} {col_type}")
            conn.execute(sql)
            logger.info(f"[migrate] ✅ 添加 think_nodes.{col_name} ({col_type})")

    logger.info("[migrate] ThinkNode v1 迁移完成")
