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

    # 空闲场景记忆提取调度（后台线程）— 已关闭，每5分钟无差别提取太激进
    # 需要时取消注释即可恢复
    # try:
    #     from agent_core.idle_extractor import start_idle_extraction_scheduler
    #     start_idle_extraction_scheduler()
    # except Exception as e:
    #     log.warning(f"空闲提取调度启动失败: {e}")

    # 🆕 Schema v0.81: 数据库迁移
    try:
        db = SessionLocal()
        from router.scene_stream import _migrate_schema_v081
        _migrate_schema_v081(db)
        db.close()
        log.info("✅ Schema v0.81 数据库迁移完成")
    except Exception as e:
        log.warning(f"Schema v0.81 迁移跳过: {e}")

    # 🆕 Schema v1.1: GatewaySession 扩展字段迁移（ALTER TABLE）
    try:
        db = SessionLocal()
        from sqlalchemy import text as _sa_text
        for col, col_type in [
            ("status", "VARCHAR(20) DEFAULT 'active'"),
            ("started_at", "TIMESTAMP"),
            ("ended_at", "TIMESTAMP"),
            ("duration_seconds", "INTEGER"),
            ("prompt_tokens", "INTEGER DEFAULT 0"),
            ("completion_tokens", "INTEGER DEFAULT 0"),
            ("total_tokens", "INTEGER DEFAULT 0"),
            ("input_tokens", "INTEGER DEFAULT 0"),
            ("output_tokens", "INTEGER DEFAULT 0"),
            ("cache_read_tokens", "INTEGER DEFAULT 0"),
            ("cache_write_tokens", "INTEGER DEFAULT 0"),
            ("reasoning_tokens", "INTEGER DEFAULT 0"),
            ("api_calls", "INTEGER DEFAULT 0"),
            ("estimated_cost_usd", "REAL DEFAULT 0.0"),
            ("cost_status", "VARCHAR(20) DEFAULT 'unknown'"),
            ("cost_source", "VARCHAR(50)"),
        ]:
            try:
                db.execute(_sa_text(f"ALTER TABLE gateway_sessions ADD COLUMN {col} {col_type}"))
            except Exception:
                pass  # 已有该列
        db.commit()
        db.close()
        log.info("✅ Schema v1.1 GatewaySession 字段迁移完成")
    except Exception as e:
        log.warning(f"GatewaySession 字段迁移跳过: {e}")

    # 🆕 Schema v1.1: 启动时清理过期的 session
    try:
        db = SessionLocal()
        from router.sessions import cleanup_all_stale_sessions
        result = cleanup_all_stale_sessions(db)
        db.close()
        log.info(f"✅ 启动清理完成: {result['web_sessions_destroyed']} Web, {result['gateway_sessions_destroyed']} Gateway")
    except Exception as e:
        log.warning(f"启动 session 清理跳过: {e}")

    # 🆕 Schema v1.1: 后台 session 超时扫描（每5分钟）
    import threading as _st
    def _session_timeout_scanner():
        import time as _time
        from config.constants import SESSION_TIMEOUT_HOURS
        while True:
            _time.sleep(300)  # 每5分钟扫一次
            try:
                _db = SessionLocal()
                from router.sessions import cleanup_all_stale_sessions
                _r = cleanup_all_stale_sessions(_db)
                _db.close()
                if _r['web_sessions_destroyed'] + _r['gateway_sessions_destroyed'] > 0:
                    log.info(f"🔄 Session 超时清理: {_r}")
            except Exception:
                pass
    _st.Thread(target=_session_timeout_scanner, daemon=True).start()
    log.info("✅ Session 超时扫描线程已启动（每5分钟）")

    uvicorn.run(app, host="0.0.0.0", port=8000)
