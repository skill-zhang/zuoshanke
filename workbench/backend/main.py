"""独立工作台后端 — FastAPI 入口"""
import os
import sys
from pathlib import Path

# 确保导入路径正确
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routes.widgets import router as widgets_router
from routes.layout import router as layout_router

app = FastAPI(title="坐山客 · 工作台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(widgets_router)
app.include_router(layout_router)


@app.on_event("startup")
def startup():
    init_db()
    _auto_migrate()


def _auto_migrate():
    """主 DB → 工作台 DB 自动迁移（首次启动时）"""
    import json
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from database import SessionLocal as WbSession
    from models import WidgetConfig

    main_db_path = Path(__file__).parent.parent.parent / "backend" / "zuoshanke.db"
    if not main_db_path.exists():
        return

    # 检查是否已有数据
    wb_db = WbSession()
    existing = wb_db.query(WidgetConfig).count()
    if existing > 0:
        wb_db.close()
        return

    try:
        main_engine = create_engine(f"sqlite:///{main_db_path}")
        MainSession = sessionmaker(bind=main_engine)
        main_db = MainSession()

        CATEGORY_MAP = {
            "life": "weather", "todo": "todo", "news": "news",
            "game": "game", "analysis": "analysis", "git": "git",
            "stock": "stock", "shopping": "shopping",
        }
        CONFIG_KEY_MAP = {
            "weather": "weather", "todo": "todo", "news": "news",
            "game": "game", "analysis": "analysis", "git": "git",
            "stock": "stock", "shopping": "shopping",
        }

        rows = main_db.execute(
            text("SELECT name, icon, category, workbench_position, scene_config FROM scenes WHERE show_on_workbench = 1 ORDER BY workbench_position")
        ).fetchall()

        count = 0
        for row in rows:
            name, icon, category, position, scene_config_json = row
            wtype = CATEGORY_MAP.get(category or "other")
            if not wtype:
                continue
            config = {}
            if scene_config_json:
                try:
                    config = json.loads(scene_config_json)
                except json.JSONDecodeError:
                    pass
            widget_data = config.get(CONFIG_KEY_MAP.get(wtype, wtype), {})
            w = WidgetConfig(
                widget_type=wtype, title=name,
                config=json.dumps(widget_data, ensure_ascii=False),
                position=position or 0, width=1, height=1,
            )
            wb_db.add(w)
            count += 1

        wb_db.commit()
        main_db.close()
        print(f"[工作台] 自动迁移: {count} 张卡片")
    except Exception as e:
        print(f"[工作台] 迁移跳过: {e}")
    finally:
        wb_db.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "workbench"}


# 静态文件（前端产物）
static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
