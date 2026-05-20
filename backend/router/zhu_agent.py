"""坐山客本体 API — Schema v0.8

包含秘密花园（秘密花园）数据聚合端点。
"""
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from agent_core.zhu_agent import ZhuAgentManager
from agent_core.memory_manager import MemoryManager
from models import Scene, Channel, ThinkNode
from utils import utcnow

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


# ═══ 秘密花园 — 坐山客内心世界 ═══

@router.get("/api/zhu-agent/garden")
def get_secret_garden(db: Session = Depends(get_db)):
    """🌸 秘密花园 — 坐山客内心世界的聚合窗口

    返回本体状态、记忆花园、成长年轮、协作金石等数据。
    """
    # ① 本体状态
    manager = ZhuAgentManager(db)
    status = manager.get_status()

    # ② 本体记忆 (scope=zhu) — 记忆花园
    mm = MemoryManager(db)
    all_memories = mm.list_all(scope="zhu")
    memory_count = len(all_memories)
    top_memories = sorted(all_memories, key=lambda m: m.get("weight", 0) or 0, reverse=True)[:20]
    memory_items = [
        {
            "content": (m.get("content", "") or "")[:120] + ("…" if len(m.get("content", "") or "") > 120 else ""),
            "key": m.get("key", ""),
            "weight": m.get("weight", 0) or 0,
            "level": m.get("level", 0) or 0,
            "created_at": str(m.get("created_at", "")) if m.get("created_at") else None,
        }
        for m in top_memories
    ]

    # ③ 成长年轮 — 统计数据
    scene_count = db.query(Scene).count()
    channel_count = db.query(Channel).count()
    # 工具注册数：读取 registry.json
    tool_count = 0
    try:
        import json
        reg_path = Path(__file__).resolve().parent.parent.parent / "tools" / "registry.json"
        if reg_path.exists():
            reg = json.loads(reg_path.read_text())
            tool_count = len(reg)
    except Exception:
        pass
    # 技能数：读取 skills 目录
    skill_count = 0
    try:
        skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
        if skills_dir.exists():
            skill_count = len([d for d in skills_dir.iterdir() if d.is_dir()])
    except Exception:
        pass
    # 思绪 = 所有 Thinking Map 节点数
    thought_count = db.query(ThinkNode).count()

    # ④ 协作历史年轮
    milestones = [
        {"date": "2026-05-28", "icon": "📜", "text": "坐山客设计哲学确立 — 本体不可篡改纲要"},
        {"date": "2026-05-27", "icon": "🔄", "text": "自动收敛+产出闭环打通 — 分身自主交付"},
        {"date": "2026-05-26", "icon": "🎭", "text": "Schema v0.8 身份架构 — 本体/分身/闲聊频道"},
        {"date": "2026-05-23", "icon": "🌳", "text": "Agent Loop 仪表盘 — 6 面板思维可视化"},
        {"date": "2026-05-20", "icon": "🧠", "text": "LLM 自主管理记忆 — 不干规则匹配"},
        {"date": "2026-05-18", "icon": "🤖", "text": "Agent Loop 引擎v1 — 贪吃蛇里程碑"},
        {"date": "2026-05-16", "icon": "🏗️", "text": "坐山客项目启动 — 双图架构"},
    ]

    return {
        "name": status.get("name", "坐山客"),
        "mood": status.get("mood", "idle"),
        "observation": status.get("observation", ""),
        "memory_garden": {
            "total": memory_count,
            "items": memory_items,
        },
        "growth": {
            "scenes": scene_count,
            "tools": tool_count,
            "skills": skill_count,
            "channels": channel_count,
            "thoughts": thought_count,
            "versions": "v0.8",
        },
        "milestones": milestones,
        "updated_at": str(utcnow()) if True else None,
    }
