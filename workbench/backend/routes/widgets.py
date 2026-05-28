"""Widget 配置 CRUD"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import WidgetConfig

router = APIRouter(prefix="/api/widgets", tags=["widgets"])

# 内建 widget 类型列表
BUILTIN_WIDGET_TYPES = [
    {"type": "hello", "name": "你好世界", "icon": "👋"},
    {"type": "clock", "name": "数字时钟", "icon": "🕐"},
]


@router.get("/types")
def list_widget_types():
    """列出可用的 widget 类型（从注册表读取）"""
    return {"types": BUILTIN_WIDGET_TYPES}


@router.get("")
def list_widgets(db: Session = Depends(get_db)):
    widgets = db.query(WidgetConfig).order_by(WidgetConfig.position).all()
    return {"widgets": [w.to_dict() for w in widgets if w.enabled]}


@router.post("")
def create_widget(data: dict, db: Session = Depends(get_db)):
    max_pos = db.query(WidgetConfig).count()
    w = WidgetConfig(
        widget_type=data.get("widget_type", "hello"),
        title=data.get("title", ""),
        config=json.dumps(data.get("config", {})),
        position=data.get("position", max_pos),
        width=data.get("width", 1),
        height=data.get("height", 1),
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"widget": w.to_dict()}


@router.put("/{widget_id}")
def update_widget(widget_id: str, data: dict, db: Session = Depends(get_db)):
    w = db.query(WidgetConfig).filter(WidgetConfig.id == widget_id).first()
    if not w:
        raise HTTPException(404, "Widget not found")
    if "title" in data:
        w.title = data["title"]
    if "config" in data:
        w.config = json.dumps(data["config"])
    if "width" in data:
        w.width = data["width"]
    if "height" in data:
        w.height = data["height"]
    if "enabled" in data:
        w.enabled = data["enabled"]
    db.commit()
    db.refresh(w)
    return {"widget": w.to_dict()}


@router.delete("/{widget_id}")
def delete_widget(widget_id: str, db: Session = Depends(get_db)):
    w = db.query(WidgetConfig).filter(WidgetConfig.id == widget_id).first()
    if not w:
        raise HTTPException(404, "Widget not found")
    db.delete(w)
    db.commit()
    return {"ok": True}


@router.put("/reorder")
def reorder_widgets(data: dict, db: Session = Depends(get_db)):
    order = data.get("order", [])
    for i, wid in enumerate(order):
        w = db.query(WidgetConfig).filter(WidgetConfig.id == wid).first()
        if w:
            w.position = i
    db.commit()
    return {"ok": True}
