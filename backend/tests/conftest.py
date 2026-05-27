"""
坐山客测试环境 conftest
- 独立的测试数据库 (zuoshanke_test.db)
- FastAPI TestClient（无需启动 uvicorn）
- 每个测试后自动清理数据
"""
import os
import sys

# 把 backend 目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 测试环境标记 — 让 database.py 不依赖外部 .env 等
os.environ.setdefault("ZUOSHANKE_REBUILD_DB", "1")

import pytest
from fastapi.testclient import TestClient

# 必须先 init_db 再 import app
from database import init_db
init_db()  # 重建 zuoshanke_test.db 表结构 + 种子数据

from main import app


# ── pytest markers ──
def pytest_configure(config):
    """注册自定义 markers"""
    config.addinivalue_line("markers", "server: 标记需要运行中的后端服务器（非 TestClient）")


@pytest.fixture(scope="session")
def client() -> TestClient:
    """提供 FastAPI TestClient（请求级别隔离）"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _db_cleanup():
    """
    每个测试函数执行后清理数据，保持测试隔离。
    """
    yield
    from database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        tables = ["messages", "think_nodes", "thinking_maps",
                   "web_sessions", "gateway_sessions",
                   "agent_memory", "cross_refs", "memory_contexts",
                   "user_profiles", "pending_traits",
                   "output_refs", "cmd_templates",
                   "scene_self_map", "document_summaries"]
        for t in tables:
            try:
                db.execute(text(f"DELETE FROM {t}"))
            except Exception:
                pass
        db.commit()
    finally:
        db.close()
