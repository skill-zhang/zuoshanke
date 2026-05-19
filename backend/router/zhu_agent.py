"""坐山客本体 API — Schema v0.8"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from agent_core.zhu_agent import ZhuAgentManager

router = APIRouter(tags=["本体"])


@router.get("/api/zhu-agent/status")
def get_zhu_agent_status(db: Session = Depends(get_db)):
    """获取坐山客本体当前状态（mood / observation）"""
    manager = ZhuAgentManager(db)
    return manager.get_status()


@router.post("/api/zhu-agent/mood")
def set_zhu_agent_mood(mood: str, observation: str = "", db: Session = Depends(get_db)):
    """手动更新本体心情（用于测试 / 闲聊频道事件）"""
    manager = ZhuAgentManager(db)
    return manager.update_mood(mood, observation)


@router.post("/api/zhu-agent/observe")
def observe_fenshen_event(event_type: str, scene_name: str = "", db: Session = Depends(get_db)):
    """分身事件 → 本体心情更新（观察通道入口）"""
    manager = ZhuAgentManager(db)
    return manager.observe_fenshen_event(event_type, scene_name)
