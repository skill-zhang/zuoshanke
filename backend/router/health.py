"""健康检查"""
from fastapi import APIRouter
from utils import get_version

router = APIRouter(tags=["健康检查"])


@router.get("/api/health")
def health():
    return {"status": "ok", "service": "zuoshanke", "version": get_version()}
