"""仪表盘 API — Priority Queue + Reflect Timeline + 收敛触发"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import ThinkingMap
from agent_core.converge_engine import (
    auto_converge_and_prioritize,
    get_pq_list,
    get_reflect_list,
    get_dashboard_status,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/{scene_id}/queue")
def api_get_queue(scene_id: str, db: Session = Depends(get_db)):
    """获取场景的优先级队列"""
    items = get_pq_list(db, scene_id)
    return {"items": items}


@router.get("/{scene_id}/reflect")
def api_get_reflect(scene_id: str, db: Session = Depends(get_db)):
    """获取场景的反馈时间线"""
    items = get_reflect_list(db, scene_id)
    return {"items": items}


@router.get("/{scene_id}/status")
def api_get_status(scene_id: str, db: Session = Depends(get_db)):
    """获取仪表盘状态汇总"""
    status = get_dashboard_status(db, scene_id)
    return status


@router.post("/{scene_id}/converge")
def api_trigger_converge(scene_id: str, db: Session = Depends(get_db)):
    """手动触发射收敛+排序（通常在自动发散后或纠正后调用）"""
    tm = db.query(ThinkingMap).filter(
        ThinkingMap.scene_id == scene_id
    ).first()
    if not tm:
        return {"ok": False, "error": "场景没有 Thinking Map"}

    pq_items = auto_converge_and_prioritize(db, scene_id, tm)
    return {"ok": True, "queue_count": len(pq_items), "items": pq_items}
