"""坐山客本体管理器 — Schema v0.8

管理 ZhuAgent 的持久化状态：mood、observation，
并在分身事件发生时更新本体状态。
"""

from typing import Optional
from models import ZhuAgent
from utils import make_id, utcnow


class ZhuAgentManager:
    """坐山客本体管理器"""

    def __init__(self, db):
        self.db = db

    def get_or_create(self) -> ZhuAgent:
        """获取本体记录，不存在则创建"""
        agent = self.db.query(ZhuAgent).first()
        if not agent:
            agent = ZhuAgent(
                id=make_id("zhu"),
                name="坐山客",
                mood="idle",
                observation="",
                core_prompt="",
            )
            self.db.add(agent)
            self.db.commit()
            self.db.refresh(agent)
        return agent

    def get_status(self) -> dict:
        """获取本体当前状态"""
        agent = self.get_or_create()
        return {
            "mood": agent.mood,
            "observation": agent.observation,
            "name": agent.name,
        }

    def update_mood(self, mood: str, observation: str = "") -> dict:
        """更新本体心情"""
        VALID_MOODS = {"idle", "watching", "thinking", "amused", "annoyed", "speaking", "resting"}
        if mood not in VALID_MOODS:
            mood = "idle"

        agent = self.get_or_create()
        agent.mood = mood
        if observation:
            agent.observation = observation
        agent.updated_at = utcnow()
        self.db.commit()
        return {"mood": agent.mood, "observation": agent.observation}

    def observe_fenshen_event(self, event_type: str, scene_name: str = ""):
        """分身事件 → 更新本体心情

        这是本体的「观察通道」入口。分身执行的各种事件
        经过这里转化为本体的情绪反应。
        """
        scene_ctx = f"【{scene_name}】" if scene_name else ""

        mood_map = {
            "fenshen:started": ("watching", f"看着{scene_ctx}分身开始干活"),
            "fenshen:thinking": ("thinking", f"{scene_ctx}分身正在思考…"),
            "fenshen:tool_success": ("watching", f"{scene_ctx}分身查到了一个结果"),
            "fenshen:discovery": ("amused", f"哦？{scene_ctx}分身发现了好东西"),
            "fenshen:error": ("annoyed", f"啧，{scene_ctx}分身碰壁了"),
            "fenshen:done": ("amused", f"{scene_ctx}分身任务完成 ✅"),
            "fenshen:done_with_errors": ("annoyed", f"{scene_ctx}分身干完了，但有几个坑"),
            "user:return": ("watching", "嘿，回来了啊"),
            "idle_timeout": ("resting", ""),
        }
        mood, obs = mood_map.get(event_type, ("watching", ""))
        return self.update_mood(mood, obs)
