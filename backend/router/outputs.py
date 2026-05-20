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
    created_at: str = ""

    class Config:
        from_attributes = True


# ═══ API ═══


@router.get("/api/outputs", response_model=List[OutputOut])
def list_outputs(scene_id: Optional[str] = None, db: Session = Depends(get_db)):
    """列出所有产出成果，可按场景过滤"""
    q = db.query(ProjectOutput).order_by(ProjectOutput.created_at.desc())
    if scene_id:
        q = q.filter(ProjectOutput.scene_id == scene_id)
    rows = q.all()
    # 手动序列化 datetime → str
    result = []
    for r in rows:
        d = {
            "id": r.id, "scene_id": r.scene_id,
            "title": r.title, "description": r.description or "",
            "type": r.type, "file_path": r.file_path, "url": r.url,
            "created_at": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
        }
        result.append(OutputOut(**d))
    return result


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
    return {
        "id": output.id, "scene_id": output.scene_id,
        "title": output.title, "description": output.description or "",
        "type": output.type, "file_path": output.file_path, "url": output.url,
        "created_at": output.created_at.isoformat() if hasattr(output.created_at, 'isoformat') else str(output.created_at),
    }


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


# ═══ Schema v0.81: 项目 CRUD ═══

from schemas import OutputProjectCreate, OutputProjectUpdate, OutputProjectOut, ConvergeStatusOut
from models import OutputProject, ThinkNode, ThinkingMap, Scene, Message


@router.get("/api/projects", response_model=List[OutputProjectOut])
def list_projects(scene_id: Optional[str] = None, db: Session = Depends(get_db)):
    """列出所有项目，可按场景过滤"""
    q = db.query(OutputProject).order_by(OutputProject.created_at.desc())
    if scene_id:
        q = q.filter(OutputProject.scene_id == scene_id)
    rows = q.all()
    result = []
    for proj in rows:
        d = {
            "id": proj.id, "scene_id": proj.scene_id,
            "name": proj.name, "description": proj.description or "",
            "converged_at": proj.converged_at.isoformat() if proj.converged_at else None,
            "is_active": proj.is_active,
            "created_at": proj.created_at.isoformat() if proj.created_at else "",
            "outputs": [],
        }
        if proj.outputs:
            d["outputs"] = [
                {
                    "id": o.id, "title": o.title,
                    "file_path": o.file_path, "type": o.type,
                }
                for o in proj.outputs
            ]
        result.append(OutputProjectOut(**d))
    return result


