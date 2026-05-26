"""用户画像 — Schema v1.4 Phase 2 API

提供暂存区管理、正式库 CRUD、以及 LLM 批量判重合并的触发端点。
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import PendingUserTrait, UserProfile

_log = logging.getLogger(__name__)

router = APIRouter(tags=["用户画像"])


# ── Pydantic Schemas ──

class PendingTraitOut(BaseModel):
    id: str
    content: str
    source_scene: Optional[str] = None
    source_scene_id: Optional[str] = None
    confidence: str = "medium"
    context_snippet: Optional[str] = None
    status: str = "pending"
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ProfileOut(BaseModel):
    id: str
    key: str
    content: str
    category: str = "preference"
    priority: str = "P2"
    tags: list = []
    source_scenes: list = []
    merged_from: list = []
    is_active: bool = True
    deprecated_by: Optional[str] = None
    total_injections: int = 0
    last_injected_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[list] = None
    is_active: Optional[bool] = None


class ProcessResult(BaseModel):
    success: bool
    message: str
    stats: Optional[dict] = None


# ── 工具函数 ──

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


# ── 暂存区端点 ──

@router.get("/api/user-profile/pending")
def list_pending_traits(db: Session = Depends(get_db)):
    """列出所有待处理的暂存条目"""
    traits = db.query(PendingUserTrait).order_by(PendingUserTrait.created_at.desc()).all()
    return {
        "success": True,
        "data": [_row_to_pending(t) for t in traits],
        "total": len(traits),
    }


@router.post("/api/user-profile/pending")
def create_pending_trait(
    content: str = Query(..., description="分身提取的描述"),
    source_scene: str = Query(""),
    source_scene_id: str = Query(""),
    confidence: str = Query("medium", description="high/medium/low"),
    context_snippet: str = Query(""),
    db: Session = Depends(get_db),
):
    """分身调用 — 写入暂存区（严格精确去重，不走文本反序列化）"""
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    # 精确去重：同内容且 pending 状态的不重复提
    existing = db.query(PendingUserTrait).filter(
        PendingUserTrait.content == content,
        PendingUserTrait.status == "pending",
    ).first()
    if existing:
        return {
            "success": True,
            "id": existing.id,
            "deduped": True,
            "message": "已合并到现有暂存条目",
        }

    trait = PendingUserTrait(
        id=_make_trait_id(),
        content=content,
        source_scene=source_scene or None,
        source_scene_id=source_scene_id or None,
        confidence=confidence,
        context_snippet=context_snippet or None,
        status="pending",
    )
    db.add(trait)
    db.commit()
    return {
        "success": True,
        "id": trait.id,
        "deduped": False,
        "message": f"用户特征已提取，等待自动合入正式库",
    }


@router.post("/api/user-profile/pending/{trait_id}/accept")
def accept_pending_trait(trait_id: str, db: Session = Depends(get_db)):
    """用户手动接受单条暂存条目 → 直接写入正式库"""
    trait = db.query(PendingUserTrait).filter(
        PendingUserTrait.id == trait_id,
        PendingUserTrait.status == "pending",
    ).first()
    if not trait:
        raise HTTPException(status_code=404, detail="暂存条目不存在或已处理")

    # 写入正式库
    key = _content_to_key(trait.content)
    profile = UserProfile(
        id=_make_profile_id(),
        key=key,
        content=trait.content,
        category="preference",
        priority=_confidence_to_priority(trait.confidence),
        source_scenes=[trait.source_scene] if trait.source_scene else [],
        merged_from=[trait.id],
    )
    db.add(profile)
    trait.status = "merged"
    trait.merged_into = key
    db.commit()

    return {"success": True, "profile_id": profile.id, "key": key}


@router.post("/api/user-profile/pending/{trait_id}/reject")
def reject_pending_trait(trait_id: str, db: Session = Depends(get_db)):
    """用户手动拒绝单条暂存条目"""
    trait = db.query(PendingUserTrait).filter(
        PendingUserTrait.id == trait_id,
        PendingUserTrait.status == "pending",
    ).first()
    if not trait:
        raise HTTPException(status_code=404, detail="暂存条目不存在或已处理")
    trait.status = "rejected"
    db.commit()
    return {"success": True, "message": "已拒绝"}


# ── 正式库端点 ──

@router.get("/api/user-profile")
def list_profiles(
    category: str = Query("", description="筛选分类"),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    """按优先级分组列出正式画像"""
    query = db.query(UserProfile)
    if category:
        query = query.filter(UserProfile.category == category)
    if active_only:
        query = query.filter(UserProfile.is_active == True)

    rows = query.order_by(UserProfile.updated_at.desc()).all()

    grouped = {"P0": [], "P1": [], "P2": [], "P3": []}
    for r in rows:
        p = r.priority or "P2"
        if p not in grouped:
            p = "P2"
        grouped[p].append(_row_to_profile(r))

    return {
        "success": True,
        "profiles": {k: v for k, v in grouped.items() if v},
        "total": len(rows),
    }


@router.get("/api/user-profile/{key}")
def get_profile(key: str, db: Session = Depends(get_db)):
    """获取单条正式画像"""
    profile = db.query(UserProfile).filter(UserProfile.key == key).first()
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    return {"success": True, "data": _row_to_profile(profile)}


@router.put("/api/user-profile/{key}")
def update_profile(key: str, update: ProfileUpdate, db: Session = Depends(get_db)):
    """编辑正式画像"""
    profile = db.query(UserProfile).filter(UserProfile.key == key).first()
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")

    if update.content is not None:
        profile.content = update.content
    if update.category is not None:
        profile.category = update.category
    if update.priority is not None:
        profile.priority = update.priority
    if update.tags is not None:
        profile.tags = update.tags
    if update.is_active is not None:
        profile.is_active = update.is_active
        if not update.is_active:
            # 记录谁替代了它
            pass

    profile.updated_at = _utcnow()
    db.commit()
    return {"success": True, "data": _row_to_profile(profile)}


@router.delete("/api/user-profile/{key}")
def soft_delete_profile(key: str, db: Session = Depends(get_db)):
    """软删正式画像"""
    profile = db.query(UserProfile).filter(UserProfile.key == key).first()
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    profile.is_active = False
    profile.updated_at = _utcnow()
    db.commit()
    return {"success": True, "message": "已软删"}


# ── 批量处理端点 ──

@router.post("/api/user-profile/process", response_model=ProcessResult)
def trigger_process(db: Session = Depends(get_db)):
    """手动触发批量处理：LLM 判重合并暂存区 → 写入正式库"""
    pending = db.query(PendingUserTrait).filter(
        PendingUserTrait.status == "pending",
    ).all()

    if not pending:
        return ProcessResult(
            success=True,
            message="暂存区为空，无需处理",
            stats={"pending_count": 0, "merged": 0, "new_profiles": 0, "discarded": 0},
        )

    # 交由 LLM 批量判重
    try:
        result = _run_llm_dedup(pending, db)
        return ProcessResult(
            success=True,
            message=result.get("message", "处理完成"),
            stats=result.get("stats"),
        )
    except Exception as e:
        _log.error(f"LLM 判重处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {e}")


# ── LLM 判重合并引擎 ──

def _run_llm_dedup(pending: list, db: Session) -> dict:
    """将 pending 暂存区 + 现有正式库打包发给 LLM，按返回方案执行"""
    existing_profiles = db.query(UserProfile).filter(
        UserProfile.is_active == True,
    ).all()

    # 构建 prompt
    prompt = _build_dedup_prompt(pending, existing_profiles)

    # 调 LLM
    llm_result = _call_llm_for_dedup(prompt)

    # 解析并执行
    stats = {"pending_count": len(pending), "merged": 0, "new_profiles": 0, "discarded": 0, "merged_into_existing": 0}

    try:
        decision = json.loads(llm_result)
        groups = decision.get("merged_groups", [])

        for group in groups:
            action = group.get("action", "new_profile")
            pending_ids = group.get("pending_ids", [])

            if action == "discard":
                # 标记为 rejected
                db.query(PendingUserTrait).filter(
                    PendingUserTrait.id.in_(pending_ids),
                ).update({"status": "rejected"}, synchronize_session=False)
                stats["discarded"] += len(pending_ids)

            elif action == "merge_into_existing":
                # 合入已有正式画像
                existing_key = group.get("existing_key", "")
                existing = db.query(UserProfile).filter(
                    UserProfile.key == existing_key,
                    UserProfile.is_active == True,
                ).first()
                if existing:
                    # 追加来源场景
                    source_scenes = []
                    for pid in pending_ids:
                        t = db.query(PendingUserTrait).filter(PendingUserTrait.id == pid).first()
                        if t and t.source_scene and t.source_scene not in (existing.source_scenes or []):
                            source_scenes.append(t.source_scene)
                    existing.source_scenes = list(set((existing.source_scenes or []) + source_scenes))
                    existing.merged_from = list(set((existing.merged_from or []) + pending_ids))
                    existing.updated_at = _utcnow()

                    # 标记暂存条目
                    db.query(PendingUserTrait).filter(
                        PendingUserTrait.id.in_(pending_ids),
                    ).update({
                        "status": "merged",
                        "merged_into": existing_key,
                    }, synchronize_session=False)
                    stats["merged_into_existing"] += len(pending_ids)

            else:  # merge 或 new_profile
                content = group.get("content", "")
                category = group.get("category", "preference")
                priority = group.get("priority", "P2")
                tags = group.get("tags", [])

                # 收集来源场景
                source_scenes = []
                for pid in pending_ids:
                    t = db.query(PendingUserTrait).filter(PendingUserTrait.id == pid).first()
                    if t and t.source_scene and t.source_scene not in source_scenes:
                        source_scenes.append(t.source_scene)

                key = _content_to_key(content)

                # 检查是否与已有正式库重复
                existing = db.query(UserProfile).filter(
                    UserProfile.key == key,
                    UserProfile.is_active == True,
                ).first()

                if existing:
                    # 更新已有
                    existing.source_scenes = list(set((existing.source_scenes or []) + source_scenes))
                    existing.merged_from = list(set((existing.merged_from or []) + pending_ids))
                    existing.updated_at = _utcnow()
                    if content != existing.content:
                        # 内容有更新，记录修正历史
                        trail = list(existing.correction_trail or [])
                        trail.append({
                            "old": existing.content,
                            "new": content,
                            "reason": group.get("reason", "LLM 判重更新"),
                            "timestamp": _iso(_utcnow()),
                        })
                        existing.correction_trail = trail
                        existing.content = content
                else:
                    profile = UserProfile(
                        id=_make_profile_id(),
                        key=key,
                        content=content,
                        category=category,
                        priority=priority,
                        tags=tags,
                        source_scenes=source_scenes,
                        merged_from=pending_ids,
                    )
                    db.add(profile)

                # 标记暂存条目
                db.query(PendingUserTrait).filter(
                    PendingUserTrait.id.in_(pending_ids),
                ).update({
                    "status": "merged",
                    "merged_into": key,
                }, synchronize_session=False)

                stats["merged" if len(pending_ids) > 1 else "new_profiles"] += 1

        db.commit()
        return {
            "message": f"处理完成: {stats['merged']} 组合并, {stats['new_profiles']} 条独立入库, "
                       f"{stats['merged_into_existing']} 条合入已有, {stats['discarded']} 条丢弃",
            "stats": stats,
        }
    except json.JSONDecodeError as e:
        _log.error(f"LLM 返回非 JSON: {llm_result[:200]}")
        raise ValueError(f"LLM 返回格式错误: {e}")


def _build_dedup_prompt(pending: list, existing_profiles: list) -> list[dict]:
    """构建 LLM 判重 prompt"""
    system_prompt = """你是一个用户画像去重合并专家。你的任务是对待处理的用户特征进行语义去重和分类。

