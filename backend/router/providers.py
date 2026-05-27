"""AI Provider CRUD — 管理 API 凭据和模型列表"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import AiProvider, AiModel
from utils import make_id, utcnow
from secret_redact import _mask_secret
from provider_catalog import get_catalog as get_provider_catalog, invalidate_cache as invalidate_catalog_cache

router = APIRouter(prefix="/api/providers", tags=["AI Provider"])


# ─── Provider 目录（从 providers.md 读取） ───

@router.get("/catalog")
def list_catalog():
    """获取已知 Provider/Model 目录（供前端下拉列表使用）"""
    return {"catalog": get_provider_catalog()}


@router.post("/catalog/refresh")
def refresh_catalog():
    """强制刷新目录缓存（每次更新 providers.md 后调用）"""
    invalidate_catalog_cache()
    return {"catalog": get_provider_catalog(force_refresh=True)}


# ─── Schemas ───

def provider_to_dict(p: AiProvider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "base_url": p.base_url,
        "api_key": _mask_secret(p.api_key) if p.api_key else "",
        "provider_type": p.provider_type,
        "is_active": p.is_active,
        "models": [model_to_dict(m) for m in (p.models or [])],
    }


def model_to_dict(m: AiModel) -> dict:
    return {
        "id": m.id,
        "provider_id": m.provider_id,
        "name": m.name,
        "display_name": m.display_name or m.name,
        "temperature": m.temperature,
        "max_tokens": m.max_tokens,
        "context_length": m.context_length,
        "repeat_penalty": m.repeat_penalty,
        "vision": m.vision,
        "function_calling": m.function_calling,
        "sort_order": m.sort_order,
    }


# ─── CRUD ───

@router.get("")
def list_providers(db: Session = Depends(get_db)):
    """获取所有 Provider（含模型列表）"""
    providers = db.query(AiProvider).order_by(AiProvider.created_at).all()
    return {"providers": [provider_to_dict(p) for p in providers]}


@router.get("/{provider_id}")
def get_provider(provider_id: str, db: Session = Depends(get_db)):
    """获取单个 Provider"""
    p = db.query(AiProvider).filter(AiProvider.id == provider_id).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    return {"provider": provider_to_dict(p)}


@router.post("")
def create_provider(data: dict, db: Session = Depends(get_db)):
    """新增 Provider"""
    required = ["name", "base_url"]
    for field in required:
        if field not in data or not data[field]:
            raise HTTPException(400, f"'{field}' is required")
    p = AiProvider(
        id=make_id(),
        name=data["name"],
        base_url=data["base_url"].rstrip("/"),
        api_key=data.get("api_key", ""),
        provider_type=data.get("provider_type", "openai-compatible"),
        is_active=data.get("is_active", True),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"provider": provider_to_dict(p)}


@router.put("/{provider_id}")
def update_provider(provider_id: str, data: dict, db: Session = Depends(get_db)):
    """更新 Provider"""
    p = db.query(AiProvider).filter(AiProvider.id == provider_id).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    for field in ["name", "base_url", "api_key", "provider_type", "is_active"]:
        if field in data:
            setattr(p, field, data[field])
    if p.base_url:
        p.base_url = p.base_url.rstrip("/")
    p.updated_at = utcnow()
    db.commit()
    db.refresh(p)
    return {"provider": provider_to_dict(p)}


@router.delete("/{provider_id}")
def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    """删除 Provider（级联删除关联模型）"""
    p = db.query(AiProvider).filter(AiProvider.id == provider_id).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ─── 模型 CRUD ───

@router.post("/{provider_id}/models")
def create_model(provider_id: str, data: dict, db: Session = Depends(get_db)):
    """新增模型"""
    p = db.query(AiProvider).filter(AiProvider.id == provider_id).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    if "name" not in data or not data["name"]:
        raise HTTPException(400, "'name' is required")
    m = AiModel(
        id=make_id(),
        provider_id=provider_id,
        name=data["name"],
        display_name=data.get("display_name"),
        temperature=data.get("temperature", 0.7),
        max_tokens=data.get("max_tokens", 8192),
        context_length=data.get("context_length", 32768),
        repeat_penalty=data.get("repeat_penalty", 1.05),
        vision=data.get("vision", False),
        function_calling=data.get("function_calling", True),
        sort_order=data.get("sort_order", 0),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"model": model_to_dict(m)}


@router.put("/{provider_id}/models/{model_id}")
def update_model(provider_id: str, model_id: str, data: dict, db: Session = Depends(get_db)):
    """更新模型"""
    m = db.query(AiModel).filter(AiModel.id == model_id, AiModel.provider_id == provider_id).first()
    if not m:
        raise HTTPException(404, "Model not found")
    for field in ["name", "display_name", "temperature", "max_tokens", "context_length",
                   "repeat_penalty", "vision", "function_calling", "sort_order"]:
        if field in data:
            setattr(m, field, data[field])
    m.updated_at = utcnow()
    db.commit()
    db.refresh(m)
    return {"model": model_to_dict(m)}


@router.delete("/{provider_id}/models/{model_id}")
def delete_model(provider_id: str, model_id: str, db: Session = Depends(get_db)):
    """删除模型"""
    m = db.query(AiModel).filter(AiModel.id == model_id, AiModel.provider_id == provider_id).first()
    if not m:
        raise HTTPException(404, "Model not found")
    db.delete(m)
    db.commit()
    return {"ok": True}
