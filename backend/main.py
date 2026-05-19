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

    # 预热 FTS5 全文索引（后台线程，不阻塞启动）
    try:
        import sys
        sys.path.insert(0, os.path.expanduser("~/zuoshanke"))
        from tools.session_search import _ensure_fts_table
        import threading
        threading.Thread(target=_ensure_fts_table, daemon=True).start()
        log.info("✅ FTS5 全文索引同步已启动")
    except Exception as e:
        log.warning(f"FTS5 索引预热跳过: {e}")

    uvicorn.run(app, host="0.0.0.0", port=8000)
