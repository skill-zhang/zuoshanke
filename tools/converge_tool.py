"""converge_tool — LLM 自主触发的收敛整理工具

Agent Loop 通过此工具在对话信息充分时，触发 Thinking Map 的自动收敛 + 排序。
LLM 判断「讨论已深入、关注点已覆盖全面」后主动调用，由用户确认执行。

使用场景：
  - LLM 和用户聊了几轮后，觉得各方信息已足够，主动询问用户是否要收敛
  - 用户主动说「收」「走起」「整理一下」「进入执行」
  - LLM 收到后调用此工具触发收敛管线

用法:
    converge(scene_id="xxx", summary="已经聊了底盘、发动机、排放标准、过户流程")
"""

import json
import sys
import os

# 把 backend 目录加入 path，以便 import database / agent_core
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


def converge(scene_id: str, summary: str = "") -> str:
    """对当前场景进行收敛整理

    LLM 在对话信息充分时调用此工具，触发 Thinking Map 的自动收敛 + 排序：
    1. 分析当前 TM 所有活跃节点，合并相似项、标记废弃
    2. 生成 P1-P4 优先级队列
    3. 写入 ReflectTimeline 记录收敛动作

    Args:
        scene_id: 场景 ID（从系统提示中的「当前场景信息」获取）
        summary: 可选，LLM 对当前讨论的摘要说明，用于 ReflectTimeline

    Returns:
        JSON 字符串，含收敛结果摘要
    """
    if not scene_id:
        return json.dumps({
            "success": False,
            "error": "scene_id 不能为空",
        }, ensure_ascii=False)

    # 懒导入 DB 模块（防止循环依赖 + 确保 path 就绪）
    try:
        from database import SessionLocal
        from models import ThinkingMap
        from agent_core.converge_engine import auto_converge_and_prioritize
    except ImportError as e:
        return json.dumps({
            "success": False,
            "error": f"导入失败: {e}",
        }, ensure_ascii=False)

    db = SessionLocal()
    try:
        # 查找场景的 Thinking Map
        tmap = db.query(ThinkingMap).filter(
            ThinkingMap.scene_id == scene_id
        ).first()

        if not tmap:
            return json.dumps({
                "success": False,
                "error": f"未找到场景 {scene_id} 的 Thinking Map",
            }, ensure_ascii=False)

        # 检查是否有足够多的节点需要收敛
        from models import ThinkNode
        node_count = db.query(ThinkNode).filter(
            ThinkNode.map_id == tmap.id,
            ThinkNode.type != "root",
        ).count()

        if node_count < 2:
            return json.dumps({
                "success": False,
                "error": f"当前只有 {node_count} 个节点，暂无收敛必要",
                "node_count": node_count,
            }, ensure_ascii=False)

        # 执行自动收敛 + 排序（传对话摘要，指导优先级判断）
        pq_items = auto_converge_and_prioritize(db, scene_id, tmap, summary=summary)

        # 写入摘要到 ReflectTimeline
        if summary and pq_items:
            try:
                from models import ReflectTimeline
                from utils import make_id
                rt = ReflectTimeline(
                    id=make_id("ref"),
                    scene_id=scene_id,
                    type="new",
                    icon="🚀",
                    title="LLM 触发收敛",
                    detail=summary[:200] if summary else "讨论充分，发起收敛",
                    tag="inject",
                    tag_text=f"{len(pq_items)} 个任务入队",
                )
                db.add(rt)
                db.commit()
            except Exception:
                pass  # ReflectTimeline 写入失败不阻塞主流程

        # 准备返回结果
        result = {
            "success": True,
            "message": f"收敛完成！合并/排序了 {len(pq_items)} 个任务",
            "queue_count": len(pq_items),
            "node_count": node_count,
        }

        # 附上 PQ 摘要（截断，避免撑爆 context）
        if pq_items:
            summaries = []
            for pq in pq_items:
                summaries.append(
                    f"[P{pq.get('priority', 2)}] {pq.get('title', '')[:40]}"
                )
            result["queue_summary"] = summaries[:8]  # 最多 8 条
            if len(summaries) > 8:
                result["queue_summary"].append(f"... 还有 {len(summaries) - 8} 个")

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"收敛失败: {e}",
        }, ensure_ascii=False)
    finally:
        db.close()
