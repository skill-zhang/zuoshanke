"""场景 + Thinking Map CRUD + 场景流式 + 场景广场/工坊/发布/导入导出"""
import difflib
import json
import os
import re
import time
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
from utils import make_id, utcnow, iso_utc
from router.shared import sse_event, sse_response

router = APIRouter(tags=["场景"])

# ── 导入子模块路由 ──
from router.thinking_map import router as thinking_map_router
router.include_router(thinking_map_router)
from router.scene_stream import router as scene_stream_router
router.include_router(scene_stream_router)

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
    # 新建场景默认填入系统人设作为背景设定
    from models import DEFAULT_SYSTEM_PROMPTS
    default_prompt = DEFAULT_SYSTEM_PROMPTS["scene"]
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
    # 点进场景 → 按需加载分身记忆到缓存
    from agent_core.memory_cache import MemoryCache
    MemoryCache.get_instance().load_scope(db, "scene", scene_id)
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
            # 显式传 null/空 → 恢复为默认人设
            from models import DEFAULT_SYSTEM_PROMPTS
            scene.user_context = DEFAULT_SYSTEM_PROMPTS["scene"]
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
    # ── Schema v0.81: 收敛/发散参数 ──
    if data.converge_threshold is not None:
        scene.converge_threshold = data.converge_threshold
    if data.converge_enabled is not None:
        scene.converge_enabled = data.converge_enabled
    if data.diverge_min_rounds is not None:
        scene.diverge_min_rounds = data.diverge_min_rounds
    if data.scene_config is not None:
        scene.scene_config = data.scene_config
    # ── Schema v1.3: 工作台 ──
    if data.show_on_workbench is not None:
        scene.show_on_workbench = data.show_on_workbench
    if data.workbench_position is not None:
        scene.workbench_position = data.workbench_position
    scene.updated_at = utcnow()
    db.commit()
    db.refresh(scene)
    return scene


@router.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id: str, db: Session = Depends(get_db)):
    scene = _get_scene_or_404(db, scene_id)
    # 级联清理关联数据
    from models import Message, ThinkingMap, ThinkNode, PriorityQueue, ReflectTimeline, SceneAsset, DialogState, OutputProject, SceneSelfMap
    db.query(SceneSelfMap).filter(SceneSelfMap.scene_id == scene_id).delete()
    db.query(DialogState).filter(DialogState.scene_id == scene_id).delete()
    db.query(SceneAsset).filter(SceneAsset.scene_id == scene_id).delete()
    db.query(PriorityQueue).filter(PriorityQueue.scene_id == scene_id).delete()
    db.query(ReflectTimeline).filter(ReflectTimeline.scene_id == scene_id).delete()
    # 清理项目和产出关联
    db.query(OutputProject).filter(OutputProject.scene_id == scene_id).delete()
    from models import ProjectOutput
    db.query(ProjectOutput).filter(ProjectOutput.scene_id == scene_id).delete()
    tm = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    if tm:
        db.query(ThinkNode).filter(ThinkNode.map_id == tm.id).delete()
        db.delete(tm)
    db.query(Message).filter(Message.scene_id == scene_id).delete()
    db.delete(scene)
    db.commit()
    return {"ok": True}


# ═══ 刷新股价 ═══

@router.post("/api/scenes/{scene_id}/refresh-stock", response_model=SceneOut)
def refresh_stock(scene_id: str, db: Session = Depends(get_db)):
    """刷新小米股价实时数据（腾讯行情接口）"""
    import urllib.request
    scene = _get_scene_or_404(db, scene_id)
    try:
        url = "https://qt.gtimg.cn/q=hk01810"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("gbk")
        # 解析腾讯行情格式: v_hk01810="100~name~code~price~yclose~open~..."
        import re
        m = re.search(r'"([^"]+)"', raw)
        if not m:
            raise ValueError("无法解析行情数据")
        fields = m.group(1).split("~")
        # 索引: 1=名称, 3=当前价, 4=昨收, 5=开盘, 30=时间, 31=涨跌额, 32=涨跌幅, 33=最高, 34=最低, 36=成交量, 37=成交额
        name = fields[1] if len(fields) > 1 else "小米集团-W"
        price = fields[3] if len(fields) > 3 else "0"
        yclose = fields[4] if len(fields) > 4 else "0"
        change = fields[31] if len(fields) > 31 else "0"
        change_pct = fields[32] if len(fields) > 32 else "0%"
        high = fields[33] if len(fields) > 33 else "0"
        low = fields[34] if len(fields) > 34 else "0"
        volume_raw = fields[36] if len(fields) > 36 else "0"
        amount_raw = fields[37] if len(fields) > 37 else "0"
        time_str = fields[30] if len(fields) > 30 else ""

        # 格式化成交量/成交额
        try:
            vol = int(float(volume_raw))
            if vol > 100000000:
                volume = f"{vol/100000000:.2f}亿"
            elif vol > 10000:
                volume = f"{vol/10000:.2f}万"
            else:
                volume = str(vol)
        except:
            volume = volume_raw

        try:
            amt = float(amount_raw)
            if amt > 100000000:
                market_cap = f"{amt/100000000:.0f}亿HKD"
            else:
                market_cap = f"{amt/10000:.0f}万HKD"
        except:
            market_cap = amount_raw

        # 涨跌额带符号
        change_str = f"{float(change):+.2f}" if change else "0.00"
        change_pct_str = f"{float(change_pct):+.2f}%" if change_pct else "0.00%"

        stock_data = {
            "name": name,
            "code": "01810.HK",
            "price": price,
            "change": change_str,
            "change_pct": change_pct_str,
            "high": high,
            "low": low,
            "volume": volume,
            "market_cap": market_cap,
            "currency": "HKD",
            "time": time_str,
        }
        existing = dict(scene.scene_config or {})
        existing["stock"] = stock_data
        scene.scene_config = existing
        scene.updated_at = utcnow()
        db.commit()
        db.refresh(scene)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[refresh-stock] 刷新失败: {e}")
        raise HTTPException(502, f"获取股价数据失败: {e}")
    return scene


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
        {"session_id": r[0], "last_active": iso_utc(r[1]) if r[1] else None, "message_count": r[2]}
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
    session_id: str = PydanticField("", description="会话 ID（可选，用于 trace）")


@router.get("/api/scenes/{scene_id}/traces")
def get_scene_traces(scene_id: str, limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    """查询场景的 Agent Loop 执行 trace 记录"""
    _get_scene_or_404(db, scene_id)
    from agent_core.trace_logger import query_traces
    traces = query_traces(db, scene_id, limit=limit, offset=offset)
    return {"traces": traces, "count": len(traces)}


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
            scene_id=data.scene_id or "",
            session_id=data.session_id or "",
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


def _persist_scene_reply(scene_id: str, content: str, session_id: str, model_name: str) -> None:
    """保存 AI 回复到数据库，无 yield，可在 GeneratorExit 中断连时安全调用"""
    if not content:
        return
    save_db = SessionLocal()
    try:
        msg = Message(
            id=make_id("msg"), scene_id=scene_id,
            role="ai", content=content,
            session_id=session_id, model=model_name,
        )
        save_db.add(msg)
        save_db.commit()
    except Exception:
        pass
    finally:
        save_db.close()


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
