"""独立工作台后端 — 数据模型"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime
from database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id():
    return f"wb_{uuid.uuid4().hex[:12]}"


class WidgetConfig(Base):
    """widget 实例配置"""
    __tablename__ = "widget_configs"

    id = Column(String, primary_key=True, default=new_id)
    widget_type = Column(String, nullable=False)
    title = Column(String, default="")
    config = Column(Text, default="{}")
    position = Column(Integer, default=0)
    width = Column(Integer, default=1)
    height = Column(Integer, default=1)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "widget_type": self.widget_type,
            "title": self.title,
            "config": self.config,
            "position": self.position,
            "width": self.width,
            "height": self.height,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LayoutConfig(Base):
    """整体布局配置"""
    __tablename__ = "layout_configs"

    id = Column(String, primary_key=True, default="default")
    columns = Column(Integer, default=3)
    gap = Column(Integer, default=16)
    max_widgets = Column(Integer, default=20)
    theme = Column(String, default="dark")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self):
        return {
            "columns": self.columns,
            "gap": self.gap,
            "max_widgets": self.max_widgets,
            "theme": self.theme,
        }
