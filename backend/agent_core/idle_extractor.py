"""记忆提取兜底调度器 — Schema v1.1: session 状态驱动

设计定位（v1.1 升级）:
  旧: 每 5 分钟扫描 → 找「最后消息 > 20 分钟」的场景 → 提取
  新: 每 1 分钟扫描 → 找「status=destroyed」的 session → 提取其未处理消息

为什么是 session 状态驱动:
  - session 超时销毁（3h 无消息）→ destroy_stale_*_sessions() 标为 destroyed
  - 销毁过程中已尝试提取（主路径），但可能因异常失败
  - 本调度器作为兜底：扫描所有 destroyed session，补提未被处理的 memory_extracted=false 消息

主路径:
  1. 前端 visibilitychange → POST /api/scenes/{id}/extract-memory（最佳时机）
  2. destroy_stale_web_sessions() → 销毁前内联提取（次佳时机）
  3. 本调度器 → 兜底扫描（安全网）

两种 session 模型:
  - WebSession: context_type(channel|scene) + context_id → 查 messages.scene_id 或 channel_id
  - GatewaySession: mode(channel|scene) + scene_id/channel_id → 同上
"""

import logging
import time
import threading

logger = logging.getLogger(__name__)

# Schema v1.1: 扫描间隔 60 秒（紧跟 session 超时销毁节奏）
SCAN_INTERVAL_SECONDS = 60
# 每次提取最大消息数
MAX_MSGS_PER_BATCH = 50


def start_idle_extraction_scheduler():
    """启动后台兜底提取调度线程（daemon，随主进程退出）"""
    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="idle-extract")
    thread.start()
    logger.info(
        f"✅ 记忆提取兜底调度已启动（Schema v1.1 session 状态驱动，"
        f"每 {SCAN_INTERVAL_SECONDS}s）"
    )


def _scheduler_loop():
    """调度循环"""
    while True:
        try:
            _scan_destroyed_sessions()
        except Exception as e:
            logger.warning(f"[idle-extract] 扫描异常: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)


def _scan_destroyed_sessions():
    """Schema v1.1: 扫描所有 destroyed session（Web + Gateway），提取未处理消息"""
    from database import SessionLocal
    from models import WebSession, GatewaySession, Message, Scene

    db = SessionLocal()
    try:
        extracted_total = 0

        # ── 1. 处理 WebSession ──
        destroyed_web = (
            db.query(WebSession)
            .filter(WebSession.status == "destroyed")
            .all()
        )
        for ws in destroyed_web:
            saved = _extract_for_session(
                db, ws.context_type, ws.context_id, ws.context_name or ""
            )
            extracted_total += saved

        # ── 2. 处理 GatewaySession ──
        destroyed_gw = (
            db.query(GatewaySession)
            .filter(GatewaySession.status == "destroyed")
            .all()
        )
        for gs in destroyed_gw:
            # Gateway mode="scene" → scene_id, mode="channel" → channel_id
            context_id = gs.scene_id if gs.mode == "scene" else gs.channel_id
            if not context_id:
                continue
            saved = _extract_for_session(
                db, gs.mode, context_id, gs.scene_name or ""
            )
            extracted_total += saved

        if extracted_total:
            logger.info(
                f"[idle-extract] 兜底提取完成: "
                f"扫描了 {len(destroyed_web) + len(destroyed_gw)} 个 destroyed session, "
                f"提取了 {extracted_total} 条记忆"
            )

    finally:
        db.close()


def _extract_for_session(db, context_type: str, context_id: str, context_name: str) -> int:
    """对单条 destroyed session 的上下文执行记忆提取

    Args:
        context_type: 'scene' | 'channel'
        context_id: 场景 ID 或频道 ID
        context_name: 上下文名称

    Returns:
        提取的记忆条数
    """
    from models import Message
    from agent_core.memory_extractor import extract_from_conversation, save_extracted_memories

    try:
        # 查找该上下文下未提取的消息
        q = db.query(Message).filter(
            Message.memory_extracted == False,
            Message.role.in_(["user", "ai"]),
        )
        if context_type == "scene":
            q = q.filter(Message.scene_id == context_id)
        elif context_type == "channel":
            q = q.filter(Message.channel_id == context_id)
        else:
            return 0

        msgs = (
            q.order_by(Message.created_at.asc())
            .limit(MAX_MSGS_PER_BATCH)
            .all()
        )

        if len(msgs) < 2:
            return 0

        # 获取场景名（如果传入的是空的）
        name = context_name
        if not name and context_type == "scene":
            sc = db.query(Scene).filter(Scene.id == context_id).first()
            if sc:
                name = sc.name

        # 提取
        messages_dict = [{"role": m.role, "content": m.content} for m in msgs]
        entries = extract_from_conversation(messages_dict, scene_name=name or "")
        saved = 0
        if entries:
            saved = save_extracted_memories(db, entries, context_id, scene_name=name or "")

        # 标记已处理（即使提取失败也标记，防止反复尝试）
        for m in msgs:
            m.memory_extracted = True
        db.commit()

        if saved:
            logger.info(
                f"[idle-extract] {name or context_id[:12]}: "
                f"提取了 {saved} 条记忆（兜底）"
            )
        return saved

    except Exception as e:
        logger.warning(
            f"[idle-extract] {context_type}/{context_id[:12]}... 提取失败: {e}"
        )
        db.rollback()
        return 0
