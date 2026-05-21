"""收敛+排序引擎 — Agent Loop 仪表盘核心管线

职责：
  1. 读 Thinking Map 节点 → LLM 分析哪些合并/废弃/排序
  2. 执行收敛合并 + 标记废弃
  3. 写入 PriorityQueue（P1-P4 + 依赖链）
  4. 写入 ReflectTimeline（记录收敛动作）
  5. 返回新 PQ 列表

使用场景：
  - 首次发散完成后（自动触发）
  - 反馈注入新节点后（自动触发）
  - 用户纠正后（聊天框触发）
"""

import json
from typing import Optional
from sqlalchemy.orm import Session

from models import ThinkNode, ThinkingMap, PriorityQueue, ReflectTimeline
from utils import make_id, utcnow


# ═══ LLM prompt 模板 ═══

CONVERGE_SYSTEM_PROMPT = '''你是一个任务调度专家。分析用户的思维导图节点，决定如何优化它们。

输出严格 JSON 格式（不要 markdown 代码块）：
{
  "merges": [
    {
      "source_ids": ["id1", "id2"],
      "target_title": "合并后标题",
      "target_desc": "合并说明（可选）"
    }
  ],
  "discarded_ids": ["id3"],
  "queue": [
    {
      "target_id": "id4",
      "title": "任务名",
      "priority": 1,
      "deps": ["id0"]
    }
  ],
  "project": {
    "is_project": false,
    "name": "",
    "description": "",
    "structure": []
  }
}

规则：
1. merges: 合并意思高度重复或紧密关联的任务。source_ids 是原始节点 ID 列表。
   - 合并后目标节点保持其原始 ID
   - target_title 必须比父节点更具体，不能与父节点同名
2. discarded_ids: 标记可以由 Agent 自主完成（无需单独任务步骤）或确实不需要的节点
3. queue: 为每个（合并后/未合并的）任务分配 P1-P4 优先级和依赖链。
   - target_id 使用节点 ID
   - P1=最高优先级，P4=最低优先级
   - deps 为依赖的任务 ID 列表
   - 不要为已废弃的节点分配队列项
4. project: 判断当前所有节点是否构成一个「项目」（一组相关的可交付产出）。
   - is_project=true 的条件：这些节点拆分后能形成多个独立的交付物（如多页面、多文档）
   - 如果 is_project=true，给出项目名称、描述和子模块结构
'''


def check_converge_threshold(nodes: list, threshold: float = 2.0) -> bool:
    """检查是否满足收敛阈值条件

    Args:
        nodes: ThinkNode 列表（不含 root）
        threshold: 收敛阈值，默认 2.0

    Returns:
        bool: 叶子数 >= 分支数 × 阈值 时返回 True
    """
    if not nodes or len(nodes) <= 1:
        return False

    node_ids = set(n.id for n in nodes)
    children_map = {}
    for n in nodes:
        if n.parent_id and n.parent_id in node_ids:
            children_map.setdefault(n.parent_id, []).append(n.id)

    leaves = [n for n in nodes if n.id not in children_map]
    branches = [n for n in nodes if n.id in children_map]

    return len(leaves) >= len(branches) * threshold


