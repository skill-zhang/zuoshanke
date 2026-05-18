"""工具 CRUD API — 注册/查看/更新/注销工具 + 预执行 + SKILL.md 管理

端点:
    GET    /api/tools                    — 列出所有工具
    POST   /api/tools                    — 注册新工具
    GET    /api/tools/{name}             — 查看工具详情（含 SKILL.md）
    PUT    /api/tools/{name}             — 更新工具配置
    DELETE /api/tools/{name}             — 注销工具
    PUT    /api/tools/{name}/preexecute  — 管理预执行配置
    GET    /api/tools/{name}/skill       — 读取 SKILL.md
    PUT    /api/tools/{name}/skill       — 写入 SKILL.md
    DELETE /api/tools/{name}/skill       — 删除 SKILL.md
"""
import json
import os
import shutil

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(prefix="/api/tools", tags=["tools"])

# ── 路径 ──
from config.paths import TOOLS_DIR

REGISTRY_PATH = os.path.join(TOOLS_DIR, "registry.json")


# ── 工具与参数模型 ──

class ParamDef(BaseModel):
    name: str
    type: str = "string"
    required: bool = True
    description: str = ""


class PreexecuteConfig(BaseModel):
    enabled: bool = False
    triggers: list[str] = Field(default_factory=list)
    requires_city: bool = False


class ToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9_]*$')
    description: str = Field(..., min_length=1, max_length=200)
    file: str = Field(..., min_length=1)
    function: str = Field(..., min_length=1)
    parameters: list[ParamDef] = Field(default_factory=list)
    returns: str = ""
    category: str = Field(default="data", max_length=32)
    verified: bool = False
    preexecute: PreexecuteConfig = Field(default_factory=PreexecuteConfig)


class ToolUpdate(BaseModel):
    description: Optional[str] = None
    file: Optional[str] = None
    function: Optional[str] = None
    parameters: Optional[list[ParamDef]] = None
    returns: Optional[str] = None
    category: Optional[str] = None
    verified: Optional[bool] = None


class PreexecuteUpdate(BaseModel):
    enabled: Optional[bool] = None
    triggers: Optional[list[str]] = None
    requires_city: Optional[bool] = None


class SkillContent(BaseModel):
    content: str = Field(..., min_length=0)


# ── 内部工具 ──

