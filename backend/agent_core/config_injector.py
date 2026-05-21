"""
Config 注入器 — 配置层叠与注入

从 ConfigEntry 表按层叠顺序加载配置：
  本体配置 → 分身配置 → scene 配置 → session 临时覆写

只注入当前生效的层叠结果，不是完整 yaml。
"""

from typing import Optional


def get_cascade(scene_id: str = "", db=None) -> dict:
    """获取当前生效的配置层叠结果

    Args:
        scene_id: 场景 ID
        db: 数据库会话

    Returns:
        层叠后的配置字典
    """
    result = {}

    if db is None:
        return result

    # 1. 模型配置（系统级）
    try:
        from models import ConfigEntry
        for entry in db.query(ConfigEntry).filter(
            ConfigEntry.category.in_(["system", "model"])
        ).all():
            _merge_config(result, entry.config_name, entry.content)
    except Exception:
        pass

    # 2. 场景级配置（从 scene 表
    if scene_id:
        try:
            from models import Scene
            scene = db.query(Scene).filter(Scene.id == scene_id).first()
            if scene:
                # 收敛参数
                if scene.converge_threshold is not None:
                    result["converge_threshold"] = scene.converge_threshold
                if scene.converge_enabled is not None:
                    result["converge_enabled"] = scene.converge_enabled
                if scene.diverge_min_rounds is not None:
                    result["diverge_min_rounds"] = scene.diverge_min_rounds
                # 场景自定义设定
                if scene.user_context:
                    result["user_context"] = scene.user_context
        except Exception:
            pass

    # 3. 服务级配置（按场景匹配）
    try:
        from models import ConfigEntry
        for entry in db.query(ConfigEntry).filter(
            ConfigEntry.category == "service"
        ).all():
            # 服务配置只有在相关时注入，这里先不自动注入
            pass
    except Exception:
        pass

    return result


def format_config_block(config: dict, scene_name: str = "") -> str:
    """将配置字典格式化为注入文本"""
    if not config:
        return ""

    lines = ["## 当前运行配置"]
    for key, value in config.items():
        lines.append(f"- {key}: {value}")

    return "\n".join(lines)


def _merge_config(target: dict, key: str, value_str: str) -> None:
    """合并配置到目标字典"""
    try:
        import json
        parsed = json.loads(value_str)
        if isinstance(parsed, dict):
            target.update(parsed)
        else:
            target[key] = parsed
    except (json.JSONDecodeError, TypeError):
        target[key] = value_str
