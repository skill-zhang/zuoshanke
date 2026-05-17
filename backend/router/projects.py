"""项目 CRUD"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Project
from schemas import ProjectCreate, ProjectOut
from utils import make_id

router = APIRouter(tags=["项目"])


@router.post("/api/projects", response_model=ProjectOut)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        id=make_id("proj"),
        name=data.name,
        description=data.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/api/projects", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.updated_at.desc()).all()


@router.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    db.delete(project)
    db.commit()
    return {"ok": True}
