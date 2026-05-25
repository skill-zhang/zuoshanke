"""Prompt 加载器 — 频道/场景的 system prompt 统一入口

策略（优先级递减）:
  1. DB settings.system_prompts（用户通过 Settings UI 自定义）
  2. config/prompts.json（后台配置文件，开发者编辑）

默认模板真源: config/default-prompts.md
  此文件是频道/场景人设的唯一默认模板来源。
  models.py 和前端 SettingsView 均通过此模块读取，
  不再有硬编码副本。
"""

import json
import os
import re
from typing import Optional

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "prompts.json")
_DEFAULT_MD_PATH = os.path.join(os.path.dirname(__file__), "config", "default-prompts.md")


def load_default_prompts() -> dict[str, str]:
    """从 config/default-prompts.md 读取默认频道/场景人设模板

    解析规则: 按 '## channel' 和 '## scene' 二级标题分段，
    取标题后到下一个二级标题之间的文本（去除开头的空行）。

    Returns:
        {"channel": "...", "scene": "..."}
    """
    try:
        with open(_DEFAULT_MD_PATH, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {
            "channel": "你是坐山客（Zuoshanke），以广博学识和理性思维为用户提供帮助。",
            "scene": "你是坐山客在某个领域的专业分身，是用户的AI工作伙伴。",
        }

    result = {}
    # 匹配 ## channel 或 ## scene，捕获标题后的文本直到下一个 ## 或文件末尾
    pattern = r"^## (channel|scene)\s*\n(.*?)(?=\n## |\Z)"
    for match in re.finditer(pattern, text, re.MULTILINE | re.DOTALL):
        key = match.group(1)
        content = match.group(2).strip()
        result[key] = content

    return result


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_channel_prompt(is_default: bool = False, db=None) -> str:
    """获取频道 system prompt。"""
    # 1. 用户自定义（DB）
    if db is not None:
        try:
            from models import Setting
            setting = db.query(Setting).first()
            if setting and setting.system_prompts:
                val = setting.system_prompts.get("channel")
                if val and val.strip():
                    return val.strip()
        except Exception:
            pass
    # 2. 后台配置
    cfg = _load_config()
    key = "channel_default" if is_default else "channel_generic"
    return cfg.get(key, "")
