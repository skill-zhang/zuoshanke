"""memory_tool — LLM 自主管理的长期记忆工具

Agent Loop 通过此工具实现对记忆中"自主存取改查"的能力。
不再依赖后台规则匹配或自动提取，而是由 LLM 在对话中判断"这条信息值得记住"后主动调用。

四个动作：
  - add:   存新信息（自动去重，已存在则强化）
  - read:  查看当前所有记忆
  - replace: 更新已有记忆
  - remove: 删除记忆

用法:
    memory_tool(action="add", target="user", content="用户喜欢冷色系")
    memory_tool(action="read", target="memory")
    memory_tool(action="replace", target="memory", old_text="冷色", content="用户喜欢暖色系")
    memory_tool(action="remove", target="memory", old_text="旧内容")
"""

import json
import logging
import sys
import os

# 把 backend 目录加入 path，以便 import database / agent_core
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

logger = logging.getLogger(__name__)

# ── 数据库连接 ──
from database import SessionLocal
from agent_core.memory_manager import MemoryManager


def _get_mm() -> MemoryManager:
    """创建带独立 DB session 的 MemoryManager 实例"""
    db = SessionLocal()
    return MemoryManager(db)


def _cleanup(mm: MemoryManager):
    """关闭 MemoryManager 的 DB session"""
    try:
        mm.db.close()
    except Exception:
        pass


def memory_tool(
    action: str,
    target: str = "memory",
    content: str = None,
    old_text: str = None,
    key: str = None,
    scope: str = None,       # 🆕 zhu | scene | channel，不传则自动推断
) -> str:
    """管理长期记忆

    Args:
        action: 操作类型 — add(新增), read(查看), replace(更新), remove(删除)
        target: 记忆目标 — "memory"(系统笔记) / "user"(用户画像)
        content: 记忆内容（add/replace 时必须）
        old_text: 要替换或删除的旧记忆文本片段（replace/remove 时必须）
        key: 可选，记忆的唯一标识键。不传则自动生成
        scope: 🆕 记忆作用域(zhu|scene|channel)，不传则自动推断当前上下文

    Returns:
        JSON 字符串，含操作结果
    """
    if action not in ("add", "reinforce", "read", "replace", "remove"):
        return json.dumps({"success": False, "error": f"不支持的 action: {action}"}, ensure_ascii=False)

    if target not in ("memory", "user"):
        return json.dumps({"success": False, "error": f"不支持的 target: {target}，请用 'memory' 或 'user'"}, ensure_ascii=False)

    # 🆕 自动推断 scope + context_id
    from agent_core.tool_executor import get_tool_context
    ctx = get_tool_context()
    if scope is None:
        if ctx.get("scene_id"):
            scope = "scene"
            context_id = ctx["scene_id"]
        elif ctx.get("channel_id"):
            scope = "channel"
            context_id = ctx["channel_id"]
        else:
            scope = "zhu"
            context_id = None
    else:
        context_id = ctx.get("scene_id") or ctx.get("channel_id") or None
        if scope == "scene":
            context_id = ctx.get("scene_id") or context_id
        elif scope == "channel":
            context_id = ctx.get("channel_id") or context_id

    # 🆕 安全校验：分身不能写 zhu
    if scope == "zhu" and (ctx.get("scene_id") or ctx.get("channel_id")):
        return json.dumps({
            "success": False,
            "error": "分身不能直接写入本体记忆（scope=zhu）。"
                     "如需将此信息存储为本体记忆，请在闲聊频道或仪表盘中提及。"
        }, ensure_ascii=False)

    try:
        mm = _get_mm()
    except Exception as e:
        return json.dumps({"success": False, "error": f"数据库连接失败: {e}"}, ensure_ascii=False)

    try:
        if action == "add":
            return _handle_add(mm, target, content, key, scope=scope, context_id=context_id)
        elif action == "reinforce":
            return _handle_reinforce(mm, target, old_text, key)
        elif action == "read":
            return _handle_read(mm, target)
        elif action == "replace":
            return _handle_replace(mm, target, old_text, content, key)
        elif action == "remove":
            return _handle_remove(mm, target, old_text)
    finally:
        _cleanup(mm)


# ── 内部处理 ──


