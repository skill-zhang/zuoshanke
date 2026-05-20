"""场景 + Thinking Map CRUD + 场景流式 + 场景广场/工坊/发布/导入导出"""
import difflib
import json
import os
import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import Scene, ThinkingMap, ThinkNode, Message, SceneAsset, PriorityQueue, ProjectOutput
from schemas import (
    SceneCreate, SceneOut, SceneUpdate, ScenePublishRequest,
    SceneExportOut, SceneImportIn,
    ThinkNodeCreate, ThinkNodeUpdate, ThinkNodeOut, ThinkingMapOut,
    MessageCreate,
)
from ai_engine import (
    extract_and_classify,
    get_settings,
    call_deepseek_chat,
)

from agent_core.memory_manager import MemoryManager
from agent_core.memory_extractor import MemoryExtractor
from agent_core.token_counter import (
    estimate_messages_tokens, get_context_length_from_route,
    context_usage_str, progress_bar,
)
from utils import make_id, utcnow
from router.shared import sse_event, sse_response

router = APIRouter(tags=["场景"])


# ═══ 智能图标匹配引擎 ═══
# 根据场景名称自动匹配 emoji 图标，无需用户手动选择

ICON_RULES = [
    # ── 知名品牌 / APP ──
    (["京东", "JD"], "🐶"),
    (["淘宝", "天猫", "淘特"], "🐱"),
    (["拼多多", "拼团"], "🛍️"),
    (["微信", "WeChat", "微商"], "💬"),
    (["抖音", "TikTok", "短视频"], "🎵"),
    (["小红书", "RED"], "📕"),
    (["B站", "哔哩哔哩", "bilibili"], "📺"),
    (["知乎", "问答"], "❓"),
    (["微博", "weibo"], "📢"),
    (["美团", "大众点评", "外卖"], "🛵"),
    (["滴滴", "打车", "出行"], "🚕"),
    (["支付宝", "Alipay"], "💳"),
    (["QQ", "腾讯"], "🐧"),
    (["百度", "Baidu"], "🔍"),
    (["谷歌", "Google"], "🌐"),
    (["GitHub", "Github"], "🐙"),
    (["微信读书", "读书"], "📖"),
    (["网易云", "云音乐", "音乐"], "🎵"),
    (["钉钉", "DingTalk"], "📌"),
    (["飞书", "Feishu", "Lark"], "📎"),
    (["企业微信", "企微"], "🏢"),
    # ── 按名称长度降序排列（长词优先匹配） ──
    (["旅游出行", "旅行规划", "旅游攻略", "行程规划"], "✈️"),
    (["商品比价", "价格对比", "购物比价"], "🛒"),
    (["天气预报", "天气查询", "气象预报"], "🌤️"),
    (["数据报表", "数据分析", "数据大屏"], "📊"),
    (["金融行情"], "📈"),
    (["二手车", "新车评估", "汽车评估"], "🚗"),
    (["AI编程", "代码助手", "编程助手"], "💻"),
    (["学习助手", "学习计划"], "📚"),
    (["工作安排", "工作计划", "任务管理"], "💼"),
    (["美食推荐", "食谱推荐"], "🍜"),
    (["电影推荐", "影视推荐"], "🎬"),
    # ── 通用短关键词 ──
    (["天气", "气象", "气温", "预报", "温度", "湿度"], "❄️"),
    (["旅游", "旅行", "出行", "度假", "景点", "酒店", "机票", "导航"], "✈️"),
    (["车", "汽车", "驾驶", "加油", "停车", "电动车"], "🚗"),
    (["商品", "比价", "价格", "购物", "订单", "物流", "退货", "电商"], "🛒"),
    (["女装", "男装", "服装", "鞋子", "衣服", "穿搭"], "👗"),
    (["股票", "基金", "理财", "投资", "保险", "税务", "金融"], "📈"),
    (["报表", "数据", "图表"], "📊"),
    (["工作", "办公", "项目", "任务", "会议", "文档", "邮件"], "💼"),
    (["学习", "教育", "考试", "课程", "培训", "知识", "阅读", "图书"], "📚"),
    (["创作", "设计", "写作", "文案", "内容", "视频", "图片", "编辑"], "🎨"),
    (["自媒体", "社交", "运营", "账号", "粉丝", "公众号", "小红书"], "💬"),
    (["AI", "代码", "编程", "开发", "部署", "算法", "数据库", "系统", "运维"], "💻"),
    (["健康", "医疗", "医生", "医院", "药物", "体检", "运动", "健身"], "🏥"),
    (["美食", "食谱", "菜谱", "餐厅", "外卖", "做饭"], "🍜"),
    (["电影", "影视", "电视剧", "娱乐"], "🎬"),
    (["日历", "时间", "提醒", "日程"], "📅"),
    # 测试放最后（仅当无其他匹配时生效）
    (["测试", "实验", "验证", "试用"], "🧪"),

    # ── 2026-05-20 新增 ──
    (["项目", "工程", "工程项目", "项目管理"], "🏗️"),
    (["科研", "研究", "学术", "论文", "专利", "实验室", "研发"], "🔬"),
    (["历史", "史学", "考古", "古籍"], "📜"),
    (["地理", "地图", "区域", "国土"], "🌍"),
    (["法律", "法规", "合同", "合规", "诉讼"], "⚖️"),
    (["招聘", "求职", "简历", "面试", "HR", "人力"], "🤝"),
    (["装修", "设计", "室内", "家装", "工装"], "🏠"),
    (["买房", "购房", "租房", "楼盘", "房产", "房价", "中介"], "🏡"),
    (["宠物", "养宠", "猫", "狗", "动物"], "🐾"),
    (["游戏", "电竞", "游玩", "娱乐", "Steam"], "🎮"),
    (["摄影", "相机", "拍照", "修图"], "📷"),
    (["音乐", "乐器", "唱歌"], "🎵"),
    (["运动", "体育", "跑步", "健身", "游泳", "瑜伽"], "⚽"),
    (["家居", "家具", "家电", "收纳", "生活"], "🪴"),
    (["手工艺", "手工", "DIY", "制作"], "✂️"),
    (["个人成长", "自我提升", "习惯", "冥想", "心理学"], "🌱"),
    (["投资", "创业", "商业", "商业模式", "融资"], "🚀"),
    (["供应链", "采购", "仓储", "库存", "物流"], "📦"),
]


def auto_detect_icon(name: str) -> str:
    """从场景名称自动匹配 emoji 图标

    策略：关键词 OR 匹配 + 长词优先。
    遍历规则，名称包含规则中任一关键词即触发，返回第一个匹配。
    """
    if not name:
        return None
    name_lower = name.lower()

    for keywords, emoji in ICON_RULES:
        if any(kw.lower() in name_lower for kw in keywords):
            return emoji

    return None


# ═══ 场景 CRUD ═══

@router.post("/api/scenes", response_model=SceneOut)
def create_scene(data: SceneCreate, db: Session = Depends(get_db)):
    # 新建场景默认填入 SCENE_SYSTEM_PROMPT 作为背景设定
    from agent_core.context_builder import SCENE_SYSTEM_PROMPT
    default_prompt = SCENE_SYSTEM_PROMPT
    scene = Scene(
        id=make_id("scene"),
        project_id="",
        name=data.name,
        description=data.description or "",
        category=data.category or "other",
        guide_text=data.guide_text or None,
        user_context=data.user_context or default_prompt,
    )
    # 有显式图标用显式，否则根据名称自动匹配
    scene.icon = data.icon or auto_detect_icon(data.name) or "📦"
    db.add(scene)
    db.commit()
    db.refresh(scene)

    tmap = ThinkingMap(id=make_id("think"), scene_id=scene.id, title=f"{data.name} · 需求梳理")
    db.add(tmap)
    db.commit()
    db.refresh(tmap)

    root = ThinkNode(
        id=make_id("n"), map_id=tmap.id,
        type="root", label=data.name, status="confirmed",
    )
    db.add(root)
    db.commit()
    return scene


