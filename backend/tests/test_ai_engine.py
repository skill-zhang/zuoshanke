"""ai_engine.py 单元测试 — 真实 DB + mock HTTP

测试覆盖:
  1. _resolve_llm()       — Provider 路由解析（mock DB session）
  2. get_settings()        — Settings 路由配置 + 缓存（mock DB session）
  3. invalidate_settings_cache() — 缓存失效
  4. call_llm()            — LLM 非流式调用（mock requests.post）
  5. call_llm_stream()     — LLM 流式调用（mock requests.post）
  6. call_qwen_chat()      — wrapper 正确传参
  7. _stream_qwen()        — wrapper 正确传参
"""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import AiProvider, AiModel, Setting, SETTINGS_ID, DEFAULT_ROUTING
from utils import make_id


# ═══════════════════════════════════════════
# 全局设置：测试用常量
# ═══════════════════════════════════════════
LOCAL_PROV_ID = "pd-test-local"
LOCAL_MODEL_ID = "pm-test-qwen"
DEEPSEEK_PROV_ID = "pd-test-deepseek"
DEEPSEEK_MODEL_ID = "pm-test-dsv4"


def _reset_ai_settings_cache():
    """测试前后清空 ai_engine 的全局缓存"""
    import ai_engine
    ai_engine._settings_cache = None


