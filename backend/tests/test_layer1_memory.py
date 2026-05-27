"""
Layer 1-A: 双重记忆池 scope 隔离测试

目标：彻底检验 scope 隔离机制的每一层边界，不放过任何泄露路径。

API 响应格式（已实测确认）：
  POST /api/memory → {"success": true, "data": {"id": "...", "key": "..."}}
  GET  /api/memory → {"success": true, "data": [{id, key, scope, context_id, ...}, ...]}
  GET  /api/memory?scope=scene&scope_only=true → {"success": true, "data": [...]}
  GET  /api/memory/{key} → {"success": true, "data": {id, key, scope, context_id, is_immortal, ...}}
"""
import uuid
import pytest
from fastapi.testclient import TestClient


# ── 辅助函数 ──

def _post_memory(client, key, content, scope="zhu", context_id=None):
    """创建记忆，返回 {success, key, id}"""
    body = {"category": "user", "key": key, "content": content,
            "scope": scope}
    if context_id is not None:
        body["context_id"] = context_id
    resp = client.post("/api/memory", json=body)
    assert resp.status_code == 200, f"POST /api/memory 失败: {resp.text}"
    d = resp.json()
    return {
        "success": d.get("success", False),
        "key": d.get("data", {}).get("key", ""),
        "id": d.get("data", {}).get("id", ""),
    }


def _list_memories(client, scope=None, context_id=None, scope_only=False):
    """获取记忆列表，返回 key 集合"""
    params = {}
    if scope:
        params["scope"] = scope
    if context_id:
        params["context_id"] = context_id
    if scope_only:
        params["scope_only"] = "true"
    resp = client.get("/api/memory", params=params)
    assert resp.status_code == 200
    data = resp.json().get("data", [])
    return {m.get("key", "") for m in data}


def _get_memory(client, key):
    """获取单条记忆详情"""
    resp = client.get(f"/api/memory/{key}")
    if resp.status_code == 404:
        return None
    assert resp.status_code == 200
    return resp.json().get("data", {})


def _assert_keys(expected, actual_set, label=""):
    """断言 key 集合匹配"""
    missing = expected - actual_set
    extra = actual_set - expected
    msg = []
    if missing:
        msg.append(f"缺少: {missing}")
    if extra:
        msg.append(f"多余: {extra}")
    assert not msg, f"{label}: {'; '.join(msg)}"


# ── 测试 ──

class TestBasicCRUD:
    """基础 CRUD —— 测试用例本身可信"""

    def test_create_zhu(self, client: TestClient):
        r = _post_memory(client, "base_zhu", "zhu数据", scope="zhu")
        assert r["success"]
        assert r["key"] == "base_zhu"

    def test_create_scene(self, client: TestClient):
        r = _post_memory(client, "base_scene", "scene数据", scope="scene", context_id="scene-1")
        assert r["success"]
        assert r["key"] == "base_scene"

    def test_read_by_key(self, client: TestClient):
        _post_memory(client, "base_read", "可读", scope="zhu")
        mem = _get_memory(client, "base_read")
        assert mem is not None
        assert mem.get("key") == "base_read"
        assert mem.get("content") == "可读"
        assert mem.get("scope") == "zhu"

    def test_delete_by_key(self, client: TestClient):
        _post_memory(client, "base_del", "待删", scope="zhu")
        resp = client.delete("/api/memory/base_del")
        assert resp.status_code == 200
        assert _get_memory(client, "base_del") is None


class TestScopeIsolation:
    """P0: scope 隔离——双池架构根基"""

    def test_zhu_invisible_in_scene(self, client: TestClient):
        """写入 zhu → scene scope_only 中不可见"""
        _post_memory(client, "iso_zhu_1", "本体秘密", scope="zhu")
        keys = _list_memories(client, scope="scene", scope_only=True)
        assert "iso_zhu_1" not in keys, "zhu 记忆泄露到 scene scope"

    def test_zhu_invisible_in_scene_with_context(self, client: TestClient):
        """写入 zhu → scene+X scope_only 中不可见"""
        _post_memory(client, "iso_zhu_2", "本体秘密2", scope="zhu")
        keys = _list_memories(client, scope="scene", context_id="scene-any", scope_only=True)
        assert "iso_zhu_2" not in keys, "zhu 记忆泄露到 scene+X scope"

    def test_scene_a_invisible_in_scene_b(self, client: TestClient):
        """写入 scene/A → scene/B 不可见"""
        _post_memory(client, "iso_scene_a", "A的秘密", scope="scene", context_id="scene-A")
        keys_b = _list_memories(client, scope="scene", context_id="scene-B", scope_only=True)
        assert "iso_scene_a" not in keys_b, "scene/A 记忆泄露到 scene/B"

    def test_scene_visible_in_own_scope(self, client: TestClient):
        """写入 scene/A → scene/A 可见"""
        _post_memory(client, "iso_scene_own", "自己的记忆", scope="scene", context_id="scene-own")
        keys = _list_memories(client, scope="scene", context_id="scene-own", scope_only=True)
        assert "iso_scene_own" in keys, "自己的 scene 中找不到刚写入的记忆"


class TestMergeMode:
    """P0: 合并模式——分身默认应能看到本体记忆"""

    def test_zhu_visible_without_scope_only(self, client: TestClient):
        """不加 scope_only → zhu 可见（默认合并模式）"""
        _post_memory(client, "merge_zhu", "本体共享记忆", scope="zhu")
        keys = _list_memories(client)  # 无 scope 过滤
        assert "merge_zhu" in keys, "不加 scope_only 时 zhu 记忆应可见"

    def test_zhu_visible_in_scene_merge_mode(self, client: TestClient):
        """scope=scene 不加 scope_only → zhu + scene 合并可见"""
        _post_memory(client, "merge_zhu2", "本体2", scope="zhu")
        _post_memory(client, "merge_scene", "分身数据", scope="scene", context_id="merge-ctx")
        keys = _list_memories(client, scope="scene", context_id="merge-ctx")  # scope_only=False
        assert "merge_zhu2" in keys, "合并模式下 zhu 应可见"
        assert "merge_scene" in keys, "合并模式下 scene 应可见"


