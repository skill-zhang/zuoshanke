"""Thinking Map 操作 — diverge / converge / prioritize / reflect"""
import json
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import Scene, ThinkingMap, ThinkNode, PriorityQueue
from router.shared import sse_event, sse_response
from schemas import ThinkingMapOut, ThinkNodeOut, ThinkNodeCreate, ThinkNodeUpdate, SceneOut
from utils import make_id, utcnow

router = APIRouter(tags=["思维导图"])

# ═══ Thinking Map ═══

@router.get("/api/scenes/{scene_id}/thinking-map", response_model=ThinkingMapOut)
def get_thinking_map(scene_id: str, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    tmap = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")
    tmap.nodes  # trigger lazy load
    return tmap


@router.post("/api/thinking-maps/{map_id}/nodes", response_model=ThinkNodeOut)
def add_node(map_id: str, data: ThinkNodeCreate, db: Session = Depends(get_db)):
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")
    if data.parent_id:
        parent = db.query(ThinkNode).filter(ThinkNode.id == data.parent_id).first()
        if not parent:
            raise HTTPException(404, "父节点不存在")

    node = ThinkNode(
        id=data.id, map_id=map_id, parent_id=data.parent_id,
        type=data.type, label=data.label, status=data.status,
        actionable=data.actionable, discussion=data.discussion,
        context_ref=data.context_ref,
        position_x=data.position_x, position_y=data.position_y,
    )
    db.add(node)
    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()
    db.refresh(node)
    return node


@router.patch("/api/think-nodes/{node_id}", response_model=ThinkNodeOut)
def update_node(node_id: str, data: ThinkNodeUpdate, db: Session = Depends(get_db)):
    node = db.query(ThinkNode).filter(ThinkNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    for field in ("label", "status", "actionable", "discussion", "position_x", "position_y",
                  "priority", "queue_order", "execution_result", "created_by"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(node, field, val)
    # JSON list fields
    if data.converged_from is not None:
        node.converged_from = data.converged_from
    if data.depends_on is not None:
        node.depends_on = data.depends_on

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == node.map_id).first()
    if tmap:
        tmap.version += 1
        tmap.updated_at = utcnow()
    db.commit()
    db.refresh(node)
    return node


@router.delete("/api/think-nodes/{node_id}")
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(ThinkNode).filter(ThinkNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    db.delete(node)
    db.commit()
    return {"ok": True}



# ═══ Agent Loop: Diverge (发散阶段) ═══

class DivergeRequest(BaseModel):
    context: str = Field("", description="额外上下文提示")
    force: bool = Field(False, description="强制重新发散")


@router.post("/api/thinking-maps/{map_id}/diverge")
def diverge_thinking_map(map_id: str, data: DivergeRequest = None, db: Session = Depends(get_db)):
    """
    发散 Thinking Map：LLM 头脑风暴拆解任务，生成节点树
    """
    from ai_engine import call_deepseek_chat
    import json

    if data is None:
        data = DivergeRequest()

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map不存在")

    scene = db.query(Scene).filter(Scene.id == tmap.scene_id).first()
    scene_name = scene.name if scene else "未命名场景"
    scene_desc = scene.description or ""

    existing_nodes = db.query(ThinkNode).filter(ThinkNode.map_id == map_id).all()
    root = next((n for n in existing_nodes if n.type == "root"), None)
    if not root:
        raise HTTPException(400, "Thinking Map缺少根节点")

    if data.force:
        for n in existing_nodes:
            if n.id != root.id and n.status == "discussing":
                db.delete(n)
        db.commit()
        existing_nodes = [root]

    is_first = len(existing_nodes) <= 1 and not any(n.type != "root" for n in existing_nodes)

    existing_summary = ""
    for n in existing_nodes:
        if n.type == "root":
            continue
        p = next((x for x in existing_nodes if x.id == n.parent_id), None)
        pl = p.label if p else "根节点"
        existing_summary += "- [" + n.status + "] " + pl + " -> " + n.label + "\n"

    # ---- Build prompts ----
    if is_first:
        prompt_lines = [
            "你是坐山客 AI 工作台的任务拆解专家。你需要将以下任务做结构化分解，输出清晰的思维导图节点树。",
            "",
            "## 任务",
            "名称: " + scene_name,
            "描述: " + (scene_desc or "(无详细描述)"),
        ]
        if data.context:
            prompt_lines.append("额外上下文: " + data.context)
        prompt_lines += [
            "",
            "## 输出格式",
            '请以 JSON 格式输出，严格按以下结构:',
            '{',
            '  "categories": [',
            '    {',
            '      "label": "类别名称",',
            '      "nodes": [',
            '        {"label": "子任务名称"},',
            '        {"label": "子任务名称"}',
            '      ]',
            '    }',
            '  ]',
            '}',
            "",
            "## 拆解要求",
            "1. 根据任务名称和描述，识别 3-5 个关键领域/模块（categories）",
            "2. 每个类别下分解 2-4 个具体可执行的子任务",
            "3. 使用简洁的中文标签（6-12 字最佳）",
            "4. 标签应该具体可执行，而非抽象概念",
            "5. 类别和子任务要有逻辑层次关系",
            "6. 输出只有 JSON，不要额外解释",
        ]
        system_prompt = "\n".join(prompt_lines)
    else:
        prompt_lines = [
            "你是坐山客 AI 工作台的任务拆解专家。请分析以下任务的思维导图当前状态，补充新的分支节点。",
            "",
            "## 任务",
            "名称: " + scene_name,
            "描述: " + (scene_desc or "(无详细描述)"),
        ]
        if data.context:
            prompt_lines.append("额外上下文: " + data.context)
        prompt_lines += [
            "",
            "## 现有节点",
            existing_summary or "(暂无细化节点)",
            "",
            "## 输出格式",
            '请以 JSON 格式输出，严格按以下结构:',
            '{',
            '  "categories": [',
            '    {',
            '      "parent_label": "要挂载的父节点名称（从现有节点中选择）",',
            '      "nodes": [',
            '        {"label": "新增子任务名称"},',
            '        {"label": "新增子任务名称"}',
            '      ]',
            '    }',
            '  ]',
            '}',
            "",
            "## 要求",
            "1. 分析现有节点，找出尚未覆盖的方向或遗漏的子任务",
            "2. 输出的 parent_label 必须从现有节点中选择（使用完全一致的名称）",
            "3. 每个父节点下补充 1-3 个新子任务",
            "4. 标签使用简洁中文（6-12 字），具体可执行",
            "5. 输出只有 JSON，不要额外解释",
        ]
        system_prompt = "\n".join(prompt_lines)

    # ---- Call LLM ----
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请对 " + scene_name + " 进行任务拆解。"},
    ]

    raw = call_deepseek_chat(messages, model="flash", temperature=0.5, max_tokens=4096, route="medium")
    if not raw:
        raise HTTPException(502, "LLM发散调用失败")

    # ---- Parse JSON ----
    def _extract_json(text):
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None

    parsed = _extract_json(raw)
    if not parsed:
        logger.error("[Diverge] LLM返回无法解析: " + raw[:300])
        raise HTTPException(502, "LLM发散结果解析失败，请重试")

    categories = parsed.get("categories", [])
    if not categories:
        categories = parsed.get("nodes", [])

    if not categories:
        return {
            "map_id": map_id,
            "new_nodes": [],
            "thinking_map": {"id": tmap.id, "title": tmap.title,
                "status": tmap.status, "version": tmap.version,
                "nodes": [n.to_schema_dict() for n in existing_nodes]},
            "message": "LLM未生成任何节点",
        }

    # ---- Create nodes ----
    name_to_id = {n.label: n.id for n in existing_nodes}
    new_nodes = []

    for cat in categories:
        parent_label = cat.get("parent_label", cat.get("label", ""))
        children = cat.get("nodes", [])

        if is_first and "label" in cat:
            parent_label = cat["label"]
            if parent_label not in name_to_id:
                l1_id = make_id("n")
                l1_node = ThinkNode(
                    id=l1_id, map_id=map_id, parent_id=root.id,
                    type="domain", label=parent_label,
                    status="discussing", created_by="brainstorm",
                )
                db.add(l1_node)
                new_nodes.append(l1_node)
                name_to_id[parent_label] = l1_id

        parent_id = name_to_id.get(parent_label, root.id)

        for child in children:
            child_label = child.get("label", "")
            if not child_label:
                continue
            is_dup = any(
                n.parent_id == parent_id and n.label == child_label
                for n in existing_nodes + new_nodes
            )
            if is_dup:
                continue
            child_id = make_id("n")
            child_node = ThinkNode(
                id=child_id, map_id=map_id, parent_id=parent_id,
                type="leaf", label=child_label,
                status="discussing", created_by="brainstorm",
            )
            db.add(child_node)
            new_nodes.append(child_node)

    if not new_nodes:
        return {
            "map_id": map_id,
            "new_nodes": [],
            "thinking_map": {"id": tmap.id, "title": tmap.title,
                "status": tmap.status, "version": tmap.version,
                "nodes": [n.to_schema_dict() for n in existing_nodes]},
            "message": "所有节点已存在，无需新增",
        }

    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()

    db.refresh(tmap)
    all_nodes = db.query(ThinkNode).filter(ThinkNode.map_id == map_id).all()
    return {
        "map_id": map_id,
        "new_nodes": [n.to_schema_dict() for n in new_nodes],
        "is_first_diverge": is_first,
        "thinking_map": {"id": tmap.id, "title": tmap.title,
            "status": tmap.status, "version": tmap.version,
            "nodes": [n.to_schema_dict() for n in all_nodes]},
    }


# ═══ Agent Loop: Converge ═══

@router.post("/api/thinking-maps/{map_id}/converge")
def converge_thinking_map(map_id: str, db: Session = Depends(get_db)):
    """
    收敛 Thinking Map：
    1. 获取所有 status=discussing 的叶子节点
    2. 用标签相似度聚类（difflib.SequenceMatcher）
    3. 对每组 2+ 相似节点：创建 refined 节点 + 标记源节点为 discarded
    4. 单节点可选提升为 refined
    返回收敛结果：merged_pairs + 更新后的 TM
    """
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    # 获取根节点（作为收敛后的父节点）
    root = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id, ThinkNode.type == "root"
    ).first()
    if not root:
        raise HTTPException(400, "Thinking Map 缺少根节点")

    nodes = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id,
        ThinkNode.status.in_(["discussing", "created"]),
    ).all()

    if not nodes:
        # 没有待收敛的节点，但可能有已确认节点需要生成 PQ/Reflect
        scene_id = tmap.scene_id
        confirmed_total = db.query(ThinkNode).filter(
            ThinkNode.map_id == map_id, ThinkNode.status.in_(["confirmed", "refined"])
        ).count()
        pq_existing = db.query(PriorityQueue).filter(
            PriorityQueue.scene_id == scene_id
        ).count()
        if confirmed_total >= 2 and pq_existing == 0:
            try:
                from agent_core.converge_engine import generate_pq_from_existing
                print(f"[converge] 已有收敛节点但无队列，补齐 PQ/Reflect: scene={scene_id}, confirmed={confirmed_total}")
                result = generate_pq_from_existing(db, scene_id, tmap)
                pq_count = len(result.get("pq_items", []))
                print(f"[converge] 补齐完成: PQ={pq_count}")
            except Exception as e:
                print(f"[converge] 补齐异常: {e}")
                import traceback
                traceback.print_exc()
        return {"map_id": map_id, "merged": [], "discarded": [], "message": "没有需要收敛的节点"}

    # 1. 聚类：共享公共子串检测（对中文短标签友好）
    # 如果两个标签包含至少一个长度 >=2 的公共子串，则认为相似
    def _share_substr(a: str, b: str, min_len: int = 2) -> bool:
        """检查两个字符串是否有长度 >= min_len 的公共子串"""
        subs = {a[i:i+min_len] for i in range(len(a)-min_len+1)}
        for i in range(len(b)-min_len+1):
            if b[i:i+min_len] in subs:
                return True
        return False

    clusters = []
    assigned = set()

    for i, a in enumerate(nodes):
        if a.id in assigned:
            continue
        group = [a]
        assigned.add(a.id)
        for j, b in enumerate(nodes):
            if b.id in assigned or i == j:
                continue
            if _share_substr(a.label, b.label, min_len=2):
                group.append(b)
                assigned.add(b.id)
        clusters.append(group)

    merged_pairs = []
    new_nodes = []
    for group in clusters:
        if len(group) >= 2:
            # 合并：创建 refined 节点
            best_label = group[0].label  # 取第一个为名
            merged_labels = [n.label for n in group]
            new_id = f"node-{uuid.uuid4().hex[:8]}"
            refined = ThinkNode(
                id=new_id,
                map_id=map_id,
                parent_id=root.id,
                type="leaf",
                label=best_label,
                status="refined",
                converged_from=merged_labels,
                created_by="brainstorm",
            )
            db.add(refined)
            new_nodes.append(refined)
            merged_pairs.append({
                "target_id": new_id,
                "target_label": best_label,
                "source_labels": merged_labels,
                "source_ids": [n.id for n in group],
            })
            # 标记源节点为 discarded
            for node in group:
                node.status = "discarded"
        else:
            # 单节点 → 升级为 refined（准备进入队列）
            node = group[0]
            node.status = "refined"

    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()

    # ── 旧收敛 + 新引擎接力：生成 PQ + Reflect ──
    # 如果产生了 refined 节点，接力调 LLM 收敛引擎生成优先级队列和反馈时间线
    has_new_nodes = bool(merged_pairs)  # 有合并
    total_refined = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id, ThinkNode.status == "refined"
    ).count()
    try:
        from agent_core.converge_engine import auto_converge_and_prioritize
        if total_refined >= 2:
            scene_id = tmap.scene_id
            print(f"[converge] 规则收敛完成，接力 LLM 引擎: scene={scene_id}, refined={total_refined}")
            result = auto_converge_and_prioritize(db, scene_id, tmap)
            if result.get("project"):
                print(f"[converge] 项目认知: {result['project']}")
            pq_count = len(result.get("pq_items", []))
            print(f"[converge] 接力完成: PQ={pq_count}, merged={result.get('merged', 0)}")
    except Exception as e:
        print(f"[converge] 接力收敛异常（非致命，已捕获）: {e}")
        import traceback
        traceback.print_exc()

    # 刷新返回
    db.refresh(tmap)
    tmap.nodes  # trigger load
    return {
        "map_id": map_id,
        "merged": merged_pairs,
        "discarded": [],  # 预留：后续可加不可行检测
        "thinking_map": {
            "id": tmap.id,
            "title": tmap.title,
            "status": tmap.status,
            "version": tmap.version,
            "nodes": [n.to_schema_dict() for n in tmap.nodes],
        },
    }