## 输入
你收到两批数据：
1. 待处理条目（pending_user_traits）— 各分身提取的用户特征，可能有重复、噪音
2. 现有正式画像（user_profiles）— 已入库的经过验证的用户特征

## 你的任务
判断每条待处理条目应该如何处理。返回一个 JSON 对象。

## 返回格式（严格 JSON，不要多余文字）
{
  "merged_groups": [
    {
      "pending_ids": ["id1", "id2"],
      "action": "merge" | "new_profile" | "merge_into_existing" | "discard",
      "reason": "为什么这么判断",
      "content": "合并后的画像内容（仅 merge/new_profile 时需要）",
      "category": "principle" | "preference" | "habit" | "context" (仅 merge/new_profile 时需要),
      "priority": "P0" | "P1" | "P2" | "P3" (仅 merge/new_profile 时需要),
      "tags": ["标签1", "标签2"] (仅 merge/new_profile 时需要),
      "existing_key": "xxx" (仅 merge_into_existing 时需要)
    }
  ]
}

## 判断规则
- merge: 多条待处理条目表达的是同一个意思 → 合并为一条完整的描述
- new_profile: 独立的新发现，正式库中不存在 → 直接入库
- merge_into_existing: 与正式库已有画像重复 → 合入已有
- discard: 噪音/闲聊感慨/明显不构成用户偏好的内容 → 丢弃