@router.get("/api/scenes", response_model=List[SceneOut])
def list_scenes(db: Session = Depends(get_db)):
    q = db.query(Scene)
    return q.order_by(Scene.pinned.desc(), Scene.updated_at.desc()).all()


# ═══ 场景广场 ═══
# 注意：plaza / workshop / import 必须注册在 {scene_id} 之前，否则被路径参数捕获

@router.get("/api/scenes/plaza", response_model=List[SceneOut])
def list_plaza_scenes(
    category: str = None,
    q: str = None,
    db: Session = Depends(get_db),
):
    """场景广场 — 仅返回已发布场景，支持分类过滤和搜索"""
    query = db.query(Scene).filter(Scene.version != "0.0")
    if category:
        query = query.filter(Scene.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.query(Scene).filter(
                Scene.name.ilike(like) | Scene.description.ilike(like)
            ).exists()
        )
    return query.order_by(Scene.published_at.desc(), Scene.updated_at.desc()).all()


@router.get("/api/scenes/workshop", response_model=List[SceneOut])
def list_workshop_scenes(
    category: str = None,
    project_id: str = None,
    db: Session = Depends(get_db),
):
    """工坊 — 自己创作的所有场景（含草稿和已发布）"""
    q = db.query(Scene)
    if project_id:
        q = q.filter(Scene.project_id == project_id)
    if category:
        q = q.filter(Scene.category == category)
    return q.order_by(Scene.pinned.desc(), Scene.updated_at.desc()).all()


@router.post("/api/scenes/import", response_model=SceneOut)
def import_scene(data: SceneImportIn, db: Session = Depends(get_db)):
    """从 JSON 导入场景"""
    s = data.scene
    scene = Scene(
        id=make_id("scene"),
        project_id="",
        name=s.name,
        description=s.description or "",
        category=s.category or "other",
        guide_text=s.guide_text,
        user_context=s.user_context,
        complexity=s.complexity,
        constraints=s.constraints,
        constraints_locked=s.constraints_locked,
        version="0.0",  # 导入后变为草稿
        source="imported",
    )
    scene.icon = s.icon or auto_detect_icon(s.name) or "📦"
    db.add(scene)
    db.commit()
    db.refresh(scene)

    tmap = ThinkingMap(id=make_id("think"), scene_id=scene.id, title=f"{s.name} · 需求梳理")
    db.add(tmap)
    db.commit()
    db.refresh(tmap)

    root = ThinkNode(
        id=make_id("n"), map_id=tmap.id,
        type="root", label=s.name, status="confirmed",
    )
    db.add(root)
    db.commit()
    return scene


# ═══ 场景 detail CRUD ═══

@router.get("/api/scenes/{scene_id}", response_model=SceneOut)
def get_scene(scene_id: str, db: Session = Depends(get_db)):
    return _get_scene_or_404(db, scene_id)


@router.patch("/api/scenes/{scene_id}", response_model=SceneOut)
def update_scene(scene_id: str, data: SceneUpdate, db: Session = Depends(get_db)):
    scene = _get_scene_or_404(db, scene_id)
    if data.name is not None:
        scene.name = data.name
        # 重命名时自动匹配新图标（除非显式传了 icon）
        if data.icon is None:
            detected = auto_detect_icon(data.name)
            if detected:
                scene.icon = detected
    if data.pinned is not None:
        scene.pinned = data.pinned
    if 'user_context' in data.model_dump(exclude_unset=True):
        val = data.user_context
        if val is None or not val.strip():
            # 显式传 null/空 → 恢复为默认 prompt
            from agent_core.context_builder import SCENE_SYSTEM_PROMPT
            scene.user_context = SCENE_SYSTEM_PROMPT
        else:
            scene.user_context = val.strip()
    if data.icon is not None:
        scene.icon = data.icon or "📦"
    if data.description is not None:
        scene.description = data.description or ""
    if data.category is not None:
        scene.category = data.category or "other"
    if data.guide_text is not None:
        scene.guide_text = data.guide_text or None
    scene.updated_at = utcnow()
    db.commit()
    db.refresh(scene)
    return scene


@router.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id: str, db: Session = Depends(get_db)):
    scene = _get_scene_or_404(db, scene_id)
    # 级联清理关联数据
    from models import Message, ThinkingMap, ThinkNode, PriorityQueue, ReflectTimeline, SceneAsset, DialogState
    db.query(DialogState).filter(DialogState.scene_id == scene_id).delete()
    db.query(SceneAsset).filter(SceneAsset.scene_id == scene_id).delete()
    db.query(PriorityQueue).filter(PriorityQueue.scene_id == scene_id).delete()
    db.query(ReflectTimeline).filter(ReflectTimeline.scene_id == scene_id).delete()
    tm = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    if tm:
        db.query(ThinkNode).filter(ThinkNode.map_id == tm.id).delete()
        db.delete(tm)
    db.query(Message).filter(Message.scene_id == scene_id).delete()
    db.delete(scene)
    db.commit()
    return {"ok": True}


# ═══ 发布 / 版本更新 ═══

@router.post("/api/scenes/{scene_id}/publish", response_model=SceneOut)
def publish_scene(scene_id: str, data: ScenePublishRequest, db: Session = Depends(get_db)):
    """发布场景或更新版本。校验 version 必须大于当前版本"""
    scene = _get_scene_or_404(db, scene_id)

    # 版本号比较（语义化：1.0 < 1.1 < 2.0）
    def _parse_version(v: str) -> tuple:
        try:
            parts = v.strip().split(".")
            return tuple(int(x) for x in parts)
        except (ValueError, AttributeError):
            raise HTTPException(400, f"版本号格式无效: {v}（请使用 x.y 格式）")

    new_ver = _parse_version(data.version)
    cur_ver = _parse_version(scene.version)
    if new_ver <= cur_ver:
        raise HTTPException(400, f"新版本 {data.version} 必须大于当前版本 {scene.version}")

    scene.version = data.version
    scene.changelog = data.changelog or None
    scene.published_at = utcnow()
    scene.updated_at = utcnow()
    db.commit()
    db.refresh(scene)
    return scene


# ═══ 导入 / 导出 ═══

@router.get("/api/scenes/{scene_id}/export", response_model=SceneExportOut)
def export_scene(scene_id: str, db: Session = Depends(get_db)):
    """导出场景为 JSON（不含消息记录）"""
    scene = _get_scene_or_404(db, scene_id)
    return SceneExportOut(
        name=scene.name,
        icon=scene.icon,
        description=scene.description or "",
        category=scene.category or "other",
        guide_text=scene.guide_text,
        user_context=scene.user_context,
        complexity=scene.complexity,
        constraints=scene.constraints,
        constraints_locked=scene.constraints_locked,
        version="0.0" if scene.version == "0.0" else scene.version,
    )


# ═══ Thinking Map ═══

@router.get("/api/scenes/{scene_id}/thinking-map", response_model=ThinkingMapOut)
def get_thinking_map(scene_id: str, db: Session = Depends(get_db)):
    _get_scene_or_404(db, scene_id)
    tmap = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")
    tmap.nodes  # trigger lazy load
    return tmap


@router.post("/api/thinking-maps/{map_id}/nodes", response_model=ThinkNodeOut)
def add_node(map_id: str, data: ThinkNodeCreate, db: Session = Depends(get_db)):
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")
    if data.parent_id:
        parent = db.query(ThinkNode).filter(ThinkNode.id == data.parent_id).first()
        if not parent:
            raise HTTPException(404, "父节点不存在")

    node = ThinkNode(
        id=data.id, map_id=map_id, parent_id=data.parent_id,
        type=data.type, label=data.label, status=data.status,
        actionable=data.actionable, discussion=data.discussion,
        context_ref=data.context_ref,
        position_x=data.position_x, position_y=data.position_y,
    )
    db.add(node)
    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()
    db.refresh(node)
    return node


