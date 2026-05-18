"""技能系统 API — CRUD + 触发器匹配

端点:
    GET    /api/skills              — 列表（全部 skill 元信息）
    GET    /api/skills/{name}       — 查看 skill 完整内容
    POST   /api/skills              — 创建 skill
    PUT    /api/skills/{name}       — 更新 skill
    DELETE /api/skills/{name}       — 删除 skill
    GET    /api/skills/match        — 按用户查询匹配相关 skill
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from agent_core.skill_manager import SkillManager

router = APIRouter(prefix="/api/skills", tags=["skills"])

sm = SkillManager()  # 单例，文件级缓存


# ── Schemas ──

class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-z0-9_-]+$')
    description: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    triggers: list[str] = Field(default_factory=list)
    category: str = Field(default="general", max_length=32)
    version: str = Field(default="1.0")


class SkillUpdate(BaseModel):
    description: Optional[str] = None
    content: Optional[str] = None
    triggers: Optional[list[str]] = None
    category: Optional[str] = None
    version: Optional[str] = None


# ── 端点 ──

@router.get("")
def list_skills(category: Optional[str] = Query(None)):
    """列出所有 skill（仅元信息，不含正文）"""
    skills = sm.list_all()
    if category:
        skills = [s for s in skills if s.get("category") == category]
    return {"success": True, "data": skills}


@router.get("/match")
def match_skills(query: str = Query(..., min_length=1, max_length=500),
                 max_count: int = Query(2, ge=1, le=10)):
    """按用户查询匹配相关 skill（触发器匹配）"""
    matched = sm.match_for_context(query, max_count=max_count)
    return {
        "success": True,
        "data": [s.to_dict(include_content=False) for s in matched],
    }


@router.get("/{name}")
def get_skill(name: str):
    """查看 skill 完整内容"""
    skill = sm.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 不存在")
    return {"success": True, "data": skill.to_dict(include_content=True)}


@router.post("")
def create_skill(body: SkillCreate):
    """创建新 skill"""
    existing = sm.get(body.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Skill '{body.name}' 已存在，使用 PUT 更新"
        )
    skill = sm.create(
        name=body.name,
        description=body.description,
        content=body.content,
        triggers=body.triggers,
        category=body.category,
        version=body.version,
    )
    return {"success": True, "data": skill.to_dict(include_content=False)}


@router.put("/{name}")
def update_skill(name: str, body: SkillUpdate):
    """更新 skill"""
    existing = sm.get(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 不存在")
    kwargs = {}
    if body.description is not None:
        kwargs["description"] = body.description
    if body.content is not None:
        kwargs["content"] = body.content
    if body.triggers is not None:
        kwargs["triggers"] = body.triggers
    if body.category is not None:
        kwargs["category"] = body.category
    if body.version is not None:
        kwargs["version"] = body.version
    sm.update(name, **kwargs)
    return {"success": True, "message": f"Skill '{name}' 已更新"}


@router.delete("/{name}")
def delete_skill(name: str):
    """删除 skill"""
    ok = sm.delete(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 不存在")
    return {"success": True, "message": f"Skill '{name}' 已删除"}


# ── 分类管理 ──


class CategoryRename(BaseModel):
    old_name: str = Field(..., min_length=1, max_length=64)
    new_name: str = Field(..., min_length=1, max_length=64)


@router.get("/categories")
def list_categories():
    """列出所有分类及数量、是否受保护"""
    return {"success": True, "data": sm.list_categories()}


@router.put("/categories/rename")
def rename_category(body: CategoryRename):
    """重命名分类（批量更新所有同分类技能）"""
    protected = {"development", "reference", "formatting", "workflow", "general"}
    if body.old_name in protected:
        raise HTTPException(status_code=403, detail=f"默认分类 '{body.old_name}' 不可重命名")
    count = sm.rename_category(body.old_name, body.new_name)
    return {"success": True, "message": f"已重命名 {count} 个技能", "count": count}
