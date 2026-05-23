"""场景自省地图 API — 每个场景一张架构图"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import SceneSelfMap
from utils import make_id

router = APIRouter(tags=["scene-self-map"])


# ═══ Schemas ═══

class SelfMapOut(BaseModel):
    id: str
    scene_id: str
    title: str
    tree: list
    diagrams: dict
    updated_at: str = ""

    class Config:
        from_attributes = True


class SelfMapIn(BaseModel):
    title: str = ""
    tree: list = []
    diagrams: dict = {}


def _serialize(sm: SceneSelfMap) -> dict:
    return {
        "id": sm.id,
        "scene_id": sm.scene_id,
        "title": sm.title or "",
        "tree": sm.tree if sm.tree else [],
        "diagrams": sm.diagrams if sm.diagrams else {},
        "updated_at": sm.updated_at.isoformat() if hasattr(sm.updated_at, 'isoformat') else str(sm.updated_at),
    }


# ═══ API ═══


@router.get("/api/scenes/{scene_id}/self-map")
def get_self_map(scene_id: str, db: Session = Depends(get_db)):
    """获取场景自省地图"""
    sm = db.query(SceneSelfMap).filter(SceneSelfMap.scene_id == scene_id).first()
    if not sm:
        return {"exists": False, "message": "场景尚未声明自省地图"}
    return {"exists": True, **{k: v for k, v in _serialize(sm).items() if k != "id"}}


@router.put("/api/scenes/{scene_id}/self-map")
def upsert_self_map(scene_id: str, data: SelfMapIn, db: Session = Depends(get_db)):
    """创建或覆盖场景自省地图"""
    sm = db.query(SceneSelfMap).filter(SceneSelfMap.scene_id == scene_id).first()
    if sm:
        sm.title = data.title
        sm.tree = data.tree
        sm.diagrams = data.diagrams
    else:
        sm = SceneSelfMap(
            id=make_id("smp"),
            scene_id=scene_id,
            title=data.title,
            tree=data.tree,
            diagrams=data.diagrams,
        )
        db.add(sm)
    db.commit()
    db.refresh(sm)
    return _serialize(sm)


@router.delete("/api/scenes/{scene_id}/self-map")
def delete_self_map(scene_id: str, db: Session = Depends(get_db)):
    """删除场景自省地图"""
    sm = db.query(SceneSelfMap).filter(SceneSelfMap.scene_id == scene_id).first()
    if not sm:
        raise HTTPException(404, "自省地图不存在")
    db.delete(sm)
    db.commit()
    return {"status": "ok"}
