"""对话阶段引擎 — 管理场景对话的引导进度。

核心职责：
  1. 阶段状态机：idle → explore → focus → decompose → challenge → finalize → execute
  2. 提供一行阶段提示注入到 LLM system prompt
  3. 检测阶段转移信号（从 LLM 回复中解析）
  4. 持久化 / 恢复阶段状态（跨会话）
  5. 允许跳阶段（向前），不允许回退
  6. decompose 是 execute 的前置条件，不能跳过

使用方式：
    engine = DialogEngine(db, scene_id)
    system_prompt += "\\n" + engine.get_phase_prompt()

    # LLM 回复后检查阶段转移
    next_phase = engine.detect_transition(llm_content)
    if next_phase:
        engine.transition_to(next_phase, summary="...", decisions=[...])
"""

import json
import re
import logging
from datetime import datetime, timezone
from typing import Optional

from models import DialogState

logger = logging.getLogger(__name__)

# ── 阶段定义 ──
PHASES = ["idle", "explore", "focus", "decompose", "challenge", "finalize", "execute"]
PHASE_ORDER = {p: i for i, p in enumerate(PHASES)}

PHASE_DESCRIPTIONS = {
    "idle": "等待中",
    "explore": "探索需求中——开放式提问，每次聚焦一个关键问题",
    "focus": "聚焦目标中——确认核心需求和约束",
    "decompose": "任务分解中——将复杂目标拆解为可执行的子任务",
    "challenge": "挑战验证中——对已有方案提出质疑和假设检验",
    "finalize": "方案定稿中——总结确定的方案和约束清单",
    "execute": "执行中——按方案逐步推进",
}

PHASE_ROLES = {
    "idle": "助手",
    "explore": "引导师",
    "focus": "分析师",
    "decompose": "架构师",
    "challenge": "评审官",
    "finalize": "记录员",
    "execute": "执行引擎",
}

PHASE_NEXT = {
    "idle": "explore",
    "explore": "focus",
    "focus": "decompose",
    "decompose": "challenge",
    "challenge": "finalize",
    "finalize": "execute",
    "execute": None,
}

# ── 阶段转移信号（LLM 回复中包含 [PHASE:xxx] 标记） ──
PHASE_TRANSITION_RE = re.compile(r'\[PHASE:\s*(\w+)\s*\]')


