"""坐山客 API — FastAPI 应用入口"""
import logging
from pathlib import Path

# 加载环境变量（优先加载 hermes 的 .env，它含有 DEEPSEEK_API_KEY 等）
try:
    from dotenv import load_dotenv
    from config.paths import HERMES_ENV
    if HERMES_ENV.exists():
        load_dotenv(HERMES_ENV)
        logging.info(f"✅ 已加载环境变量: {HERMES_ENV}")
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from router import register_all_routers
from config.urls import CORS_ORIGINS

app = FastAPI(title="坐山客 API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_all_routers(app)

if __name__ == "__main__":
    import uvicorn
    from logger import configure_logger

    configure_logger()
    log = logging.getLogger("main")

    init_db()
    log.info("✅ 数据库已初始化")
    uvicorn.run(app, host="0.0.0.0", port=8000)