def _make_test_db():
    """创建 in-memory 测试 DB，返回 engine 和 sessionmaker"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


def _seed_providers(db):
    """插入测试用 Provider + Model"""
    p_local = AiProvider(
        id=LOCAL_PROV_ID, name="local-qwen",
        base_url="http://localhost:8080/v1", api_key="",
        provider_type="local", is_active=True,
    )
    m_local = AiModel(
        id=LOCAL_MODEL_ID, provider_id=LOCAL_PROV_ID,
        name="qwen3.5-9b", display_name="Qwen 3.5 9B",
    )
    p_ds = AiProvider(
        id=DEEPSEEK_PROV_ID, name="deepseek",
        base_url="https://api.deepseek.com", api_key="sk-test-key",
        provider_type="openai-compatible", is_active=True,
    )
    m_ds = AiModel(
        id=DEEPSEEK_MODEL_ID, provider_id=DEEPSEEK_PROV_ID,
        name="deepseek-chat", display_name="DeepSeek V4 Flash",
    )
    db.add_all([p_local, m_local, p_ds, m_ds])
    db.commit()


class TestResolveLlm(unittest.TestCase):
    """_resolve_llm() — Provider 路由解析"""

    def setUp(self):
        self.engine, self.TestSession = _make_test_db()
        self.db = self.TestSession()
        _seed_providers(self.db)
        _reset_ai_settings_cache()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        _reset_ai_settings_cache()

    # ── 测试用例 ──

    @patch("database.SessionLocal")
    def test_resolve_local_provider(self, mock_sl):
        """通过 provider_id/model_id 解析出本地 Qwen"""
        mock_sl.return_value = self.db
        from ai_engine import _resolve_llm

        cfg = {
            "provider_id": LOCAL_PROV_ID,
            "model_id": LOCAL_MODEL_ID,
            "provider": "local",
            "model": "qwen3.5-9b",
        }
        base_url, api_key, model_name = _resolve_llm(cfg)
        # /v1 后缀应被标准化移除
        self.assertEqual(base_url, "http://localhost:8080")
        self.assertEqual(api_key, "")
        self.assertEqual(model_name, "qwen3.5-9b")

    @patch("database.SessionLocal")
    def test_resolve_deepseek_provider(self, mock_sl):
        """通过 provider_id/model_id 解析出 DeepSeek"""
        mock_sl.return_value = self.db
        from ai_engine import _resolve_llm

        cfg = {
            "provider_id": DEEPSEEK_PROV_ID,
            "model_id": DEEPSEEK_MODEL_ID,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
        }
        base_url, api_key, model_name = _resolve_llm(cfg)
        self.assertEqual(base_url, "https://api.deepseek.com")
        self.assertEqual(api_key, "sk-test-key")
        self.assertEqual(model_name, "deepseek-chat")

    def test_resolve_fallback_deepseek_string(self):
        """无 provider_id 时 fallback 到字符串 deepseek"""
        from ai_engine import _resolve_llm, DEEPSEEK_BASE_URL
        cfg = {
            "provider_id": "",
            "model_id": "",
            "provider": "deepseek",
            "model": "flash",
        }
        base_url, api_key, model_name = _resolve_llm(cfg)
        self.assertEqual(base_url, DEEPSEEK_BASE_URL.rstrip("/"))
        self.assertEqual(model_name, "deepseek-chat")

    def test_resolve_fallback_local_string(self):
        """无 provider_id 时 fallback 到字符串 local（QWEN_API）"""
        from ai_engine import _resolve_llm
        from config.urls import QWEN_API
        cfg = {
            "provider_id": "",
            "model_id": "",
            "provider": "local",
            "model": "qwen3.5-9b",
        }
        base_url, api_key, model_name = _resolve_llm(cfg)
        expected = QWEN_API.rstrip("/")
        if expected.endswith("/v1"):
            expected = expected[:-3]
        self.assertEqual(base_url, expected)
        self.assertEqual(api_key, "")
        self.assertEqual(model_name, "qwen3.5-9b")

    def test_resolve_empty_cfg_returns_local(self):
        """空配置 fallback 到本地"""
        from ai_engine import _resolve_llm
        base_url, api_key, model_name = _resolve_llm({})
        # fallback_provider="" → else 分支 → local
        self.assertTrue("localhost" in base_url or "127.0" in base_url)

    @patch("database.SessionLocal")
    def test_resolve_db_nonexistent_fallback(self, mock_sl):
        """DB 查询找不到 provider 时 fallback 到字符串"""
        mock_sl.return_value = self.db
        from ai_engine import _resolve_llm
        cfg = {
            "provider_id": "pd-nonexistent",
            "model_id": "pm-nonexistent",
            "provider": "local",
            "model": "qwen3.5-9b",
        }
        base_url, _, _ = _resolve_llm(cfg)
        from config.urls import QWEN_API
        expected = QWEN_API.rstrip("/")
        if expected.endswith("/v1"):
            expected = expected[:-3]
        self.assertEqual(base_url, expected)

    @patch("database.SessionLocal")
    def test_resolve_v1_suffix_normalization(self, mock_sl):
        """base_url 末尾的 /v1 被标准化移除"""
        mock_sl.return_value = self.db
        from ai_engine import _resolve_llm

        # 插入一个带 /v1 的 provider
        p = AiProvider(
            id="pd-v1test", name="v1-test",
            base_url="http://test:8080/v1", api_key="",
            provider_type="openai-compatible", is_active=True,
        )
        m = AiModel(
            id="pm-v1test", provider_id="pd-v1test",
            name="test-model",
        )
        self.db.add(p)
        self.db.add(m)
        self.db.commit()

        cfg = {"provider_id": "pd-v1test", "model_id": "pm-v1test"}
        base_url, api_key, model_name = _resolve_llm(cfg)
        self.assertEqual(base_url, "http://test:8080")
        self.assertEqual(model_name, "test-model")


class TestGetSettings(unittest.TestCase):
    """get_settings() — 路由配置读取 + 缓存"""

    def setUp(self):
        self.engine, self.TestSession = _make_test_db()
        self.db = self.TestSession()
        _seed_providers(self.db)
        _reset_ai_settings_cache()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        _reset_ai_settings_cache()

    def test_get_settings_default_route(self):
        """无 DB setting 时返回 DEFAULT_ROUTING 的值"""
        from ai_engine import get_settings
        cfg = get_settings("channel")
        self.assertIn("model", cfg)
        self.assertIn("provider", cfg)
        self.assertIn("temperature", cfg)

    @patch("database.SessionLocal")
    def test_get_settings_custom_route(self, mock_sl):
        """写入自定义 routing 后能正确读取"""
        mock_sl.side_effect = self.TestSession
        from ai_engine import get_settings

        custom_routing = {
            "channel": {"model": "qwen3.5-9b", "provider": "local",
                        "temperature": 0.5, "max_tokens": 2048},
            "scene": {"model": "deepseek-v4-flash", "provider": "deepseek",
                      "temperature": 0.3, "max_tokens": 8192},
        }
        s = Setting(id=SETTINGS_ID, routing=custom_routing)
        self.db.add(s)
        self.db.commit()

        # 设完后要失效缓存，否则 get_settings 读旧数据
        _reset_ai_settings_cache()

        cfg = get_settings("channel")
        self.assertEqual(cfg["model"], "qwen3.5-9b")
        self.assertEqual(cfg["temperature"], 0.5)

        cfg_scene = get_settings("scene")
        self.assertEqual(cfg_scene["model"], "deepseek-v4-flash")

    def test_get_settings_unknown_route_fallback(self):
        """请求不存在的 route 时获得默认值"""
        from ai_engine import get_settings
        cfg = get_settings("nonexistent_route_xyz")
        self.assertIsNotNone(cfg)

    @patch("database.SessionLocal")
    def test_invalidate_settings_cache(self, mock_sl):
        """invalidate_settings_cache 后读取新值"""
        mock_sl.side_effect = self.TestSession
        from ai_engine import get_settings, invalidate_settings_cache

        # 设初始值
        custom = {"channel": {"model": "v1", "provider": "local", "temperature": 0.7}}
        s = Setting(id=SETTINGS_ID, routing=custom)
        self.db.add(s)
        self.db.commit()
        _reset_ai_settings_cache()

        cfg1 = get_settings("channel")
        self.assertEqual(cfg1["model"], "v1")

        # 更新 DB — 赋值新 dict 以触发 SQLAlchemy 变更检测
        s2 = self.db.query(Setting).filter(Setting.id == SETTINGS_ID).first()
        s2.routing = {"channel": {"model": "v2", "provider": "local", "temperature": 0.7}}
        self.db.commit()

        # 未失效缓存前，读的还是旧值
        cfg2 = get_settings("channel")
        self.assertEqual(cfg2["model"], "v1")

        # 失效缓存
        invalidate_settings_cache()

        # 现应读到新值
        cfg3 = get_settings("channel")
        self.assertEqual(cfg3["model"], "v2")


class TestCallLlm(unittest.TestCase):
    """call_llm() — mock requests.post + 模拟 DB session"""

    def setUp(self):
        self.engine, self.TestSession = _make_test_db()
        self.db = self.TestSession()
        _seed_providers(self.db)
        _reset_ai_settings_cache()

        self.route_cfg = {
            "provider_id": LOCAL_PROV_ID,
            "model_id": LOCAL_MODEL_ID,
            "provider": "local",
            "model": "test-model",
            "temperature": 0.7,
            "max_tokens": 4096,
        }

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        _reset_ai_settings_cache()

    @patch("database.SessionLocal")
    @patch("ai_engine.requests.post")
    @patch("agent_core.prompt_caching.inject_prompt_cache_markers")
    def test_call_llm_success(self, mock_cache, mock_post, mock_sl):
        """正常调用返回文本"""
        mock_sl.return_value = self.db
        from ai_engine import call_llm

        mock_cache.return_value = [{"role": "user", "content": "hi"}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello from LLM"}}]
        }
        mock_post.return_value = mock_resp

        result = call_llm(
            [{"role": "user", "content": "hi"}],
            self.route_cfg,
            temperature=0.5,
        )
        self.assertEqual(result, "Hello from LLM")

        # 验证请求参数
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["model"], "qwen3.5-9b")  # DB 中的 model name
        self.assertEqual(kwargs["json"]["temperature"], 0.5)
        self.assertEqual(kwargs["json"]["max_tokens"], 4096)
        self.assertIn("/v1/chat/completions", mock_post.call_args[0][0])

    @patch("database.SessionLocal")
    @patch("ai_engine.requests.post")
    @patch("agent_core.prompt_caching.inject_prompt_cache_markers")
    def test_call_llm_http_error(self, mock_cache, mock_post, mock_sl):
        """HTTP 错误返回 None"""
        mock_sl.return_value = self.db
        from ai_engine import call_llm

        mock_cache.return_value = [{"role": "user", "content": "hi"}]
        mock_post.side_effect = Exception("Connection refused")

        result = call_llm(
            [{"role": "user", "content": "hi"}],
            self.route_cfg,
        )
        self.assertIsNone(result)

    def test_call_llm_empty_route_cfg(self):
        """空 route_cfg 导致 _resolve_llm 失败，返回 None"""
        from ai_engine import call_llm

        result = call_llm(
            [{"role": "user", "content": "hi"}],
            {"provider": "", "model": ""},
        )
        self.assertIsNone(result)

    @patch("database.SessionLocal")
    @patch("ai_engine.requests.post")
    @patch("agent_core.prompt_caching.inject_prompt_cache_markers")
    def test_call_llm_max_tokens_override(self, mock_cache, mock_post, mock_sl):
        """max_tokens 参数传入时覆盖 route_cfg 的值"""
        mock_sl.return_value = self.db
        from ai_engine import call_llm

        mock_cache.return_value = [{"role": "user", "content": "hi"}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_post.return_value = mock_resp

        call_llm(
            [{"role": "user", "content": "hi"}],
            self.route_cfg,
            max_tokens=999,
        )
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["max_tokens"], 999)

    @patch("database.SessionLocal")
    @patch("ai_engine.requests.post")
    @patch("agent_core.prompt_caching.inject_prompt_cache_markers")
    def test_call_llm_prompt_cache_injected(self, mock_cache, mock_post, mock_sl):
        """call_llm 内部调用了 inject_prompt_cache_markers"""
        mock_sl.return_value = self.db
        from ai_engine import call_llm

        mock_cache.return_value = [{"role": "user", "content": "cached"}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_post.return_value = mock_resp

        messages = [{"role": "user", "content": "hi"}]
        call_llm(messages, self.route_cfg)

        mock_cache.assert_called_once_with(messages, model_name="qwen3.5-9b")


class TestCallLlmStream(unittest.TestCase):
    """call_llm_stream() — mock requests.post streaming"""

    def setUp(self):
        self.engine, self.TestSession = _make_test_db()
        self.db = self.TestSession()
        _seed_providers(self.db)
        _reset_ai_settings_cache()

        self.route_cfg = {
            "provider_id": LOCAL_PROV_ID,
            "model_id": LOCAL_MODEL_ID,
            "provider": "local",
            "model": "test-model",
            "temperature": 0.7,
            "max_tokens": 4096,
        }

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        _reset_ai_settings_cache()

    @patch("database.SessionLocal")
    @patch("ai_engine.requests.post")
    @patch("agent_core.prompt_caching.inject_prompt_cache_markers")
    def test_call_llm_stream_yields_tokens(self, mock_cache, mock_post, mock_sl):
        """流式调用逐 token yield"""
        mock_sl.return_value = self.db
        from ai_engine import call_llm_stream

        mock_cache.return_value = [{"role": "user", "content": "hi"}]

        chunks = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
            b'data: {"choices":[{"delta":{"content":" world"}}]}\n',
            b'data: {"choices":[{"delta":{"content":"!"}}]}\n',
            b'data: [DONE]\n',
        ]
        mock_iter = iter(chunks)
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = mock_iter
        mock_post.return_value = mock_resp

        tokens = list(call_llm_stream(
            [{"role": "user", "content": "hi"}],
            self.route_cfg,
        ))
        self.assertEqual(tokens, ["Hello", " world", "!"])

    @patch("database.SessionLocal")
    @patch("ai_engine.requests.post")
    @patch("agent_core.prompt_caching.inject_prompt_cache_markers")
    def test_call_llm_stream_error_yields_none(self, mock_cache, mock_post, mock_sl):
        """流式调用错误时 yield None"""
        mock_sl.return_value = self.db
        from ai_engine import call_llm_stream

        mock_cache.return_value = [{"role": "user", "content": "hi"}]
        mock_post.side_effect = Exception("Stream failed")

        tokens = list(call_llm_stream(
            [{"role": "user", "content": "hi"}],
            self.route_cfg,
        ))
        self.assertEqual(tokens, [None])

    def test_call_llm_stream_empty_route_cfg(self):
        """空 route_cfg 时 yield None"""
        from ai_engine import call_llm_stream

        tokens = list(call_llm_stream(
            [{"role": "user", "content": "hi"}],
            {},
        ))
        self.assertEqual(tokens, [None])


class TestCallQwenChat(unittest.TestCase):
    """call_qwen_chat() — wrapper 正确传参给 call_llm"""

    def setUp(self):
        self.engine, self.TestSession = _make_test_db()
        self.db = self.TestSession()
        _seed_providers(self.db)
        _reset_ai_settings_cache()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        _reset_ai_settings_cache()

    @patch("database.SessionLocal")
    @patch("ai_engine.call_llm")
    def test_call_qwen_chat_passes_messages(self, mock_call_llm, mock_sl):
        """call_qwen_chat 将消息透传给 call_llm"""
        mock_sl.return_value = self.db
        from ai_engine import call_qwen_chat

        mock_call_llm.return_value = "reply"

        messages = [{"role": "user", "content": "hello"}]
        result = call_qwen_chat(messages, temperature=0.3, route="scene")

        self.assertEqual(result, "reply")
        mock_call_llm.assert_called_once()
        args, kwargs = mock_call_llm.call_args
        self.assertEqual(args[0], messages)  # messages
        self.assertEqual(kwargs["temperature"], 0.3)

    @patch("database.SessionLocal")
    @patch("ai_engine.call_llm")
    def test_call_qwen_chat_default_temperature(self, mock_call_llm, mock_sl):
        """temperature=None 时从 route_cfg 读取"""
        mock_sl.return_value = self.db
        from ai_engine import call_qwen_chat

        mock_call_llm.return_value = "reply"
        call_qwen_chat([{"role": "user", "content": "hi"}], route="channel")

        _, kwargs = mock_call_llm.call_args
        self.assertIn("temperature", kwargs)


class TestStreamQwen(unittest.TestCase):
    """_stream_qwen() — wrapper 正确传参给 call_llm_stream"""

    def setUp(self):
        self.engine, self.TestSession = _make_test_db()
        self.db = self.TestSession()
        _seed_providers(self.db)
        _reset_ai_settings_cache()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        _reset_ai_settings_cache()

    @patch("database.SessionLocal")
    @patch("ai_engine.call_llm_stream")
    def test_stream_qwen_passes_to_call_llm_stream(self, mock_stream, mock_sl):
        """_stream_qwen 透传给 call_llm_stream"""
        mock_sl.return_value = self.db
        from ai_engine import _stream_qwen

        mock_stream.return_value = iter(["a", "b"])
        messages = [{"role": "user", "content": "hi"}]
        result = list(_stream_qwen(messages, temperature=0.5, route="scene"))

        self.assertEqual(result, ["a", "b"])
        mock_stream.assert_called_once()

    @patch("database.SessionLocal")
    @patch("ai_engine.call_llm_stream")
    def test_stream_qwen_default_temperature(self, mock_stream, mock_sl):
        """temperature=None 时从 route_cfg 读取"""
        mock_sl.return_value = self.db
        from ai_engine import _stream_qwen

        mock_stream.return_value = iter([])
        list(_stream_qwen([{"role": "user", "content": "hi"}]))

        mock_stream.assert_called_once()
        _, kwargs = mock_stream.call_args
        self.assertIn("temperature", kwargs)
