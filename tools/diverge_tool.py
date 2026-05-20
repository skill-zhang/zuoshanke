"""diverge_tool — LLM 自主触发的发散工具

Agent Loop 通过此工具在对话中发现新话题/新需求时，往 Thinking Map 添加思维节点。
每识别一个新维度（需求、约束、渠道、方法等），自动创建 ThinkNode。

使用场景：
  - 用户说了新的需求、约束条件、目标
  - LLM 发现了之前没覆盖到的新维度
  - 用户主动提出了新的关注点

用法:
    diverge(scene_id="xxx", nodes=[{"label": "预算30万", "type": "domain"}, ...])
"""

import json
import sys
import os

# 把 backend 目录加入 path，以便 import database / agent_core
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


def diverge(scene_id: str, nodes: list = None) -> str:
    """向当前场景的 Thinking Map 添加发散节点

    LLM 在对话过程中识别到新话题/新维度时调用此工具，
    自动创建 ThinkNode 并关联到场景的 ThinkingMap。

    Args:
        scene_id: 场景 ID（从系统提示中的「当前场景信息」获取）
        nodes: 节点列表，每个节点格式：
            {"label": "节点标题", "type": "domain|leaf", "parent_label": "父节点标题（可选）"}

    Returns:
        JSON 字符串，含创建的节点列表
    """
    from sqlalchemy.orm import Session
    from database import SessionLocal
    from models import ThinkingMap, ThinkNode
    from utils import make_id

    if not scene_id:
        return json.dumps({"success": False, "error": "scene_id 不能为空"})

    if not nodes:
        return json.dumps({"success": False, "error": "nodes 不能为空"})

    db: Session = SessionLocal()
    try:
        # 查找场景的 ThinkingMap（没有则创建）
        tm = db.query(ThinkingMap).filter(
            ThinkingMap.scene_id == scene_id
        ).first()

        if not tm:
            return json.dumps({
                "success": False,
                "error": "场景还没有 ThinkingMap，请先确保场景已初始化",
                "hint": "场景内的首次对话会自动创建 ThinkingMap"
            })

        # 获取现有节点用于 parent_label → parent_id 映射
        existing_nodes = db.query(ThinkNode).filter(
            ThinkNode.map_id == tm.id
        ).all()
        label_to_id = {n.label: n.id for n in existing_nodes}

        created = []
        for node_def in nodes:
            label = node_def.get("label", "").strip()
            if not label:
                continue
            node_type = node_def.get("type", "leaf")
            parent_label = node_def.get("parent_label", "")

            # 找父节点 ID
            parent_id = None
            if parent_label and parent_label in label_to_id:
                parent_id = label_to_id[parent_label]
            else:
                # 没有指定父标签，放在根节点下
                root_nodes = [n for n in existing_nodes if n.type == "root"]
                if root_nodes:
                    parent_id = root_nodes[0].id

            # 去重：检查是否有同 label 的活跃节点
            duplicate = db.query(ThinkNode).filter(
                ThinkNode.map_id == tm.id,
                ThinkNode.label == label,
                ThinkNode.status.in_(["discussing", "confirmed"]),
            ).first()
            if duplicate:
                created.append({
                    "id": duplicate.id,
                    "label": duplicate.label,
                    "type": duplicate.type,
                    "existing": True,
                })
                continue

            # Schema v0.81: 如果父节点是 leaf，自动升级为 domain
            if parent_id:
                parent_node = db.query(ThinkNode).filter(ThinkNode.id == parent_id).first()
                if parent_node and parent_node.type == "leaf":
                    parent_node.type = "domain"
                    print(f"[diverge] 自动升级父节点 {parent_node.label}: leaf → domain")
                    db.commit()

            node = ThinkNode(
                id=make_id("tn"),
                map_id=tm.id,
                parent_id=parent_id,
                type=node_type,
                label=label,
                status="discussing",
                created_by="brainstorm",
            )
            db.add(node)
            db.commit()
            db.refresh(node)

            label_to_id[label] = node.id
            created.append({
                "id": node.id,
                "label": node.label,
                "type": node.type,
                "existing": False,
            })

        return json.dumps({
            "success": True,
            "count": len(created),
            "nodes": created,
        }, ensure_ascii=False)

    except Exception as e:
        db.rollback()
        return json.dumps({"success": False, "error": str(e)})
    finally:
        db.close()