# ═══ Agent Loop: Priority Queue ═══

def _topological_sort(nodes: list) -> list:
    """
    拓扑排序（Kahn 算法）。
    nodes: 每个元素有 id, depends_on (list of ids)。
    返回排序后的节点列表；若有环则按入度降序返回（尽力而为）。
    """
    adj = {n.id: [] for n in nodes}  # 邻接表
    in_deg = {n.id: 0 for n in nodes}
    id_map = {n.id: n for n in nodes}

    for n in nodes:
        for dep_id in (n.depends_on or []):
            if dep_id in adj:
                adj[dep_id].append(n.id)
                in_deg[n.id] = in_deg.get(n.id, 0) + 1

    queue = [nid for nid, d in in_deg.items() if d == 0]
    sorted_ids = []

    while queue:
        # 按依赖数量排序，先处理 blocking 更多的
        queue.sort(key=lambda nid: len(adj.get(nid, [])), reverse=True)
        nid = queue.pop(0)
        sorted_ids.append(nid)
        for neighbor in adj.get(nid, []):
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)

    # 如果有剩余（环），按入度降序追加
    remaining = [nid for nid in in_deg if nid not in sorted_ids]
    remaining.sort(key=lambda nid: in_deg[nid], reverse=True)
    sorted_ids.extend(remaining)

    return [id_map[nid] for nid in sorted_ids if nid in id_map]


