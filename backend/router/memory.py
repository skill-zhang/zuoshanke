"""记忆系统 API — CRUD + 搜索 + 权重调整

端点:
    GET    /api/memory          — 列表（支持 category 筛选）
    GET    /api/memory/top      — 获取应注入上下文的 Top-N 记忆
    POST   /api/memory          — 创建记忆
    GET    /api/memory/{key}    — 按 key 查看
    PUT    /api/memory/{key}    — 更新记忆
    DELETE /api/memory/{key}    — 删除记忆
    POST   /api/memory/{key}/reinforce  — 强化记忆（用户强调）
    POST   /api/memory/{key}/pin       — 标记 P0（永不过期）
    POST   /api/memory/auto-extract    — 从对话中自动提取记忆
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from database import get_db
from sqlalchemy.orm import Session
from agent_core.memory_manager import MemoryManager


# ── 记忆来源名解析 ──

_MEMORY_SOURCE_NAMES: dict[str, tuple[str, str]] = {}  # (scope, context_id) → (name, icon)


def _resolve_group_name(db: Session, scope: str, context_id: str | None) -> tuple[str, str]:
    """根据 scope + context_id 解析来源名和图标"""
    cache_key = f"{scope}:{context_id or ''}"
    if cache_key in _MEMORY_SOURCE_NAMES:
        return _MEMORY_SOURCE_NAMES[cache_key]

    if scope == "zhu":
        name, icon = "本体记忆", "🧠"
    elif scope == "scene" and context_id:
        from models import Scene
        scene = db.query(Scene).filter(Scene.id == context_id).first()
        if scene and (scene.name or scene.icon):
            # 去重场景名：同名场景追加图标区分
            name = scene.name
            icon = scene.icon or "📦"
        else:
            name, icon = "已删除场景", "🗑️"
    elif scope == "channel" and context_id:
        from models import Channel
        ch = db.query(Channel).filter(Channel.id == context_id).first()
        if ch:
            name, icon = ch.name or "未命名频道", "💬"
        else:
            name, icon = "已删除频道", "🗑️"
    else:
        name, icon = "其他", "📦"

    _MEMORY_SOURCE_NAMES[cache_key] = (name, icon)
    return name, icon


router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/groups")
def list_memory_groups(db: Session = Depends(get_db)):
    """按来源聚合记忆，返回每个组的概览（上层卡片）"""
    from models import AgentMemory
    from sqlalchemy import func

    # 按 scope + context_id 分组聚合
    rows = (
        db.query(
            AgentMemory.scope,
            AgentMemory.context_id,
            func.count(AgentMemory.id).label("count"),
            func.max(AgentMemory.created_at).label("latest"),
        )
        .group_by(AgentMemory.scope, AgentMemory.context_id)
        .order_by(func.max(AgentMemory.created_at).desc())
        .all()
    )

    groups = []
    for r in rows:
        # 隐藏本体记忆（scope=zhu）— 它属于秘密花园
        if r.scope == "zhu":
            continue
        name, icon = _resolve_group_name(db, r.scope, r.context_id)
        # 取最新一条作为预览
        preview_entry = (
            db.query(AgentMemory.content)
            .filter(
                AgentMemory.scope == r.scope,
                AgentMemory.context_id == r.context_id,
            )
            .order_by(AgentMemory.created_at.desc())
            .first()
        )
        groups.append({
            "scope": r.scope,
            "context_id": r.context_id,
            "name": name,
            "icon": icon,
            "count": r.count,
            "preview": (preview_entry[0][:60] + "...") if preview_entry and len(preview_entry[0]) > 60 else (preview_entry[0] if preview_entry else ""),
            "latest": r.latest.isoformat() if r.latest else None,
        })

    return {"success": True, "data": groups}


# ── Schemas ──

class MemoryCreate(BaseModel):
    category: str = Field("user", description="user | agent")
    key: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    base_weight: int = Field(default=2, ge=1, le=10)
    source: str = Field(default="user", description="auto | llm | user")
    is_narrative: bool = Field(default=False, description="🆕 v2 叙事型关系记忆（历程/决策/迭代故事）")


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    base_weight: Optional[int] = None
    category: Optional[str] = None


# ── 端点 ──

@router.get("")
def list_memories(db: Session = Depends(get_db),
                  category: Optional[str] = Query(None),
                  limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0),
                  scope: Optional[str] = Query(None),         # 🆕
                  context_id: Optional[str] = Query(None),    # 🆕
                  scope_only: bool = Query(False)):            # 🆕
    """列出所有记忆（按实时权重降序）"""
    mm = MemoryManager(db)
    return {
        "success": True,
        "data": mm.list_all(category=category, limit=limit, offset=offset,
                            scope=scope, context_id=context_id,
                            scope_only=scope_only),
    }


@router.get("/top")
def get_top_memories(query: str = Query("", max_length=500),
                     max_count: int = Query(5, ge=1, le=20),
                     db: Session = Depends(get_db)):
    """获取应注入上下文的 Top-N 记忆"""
    mm = MemoryManager(db)
    return {
        "success": True,
        "data": mm.get_top_for_context(query=query, max_count=max_count),
    }


@router.post("")
def create_memory(body: MemoryCreate, db: Session = Depends(get_db)):
    """创建新记忆（带内容去重）"""
    mm = MemoryManager(db)
    # 检查 key 是否已存在
    existing = mm.get(body.key)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"记忆 '{body.key}' 已存在，使用 PUT 更新"
        )
    # 🆕 内容查重 — 防止相似记忆重复创建
    similar = mm.find_similar_content(body.content, threshold=0.50)
    if similar:
        # 相似已存在 → 强化权重，不创建新条目
        mm.reinforce(similar.key)
        return {
            "success": True,
            "action": "reinforced",
            "message": f"相似记忆已存在（{similar.key}），已强化权重",
            "data": {"id": similar.id, "key": similar.key},
        }
    mem = mm.add(
        category=body.category,
        key=body.key,
        content=body.content,
        tags=body.tags,
        base_weight=body.base_weight,
        source=body.source,
        is_narrative=body.is_narrative,
    )
    return {"success": True, "data": {"id": mem.id, "key": mem.key}}


@router.get("/{key}")
def get_memory(key: str, db: Session = Depends(get_db)):
    """按 key 查看记忆详情"""
    mm = MemoryManager(db)
    mem = mm.get(key)
    if not mem:
        raise HTTPException(status_code=404, detail=f"记忆 '{key}' 不存在")
    # 获取实时权重
    from models import AgentMemory
    d = mm._to_dict(mem)
    d["weight"] = round(mm.calc_weight(mem), 2)
    return {"success": True, "data": d}


@router.put("/{key}")
def update_memory(key: str, body: MemoryUpdate, db: Session = Depends(get_db)):
    """更新记忆"""
    mm = MemoryManager(db)
    existing = mm.get(key)
    if not existing:
        raise HTTPException(status_code=404, detail=f"记忆 '{key}' 不存在")
    kwargs = {}
    if body.content is not None:
        kwargs["content"] = body.content
    if body.tags is not None:
        kwargs["tags"] = body.tags
    if body.base_weight is not None:
        kwargs["base_weight"] = body.base_weight
    if body.category is not None:
        kwargs["category"] = body.category
    mm.update(key, **kwargs)
    return {"success": True, "message": f"记忆 '{key}' 已更新"}


@router.delete("/{key}")
def delete_memory(key: str, db: Session = Depends(get_db)):
    """删除记忆"""
    mm = MemoryManager(db)
    ok = mm.delete(key)
    if not ok:
        raise HTTPException(status_code=404, detail=f"记忆 '{key}' 不存在")
    return {"success": True, "message": f"记忆 '{key}' 已删除"}


@router.post("/{key}/reinforce")
def reinforce_memory(key: str, db: Session = Depends(get_db)):
    """强化记忆 — 用户反复提及的主题，权重 ×2"""
    mm = MemoryManager(db)
    ok = mm.reinforce(key)
    if not ok:
        raise HTTPException(status_code=404, detail=f"记忆 '{key}' 不存在")
    return {"success": True, "message": f"记忆 '{key}' 已强化"}


@router.post("/{key}/pin")
def pin_memory(key: str, db: Session = Depends(get_db)):
    """标记为 P0 — 用户要求永久保留"""
    mm = MemoryManager(db)
    ok = mm.update(key, base_weight=8)
    if not ok:
        raise HTTPException(status_code=404, detail=f"记忆 '{key}' 不存在")
    return {"success": True, "message": f"记忆 '{key}' 已标记为 P0（永不过期）"}


@router.post("/semantic-dedup")
def semantic_dedup_memories(db: Session = Depends(get_db),
                             dry_run: bool = Query(False, description="模拟运行，不执行删除")):
    """语义去重 — LLM 判断哪些记忆内容重复，合并到权重最高的那条

    按 scope+context_id 分组，每组内用 LLM 判断语义相似度。
    相似组内保留权重最高的，删除其他，合并标签。
    """
    from models import AgentMemory
    from sqlalchemy import func

    mm = MemoryManager(db)

    # 按 scope+context_id 分组
    rows = (
        db.query(
            AgentMemory.scope,
            AgentMemory.context_id,
        )
        .group_by(AgentMemory.scope, AgentMemory.context_id)
        .all()
    )

    total_deleted = 0
    total_kept = 0
    groups_analyzed = 0
    merge_log = []

    for row in rows:
        mems = db.query(AgentMemory).filter(
            AgentMemory.scope == row.scope,
            AgentMemory.context_id == row.context_id,
        ).all()

        if len(mems) < 2:
            continue

        # 格式化给 LLM
        items = []
        for m in mems:
            w = mm.calc_weight(m)
            items.append({"id": m.id, "key": m.key, "content": m.content, "tags": m.tags or [], "weight": round(w, 2)})

        # 调 LLM 判断语义分组
        merged = _semantic_dedup_group(items)
        if not merged:
            continue

        groups_analyzed += 1
        for group in merged:
            if len(group) < 2:
                continue
            # 按权重降序，保留第一个
            group.sort(key=lambda x: -x["weight"])
            primary = group[0]
            dups = group[1:]

            # 合并标签
            all_tags = set(primary.get("tags", []))
            for d in dups:
                all_tags.update(d.get("tags", []))
            keep_mem = db.query(AgentMemory).filter(AgentMemory.id == primary["id"]).first()
            if keep_mem:
                keep_mem.tags = list(all_tags)

            # 删除重复
            for d in dups:
                dup_mem = db.query(AgentMemory).filter(AgentMemory.id == d["id"]).first()
                if dup_mem:
                    if not dry_run:
                        db.delete(dup_mem)
                    total_deleted += 1
                total_kept += 1

            merge_log.append({
                "kept": primary["key"],
                "kept_content": primary["content"][:60],
                "deleted_count": len(dups),
                "deleted_keys": [d["key"] for d in dups],
            })

    if not dry_run:
        db.commit()

    return {
        "success": True,
        "groups_analyzed": groups_analyzed,
        "kept": total_kept,
        "deleted": total_deleted,
        "dry_run": dry_run,
        "merges": merge_log,
    }


_SEMANTIC_DEDUP_PROMPT = (
    "你是一个记忆品控助手。以下是同一来源的多条记忆，请找出其中语义重复的内容进行分组。\n\n"
    "分组规则：\n"
    "- 如果两条记忆在说同一件事、同一信息，只是表达方式不同 -> 分到同一组\n"
    "  ✅ 同组: '用户有30万资金' 和 '用户拥有30万启动资金'\n"
    "  ✅ 同组: '用户叫张清泉' 和 '用户名为张清泉'\n"
    "  ✅ 同组: '预算22万用于购车' 和 '购车预算22万元'\n"
    "  ❌ 不同组: '用户有30万资金' 和 '用户有3个停车车位'（不同信息）\n"
    "- 一条包含多条信息的宽泛记忆，如果其他单条是其子集，也算重复\n"
    "  ✅ 同组: '用户张清泉，30万资金，3个车位' 和 '用户有30万资金'\n"
    "- 每条记忆只分到一个组\n\n"
    "返回格式：按序号分组，每组是一个数组\n"
    "示例：[[1, 3], [2, 5, 7]] 表示记忆 1 和 3 重复，2、5 和 7 重复\n"
    "如果没有重复，返回空数组 []。\n"
    "只返回 JSON 数字数组，不要其他文字。"
)


def _semantic_dedup_group(items: list[dict]) -> list[list[dict]]:
    """调本地 LLM 做语义去重分组

    LLM 返回按 1-based 序号的分组：[[1, 3], [2, 5, 7]]
    """
    if not items or len(items) < 2:
        return []

    # 格式化输入
    lines = ["# 记忆列表"]
    for i, item in enumerate(items):
        lines.append(f"{i+1}. [{item['key']}] {item['content']}")
    text = "\n".join(lines)

    try:
        import requests
        payload = {
            "model": "qwen3.5-q4",
            "messages": [
                {"role": "system", "content": _SEMANTIC_DEDUP_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }
        resp = requests.post("http://localhost:8083/v1/chat/completions", json=payload, timeout=30)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[semantic-dedup] LLM 调用失败: {e}")
        return []

    # 解析 JSON 数字数组
    raw = raw.strip()
    if raw.startswith("```"):
        start = raw.find("\n")
        end = raw.rfind("```")
        if start != -1 and end != -1:
            raw = raw[start:end].strip()
    if not raw.startswith("["):
        return []

    try:
        import json
        groups = json.loads(raw)
        if not isinstance(groups, list):
            return []

        result = []
        used_indices = set()
        for g in groups:
            if not isinstance(g, list) or len(g) < 2:
                continue
            # 转为 0-based 并查 items
            idxs = sorted(set(
                int(x) - 1 for x in g
                if isinstance(x, (int, float)) and 1 <= int(x) <= len(items)
            ))
            if len(idxs) < 2:
                continue
            if any(i in used_indices for i in idxs):
                # 跳过已分配的条目
                idxs = [i for i in idxs if i not in used_indices]
                if len(idxs) < 2:
                    continue
            for i in idxs:
                used_indices.add(i)
            result.append([items[i] for i in idxs])

        return result
    except Exception:
        return []


class AutoExtractRequest(BaseModel):
    messages: list[dict] = Field(..., description="本轮对话的消息列表")


@router.post("/auto-extract")
def auto_extract(body: AutoExtractRequest, db: Session = Depends(get_db)):
    """从对话中自动提取记忆

    扫描本轮对话，检测三种模式：
    1. 显式标记（"记住"、"很重要"）→ 创建/强化，×3
    2. 用户纠正（"不是A是B"）→ 更新记忆，×2
    3. 重复主题（同一话题3次+）→ 强化，×2
    """
    mm = MemoryManager(db)
    results = mm.auto_extract_from_conversation(body.messages)
    return {"success": True, "data": results}


@router.post("/dedup")
def dedup_memories(threshold: float = Query(0.50, ge=0.3, le=1.0),
                   db: Session = Depends(get_db)):
    """扫描并合并重复记忆 — 基于 Jaccard 相似度

    每组相似记忆中保留权重最高的，删除其他，合并标签。
    """
    from models import AgentMemory
    mm = MemoryManager(db)
    mems = db.query(AgentMemory).all()
    if not mems:
        return {"success": True, "message": "无记忆", "deleted": 0, "kept": 0}

    import re
    def token_set(content: str) -> set:
        return set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', content or ""))

    scored = [(mm.calc_weight(m), m) for m in mems]
    scored.sort(key=lambda x: -x[0])  # 高权重在前

    deleted = 0
    kept = 0
    used = set()  # 已处理的 ID

    for w, m in scored:
        if m.id in used:
            continue
        m_tokens = token_set(m.content)
        if not m_tokens:
            used.add(m.id)
            continue
        used.add(m.id)
        group = [m]

        # 找相似记忆
        for w2, m2 in scored:
            if m2.id in used:
                continue
            m2_tokens = token_set(m2.content)
            if not m2_tokens:
                continue
            intersection = m_tokens & m2_tokens
            union = m_tokens | m2_tokens
            score = len(intersection) / len(union)
            if score >= threshold:
                group.append(m2)
                used.add(m2.id)

        # 保留第一个（权重最高），删除其他
        primary = group[0]
        kept += 1
        for dup in group[1:]:
            # 合并标签
            if dup.tags and primary.tags:
                primary.tags = list(set(primary.tags + dup.tags))
            db.delete(dup)
            deleted += 1

    db.commit()
    return {
        "success": True,
        "message": f"合并完成：保留 {kept} 条，删除 {deleted} 条重复",
        "kept": kept,
        "deleted": deleted,
    }
