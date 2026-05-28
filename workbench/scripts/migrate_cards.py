"""迁移脚本：从坐山客主 DB 读取工作台场景，写入工作台 DB
直接用 SQLAlchemy 查主 DB，不依赖主后端的 models 模块（避免各种 import 冲突）
"""
import json
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def migrate():
    wb_backend = Path(__file__).parent.parent / "backend"
    import sys
    sys.path.insert(0, str(wb_backend))

    from database import SessionLocal as WbSession, init_db as wb_init
    from models import WidgetConfig

    wb_init()
    wb_db = WbSession()

    # 直接连主 DB
    main_db_path = Path(__file__).parent.parent.parent / "backend" / "zuoshanke.db"
    if not main_db_path.exists():
        print(f"❌ 主 DB 不存在: {main_db_path}")
        return

    main_engine = create_engine(f"sqlite:///{main_db_path}")
    MainSession = sessionmaker(bind=main_engine)
    main_db = MainSession()

    CATEGORY_MAP = {
        "life": "weather",
        "todo": "todo",
        "news": "news",
        "game": "game",
        "analysis": "analysis",
        "git": "git",
        "stock": "stock",
        "shopping": "shopping",
    }

    CONFIG_KEY_MAP = {
        "weather": "weather", "todo": "todo", "news": "news",
        "game": "game", "analysis": "analysis", "git": "git",
        "stock": "stock", "shopping": "shopping",
    }

    rows = main_db.execute(
        text("SELECT id, name, icon, category, show_on_workbench, workbench_position, scene_config FROM scenes WHERE show_on_workbench = 1 ORDER BY workbench_position")
    ).fetchall()

    print(f"找到 {len(rows)} 个工作台场景")

    migrated = 0
    for row in rows:
        sid, name, icon, category, _, position, scene_config_json = row
        cat = category or "other"
        wtype = CATEGORY_MAP.get(cat)
        if not wtype:
            print(f"  跳过 {name}: 未知类别 {cat}")
            continue

        config = {}
        if scene_config_json:
            try:
                config = json.loads(scene_config_json)
            except json.JSONDecodeError:
                pass

        config_key = CONFIG_KEY_MAP.get(wtype, wtype)
        widget_data = config.get(config_key, {})

        exists = wb_db.query(WidgetConfig).filter(
            WidgetConfig.widget_type == wtype,
            WidgetConfig.title == name,
        ).first()
        if exists:
            print(f"  ⏭ {name} 已存在，跳过")
            continue

        w = WidgetConfig(
            widget_type=wtype,
            title=name,
            config=json.dumps(widget_data, ensure_ascii=False),
            position=position or 0,
            width=1,
            height=1,
        )
        wb_db.add(w)
        migrated += 1
        print(f"  ✅ {icon or ''} {name} → {wtype}")

    wb_db.commit()
    wb_db.close()
    main_db.close()
    print(f"\n迁移完成: {migrated} / {len(rows)} 个场景已迁移")


if __name__ == "__main__":
    migrate()
