"""Action Map CRUD + 生成 + 执行 + 日志"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import (
    ThinkingMap, ThinkNode, ActionMap, ActionNode, ActionEdge,
    ActionExecutionLog, Scene, Message,
)
from schemas import (
    ActionMapCreate, ActionMapOut, ActionNodeOut,
    ActionMapStatusUpdate, ActionNodeStatusUpdate,
    ActionMapGenerateRequest,
)
from ai_engine import (
    call_hermes_action_map, call_hermes_execute_node,
    scan_and_document_tools, call_qwen_chat,
)
from utils import make_id, utcnow
from router.shared import sse_event, sse_response

router = APIRouter(tags=["Action Map"])


# ═══ Action Map CRUD ═══

@router.post("/api/action-maps", response_model=ActionMapOut)
def create_action_map(data: ActionMapCreate, db: Session = Depends(get_db)):
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == data.think_map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")
    node = db.query(ThinkNode).filter(ThinkNode.id == data.think_node_id).first()
    if not node:
        raise HTTPException(404, "ThinkNode 不存在")
    if not node.actionable:
        raise HTTPException(400, "此节点未标记为可执行")

    amap = ActionMap(
        id=make_id("action"), think_map_id=data.think_map_id,
        think_node_id=data.think_node_id, title=data.title, status="draft",
    )
    db.add(amap)
    db.flush()

    for n in data.nodes:
        an = ActionNode(
            id=n.id, map_id=amap.id, type=n.type, label=n.label,
            requires_approval=n.requires_approval, timeout=n.timeout,
            retry=n.retry, verification=n.verification.model_dump() if n.verification else None,
            fallback_node=n.fallback_node, order_index=n.order_index,
            position_x=n.position_x, position_y=n.position_y,
        )
        db.add(an)

    for e in data.edges:
        ae = ActionEdge(
            id=e.id, map_id=amap.id, from_node_id=e.from_node_id,
            to_node_id=e.to_node_id, type=e.type, label=e.label, condition=e.condition,
        )
        db.add(ae)

    node.linked_action_map = amap.id
    node.action_status = "draft"
    db.commit()
    db.refresh(amap)
    _load_relations(amap)
    return amap


@router.post("/api/action-maps/generate")
def generate_action_map_stream(data: ActionMapGenerateRequest):
    """调用 Hermes 子进程生成 Action Map（SSE 流式）"""

    def event_stream():
        db = SessionLocal()
        try:
            node = db.query(ThinkNode).filter(ThinkNode.id == data.think_node_id).first()
            if not node:
                yield sse_event("error", message="ThinkNode 不存在")
                return
            if not node.actionable:
                yield sse_event("error", message="此节点未标记为可执行")
                return

            tmap = db.query(ThinkingMap).filter(ThinkingMap.id == node.map_id).first()
            if not tmap:
                yield sse_event("error", message="Thinking Map 不存在")
                return

            # 流式调用 Hermes
            action_map_json = None
            for event in call_hermes_action_map(data.think_node_id, db):
                et = event["type"]
                if et == "hermes_log":
                    yield sse_event("hermes_log", line=event["line"])
                elif et == "status":
                    yield sse_event("status", line=event["line"])
                elif et == "result":
                    action_map_json = event.get("action_map")
                elif et == "error":
                    yield sse_event("error", message=event["message"])
                    return

            if not action_map_json or not action_map_json.get("nodes"):
                yield sse_event("error", message="生成的节点为空")
                return

            # 标题去重
            base_title = action_map_json.get("title", f"{node.label} · 行动计划")
            existing_count = db.query(ActionMap).filter(
                ActionMap.think_node_id == node.id
            ).count()
            title = f"{base_title}_{existing_count + 1}" if existing_count > 0 else base_title

            # ID 重映射
            gen_nodes = action_map_json.get("nodes", [])
            gen_edges = action_map_json.get("edges", [])
            id_map = {n.get("id", ""): make_id("an") for n in gen_nodes}

            # 创建 Action Map
            amap = ActionMap(
                id=make_id("action"), think_map_id=tmap.id,
                think_node_id=node.id, title=title, status="draft",
            )
            db.add(amap)
            db.flush()

            for n in gen_nodes:
                db.add(ActionNode(
                    id=id_map.get(n.get("id", ""), ""), map_id=amap.id,
                    type=n.get("type", "exec"), label=n.get("label", ""),
                    requires_approval=n.get("requires_approval", False),
                    timeout=n.get("timeout", 300), retry=n.get("retry", 0),
                    verification=n.get("verification"),
                    fallback_node=id_map.get(n.get("fallback_node")) if n.get("fallback_node") else None,
                    order_index=n.get("order_index", 0),
                    position_x=n.get("position_x"), position_y=n.get("position_y"),
                ))

            for e in gen_edges:
                db.add(ActionEdge(
                    id=make_id("ae"), map_id=amap.id,
                    from_node_id=id_map.get(e.get("from_node_id", ""), ""),
                    to_node_id=id_map.get(e.get("to_node_id", ""), ""),
                    type=e.get("type", "flow"), label=e.get("label"),
                    condition=e.get("condition"),
                ))

            node.linked_action_map = amap.id
            node.action_status = "draft"
            db.commit()
            db.refresh(amap)
            _load_relations(amap)

            # 用 Pydantic schema 序列化，避免手写字典
            result = ActionMapOut.model_validate(amap).model_dump()
            yield sse_event("result", action_map=result)
            yield sse_event("done")

        except Exception as e:
            yield sse_event("error", message=f"服务器异常: {e}")
        finally:
            db.close()

    return sse_response(event_stream())


@router.get("/api/action-maps", response_model=List[ActionMapOut])
def list_action_maps(
    think_map_id: Optional[str] = None,
    think_node_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(ActionMap)
    if think_map_id:
        q = q.filter(ActionMap.think_map_id == think_map_id)
    if think_node_id:
        q = q.filter(ActionMap.think_node_id == think_node_id)
    results = q.order_by(ActionMap.updated_at.desc()).all()
    for am in results:
        _load_relations(am)
    return results


@router.get("/api/action-maps/{action_map_id}", response_model=ActionMapOut)
def get_action_map(action_map_id: str, db: Session = Depends(get_db)):
    amap = db.query(ActionMap).filter(ActionMap.id == action_map_id).first()
    if not amap:
        raise HTTPException(404, "Action Map 不存在")
    _load_relations(amap)
    return amap


@router.patch("/api/action-maps/{action_map_id}/status")
def update_action_map_status(
    action_map_id: str, data: ActionMapStatusUpdate, db: Session = Depends(get_db),
):
    amap = db.query(ActionMap).filter(ActionMap.id == action_map_id).first()
    if not amap:
        raise HTTPException(404, "Action Map 不存在")
    amap.status = data.status
    amap.updated_at = utcnow()

    node = db.query(ThinkNode).filter(ThinkNode.id == amap.think_node_id).first()
    if node:
        node.action_status = data.status
    db.commit()
    return {"ok": True, "status": data.status}


@router.patch("/api/action-maps/{action_map_id}/nodes/{node_id}")
def update_action_node(
    action_map_id: str, node_id: str, data: ActionNodeStatusUpdate, db: Session = Depends(get_db),
):
    node = db.query(ActionNode).filter(
        ActionNode.id == node_id, ActionNode.map_id == action_map_id,
    ).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    node.status = data.status
    if data.status == "running":
        node.started_at = utcnow()
    elif data.status in ("completed", "failed", "timeout"):
        node.completed_at = utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/api/action-maps/{action_map_id}")
def delete_action_map(action_map_id: str, db: Session = Depends(get_db)):
    amap = db.query(ActionMap).filter(ActionMap.id == action_map_id).first()
    if not amap:
        raise HTTPException(404, "Action Map 不存在")
    node = db.query(ThinkNode).filter(ThinkNode.id == amap.think_node_id).first()
    if node and node.linked_action_map == amap.id:
        node.linked_action_map = None
        node.action_status = None
    db.delete(amap)
    db.commit()
    return {"ok": True}


# ═══ Action Map 执行 ═══

@router.post("/api/action-maps/{action_map_id}/execute")
def execute_action_map(action_map_id: str):
    """执行 Action Map 全部节点（SSE 流式）"""

    def event_stream():
        db = SessionLocal()
        try:
            amap = db.query(ActionMap).filter(ActionMap.id == action_map_id).first()
            if not amap:
                yield sse_event("error", message="Action Map 不存在")
                return

            nodes = db.query(ActionNode).filter(
                ActionNode.map_id == action_map_id
            ).order_by(ActionNode.order_index).all()
            if not nodes:
                yield sse_event("error", message="Action Map 无节点")
                return

            amap.status = "running"
            db.commit()
            yield sse_event("map_status", status="running")

            failed = False
            node_results = []

            for node in nodes:
                if failed:
                    break

                # 跳过已完成的节点
                if node.status == "completed":
                    node_results.append(
                        {"label": node.label, "result": node.result_summary or "", "status": "completed"}
                    )
                    continue

                if node.type in ("start", "milestone", "end", "decision"):
                    node.status = "completed"
                    node.completed_at = utcnow()
                    db.commit()
                    _log(db, action_map_id, node.id, node.label, "node_done", status="completed")
                    yield sse_event("node_done", node_id=node.id, status="completed", label=node.label)
                    continue

                if node.type == "exec":
                    max_attempts = (node.retry or 0) + 1
                    result_text = ""
                    exec_ok = False

                    for attempt in range(1, max_attempts + 1):
                        if attempt > 1:
                            node.retry_count = attempt - 1
                            node.status = "running"
                            node.started_at = utcnow()
                            db.commit()
                            _log(db, action_map_id, node.id, node.label, "node_retry",
                                 line=f"重试第 {attempt - 1} 次（共 {max_attempts - 1} 次）")
                            yield sse_event("node_retry", node_id=node.id, label=node.label, retry=attempt - 1)
                        else:
                            node.status = "running"
                            node.started_at = utcnow()
                            db.commit()
                            _log(db, action_map_id, node.id, node.label, "node_start")
                            yield sse_event("node_start", node_id=node.id, label=node.label)

                        result_text = ""
                        exec_ok = False

                        for event in call_hermes_execute_node(
                            node_id=node.id, node_label=node.label,
                            node_type=node.type, verification=node.verification,
                            timeout=node.timeout or 300,
                        ):
                            et = event["type"]
                            if et in ("hermes_log", "status"):
                                _log(db, action_map_id, node.id, node.label, "hermes_log", line=event["line"])
                                yield sse_event("hermes_log", node_id=node.id, line=event["line"])
                            elif et == "result":
                                result_text = event["text"]
                                exec_ok = True
                            elif et == "error":
                                result_text = event["message"]
                                exec_ok = False
                                break

                        if exec_ok:
                            node.status = "completed"
                            node.result_summary = result_text
                            node.completed_at = utcnow()
                            db.commit()
                            node_results.append(
                                {"label": node.label, "result": result_text, "status": "completed"}
                            )
                            _log(db, action_map_id, node.id, node.label, "node_done",
                                 status="completed", result=result_text[:500])
                            yield sse_event("node_done", node_id=node.id, status="completed",
                                            label=node.label, result=result_text[:200])
                            break
                    else:
                        node.status = "failed"
                        node.retry_count = max_attempts - 1
                        node.result_summary = result_text or f"重试 {max_attempts - 1} 次后仍失败"
                        node.completed_at = utcnow()
                        db.commit()
                        failed = True
                        node_results.append(
                            {"label": node.label, "result": node.result_summary, "status": "failed"}
                        )
                        _log(db, action_map_id, node.id, node.label, "node_done",
                             status="failed", result=(result_text or "")[:500])
                        yield sse_event("node_done", node_id=node.id, status="failed",
                                        label=node.label, result=(result_text or "")[:200])

            # 更新 map 最终状态
            amap.status = "completed" if not failed else "failed"
            db.commit()
            _log(db, action_map_id, None, None, "map_done", status=amap.status)
            yield sse_event("map_done", status=amap.status)

            # 工具自文档化钩子
            new_tools = []
            if amap.status == "completed":
                try:
                    new_tools = scan_and_document_tools(action_map_id)
                    if new_tools:
                        tools_data = [{"name": t["name"], "description": t.get("description", "")} for t in new_tools]
                        _log(db, action_map_id, None, None, "tools_documented",
                             line=f"新增 {len(new_tools)} 个工具: {', '.join(t['name'] for t in new_tools)}")
                        yield sse_event("tools_documented", count=len(new_tools), tools=tools_data)
                except Exception as e:
                    print(f"[ToolDocs hook] {e}")

            # 创建聊天消息
            try:
                tmap = db.query(ThinkingMap).filter(ThinkingMap.id == amap.think_map_id).first()
                if tmap:
                    scene = db.query(Scene).filter(Scene.id == tmap.scene_id).first()
                    if scene:
                        content = _build_execution_report(amap, node_results, scene.constraints, scene.constraints_locked, new_tools)
                        msg = Message(
                            id=make_id("msg"), scene_id=scene.id, channel_id=None,
                            role="ai", content=content, map_ref=action_map_id,
                        )
                        db.add(msg)
                        db.commit()
            except Exception as e:
                print(f"[ChatMsg] 创建聊天消息失败: {e}")

        except Exception as e:
            yield sse_event("error", message=f"执行异常: {e}")
        finally:
            db.close()

    return sse_response(event_stream())


# ═══ 执行日志查询 ═══

@router.get("/api/action-maps/{action_map_id}/logs")
def get_action_map_logs(action_map_id: str, db: Session = Depends(get_db)):
    logs = db.query(ActionExecutionLog).filter(
        ActionExecutionLog.map_id == action_map_id,
    ).order_by(ActionExecutionLog.created_at).all()
    return [
        {
            "id": log.id, "node_id": log.node_id, "node_label": log.node_label,
            "event_type": log.event_type, "line": log.line, "status": log.status,
            "result": log.result,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


# ═══ 辅助函数 ═══

def _load_relations(amap: ActionMap):
    """预加载 nodes / edges 关系"""
    amap.nodes
    amap.edges


def _log(db, map_id, nid, nlabel, etype, line=None, status=None, result=None):
    """写入执行日志并立即持久化"""
    db.add(ActionExecutionLog(
        id=make_id("aelog"), map_id=map_id, node_id=nid,
        node_label=nlabel, event_type=etype,
        line=line, status=status, result=result,
    ))
    db.commit()


def _build_execution_report(amap: ActionMap, node_results: list,
                             constraints, constraints_locked: bool,
                             new_tools: list) -> str:
    """构建 Action Map 执行完成后的聊天消息内容（含统计 + Qwen 报告 + 约束校验）"""
    completed_count = sum(1 for r in node_results if r["status"] == "completed")
    failed_count = sum(1 for r in node_results if r["status"] == "failed")
    total_count = len(node_results)

    lines = [f"⚡ **Action Map 执行完成** — {amap.title}\n"]
    lines.append("| Action | ✅ 成功 | ❌ 失败 | 📊 总计 |")
    lines.append("|--------|--------|--------|--------|")
    lines.append(f"| {amap.title} | {completed_count} | {failed_count} | {total_count} |")
    lines.append("")

    # Qwen 整理报告
    qwen_report = _generate_qwen_report(amap, node_results) if node_results else ""
    if qwen_report:
        lines.append("### 📊 执行报告\n")
        lines.append(qwen_report)
        lines.append("")

    # 约束校验
    if constraints and constraints_locked and node_results:
        verify_result = _verify_constraints(constraints, node_results)
        if verify_result:
            lines.append("### ✅ 约束校验\n")
            lines.append(verify_result)
            lines.append("")

    # 新工具通知
    if new_tools:
        tool_names = " · ".join(f"`{t['name']}`" for t in new_tools)
        lines.append(f"\n🔧 新增 {len(new_tools)} 个工具: {tool_names}")

    return "\n".join(lines)


def _generate_qwen_report(amap: ActionMap, node_results: list) -> str:
    """调用 Qwen 整理执行报告"""
    think_node = None
    try:
        db = SessionLocal()
        think_node = db.query(ThinkNode).filter(ThinkNode.id == amap.think_node_id).first()
    except Exception as e:
        print(f"[Qwen report] DB 查询失败: {e}")
    finally:
        if 'db' in locals():
            db.close()

    purpose = think_node.label if think_node else amap.title
    completed_count = sum(1 for r in node_results if r["status"] == "completed")
    failed_count = sum(1 for r in node_results if r["status"] == "failed")
    total_count = len(node_results)

    all_results = "\n\n".join(
        f"## {r['label']}（{r['status']}）\n{r['result'] or '(无输出)'}"
        for r in node_results
    )

    qwen_messages = [
        {"role": "system", "content": "你是一个专业的执行结果整理助手。请把执行结果整理成简洁的报告。"},
        {"role": "user", "content": f"""请将以下 Action Map 执行结果整理成一份报告。

