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
        """获取本体当前状态（含空闲超时检测）"""
        agent = self.get_or_create()
        mood = agent.mood
        obs = agent.observation

        # 空闲超时：非 idle/resting 状态超过 45 秒 → 自动归位
        REACTIVE_MOODS = {"watching", "analyzing", "thinking", "amused", "annoyed", "speaking"}
        if mood in REACTIVE_MOODS and agent.updated_at:
            from datetime import datetime, timezone
            # SQLite 存储的 datetime 是 naive（无时区），补上 UTC 再比较
            ua = agent.updated_at
            if ua.tzinfo is None:
                from datetime import timezone as tz
                ua = ua.replace(tzinfo=tz.utc)
            now = datetime.now(timezone.utc)
            age = (now - ua).total_seconds()
            if age > 45:
                mood = "idle"
                obs = ""

        return {
            "mood": mood,
            "observation": obs,
            "name": agent.name,
        }

    def update_mood(self, mood: str, observation: Optional[str] = None) -> dict:
        """更新本体心情"""
        VALID_MOODS = {"idle", "watching", "analyzing", "thinking", "amused", "annoyed", "speaking", "resting"}
        if mood not in VALID_MOODS:
            mood = "idle"

        agent = self.get_or_create()
        agent.mood = mood
        if observation is not None:
            agent.observation = observation
        agent.updated_at = utcnow()
        self.db.commit()
        return {"mood": agent.mood, "observation": agent.observation}

    def observe_fenshen_event(self, event_type: str, scene_name: str = ""):
        """分身事件 → 更新本体心情

        这是本体的「观察通道」入口。分身执行的各种事件
        经过这里转化为本体的情绪反应。

        闲聊频道（scene_name="闲聊"）是本体之家，不走分身文案。
        """
        scene_ctx = f"【{scene_name}】" if scene_name else ""

        # 闲聊频道是本体之家，走本体直接表达
        is_zhu_home = (scene_name == "闲聊")

        mood_map = {
            "fenshen:started": ("watching", "" if is_zhu_home else f"看着{scene_ctx}分身开始干活"),
            "fenshen:analyzing": ("analyzing", f"{scene_ctx}分身正在翻数据、调工具…"),
            "fenshen:thinking": ("thinking", f"{scene_ctx}分身正在思考…"),
            "fenshen:tool_success": ("watching", f"{scene_ctx}分身查到了一个结果"),
            "fenshen:discovery": ("amused", f"哦？{scene_ctx}分身发现了好东西"),
            "fenshen:error": ("annoyed", f"啧，{scene_ctx}分身碰壁了"),
            "fenshen:done": ("amused", "" if is_zhu_home else f"{scene_ctx}分身任务完成 ✅"),
            "fenshen:done_with_errors": ("annoyed", f"{scene_ctx}分身干完了，但有几个坑"),
            "user:return": ("watching", "嘿，回来了啊"),
            "idle_timeout": ("resting", ""),
        }
        mood, obs = mood_map.get(event_type, ("watching", ""))
        return self.update_mood(mood, obs)