@router.post("/api/projects", response_model=OutputProjectOut)
def create_project(data: OutputProjectCreate, db: Session = Depends(get_db)):
    """手动创建一个项目"""
    scene = db.query(Scene).filter(Scene.id == data.scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    proj = OutputProject(
        id=make_id("proj"),
        scene_id=data.scene_id,
        name=data.name,
        description=data.description or "",
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return {
        "id": proj.id, "scene_id": proj.scene_id,
        "name": proj.name, "description": proj.description or "",
        "converged_at": proj.converged_at.isoformat() if proj.converged_at else None,
        "is_active": proj.is_active,
        "created_at": proj.created_at.isoformat() if proj.created_at else "",
        "outputs": [],
    }


@router.get("/api/projects/{project_id}", response_model=OutputProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    proj = db.query(OutputProject).filter(OutputProject.id == project_id).first()
    if not proj:
        raise HTTPException(404, "项目不存在")
    d = {
        "id": proj.id, "scene_id": proj.scene_id,
        "name": proj.name, "description": proj.description or "",
        "converged_at": proj.converged_at.isoformat() if proj.converged_at else None,
        "is_active": proj.is_active,
        "created_at": proj.created_at.isoformat() if proj.created_at else "",
        "outputs": [],
    }
    if proj.outputs:
        d["outputs"] = [
            {
                "id": o.id, "title": o.title,
                "file_path": o.file_path, "type": o.type,
            }
            for o in proj.outputs
        ]
    return OutputProjectOut(**d)


@router.patch("/api/projects/{project_id}", response_model=OutputProjectOut)
def update_project(project_id: str, data: OutputProjectUpdate, db: Session = Depends(get_db)):
    proj = db.query(OutputProject).filter(OutputProject.id == project_id).first()
    if not proj:
        raise HTTPException(404, "项目不存在")
    if data.name is not None:
        proj.name = data.name
    if data.description is not None:
        proj.description = data.description
    if data.is_active is not None:
        proj.is_active = data.is_active
    db.commit()
    db.refresh(proj)
    return get_project(project_id, db)


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    """删除项目，级联解除 output 关联但不删除文件"""
    proj = db.query(OutputProject).filter(OutputProject.id == project_id).first()
    if not proj:
        raise HTTPException(404, "项目不存在")
    # 解除关联的 outputs
    from models import ProjectOutput as _PO
    for out in proj.outputs:
        out.project_id = None
    db.delete(proj)
    db.commit()
    return {"status": "ok"}


@router.get("/api/projects/{project_id}/outputs")
def list_project_outputs(project_id: str, db: Session = Depends(get_db)):
    """获取项目下的所有产出"""
    proj = db.query(OutputProject).filter(OutputProject.id == project_id).first()
    if not proj:
        raise HTTPException(404, "项目不存在")
    outputs = []
    for o in proj.outputs:
        outputs.append({
            "id": o.id, "title": o.title,
            "description": o.description, "type": o.type,
            "file_path": o.file_path, "url": o.url,
            "created_at": o.created_at.isoformat() if o.created_at else "",
        })
    return outputs


@router.get("/api/scenes/{scene_id}/converge-status", response_model=ConvergeStatusOut)
def get_converge_status(scene_id: str, db: Session = Depends(get_db)):
    """获取场景的收敛状态"""
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    ai_rounds = db.query(Message).filter(
        Message.scene_id == scene_id, Message.role == "ai",
    ).count()

    tmap = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    leaf_count = 0
    branch_count = 0
    has_tree = False
    has_converged = False

    if tmap:
        nodes = db.query(ThinkNode).filter(
            ThinkNode.map_id == tmap.id, ThinkNode.type != "root",
        ).all()
        if nodes:
            has_tree = True
            node_ids = set(n.id for n in nodes)
            children_map = {}
            for n in nodes:
                if n.parent_id and n.parent_id in node_ids:
                    children_map.setdefault(n.parent_id, []).append(n.id)
            leaf_count = len([n for n in nodes if n.id not in children_map])
            branch_count = len([n for n in nodes if n.id in children_map])
            # 检查是否有已收敛的节点
            has_converged = any(n.status == "confirmed" for n in nodes)

    # 查找活跃项目
    project = None
    active_proj = db.query(OutputProject).filter(
        OutputProject.scene_id == scene_id, OutputProject.is_active == True,
    ).first()
    if active_proj:
        project = {
            "id": active_proj.id, "scene_id": active_proj.scene_id,
            "name": active_proj.name, "description": active_proj.description or "",
            "converged_at": active_proj.converged_at.isoformat() if active_proj.converged_at else None,
            "is_active": active_proj.is_active,
            "created_at": active_proj.created_at.isoformat() if active_proj.created_at else "",
            "outputs": [],
        }

    threshold = scene.converge_threshold or 2.0
    trigger_ready = has_tree and leaf_count >= branch_count * threshold if branch_count > 0 else False

    return ConvergeStatusOut(
        scene_id=scene_id,
        ai_rounds=ai_rounds,
        diverge_min_rounds=scene.diverge_min_rounds or 2,
        has_tree=has_tree,
        has_converged=has_converged,
        leaf_count=leaf_count,
        branch_count=branch_count,
        threshold=threshold,
        trigger_ready=trigger_ready,
        project=project,
    )
