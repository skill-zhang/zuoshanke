"""
Layer 1-A: 双重记忆池核心契约测试

测试目标（按优先级排列）：
  P0-1: scope 标签正确写入 — POST 创建的记忆 scope 字段正确
  P0-2: 写入穿透 — 通过 API 写入后 get_top 可见
  P0-3: CRUD — 创建/读取/删除按 key
  P0-4: 记忆分组API正常
"""
import pytest
from fastapi.testclient import TestClient


class TestMemoryCRUD:
    """P0: 记忆 CRUD 基本操作 — 确保 API 可用性"""

    def test_create_and_read(self, client: TestClient):
        key = "crud_" + __import__('uuid').uuid4().hex[:6]
        resp = client.post("/api/memory", json={
            "category": "user",
            "key": key,
            "content": "测试内容",
        })
        assert resp.status_code == 200, f"创建失败: {resp.text}"

        resp_get = client.get(f"/api/memory/{key}")
        assert resp_get.status_code == 200, f"读取失败: {resp_get.text}"
        assert resp_get.json()["data"]["key"] == key

    def test_list_memories(self, client: TestClient):
        resp = client.get("/api/memory")
        assert resp.status_code == 200

    def test_create_and_delete(self, client: TestClient):
        key = "待删除_" + __import__('uuid').uuid4().hex[:6]
        resp = client.post("/api/memory", json={
            "category": "user",
            "key": key,
            "content": "即将被删除",
        })
        assert resp.status_code == 200

        resp_del = client.delete(f"/api/memory/{key}")
        assert resp_del.status_code == 200, f"删除失败: {resp_del.text}"

        resp_get = client.get(f"/api/memory/{key}")
        assert resp_get.status_code == 404, "删除后应返回 404"


class TestMemoryWriteThrough:
    """P0: 写入穿透 — API 写入后 get_top 立即可见"""

    def test_create_then_top(self, client: TestClient):
        key = "穿透_" + __import__('uuid').uuid4().hex[:6]
        resp = client.post("/api/memory", json={
            "category": "user",
            "key": key,
            "content": "写入穿透测试",
        })
        assert resp.status_code == 200

        resp_top = client.get("/api/memory/top")
        assert resp_top.status_code == 200
        top = resp_top.json().get("data", [])
        top_keys = [m.get("key", "") for m in top]
        assert key in top_keys, f"写入后 get_top 不可见（穿透失败）"


class TestMemoryScopeIsolation:
    """P0: 记忆池 scope 隔离 — 双池架构的根基"""

    def test_zhu_not_visible_in_scene(self, client: TestClient):
        """写入 zhu 记忆 → GET /api/memory?scope=scene&scope_only=true 不应包含"""
        key = "zhu_secret_" + __import__('uuid').uuid4().hex[:6]
        resp = client.post("/api/memory", json={
            "category": "user",
            "key": key,
            "content": "只有本体知道的秘密",
        })
        assert resp.status_code == 200

        # 查 scene scope（仅 scene）→ 不应包含 zhu 记忆
        resp_scene = client.get("/api/memory?scope=scene&scope_only=true")
        assert resp_scene.status_code == 200
        data = resp_scene.json().get("data", [])
        keys = [m.get("key", "") for m in data]
        assert key not in keys, f"zhu 记忆泄露到 scene scope! key={key}"

    def test_zhu_visible_when_not_scope_only(self, client: TestClient):
        """分身查记忆（不加 scope_only）→ 能看到 zhu（合并模式）"""
        key = "zhu_shared_" + __import__('uuid').uuid4().hex[:6]
        resp = client.post("/api/memory", json={
            "category": "user",
            "key": key,
            "content": "本体分享给分身的记忆",
        })
        assert resp.status_code == 200

        # 不加 scope_only → zhu 可见（合并模式）
        resp_all = client.get("/api/memory")
        assert resp_all.status_code == 200
        data = resp_all.json().get("data", [])
        keys = [m.get("key", "") for m in data]
        assert key in keys, f"不加 scope_only 时 zhu 记忆应该可见"


class TestMemoryGroups:
    """P1: 记忆分组 API"""

    def test_list_groups(self, client: TestClient):
        resp = client.get("/api/memory/groups")
        assert resp.status_code == 200
        groups = resp.json().get("groups", resp.json().get("data", []))
        assert isinstance(groups, list)
