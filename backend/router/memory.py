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

router = APIRouter(prefix="/api/memory", tags=["memory"])


# ── Schemas ──

class MemoryCreate(BaseModel):
    category: str = Field("user", description="user | agent")
    key: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    base_weight: int = Field(default=2, ge=1, le=10)
    source: str = Field(default="user", description="auto | llm | user")


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
                  offset: int = Query(0, ge=0)):
    """列出所有记忆（按实时权重降序）"""
    mm = MemoryManager(db)
    return {
        "success": True,
        "data": mm.list_all(category=category, limit=limit, offset=offset),
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
    """创建新记忆"""
    mm = MemoryManager(db)
    # 检查是否已存在
    existing = mm.get(body.key)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"记忆 '{body.key}' 已存在，使用 PUT 更新"
        )
    mem = mm.add(
        category=body.category,
        key=body.key,
        content=body.content,
        tags=body.tags,
        base_weight=body.base_weight,
        source=body.source,
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