## 优先级参考
- P0: 核心原则，用户多次强调的铁律（多条 high 证据+场景）
- P1: 重要偏好，多场景验证
- P2: 一般偏好，单条中等置信度
- P3: 临时/弱信号

## 注意
- 严格语义判断，不要相同内容分成两组
- "喜欢简洁界面" ≈ "热爱极简设计" → merge
- "喜欢简洁界面" ≠ "代码审查严格" → 各自独立
- 正式库已有完全一样的 → merge_into_existing
"""

    pending_text = "\n".join(
        f"  [{t.id}] 内容: {t.content} | 来源: {t.source_scene or '未知'} | 置信度: {t.confidence}"
        for t in pending
    )

    existing_text = "（无正式画像）"
    if existing_profiles:
        existing_text = "\n".join(
            f"  [{p.key}] 内容: {p.content} | 分类: {p.category} | 优先级: {p.priority} | 来源: {', '.join(p.source_scenes or [])}"
            for p in existing_profiles
        )

    user_prompt = f"""## 待处理条目
{pending_text}

## 现有正式画像
{existing_text}

请判断每条待处理条目应如何处理，按指定 JSON 格式返回。"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _call_llm_for_dedup(messages: list[dict]) -> str:
    """调用 LLM 进行判重"""
    from ai_engine import call_llm, get_settings

    route_cfg = get_settings("extraction")  # 用小模型即可，判重不需要大模型
    route_cfg["temperature"] = 0.1  # 低温度保证一致性
    result = call_llm(messages, route_cfg, temperature=0.1)
    return result


