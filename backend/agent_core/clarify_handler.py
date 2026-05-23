"""Clarify Handler — 阻塞式 Callback 模式

核心设计：
  Agent Loop 调 clarify 工具 → callback() 创建一个 threading.Event
  → 阻塞等待用户回复 → SSE 发送给前端 → 用户点选/输入 → POST 回后端
  → event.set() → callback 返回 → Agent Loop 继续

这与「暂停循环再恢复」不同：Agent Loop 的同步函数自然阻塞，
不需要改循环逻辑。
"""

import json
import threading
import time
import uuid
from typing import Optional


class ClarifyRequest:
    """一次等待用户回复的 clarify 请求"""

    def __init__(self, question: str, choices: Optional[list[str]] = None):
        self.event_id = f"clar_{uuid.uuid4().hex[:12]}"
        self.question = question
        self.choices = choices
        self.event = threading.Event()
        self.response: str = ""
        self.created_at = time.time()
        self.resolved: bool = False

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "question": self.question,
            "choices": self.choices,
        }

    def to_result(self) -> str:
        """给 LLM 回调用的 JSON 结果"""
        return json.dumps({
            "event_id": self.event_id,
            "question": self.question,
            "choices_offered": self.choices,
            "user_response": self.response.strip(),
        }, ensure_ascii=False)


class ClarifyHandler:
    """全局单例：管理正在等待用户回复的 clarify 请求"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._pending: dict[str, ClarifyRequest] = {}

    @classmethod
    def get_instance(cls) -> "ClarifyHandler":
        if cls._instance is None:
            cls._instance = ClarifyHandler()
        return cls._instance

    def create_request(self, question: str, choices: Optional[list[str]] = None) -> ClarifyRequest:
        """创建一个新的 clarify 请求，返回请求对象（含 event_id）"""
        req = ClarifyRequest(question, choices)
        with self._lock:
            # 清理已过时的 pending（超过 5 分钟的自动放弃）
            now = time.time()
            stale = [eid for eid, r in self._pending.items() if now - r.created_at > 300]
            for eid in stale:
                del self._pending[eid]
            self._pending[req.event_id] = req
        return req

    def wait_for_response(self, event_id: str, timeout: int = 300) -> str:
        """阻塞等待用户回复，返回用户输入

        超时返回超时提示。清除非 pending。
        """
        req = self._pending.get(event_id)
        if not req:
            return json.dumps({"error": f"请求 {event_id} 不存在或已过期"}, ensure_ascii=False)

        # 最多等 timeout 秒
        ok = req.event.wait(timeout=timeout)

        # 清理
        with self._lock:
            self._pending.pop(event_id, None)

        if not ok:
            return json.dumps({"error": "等待用户回复超时", "event_id": event_id}, ensure_ascii=False)

        req.resolved = True
        return req.to_result()

    def resolve_request(self, event_id: str, response: str) -> bool:
        """前端调用的 API 端点 → 解锁等待的线程

        Returns:
            True=成功解锁, False=请求不存在或已过期
        """
        req = self._pending.get(event_id)
        if not req:
            return False
        req.response = response
        req.event.set()
        # 从 pending 中移除（避免 get_pending_event_id 仍返回它）
        with self._lock:
            self._pending.pop(event_id, None)
        return True

    def cancel_request(self, event_id: str):
        """取消一个 pending 的请求"""
        with self._lock:
            req = self._pending.pop(event_id, None)
            if req:
                req.response = "[user cancelled]"
                req.event.set()

    def get_pending_event_id(self) -> Optional[str]:
        """返回当前是否有 pending 的 clarify（前端轮询用）"""
        with self._lock:
            for eid, req in list(self._pending.items()):
                if not req.resolved:
                    return eid
        return None

    def get_pending_info(self, event_id: str) -> Optional[dict]:
        """获取 pending 请求的信息（前端获取详情用）"""
        req = self._pending.get(event_id)
        if not req or req.resolved:
            return None
        return req.to_dict()
