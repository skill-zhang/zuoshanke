"""工具 SKILL.md 读取"""
import os

from fastapi import APIRouter, HTTPException
from config.paths import TOOLS_DIR

router = APIRouter(tags=["工具"])


@router.get("/api/tools/{tool_name}/skill")
def get_tool_skill(tool_name: str):
    """读取工具的 SKILL.md 原文"""
    skill_path = os.path.join(TOOLS_DIR, tool_name, "SKILL.md")
    if not os.path.isfile(skill_path):
        raise HTTPException(404, f"工具 '{tool_name}' 的文档不存在")
    with open(skill_path) as f:
        content = f.read()
    return {"name": tool_name, "content": content}
