"""场景自省地图工具 — LLM 通过 function calling 自主声明架构图

提供 2 个工具：
  - self_map_declare: 全量初始化/覆盖
  - self_map_update: 增量更新
"""

from models import SceneSelfMap
from database import SessionLocal
from utils import make_id


def do_self_map_declare(
    title: str = "",
    tree: list = None,
    diagrams: dict = None,
) -> dict:
    """声明/覆盖场景自省图（全量）"""
    from agent_core.tool_executor import get_tool_context
    ctx = get_tool_context()
    scene_id = ctx.get("scene_id", "")
    if not scene_id:
        return {"status": "error", "message": "无法获取场景 ID，请确保在场景对话中调用"}

    db = SessionLocal()
    try:
        existing = db.query(SceneSelfMap).filter(
            SceneSelfMap.scene_id == scene_id
        ).first()
        if existing:
            existing.title = title
            existing.tree = tree or []
            existing.diagrams = diagrams or {}
        else:
            sm = SceneSelfMap(
                id=make_id("smp"),
                scene_id=scene_id,
                title=title,
                tree=tree or [],
                diagrams=diagrams or {},
            )
            db.add(sm)
        db.commit()
        return {
            "status": "ok",
            "title": title,
            "node_count": len(tree or []),
            "message": f"自省图已{'更新' if existing else '创建'}，共 {len(tree or [])} 个根节点",
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def _find_and_operate(tree: list, predicate, operation):
    """递归操作树节点"""
    for i, item in enumerate(tree):
        if predicate(item):
            return operation(tree, i, item)
        if "children" in item and item["children"]:
            result = _find_and_operate(item["children"], predicate, operation)
            if result:
                return result
    return None


def do_self_map_update(
    action: str = "",
    parent_id: str = None,
    node: dict = None,
    node_id: str = None,
    diagram_node_id: str = None,
    diagram: dict = None,
    title: str = None,
) -> dict:
    """增量更新场景自省图"""
    from agent_core.tool_executor import get_tool_context
    ctx = get_tool_context()
    scene_id = ctx.get("scene_id", "")
    if not scene_id:
        return {"status": "error", "message": "无法获取场景 ID"}

    db = SessionLocal()
    try:
        sm = db.query(SceneSelfMap).filter(
            SceneSelfMap.scene_id == scene_id
        ).first()
        if not sm:
            return {"status": "error", "message": "自省图尚未初始化，请先调用 self_map_declare"}

        if action == "update_title" and title:
            sm.title = title
        elif action == "add_node" and node:
            sm.tree = _add_node(sm.tree, node, parent_id)
        elif action == "update_node" and node:
            sm.tree = _update_node(sm.tree, node)
        elif action == "remove_node" and node_id:
            sm.tree = _remove_node(sm.tree, node_id)
            sm.diagrams.pop(node_id, None)
        elif action == "add_diagram" and diagram_node_id and diagram:
            sm.diagrams[diagram_node_id] = diagram
            # 自动标记关联节点有流程图
            sm.tree = _mark_has_diagram(sm.tree, diagram_node_id)
        elif action == "remove_diagram" and diagram_node_id:
            sm.diagrams.pop(diagram_node_id, None)
        else:
            return {"status": "error", "message": f"无效操作: {action} 或缺少必要参数"}

        db.commit()
        return {
            "status": "ok",
            "action": action,
            "node_count": len(sm.tree),
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def _add_node(tree: list, node: dict, parent_id: str = None) -> list:
    if not parent_id:
        return tree + [node]
    for item in tree:
        if item["id"] == parent_id:
            item.setdefault("children", []).append(node)
            return tree
        if "children" in item:
            _add_node(item["children"], node, parent_id)
    return tree


def _update_node(tree: list, node: dict) -> list:
    for i, item in enumerate(tree):
        if item["id"] == node["id"]:
            tree[i] = {**item, **node}
            return tree
        if "children" in item:
            _update_node(item["children"], node)
    return tree


def _remove_node(tree: list, node_id: str) -> list:
    result = []
    for item in tree:
        if item["id"] == node_id:
            continue
        if "children" in item:
            item["children"] = _remove_node(item["children"], node_id)
        result.append(item)
    return result


def _mark_has_diagram(tree: list, node_id: str) -> list:
    for item in tree:
        if item["id"] == node_id:
            item["hasDiagram"] = True
            return tree
        if "children" in item:
            _mark_has_diagram(item["children"], node_id)
    return tree