@router.patch("/api/think-nodes/{node_id}", response_model=ThinkNodeOut)
def update_node(node_id: str, data: ThinkNodeUpdate, db: Session = Depends(get_db)):
    node = db.query(ThinkNode).filter(ThinkNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    for field in ("label", "status", "actionable", "discussion", "position_x", "position_y",
                  "priority", "queue_order", "execution_result", "created_by"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(node, field, val)
    # JSON list fields
    if data.converged_from is not None:
        node.converged_from = data.converged_from
    if data.depends_on is not None:
        node.depends_on = data.depends_on

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == node.map_id).first()
    if tmap:
        tmap.version += 1
        tmap.updated_at = utcnow()
    db.commit()
    db.refresh(node)
    return node


@router.delete("/api/think-nodes/{node_id}")
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(ThinkNode).filter(ThinkNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    db.delete(node)
    db.commit()
    return {"ok": True}



# ═══ Agent Loop: Diverge (发散阶段) ═══

class DivergeRequest(BaseModel):
    context: str = Field("", description="额外上下文提示")
    force: bool = Field(False, description="强制重新发散")


@router.post("/api/thinking-maps/{map_id}/diverge")
def diverge_thinking_map(map_id: str, data: DivergeRequest = None, db: Session = Depends(get_db)):
    """
    发散 Thinking Map：LLM 头脑风暴拆解任务，生成节点树
    """
    from ai_engine import call_deepseek_chat
    import json

    if data is None:
        data = DivergeRequest()

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map不存在")

    scene = db.query(Scene).filter(Scene.id == tmap.scene_id).first()
    scene_name = scene.name if scene else "未命名场景"
    scene_desc = scene.description or ""

    existing_nodes = db.query(ThinkNode).filter(ThinkNode.map_id == map_id).all()
    root = next((n for n in existing_nodes if n.type == "root"), None)
    if not root:
        raise HTTPException(400, "Thinking Map缺少根节点")

    if data.force:
        for n in existing_nodes:
            if n.id != root.id and n.status == "discussing":
                db.delete(n)
        db.commit()
        existing_nodes = [root]

    is_first = len(existing_nodes) <= 1 and not any(n.type != "root" for n in existing_nodes)

    existing_summary = ""
    for n in existing_nodes:
        if n.type == "root":
            continue
        p = next((x for x in existing_nodes if x.id == n.parent_id), None)
        pl = p.label if p else "根节点"
        existing_summary += "- [" + n.status + "] " + pl + " -> " + n.label + "\n"

    # ---- Build prompts ----
    if is_first:
        prompt_lines = [
            "你是坐山客 AI 工作台的任务拆解专家。你需要将以下任务做结构化分解，输出清晰的思维导图节点树。",
            "",
            "## 任务",
            "名称: " + scene_name,
            "描述: " + (scene_desc or "(无详细描述)"),
        ]
        if data.context:
            prompt_lines.append("额外上下文: " + data.context)
        prompt_lines += [
            "",
            "## 输出格式",
            '请以 JSON 格式输出，严格按以下结构:',
            '{',
            '  "categories": [',
            '    {',
            '      "label": "类别名称",',
            '      "nodes": [',
            '        {"label": "子任务名称"},',
            '        {"label": "子任务名称"}',
            '      ]',
            '    }',
            '  ]',
            '}',
            "",
            "## 拆解要求",
            "1. 根据任务名称和描述，识别 3-5 个关键领域/模块（categories）",
            "2. 每个类别下分解 2-4 个具体可执行的子任务",
            "3. 使用简洁的中文标签（6-12 字最佳）",
            "4. 标签应该具体可执行，而非抽象概念",
            "5. 类别和子任务要有逻辑层次关系",
            "6. 输出只有 JSON，不要额外解释",
        ]
        system_prompt = "\n".join(prompt_lines)
    else:
        prompt_lines = [
            "你是坐山客 AI 工作台的任务拆解专家。请分析以下任务的思维导图当前状态，补充新的分支节点。",
            "",
            "## 任务",
            "名称: " + scene_name,
            "描述: " + (scene_desc or "(无详细描述)"),
        ]
        if data.context:
            prompt_lines.append("额外上下文: " + data.context)
        prompt_lines += [
            "",
            "## 现有节点",
            existing_summary or "(暂无细化节点)",
            "",
            "## 输出格式",
            '请以 JSON 格式输出，严格按以下结构:',
            '{',
            '  "categories": [',
            '    {',
            '      "parent_label": "要挂载的父节点名称（从现有节点中选择）",',
            '      "nodes": [',
            '        {"label": "新增子任务名称"},',
            '        {"label": "新增子任务名称"}',
            '      ]',
            '    }',
            '  ]',
            '}',
            "",
            "## 要求",
            "1. 分析现有节点，找出尚未覆盖的方向或遗漏的子任务",
            "2. 输出的 parent_label 必须从现有节点中选择（使用完全一致的名称）",
            "3. 每个父节点下补充 1-3 个新子任务",
            "4. 标签使用简洁中文（6-12 字），具体可执行",
            "5. 输出只有 JSON，不要额外解释",
        ]
        system_prompt = "\n".join(prompt_lines)

    # ---- Call LLM ----
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请对 " + scene_name + " 进行任务拆解。"},
    ]

    raw = call_deepseek_chat(messages, model="flash", temperature=0.5, max_tokens=4096, route="medium")
    if not raw:
        raise HTTPException(502, "LLM发散调用失败")

    # ---- Parse JSON ----
    def _extract_json(text):
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None

    parsed = _extract_json(raw)
    if not parsed:
        logger.error("[Diverge] LLM返回无法解析: " + raw[:300])
        raise HTTPException(502, "LLM发散结果解析失败，请重试")

    categories = parsed.get("categories", [])
    if not categories:
        categories = parsed.get("nodes", [])

    if not categories:
        return {
            "map_id": map_id,
            "new_nodes": [],
            "thinking_map": {"id": tmap.id, "title": tmap.title,
                "status": tmap.status, "version": tmap.version,
                "nodes": [n.to_schema_dict() for n in existing_nodes]},
            "message": "LLM未生成任何节点",
        }

    # ---- Create nodes ----
    name_to_id = {n.label: n.id for n in existing_nodes}
    new_nodes = []

    for cat in categories:
        parent_label = cat.get("parent_label", cat.get("label", ""))
        children = cat.get("nodes", [])

        if is_first and "label" in cat:
            parent_label = cat["label"]
            if parent_label not in name_to_id:
                l1_id = make_id("n")
                l1_node = ThinkNode(
                    id=l1_id, map_id=map_id, parent_id=root.id,
                    type="domain", label=parent_label,
                    status="discussing", created_by="brainstorm",
                )
                db.add(l1_node)
                new_nodes.append(l1_node)
                name_to_id[parent_label] = l1_id

        parent_id = name_to_id.get(parent_label, root.id)

        for child in children:
            child_label = child.get("label", "")
            if not child_label:
                continue
            is_dup = any(
                n.parent_id == parent_id and n.label == child_label
                for n in existing_nodes + new_nodes
            )
            if is_dup:
                continue
            child_id = make_id("n")
            child_node = ThinkNode(
                id=child_id, map_id=map_id, parent_id=parent_id,
                type="leaf", label=child_label,
                status="discussing", created_by="brainstorm",
            )
            db.add(child_node)
            new_nodes.append(child_node)

    if not new_nodes:
        return {
            "map_id": map_id,
            "new_nodes": [],
            "thinking_map": {"id": tmap.id, "title": tmap.title,
                "status": tmap.status, "version": tmap.version,
                "nodes": [n.to_schema_dict() for n in existing_nodes]},
            "message": "所有节点已存在，无需新增",
        }

    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()

    db.refresh(tmap)
    all_nodes = db.query(ThinkNode).filter(ThinkNode.map_id == map_id).all()
    return {
        "map_id": map_id,
        "new_nodes": [n.to_schema_dict() for n in new_nodes],
        "is_first_diverge": is_first,
        "thinking_map": {"id": tmap.id, "title": tmap.title,
            "status": tmap.status, "version": tmap.version,
            "nodes": [n.to_schema_dict() for n in all_nodes]},
    }


# ═══ Agent Loop: Converge ═══

@router.post("/api/thinking-maps/{map_id}/converge")
def converge_thinking_map(map_id: str, db: Session = Depends(get_db)):
    """
    收敛 Thinking Map：
    1. 获取所有 status=discussing 的叶子节点
    2. 用标签相似度聚类（difflib.SequenceMatcher）
    3. 对每组 2+ 相似节点：创建 refined 节点 + 标记源节点为 discarded
    4. 单节点可选提升为 refined
    返回收敛结果：merged_pairs + 更新后的 TM
    """
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    # 获取根节点（作为收敛后的父节点）
    root = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id, ThinkNode.type == "root"
    ).first()
    if not root:
        raise HTTPException(400, "Thinking Map 缺少根节点")

    nodes = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id,
        ThinkNode.status.in_(["discussing", "created"]),
    ).all()

    if not nodes:
        return {"map_id": map_id, "merged": [], "discarded": [], "message": "没有需要收敛的节点"}

    # 1. 聚类：共享公共子串检测（对中文短标签友好）
    # 如果两个标签包含至少一个长度 >=2 的公共子串，则认为相似
    def _share_substr(a: str, b: str, min_len: int = 2) -> bool:
        """检查两个字符串是否有长度 >= min_len 的公共子串"""
        subs = {a[i:i+min_len] for i in range(len(a)-min_len+1)}
        for i in range(len(b)-min_len+1):
            if b[i:i+min_len] in subs:
                return True
        return False

    clusters = []
    assigned = set()

    for i, a in enumerate(nodes):
        if a.id in assigned:
            continue
        group = [a]
        assigned.add(a.id)
        for j, b in enumerate(nodes):
            if b.id in assigned or i == j:
                continue
            if _share_substr(a.label, b.label, min_len=2):
                group.append(b)
                assigned.add(b.id)
        clusters.append(group)

    merged_pairs = []
    new_nodes = []
    for group in clusters:
        if len(group) >= 2:
            # 合并：创建 refined 节点
            best_label = group[0].label  # 取第一个为名
            merged_labels = [n.label for n in group]
            new_id = f"node-{uuid.uuid4().hex[:8]}"
            refined = ThinkNode(
                id=new_id,
                map_id=map_id,
                parent_id=root.id,
                type="leaf",
                label=best_label,
                status="refined",
                converged_from=merged_labels,
                created_by="brainstorm",
            )
            db.add(refined)
            new_nodes.append(refined)
            merged_pairs.append({
                "target_id": new_id,
                "target_label": best_label,
                "source_labels": merged_labels,
                "source_ids": [n.id for n in group],
            })
            # 标记源节点为 discarded
            for node in group:
                node.status = "discarded"
        else:
            # 单节点 → 升级为 refined（准备进入队列）
            node = group[0]
            node.status = "refined"

    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()

    # 刷新返回
    db.refresh(tmap)
    tmap.nodes  # trigger load
    return {
        "map_id": map_id,
        "merged": merged_pairs,
        "discarded": [],  # 预留：后续可加不可行检测
        "thinking_map": {
            "id": tmap.id,
            "title": tmap.title,
            "status": tmap.status,
            "version": tmap.version,
            "nodes": [n.to_schema_dict() for n in tmap.nodes],
        },
    }


