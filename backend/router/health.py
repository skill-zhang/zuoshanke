"""健康检查"""
from fastapi import APIRouter

router = APIRouter(tags=["健康检查"])


@router.get("/api/health")
def health():
    return {"status": "ok", "service": "zuoshanke", "version": "0.2.0"}
