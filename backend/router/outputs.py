"""产出成果 API — 分身生成的独立 HTML/入口管理"""
import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ProjectOutput, Scene
from utils import make_id, utcnow

router = APIRouter(tags=["outputs"])


# ═══ Schemas ═══
from pydantic import BaseModel


class OutputCreate(BaseModel):
    scene_id: str
    title: str
    description: str = ""
    type: str = "html"
    file_path: Optional[str] = None
    url: Optional[str] = None


class OutputUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    file_path: Optional[str] = None


class OutputOut(BaseModel):
    id: str
    scene_id: str
    title: str
    description: str
    type: str
    file_path: Optional[str] = None
    url: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


# ═══ API ═══


@router.get("/api/outputs", response_model=List[OutputOut])
def list_outputs(scene_id: Optional[str] = None, db: Session = Depends(get_db)):
    """列出所有产出成果，可按场景过滤"""
    q = db.query(ProjectOutput).order_by(ProjectOutput.created_at.desc())
    if scene_id:
        q = q.filter(ProjectOutput.scene_id == scene_id)
    return q.all()


@router.post("/api/outputs", response_model=OutputOut)
def create_output(data: OutputCreate, db: Session = Depends(get_db)):
    """注册一个新的产出成果"""
    scene = db.query(Scene).filter(Scene.id == data.scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    output = ProjectOutput(
        id=make_id("out"),
        scene_id=data.scene_id,
        title=data.title,
        description=data.description or "",
        type=data.type or "html",
        file_path=data.file_path,
        url=data.url,
    )
    db.add(output)
    db.commit()
    db.refresh(output)
    return output


@router.delete("/api/outputs/{output_id}")
def delete_output(output_id: str, db: Session = Depends(get_db)):
    """删除产出成果"""
    out = db.query(ProjectOutput).filter(ProjectOutput.id == output_id).first()
    if not out:
        raise HTTPException(404, "产出不存在")
    # 如果有关联的 HTML 文件，也删除
    if out.file_path:
        full_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "outputs", out.file_path
        )
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError:
                pass
    db.delete(out)
    db.commit()
    return {"status": "ok"}