@router.post("/api/thinking-maps/{map_id}/prioritize")
def prioritize_thinking_map(map_id: str, db: Session = Depends(get_db)):
    """
    自动排序 Priority Queue：
    1. 收集所有 status=refined 的节点
    2. 基于公共子串启发式检测依赖关系（如果 A 的标签包含 B 标签的子串 → A 依赖 B）
    3. 拓扑排序
    4. 分配 priority + queue_order
    5. 孤立的单节点（无依赖无阻塞）排最后
    """
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    # 只处理 refined 节点
    refined_nodes = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id,
        ThinkNode.status == "refined",
    ).all()

    if not refined_nodes:
        return {"map_id": map_id, "queue": [], "message": "没有 refined 节点需要排序"}

    # 1. 启发式依赖检测：如果 A 标签包含 B 标签中长度 >=2 的子串，A 依赖 B
    def _shares_substr(a: str, b: str) -> bool:
        subs = {a[i:i+2] for i in range(len(a)-1)}
        for i in range(len(b)-1):
            if b[i:i+2] in subs:
                return True
        return False

    current_deps = {}
    for n in refined_nodes:
        deps = n.depends_on or []
        # 自动检测：如果当前节点标签包含其他节点标签的子串，自动添加依赖
        for other in refined_nodes:
            if other.id == n.id:
                continue
            # 如果 other 的标签是 n 标签的子串 → n 依赖 other（other 是前置条件）
            if other.label in n.label or _shares_substr(other.label, n.label):
                if other.id not in deps:
                    deps.append(other.id)
        n.depends_on = list(set(deps))  # 去重
        current_deps[n.id] = n.depends_on

    # 2. 拓扑排序
    sorted_nodes = _topological_sort(refined_nodes)

    # 3. 计算每个节点的阻塞数（有多少节点直接依赖它）
    dependents_count = {n.id: 0 for n in refined_nodes}
    for n in sorted_nodes:
        for dep_id in (n.depends_on or []):
            if dep_id in dependents_count:
                dependents_count[dep_id] = dependents_count.get(dep_id, 0) + 1

    # 4. 分配 queue_order + priority
    queue = []
    level_map = {}  # nid → depth level

    # BFS 计算依赖深度
    for n in sorted_nodes:
        deps = n.depends_on or []
        if not deps:
            level_map[n.id] = 0
        else:
            existing_levels = [level_map.get(d, 0) for d in deps if d in level_map]
            level_map[n.id] = max(existing_levels, default=0) + 1

    for idx, n in enumerate(sorted_nodes):
        n.queue_order = idx + 1
        blocks = dependents_count.get(n.id, 0)

        # 优先级启发式
        if blocks >= 2:
            n.priority = 1  # P1: 2+ 节点依赖它（关键阻塞）
        elif blocks >= 1:
            n.priority = 2  # P2: 1 个节点依赖它
        elif level_map.get(n.id, 0) == 0:
            n.priority = 1  # P1: 无依赖，可立即开工
        elif level_map.get(n.id, 0) <= 2:
            n.priority = 3  # P3: 有依赖但浅
        else:
            n.priority = 4  # P4: 深依赖或无阻塞

        queue.append({
            "id": n.id,
            "label": n.label,
            "queue_order": n.queue_order,
            "priority": n.priority,
            "depends_on": n.depends_on or [],
            "blocks_count": blocks,
            "level": level_map.get(n.id, 0),
        })

    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()

    return {
        "map_id": map_id,
        "queue": queue,
        "node_count": len(queue),
    }