def _handle_add(mm: MemoryManager, target: str, content: str, key: str = None,
                scope: str = "zhu", context_id: str = None) -> str:
    """新增记忆 — 自动去重（检查内容相似度）"""
    if not content or not content.strip():
        return json.dumps({"success": False, "error": "content 不能为空"}, ensure_ascii=False)

    content = content.strip()

    # 检查内容是否已存在（Jaccard 相似度 + 作用域感知）
    existing = _find_existing_by_content(mm, content, scope=scope, context_id=context_id)
    if existing:
        # 已存在 → 强化权重，不创建新条目
        mm.reinforce(existing.key)
        _log_extraction(target, f"原有记忆强化（跳过创建→{existing.key}）")
        return json.dumps({
            "success": True,
            "action": "reinforced",
            "message": f"该记忆已存在（key={existing.key}），已强化权重",
            "key": existing.key,
            "content": existing.content,
        }, ensure_ascii=False)

    # 自动生成 key
    if not key:
        key = _auto_key(content, target)

    # 检查 key 是否已存在
    existing_by_key = mm.get(key)
    if existing_by_key:
        # key 已存在 → 更新内容 + 强化
        mm.update(key, content=content)
        mm.reinforce(key)
        _log_extraction(target, f"已更新+强化 key={key}")
        return json.dumps({
            "success": True,
            "action": "updated",
            "message": f"key={key} 已存在，已更新内容并强化",
            "key": key,
            "content": content,
        }, ensure_ascii=False)

    # 新建
    try:
        category = target  # "memory" 或 "user" 对应 category
        mm.add(category, key, content, tags=[_infer_topic(content)], source="llm",
               base_weight=3, scope=scope, context_id=context_id)
        _log_extraction(target, f"新建记忆 key={key} scope={scope}")
        return json.dumps({
            "success": True,
            "action": "created",
            "message": f"记忆已保存（key={key}）",
            "key": key,
            "content": content,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"保存失败: {e}"}, ensure_ascii=False)


def _handle_reinforce(mm: MemoryManager, target: str, old_text: str = None, key: str = None) -> str:
    """强化已有记忆的权重（用户强调或纠正时调用）"""
    if key:
        # 按 key 精确匹配
        if mm.reinforce(key):
            return json.dumps({"success": True, "action": "reinforced", "key": key, "message": f"key={key} 已强化"}, ensure_ascii=False)
        return json.dumps({"success": False, "error": f"未找到 key={key}"}, ensure_ascii=False)

    if old_text:
        # 内容模糊匹配
        matched = _find_by_text_match(mm, target, old_text)
        if not matched:
            return json.dumps({"success": False, "error": f"未找到包含「{old_text}」的记忆"}, ensure_ascii=False)
        if len(matched) > 1:
            previews = [m["content"][:60] for m in matched]
            return json.dumps({"success": False, "error": f"多条记忆匹配，请更具体或指定 key", "matches": previews}, ensure_ascii=False)
        m = matched[0]
        mm.reinforce(m["key"])
        return json.dumps({"success": True, "action": "reinforced", "key": m["key"], "message": f"已强化包含「{old_text}」的记忆"}, ensure_ascii=False)

    return json.dumps({"success": False, "error": "reinforce 需要 key 或 old_text"}, ensure_ascii=False)


def _handle_read(mm: MemoryManager, target: str) -> str:
    """读取记忆列表"""
    try:
        entries = mm.list_all(category=target if target != "all" else None, limit=100)
        if not entries:
            return json.dumps({
                "success": True,
                "target": target,
                "entries": [],
                "count": 0,
                "message": f"{target} 暂无记忆",
            }, ensure_ascii=False)

        # 格式化返回
        formatted = []
        for e in entries:
            formatted.append({
                "key": e["key"],
                "content": e["content"],
                "level": e["priority_level"],
                "weight": e.get("weight", 0),
                "tags": e.get("tags", []),
            })

        return json.dumps({
            "success": True,
            "target": target,
            "entries": formatted,
            "count": len(formatted),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"读取失败: {e}"}, ensure_ascii=False)


def _handle_replace(mm: MemoryManager, target: str, old_text: str, content: str, key: str = None) -> str:
    """替换记忆"""
    if not old_text or not old_text.strip():
        return json.dumps({"success": False, "error": "old_text 不能为空"}, ensure_ascii=False)
    if not content or not content.strip():
        return json.dumps({"success": False, "error": "content 不能为空"}, ensure_ascii=False)

    old_text = old_text.strip()
    content = content.strip()

    # 如果有 key，直接 key 定位
    if key:
        existing = mm.get(key)
        if existing:
            mm.update(key, content=content)
            return json.dumps({
                "success": True,
                "action": "replaced",
                "message": f"key={key} 已更新",
                "key": key,
            }, ensure_ascii=False)
        else:
            return json.dumps({"success": False, "error": f"未找到 key={key}"}, ensure_ascii=False)

    # 没有 key，内容模糊匹配
    matched = _find_by_text_match(mm, target, old_text)
    if not matched:
        return json.dumps({"success": False, "error": f"未找到包含「{old_text}」的记忆"}, ensure_ascii=False)

    if len(matched) > 1:
        previews = [m["content"][:60] for m in matched]
        return json.dumps({
            "success": False,
            "error": f"多条记忆匹配「{old_text}」",
            "matches": previews,
            "suggestion": "请用更具体的 old_text 或指定 key",
        }, ensure_ascii=False)

    m = matched[0]
    mm.update(m["key"], content=content)
    return json.dumps({
        "success": True,
        "action": "replaced",
        "message": f"已替换包含「{old_text}」的记忆",
        "key": m["key"],
    }, ensure_ascii=False)


