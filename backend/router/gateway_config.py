"""
Gateway 配置管理 API

提供微信 Token/Account ID 的 CRUD 接口（存到 ~/.zuoshanke/.gateway.env）
以及 Gateway 进程状态查看。
"""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from gateway.config import GatewayConfig, save_gateway_config, GATEWAY_ENV_FILE, ILINK_BASE_URL

router = APIRouter(tags=["网关配置"])


class GatewayConfigOut(BaseModel):
    """Gateway 配置（返回）"""
    weixin_token_set: bool = False
    weixin_account_id_set: bool = False
    weixin_account_id_preview: Optional[str] = None
    weixin_base_url: str = ILINK_BASE_URL
    backend_url: str = ""
    config_file_exists: bool = False


class GatewayConfigUpdate(BaseModel):
    """Gateway 配置（更新）"""
    weixin_token: str
    weixin_account_id: str
    weixin_base_url: str = ILINK_BASE_URL


class GatewayConfigDelete(BaseModel):
    """确认删除配置"""
    confirm: bool = False


@router.get("/api/gateway/config", response_model=GatewayConfigOut)
def get_gateway_config():
    """读取当前 Gateway 配置状态"""
    config = GatewayConfig()
    return GatewayConfigOut(
        weixin_token_set=bool(config.weixin_token),
        weixin_account_id_set=bool(config.weixin_account_id),
        weixin_account_id_preview=config.weixin_account_id[:8] + "..." if config.weixin_account_id else None,
        weixin_base_url=config.weixin_base_url,
        backend_url=config.backend_url,
        config_file_exists=GATEWAY_ENV_FILE.exists(),
    )


@router.post("/api/gateway/config")
def set_gateway_config(data: GatewayConfigUpdate):
    """保存 Gateway 配置（Token / Account ID）"""
    if not data.weixin_token or not data.weixin_account_id:
        raise HTTPException(400, "Token 和 Account ID 不能为空")
    if not data.weixin_token.strip() or not data.weixin_account_id.strip():
        raise HTTPException(400, "Token 和 Account ID 不能为空")

    save_gateway_config(
        token=data.weixin_token.strip(),
        account_id=data.weixin_account_id.strip(),
        base_url=data.weixin_base_url.strip() or ILINK_BASE_URL,
    )
    return {"ok": True, "message": "Gateway 配置已保存"}


@router.delete("/api/gateway/config")
def delete_gateway_config(data: GatewayConfigDelete):
    """删除 Gateway 配置文件"""
    if not data.confirm:
        raise HTTPException(400, "需要确认删除（confirm=true）")
    if GATEWAY_ENV_FILE.exists():
        GATEWAY_ENV_FILE.unlink()
        return {"ok": True, "message": "Gateway 配置已删除"}
    return {"ok": True, "message": "配置文件不存在"}
