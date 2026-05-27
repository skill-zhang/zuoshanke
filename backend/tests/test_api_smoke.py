"""API 冒烟测试 — 验证 TestClient + 测试 DB 正常工作"""
import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """健康检查端点"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data or "message" in data


def test_list_channels(client: TestClient):
    """列出频道"""
    resp = client.get("/api/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) or "channels" in data


def test_create_scene(client: TestClient):
    """创建场景"""
    resp = client.post("/api/scenes", json={"name": "测试场景", "category": "life"})
    assert resp.status_code == 200
    data = resp.json()
    scene_id = data.get("id") or data.get("scene", {}).get("id", "")
    assert scene_id

    # 读取创建的场景
    resp2 = client.get(f"/api/scenes/{scene_id}")
    assert resp2.status_code == 200


def test_list_providers(client: TestClient):
    """列出 Provider"""
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) or "providers" in data
