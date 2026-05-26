"""thinking_map_read — 读取 Thinking Map 思维导图节点信息（只读查询）

LLM 通过此工具查询当前场景的思维导图节点树，了解已有哪些节点、结构如何，
以便做出更合理的发散/收敛决策。

用法:
    thinking_map_read(scene_id="scene-xxx")
"""

import json
import sys
import os

# 把 backend 目录加入 path，以便 import database / models
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


def _serialize_node(node, indent=0):
    """将 ThinkNode 对象序列化为字典"""
    prefix = "  " * indent
    result = {
        "id": node.id,
        "label": node.label,
        "type": node.type,
        "status": node.status,
        "actionable": node.actionable,
        "priority": node.priority,
        "queue_order": node.queue_order,
    }
    # 可选字段，有值才返回
    if node.discussion:
        result["discussion"] = node.discussion
    if node.converged_from:
        result["converged_from"] = node.converged_from
    if node.depends_on:
        result["depends_on"] = node.depends_on
    if node.execution_result:
        result["execution_result"] = node.execution_result[:200] if len(node.execution_result) > 200 else node.execution_result
    if node.context_ref:
        result["context_ref"] = node.context_ref
    return result


def thinking_map_read(scene_id: str = None) -> str:
    """读取当前场景的 Thinking Map 思维导图节点信息（只读查询）

    返回场景的思维导图结构，包括所有节点及其层级关系、状态、优先级等信息。
    不修改任何数据。

    Args:
        scene_id: 场景 ID（从系统提示中的「当前场景信息」获取）。必填。

    Returns:
        JSON 字符串，含思维导图信息
    """
    if not scene_id:
        return json.dumps({
            "success": False,
            "error": "scene_id 不能为空",
        }, ensure_ascii=False)

    try:
        from database import SessionLocal
        from models import ThinkingMap, ThinkNode
    except ImportError as e:
        return json.dumps({
            "success": False,
            "error": f"导入失败: {e}",
        }, ensure_ascii=False)

    db = SessionLocal()
    try:
        # 查找场景的 ThinkingMap
        tm = db.query(ThinkingMap).filter(
            ThinkingMap.scene_id == scene_id
        ).first()

        if not tm:
            return json.dumps({
                "success": True,
                "exists": False,
                "message": f"场景 {scene_id} 还没有 Thinking Map",
            }, ensure_ascii=False)

        # 获取所有节点
        all_nodes = db.query(ThinkNode).filter(
            ThinkNode.map_id == tm.id
        ).order_by(ThinkNode.type, ThinkNode.queue_order.asc().nullslast(), ThinkNode.label).all()

        # 构建树结构
        root_nodes = [n for n in all_nodes if n.type == "root"]
        domain_nodes = [n for n in all_nodes if n.type == "domain"]
        leaf_nodes = [n for n in all_nodes if n.type == "leaf"]

        # 按 parent_id 组织子节点
        children_map = {}
        for n in all_nodes:
            pid = n.parent_id or "root"
            if pid not in children_map:
                children_map[pid] = []
            children_map[pid].append(_serialize_node(n))

        # 构建树
        def build_tree(parent_id):
            nodes = children_map.get(parent_id, [])
            for node in nodes:
                node["children"] = children_map.get(node["id"], [])
            return nodes

        tree = build_tree("root")

        # 统计信息
        status_counts = {}
        for n in all_nodes:
            s = n.status
            status_counts[s] = status_counts.get(s, 0) + 1

        priority_counts = {}
        for n in all_nodes:
            if n.priority:
                key = f"P{n.priority}"
                priority_counts[key] = priority_counts.get(key, 0) + 1

        result = {
            "success": True,
            "exists": True,
            "map": {
                "id": tm.id,
                "title": tm.title,
                "status": tm.status,
                "version": tm.version,
                "created_at": tm.created_at.isoformat() if tm.created_at else None,
                "updated_at": tm.updated_at.isoformat() if tm.updated_at else None,
            },
            "stats": {
                "total_nodes": len(all_nodes),
                "roots": len(root_nodes),
                "domains": len(domain_nodes),
                "leaves": len(leaf_nodes),
                "by_status": status_counts,
                "by_priority": priority_counts,
            },
            "tree": tree,
        }

        # 如果有优先级队列，单独列出
        priority_nodes = [n for n in all_nodes if n.priority is not None]
        if priority_nodes:
            priority_nodes.sort(key=lambda n: (n.priority or 99, n.queue_order or 0))
            result["priority_queue"] = [
                {
                    "id": n.id,
                    "label": n.label,
                    "type": n.type,
                    "priority": n.priority,
                    "queue_order": n.queue_order,
                    "status": n.status,
                    "actionable": n.actionable,
                }
                for n in priority_nodes
            ]

        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"查询失败: {e}",
        }, ensure_ascii=False)
    finally:
        db.close()
