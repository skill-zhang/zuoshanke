"""
Layer 1-C: SSE 消息流核心契约测试

测试目标：
  P0-1: SSE 端点存在 → 返回正确 Content-Type (text/event-stream)
  P0-2: 发送消息 → user_msg 事件回显（含 content）
  P0-3: 事件序列 — user_msg 是第一个事件
  P0-4: 消息列表 API — 发送后的消息能在列表中查到
  P0-5: 场景 CRUD — 创建/读取/修改生命周期
"""
import json
import pytest
from fastapi.testclient import TestClient
import threading
import time


def _create_scene(client, name="SSE测试场景"):
    """辅助：创建一个场景并返回 scene_id"""
    resp = client.post("/api/scenes", json={"name": name, "category": "life"})
    assert resp.status_code == 200, f"场景创建失败: {resp.text}"
    data = resp.json()
    return data.get("id", "")


def _read_sse_events_fast(resp, max_events=5, timeout_sec=8):
    """
    从 SSE StreamingResponse 中快速读取前 N 个事件。
    用线程+超时方式避免阻塞。
    返回事件列表。
    """
    events = []
    stop = False

    def read():
        nonlocal stop
        try:
            for line in resp.iter_lines():
                if stop:
                    break
                if not line:
                    continue
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                if text.startswith("data: "):
                    try:
                        payload = json.loads(text[6:])
                        events.append(payload)
                        if len(events) >= max_events:
                            stop = True
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    stop = True
    return events


class TestSSEEndpointExistence:
    """P0: SSE 端点（需 LLM mock，暂跳过）"""

    @pytest.mark.skip(reason="触发真实 LLM 调用")
    def test_scene_stream_returns_200(self, client: TestClient):
        pass

    @pytest.mark.skip(reason="触发真实 LLM 调用")
    def test_response_content_type(self, client: TestClient):
        pass


class TestSSEUserMsg:
    """P0: user_msg 事件验证（需 LLM mock，暂标记跳过）"""

    @pytest.mark.skip(reason="需要 mock LLM 调用以避免真实 API 耗时")
    def test_user_msg_has_content(self, client: TestClient):
        pass


class TestMessageListAPI:
    """P0: 消息列表 API"""

    @pytest.mark.skip(reason="需要 mock LLM 调用以避免真实 API 耗时")
    def test_send_then_list(self, client: TestClient):
        pass


class TestSceneCRUD:
    """P1: 场景生命周期"""

    def test_create_and_read(self, client: TestClient):
        """创建场景 → 按 ID 读取 → 验证字段"""
        name = "CRUD测试_" + __import__('uuid').uuid4().hex[:6]
        resp = client.post("/api/scenes", json={
            "name": name,
            "category": "life",
            "icon": "🌤️",
        })
        assert resp.status_code == 200
        data = resp.json()
        scene_id = data.get("id", "")
        assert scene_id, "场景创建未返回 id"

        resp_get = client.get(f"/api/scenes/{scene_id}")
        assert resp_get.status_code == 200
        assert resp_get.json().get("name") == name

    def test_patch_scene(self, client: TestClient):
        """修改场景字段"""
        scene_id = _create_scene(client, "PATCH测试_" + __import__('uuid').uuid4().hex[:6])
        resp = client.patch(f"/api/scenes/{scene_id}", json={
            "version": "1.0",
            "show_on_workbench": True,
        })
        assert resp.status_code == 200

        resp_get = client.get(f"/api/scenes/{scene_id}")
        updated = resp_get.json()
        assert updated.get("version") == "1.0" or updated.get("show_on_workbench") is True, \
            f"场景更新未生效: {updated}"

    def test_list_scenes(self, client: TestClient):
        """场景列表端点正常"""
        name = "列表测试_" + __import__('uuid').uuid4().hex[:6]
        _create_scene(client, name)

        resp = client.get("/api/scenes")
        assert resp.status_code == 200
        scenes = resp.json()
        # 响应可能是 list 或 dict
        if isinstance(scenes, list):
            names = [s.get("name", "") for s in scenes]
        else:
            names = [s.get("name", "") for s in scenes.get("scenes", scenes.get("items", []))]
        assert name in names
