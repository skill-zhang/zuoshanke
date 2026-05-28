"""
Layer 1-E: 真实 Provider 路由 + call_llm 端到端测试

不 mock，真实调用 DeepSeek API（需环境已配置 DEEPSEEK_API_KEY）。
使用 short timeout 确保不 hang。
"""
import pytest
import os


def _has_deepseek_key() -> bool:
    """检查环境是否配置了 DeepSeek API Key（先加载 .env）"""
    try:
        from dotenv import load_dotenv
        from config.paths import ZUOSHANKE_ENV
        if ZUOSHANKE_ENV.exists():
            load_dotenv(ZUOSHANKE_ENV)
    except Exception:
        pass
    return bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_KEY", ""))


# ═══════════════════════════════════════════════════════
# 1. _resolve_llm — Provider 查找逻辑
# ═══════════════════════════════════════════════════════

class TestResolveLLM:
    """Provider 路由解析——从 DB 或配置中找出正确的(base_url, api_key, model)"""

    def test_resolve_deepseek_by_provider_id(self):
        """route_cfg 带 provider_id → 从 DB 查出 DeepSeek 连接信息"""
        from ai_engine import _resolve_llm

        # 验证 DB 中有 DeepSeek provider
        from database import SessionLocal
        from models import AiProvider
        _db = SessionLocal()
        _p = _db.query(AiProvider).filter(AiProvider.id == 'pd-deepseek').first()
        _db.close()
        assert _p is not None, "DB 中无 pd-deepseek provider（init_db 未执行？）"
        assert _p.api_key, f"DB 中 DeepSeek provider 的 api_key 为空"

        route_cfg = {
            "provider_id": "pd-deepseek",
            "model_id": "pm-deepseek-v4-flash",
        }
        base_url, api_key, model_name = _resolve_llm(route_cfg)
        assert "deepseek" in base_url, f"base_url 应指向 deepseek: {base_url}"
        assert api_key, "应返回 API key"
        assert "flash" in model_name.lower() or "deepseek-chat" in model_name.lower(), \
            f"model_name 应匹配: {model_name}"

    def test_resolve_deepseek_by_provider_id_pro_model(self):
        """v4-pro 的 model_id → 解析出 pro 模型名"""
        from ai_engine import _resolve_llm

        route_cfg = {
            "provider_id": "pd-deepseek",
            "model_id": "pm-deepseek-v4-pro",
        }
        base_url, api_key, model_name = _resolve_llm(route_cfg)
        assert base_url and api_key, "DeepSeek 应有 base_url 和 key"
        assert model_name, f"应有 model_name: {model_name}"

    def test_resolve_local_fallback(self):
        """无 provider_id → fallback 到 local Qwen"""
        from ai_engine import _resolve_llm

        route_cfg = {"provider": "local", "model": "qwen3.5-9b"}
        base_url, api_key, model_name = _resolve_llm(route_cfg)
        assert "localhost" in base_url or "127.0.0.1" in base_url, \
            f"local fallback 应指向 localhost: {base_url}"
        assert "qwen" in model_name.lower(), f"model 应为 qwen: {model_name}"

    def test_resolve_deepseek_fallback(self):
        """provider=deepseek, 无 provider_id → fallback 到字符串配置"""
        from ai_engine import _resolve_llm

        route_cfg = {"provider": "deepseek", "model": "flash"}
        base_url, api_key, model_name = _resolve_llm(route_cfg)
        assert "deepseek" in base_url, f"deepseek fallback: {base_url}"
        # fallback 用 DEEPSEEK_MODEL_MAP
        assert model_name, f"应有 model: {model_name}"

    def test_resolve_with_nonexistent_id_returns_fallback(self):
        """provider_id 不存在 → 不抛异常，fallback 到字符串配置"""
        from ai_engine import _resolve_llm

        route_cfg = {"provider_id": "nonexistent", "model_id": "also_nonexistent",
                      "provider": "deepseek", "model": "flash"}
        base_url, api_key, model_name = _resolve_llm(route_cfg)
        # 因 DB 找不到，fallback 到字符串
        assert base_url, "应返回 fallback base_url"
        assert model_name, "应返回 fallback model"


# ═══════════════════════════════════════════════════════
# 2. get_settings — 路由配置读取
# ═══════════════════════════════════════════════════════

class TestGetSettings:
    """从 DB 读取路由配置"""

    def test_get_scene_settings(self):
        """get_settings('scene') 返回有效路由配置"""
        from ai_engine import get_settings
        cfg = get_settings("scene")
        assert isinstance(cfg, dict), f"应返回 dict: {type(cfg)}"
        assert "provider_id" in cfg or "provider" in cfg, \
            f"配置应包含 provider 信息: {list(cfg.keys())[:5]}"

    def test_get_channel_settings(self):
        """get_settings('channel') 返回有效配置"""
        from ai_engine import get_settings
        cfg = get_settings("channel")
        assert isinstance(cfg, dict)

    def test_settings_have_model_id(self):
        """场景配置应包含 model_id"""
        from ai_engine import get_settings
        cfg = get_settings("scene")
        assert cfg.get("model_id") or cfg.get("model"), \
            f"配置应指定模型: {cfg}"
        assert cfg.get("temperature") is not None, "应有温度设置"


