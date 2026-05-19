"""数据库连接与配置"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "zuoshanke.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表 + 种子数据"""
    import models  # noqa: F401

    # 检查是否需要重建（schema 变更）
    rebuild = os.environ.get("ZUOSHANKE_REBUILD_DB", "0") == "1"

    if rebuild:
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS messages"))
            conn.execute(text("DROP TABLE IF EXISTS cross_refs"))
            conn.execute(text("DROP TABLE IF EXISTS think_nodes"))
            conn.execute(text("DROP TABLE IF EXISTS thinking_maps"))
            conn.execute(text("DROP TABLE IF EXISTS scenes"))
            conn.execute(text("DROP TABLE IF EXISTS projects"))
            conn.execute(text("DROP TABLE IF EXISTS channels"))
            conn.commit()
        print("🗑  旧表已删除，准备重建 schema")

    Base.metadata.create_all(bind=engine)

    # 迁移：新增 session_id 字段（零破坏）
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(messages)")).fetchall()]
            if "session_id" not in cols:
                conn.execute(text("ALTER TABLE messages ADD COLUMN session_id VARCHAR"))
                conn.commit()
                print("✅ messages 表新增 session_id 字段")
    except Exception as e:
        print(f"⚠️  session_id 迁移跳过: {e}")

    # 迁移：gateway_sessions 表（零破坏，仅新增表）
    try:
        with engine.connect() as conn:
            tables = [row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
            if "gateway_sessions" not in tables:
                conn.execute(text("""
                    CREATE TABLE gateway_sessions (
                        id VARCHAR NOT NULL PRIMARY KEY,
                        platform VARCHAR NOT NULL,
                        platform_user_id VARCHAR NOT NULL,
                        mode VARCHAR NOT NULL DEFAULT 'channel',
                        channel_id VARCHAR,
                        scene_id VARCHAR,
                        scene_name VARCHAR,
                        platform_username VARCHAR,
                        last_active_at DATETIME,
                        created_at DATETIME,
                        updated_at DATETIME,
                        UNIQUE (platform, platform_user_id)
                    )
                """))
                conn.commit()
                print("✅ gateway_sessions 表已创建")
    except Exception as e:
        print(f"⚠️  gateway_sessions 表创建跳过: {e}")

    # 迁移：Scenes 表新增广场/工坊字段（零破坏）
    NEW_SCENE_COLS = [
        ("icon", "VARCHAR"),
        ("description", "TEXT DEFAULT '' NOT NULL"),
        ("guide_text", "VARCHAR"),
        ("category", "VARCHAR DEFAULT 'other' NOT NULL"),
        ("version", "VARCHAR DEFAULT '0.0' NOT NULL"),
        ("source", "VARCHAR DEFAULT 'self' NOT NULL"),
        ("changelog", "VARCHAR"),
        ("published_at", "DATETIME"),
    ]
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(scenes)")).fetchall()]
            for col_name, col_type in NEW_SCENE_COLS:
                if col_name not in cols:
                    conn.execute(text(f"ALTER TABLE scenes ADD COLUMN {col_name} {col_type}"))
            conn.commit()
            added = [c for c, _ in NEW_SCENE_COLS if c not in cols]
            if added:
                print(f"✅ scenes 表新增字段: {', '.join(added)}")
    except Exception as e:
        print(f"⚠️  scenes 字段迁移跳过: {e}")

    # 迁移：ThinkNode v1 — Agent Loop 新字段（零破坏）
    THINKNODE_V1_COLS = [
        ("converged_from", "JSON DEFAULT '[]'"),
        ("created_by", "TEXT DEFAULT 'brainstorm'"),
        ("priority", "INTEGER"),
        ("queue_order", "INTEGER"),
        ("depends_on", "JSON DEFAULT '[]'"),
        ("execution_result", "TEXT"),
    ]
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(think_nodes)")).fetchall()]
            for col_name, col_type in THINKNODE_V1_COLS:
                if col_name not in cols:
                    conn.execute(text(f"ALTER TABLE think_nodes ADD COLUMN {col_name} {col_type}"))
            conn.commit()
            added = [c for c, _ in THINKNODE_V1_COLS if c not in cols]
            if added:
                print(f"✅ think_nodes 表新增字段: {', '.join(added)}")
    except Exception as e:
        print(f"⚠️  think_nodes v1 迁移跳过: {e}")

    # 迁移：memory scope 字段（零破坏，2026-05-27）
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(agent_memory)")).fetchall()]
            if "scope" not in cols:
                conn.execute(text("ALTER TABLE agent_memory ADD COLUMN scope VARCHAR(10) NOT NULL DEFAULT 'zhu'"))
                conn.execute(text("ALTER TABLE agent_memory ADD COLUMN context_id VARCHAR(32)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_memory_scope ON agent_memory(scope)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_memory_context_id ON agent_memory(context_id)"))
                conn.commit()
                print("✅ agent_memory 表新增 scope + context_id 字段")
    except Exception as e:
        print(f"⚠️  agent_memory scope 迁移跳过: {e}")

    # 种子数据：默认闲聊频道
    db = SessionLocal()
    try:
        existing = db.query(models.Channel).filter(models.Channel.is_default == True).first()
        if not existing:
            import uuid
            channel = models.Channel(
                id=f"ch-{uuid.uuid4().hex[:8]}",
                name="闲聊",
                is_default=True,
            )
            db.add(channel)
            db.commit()
            print("✅ 默认「闲聊」频道已创建")
    finally:
        db.close()

    # 种子数据：默认系统设置（单行）
    db = SessionLocal()
    try:
        existing = db.query(models.Setting).filter(models.Setting.id == models.SETTINGS_ID).first()
        if not existing:
            setting = models.Setting(
                id=models.SETTINGS_ID,
                routing=models.DEFAULT_ROUTING.copy(),
                system_prompts=models.DEFAULT_SYSTEM_PROMPTS.copy(),
                features={"pdf_as_image": False, "vision_enabled": False},
            )
            db.add(setting)
            db.commit()
            print("✅ 默认系统设置已创建")
    finally:
        db.close()
