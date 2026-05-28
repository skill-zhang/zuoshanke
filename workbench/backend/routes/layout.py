"""布局配置 CRUD"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import LayoutConfig

router = APIRouter(prefix="/api/layout", tags=["layout"])


@router.get("")
def get_layout(db: Session = Depends(get_db)):
    layout = db.query(LayoutConfig).filter(LayoutConfig.id == "default").first()
    if not layout:
        layout = LayoutConfig(id="default")
        db.add(layout)
        db.commit()
        db.refresh(layout)
    return layout.to_dict()


@router.put("")
def update_layout(data: dict, db: Session = Depends(get_db)):
    layout = db.query(LayoutConfig).filter(LayoutConfig.id == "default").first()
    if not layout:
        layout = LayoutConfig(id="default")
        db.add(layout)
    if "columns" in data:
        layout.columns = data["columns"]
    if "gap" in data:
        layout.gap = data["gap"]
    if "max_widgets" in data:
        layout.max_widgets = data["max_widgets"]
    if "theme" in data:
        layout.theme = data["theme"]
    db.commit()
    db.refresh(layout)
    return layout.to_dict()
