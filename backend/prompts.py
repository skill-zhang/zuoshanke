"""Prompt 加载器 — 频道/场景的 system prompt 统一入口

策略（优先级递减）:
  1. DB settings.system_prompts（用户通过 Settings UI 自定义）
  2. config/prompts.json（后台配置文件，开发者编辑）
"""

import json
import os
from typing import Optional

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "prompts.json")


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
