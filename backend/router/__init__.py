"""坐山客 API 路由注册"""
from fastapi import FastAPI

from router.health import router as health_router
from router.projects import router as projects_router
from router.scenes import router as scenes_router
from router.channels import router as channels_router
from router.messages import router as messages_router
from router.action_maps import router as action_maps_router
from router.tools import router as tools_router


def register_all_routers(app: FastAPI):
    """注册所有路由模块"""
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(scenes_router)
    app.include_router(channels_router)
    app.include_router(messages_router)
    app.include_router(action_maps_router)
    app.include_router(tools_router)