def _load_registry() -> list[dict]:
    """读取 registry.json"""
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tools", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_registry(tools: list[dict]):
    """写入 registry.json"""
    os.makedirs(TOOLS_DIR, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump({"tools": tools}, f, ensure_ascii=False, indent=2)


def _param_to_dict(p: ParamDef) -> dict:
    d = {"type": p.type, "description": p.description}
    if not p.required:
        d["optional"] = True
    return d


def _param_from_dict(name: str, pd: dict) -> dict:
    return {
        "name": name,
        "type": pd.get("type", "string"),
        "required": not pd.get("optional", False),
        "description": pd.get("description", ""),
    }


def _tool_to_summary(t: dict) -> dict:
    """工具列表用的摘要信息"""
    params = t.get("parameters", {})
    pre = t.get("preexecute", {})
    skill_path = os.path.join(TOOLS_DIR, t["name"], "SKILL.md")
    return {
        "name": t["name"],
        "description": t.get("description", ""),
        "category": t.get("category", "data"),
        "verified": t.get("verified", False),
        "params_count": len(params) if isinstance(params, dict) else 0,
        "preexecute_enabled": pre.get("enabled", False) if isinstance(pre, dict) else False,
        "preexecute_triggers_count": len(pre.get("triggers", [])) if isinstance(pre, dict) else 0,
        "has_skill": os.path.isfile(skill_path),
    }


def _tool_to_detail(t: dict) -> dict:
    """工具完整详情"""
    params_raw = t.get("parameters", {})
    pre = t.get("preexecute", {})
    skill_path = os.path.join(TOOLS_DIR, t["name"], "SKILL.md")

    # 参数统一格式
    if isinstance(params_raw, list):
        params = params_raw
    elif isinstance(params_raw, dict):
        params = [_param_from_dict(k, v) for k, v in params_raw.items()]
    else:
        params = []

    # 读取 SKILL.md
    skill_content = None
    if os.path.isfile(skill_path):
        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                skill_content = f.read()
        except Exception:
            skill_content = None

    return {
        "name": t["name"],
        "description": t.get("description", ""),
        "file": t.get("file", ""),
        "function": t.get("function", ""),
        "parameters": params,
        "returns": t.get("returns", ""),
        "category": t.get("category", "data"),
        "verified": t.get("verified", False),
        "preexecute": {
            "enabled": pre.get("enabled", False) if isinstance(pre, dict) else False,
            "triggers": pre.get("triggers", []) if isinstance(pre, dict) else [],
            "requires_city": pre.get("requires_city", False) if isinstance(pre, dict) else False,
        },
        "has_skill": os.path.isfile(skill_path),
        "skill_content": skill_content,
    }


def _find_tool(tools: list[dict], name: str) -> Optional[dict]:
    for t in tools:
        if t.get("name") == name:
            return t
    return None


# ── API 端点 ──


@router.get("")
def list_tools(category: Optional[str] = Query(None)):
    """列出所有工具（摘要信息，不含正文）"""
    tools = _load_registry()
    result = [_tool_to_summary(t) for t in tools]

    if category:
        result = [t for t in result if t["category"] == category]

    return {"success": True, "data": result}


@router.get("/{name}")
def get_tool(name: str):
    """查看工具完整详情"""
    tools = _load_registry()
    t = _find_tool(tools, name)
    if not t:
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 不存在")
    return {"success": True, "data": _tool_to_detail(t)}


@router.post("")
def create_tool(body: ToolCreate):
    """注册新工具"""
    tools = _load_registry()

    if _find_tool(tools, body.name):
        raise HTTPException(status_code=409, detail=f"工具 '{body.name}' 已存在")

    # 构建参数 dict
    params_dict = {}
    for p in body.parameters:
        params_dict[p.name] = _param_to_dict(p)

    entry = {
        "name": body.name,
        "description": body.description,
        "file": body.file,
        "function": body.function,
        "parameters": params_dict,
        "returns": body.returns,
        "category": body.category,
        "verified": body.verified,
        "preexecute": {
            "enabled": body.preexecute.enabled,
            "triggers": body.preexecute.triggers,
            "requires_city": body.preexecute.requires_city,
        },
    }

    tools.append(entry)
    _save_registry(tools)

    # 加载后返回详情
    return {"success": True, "data": _tool_to_detail(entry)}


@router.put("/{name}")
def update_tool(name: str, body: ToolUpdate):
    """更新工具配置"""
    tools = _load_registry()
    t = _find_tool(tools, name)
    if not t:
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 不存在")

    if body.description is not None:
        t["description"] = body.description
    if body.file is not None:
        t["file"] = body.file
    if body.function is not None:
        t["function"] = body.function
    if body.category is not None:
        t["category"] = body.category
    if body.verified is not None:
        t["verified"] = body.verified
    if body.returns is not None:
        t["returns"] = body.returns

    if body.parameters is not None:
        params_dict = {}
        for p in body.parameters:
            params_dict[p.name] = _param_to_dict(p)
        t["parameters"] = params_dict

    _save_registry(tools)
    return {"success": True, "data": _tool_to_detail(t)}


@router.delete("/{name}")
def delete_tool(name: str):
    """注销工具（从 registry 移除，可选保留 SKILL.md）"""
    tools = _load_registry()
    t = _find_tool(tools, name)
    if not t:
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 不存在")

    tools = [x for x in tools if x.get("name") != name]
    _save_registry(tools)

    return {"success": True, "message": f"工具 '{name}' 已注销"}


@router.put("/{name}/preexecute")
def update_preexecute(name: str, body: PreexecuteUpdate):
    """管理工具的预执行配置"""
    tools = _load_registry()
    t = _find_tool(tools, name)
    if not t:
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 不存在")

    pre = t.setdefault("preexecute", {})
    if body.enabled is not None:
        pre["enabled"] = body.enabled
    if body.triggers is not None:
        pre["triggers"] = body.triggers
    if body.requires_city is not None:
        pre["requires_city"] = body.requires_city

    _save_registry(tools)
    return {"success": True, "data": _tool_to_detail(t)}


# ── SKILL.md 管理 ──


@router.get("/{name}/skill")
def get_tool_skill(name: str):
    """读取工具的 SKILL.md"""
    skill_path = os.path.join(TOOLS_DIR, name, "SKILL.md")
    if not os.path.isfile(skill_path):
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 的使用手册不存在")
    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"success": True, "data": {"name": name, "content": content}}


@router.put("/{name}/skill")
def put_tool_skill(name: str, body: SkillContent):
    """创建或更新工具的 SKILL.md"""
    tool_dir = os.path.join(TOOLS_DIR, name)
    os.makedirs(tool_dir, exist_ok=True)
    skill_path = os.path.join(tool_dir, "SKILL.md")
    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(body.content)
    return {"success": True, "message": f"工具 '{name}' 的使用手册已保存"}


@router.delete("/{name}/skill")
def delete_tool_skill(name: str):
    """删除工具的 SKILL.md"""
    skill_path = os.path.join(TOOLS_DIR, name, "SKILL.md")
    if not os.path.isfile(skill_path):
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 的使用手册不存在")
    os.remove(skill_path)
    return {"success": True, "message": f"工具 '{name}' 的使用手册已删除"}
