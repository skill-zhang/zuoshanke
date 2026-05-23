"""坐山客 API 路由注册"""
from fastapi import FastAPI

from router.health import router as health_router
from router.scenes import router as scenes_router
from router.channels import router as channels_router
from router.messages import router as messages_router
from router.tools import router as tools_router
from router.tools_crud import router as tools_crud_router
from router.settings import router as settings_router
from router.memory import router as memory_router      # 🆕 Schema v0.5
from router.skills import router as skills_router       # 🆕 Schema v0.5
from router.gateway import router as gateway_router     # 🆕 多平台网关
from router.gateway_config import router as gateway_config_router  # 🆕 网关配置
from router.dashboard import router as dashboard_router           # 🆕 Schema v0.7 仪表盘
from router.zhu_agent import router as zhu_router                 # 🆕 Schema v0.8 本体
from router.sessions import router as sessions_router             # 🆕 Schema v1.1 Session 管理
from router.outputs import router as outputs_router                # 🆕 产出成果
from router.garden_chat import router as garden_chat_router          # 🆕 起居室
from router.clarify_router import router as clarify_router           # 🆕 自开发场景 Clarify
from router.delegate_results import router as delegate_results_router  # 🆕 子 Agent 成果展示
from router.scene_self_map import router as scene_self_map_router      # 🆕 场景自省地图


def register_all_routers(app: FastAPI):
    """注册所有路由模块"""
    app.include_router(health_router)
    app.include_router(scenes_router)
    app.include_router(channels_router)
    app.include_router(messages_router)
    app.include_router(tools_router)
    app.include_router(tools_crud_router)
    app.include_router(settings_router)
    app.include_router(memory_router)     # 🆕
    app.include_router(skills_router)      # 🆕
    app.include_router(gateway_router)     # 🆕 多平台网关
    app.include_router(gateway_config_router)  # 🆕 网关配置
    app.include_router(dashboard_router)   # 🆕 Schema v0.7 仪表盘
    app.include_router(zhu_router)         # 🆕 Schema v0.8 本体
    app.include_router(sessions_router)    # 🆕 Schema v1.1 Session 管理
    app.include_router(outputs_router)     # 🆕 产出成果
    app.include_router(garden_chat_router)  # 🆕 起居室
    app.include_router(clarify_router)      # 🆕 自开发场景 Clarify
    app.include_router(delegate_results_router)  # 🆕 子 Agent 成果展示
    app.include_router(scene_self_map_router)     # 🆕 场景自省地图
