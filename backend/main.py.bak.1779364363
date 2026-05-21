"""坐山客 API — FastAPI 应用入口"""
import logging
import os
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

# 🆕 产出成果静态文件服务
_outputs_dir = Path(__file__).resolve().parent.parent / "outputs"
_outputs_dir.mkdir(exist_ok=True)
from fastapi.staticfiles import StaticFiles
app.mount("/outputs", StaticFiles(directory=str(_outputs_dir)), name="outputs")

if __name__ == "__main__":
    import uvicorn
    from logger import configure_logger

    configure_logger()
    log = logging.getLogger("main")

    init_db()
    log.info("✅ 数据库已初始化")

    # 🆕 MemoryCache 预热：启动时加载本体记忆
    try:
        from database import SessionLocal as _DL
        from agent_core.memory_cache import MemoryCache
        _db = _DL()
        MemoryCache.get_instance().initialize(_db)
        _db.close()
        log.info("✅ MemoryCache 已加载本体记忆")
    except Exception as e:
        log.warning(f"MemoryCache 初始化跳过: {e}")

    # 🆕 Schema v0.8: 初始化坐山客本体（如无则创建）
    try:
        from database import SessionLocal
        from agent_core.zhu_agent import ZhuAgentManager
        db = SessionLocal()
        ZhuAgentManager(db).get_or_create()
        db.close()
        log.info("✅ 坐山客本体已就绪")
    except Exception as e:
        log.warning(f"本体初始化跳过: {e}")

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

    # 空闲场景记忆提取调度（后台线程）
    try:
        from agent_core.idle_extractor import start_idle_extraction_scheduler
        start_idle_extraction_scheduler()
    except Exception as e:
        log.warning(f"空闲提取调度启动失败: {e}")

    # 🆕 Schema v0.81: 数据库迁移
    try:
        db = SessionLocal()
        from router.scene_stream import _migrate_schema_v081
        _migrate_schema_v081(db)
        db.close()
        log.info("✅ Schema v0.81 数据库迁移完成")
    except Exception as e:
        log.warning(f"Schema v0.81 迁移跳过: {e}")

    uvicorn.run(app, host="0.0.0.0", port=8000)