class TestReverseIsolation:
    """P0: 反向隔离——写入 scene 不污染 zhu"""

    def test_scene_memories_not_in_zhu(self, client: TestClient):
        """写入 scene → zhu scope_only 中不可见"""
        _post_memory(client, "rev_scene", "分身专属", scope="scene", context_id="rev-ctx")
        keys = _list_memories(client, scope="zhu", scope_only=True)
        assert "rev_scene" not in keys, "scene 记忆反向泄露到 zhu"

    def test_channel_memories_not_in_zhu(self, client: TestClient):
        """写入 channel → zhu scope_only 中不可见"""
        _post_memory(client, "rev_ch", "频道专属", scope="channel", context_id="ch-ctx")
        keys = _list_memories(client, scope="zhu", scope_only=True)
        assert "rev_ch" not in keys, "channel 记忆反向泄露到 zhu"


class TestMultiScopeCoexistence:
    """P0: 多 scope 共存——三者互不干扰"""

    def test_three_scopes_independent(self, client: TestClient):
        """zhu + scene/A + channel/B 各写一条，各自 scope_only 只看到自己的"""
        _post_memory(client, "multi_zhu", "zhu", scope="zhu")
        _post_memory(client, "multi_scene", "scene", scope="scene", context_id="multi-scene")
        _post_memory(client, "multi_ch", "channel", scope="channel", context_id="multi-ch")

        zhu_keys = _list_memories(client, scope="zhu", scope_only=True)
        scene_keys = _list_memories(client, scope="scene", context_id="multi-scene", scope_only=True)
        ch_keys = _list_memories(client, scope="channel", context_id="multi-ch", scope_only=True)

        assert "multi_zhu" in zhu_keys, "zhu scope 应包含 zhu 记忆"
        assert "multi_scene" in scene_keys, "scene 应包含 scene 记忆"
        assert "multi_ch" in ch_keys, "channel 应包含 channel 记忆"

        assert "multi_scene" not in zhu_keys, "scene 泄露到 zhu"
        assert "multi_ch" not in zhu_keys, "channel 泄露到 zhu"
        assert "multi_zhu" not in scene_keys, "zhu 泄露到 scene"
        assert "multi_zhu" not in ch_keys, "zhu 泄露到 channel"


class TestContextIsolationWithinScope:
    """P0: 同一 scope 下不同 context_id 隔离"""

    def test_different_contexts_isolated(self, client: TestClient):
        """scene/A 和 scene/B 各自的数据互不可见"""
        _post_memory(client, "ctx_a_data", "这是场景A独有的对话记录", scope="scene", context_id="ctx-A")
        _post_memory(client, "ctx_b_data", "场景B讨论的是完全不同的话题", scope="scene", context_id="ctx-B")

        a_keys = _list_memories(client, scope="scene", context_id="ctx-A", scope_only=True)
        b_keys = _list_memories(client, scope="scene", context_id="ctx-B", scope_only=True)

        assert "ctx_a_data" in a_keys
        assert "ctx_b_data" in b_keys
        assert "ctx_b_data" not in a_keys, "B 泄露到 A"
        assert "ctx_a_data" not in b_keys, "A 泄露到 B"


class TestMemoryScopePersistence:
    """P1: scope 字段持久化——写入时指定的 scope 在读取时不变"""

    def test_zhu_scope_persists(self, client: TestClient):
        _post_memory(client, "persist_zhu", "test", scope="zhu")
        mem = _get_memory(client, "persist_zhu")
        assert mem.get("scope") == "zhu"

    def test_scene_scope_persists(self, client: TestClient):
        _post_memory(client, "persist_scene", "test", scope="scene", context_id="persist-ctx")
        mem = _get_memory(client, "persist_scene")
        assert mem.get("scope") == "scene"
        assert mem.get("context_id") == "persist-ctx"

    def test_channel_scope_persists(self, client: TestClient):
        _post_memory(client, "persist_ch", "test", scope="channel", context_id="persist-ch")
        mem = _get_memory(client, "persist_ch")
        assert mem.get("scope") == "channel"
        assert mem.get("context_id") == "persist-ch"


class TestImmortalRule:
    """P0: is_immortal 自动赋值规则"""

    def test_zhu_is_immortal(self, client: TestClient):
        _post_memory(client, "im_zhu", "不朽", scope="zhu")
        mem = _get_memory(client, "im_zhu")
        assert mem.get("is_immortal") is True, f"zhu scope 应自动 is_immortal=True，实际={mem.get('is_immortal')}"

    def test_scene_is_not_immortal(self, client: TestClient):
        _post_memory(client, "im_scene", "可衰减", scope="scene", context_id="im-ctx")
        mem = _get_memory(client, "im_scene")
        assert mem.get("is_immortal") is False, f"scene scope 应为 is_immortal=False，实际={mem.get('is_immortal')}"

    def test_channel_is_not_immortal(self, client: TestClient):
        _post_memory(client, "im_ch", "可衰减", scope="channel", context_id="im-ch")
        mem = _get_memory(client, "im_ch")
        assert mem.get("is_immortal") is False, f"channel scope 应为 is_immortal=False，实际={mem.get('is_immortal')}"
