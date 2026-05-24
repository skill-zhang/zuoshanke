"""高危命令审批 — 用户确认/拒绝被阻断的命令

用户通过前端弹窗批准或拒绝高危命令时，此模块记录审批结果。
后续 LLM 可以通过外部知识（审批记录）决定是否重试。
"""

import threading
from typing import Optional
from fastapi import APIRouter

router = APIRouter(tags=["高危命令审批"])

# 线程安全的审批记录
_approval_lock = threading.Lock()
_approved_commands: dict[str, bool] = {}  # command_hash → approved


class ApprovalRequest:
    """审批请求"""
    command: str
    approved: bool


@router.post("/api/agent-loop/command-approval")
def command_approval(data: dict):
    """记录用户的命令审批结果"""
    command = data.get("command", "")
    approved = data.get("approved", False)

    if not command:
        return {"ok": False, "error": "缺少 command"}

    with _approval_lock:
        _approved_commands[command] = approved

    status = "已批准" if approved else "已拒绝"
    print(f"[command_approval] {status}: {command[:120]}")
    return {"ok": True, "status": status}


def is_command_approved(command: str) -> Optional[bool]:
    """检查某个命令是否已被用户批准

    Returns:
        True: 已批准
        False: 已拒绝
        None: 无记录
    """
    with _approval_lock:
        return _approved_commands.get(command)


def clear_approvals():
    """清空所有审批记录（安全重置用）"""
    with _approval_lock:
        _approved_commands.clear()