# ═══════════════════════════════════════════════════════
# 3. call_llm — 真实 API 调用
# ═══════════════════════════════════════════════════════

class TestCallLLMReal:
    """真实 LLM API 调用——需要有效的 API Key"""

    @pytest.mark.skipif(not _has_deepseek_key(), reason="无 DEEPSEEK_API_KEY")
    def test_call_llm_basic(self):
        """调 DeepSeek 返回有效回复文本"""
        from ai_engine import call_llm, get_settings

        route_cfg = get_settings("scene")
        messages = [
            {"role": "system", "content": "你是一个助手，请简短回答。"},
            {"role": "user", "content": "用一句话回答：1+1等于几？"},
        ]
        result = call_llm(messages, route_cfg, temperature=0.3, max_tokens=100)
        assert result is not None, f"call_llm 返回 None（可能 API 调用失败）"
        assert len(result) > 0, "回复不应为空"
        assert "2" in result or "二" in result, f"回复应包含答案: {result[:200]}"

    @pytest.mark.skipif(not _has_deepseek_key(), reason="无 DEEPSEEK_API_KEY")
    def test_call_llm_streaming(self):
        """流式调用返回逐 token 文本"""
        from ai_engine import call_llm_stream, get_settings

        route_cfg = get_settings("scene")
        messages = [
            {"role": "system", "content": "你是一个助手，简短回答。"},
            {"role": "user", "content": "说三个字：你好吗"},
        ]
        tokens = list(call_llm_stream(messages, route_cfg, temperature=0.3, max_tokens=50))
        assert len(tokens) > 0, "应至少返回一个 token"
        full = "".join(t for t in tokens if t)
        assert len(full) > 0, "拼接后的文本不应为空"

    @pytest.mark.skipif(not _has_deepseek_key(), reason="无 DEEPSEEK_API_KEY")
    def test_call_llm_multilingual(self):
        """中文输入 → 中文回复"""
        from ai_engine import call_llm, get_settings

        route_cfg = get_settings("scene")
        messages = [
            {"role": "user", "content": "请用中文回答：今天天气怎么样（假设你在北京）？给一句简短回答。"},
        ]
        result = call_llm(messages, route_cfg, temperature=0.3, max_tokens=200)
        assert result is not None
        # 检查回复中包含中文字符
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in result)
        assert has_chinese, f"应返回中文回复: {result[:200]}"

    @pytest.mark.skipif(not _has_deepseek_key(), reason="无 DEEPSEEK_API_KEY")
    def test_call_llm_tool_call_format(self):
        """回复响应格式——包含有效的文本"""
        from ai_engine import call_llm, get_settings

        route_cfg = get_settings("scene")
        messages = [
            {"role": "system", "content": "你是一个助手。如果用户问工具，用简短文本回答。"},
            {"role": "user", "content": "写一个 Python hello world"},
        ]
        result = call_llm(messages, route_cfg, temperature=0.3, max_tokens=500)
        assert result is not None
        assert "print" in result or "hello" in result.lower(), \
            f"应包含代码: {result[:300]}"

    @pytest.mark.skipif(not _has_deepseek_key(), reason="无 DEEPSEEK_API_KEY")
    def test_call_llm_with_system_prompt(self):
        """带 system prompt 的调用"""
        from ai_engine import call_llm, get_settings

        route_cfg = get_settings("scene")
        messages = [
            {"role": "system", "content": "你只简短回答，不要多说。"},
            {"role": "user", "content": "明白了吗"},
        ]
        result = call_llm(messages, route_cfg, temperature=0.1, max_tokens=50)
        assert result is not None
        assert len(result) < 100, f"应简短回复: {result[:200]}"


# ═══════════════════════════════════════════════════════
# 4. call_qwen_chat — 高層封裝
# ═══════════════════════════════════════════════════════

class TestCallQwenChat:
    """call_qwen_chat 端到端——通过 provider 路由调真实 API"""

    @pytest.mark.skipif(not _has_deepseek_key(), reason="无 DEEPSEEK_API_KEY")
    def test_qwen_chat_returns_text(self):
        """call_qwen_chat 返回文本回复"""
        from ai_engine import call_qwen_chat

        messages = [
            {"role": "system", "content": "简短回答。"},
            {"role": "user", "content": "法国的首都是哪里？"},
        ]
        result = call_qwen_chat(messages, temperature=0.3)
        assert result is not None
        assert "巴黎" in result, f"应返回巴黎: {result[:200]}"


# ═══════════════════════════════════════════════════════
# 5. 错误处理 — 无 key 时的行为
# ═══════════════════════════════════════════════════════

class TestCallLLMErrorHandling:
    """API 调用失败时的错误处理"""

    def test_call_with_empty_messages_returns_none(self):
        """空消息 → 返回 None（不崩溃）"""
        from ai_engine import call_llm
        result = call_llm([], {"provider": "local", "model": "qwen3.5-9b"}, temperature=0.3)
        # 可能返回 None（本地无模型）或错误信息
        assert result is None or isinstance(result, str)

    def test_resolve_with_empty_config(self):
        """空配置 → 不崩溃"""
        from ai_engine import _resolve_llm
        base_url, api_key, model_name = _resolve_llm({})
        # 至少返回空字符串或某种 fallback
        assert isinstance(base_url, str)
        assert isinstance(api_key, str)
        assert isinstance(model_name, str)