# ═══ Agent Loop: Priority Queue ═══

def _topological_sort(nodes: list) -> list:
    """
    拓扑排序（Kahn 算法）。
    nodes: 每个元素有 id, depends_on (list of ids)。
    返回排序后的节点列表；若有环则按入度降序返回（尽力而为）。
    """
    adj = {n.id: [] for n in nodes}  # 邻接表
    in_deg = {n.id: 0 for n in nodes}
    id_map = {n.id: n for n in nodes}

    for n in nodes:
        for dep_id in (n.depends_on or []):
            if dep_id in adj:
                adj[dep_id].append(n.id)
                in_deg[n.id] = in_deg.get(n.id, 0) + 1

    queue = [nid for nid, d in in_deg.items() if d == 0]
    sorted_ids = []

    while queue:
        # 按依赖数量排序，先处理 blocking 更多的
        queue.sort(key=lambda nid: len(adj.get(nid, [])), reverse=True)
        nid = queue.pop(0)
        sorted_ids.append(nid)
        for neighbor in adj.get(nid, []):
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)

    # 如果有剩余（环），按入度降序追加
    remaining = [nid for nid in in_deg if nid not in sorted_ids]
    remaining.sort(key=lambda nid: in_deg[nid], reverse=True)
    sorted_ids.extend(remaining)

    return [id_map[nid] for nid in sorted_ids if nid in id_map]


@router.post("/api/thinking-maps/{map_id}/prioritize")
def prioritize_thinking_map(map_id: str, db: Session = Depends(get_db)):
    """
    自动排序 Priority Queue：
    1. 收集所有 status=refined 的节点
    2. 基于公共子串启发式检测依赖关系（如果 A 的标签包含 B 标签的子串 → A 依赖 B）
    3. 拓扑排序
    4. 分配 priority + queue_order
    5. 孤立的单节点（无依赖无阻塞）排最后
    """
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    # 只处理 refined 节点
    refined_nodes = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id,
        ThinkNode.status == "refined",
    ).all()

    if not refined_nodes:
        return {"map_id": map_id, "queue": [], "message": "没有 refined 节点需要排序"}

    # 1. 启发式依赖检测：如果 A 标签包含 B 标签中长度 >=2 的子串，A 依赖 B
    def _shares_substr(a: str, b: str) -> bool:
        subs = {a[i:i+2] for i in range(len(a)-1)}
        for i in range(len(b)-1):
            if b[i:i+2] in subs:
                return True
        return False

    current_deps = {}
    for n in refined_nodes:
        deps = n.depends_on or []
        # 自动检测：如果当前节点标签包含其他节点标签的子串，自动添加依赖
        for other in refined_nodes:
            if other.id == n.id:
                continue
            # 如果 other 的标签是 n 标签的子串 → n 依赖 other（other 是前置条件）
            if other.label in n.label or _shares_substr(other.label, n.label):
                if other.id not in deps:
                    deps.append(other.id)
        n.depends_on = list(set(deps))  # 去重
        current_deps[n.id] = n.depends_on

    # 2. 拓扑排序
    sorted_nodes = _topological_sort(refined_nodes)

    # 3. 计算每个节点的阻塞数（有多少节点直接依赖它）
    dependents_count = {n.id: 0 for n in refined_nodes}
    for n in sorted_nodes:
        for dep_id in (n.depends_on or []):
            if dep_id in dependents_count:
                dependents_count[dep_id] = dependents_count.get(dep_id, 0) + 1

    # 4. 分配 queue_order + priority
    queue = []
    level_map = {}  # nid → depth level

    # BFS 计算依赖深度
    for n in sorted_nodes:
        deps = n.depends_on or []
        if not deps:
            level_map[n.id] = 0
        else:
            existing_levels = [level_map.get(d, 0) for d in deps if d in level_map]
            level_map[n.id] = max(existing_levels, default=0) + 1

    for idx, n in enumerate(sorted_nodes):
        n.queue_order = idx + 1
        blocks = dependents_count.get(n.id, 0)

        # 优先级启发式
        if blocks >= 2:
            n.priority = 1  # P1: 2+ 节点依赖它（关键阻塞）
        elif blocks >= 1:
            n.priority = 2  # P2: 1 个节点依赖它
        elif level_map.get(n.id, 0) == 0:
            n.priority = 1  # P1: 无依赖，可立即开工
        elif level_map.get(n.id, 0) <= 2:
            n.priority = 3  # P3: 有依赖但浅
        else:
            n.priority = 4  # P4: 深依赖或无阻塞

        queue.append({
            "id": n.id,
            "label": n.label,
            "queue_order": n.queue_order,
            "priority": n.priority,
            "depends_on": n.depends_on or [],
            "blocks_count": blocks,
            "level": level_map.get(n.id, 0),
        })

    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()

    return {
        "map_id": map_id,
        "queue": queue,
        "node_count": len(queue),
    }


