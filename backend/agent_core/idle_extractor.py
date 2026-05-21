"""空闲场景记忆提取调度器 — 后台线程，每5分钟扫描一次

找出最后一条消息超过 20 分钟未更新的场景，自动触发记忆提取。
"""

import logging
import time
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# 空闲阈值：20 分钟
IDLE_THRESHOLD_MINUTES = 20
# 扫描间隔：5 分钟
SCAN_INTERVAL_SECONDS = 300


def start_idle_extraction_scheduler():
    """启动后台空闲提取调度线程（daemon，随主进程退出）"""
    import threading
    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="idle-extract")
    thread.start()
    logger.info(f"✅ 空闲记忆提取调度已启动（每{SCAN_INTERVAL_SECONDS}s扫描，{IDLE_THRESHOLD_MINUTES}分钟空闲触发）")


def _scheduler_loop():
    """调度循环"""
    while True:
        try:
            _scan_and_extract()
        except Exception as e:
            logger.warning(f"[idle-extract] 扫描异常: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)


def _scan_and_extract():
    """扫描所有场景，找出空闲超时的，触发提取"""
    from database import SessionLocal
    from models import Scene, Message
    from sqlalchemy import func

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=IDLE_THRESHOLD_MINUTES)

        # 找出每个场景的最后一条消息时间
        subq = (
            db.query(
                Message.scene_id,
                func.max(Message.created_at).label("last_msg_at"),
            )
            .filter(Message.scene_id.isnot(None))
            .group_by(Message.scene_id)
            .subquery()
        )

        idle_scenes = (
            db.query(Scene)
            .join(subq, Scene.id == subq.c.scene_id)
            .filter(subq.c.last_msg_at < cutoff)
            .all()
        )

        if not idle_scenes:
            return

        logger.info(f"[idle-extract] 发现 {len(idle_scenes)} 个空闲场景，准备提取")

        from agent_core.memory_extractor import extract_from_conversation, save_extracted_memories

        for scene in idle_scenes:
            try:
                # 只读未提取过的消息
                msgs = (
                    db.query(Message)
                    .filter(
                        Message.scene_id == scene.id,
                        Message.role.in_(["user", "ai"]),
                        Message.memory_extracted == False,
                    )
                    .order_by(Message.created_at.asc())
                    .limit(30)
                    .all()
                )
                if len(msgs) < 2:
                    # 没有未提取的消息，跳过
                    continue

                messages_dict = [{"role": m.role, "content": m.content} for m in msgs]

                entries = extract_from_conversation(messages_dict, scene_name=scene.name)
                if entries:
                    saved = save_extracted_memories(db, entries, scene.id, scene_name=scene.name)
                    logger.info(f"[idle-extract] {scene.name}: 提取了 {saved} 条记忆")

                # 标记已处理的消息
                for m in msgs:
                    m.memory_extracted = True
                db.commit()
            except Exception as e:
                logger.warning(f"[idle-extract] {scene.name} 提取失败: {e}")
                db.rollback()

    finally:
        db.close()