# ── 自动调度器 ──

_PROCESSING_LOCK = threading.Lock()
_LAST_PROCESSED_AT: Optional[datetime] = None


def start_profile_processing_scheduler():
    """启动用户画像自动处理线程（每60秒检查一次，条件触发则执行LLM判重合并）"""
    _log.info("🔄 用户画像自动处理调度器启动（每60秒扫描）")
    thread = threading.Thread(target=_scheduler_loop, daemon=True)
    thread.start()


def _scheduler_loop():
    global _LAST_PROCESSED_AT
    while True:
        time.sleep(60)
        try:
            db = SessionLocal()
            try:
                pending_count = db.query(PendingUserTrait).filter(
                    PendingUserTrait.status == "pending",
                ).count()

                if pending_count == 0:
                    continue

                # 触发条件：
                # 1. pending ≥ 5 条
                # 2. 距上次处理 ≥ 30 分钟
                now = _utcnow()
                time_elapsed = (now - (_LAST_PROCESSED_AT or datetime.min.replace(tzinfo=timezone.utc))).total_seconds()
                should_process = (
                    pending_count >= 5
                    or (_LAST_PROCESSED_AT is None)
                    or time_elapsed >= 1800  # 30分钟
                )

                if not should_process:
                    continue

                if _PROCESSING_LOCK.acquire(blocking=False):
                    try:
                        _log.info(f"🔄 用户画像自动处理触发: {pending_count} 条待处理")
                        pending = db.query(PendingUserTrait).filter(
                            PendingUserTrait.status == "pending",
                        ).all()
                        result = _run_llm_dedup(pending, db)
                        _LAST_PROCESSED_AT = _utcnow()
                        _log.info(f"✅ 画像自动处理完成: {result.get('message', '')}")
                    finally:
                        _PROCESSING_LOCK.release()
            finally:
                db.close()
        except Exception as e:
            _log.warning(f"画像自动处理调度器异常: {e}")


# ── 辅助函数 ──

def _make_trait_id() -> str:
    return f"pt-{uuid4().hex[:12]}"


def _make_profile_id() -> str:
    return f"up-{uuid4().hex[:12]}"


def _content_to_key(content: str) -> str:
    """从内容生成唯一 key"""
    import re
    # 取前6个中文字符或前20个字符，降级为 ID 前缀
    cleaned = re.sub(r"[^\u4e00-\u9fff\w]", "", content)[:20]
    if not cleaned:
        cleaned = "profile"
    return f"{cleaned}-{uuid4().hex[:6]}"


def _confidence_to_priority(confidence: str) -> str:
    mapping = {"high": "P1", "medium": "P2", "low": "P3"}
    return mapping.get(confidence, "P2")


def _row_to_pending(t) -> dict:
    return {
        "id": t.id,
        "content": t.content,
        "source_scene": t.source_scene,
        "source_scene_id": t.source_scene_id,
        "confidence": t.confidence,
        "context_snippet": t.context_snippet,
        "status": t.status,
        "merged_into": t.merged_into,
        "created_at": _iso(t.created_at),
    }


def _row_to_profile(r) -> dict:
    return {
        "id": r.id,
        "key": r.key,
        "content": r.content,
        "category": r.category,
        "priority": r.priority,
        "tags": r.tags or [],
        "source_scenes": r.source_scenes or [],
        "merged_from": r.merged_from or [],
        "is_active": r.is_active,
        "deprecated_by": r.deprecated_by,
        "correction_trail": r.correction_trail or [],
        "total_injections": r.total_injections,
        "last_injected_at": _iso(r.last_injected_at),
        "created_at": _iso(r.created_at),
        "updated_at": _iso(r.updated_at),
    }
