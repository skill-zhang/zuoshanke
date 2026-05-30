from typing import Optional
"""工作台对话 SSE 端点 — Avatar 对话回应（Phase 2）

Phase 1: 接收用户输入 → 轻量 LLM 调用 → 流式返回 speech 事件
Phase 2: speech:done → 解析意图 → 执行场景操作 → yield action 事件
"""
import json
import logging
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from agent_core.zhu_agent import ZhuAgentManager
from ai_engine import call_llm, call_llm_stream, get_settings
from models import Scene
from router.shared import sse_event, sse_response

_log = logging.getLogger(__name__)

router = APIRouter(tags=["工作台"])


class WorkbenchChatRequest(BaseModel):
    content: str
    scene_ids: list[str] = []


def _parse_actions(text: Optional[str]) -> list[dict]:
    """解析 LLM 返回的 JSON action 列表（3 层容错）"""
    if not text or not text.strip():
        return []
    # 策略 1：直接解析
    try:
        data = json.loads(text)
        return data.get("actions", [])
    except json.JSONDecodeError:
        pass
    # 策略 2：提取 {} 块（LLM 可能前后加说明文字）
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        try:
            data = json.loads(brace_match.group())
            return data.get("actions", [])
        except json.JSONDecodeError:
            pass
    # 策略 3：修复尾逗号
    fixed = re.sub(r',\s*}', '}', text)
    fixed = re.sub(r',\s*]', ']', fixed)
    try:
        data = json.loads(fixed)
        return data.get("actions", [])
    except json.JSONDecodeError:
        pass
    return []


def _execute_action(db: Session, action: dict) -> dict:
    """执行单个动作，不提交事务（由调用方统一 commit）"""
    atype = action.get("type", "")
    scene_id = action.get("scene_id", "")
    result = {"type": atype, "scene_id": scene_id}

    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        _log.warning(f"[workbench_chat] scene not found: {scene_id}")
        return result

    if atype == "reorder":
        new_pos = action.get("new_position")
        if new_pos is not None:
            scene.workbench_position = int(new_pos)
            _log.info(f"[workbench_chat] reorder {scene.name} → pos {new_pos}")

    elif atype == "pin":
        scene.show_on_workbench = True
        _log.info(f"[workbench_chat] pin {scene.name}")

    elif atype == "unpin":
        scene.show_on_workbench = False
        _log.info(f"[workbench_chat] unpin {scene.name}")

    elif atype == "update":
        config = action.get("config", {})
        if config:
            existing = scene.scene_config or {}
            existing.update(config)
            scene.scene_config = existing
            _log.info(f"[workbench_chat] update {scene.name} config")

    return result


def _generate_speech(req: WorkbenchChatRequest, db: Session):
    """生成工作台 Avatar 对话 SSE 流

    事件序列：
      speech:token    — 逐 token 推送（打字机效果）
      speech:done     — Avatar 说完
      action:xxx      — 场景操作事件（reorder/pin/unpin/update）
      action:reload   — 前端刷新信号
      done            — 全流程完成
    """
    _log.info(f"[workbench_chat] content={req.content[:60]}")
    zhu = ZhuAgentManager(db)
    route_cfg = get_settings("channel")

    # ═══ Phase 1: Avatar 回话 ═══
    zhu.update_mood("speaking", "")
    speech_prompt = (
        "你是坐山客，用户的 AI 伙伴。\n\n"
        f"用户在工作台对你说：{req.content}\n\n"
        "生成一句简短自然的回复（不超过 50 字），"
        "表示已收到用户的请求。"
        "⚠️ 重要：不要声称已经完成了任何操作——"
        "你只是收到了请求，后续会由系统执行。"
        "例如，用户说「调整顺序」，回复「好的，我来调整一下顺序」"
        "而不是「已经调整好了」。"
    )
    reply = ""
    try:
        for token in call_llm_stream(
            [{"role": "user", "content": speech_prompt}],
            route_cfg, temperature=0.5, max_tokens=200
        ):
            if token is None:
                break
            reply += token
            yield sse_event("speech:token", text=reply)
    except Exception as e:
        _log.error(f"[workbench_chat] LLM error: {e}")
        reply = "好的，收到。"
        yield sse_event("speech:token", text=reply)

    yield sse_event("speech:done", text=reply)

    # ═══ Phase 2: 意图解析 + 执行操作 ═══
    if req.scene_ids:
        # 查询场景列表（按 workbench_position 排序）
        scenes = (
            db.query(Scene)
            .filter(Scene.id.in_(req.scene_ids))
            .order_by(Scene.workbench_position)
            .all()
        )
        scene_list = "\n".join(
            f'{i+1}. "{s.name}" (id: {s.id}, pos: {s.workbench_position}, category: {s.category})'
            for i, s in enumerate(scenes)
        )

        zhu.update_mood("thinking", "分析你的需求…")
        intent_prompt = (
            f"你是一个工作台管理助手。工作台当前场景列表（按显示顺序）：\n{scene_list}\n\n"
            f"用户说：{req.content}\n\n"
            "理解用户意图，返回 JSON 格式的操作列表。\n\n"
            "支持的操作类型：\n"
            "- reorder: 调整场景顺序，需指定 scene_id + new_position（从0开始）\n"
            "- pin: 将场景添加到工作台 (show_on_workbench=true)\n"
            "- unpin: 从工作台移除场景 (show_on_workbench=false)\n"
            "- update: 更新场景的 scene_config，需指定 scene_id + config dict\n\n"
            "如果用户提到的「卡片N」对应列表中的第N项。\n"
            "如果无法理解意图，返回 {\"actions\": []}\n\n"
            '返回格式：{"actions": [{"type": "reorder", "scene_id": "...", "new_position": 0}]}'
        )

        try:
            intent_text = call_llm(
                [{"role": "user", "content": intent_prompt}],
                route_cfg, temperature=0.1, max_tokens=800
            )
            if intent_text:
                actions = _parse_actions(intent_text)
                _log.info(f"[workbench_chat] parsed {len(actions)} actions: {actions}")

                if actions:
                    # 统一事务：所有操作成功才 commit
                    try:
                        for act in actions:
                            result = _execute_action(db, act)
                            yield sse_event(f"action:{result['type']}", **result)
                        db.commit()
                        yield sse_event("action:reload")
                    except GeneratorExit:
                        # 客户端断连：不 yield、不回滚（commit 已成功或没执行）
                        return
                    except Exception as e:
                        db.rollback()
                        _log.error(f"[workbench_chat] actions failed, rolled back: {e}")
                        zhu.update_mood("annoyed", f"操作未完成：{e}")

        except Exception as e:
            _log.error(f"[workbench_chat] intent parse error: {e}")

    # done 事件同样防 GeneratorExit
    zhu.update_mood("amused", "")
    try:
        yield sse_event("done")
    except GeneratorExit:
        return


@router.post("/api/workbench/chat")
def workbench_chat(req: WorkbenchChatRequest, db: Session = Depends(get_db)):
    """工作台聊天 — SSE 流式返回 Avatar 回应 + 场景操作"""
    return sse_response(_generate_speech(req, db))