def auto_converge_and_prioritize(db: Session, scene_id: str, tm: ThinkingMap,
                                 summary: str = "", target_layers: list = None) -> dict:
    """自动收敛+排序 Thinking Map 节点

    Args:
        db: DB session
        scene_id: 场景 ID
        tm: ThinkingMap 对象
        summary: 可选，LLM 对当前讨论的摘要说明
        target_layers: 可选，指定收敛的目标层级（不指定则全局收敛）

    Returns:
        dict: {"pq_items": [...], "project": {...} or None, "merged": int, "discarded": int}
    """
    # ── 1. 读当前节点（排除已废弃的） ──
    all_nodes = db.query(ThinkNode).filter(
        ThinkNode.map_id == tm.id,
        ThinkNode.type != "root",
    ).all()

    if not all_nodes or len(all_nodes) <= 1:
        return {"pq_items": [], "project": None, "merged": 0, "discarded": 0}

    # ── 2. 构建 LLM 输入 ──
    parent_labels = {n.id: n.label for n in all_nodes}
    active_nodes = [n for n in all_nodes if n.status not in ("discarded", "confirmed")]
    if not active_nodes:
        return {"pq_items": [], "project": None, "merged": 0, "discarded": 0}

    # 如果指定了 target_layers，只传目标层的节点
    if target_layers:
        # 计算每层 depth
        node_map = {n.id: n for n in all_nodes}
        def get_layer(n):
            depth = 0
            p = n.parent_id
            while p and p in node_map and node_map[p].type != "root":
                depth += 1
                p = node_map[p].parent_id
            return depth
        layer_nodes = [n for n in active_nodes if get_layer(n) == target_layers[0]]
        if layer_nodes:
            active_nodes = layer_nodes

    node_summary = [
        {"id": n.id, "label": n.label, "type": n.type, "status": n.status,
         "parent_label": parent_labels.get(n.parent_id, ""),
         "parent_id": n.parent_id or "",
         "children": [c.id for c in n.children] if n.children else []}
        for n in active_nodes
    ]

    # ── 3. 调 LLM 分析 ──
    from ai_engine import call_deepseek_chat

    user_parts = [f"请分析以下任务节点：\n{json.dumps(node_summary, ensure_ascii=False, indent=2)}"]
    if summary:
        user_parts.append(f"对话背景（优先级决策参考）：\n{summary}\n")
    user_msg = "\n\n".join(user_parts)

    messages = [
        {"role": "system", "content": CONVERGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    raw = call_deepseek_chat(
        messages,
        model="flash",
        temperature=0.1,
        max_tokens=4096,
        route="medium",
    )

    if not raw:
        print(f"[converge] LLM 返回空，跳过收敛")
        return {"pq_items": [], "project": None, "merged": 0, "discarded": 0}

    # ── 4. 解析 JSON ──
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(text) if text.startswith("{") else None
        if not parsed:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end+1])

        if not parsed:
            print(f"[converge] 无法解析 LLM JSON 输出: {raw[:200]}")
            return {"pq_items": [], "project": None, "merged": 0, "discarded": 0}

    except json.JSONDecodeError as e:
        print(f"[converge] JSON 解析失败: {e}\n{raw[:300]}")
        return {"pq_items": [], "project": None, "merged": 0, "discarded": 0}

    # ── 5. 执行合并 ──
    merge_records = parsed.get("merges", [])
    node_id_to_label = {n.id: n.label for n in all_nodes}

    for merge in merge_records:
        source_ids = merge.get("source_ids", [])
        target_title = merge.get("target_title", "")

        if len(source_ids) < 2 or not target_title:
            continue

        # 🛡️ 后处理校验：合并后标题不能与父节点同名
        target_id = source_ids[0]
        target_node = db.query(ThinkNode).filter(ThinkNode.id == target_id).first()
        if not target_node:
            continue
        parent_label = parent_labels.get(target_node.parent_id, "")
        if parent_label and target_title.strip() == parent_label.strip():
            print(f"[converge] ⚠️ 跳过合并: 标题「{target_title}」与父节点同名")
            continue

        # 记录被合并的节点名
        merged_names = [node_id_to_label.get(sid, sid) for sid in source_ids]

        # 更新目标节点
        target_node.label = target_title
        target_node.status = "confirmed"
        target_node.converged_from = list(set((target_node.converged_from or []) + merged_names))

        # 废弃其他源节点
        for sid in source_ids[1:]:
            source_node = db.query(ThinkNode).filter(ThinkNode.id == sid).first()
            if source_node:
                source_node.status = "discarded"

        print(f"[converge] 合并: {' + '.join(merged_names)} → {target_title}")

    # ── 6. 标记废弃 ──
    discarded_ids = parsed.get("discarded_ids", [])
    for did in discarded_ids:
        node = db.query(ThinkNode).filter(ThinkNode.id == did).first()
        if node and node.status != "discarded":
            node.status = "discarded"
            print(f"[converge] 废弃: {node.label}")

    db.commit()

    # ── 7. 写入 PriorityQueue ──
    # 先清空该场景的旧 PQ
    db.query(PriorityQueue).filter(PriorityQueue.scene_id == scene_id).delete()

    queue_entries = parsed.get("queue", [])
    pq_items = []

    for idx, entry in enumerate(queue_entries):
        target_id = entry.get("target_id", "")
        title = entry.get("title", "")
        priority = entry.get("priority", 2)
        deps = entry.get("deps", [])

        if not target_id or not title:
            continue

        # 校验节点存在
        node = db.query(ThinkNode).filter(ThinkNode.id == target_id).first()
        if not node:
            continue

        pq = PriorityQueue(
            id=make_id("pq"),
            scene_id=scene_id,
            node_id=target_id,
            title=title,
            priority=priority,
            status="pending",
            deps=json.dumps(deps, ensure_ascii=False),
            sort_order=idx,
        )
        db.add(pq)
        pq_items.append(pq)

    db.commit()

    # ── 7.5 同步更新入队节点的状态 ──
    for entry in queue_entries:
        target_id = entry.get("target_id", "")
        if target_id:
            node = db.query(ThinkNode).filter(ThinkNode.id == target_id).first()
            if node and node.status != "discarded":
                node.status = "confirmed"
    db.commit()

    # ── 8. 写入 ReflectTimeline（收敛记录） ──
    reflect_records = []

    for merge in merge_records:
        source_ids = merge.get("source_ids", [])
        target_title = merge.get("target_title", "")
        if len(source_ids) >= 2:
            merged_names = [node_id_to_label.get(sid, sid) for sid in source_ids]
            detail = f"「{'」+「'.join(merged_names)}」→「{target_title}」"
            r = ReflectTimeline(
                id=make_id("ref"),
                scene_id=scene_id,
                type="merge",
                icon="🔀",
                title=f"收敛合并: {target_title}",
                detail=detail,
                tag="inject",
                tag_text="↪ 已合并入队列",
            )
            db.add(r)
            reflect_records.append(r)

    if discarded_ids:
        discarded_names = [node_id_to_label.get(did, did) for did in discarded_ids if did in node_id_to_label]
        if discarded_names:
            r = ReflectTimeline(
                id=make_id("ref"),
                scene_id=scene_id,
                type="fail",
                icon="🔴",
                title=f"废弃 {len(discarded_names)} 个节点",
                detail=f"「{'」「'.join(discarded_names)}」标记为不需要单独步骤",
                tag="blocked",
            )
            db.add(r)
            reflect_records.append(r)

    # 队列摘要
    if pq_items:
        p1_count = sum(1 for e in queue_entries if e.get("priority") == 1)
        total = len(queue_entries)
        r = ReflectTimeline(
            id=make_id("ref"),
            scene_id=scene_id,
            type="new",
            icon="📊",
            title=f"优先级队列就绪",
            detail=f"{total} 个任务入队，P1={p1_count} 个",
            tag="queue_update",
        )
        db.add(r)
        reflect_records.append(r)

    db.commit()

    # ── 9. 检测项目认知 ──
    project_info = parsed.get("project", {})
    project_result = None
    if project_info and project_info.get("is_project"):
        from models import OutputProject
        proj_name = project_info.get("name", "未命名项目")[:200]
        proj_desc = project_info.get("description", "")[:500]
        # 查找该场景已有的活跃项目，有则更新，无则创建
        existing = db.query(OutputProject).filter(
            OutputProject.scene_id == scene_id,
            OutputProject.is_active == True,
        ).first()
        if existing:
            existing.name = proj_name
            existing.description = proj_desc
            db.commit()
            project_result = {"project_id": existing.id, "name": proj_name, "description": proj_desc}
            print(f"[converge] 更新项目: {proj_name} ({existing.id})")
        else:
            proj = OutputProject(
                id=make_id("proj"),
                scene_id=scene_id,
                name=proj_name,
                description=proj_desc,
            )
            db.add(proj)
            db.commit()
            project_result = {"project_id": proj.id, "name": proj_name, "description": proj_desc}
            print(f"[converge] 创建项目: {proj_name} ({proj.id})")
            # 记录项目创建
            rt = ReflectTimeline(
                id=make_id("ref"),
                scene_id=scene_id, type="new",
                icon="🏗️", title=f"项目: {proj_name}",
                detail=proj_desc[:100], tag="inject",
                tag_text="收敛自动创建",
            )
            db.add(rt)
            db.commit()

    # ── 10. 返回结果 ──
    print(f"[converge] 完成: {len(merge_records)} 组合并, {len(discarded_ids)} 废弃, {len(queue_entries)} 入队")
    return {
        "pq_items": [_pq_to_dict(p) for p in pq_items],
        "project": project_result,
        "merged": len(merge_records),
        "discarded": len(discarded_ids),
    }