## Action 目的
{purpose}

## 执行统计
- 总节点: {total_count}
- 成功: {completed_count}
- 失败: {failed_count}

## 各节点执行结果
{all_results}

请用 Markdown 格式整理，包含：
1. **总体概述**（1-2 句，说明完成了什么）
2. **关键产出**（每个成功节点的核心成果，提炼要点）
3. **问题与建议**（如有失败节点，简要说明并给出建议）

保持简洁，300-500 字。直接输出内容，不要用代码块包裹。"""},
    ]

    try:
        return call_qwen_chat(qwen_messages, temperature=0.3) or ""
    except Exception as e:
        print(f"[Qwen report] 整理失败: {e}")
        return ""


def _verify_constraints(constraints, node_results: list) -> str:
    """调用 Qwen 逐条校验约束是否满足"""
    import json
    c_json = json.dumps(constraints, ensure_ascii=False, indent=2)
    all_results_text = "\n\n".join(
        f"## {r['label']}（{r['status']}）\n{r['result'] or '(无输出)'}"
        for r in node_results
    ) if node_results else "(无执行结果)"

    verify_msg = [
        {"role": "system", "content": "你是一个约束校验引擎。检查执行结果是否满足原始约束条件，逐条输出校验结果。"},
        {"role": "user", "content": f"""## 原始约束
{c_json}

## 执行结果摘要
{all_results_text[:3000]}

请逐条检查每条约束是否被满足，输出格式（Markdown）：
✅ 约束名称：结论（证据）
❌ 约束名称：问题说明"""},
    ]
    try:
        vr = call_qwen_chat(verify_msg, temperature=0.3)
        return vr.strip() if vr and vr.strip() else ""
    except Exception as e:
        print(f"[Constraint verify] 失败: {e}")
        return ""