@router.get("/api/thinking-maps/{map_id}/queue")
def get_priority_queue(map_id: str, db: Session = Depends(get_db)):
    """获取 Priority Queue（按 queue_order 排序）"""
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    refined = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id,
        ThinkNode.status == "refined",
    ).order_by(ThinkNode.queue_order).all()

    queue = []
    for n in refined:
        queue.append({
            "id": n.id,
            "label": n.label,
            "queue_order": n.queue_order,
            "priority": n.priority,
            "depends_on": n.depends_on or [],
            "converged_from": n.converged_from or [],
        })

    return {
        "map_id": map_id,
        "queue": queue,
        "node_count": len(queue),
    }


@router.get("/api/thinking-maps/{map_id}/focus-queue")
def get_focus_queue(map_id: str, limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    """
    获取聚焦队列（WIP 限制版）：
    返回 Priority Queue 顶部 N 个节点，附带关联的 Action Map 信息。
    """
    from models import ActionMap

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    refined = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id,
        ThinkNode.status == "refined",
    ).order_by(ThinkNode.queue_order).limit(limit).all()

    items = []
    for n in refined:
        # 查找已有关联的 Action Map
        am = db.query(ActionMap).filter(
            ActionMap.think_node_id == n.id
        ).order_by(ActionMap.created_at.desc()).first()

        items.append({
            "id": n.id,
            "label": n.label,
            "queue_order": n.queue_order,
            "priority": n.priority,
            "depends_on": n.depends_on or [],
            "action_map": {
                "id": am.id if am else None,
                "status": am.status if am else None,
                "title": am.title if am else None,
            } if am else None,
        })

    return {
        "map_id": map_id,
        "items": items,
        "item_count": len(items),
        "limit": limit,
    }


# ═══ Agent Loop: Reflect（反馈注入）═══

class ReflectRequest(BaseModel):
    node_id: str
    result_summary: str
    new_discoveries: List[str] = Field(default_factory=list)
    is_success: bool = True


