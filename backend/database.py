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
