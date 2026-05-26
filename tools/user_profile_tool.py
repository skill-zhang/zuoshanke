"""
User Profile Tool — 坐山客用户画像系统

提供两个接口：
1. pending_extract — 分身提取用户偏好，写入 pending_user_traits 暂存区
2. profile_list — 查询正式用户画像，按优先级分组返回

用法：
    from tools.user_profile_tool import pending_extract, profile_list
    result = pending_extract(content="...", source_scene="...", ...)
    result = profile_list(category=None, active_only=True)
"""
import json
import sys
import os
from datetime import datetime, timezone
from uuid import uuid4

# ── 导入 backend 模型 ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.database import SessionLocal
from backend.models import PendingUserTrait, UserProfile


def pending_extract(
    content: str,
    source_scene: str = "",
    source_scene_id: str = "",
    confidence: str = "medium",
    context_snippet: str = "",
) -> str:
    """分身提取用户偏好，写入 pending_user_traits 暂存区

    Args:
        content: 分身提取的描述（必填）
        source_scene: 来源场景名称
        source_scene_id: 来源场景 ID
        confidence: 置信度 high / medium / low
        context_snippet: 触发对话片段

    Returns:
        JSON 字符串 {success, id, message}
    """
    try:
        db = SessionLocal()
        try:
            trait = PendingUserTrait(
                id=str(uuid4()),
                content=content,
                source_scene=source_scene,
                source_scene_id=source_scene_id,
                confidence=confidence if confidence in ("high", "medium", "low") else "medium",
                context_snippet=context_snippet or None,
                status="pending",
            )
            db.add(trait)
            db.commit()
            return json.dumps({
                "success": True,
                "id": trait.id,
                "message": f"用户特征已提取，ID={trait.id}，等待确认合入正式库",
            }, ensure_ascii=False)
        finally:
            db.close()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


def profile_list(category: str = "", active_only: bool = True) -> str:
    """查询正式用户画像，按优先级分组返回

    Args:
        category: 筛选分类（principle / preference / habit / context），空=全部
        active_only: 仅返回有效的画像（is_active=True），默认 True

    Returns:
        JSON 字符串 {success, profiles: {P0: [...], P1: [...], P2: [...], P3: [...]}, total}
    """
    try:
        db = SessionLocal()
        try:
            query = db.query(UserProfile)
            if category:
                query = query.filter(UserProfile.category == category)
            if active_only:
                query = query.filter(UserProfile.is_active == True)

            rows = query.order_by(UserProfile.created_at.desc()).all()

            grouped = {"P0": [], "P1": [], "P2": [], "P3": []}
            for r in rows:
                p = r.priority or "P2"
                if p not in grouped:
                    p = "P2"
                grouped[p].append({
                    "id": r.id,
                    "key": r.key,
                    "content": r.content,
                    "category": r.category,
                    "priority": r.priority,
                    "tags": r.tags or [],
                    "source_scenes": r.source_scenes or [],
                    "is_active": r.is_active,
                    "total_injections": r.total_injections,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                })

            return json.dumps({
                "success": True,
                "profiles": {k: v for k, v in grouped.items() if v},
                "total": len(rows),
            }, ensure_ascii=False)
        finally:
            db.close()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)