@router.post("/api/thinking-maps/{map_id}/reflect")
def reflect_thinking_map(map_id: str, data: ReflectRequest, db: Session = Depends(get_db)):
    """
    反馈注入：Action Map 执行完成后，将结果和发现反哺回 Thinking Map。
    1. 更新已执行节点的 execution_result + status
    2. 为每个新发现创建子节点（created_by=reflect）
    3. 自动重新收敛 + 排序
    """
    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == map_id).first()
    if not tmap:
        raise HTTPException(404, "Thinking Map 不存在")

    root = db.query(ThinkNode).filter(
        ThinkNode.map_id == map_id, ThinkNode.type == "root"
    ).first()
    if not root:
        raise HTTPException(400, "缺少根节点")

    # 1. 更新已执行节点
    node = db.query(ThinkNode).filter(ThinkNode.id == data.node_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")

    node.execution_result = data.result_summary
    node.status = "completed" if data.is_success else "refined"
    reflect_events = [{
        "type": "node_completed" if data.is_success else "node_blocked",
        "node_id": node.id,
        "label": node.label,
        "summary": data.result_summary[:100],
    }]

    # 2. 创建新发现子节点
    new_node_ids = []
    for discovery_label in data.new_discoveries:
        new_id = f"node-{uuid.uuid4().hex[:8]}"
        new_node = ThinkNode(
            id=new_id,
            map_id=map_id,
            parent_id=root.id,
            type="leaf",
            label=discovery_label,
            status="discussing",
            created_by="reflect",
        )
        db.add(new_node)
        new_node_ids.append(new_id)
        reflect_events.append({
            "type": "new_discovery",
            "node_id": new_id,
            "label": discovery_label,
            "summary": f"在执行「{node.label}」时发现",
        })

    tmap.version += 1
    tmap.updated_at = utcnow()
    db.commit()

    # 3. 自动重新收敛 + 排序（如果有新发现）
    re_converge = None
    re_prioritize = None
    if new_node_ids:
        # 调用收敛（复用之前的聚类逻辑）
        discussing = db.query(ThinkNode).filter(
            ThinkNode.map_id == map_id,
            ThinkNode.status.in_(["discussing", "created"]),
        ).all()
        # 简化：把新节点标记为 refined（暂不聚类）
        for dn in discussing:
            dn.status = "refined"

        # 调用排序
        refined = db.query(ThinkNode).filter(
            ThinkNode.map_id == map_id,
            ThinkNode.status == "refined",
        ).order_by(ThinkNode.queue_order).all()
        if refined:
            # 更新 queue_order：追加到末尾
            max_order = max((n.queue_order or 0) for n in refined)
            for idx, rn in enumerate(refined):
                if rn.queue_order is None or rn.queue_order == 0:
                    max_order += 1
                    rn.queue_order = max_order
                    rn.priority = 3  # 新发现默认 P3
            db.commit()

        re_converge = True
        re_prioritize = True

    # 刷新返回
    db.refresh(tmap)
    tmap.nodes
    return {
        "map_id": map_id,
        "events": reflect_events,
        "new_node_ids": new_node_ids,
        "re_converge": re_converge,
        "re_prioritize": re_prioritize,
        "thinking_map": {
            "id": tmap.id,
            "title": tmap.title,
            "status": tmap.status,
            "version": tmap.version,
            "nodes": [n.to_schema_dict() for n in tmap.nodes],
        },
    }


# ═══ 工具卡片 ═══
def _build_tool_cards(tool_results: list[dict]) -> list[dict]:
    """将预执行工具结果转为前端可渲染的卡片数据

    Returns:
        [{"type": "weather"|"attractions"|"equipment", "data": {...}}, ...]
    """
    cards = []
    for r in tool_results:
        if not r.get("success") or not r.get("result"):
            continue
        tool = r["tool"]
        res = r["result"]

        if tool == "get_weather" and isinstance(res, dict):
            cards.append({
                "type": "weather",
                "data": {
                    "city": res.get("city", ""),
                    "desc": res.get("desc", ""),
                    "temp": res.get("temp", ""),
                    "humidity": res.get("humidity", ""),
                    "wind": res.get("wind", ""),
                    "forecast": res.get("forecast", []),
                    "hourly": res.get("hourly", []),
                },
            })

        elif tool == "recommend_attractions" and isinstance(res, dict):
            cards.append({
                "type": "attractions",
                "data": {
                    "city": res.get("city", ""),
                    "category_label": res.get("category_label", ""),
                    "default_category": res.get("default_category", ""),
                    "total_matched": res.get("total_matched", 0),
                    "items": [
                        {
                            "name": it.get("name", ""),
                            "category": it.get("category", ""),
                            "tags": it.get("tags", []),
                            "indoor": it.get("indoor", False),
                            "note": it.get("note", ""),
                            "score": it.get("score", 0),
                        }
                        for it in (res.get("items", []) or [])
                    ],
                },
            })

        elif tool == "get_equipment_checklist" and isinstance(res, dict):
            items = res.get("items", []) or []
            cards.append({
                "type": "equipment",
                "data": {
                    "label": res.get("label", ""),
                    "icon": res.get("icon", ""),
                    "default_category": res.get("default_category", ""),
                    "total": res.get("total", 0),
                    "must_have": res.get("must_have", 0),
                    "recommended": res.get("recommended", 0),
                    "optional": res.get("optional", 0),
                    "items": [
                        {
                            "name": it.get("name", ""),
                            "necessity": it.get("necessity", ""),
                            "note": it.get("note", ""),
                        }
                        for it in items
                    ],
                },
            })

    return cards


# ═══ 场景记忆提取（跨会话持久化） ═══


@router.post("/api/scenes/{scene_id}/extract-memory")
def extract_scene_memory(scene_id: str, db: Session = Depends(get_db)):
    """从场景的最新对话中提取关键信息，存为场景级记忆

    由前端在用户切走场景 / 页面关闭时触发。
    不阻塞前端（快速返回），在后台完成 LLM 提取 + 写入。
    """
    scene = _get_scene_or_404(db, scene_id)

    # 读取最近的消息
    msgs = (
        db.query(Message)
        .filter(Message.scene_id == scene_id, Message.role.in_(["user", "ai"]))
        .order_by(Message.created_at.desc())
        .limit(30)
        .all()
    )
    msgs.reverse()
    if len(msgs) < 2:
        return {"ok": True, "extracted": 0, "reason": "对话太短，无需提取"}

    messages_dict = [{"role": m.role, "content": m.content} for m in msgs]

    # 调 LLM 提取
    from agent_core.memory_extractor import extract_from_conversation, save_extracted_memories

    entries = extract_from_conversation(messages_dict, scene_name=scene.name)
    if not entries:
        return {"ok": True, "extracted": 0, "reason": "无值得记忆的内容"}

    saved = save_extracted_memories(db, entries, scene_id, scene_name=scene.name)
    db.commit()

    return {"ok": True, "extracted": saved, "total_candidates": len(entries)}


# ═══ 场景流式 ═══

@router.post("/api/scenes/{scene_id}/stream")
def stream_scene_message(scene_id: str, data: MessageCreate, db: Session = Depends(get_db)):
    """发送消息到场景 + 流式 SSE 返回 AI 回复"""
    scene = _get_scene_or_404(db, scene_id)

    user_msg = Message(
        id=make_id("msg"), scene_id=scene_id,
        role="user", content=data.content, session_id=data.session_id,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    def generate():
        nonlocal scene
        # 1. 用户消息事件
        yield sse_event("user_msg", id=user_msg.id, role="user",
                        content=user_msg.content, created_at=user_msg.created_at.isoformat())

        # 2. 历史消息（session 隔离）
        q = db.query(Message).filter(Message.scene_id == scene_id)
        if data.session_id:
            q = q.filter(Message.session_id == data.session_id)
        scene_history = q.order_by(Message.created_at.desc()).limit(20).all()
        scene_history.reverse()
        history_messages = [
            {"role": m.role, "content": m.content}
            for m in scene_history if m.id != user_msg.id
        ]

        # 3. 约束提取 + 路由
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        need_extraction = scene.constraints is None or not scene.constraints_locked
        if need_extraction:
            result = extract_and_classify(data.content, scene.complexity, scene.constraints)
            scene.constraints = result["constraints"]
            scene.complexity = result["complexity"]
            scene.constraints_locked = result["constraints_locked"]
            db.commit()
            complexity, constraints_ok = result["complexity"], result["constraints_locked"]
            missing_info = result.get("missing_info", [])
        else:
            complexity, constraints_ok = scene.complexity or "medium", True
            missing_info = []

        user_ctx = scene.user_context

        # ── Agent Loop：LLM 自主决策调工具（替代预执行 + 规则路由） ──
        from agent_core.agent_loop import run_agent_loop
        from agent_core.context_builder import build_agent_context

        # 用 build_agent_context 构建完整分层的初始消息（DB prompt + 记忆块 + skill + 工具列表）
        agent_messages = build_agent_context(
            user_content=data.content,
            history_messages=history_messages,
            user_context=scene.user_context,
            db=db,
            scene_id=scene_id,
            scene_name=scene.name,
        )

        # 🆕 Dialog Engine: 初始化/恢复阶段状态
        from agent_core.dialog_engine import DialogEngine
        dialog_engine = DialogEngine(db, scene_id)

        # 🆕 Schema v0.8: 本体观察 — 分身启动
        from agent_core.zhu_agent import ZhuAgentManager
        _zhu = ZhuAgentManager(db)
        _zhu.observe_fenshen_event("fenshen:started", scene.name)

        agent_stream = run_agent_loop(
            initial_messages=agent_messages,
            max_steps=15,
            dialog_engine=dialog_engine,
            scene_id=scene_id,  # 🆕 Schema v0.7
        )

        model_name = "DeepSeek Flash"
        full_reply = ""

        yield sse_event("model_info", model=model_name, complexity=complexity)

        # ── Context 用量估算 ──
        api_msgs = history_messages + [{"role": "user", "content": data.content}]
        total_tokens = estimate_messages_tokens(api_msgs)
        max_tokens = get_context_length_from_route(get_settings("scene"))
        pct = round(total_tokens / max_tokens * 100, 1) if max_tokens > 0 else 0
        yield sse_event("context_info",
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            percentage=pct,
            usage_str=context_usage_str(total_tokens, max_tokens),
            progress_bar=progress_bar(pct),
            history_count=len(history_messages),
        )
        if pct >= 75:
            yield sse_event("capacity_warning",
                total_tokens=total_tokens,
                max_tokens=max_tokens,
                percentage=pct,
                message=(
                    f"⚠️ 上下文已使用 {context_usage_str(total_tokens, max_tokens)}，"
                    f"建议压缩摘要或重置会话以避免达到上限。"
                ),
            )

        # ── 流式收 Agent Loop 回复 ──
        agent_tool_results = []
        try:
            for event in agent_stream:
                etype = event["type"]
                if etype == "tool_start":
                    yield sse_event("tool_status", tool=event["tool"], status="running",
                                    message=f"正在执行：{event['tool']}...")
                elif etype == "tool_done":
                    yield sse_event("tool_status", tool=event["tool"], status="done",
                                    success=True, message="已完成")
                    agent_tool_results.append({
                        "tool": event["tool"], "params": {},
                        "result": event.get("result"), "success": True,
                    })
                elif etype == "tool_error":
                    yield sse_event("tool_status", tool=event["tool"], status="error",
                                    success=False, message=event.get("error", "执行失败"))
                    agent_tool_results.append({
                        "tool": event["tool"], "params": {},
                        "result": event.get("error", "执行失败"), "success": False,
                    })
                elif etype == "thinking":
                    text = event["text"]
                    full_reply += text
                    yield sse_event("token", token=text)
                elif etype == "done":
                    full_reply = event.get("summary", full_reply)
                    break
                elif etype == "error":
                    _log.error(f"[scene agent loop] {event['message']}")
                    yield sse_event("error", message=event["message"])
                    return
                # 🆕 Schema v0.7: 仪表盘事件透传
                elif etype == "dashboard:reflect":
                    yield sse_event("dashboard:reflect",
                                    tool=event.get("tool", ""),
                                    tool_success=event.get("tool_success", False),
                                    result_preview=event.get("result_preview", ""))
        except Exception as e:
            _log.error(f"[scene agent loop] 迭代异常: {e}")
            yield sse_event("error", message=f"AI 响应生成异常: {e}")
            return

        # ── 工具卡片（从 Agent Loop 结果重建） ──
        tool_cards = _build_tool_cards(agent_tool_results) if agent_tool_results else []
        if tool_cards:
            yield sse_event("tool_cards", cards=tool_cards)
        tool_results = agent_tool_results or None

        # 5. 保存 AI 消息（独立 DB session）
        ai_msg_id = make_id("msg")
        new_db = SessionLocal()
        try:
            ai_msg = Message(
                id=ai_msg_id, scene_id=scene_id,
                role="ai", content=full_reply,
                session_id=data.session_id, model=model_name,
            )
            new_db.add(ai_msg)
            new_db.commit()
            new_db.refresh(ai_msg)
            yield sse_event("done", id=ai_msg.id, role="ai", content=full_reply,
                            created_at=ai_msg.created_at.isoformat(),
                            changes=[], model=model_name)

            # 🆕 检测 AI 回复中的 HTML 代码块 → 自动保存为产出成果
            try:
                html_match = re.search(
                    r'```html\s*\n(.*?)```',
                    full_reply, re.DOTALL
                )
                if html_match:
                    html_content = html_match.group(1).strip()
                    if len(html_content) > 50:  # 至少 50 字符才算有效 HTML
                        safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', '', scene.name or '产出')[:20]
                        out_dir = Path(__file__).resolve().parent.parent.parent / "outputs" / scene_id
                        out_dir.mkdir(parents=True, exist_ok=True)
                        out_path = out_dir / f"{ai_msg_id}.html"
                        out_path.write_text(html_content, encoding="utf-8")

                        out_rec = ProjectOutput(
                            id=make_id("out"),
                            scene_id=scene_id,
                            title=f"{safe_name} - HTML 页面",
                            description="从对话中自动提取的 HTML 页面",
                            type="html",
                            file_path=f"{scene_id}/{ai_msg_id}.html",
                        )
                        new_db.add(out_rec)
                        new_db.commit()

                        yield sse_event("output:created",
                            output_id=out_rec.id,
                            title=out_rec.title,
                            file_path=out_rec.file_path,
                        )
                        print(f"[output] 自动产出 HTML: {out_rec.file_path}")
            except Exception as e:
                print(f"[output] 自动提取 HTML 失败: {e}")

            # 🆕 Schema v0.8: 本体观察 — 分身完成
            try:
                _zhu.observe_fenshen_event("fenshen:done", scene.name)
            except Exception:
                pass

            # ── 6. 自动提取记忆（双通道） ──
            try:
                # 收集本轮对话
                extract_msgs = [
                    {"role": m.role, "content": m.content}
                    for m in scene_history
                ]
                extract_msgs.append({"role": "user", "content": data.content})
                extract_msgs.append({"role": "ai", "content": full_reply})

                # 双通道提取：快速关键词 + LLM 智能提取
                extractor = MemoryExtractor(db)
                mem_results = extractor.extract(extract_msgs, data.content)
                if mem_results:
                    print(f"[memory] extract: {json.dumps(mem_results, ensure_ascii=False)}")
            except Exception as e:
                print(f"[memory] extract error: {e}")

            # ── 7.5 自动发散（首次消息时自动触发 Thinking Map 拆解） ──
            try:
                tmap = db.query(ThinkingMap).filter(
                    ThinkingMap.scene_id == scene_id
                ).first()
                if tmap:
                    existing = db.query(ThinkNode).filter(
                        ThinkNode.map_id == tmap.id
                    ).all()
                    is_first_msg = len(existing) <= 1 and not any(
                        n.type != "root" for n in existing
                    )
                    if is_first_msg:
                        print(f"[diverge] auto-diverge for scene {scene_id}")
                        # 用这个请求构建 diverge 请求
                        d_ctx = data.content[:500]
                        d_messages = [
                            {"role": "system", "content": (
                                "你是坐山客 AI 工作台的任务拆解专家。"
                                "将用户的目标拆解为思维导图节点树。"
                                "输出 JSON，结构: {\"categories\": [{\"label\": \"类别\", \"nodes\": [{\"label\": \"子任务\"}]}]}"
                            )},
                            {"role": "user", "content": f"目标：{d_ctx}"},
                        ]
                        d_raw = call_deepseek_chat(d_messages, model="flash",
                                                   temperature=0.5, max_tokens=3072,
                                                   route="medium")
                        if d_raw:
                            import json as _json
                            text = d_raw.strip()
                            if "```json" in text:
                                text = text.split("```json")[1].split("```")[0].strip()
                            elif "```" in text:
                                text = text.split("```")[1].split("```")[0].strip()
                            parsed = _json.loads(text) if text.startswith("{") else None
                            if not parsed:
                                start = text.find("{")
                                end = text.rfind("}")
                                if start >= 0 and end > start:
                                    parsed = _json.loads(text[start:end+1])
                            if parsed:
                                categories = parsed.get("categories", []) or parsed.get("nodes", [])
                                name_to_id = {n.label: n.id for n in existing}
                                root = next((n for n in existing if n.type == "root"), None)
                                new_count = 0
                                for cat in categories:
                                    p_label = cat.get("parent_label", cat.get("label", ""))
                                    children = cat.get("nodes", [])
                                    if root and "label" in cat and p_label not in name_to_id:
                                        nid = make_id("n")
                                        node = ThinkNode(
                                            id=nid, map_id=tmap.id, parent_id=root.id,
                                            type="domain", label=p_label,
                                            status="discussing", created_by="brainstorm",
                                        )
                                        db.add(node)
                                        name_to_id[p_label] = nid
                                        new_count += 1
                                    pid = name_to_id.get(p_label, root.id if root else None)
                                    if not pid:
                                        continue
                                    for child in children:
                                        cl = child.get("label", "")
                                        if not cl:
                                            continue
                                        dup = any(
                                            x.parent_id == pid and x.label == cl
                                            for x in existing
                                        )
                                        if not dup:
                                            db.add(ThinkNode(
                                                id=make_id("n"), map_id=tmap.id,
                                                parent_id=pid, type="leaf",
                                                label=cl, status="discussing",
                                                created_by="brainstorm",
                                            ))
                                            new_count += 1
                                if new_count:
                                    tmap.version += 1
                                    tmap.updated_at = utcnow()
                                    db.commit()
                                    print(f"[diverge] auto-diverge created {new_count} nodes")
                                    yield sse_event("thinking_map:diverged",
                                                    node_count=new_count)

                                    # Schema v0.7+改动: 只发散不收敛——收敛交给 LLM 自主调 converge 工具
                                    # 用户讨论充分后，LLM 提议 → 用户确认 → converge 工具触发
            except Exception as e:
                print(f"[diverge] auto-diverge error: {e}")

            # ── 8. 缺工具提案（仅当使用了 web_search 兜底时） ──
            try:
                _was_web_search = any(
                    r.get("tool") == "web_search" for r in (tool_results or [])
                )
                if _was_web_search:
                    from ai_engine import propose_tool
                    proposal = propose_tool(data.content, full_reply, tool_was_used=True)
                    if proposal.get("need_tool"):
                        tool_msg = Message(
                            id=make_id("msg"),
                            scene_id=scene_id,
                            role="system",
                            content=(
                                f"🔧 **系统检测到你可能需要一个工具**\n\n"
                                f"你问「{data.content}」时，系统发现缺少一个名为 "
                                f"**{proposal['tool_name']}** 的通用能力。\n\n"
                                f"> {proposal['reason']}\n\n"
                                f"我已生成了一个工具创建方案，前往 **工坊 → 工具提案** 查看并决定是否创建。"
                            ),
                            session_id=data.session_id,
                        )
                        new_db.add(tool_msg)
                        new_db.commit()
                        yield sse_event("tool_proposal", **proposal)
            except Exception as e:
                print(f"[tool_proposal] 生成失败: {e}")
        except Exception as e:
            print(f"[scene stream save error] {e}")
            yield sse_event("error", message="AI 回复保存失败")
        finally:
            new_db.close()

    return sse_response(generate())


# ═══ 会话管理 ═══

@router.post("/api/scenes/{scene_id}/new-session")
def new_scene_session(scene_id: str, db: Session = Depends(get_db)):
    _get_scene_or_404(db, scene_id)
    session_id = f"ses-{uuid.uuid4().hex[:12]}"
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    scene.constraints = None
    scene.constraints_locked = False
    scene.complexity = None
    db.commit()
    return {"session_id": session_id}


@router.get("/api/scenes/{scene_id}/sessions")
def list_scene_sessions(scene_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import func
    _get_scene_or_404(db, scene_id)
    rows = (
        db.query(Message.session_id, func.max(Message.created_at), func.count(Message.id))
        .filter(Message.scene_id == scene_id, Message.session_id.isnot(None))
        .group_by(Message.session_id)
        .order_by(func.max(Message.created_at).desc())
        .all()
    )
    return [
        {"session_id": r[0], "last_active": r[1].isoformat() if r[1] else None, "message_count": r[2]}
        for r in rows
    ]


# ═══ 类别管理 ═══

@router.get("/api/categories")
def list_categories(db: Session = Depends(get_db)):
    """返回所有类别及其场景数量、图标、中文名 — 合并 DB 元数据 + 场景实际数据"""
    from sqlalchemy import func
    from models import CategoryMeta

    # 1. 获取场景中实际使用的类别及其计数
    scene_counts: dict[str, int] = {}
    for cat_name, count in db.query(Scene.category, func.count(Scene.id)).group_by(Scene.category).all():
        scene_counts[cat_name] = count

    # 2. 从 DB 读取类别元数据（预定义+用户创建）
    metas = db.query(CategoryMeta).order_by(CategoryMeta.sort_order).all()
    meta_map = {m.name: m for m in metas}

    # 3. 合并：所有元数据中的类别 + 场景中用到的但元数据缺失的
    all_keys: set[str] = set(meta_map.keys()) | set(scene_counts.keys())
    categories = []
    for key in all_keys:
        m = meta_map.get(key)
        categories.append({
            "name": key,
            "label": m.label if m else key,
            "icon": m.icon if m else "📦",
            "count": scene_counts.get(key, 0),
        })

    # 4. 排序：有 sort_order 的按 sort_order，没有的排末尾
    categories.sort(key=lambda c: (
        meta_map[c["name"]].sort_order if c["name"] in meta_map else 999,
        c["name"],
    ))
    return categories


@router.post("/api/categories")
def create_category(data: dict, db: Session = Depends(get_db)):
    """创建新类别"""
    from models import CategoryMeta
    from sqlalchemy import func
    name = data.get("name", "").strip().lower()
    label = data.get("label", "").strip()
    icon = data.get("icon", "").strip()

    if not name:
        raise HTTPException(400, "类别英文名不能为空")
    if not label:
        label = name  # 用 name 作为 label

    # 图标自动匹配：未指定时用 label 智能匹配
    if not icon:
        icon = auto_detect_icon(label) or "📁"

    # 检查是否已存在
    existing = db.query(CategoryMeta).filter(CategoryMeta.name == name).first()
    if existing:
        raise HTTPException(409, f"类别「{name}」已存在")

    # 找最大 sort_order
    max_order = db.query(func.max(CategoryMeta.sort_order)).scalar() or 0

    cat = CategoryMeta(
        name=name,
        label=label,
        icon=icon or "📁",
        sort_order=max_order + 1,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)

    return {
        "ok": True,
        "category": {
            "name": cat.name,
            "label": cat.label,
            "icon": cat.icon,
            "count": 0,
        },
    }


@router.delete("/api/categories/{name}")
def delete_category(name: str, db: Session = Depends(get_db)):
    """删除类别元数据（不删除场景，仅清除元数据记录）"""
    from models import CategoryMeta
    cat = db.query(CategoryMeta).filter(CategoryMeta.name == name).first()
    if not cat:
        raise HTTPException(404, f"类别「{name}」不存在")

    db.delete(cat)
    db.commit()
    return {"ok": True, "deleted": name}


@router.put("/api/categories/{name}")
def rename_category(name: str, data: dict, db: Session = Depends(get_db)):
    """重命名类别（更新 CategoryMeta 元数据 + 该类别下所有场景的 category 字段）"""
    from models import CategoryMeta
    new_name = data.get("new_name", "").strip().lower()
    if not new_name:
        raise HTTPException(400, "新类别名不能为空")
    if new_name == name:
        raise HTTPException(400, "新旧名称相同")

    # 更新场景的 category 字段
    count = db.query(Scene).filter(Scene.category == name).update(
        {"category": new_name}, synchronize_session=False
    )
    db.commit()

    # 更新元数据表中的 name（如果存在）
    meta = db.query(CategoryMeta).filter(CategoryMeta.name == name).first()
    if meta:
        meta.name = new_name
        db.commit()

    return {"ok": True, "updated": count, "old_name": name, "new_name": new_name}


# ═══ Agent Loop 执行引擎 ═══

from pydantic import Field as PydanticField

class AgentLoopRequest(BaseModel):
    task: str = PydanticField(..., description="任务描述")
    model: str = PydanticField("flash", description="模型: flash / pro")
    scene_id: Optional[str] = PydanticField(None, description="关联的场景 ID（可选）")
    memory_context: str = PydanticField("", description="额外上下文/记忆信息")


@router.post("/api/agent-loop/stream")
def stream_agent_loop(data: AgentLoopRequest, db: Session = Depends(get_db)):
    """Agent Loop：用 LLM 自主调工具完成任务，SSE 流式输出每一步。

    流程：
      1. LLM 收到任务 + 工具定义
      2. LLM 决定调什么工具 → 后端执行 → 结果喂回
      3. 重复直到 LLM 返回最终回复
      4. SSE 流式输出每一步状态
    """
    from agent_core.agent_loop import run_agent_loop

    def generate():
        # 1. 可选：注入场景记忆
        memory_ctx = data.memory_context
        if data.scene_id:
            try:
                mm = MemoryManager(db, data.scene_id)
                ctx = mm.build_context()
                if ctx:
                    memory_ctx += "\n" + ctx
            except Exception:
                pass

        yield sse_event("agent_loop:start", task=data.task[:100], model=data.model)

        # 2. 运行 Agent Loop
        for event in run_agent_loop(
            task=data.task,
            memory_context=memory_ctx,
            model=data.model,
        ):
            event_type = event.pop("type", "unknown")

            if event_type == "status":
                yield sse_event("agent_loop:status", message=event.get("message", ""))

            elif event_type == "tool_start":
                yield sse_event("agent_loop:tool_start",
                                tool=event.get("tool", ""),
                                args=event.get("args", {}),
                                tool_call_id=event.get("tool_call_id", ""))

            elif event_type == "tool_done":
                yield sse_event("agent_loop:tool_done",
                                tool=event.get("tool", ""),
                                result=event.get("result", ""),
                                tool_call_id=event.get("tool_call_id", ""))

            elif event_type == "tool_error":
                yield sse_event("agent_loop:tool_error",
                                tool=event.get("tool", ""),
                                error=event.get("error", ""),
                                tool_call_id=event.get("tool_call_id", ""))

            elif event_type == "thinking":
                yield sse_event("agent_loop:thinking",
                                text=event.get("text", ""))

            elif event_type == "token":
                yield sse_event("agent_loop:token",
                                token=event.get("text", ""))

            elif event_type == "done":
                yield sse_event("agent_loop:done",
                                summary=event.get("summary", ""),
                                steps=event.get("steps", 0),
                                finish_reason=event.get("finish_reason", ""))

            elif event_type == "error":
                yield sse_event("agent_loop:error",
                                message=event.get("message", ""))

            else:
                # 透传未知事件
                yield sse_event(f"agent_loop:{event_type}", **event)

        # 3. 完成标记
        yield sse_event("done", type="agent_loop", task=data.task[:100])

    return sse_response(generate())


# ═══ 辅助函数 ═══

def _get_scene_or_404(db: Session, scene_id: str):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    return scene


# ═══ web_search 兜底触发判断 ═══

def _needs_search_fallback(text: str) -> bool:
    """判断用户消息是否需要走 web_search 兜底（模型驱动）

    简单预过滤后，用 Qwen 做二分类判断。
    调用失败时保守返回 False（不搜）。
    """
    if not text or not text.strip():
        return False
    t = text.strip()

    # 极简预过滤：太短或纯语气词/问候，省一次模型调用
    if len(t) < 4:
        return False
    stopwords = {"嗯","哦","好","行","是","不","嗨","哈","嘿",
                 "好的","好吧","是的","不是","没错","不对",
                 "谢谢","感谢","你好","您好","再见","拜拜",
                 "在吗","嗯嗯","哦哦","哈哈","呵呵"}
    if t in stopwords:
        return False

    from ai_engine import should_web_search
    return should_web_search(t)
