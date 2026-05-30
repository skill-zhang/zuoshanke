from __future__ import annotations
"""子 Agent 执行结果 API — 持久化的 delegate 成果展示"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import DelegateResult, Scene
from utils import make_id

router = APIRouter(tags=["delegate-results"])


# ═══ Schemas ═══

class DelegateResultOut(BaseModel):
    id: str
    scene_id: str
    session_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    task: str
    status: str  # success / error / timeout
    summary: str
    steps: int
    error: Optional[str] = None
    created_at: str = ""

    class Config:
        from_attributes = True


def _serialize(r: DelegateResult) -> dict:
    return {
        "id": r.id,
        "scene_id": r.scene_id,
        "session_id": r.session_id,
        "parent_message_id": r.parent_message_id,
        "task": r.task,
        "status": r.status,
        "summary": r.summary or "",
        "steps": r.steps or 0,
        "error": r.error,
        "created_at": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
    }


# ═══ API ═══


@router.get("/api/delegate-results", response_model=List[DelegateResultOut])
def list_all_results(
    scene_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """列出所有 delegate 结果，可按场景过滤"""
    q = db.query(DelegateResult).order_by(DelegateResult.created_at.desc())
    if scene_id:
        q = q.filter(DelegateResult.scene_id == scene_id)
    rows = q.limit(min(limit, 200)).all()
    return [_serialize(r) for r in rows]


@router.get("/api/delegate-results/{result_id}", response_model=DelegateResultOut)
def get_result(result_id: str, db: Session = Depends(get_db)):
    """获取单个 delegate 结果详情"""
    r = db.query(DelegateResult).filter(DelegateResult.id == result_id).first()
    if not r:
        raise HTTPException(404, "结果不存在")
    return _serialize(r)


@router.delete("/api/delegate-results/{result_id}")
def delete_result(result_id: str, db: Session = Depends(get_db)):
    """删除 delegate 结果"""
    r = db.query(DelegateResult).filter(DelegateResult.id == result_id).first()
    if not r:
        raise HTTPException(404, "结果不存在")
    db.delete(r)
    db.commit()
    return {"status": "ok"}


# ═══ 内部写入（供 scene_stream 调用） ═══

def save_delegate_results(
    scene_id: str,
    children: list[dict],
    db: Session,
    session_id: str | None = None,
    parent_message_id: str | None = None,
) -> list[DelegateResult]:
    """批量保存子 Agent 执行结果到 DB"""
    saved = []
    for child in children:
        dr = DelegateResult(
            id=make_id("dres"),
            scene_id=scene_id,
            session_id=session_id,
            parent_message_id=parent_message_id,
            task=child.get("task", child.get("goal", "?")),
            status=child.get("status", "error"),
            summary=child.get("summary", ""),
            steps=child.get("steps", 0),
            error=child.get("error"),
        )
        db.add(dr)
        saved.append(dr)
    db.commit()
    return saved
