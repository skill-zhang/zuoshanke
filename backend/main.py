"""坐山客 API — FastAPI 应用入口"""
import logging
import os
from pathlib import Path

# 自动同步版本号（必须在任何版本读取之前）
from utils import sync_version_from_schema
sync_version_from_schema()

# 加载环境变量（优先加载 ~/.zuoshanke/.env，它含有 DEEPSEEK_API_KEY 等）
try:
    from dotenv import load_dotenv
    from config.paths import ZUOSHANKE_ENV
    if ZUOSHANKE_ENV.exists():
        load_dotenv(ZUOSHANKE_ENV)
        logging.info(f"✅ 已加载环境变量: {ZUOSHANKE_ENV}")
except ImportError:
    pass

# 🛡️ 代理防护：系统 http_proxy 可能指向 Windows 侧代理（如 Clash/v2ray），
# 该代理间歇断连会导致 LLM API 调用失败。此处强制 bypass 代理访问外部 API。
# DeepSeek 在中国可直接访问，无需走系统代理；本地服务更不应走代理。
for _key in ('no_proxy', 'NO_PROXY'):
    if not os.environ.get(_key):
        os.environ[_key] = 'localhost,127.0.0.1,api.deepseek.com,*.deepseek.com'
logging.info(f"✅ 已设置 no_proxy={os.environ.get('no_proxy', '')}")

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

# 🆕 上传文件静态服务
_uploads_dir = Path(__file__).resolve().parent.parent / "uploads"
_uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")

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

    # 🆕 运行时检查：「坐山客自开发」场景存在性（不在 init_db 中做，避免与 schema 初始化耦合）
    try:
        from database import SessionLocal
        from models import Scene
        import uuid
        _db2 = SessionLocal()
        exists = _db2.query(Scene).filter(Scene.name == "坐山客自开发").first()
        if not exists:
            dev_scene = Scene(
                id=f"scene-{uuid.uuid4().hex[:8]}",
                name="坐山客自开发",
                icon="⚒️",
                category="other",
                complexity="light",
                converge_enabled=False,
                diverge_min_rounds=0,
                scene_config={"temperature": 0.7},
                user_context="""你是【坐山客自开发】领域的智能助手。

## 开发流程（先方案再动手）

你的工作方式不同于普通场景——你不是接到需求就立刻执行：

1. 【方案阶段】用户提出需求后，先给出设计方案。
   - 分析需求涉及哪些模块（前端/后端/数据库/工具）
   - 提出具体的技术方案
   - 如果有多条路径可选，调 clarify 工具让用户选择
   - 如果需求不明确，调 clarify 工具追问细节

2. 【契约阶段】方案确认后，如果涉及多模块开发，先写接口契约文件。
   - 用 write_file 创建 shared/INTERFACE.md（API 端点 + 数据模型 + 模块边界）
   - 契约是子 Agent 之间唯一的共享上下文
   - 子 Agent 不知道彼此存在，只需要遵守契约
   - 任何子任务涉及多个 Agent 协作，必须写契约先行

3. 【执行阶段】按确认的方案实施。
   - 调用 file_tools/code_runner 等工具改代码
   - 必要时用 delegate_task 派子 Agent 并行执行（传 contract_path 引用契约文件）
   - 改完后跑测试验证（pytest / 拨测）
   - 如果过程中需要决策，调 clarify 暂停等待

4. 【联调阶段】所有子 Agent 完成后，进行联调验证。
   - 核对每个子 Agent 的产出是否符合契约
   - 启动后端/前端服务并拨测验证
   - 全部通过后，调 clarify 问用户是否需要提交

5. 【提交阶段】用户确认后，用 git_commit 提交代码。

## 工具使用

你有以下工具可用：
- 标准工具：file_tools/code_runner/session_search/memory/web_search/diverge/converge
- 开发专用工具：clarify（问用户问题）、delegate_task（派子 Agent + 契约引用）
- 拨测工具：browser_dial_test（完整拨测）、dial_style（CSS 检查）、dial_assert（断言验证）
- Git 工具：git_status（查看状态）、git_commit（提交代码）、git_diff（查看改动）

## 重要约束

- 在方案未被确认前，不要开始写代码
- 多模块并行开发时，必须先写 shared/INTERFACE.md 契约文件
- 子 Agent 不能调 clarify（它们不能问用户），如果子任务需要决策，汇报给父 Agent
- 改完前端代码后，用拨测工具验证渲染正确性
- 提交前先调 git_status 确认变更内容
- 所有重要修改需要用户确认后再提交""",
            )
            _db2.add(dev_scene)
            _db2.commit()
            log.info("✅ 默认「坐山客自开发」场景已创建（运行时检查）")
        _db2.close()
    except Exception as e:
        log.warning(f"坐山客自开发场景创建跳过: {e}")

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

    # 🆕 Schema v1.1: 记忆提取兜底调度（session 状态驱动，每60s扫描destroyed session）
    # 主链路: visibilitychange → destroy_stale_*_sessions() 内联提取
    # 兜底: 本调度器扫描 destroyed session 的未提取消息 → 补提
    try:
        from agent_core.idle_extractor import start_idle_extraction_scheduler
        start_idle_extraction_scheduler()
    except Exception as e:
        log.warning(f"记忆提取兜底调度启动失败: {e}")

    # 🆕 Schema v1.4: 用户画像自动处理调度器（每60秒检查 pending 暂存区）
    try:
        from router.user_profile import start_profile_processing_scheduler
        start_profile_processing_scheduler()
    except Exception as e:
        log.warning(f"用户画像自动处理调度器启动失败: {e}")

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

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True,
                reload_delay=3, reload_includes=["*.py"])