def _handle_remove(mm: MemoryManager, target: str, old_text: str) -> str:
    """删除记忆"""
    if not old_text or not old_text.strip():
        return json.dumps({"success": False, "error": "old_text 不能为空"}, ensure_ascii=False)

    old_text = old_text.strip()

    # 先尝试 key 精确匹配
    if mm.get(old_text):
        mm.delete(old_text)
        return json.dumps({
            "success": True,
            "action": "removed",
            "message": f"已删除 key={old_text}",
        }, ensure_ascii=False)

    # 内容模糊匹配
    matched = _find_by_text_match(mm, target, old_text)
    if not matched:
        return json.dumps({"success": False, "error": f"未找到包含「{old_text}」的记忆"}, ensure_ascii=False)

    if len(matched) > 1:
        previews = [m["content"][:60] for m in matched]
        return json.dumps({
            "success": False,
            "error": f"多条记忆匹配「{old_text}」",
            "matches": previews,
            "suggestion": "请用更具体的文本或直接指定 key",
        }, ensure_ascii=False)

    m = matched[0]
    mm.delete(m["key"])
    return json.dumps({
        "success": True,
        "action": "removed",
        "message": f"已删除包含「{old_text}」的记忆",
        "key": m["key"],
    }, ensure_ascii=False)


# ── 辅助函数 ──


def _content_similarity(a: str, b: str) -> float:
    """计算两条记忆内容的 Jaccard 相似度

    分词策略（与 MemoryManager._tokenize 一致）：
      中文单字、英文单词、数字各自作为 token
    """
    import re
    if not a or not b:
        return 0.0
    tokens_a = set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', a))
    tokens_b = set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _find_existing_by_content(mm: MemoryManager, content: str,
                              scope: str = "zhu", context_id: str = None):
    """检查内容相似度 — 调用 MemoryManager.find_similar_content

    短内容（<20字）阈值提高至 0.65，长内容 0.50
    """
    threshold = 0.50 if len(content) >= 20 else 0.65
    return mm.find_similar_content(
        content, scope=scope, context_id=context_id,
        threshold=threshold,
    )


def _find_by_text_match(mm: MemoryManager, target: str, text: str, limit: int = 5):
    """通过文本片段搜索记忆"""
    from models import AgentMemory
    entries = mm.db.query(AgentMemory).filter(
        AgentMemory.category == target,
        AgentMemory.content.contains(text),
    ).limit(limit).all()
    if not entries:
        # 不限制 category 再搜一次
        entries = mm.db.query(AgentMemory).filter(
            AgentMemory.content.contains(text),
        ).limit(limit).all()
    return [
        {"key": e.key, "content": e.content, "level": e.priority_level}
        for e in entries
    ]


def _auto_key(content: str, target: str) -> str:
    """根据内容自动生成 key"""
    import re
    # 去掉标点符号，取前 4 个中文字/英文词
    clean = re.sub(r'[^\w\u4e00-\u9fff]', '_', content[:30])
    clean = clean.strip('_').lower()
    if not clean:
        import uuid
        clean = uuid.uuid4().hex[:8]
    # 限制长度
    return f"{target}_{clean[:20]}"


def _infer_topic(content: str) -> str:
    """从内容推断话题域（简单关键词法，不作为主力去重）"""
    topic_map = {
        "personal_info": ["我叫", "我是", "姓名", "名字", "英文名", "住在", "居住在", "家住", "职业", "工作", "年龄", "生日"],
        "preference": ["喜欢", "偏爱", "偏好", "爱", "讨厌", "不喜欢", "最", "推荐"],
        "habit": ["习惯", "通常", "一般", "经常", "每天", "每周", "作息"],
        "tech": ["技术", "编程", "代码", "开发", "工具", "配置", "安装", "部署", "API"],
        "work": ["项目", "任务", "需求", "工作", "交付", "截止", "客户"],
        "entertainment": ["电影", "电视剧", "综艺", "小说", "动漫", "音乐", "游戏", "好看"],
        "food": ["吃", "饭", "菜", "美食", "餐厅", "好吃", "烹饪"],
        "travel": ["旅游", "旅行", "景点", "出行", "酒店", "机票"],
        "health": ["健康", "运动", "减肥", "健身", "锻炼", "体检"],
    }
    for topic, keywords in topic_map.items():
        for kw in keywords:
            if kw in content:
                return topic
    return "general"


def _log_extraction(target: str, msg: str):
    """记录记忆操作日志"""
    print(f"[memory] {target}: {msg}")


# ── 确保 AgentMemory 在模块级可导入 ──
try:
    from models import AgentMemory
except ImportError:
    AgentMemory = None