def get_pq_list(db: Session, scene_id: str) -> list[dict]:
    """获取场景的优先级队列"""
    items = db.query(PriorityQueue).filter(
        PriorityQueue.scene_id == scene_id
    ).order_by(PriorityQueue.priority, PriorityQueue.sort_order).all()
    return [_pq_to_dict(p) for p in items]


def get_reflect_list(db: Session, scene_id: str, limit: int = 20) -> list[dict]:
    """获取场景的反馈时间线"""
    items = db.query(ReflectTimeline).filter(
        ReflectTimeline.scene_id == scene_id
    ).order_by(ReflectTimeline.created_at.desc()).limit(limit).all()
    items.reverse()
    return [_reflect_to_dict(r) for r in items]


def get_dashboard_status(db: Session, scene_id: str) -> dict:
    """获取仪表盘状态汇总"""
    pq_count = db.query(PriorityQueue).filter(
        PriorityQueue.scene_id == scene_id
    ).count()

    running = db.query(PriorityQueue).filter(
        PriorityQueue.scene_id == scene_id,
        PriorityQueue.status == "running"
    ).first()

    completed = db.query(PriorityQueue).filter(
        PriorityQueue.scene_id == scene_id,
        PriorityQueue.status == "completed"
    ).count()

    return {
        "queue_total": pq_count,
        "completed": completed,
        "current_task": _pq_to_dict(running) if running else None,
    }


