"""场景流式消息 — stream_scene_message + Agent Loop 引擎"""
import json
import os
import re
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import Scene, ThinkingMap, ThinkNode, Message, SceneAsset, PriorityQueue, ProjectOutput, FileSnapshot
from schemas import MessageOut, MessageCreate, SceneExportOut
from ai_engine import call_deepseek_chat, extract_and_classify, get_settings
from agent_core.token_counter import (
    estimate_messages_tokens, get_context_length_from_route,
    context_usage_str, progress_bar,
)
from agent_core.memory_manager import MemoryManager
from agent_core.memory_extractor import MemoryExtractor
from agent_core.context_builder import build_agent_context_v1
from agent_core.priority_assigner import extract_priority
from utils import make_id, utcnow, iso_utc
from router.shared import sse_event, sse_response
from router.clarify_router import make_clarify_callback  # 🆕 Clarify 回调注入

router = APIRouter(tags=["场景流式"])

# 🆕 Schema v1.1: Web session 辅助

def _ensure_web_session(db, context_type: str, context_id: str, context_name: str | None = None):
    """获取或创建 Web session，供场景/频道流式端点集成"""
    from models import WebSession
    from utils import make_id
    ws = db.query(WebSession).filter(
        WebSession.context_type == context_type,
        WebSession.context_id == context_id,
        WebSession.status == "active",
    ).first()
    if ws:
        return ws
    ws = WebSession(
        id=make_id("ws"),
        context_type=context_type,
        context_id=context_id,
        context_name=context_name,
        status="active",
        started_at=utcnow(),
        last_active_at=utcnow(),
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


# ═══ 工具卡片 ═══
def _build_tool_cards(tool_results: list[dict]) -> list[dict]:
    """将预执行工具结果转为前端可渲染的卡片数据

    Returns:
        [{"type": "weather"|"attractions"|"equipment", "data": {...}}, ...]
    """
    cards = []
    for r in tool_results:
        if not r.get("success") or not r.get("result"):
            continue
        tool = r["tool"]
        res = r["result"]

        if tool == "get_weather" and isinstance(res, dict):
            cards.append({
                "type": "weather",
                "data": {
                    "city": res.get("city", ""),
                    "desc": res.get("desc", ""),
                    "temp": res.get("temp", ""),
                    "humidity": res.get("humidity", ""),
                    "wind": res.get("wind", ""),
                    "forecast": res.get("forecast", []),
                    "hourly": res.get("hourly", []),
                },
            })

        elif tool == "recommend_attractions" and isinstance(res, dict):
            cards.append({
                "type": "attractions",
                "data": {
                    "city": res.get("city", ""),
                    "category_label": res.get("category_label", ""),
                    "default_category": res.get("default_category", ""),
                    "total_matched": res.get("total_matched", 0),
                    "items": [
                        {
                            "name": it.get("name", ""),
                            "category": it.get("category", ""),
                            "tags": it.get("tags", []),
                            "indoor": it.get("indoor", False),
                            "note": it.get("note", ""),
                            "score": it.get("score", 0),
                        }
                        for it in (res.get("items", []) or [])
                    ],
                },
            })

        elif tool == "get_equipment_checklist" and isinstance(res, dict):
            items = res.get("items", []) or []
            cards.append({
                "type": "equipment",
                "data": {
                    "label": res.get("label", ""),
                    "icon": res.get("icon", ""),
                    "default_category": res.get("default_category", ""),
                    "total": res.get("total", 0),
                    "must_have": res.get("must_have", 0),
                    "recommended": res.get("recommended", 0),
                    "optional": res.get("optional", 0),
                    "items": [
                        {
                            "name": it.get("name", ""),
                            "necessity": it.get("necessity", ""),
                            "note": it.get("note", ""),
                        }
                        for it in items
                    ],
                },
            })

    return cards


# ═══ 场景记忆提取（跨会话持久化） ═══


@router.post("/api/scenes/{scene_id}/extract-memory")
def extract_scene_memory(scene_id: str, db: Session = Depends(get_db)):
    """从场景的最新对话中提取关键信息，存为场景级记忆

    修复：只处理未提取过的消息（memory_extracted=False），处理后打标。
    避免同一批消息被反复提取 → 记忆只增不减 + 权重暴涨。
    """
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    # 读取未提取过的消息
    msgs = (
        db.query(Message)
        .filter(
            Message.scene_id == scene_id,
            Message.role.in_(["user", "ai"]),
            Message.memory_extracted == False,
        )
        .order_by(Message.created_at.asc())
        .limit(30)
        .all()
    )
    if len(msgs) < 2:
        return {"ok": True, "extracted": 0, "reason": "无未提取的消息"}

    messages_dict = [{"role": m.role, "content": m.content} for m in msgs]

    # 调 LLM 提取
    from agent_core.memory_extractor import extract_from_conversation, save_extracted_memories

    entries = extract_from_conversation(messages_dict, scene_name=scene.name)
    saved = 0
    if entries:
        saved = save_extracted_memories(db, entries, scene_id, scene_name=scene.name)

    # 标记所有已处理的消息为「已提取」
    for m in msgs:
        m.memory_extracted = True
    db.commit()

    return {"ok": True, "extracted": saved, "total_candidates": len(entries)}


# ═══ Schema v0.81: 异步收敛检查 ═══

import threading as _threading

_CONVERGE_LOCKS = {}  # scene_id → lock, 防止同一场景并发收敛
_CONVERGE_LOCK = _threading.Lock()


def _migrate_schema_v081(db):
    """为已有 DB 添加 Schema v0.81 新列和新表（安全执行，不报错）"""
    from sqlalchemy import text as _sa_text
    # 新表由 create_all 自动创建，这里只处理 ALTER TABLE
    for col, col_type in [
        ("converge_threshold", "FLOAT DEFAULT 2.0"),
        ("converge_enabled", "BOOLEAN DEFAULT 1"),
        ("diverge_min_rounds", "INTEGER DEFAULT 2"),
    ]:
        try:
            db.execute(_sa_text(f"ALTER TABLE scenes ADD COLUMN {col} {col_type}"))
        except Exception:
            pass  # 已有该列
    # project_outputs 加 project_id
    try:
        db.execute(_sa_text("ALTER TABLE project_outputs ADD COLUMN project_id VARCHAR REFERENCES output_projects(id)"))
    except Exception:
        pass
    db.commit()


def _build_diverge_context(db, scene_id: str) -> str:
    """构建 auto-diverge 的完整上下文（非单条消息）"""
    from models import Scene, Message
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        return ""
    parts = [f"场景名称：{scene.name}"]
    if scene.user_context:
        parts.append(f"场景设定：{scene.user_context[:200]}")
    # 取最近 10 条对话
    msgs = db.query(Message).filter(
        Message.scene_id == scene_id,
        Message.role.in_(["user", "ai"]),
    ).order_by(Message.created_at.desc()).limit(10).all()
    msgs.reverse()
    if msgs:
        dialog_lines = []
        for m in msgs:
            role = "用户" if m.role == "user" else "AI"
            content = m.content[:200]
            dialog_lines.append(f"{role}: {content}")
        parts.append("对话历史：\n" + "\n".join(dialog_lines))
    return "\n\n".join(parts)


def _async_converge_worker(scene_id: str):
    """后台异步收敛检查线程"""
    from database import SessionLocal
    from models import Scene, ThinkingMap, ThinkNode, Message
    from agent_core.converge_engine import (
        auto_converge_and_prioritize,
        check_converge_threshold,
    )

    # 每个场景一把锁，防止并发
    with _CONVERGE_LOCK:
        if scene_id not in _CONVERGE_LOCKS:
            _CONVERGE_LOCKS[scene_id] = _threading.Lock()

    if not _CONVERGE_LOCKS[scene_id].acquire(blocking=False):
        print(f"[converge] 场景 {scene_id} 已有收敛线程在跑，跳过本轮")
        return

    try:
        db = SessionLocal()
        try:
            scene = db.query(Scene).filter(Scene.id == scene_id).first()
            if not scene or not scene.converge_enabled:
                return

            # 闲聊场景跳过
            if "闲聊" in (scene.name or ""):
                return

            # 统计 AI 回复轮数
            ai_rounds = db.query(Message).filter(
                Message.scene_id == scene_id,
                Message.role == "ai",
            ).count()

            # 查找场景的 ThinkingMap
            tmap = db.query(ThinkingMap).filter(
                ThinkingMap.scene_id == scene_id
            ).first()

            if not tmap:
                # 轮数不够？跳过
                if ai_rounds < (scene.diverge_min_rounds or 2):
                    return
                # 需要建树 — 但此时 auto-diverge 已被 SSE 流中同步执行处理
                # 这里仅做收敛检查
                return

            # 检查已有节点（不含 root）
            nodes = db.query(ThinkNode).filter(
                ThinkNode.map_id == tmap.id,
                ThinkNode.type != "root",
            ).all()

            if not nodes or len(nodes) <= 1:
                return

            # 用 converge_engine 的统一阈值检查（消除重复逻辑）
            threshold = scene.converge_threshold or 2.0
            if not check_converge_threshold(nodes, threshold):
                return

            # 统计用于日志
            node_ids = set(n.id for n in nodes)
            children_map = {}
            for n in nodes:
                if n.parent_id and n.parent_id in node_ids:
                    children_map.setdefault(n.parent_id, []).append(n.id)
            leaves = [n for n in nodes if n.id not in children_map]
            branches = [n for n in nodes if n.id in children_map]

            print(f"[converge] 自动触发收敛: scene={scene_id}, leaf={len(leaves)}, branch={len(branches)}, threshold={threshold}")

            # 执行收敛
            result = auto_converge_and_prioritize(db, scene_id, tmap)
            if result.get("project"):
                print(f"[converge] 项目认知: {result['project']}")

        finally:
            db.close()
    finally:
        _CONVERGE_LOCKS[scene_id].release()


def start_async_converge_check(scene_id: str):
    """启动异步收敛检查（在 SSE done 后调用）"""
    t = _threading.Thread(target=_async_converge_worker, args=(scene_id,), daemon=True)
    t.start()


# ═══ 场景流式 ═══

@router.post("/api/scenes/{scene_id}/stream")
def stream_scene_message(scene_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到场景 + 流式 SSE 返回 AI 回复"""
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    user_msg = Message(
        id=make_id("msg"), scene_id=scene_id,
        role="user", content=data.content, session_id=data.session_id,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 🆕 Schema v1.1: 确保 Web session 存在（若无 session_id，自动创建/激活）
    ws = _ensure_web_session(db, "scene", scene_id, scene.name)
    # 更新 last_active_at
    ws.last_active_at = utcnow()
    ws.updated_at = utcnow()
    db.commit()

    def generate():
        nonlocal scene
        # 1. 用户消息事件
        yield sse_event("user_msg", id=user_msg.id, role="user",
                        content=user_msg.content, created_at=iso_utc(user_msg.created_at))

        # 2. 历史消息（session 隔离）
        q = db.query(Message).filter(Message.scene_id == scene_id)
        if data.session_id:
            q = q.filter(Message.session_id == data.session_id)
        scene_history = q.order_by(Message.created_at.desc()).limit(20).all()
        scene_history.reverse()
        history_messages = [
            {"role": m.role, "content": m.content}
            for m in scene_history if m.id != user_msg.id
        ]

        # 3. 约束提取 + 路由
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        need_extraction = scene.constraints is None or not scene.constraints_locked
        if need_extraction:
            result = extract_and_classify(data.content, scene.complexity, scene.constraints)
            scene.constraints = result["constraints"]
            scene.complexity = result["complexity"]
            scene.constraints_locked = result["constraints_locked"]
            db.commit()
            complexity, constraints_ok = result["complexity"], result["constraints_locked"]
            missing_info = result.get("missing_info", [])
        else:
            complexity, constraints_ok = scene.complexity or "medium", True
            missing_info = []

        user_ctx = scene.user_context

        # ── Agent Loop：LLM 自主决策调工具（替代预执行 + 规则路由） ──
        from agent_core.agent_loop import run_agent_loop
        from agent_core.context_builder import build_agent_context_v1

        # Schema v1.0: 使用 Context Composer 7 层精炼构建上下文
        agent_messages = build_agent_context_v1(
            user_content=data.content,
            history_messages=history_messages,
            user_context=scene.user_context,
            db=db,
            scene_id=scene_id,
            scene_name=scene.name,
            work_output_window=3,
        )

        # 🆕 Dialog Engine: 初始化/恢复阶段状态
        from agent_core.dialog_engine import DialogEngine
        dialog_engine = DialogEngine(db, scene_id)

        # 🆕 Schema v0.8: 本体观察 — 分身启动
        from agent_core.zhu_agent import ZhuAgentManager
        _zhu = ZhuAgentManager(db)
        _zhu.observe_fenshen_event("fenshen:started", scene.name)

        # 🆕 自开发场景：注入 clarify 回调
        tool_callbacks = {}
        if scene.name and "自开发" in scene.name:
            def _yield_clarify_event(clarify_data: dict):
                """在 generate() 内部 yield SSE 事件"""
                yield sse_event("zhu:clarify", **clarify_data)

            clarify_cb = make_clarify_callback(scene_id, _yield_clarify_event)
            tool_callbacks["clarify"] = clarify_cb

        agent_stream = run_agent_loop(
            initial_messages=agent_messages,
            max_steps=99,
            dialog_engine=dialog_engine,
            scene_id=scene_id,  # 🆕 Schema v0.7
            scene_config=scene.scene_config or {},
            tool_callbacks=tool_callbacks or None,  # 🆕 工具回调
        )

        model_name = "DeepSeek Flash"
        full_reply = ""

        yield sse_event("model_info", model=model_name, complexity=complexity)

        # ── Context 用量估算 ──
        api_msgs = history_messages + [{"role": "user", "content": data.content}]
        total_tokens = estimate_messages_tokens(api_msgs)
        max_tokens = get_context_length_from_route(get_settings("scene"))
        pct = round(total_tokens / max_tokens * 100, 1) if max_tokens > 0 else 0
        yield sse_event("context_info",
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            percentage=pct,
            usage_str=context_usage_str(total_tokens, max_tokens),
            progress_bar=progress_bar(pct),
            history_count=len(history_messages),
        )
        if pct >= 75:
            yield sse_event("capacity_warning",
                total_tokens=total_tokens,
                max_tokens=max_tokens,
                percentage=pct,
                message=(
                    f"⚠️ 上下文已使用 {context_usage_str(total_tokens, max_tokens)}，"
                    f"建议压缩摘要或重置会话以避免达到上限。"
                ),
            )

        # ── 流式收 Agent Loop 回复 ──
        agent_tool_results = []
        try:
            for event in agent_stream:
                etype = event["type"]
                if etype == "tool_start":
                    # 🆕 Clarify 工具：发射询问事件给前端（在工具阻塞前）
                    if event["tool"] == "clarify":
                        args = event.get("args", {})
                        yield sse_event("zhu:clarify",
                            question=args.get("question", ""),
                            choices=args.get("choices"),
                        )
                    # 🆕 Delegate 工具：发射子任务状态
                    elif event["tool"] == "delegate_task":
                        args = event.get("args", {})
                        tasks = args.get("tasks", []) or [{"goal": args.get("goal", "未知任务")}]
                        yield sse_event("child:started",
                            tasks=[{"goal": t.get("goal", "?"), "status": "running"} for t in tasks],
                        )
                    yield sse_event("tool_status", tool=event["tool"], status="running",
                                    message=f"正在执行：{event['tool']}...")
                    # 🆕 分身开始调工具 → analyzing
                    try:
                        _zhu.observe_fenshen_event("fenshen:analyzing", scene.name)
                    except Exception:
                        pass
                elif etype == "tool_done":
                    # 🆕 Delegate 完成：发射子任务结果
                    if event["tool"] == "delegate_task":
                        result_raw = event.get("result", "")
                        if isinstance(result_raw, str):
                            try:
                                children = json.loads(result_raw)
                            except json.JSONDecodeError:
                                children = []
                        else:
                            children = []
                        yield sse_event("child:done", children=children)
                        # 🆕 持久化到 DB
                        try:
                            from router.delegate_results import save_delegate_results
                            save_delegate_results(
                                scene_id=scene_id, children=children, db=db,
                                session_id=data.session_id,
                                parent_message_id=getattr(user_msg, 'id', None),
                            )
                        except Exception as e:
                            pass  # 持久化失败不影响主流程
                    yield sse_event("tool_status", tool=event["tool"], status="done",
                                    success=True, message="已完成")
                    agent_tool_results.append({
                        "tool": event["tool"], "params": {},
                        "result": event.get("result"), "success": True,
                    })
                elif etype == "tool_error":
                    # 🆕 高危命令阻断 → 发射 approval 事件
                    high_risk = event.get("high_risk")
                    if high_risk:
                        yield sse_event("command_approval",
                            command=event.get("blocked_command", ""),
                            reason=high_risk.get("reason", ""),
                            category=high_risk.get("category", ""),
                            description=high_risk.get("description", ""),
                        )
                    yield sse_event("tool_status", tool=event["tool"], status="error",
                                    success=False, message=event.get("error", "执行失败"))
                    agent_tool_results.append({
                        "tool": event["tool"], "params": {},
                        "result": event.get("error", "执行失败"), "success": False,
                    })
                elif etype == "thinking":
                    text = event["text"]
                    full_reply += text
                    yield sse_event("token", token=text)
                elif etype == "done":
                    full_reply = event.get("summary", full_reply)
                    break
                elif etype == "error":
                    _log.error(f"[scene agent loop] {event['message']}")
                    yield sse_event("error", message=event["message"])
                    return
                # 🆕 Schema v0.7: 仪表盘事件透传
                elif etype == "dashboard:reflect":
                    yield sse_event("dashboard:reflect",
                                    tool=event.get("tool", ""),
                                    tool_success=event.get("tool_success", False),
                                    result_preview=event.get("result_preview", ""))
        except GeneratorExit:
            # 用户断开连接：保存已收到的回复再退出（不能 yield）
            _log.info(f"[scene] 客户端断开，保存部分回复: scene={scene_id}")
            _persist_scene_reply(scene_id, full_reply, data.session_id, model_name)
            return
        except Exception as e:
            _log.error(f"[scene agent loop] 迭代异常: {e}")
            yield sse_event("error", message=f"AI 响应生成异常: {e}")
            return

        # ── 工具卡片（从 Agent Loop 结果重建） ──
        tool_cards = _build_tool_cards(agent_tool_results) if agent_tool_results else []
        if tool_cards:
            yield sse_event("tool_cards", cards=tool_cards)
        tool_results = agent_tool_results or None

        # 4.5 从 full_reply 解析优先级标记
        from agent_core.priority_assigner import extract_priority
        clean_reply, msg_priority = extract_priority(full_reply)
        full_reply = clean_reply

        # 5. 保存 AI 消息（独立 DB session）
        ai_msg_id = make_id("msg")
        new_db = SessionLocal()
        try:
            ai_msg = Message(
                id=ai_msg_id, scene_id=scene_id,
                role="ai", content=full_reply,
                session_id=data.session_id, model=model_name,
                priority=msg_priority,
            )
            new_db.add(ai_msg)
            new_db.commit()
            new_db.refresh(ai_msg)
            yield sse_event("done", id=ai_msg.id, role="ai", content=full_reply,
                            created_at=iso_utc(ai_msg.created_at),
                            changes=[], model=model_name)

            # 🆕 检测 AI 回复中的 HTML 代码块 → 自动保存为产出成果
            try:
                html_match = re.search(
                    r'```html\s*\n(.+?)(```|$)',
                    full_reply, re.DOTALL
                )
                if html_match:
                    html_content = html_match.group(1).strip()
                    if len(html_content) > 50:  # 至少 50 字符才算有效 HTML
                        safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', '', scene.name or '产出')[:20]
                        out_dir = Path(__file__).resolve().parent.parent.parent / "outputs" / scene_id
                        out_dir.mkdir(parents=True, exist_ok=True)
                        out_path = out_dir / f"{ai_msg_id}.html"
                        out_path.write_text(html_content, encoding="utf-8")

                        out_rec = ProjectOutput(
                            id=make_id("out"),
                            scene_id=scene_id,
                            title=f"{safe_name} - HTML 页面",
                            description="从对话中自动提取的 HTML 页面",
                            type="html",
                            file_path=f"{scene_id}/{ai_msg_id}.html",
                        )
                        new_db.add(out_rec)
                        new_db.commit()

                        yield sse_event("output:created",
                            output_id=out_rec.id,
                            title=out_rec.title,
                            file_path=out_rec.file_path,
                        )
                        print(f"[output] 自动产出 HTML: {out_rec.file_path}")
            except Exception as e:
                print(f"[output] 自动提取 HTML 失败: {e}")

            # 🆕 检测 run_code 通过 code_b64 写入的 HTML 文件 → 注册为产出成果
            try:
                out_dir = Path(__file__).resolve().parent.parent.parent / "outputs" / scene_id
                out_dir.mkdir(parents=True, exist_ok=True)
                # 方式A：扫目录已有 .html 文件
                if out_dir.exists():
                    for html_file in sorted(out_dir.glob("*.html")):
                        fname = html_file.name
                        fpath = f"{scene_id}/{fname}"
                        existing = new_db.query(ProjectOutput).filter(
                            ProjectOutput.file_path == fpath
                        ).first()
                        if existing:
                            continue
                        fsize = html_file.stat().st_size
                        if fsize < 50:
                            continue
                        out_rec = ProjectOutput(
                            id=make_id("out"), scene_id=scene_id,
                            title=f"{scene.name or '产出'} - HTML",
                            description=f"run_code 生成的 HTML 页面 ({fsize} 字节)",
                            type="html", file_path=fpath,
                        )
                        new_db.add(out_rec); new_db.commit()
                        yield sse_event("output:created", output_id=out_rec.id,
                            title=out_rec.title, file_path=out_rec.file_path)
                        print(f"[output] 目录扫描 HTML: {fpath}")
                # 方式B：从 run_code 的 stdout 中提取 HTML（LLM print(html) 场景）
                for idx, tr in enumerate(agent_tool_results or []):
                    if tr.get("tool") == "run_code" and tr.get("success"):
                        stdout = (tr.get("result") or {}).get("stdout", "") if isinstance(tr.get("result"), dict) else str(tr.get("result", ""))
                        # 方式B1：stdout 直接包含 HTML 内容
                        if "<!DOCTYPE html>" in stdout or "<html" in stdout[:200]:
                            html_start = stdout.find("<!DOCTYPE html>")
                            if html_start == -1:
                                html_start = stdout.find("<html")
                            if html_start >= 0:
                                html_content = stdout[html_start:].strip()
                                if len(html_content) > 50:
                                    safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', '', scene.name or '产出')[:20]
                                    out_path = out_dir / f"run-{idx}.html"
                                    if out_path.exists():
                                        out_path = out_dir / f"run-{idx}-{ai_msg_id[:8]}.html"
                                    out_path.write_text(html_content, encoding="utf-8")
                                    fpath = f"{scene_id}/{out_path.name}"
                                    existing = new_db.query(ProjectOutput).filter(
                                        ProjectOutput.file_path == fpath
                                    ).first()
                                    if not existing:
                                        out_rec = ProjectOutput(
                                            id=make_id("out"), scene_id=scene_id,
                                            title=f"{safe_name} - HTML",
                                            description="从 run_code 输出提取的 HTML",
                                            type="html", file_path=fpath,
                                        )
                                        new_db.add(out_rec); new_db.commit()
                                        yield sse_event("output:created",
                                            output_id=out_rec.id, title=out_rec.title,
                                            file_path=out_rec.file_path)
                                        print(f"[output] run_code stdout HTML: {fpath}")
                        # 方式B2：stdout 提到 .html 文件路径 → 复制到 outputs/ 目录
                        html_paths = re.findall(r'(/[^\s]+\.html)', stdout)
                        for html_path in html_paths:
                            html_path = html_path.rstrip('.,;:)')
                            if os.path.exists(html_path):
                                file_size = os.path.getsize(html_path)
                                if file_size >= 50:
                                    fname = os.path.basename(html_path)
                                    dest = out_dir / fname
                                    if not dest.exists():
                                        import shutil
                                        shutil.copy2(html_path, str(dest))
                                    fpath = f"{scene_id}/{dest.name}"
                                    existing = new_db.query(ProjectOutput).filter(
                                        ProjectOutput.file_path == fpath
                                    ).first()
                                    if not existing:
                                        safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', '', scene.name or '产出')[:20]
                                        out_rec = ProjectOutput(
                                            id=make_id("out"), scene_id=scene_id,
                                            title=f"{safe_name} - HTML",
                                            description=f"从 {html_path} 复制",
                                            type="html", file_path=fpath,
                                        )
                                        new_db.add(out_rec); new_db.commit()
                                        yield sse_event("output:created",
                                            output_id=out_rec.id, title=out_rec.title,
                                            file_path=out_rec.file_path)
                                        print(f"[output] run_code 复制 HTML: {fpath}")
            except Exception as e:
                print(f"[output] 扫描产出目录失败: {e}")

            # 🆕 方式C：扫描所有工具执行中可能被创建的 .html 文件（不依赖 stdout）
            try:
                out_dir = Path(__file__).resolve().parent.parent.parent / "outputs" / scene_id
                out_dir.mkdir(parents=True, exist_ok=True)
                project_root = Path(__file__).resolve().parent.parent.parent  # zuoshanke/
                scan_dirs = [project_root / "backend", project_root / "capability-demo", project_root]
                scanned_paths = set()
                scan_cutoff = time.time() - 120  # 只考虑120秒内修改过的文件
                for scan_dir in scan_dirs:
                    if not scan_dir.exists():
                        continue
                    for html_file in sorted(scan_dir.glob("**/*.html")):
                        fpath_str = str(html_file.resolve())
                        if fpath_str in scanned_paths:
                            continue
                        scanned_paths.add(fpath_str)
                        # 排除已知目录
                        exclude_dirs = {"outputs", "node_modules", ".git", "__pycache__",
                                        "frontend", "skills", "tools", "docs", "references",
                                        "scripts", "games", "prototypes", "data", "action-maps"}
                        if exclude_dirs & set(html_file.parts):
                            continue
                        # 只取最近120秒内修改过的文件（LLM 刚生成的）
                        fsize = html_file.stat().st_size
                        mtime = html_file.stat().st_mtime
                        if fsize < 100 or mtime < scan_cutoff:
                            continue
                        # 复制到 outputs/
                        fname = html_file.name
                        dest = out_dir / fname
                        if not dest.exists():
                            import shutil
                            shutil.copy2(str(html_file), str(dest))
                        fpath = f"{scene_id}/{dest.name}"
                        existing = new_db.query(ProjectOutput).filter(
                            ProjectOutput.file_path == fpath
                        ).first()
                        if not existing:
                            safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', '', scene.name or '产出')[:20]
                            out_rec = ProjectOutput(
                                id=make_id("out"), scene_id=scene_id,
                                title=f"{safe_name} - {fname}",
                                description=f"自动发现的 HTML 页面 ({fsize} 字节)",
                                type="html", file_path=fpath,
                            )
                            new_db.add(out_rec); new_db.commit()
                            yield sse_event("output:created",
                                output_id=out_rec.id, title=out_rec.title,
                                file_path=fpath)
                            print(f"[output] 扫描发现 HTML: {fpath}")
            except Exception as e:
                print(f"[output] 全盘扫描 HTML 失败: {e}")

            # 🆕 Schema v0.8: 本体观察 — 分身完成
            try:
                _zhu.observe_fenshen_event("fenshen:done", scene.name)
            except Exception:
                pass

            # ── 6. 自动提取记忆（双通道） ──
            try:
                # 收集本轮对话
                extract_msgs = [
                    {"role": m.role, "content": m.content}
                    for m in scene_history
                ]
                extract_msgs.append({"role": "user", "content": data.content})
                extract_msgs.append({"role": "ai", "content": full_reply})

                # 双通道提取：快速关键词 + LLM 智能提取
                mem_results = MemoryExtractor.extract(db, scene_id, extract_msgs)
                if mem_results:
                    print(f"[memory] extract: {json.dumps(mem_results, ensure_ascii=False)}")
            except Exception as e:
                print(f"[memory] extract error: {e}")

            # ── 7.5 自动发散（按轮数触发，非首次消息） ──
            try:
                from models import ThinkingMap, ThinkNode as _TN
                tmap = db.query(ThinkingMap).filter(
                    ThinkingMap.scene_id == scene_id
                ).first()
                if tmap:
                    existing = db.query(_TN).filter(
                        _TN.map_id == tmap.id
                    ).all()
                    # 统计 AI 回复轮数
                    ai_rounds = db.query(Message).filter(
                        Message.scene_id == scene_id,
                        Message.role == "ai",
                    ).count()
                    has_non_root = any(n.type != "root" for n in existing)
                    min_rounds = scene.diverge_min_rounds or 2

                    if not has_non_root and ai_rounds >= min_rounds:
                        print(f"[diverge] auto-diverge for scene {scene_id} (round {ai_rounds})")
                        # 用全量上下文代替单条消息
                        d_ctx = _build_diverge_context(db, scene_id)
                        if not d_ctx:
                            d_ctx = data.content[:500]
                        d_messages = [
                            {"role": "system", "content": (
                                "你是坐山客 AI 工作台的任务拆解专家。"
                                "将用户的目标拆解为思维导图节点树，支持多层嵌套。"
                                "输出 JSON 树形结构："
                                '{"tree": [{"label": "根分类", "children": [{"label": "子分类", "children": [{"label": "最细项"}]}]}]}'
                                "没有 children 的节点是叶子节点(leaf)，有 children 的节点是分类节点(domain)。"
                            )},
                            {"role": "user", "content": f"基于以下对话上下文，拆解任务维度：\n\n{d_ctx}"},
                        ]
                        d_raw = call_deepseek_chat(d_messages, model="flash",
                                                   temperature=0.5, max_tokens=3072,
                                                   route="medium")
                        if d_raw:
                            import json as _json
                            text = d_raw.strip()
                            if "```json" in text:
                                text = text.split("```json")[1].split("```")[0].strip()
                            elif "```" in text:
                                text = text.split("```")[1].split("```")[0].strip()
                            parsed = _json.loads(text) if text.startswith("{") else None
                            if not parsed:
                                start = text.find("{")
                                end = text.rfind("}")
                                if start >= 0 and end > start:
                                    parsed = _json.loads(text[start:end+1])
                            if parsed:
                                # Schema v0.81: 支持递归 tree 和旧版 categories 格式
                                tree = parsed.get("tree", []) or parsed.get("categories", []) or parsed.get("nodes", [])
                                name_to_id = {n.label: n.id for n in existing}
                                root = next((n for n in existing if n.type == "root"), None)
                                new_count = 0

                                def _build_tree_nodes(items, parent_id):
                                    nonlocal new_count
                                    for item in items:
                                        label = item.get("label", "").strip()
                                        if not label:
                                            continue
                                        children = item.get("children", []) or item.get("nodes", [])
                                        ntype = "domain" if children else "leaf"
                                        # 去重
                                        dup = any(
                                            x.parent_id == parent_id and x.label == label
                                            for x in existing
                                        )
                                        if dup:
                                            continue
                                        nid = make_id("n")
                                        db.add(ThinkNode(
                                            id=nid, map_id=tmap.id, parent_id=parent_id,
                                            type=ntype, label=label,
                                            status="discussing", created_by="brainstorm",
                                        ))
                                        new_count += 1
                                        # 递归处理子节点
                                        if children:
                                            _build_tree_nodes(children, nid)

                                if root:
                                    _build_tree_nodes(tree, root.id)
                                if new_count:
                                    tmap.version += 1
                                    tmap.updated_at = utcnow()
                                    db.commit()
                                    print(f"[diverge] auto-diverge created {new_count} nodes")
                                    yield sse_event("thinking_map:diverged",
                                                    node_count=new_count)

                                    # 🆕 发散后同步检查收敛阈值，达标则收敛+发队列事件
                                    try:
                                        from agent_core.converge_engine import (
                                            check_converge_threshold as _check_threshold,
                                            auto_converge_and_prioritize as _do_converge,
                                        )
                                        # 重新查节点（含刚创建的）
                                        _all_nodes = db.query(ThinkNode).filter(
                                            ThinkNode.map_id == tmap.id,
                                            ThinkNode.type != "root",
                                        ).all()
                                        _threshold = scene.converge_threshold or 2.0
                                        if _check_threshold(_all_nodes, _threshold):
                                            print(f"[converge] 同步触发收敛: scene={scene_id}, threshold={_threshold}")
                                            _result = _do_converge(db, scene_id, tmap)
                                            _pq = _result.get("pq_items", [])
                                            yield sse_event("dashboard:converge",
                                                merge_count=_result.get("merged", 0),
                                                queue_count=len(_pq))
                                            if _pq:
                                                yield sse_event("dashboard:queue_update",
                                                    items=_pq)
                                    except Exception as _ce:
                                        print(f"[converge] 同步收敛失败（回退异步）: {_ce}")
                                        # 回退到异步收敛
                                        start_async_converge_check(scene_id)
            except Exception as e:
                print(f"[diverge] auto-diverge error: {e}")

            # ── 8. 缺工具提案（仅当使用了 web_search 兜底时） ──
            try:
                _was_web_search = any(
                    r.get("tool") == "web_search" for r in (tool_results or [])
                )
                if _was_web_search:
                    from ai_engine import propose_tool
                    proposal = propose_tool(data.content, full_reply, tool_was_used=True)
                    if proposal.get("need_tool"):
                        tool_msg = Message(
                            id=make_id("msg"),
                            scene_id=scene_id,
                            role="system",
                            content=(
                                f"🔧 **系统检测到你可能需要一个工具**\n\n"
                                f"你问「{data.content}」时，系统发现缺少一个名为 "
                                f"**{proposal['tool_name']}** 的通用能力。\n\n"
                                f"> {proposal['reason']}\n\n"
                                f"我已生成了一个工具创建方案，前往 **工坊 → 工具提案** 查看并决定是否创建。"
                            ),
                            session_id=data.session_id,
                        )
                        new_db.add(tool_msg)
                        new_db.commit()
                        yield sse_event("tool_proposal", **proposal)
            except Exception as e:
                print(f"[tool_proposal] 生成失败: {e}")

            # 🆕 Schema v1.1: 累加 token 用量
            from models import WebSession as _WS
            _ws = db.query(_WS).filter(
                _WS.context_type == "scene",
                _WS.context_id == scene_id,
                _WS.status == "active",
            ).first()
            if _ws:
                _ws.prompt_tokens += total_tokens
                _ws.completion_tokens += estimate_messages_tokens([{"role": "assistant", "content": full_reply}])
                _ws.total_tokens = _ws.prompt_tokens + _ws.completion_tokens
                _ws.api_calls += 1
                _ws.last_active_at = utcnow()
                _ws.updated_at = utcnow()
                db.commit()

        except Exception as e:
            print(f"[scene stream save error] {e}")
            yield sse_event("error", message="AI 回复保存失败")
        finally:
            new_db.close()
            # 🆕 Schema v0.81: SSE 流结束后异步检查收敛
            try:
                start_async_converge_check(scene_id)
            except Exception:
                pass

    return sse_response(generate())


