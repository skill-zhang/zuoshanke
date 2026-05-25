"""系统设置路由 — Settings API

三层分层：
① 服务运维层 -> GET /api/settings/service（实时拉 llama-server 状态，不存 DB）
② 模型路由层 -> GET/PATCH /api/settings（持久化到 DB）
③ 人设/能力层 -> 同属 /api/settings（暂 disable 编辑）
"""
import json
import requests
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Setting, SETTINGS_ID
from schemas import SettingsOut, SettingsUpdate, ServiceStatusOut, RouteConfig, SystemPrompts, Features

router = APIRouter(tags=["系统设置"])

# 已知路由键
KNOWN_ROUTES = {"channel", "scene", "extraction", "medium", "heavy"}


# ── 内存缓存 ──
_settings_cache: dict | None = None


def invalidate_settings_cache():
    """PATCH 后调用，下次 GET 重新加载"""
    global _settings_cache
    _settings_cache = None


def get_cached_settings(db: Session) -> dict:
    """读取设置（缓存优先）"""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    s = db.query(Setting).filter(Setting.id == SETTINGS_ID).first()
    if s is None:
        # 空 DB 返回默认
        from models import DEFAULT_ROUTING, DEFAULT_SYSTEM_PROMPTS
        _settings_cache = {
            "routing": DEFAULT_ROUTING,
            "system_prompts": DEFAULT_SYSTEM_PROMPTS,
            "features": {"pdf_as_image": False, "vision_enabled": False, "message_load_count": 4},
            "updated_at": None,
        }
    else:
        _settings_cache = {
            "routing": s.routing or {},
            "system_prompts": s.system_prompts or {},
            "features": s.features or {},
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
    # 🆕 对旧数据自动补全 provider_id/model_id
    _enrich_routing(db, _settings_cache["routing"])
    # 🆕 清理未知路由键
    _settings_cache["routing"] = {k: v for k, v in _settings_cache["routing"].items() if k in KNOWN_ROUTES}
    return _settings_cache


def _enrich_routing(db: Session, routing: dict):
    """自动补全路由中缺失的 provider_id 和 model_id"""
    try:
        from models import AiProvider, AiModel
    except ImportError:
        return
    for route_cfg in routing.values():
        if not route_cfg.get("provider_id") or not route_cfg.get("model_id"):
            provider_str = route_cfg.get("provider", "")
            # 先按名称匹配，再按 provider_type 兜底
            p = db.query(AiProvider).filter(
                (AiProvider.name.ilike(provider_str)) |
                (AiProvider.name.ilike(f"%{provider_str}%"))
            ).first()
            if not p:
                # 兜底：provider_type='local' 或 provider_type='openai-compatible' 的第一个
                p = db.query(AiProvider).filter(
                    AiProvider.provider_type == (provider_str if provider_str in ("local",) else "openai-compatible")
                ).first()
            if p:
                route_cfg["provider_id"] = p.id
                m = db.query(AiModel).filter(
                    AiModel.provider_id == p.id,
                    AiModel.name.ilike(route_cfg.get("model", ""))
                ).first()
                if m:
                    route_cfg["model_id"] = m.id


def _model_validate_routing(routing: dict) -> dict:
    """将 raw dict 罗盘转为 RouteConfig 对象并转回 dict（含校验）"""
    result = {}
    for key, cfg in routing.items():
        result[key] = RouteConfig(**cfg).model_dump()
    return result


# ── ② 模型路由层 + ③ 人设/能力层 ──


@router.get("/api/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    """读取全部系统设置（含模型路由、人设、特性开关）"""
    cached = get_cached_settings(db)

    routing = {}
    for key, cfg in cached["routing"].items():
        if key not in KNOWN_ROUTES:
            continue
        try:
            routing[key] = RouteConfig(**cfg)
        except Exception:
            continue

    return SettingsOut(
        routing=routing,
        system_prompts=SystemPrompts(**cached["system_prompts"]),
        features=Features(**cached["features"]),
        updated_at=cached["updated_at"],
    )


@router.patch("/api/settings", response_model=SettingsOut)
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    """部分更新系统设置（传什么改什么）"""
    s = db.query(Setting).filter(Setting.id == SETTINGS_ID).first()
    if s is None:
        from models import DEFAULT_ROUTING, DEFAULT_SYSTEM_PROMPTS
        s = Setting(
            id=SETTINGS_ID,
            routing=DEFAULT_ROUTING.copy(),
            system_prompts=DEFAULT_SYSTEM_PROMPTS.copy(),
            features={"pdf_as_image": False, "vision_enabled": False},
        )
        db.add(s)

    if data.routing:
        # 重建整个 routing dict（避免 SQLAlchemy JSON mutation tracking 问题）
        new_routing = dict(s.routing)
        for route_key, update in data.routing.items():
            if route_key not in KNOWN_ROUTES:
                continue  # 忽略未知路由键
            update_dict = update.model_dump(exclude_none=True)
            if update_dict:
                existing = dict(new_routing.get(route_key, {}))
                existing.update(update_dict)
                new_routing[route_key] = existing
        s.routing = new_routing

    if data.system_prompts:
        new_system_prompts = dict(s.system_prompts)
        sp = data.system_prompts.model_dump(exclude_none=True)
        for k, v in sp.items():
            new_system_prompts[k] = v
        s.system_prompts = new_system_prompts

    if data.features:
        new_features = dict(s.features)
        ft = data.features.model_dump(exclude_none=True)
        for k, v in ft.items():
            new_features[k] = v
        s.features = new_features

    s.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)

    # 刷新两处缓存（router + ai_engine）
    invalidate_settings_cache()  # router 缓存
    from ai_engine import invalidate_settings_cache as invalidate_ai_cache
    invalidate_ai_cache()  # ai_engine 缓存

    # 重新读取返回
    cached = get_cached_settings(db)
    routing = {}
    for key, cfg in cached["routing"].items():
        if key not in KNOWN_ROUTES:
            continue
        try:
            routing[key] = RouteConfig(**cfg)
        except Exception:
            continue

    return SettingsOut(
        routing=routing,
        system_prompts=SystemPrompts(**cached["system_prompts"]),
        features=Features(**cached["features"]),
        updated_at=cached["updated_at"],
    )


# ── ① 服务运维层 ──


@router.get("/api/settings/service", response_model=ServiceStatusOut)
def get_service_status():
    """读取 llama-server 运行状态（实时拉取，不存 DB）

    从 /health, /slots, /props 获取实时数据。
    任何一项失败不会影响其他项。
    """
    from config.urls import QWEN_API as LLAMA_BASE
    base = LLAMA_BASE.rsplit("/v1", 1)[0]  # 去掉 /v1/chat/completions 保留根
    result = ServiceStatusOut(
        llama_server="stopped",
        port=8083,
    )

    # /health
    try:
        r = requests.get(f"{base}/health", timeout=3)
        if r.status_code == 200:
            result.llama_server = "running"
        else:
            result.llama_server = "error"
    except requests.RequestException:
        result.llama_server = "stopped"
        return result  # 服务没起，后面的也不用查了

    # /slots
    try:
        r = requests.get(f"{base}/slots", timeout=3)
        if r.status_code == 200:
            slots = r.json()
            result.slots = len(slots)
            result.processing = any(s.get("is_processing", False) for s in slots)
            # 从第一个 slot 取 n_ctx
            if slots:
                result.context_size = slots[0].get("n_ctx")
    except Exception:
        pass

    # /props
    try:
        r = requests.get(f"{base}/props", timeout=3)
        if r.status_code == 200:
            props = r.json()
            result.model_name = props.get("model_alias")
            result.is_sleeping = props.get("is_sleeping", False)
            # VRAM 从 n_ctx 估算或者从 slots 拿
            if result.context_size is None:
                result.context_size = props.get("default_generation_settings", {}).get("n_ctx")
    except Exception:
        pass

    # VRAM (from nvidia-smi)
    try:
        import subprocess as _sp
        out = _sp.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3
        )
        if out.returncode == 0:
            parts = out.stdout.strip().split(",")
            if len(parts) == 2:
                result.vram_used_mb = int(parts[0].strip())
                result.vram_total_mb = int(parts[1].strip())
    except Exception:
        pass

    # Flash attention 从进程 cmdline 推测
    try:
        import os as _os
        import subprocess as _sp2
        pid = _sp2.run(["pgrep", "-f", "llama-server"], capture_output=True, text=True, timeout=2).stdout.strip()
        if pid:
            cmdline_path = _os.path.join("/proc", pid, "cmdline")
            if _os.path.exists(cmdline_path):
                with open(cmdline_path) as f:
                    raw = f.read()
                    cmd = raw.replace("\0", " ")
                    if "--flash-attn" in cmd or "-fa" in cmd:
                        idx = cmd.find("--flash-attn")
                        if idx >= 0:
                            rest = cmd[idx:].split()
                            val = rest[0].split("=")
                            result.flash_attention = val[1] if len(val) > 1 else "on"
                        else:
                            result.flash_attention = "on"
    except Exception:
        pass

    return result