class DialogEngine:
    """对话阶段引擎 — 管理场景对话的引导进度。"""

    def __init__(self, db, scene_id: str):
        self.db = db
        self.scene_id = scene_id
        self._state = self._load_or_create()

    # ── 内部 ─────────────────────────────────────────

    def _load_or_create(self) -> DialogState:
        """加载场景的阶段状态，不存在则创建（默认 idle）。"""
        state = self.db.query(DialogState).filter(
            DialogState.scene_id == self.scene_id
        ).first()
        if not state:
            state = DialogState(
                scene_id=self.scene_id,
                phase="idle",
                summary="",
                decisions=[],
                context={},
            )
            self.db.add(state)
            self.db.commit()
            logger.info(f"[DialogEngine] 新对话状态: scene={self.scene_id}, phase=idle")
        return state

    def _to_dict(self) -> dict:
        """返回当前状态的 dict（不直接暴露 SQLAlchemy 模型给外部）。"""
        return {
            "scene_id": self._state.scene_id,
            "phase": self._state.phase,
            "summary": self._state.summary or "",
            "decisions": self._state.decisions or [],
            "context": self._state.context or {},
        }

    # ── 公共 API ─────────────────────────────────────

    @property
    def phase(self) -> str:
        return self._state.phase

    @property
    def is_active(self) -> bool:
        """是否处于引导模式（即不是 idle 也不是 execute 完成状态）。"""
        return self._state.phase not in ("idle",)

    @property
    def is_complex(self) -> bool:
        """是否已经进入引导模式（非 idle = 复杂问题已触发）。"""
        return self._state.phase != "idle"

    def get_phase_prompt(self) -> str:
        """返回一行阶段提示，注入到 LLM 的 system prompt。

        格式: 「当前角色: 引导师 | 当前阶段: explore — 探索需求中」
        """
        p = self._state.phase
        role = PHASE_ROLES.get(p, "助手")
        desc = PHASE_DESCRIPTIONS.get(p, "")
        return f"当前角色: {role} | 当前阶段: {p} — {desc}"

    def get_transition_instruction(self) -> str:
        """返回阶段转移指令，注入到 system prompt 中。

        告诉 LLM 在阶段完成时如何发出转移信号。
        """
        return (
            "当你觉得当前阶段目标已达成、可以进入下一阶段时，"
            "在回复末尾加上 [PHASE:下一阶段名] 标记。"
            "例如：[PHASE:decompose]。可用的阶段: explore, focus, decompose, challenge, finalize, execute。"
            "可以跳过中间阶段向前，但不要回退。"
        )

    def detect_transition(self, llm_content: str) -> Optional[str]:
        """检测 LLM 回复中是否包含阶段转移信号。

        规则:
          - 只能向前，不能回退
          - 允许跳阶段（如 explore → challenge）
          - decompose 是 execute 的前置条件，
            未经过 decompose 不能进入 execute

        Args:
            llm_content: LLM 回复的文本内容

        Returns:
            目标阶段名，如果没有信号或信号无效则返回 None
        """
        if not llm_content:
            return None

        match = PHASE_TRANSITION_RE.search(llm_content)
        if not match:
            return None

        target = match.group(1).lower()
        current_idx = PHASE_ORDER.get(self._state.phase, 0)
        target_idx = PHASE_ORDER.get(target, -1)

        # 验证阶段名有效
        if target_idx < 0:
            logger.warning(f"[DialogEngine] 无效阶段名: {target}")
            return None

        # 不能回退
        if target_idx <= current_idx:
            logger.warning(
                f"[DialogEngine] 不能回退阶段: {self._state.phase} → {target}"
            )
            return None

        # decompose 是 execute 的前置条件
        if target == "execute":
            context = self._state.context or {}
            if not context.get("decompose_completed", False):
                logger.warning(
                    f"[DialogEngine] 不能跳过 decompose 进入 execute"
                )
                return None

        return target

    def strip_transition_marker(self, llm_content: str) -> str:
        """从 LLM 回复中移除阶段转移标记（不暴露给用户）。"""
        return PHASE_TRANSITION_RE.sub("", llm_content).strip()

    def transition_to(self, phase: str, summary: str = "",
                      decisions: Optional[list] = None,
                      context: Optional[dict] = None) -> bool:
        """执行阶段转移。

        Args:
            phase: 目标阶段
            summary: 当前讨论摘要
            decisions: 已确定的决策列表
            context: 关键上下文 key-value

        Returns:
            True 成功，False 失败
        """
        if phase not in PHASES:
            logger.warning(f"[DialogEngine] 无效阶段: {phase}")
            return False

        now = datetime.now(timezone.utc)
        self._state.phase = phase

        # 标记 decompose 已完成（用于 execute 前置条件检查）
        if phase == "decompose":
            ctx = dict(self._state.context or {})
            ctx["decompose_completed"] = True
            self._state.context = ctx

        if summary:
            self._state.summary = summary
        if decisions is not None:
            # 追加到已有决策（新决策最有价值，排前面）
            existing = self._state.decisions or []
            self._state.decisions = decisions + existing
        if context is not None:
            self._state.context = {**self._state.context, **context}
        self._state.updated_at = now
        self.db.commit()

        logger.info(
            f"[DialogEngine] 阶段转移: scene={self.scene_id} "
            f"→ {phase}"
        )
        return True

    def reset(self) -> bool:
        """重置到 idle（用户说「重新开始」时调用）。"""
        self._state.phase = "idle"
        self._state.summary = ""
        self._state.decisions = []
        self._state.context = {}
        self._state.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.info(f"[DialogEngine] 重置: scene={self.scene_id}")
        return True

    def update_from_conversation(self, user_msg: str, llm_content: str) -> dict:
        """每轮对话后调用：检测转移 + 剥离标记 + 返回操作摘要。

        Args:
            user_msg: 用户本轮消息
            llm_content: LLM 回复的原始内容（含可能的 [PHASE:] 标记）

        Returns:
            {"transited": bool, "phase": str, "content": str（剥离后）}
        """
        result = {
            "transited": False,
            "phase": self._state.phase,
            "content": self.strip_transition_marker(llm_content),
        }

        target = self.detect_transition(llm_content)
        if target:
            self.transition_to(target)
            result["transited"] = True
            result["phase"] = target

        return result

    @classmethod
    def load_state(cls, db, scene_id: str) -> Optional[dict]:
        """静态方法：加载场景的阶段状态摘要（用于跨会话恢复）。"""
        state = db.query(DialogState).filter(
            DialogState.scene_id == scene_id
        ).first()
        if not state or state.phase == "idle":
            return None
        return {
            "scene_id": scene_id,
            "phase": state.phase,
            "summary": state.summary or "",
            "decisions": state.decisions or [],
        }