@router.get("/api/thinking-maps/{map_id}/queue")
def get_priority_queue(map_id: str, db: Session = Depends(get_db)):
    """获取 Priority Queue（按 queue_order 排序）"""
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    refined = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id,
        ThinkNode.status == "refined",
    ).order_by(ThinkNode.queue_order).all()

    queue = []
    for n in refined:
        queue.append({
            "id": n.id,
            "label": n.label,
            "queue_order": n.queue_order,
            "priority": n.priority,
            "depends_on": n.depends_on or [],
            "converged_from": n.converged_from or [],
        })

    return {
        "map_id": map_id,
        "queue": queue,
        "node_count": len(queue),
    }


# ═══ Agent Loop: Reflect（反馈注入）═══

class ReflectRequest(BaseModel):
    node_id: str
    result_summary: str
    new_discoveries: List[str] = Field(default_factory=list)
    is_success: bool = True


@router.post("/api/thinking-maps/{map_id}/reflect")
def reflect_thinking_map(map_id: str, data: ReflectRequest, db: Session = Depends(get_db)):
    """
    反馈注入：Action Map 执行完成后，将结果和发现反哺回 Thinking Map。
    1. 更新已执行节点的 execution_result + status
    2. 为每个新发现创建子节点（created_by=reflect）
    3. 自动重新收敛 + 排序
    """
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    root = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id, ThinkNode.type == "root"
    ).first()
    if not root:
        raise HTTPException(400, "缺少根节点")

    # 1. 更新已执行节点
    node = db.query(ThinkNode).filter(ThinkNode.id == data.node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")

    node.execution_result = data.result_summary
    node.status = "completed" if data.is_success else "refined"
    reflect_events = [{
        "type": "node_completed" if data.is_success else "node_blocked",
        "node_id": node.id,
        "label": node.label,
        "summary": data.result_summary[:100],
    }]

    # 2. 创建新发现子节点
    new_node_ids = []
    for discovery_label in data.new_discoveries:
        new_id = f"node-{uuid.uuid4().hex[:8]}"
        new_node = ThinkNode(
            id=new_id,
            map_id=map_id,
            parent_id=root.id,
            type="leaf",
            label=discovery_label,
            status="discussing",
            created_by="reflect",
        )
        db.add(new_node)
        new_node_ids.append(new_id)
        reflect_events.append({
            "type": "new_discovery",
            "node_id": new_id,
            "label": discovery_label,
            "summary": f"在执行「{node.label}」时发现",
        })

    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()

    # 3. 自动重新收敛 + 排序（如果有新发现）
    re_converge = None
    re_prioritize = None
    if new_node_ids:
        # 调用收敛（复用之前的聚类逻辑）
        discussing = db.query(ThinkNode).filter(
            ThinkNode.map_id == map_id,
            ThinkNode.status.in_(["discussing", "created"]),
        ).all()
        # 简化：把新节点标记为 refined（暂不聚类）
        for dn in discussing:
            dn.status = "refined"

        # 调用排序
        refined = db.query(ThinkNode).filter(
            ThinkNode.map_id == map_id,
            ThinkNode.status == "refined",
        ).order_by(ThinkNode.queue_order).all()
        if refined:
            # 更新 queue_order：追加到末尾
            max_order = max((n.queue_order or 0) for n in refined)
            for idx, rn in enumerate(refined):
                if rn.queue_order is None or rn.queue_order == 0:
                    max_order += 1
                    rn.queue_order = max_order
                    rn.priority = 3  # 新发现默认 P3
            db.commit()

        re_converge = True
        re_prioritize = True

    # 刷新返回
    db.refresh(tmap)
    tmap.nodes
    return {
        "map_id": map_id,
        "events": reflect_events,
        "new_node_ids": new_node_ids,
        "re_converge": re_converge,
        "re_prioritize": re_prioritize,
        "thinking_map": {
            "id": tmap.id,
            "title": tmap.title,
            "status": tmap.status,
            "version": tmap.version,
            "nodes": [n.to_schema_dict() for n in tmap.nodes],
        },
    }