def _pq_to_dict(pq: PriorityQueue) -> dict:
    return {
        "id": pq.id,
        "scene_id": pq.scene_id,
        "node_id": pq.node_id,
        "title": pq.title,
        "priority": pq.priority,
        "status": pq.status,
        "deps": json.loads(pq.deps) if pq.deps else [],
        "sort_order": pq.sort_order,
        "created_at": pq.created_at.isoformat() if pq.created_at else None,
        "completed_at": pq.completed_at.isoformat() if pq.completed_at else None,
    }


def _reflect_to_dict(r: ReflectTimeline) -> dict:
    return {
        "id": r.id,
        "type": r.type,
        "icon": r.icon,
        "title": r.title,
        "detail": r.detail,
        "tag": r.tag,
        "tag_text": r.tag_text,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def generate_pq_from_existing(db: Session, scene_id: str, tm: ThinkingMap,
                               summary: str = "") -> dict:
    """（补齐用）对已收敛节点重新生成 PriorityQueue + ReflectTimeline

    适用于旧规则收敛后没有 PQ/Reflect 的场景。
    只生成队列，不修改节点状态。
    """
    from ai_engine import call_deepseek_chat

    all_nodes = db.query(ThinkNode).filter(
        ThinkNode.map_id == tm.id,
        ThinkNode.type != "root",
        ThinkNode.status.in_(["confirmed", "refined"]),
    ).all()

    if not all_nodes or len(all_nodes) < 2:
        return {"pq_items": [], "project": None}

    parent_labels = {n.id: n.label for n in all_nodes}
    node_summary = [
        {"id": n.id, "label": n.label, "type": n.type, "status": n.status,
         "parent_label": parent_labels.get(n.parent_id, ""),
         "children": [c.id for c in n.children] if n.children else []}
        for n in all_nodes
    ]

    prompt = '''你是一个任务调度专家。分析以下已收敛的任务节点，生成优先级队列。

输出严格 JSON（不要 markdown 代码块）：
{
  "queue": [
    {
      "target_id": "节点ID",
      "title": "任务名",
      "priority": 1,
      "deps": ["依赖ID"]
    }
  ],
  "project": {
    "is_project": false,
    "name": "",
    "description": "",
    "structure": []
  }
}

规则：
1. 为每个节点分配 P1-P4 优先级和依赖链
2. P1=最高优先级，P4=最低优先级
3. 根据任务的实际工作流逻辑判断先后顺序和依赖关系
4. project: 判断这些节点是否构成一个可交付的项目（多页面/多文档等）
'''

    user_msg = f"请分析以下任务节点：\\n{json.dumps(node_summary, ensure_ascii=False, indent=2)}"
    if summary:
        user_msg += f"\\n\\n对话背景：\\n{summary}\\n"

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_msg},
    ]

    raw = call_deepseek_chat(messages, model="flash", temperature=0.1, max_tokens=4096, route="medium")
    if not raw:
        print(f"[pq_gen] LLM 返回空")
        return {"pq_items": [], "project": None}

    text = raw.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(text) if text.startswith("{") else None
        if not parsed:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end+1])
        if not parsed:
            print(f"[pq_gen] 无法解析 LLM 输出: {raw[:200]}")
            return {"pq_items": [], "project": None}
    except json.JSONDecodeError as e:
        print(f"[pq_gen] JSON 解析失败: {e}\\n{raw[:300]}")
        return {"pq_items": [], "project": None}

    # 清空旧 PQ
    db.query(PriorityQueue).filter(PriorityQueue.scene_id == scene_id).delete()

    queue_entries = parsed.get("queue", [])
    pq_items = []
    for idx, entry in enumerate(queue_entries):
        target_id = entry.get("target_id", "")
        title = entry.get("title", "")
        priority = entry.get("priority", 2)
        deps = entry.get("deps", [])
        if not target_id or not title:
            continue
        node = db.query(ThinkNode).filter(ThinkNode.id == target_id).first()
        if not node:
            continue
        pq = PriorityQueue(
            id=make_id("pq"), scene_id=scene_id, node_id=target_id,
            title=title, priority=priority, status="pending",
            deps=json.dumps(deps, ensure_ascii=False), sort_order=idx,
        )
        db.add(pq)
        pq_items.append(pq)

    db.commit()

    # Reflect 摘要
    if pq_items:
        p1_count = sum(1 for e in queue_entries if e.get("priority") == 1)
        rt = ReflectTimeline(
            id=make_id("ref"), scene_id=scene_id, type="new",
            icon="📊", title=f"优先级队列就绪（补齐）",
            detail=f"{len(queue_entries)} 个任务入队，P1={p1_count} 个",
            tag="queue_update",
        )
        db.add(rt)
        db.commit()

    # 项目认知
    project_info = parsed.get("project", {})
    project_result = None
    if project_info and project_info.get("is_project"):
        from models import OutputProject
        proj_name = project_info.get("name", "未命名项目")[:200]
        proj_desc = project_info.get("description", "")[:500]
        existing = db.query(OutputProject).filter(
            OutputProject.scene_id == scene_id, OutputProject.is_active == True,
        ).first()
        if existing:
            existing.name = proj_name
            existing.description = proj_desc
            db.commit()
            project_result = {"project_id": existing.id, "name": proj_name, "description": proj_desc}
        else:
            proj = OutputProject(
                id=make_id("proj"), scene_id=scene_id, name=proj_name, description=proj_desc,
            )
            db.add(proj)
            db.commit()
            project_result = {"project_id": proj.id, "name": proj_name, "description": proj_desc}
            rt = ReflectTimeline(
                id=make_id("ref"), scene_id=scene_id, type="new", icon="🏗️",
                title=f"项目: {proj_name}", detail=proj_desc[:100],
                tag="inject", tag_text="收敛补齐自动创建",
            )
            db.add(rt)
            db.commit()

    print(f"[pq_gen] 完成: {len(queue_entries)} 入队")
    return {
        "pq_items": [_pq_to_dict(p) for p in pq_items],
        "project": project_result,
    }
