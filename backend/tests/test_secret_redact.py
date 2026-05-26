"""测试秘密遮盖系统"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from secret_redact import (
    redact,
    SecretRedactFilter,
    redact_headers,
    redact_text,
    _is_sensitive_key,
    _redact_value,
    _redact_string,
    _mask_secret,
)


def test_is_sensitive_key():
    """测试敏感字段名检测"""
    assert _is_sensitive_key("api_key")
    assert _is_sensitive_key("API_KEY")
    assert _is_sensitive_key("Api-Key")
    assert _is_sensitive_key("password")
    assert _is_sensitive_key("secret")
    assert _is_sensitive_key("token")
    assert _is_sensitive_key("authorization")
    assert not _is_sensitive_key("name")
    assert not _is_sensitive_key("base_url")
    assert not _is_sensitive_key("model")


def test_redact_value():
    """测试值遮盖"""
    result = _redact_value("sk-abc123xyz456")
    assert result == "sk-a***...***"
    assert "sk-abc" not in result  # 不应包含完整值

    # 短值
    result = _redact_value("abc")
    assert result == "***...***"


def test_redact_string():
    """测试字符串中的敏感模式遮盖"""
    # API Key
    result = _redact_string("my key is sk-abc123xyz4567890abcdefghij")
    assert "sk-abc123xyz4567890abcdefghij" not in result
    assert "sk-a***" in result or "***" in result

    # Bearer token
    result = _redact_string("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
    assert "***" in result

    # 普通文本不应被遮盖
    result = _redact_string("Hello, this is a normal message")
    assert result == "Hello, this is a normal message"


def test_redact_dict():
    """测试字典遮盖"""
    data = {
        "name": "Test Provider",
        "base_url": "https://api.example.com",
        "api_key": "sk-abc123xyz456",
        "password": "mysecretpass123",
        "models": [{"name": "gpt-4", "api_key": "sk-inner-key"}],
    }
    result = redact(data)

    # 非敏感字段保留
    assert result["name"] == "Test Provider"
    assert result["base_url"] == "https://api.example.com"

    # 敏感字段遮盖
    assert result["api_key"] != "sk-abc123xyz456"
    assert "***" in result["api_key"]
    assert result["password"] != "mysecretpass123"
    assert "***" in result["password"]

    # 嵌套遮盖
    assert result["models"][0]["name"] == "gpt-4"
    assert "***" in result["models"][0]["api_key"]


def test_redact_list():
    """测试列表遮盖"""
    data = [
        {"name": "model1", "api_key": "sk-key1"},
        {"name": "model2", "api_key": "sk-key2"},
    ]
    result = redact(data)
    assert len(result) == 2
    assert result[0]["name"] == "model1"
    assert "***" in result[0]["api_key"]
    assert result[1]["name"] == "model2"
    assert "***" in result[1]["api_key"]


def test_redact_headers():
    """测试请求头遮盖"""
    headers = {
        "Authorization": "Bearer sk-abc123xyz456",
        "Content-Type": "application/json",
        "X-API-Key": "my-secret-api-key-12345",
    }
    result = redact_headers(headers)

    # Authorization 被遮盖
    assert result["Authorization"] != headers["Authorization"]
    assert "***" in result["Authorization"]

    # Content-Type 不变
    assert result["Content-Type"] == "application/json"

    # X-API-Key 被遮盖
    assert "***" in result["X-API-Key"]

    # 原始字典不变
    assert headers["Authorization"] == "Bearer sk-abc123xyz456"


def test_log_filter():
    """测试日志过滤器"""
    logger = logging.getLogger("test_redact")
    logger.setLevel(logging.DEBUG)

    # 添加过滤器
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SecretRedactFilter())
    logger.addHandler(handler)

    # 记录含敏感信息的日志（不会抛异常即可）
    logger.info("API Key: sk-abc123xyz4567890abcdefghijklmn")
    logger.info("Bearer token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0")

    # 清理
    logger.removeHandler(handler)


def test_redact_preserves_structure():
    """测试遮盖不改变数据结构"""
    data = {
        "name": "test",
        "config": {
            "timeout": 30,
            "retry": True,
            "count": 42,
            "api_key": "sk-secret",
        },
        "tags": ["a", "b"],
        "score": 3.14,
    }
    result = redact(data)

    assert isinstance(result, dict)
    assert isinstance(result["config"], dict)
    assert isinstance(result["tags"], list)
    assert isinstance(result["score"], float)
    assert result["config"]["timeout"] == 30
    assert result["config"]["retry"] is True
    assert result["config"]["count"] == 42


# ═══════════════════════════════════════════════════
# v2 新增测试
# ═══════════════════════════════════════════════════

def test_mask_secret():
    """测试 mask_secret 遮盖逻辑"""
    # 长值保留首尾
    assert _mask_secret("sk-proj-abcdef1234567890") == "sk-p...7890"
    assert _mask_secret("ghp_abc123def456", head=4, tail=4) == "ghp_...f456"

    # 短值完全遮盖
    assert _mask_secret("short") == "***...***"

    # 空值
    assert _mask_secret("") == ""
    assert _mask_secret(None) == ""


def test_github_pat():
    """GitHub PAT 遮盖"""
    text = "token is ghp_abcdef1234567890abcdef1234567890abcdef12"
    r = redact_text(text)
    assert "ghp_abcdef" not in r
    assert "***" in r

    text = "fine_grained: github_pat_11AAAfakeToken1234567890abcdefghij1234567890"
    r = redact_text(text)
    # 整个 token 被匹配替换，前缀不在输出中
    assert "github_pat_11A" not in r
    assert "***" in r


def test_google_api_key():
    """Google AIza key 遮盖"""
    text = "key=AIzaSyABCdefGHIjklMNOpqrSTUvwxYZ1234567890abcde"
    r = redact_text(text)
    assert "AIzaSyABC" not in r
    assert "***" in r


def test_slack_token():
    """Slack token 遮盖"""
    text = "slack_token = xoxb-123456789012-123456789012-abcdefghijklmn"
    r = redact_text(text)
    assert "xoxb-123456789012" not in r
    assert "***" in r


def test_huggingface_token():
    """HuggingFace token 遮盖"""
    text = "hf_token = hf_abcdefghijklmnopqrstuvwxyz"
    r = redact_text(text)
    assert "abcdefghijklmnopqrstuvwxyz" not in r
    assert "***" in r


def test_groq_key():
    """Groq key 遮盖"""
    text = "groq: gsk_abcdefghijklmnopqrstuvwxyz123456"
    r = redact_text(text)
    assert "gsk_abcdefghijklmnopqrstuvwxyz" not in r
    assert "***" in r


def test_stripe_key():
    """Stripe key 遮盖"""
    text = "stripe: sk_live_abcdefghijklmnopqrstuvwxyz123456"
    r = redact_text(text)
    assert "sk_live_abcdefghijklmnopqrstuvwxyz" not in r
    assert "***" in r


def test_aws_key():
    """AWS Access Key 遮盖"""
    text = "aws_key=AKIAIOSFODNN7EXAMPLE"
    r = redact_text(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in r
    assert "***" in r


def test_private_key_block():
    """私钥块完全遮盖"""
    text = ("-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA...\n"
            "-----END RSA PRIVATE KEY-----")
    r = redact_text(text)
    assert "RSA PRIVATE KEY" not in r
    assert "MIIEp" not in r
    assert "[REDACTED PRIVATE KEY]" in r


def test_db_connection_string():
    """数据库连接串密码遮盖"""
    text = "postgres://user:mysecretpassword@localhost:5432/dbname"
    r = redact_text(text)
    assert "mysecretpassword" not in r
    assert "***" in r

    # mysql
    text = "mysql://admin:pass123@host.com/mydb"
    r = redact_text(text)
    assert "pass123" not in r


def test_jwt_token():
    """JWT token 遮盖"""
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwxyz"
    text = f"token={jwt}"
    r = redact_text(text)
    assert jwt not in r
    assert "***" in r


def test_url_query_param():
    """URL query 敏感参数遮盖"""
    text = "https://example.com/callback?code=abc123&state=xyz&access_token=secret123"
    r = redact_text(text)
    assert "access_token=secret123" not in r
    assert "access_token=***" in r
    assert "code=abc123" not in r
    assert "code=***" in r
    assert "state=xyz" in r


def test_phone_number():
    """手机号遮盖"""
    text = "phone: +8613800138000"
    r = redact_text(text)
    assert "+86" in r or "+8613" in r
    assert "+8613800138000" not in r
    assert "****" in r


def test_env_assignment():
    """环境变量赋值遮盖"""
    text = "export OPENAI_API_KEY=sk-abcdef1234567890abcdef1234567890"
    r = redact_text(text)
    assert "sk-abcdef" not in r
    assert "=" in r
    assert "***" in r


def test_json_field():
    """JSON 敏感字段遮盖"""
    text = '{"name": "test", "apiKey": "sk-abcdef1234567890", "token": "eyJhbGciOiJIUzI1NiJ9"}'
    r = redact_text(text)
    assert '"apiKey": "sk-abcdef' not in r
    assert '"token": "eyJhbGci' not in r
    assert '"name": "test"' in r


def test_code_file_mode():
    """code_file=True 跳过 env/JSON 正则，避免源码误报"""
    text = 'DEEPSEEK_API_KEY = "sk-test-key-for-testing-only-12345678"'
    r_normal = redact_text(text, code_file=False)
    assert "test-key" not in r_normal

    r_code = redact_text(text, code_file=True)
    # 源码模式下 env 赋值跳过，但前缀正则仍生效
    assert "sk-test-key" not in r_code  # _PREFIX_RE 仍会匹配


def test_force_mode():
    """force=True 忽略开关强制遮盖"""
    text = "sk-abcdef1234567890abcdef1234567890"
    r = redact_text(text, force=True)
    assert "sk-abcdef1234567890" not in r
    assert "***" in r


def test_switch_toggle():
    """测试开关状态一致性"""
    from secret_redact import _REDACT_ENABLED
    if not _REDACT_ENABLED:
        data = {"api_key": "sk-test"}
        assert redact(data)["api_key"] == "sk-test"
    else:
        data = {"api_key": "sk-test-long-enough-12345678"}
        r = redact(data, force=True)
        assert r["api_key"] != data["api_key"]
        assert "***" in r["api_key"]


if __name__ == "__main__":
    # v1 tests
    test_is_sensitive_key()
    print("✓ test_is_sensitive_key")
    test_redact_value()
    print("✓ test_redact_value")
    test_redact_string()
    print("✓ test_redact_string")
    test_redact_dict()
    print("✓ test_redact_dict")
    test_redact_list()
    print("✓ test_redact_list")
    test_redact_headers()
    print("✓ test_redact_headers")
    test_log_filter()
    print("✓ test_log_filter")
    test_redact_preserves_structure()
    print("✓ test_redact_preserves_structure")

    # v2 new tests
    test_mask_secret()
    print("✓ test_mask_secret")
    test_github_pat()
    print("✓ test_github_pat")
    test_google_api_key()
    print("✓ test_google_api_key")
    test_slack_token()
    print("✓ test_slack_token")
    test_huggingface_token()
    print("✓ test_huggingface_token")
    test_groq_key()
    print("✓ test_groq_key")
    test_stripe_key()
    print("✓ test_stripe_key")
    test_aws_key()
    print("✓ test_aws_key")
    test_private_key_block()
    print("✓ test_private_key_block")
    test_db_connection_string()
    print("✓ test_db_connection_string")
    test_jwt_token()
    print("✓ test_jwt_token")
    test_url_query_param()
    print("✓ test_url_query_param")
    test_phone_number()
    print("✓ test_phone_number")
    test_env_assignment()
    print("✓ test_env_assignment")
    test_json_field()
    print("✓ test_json_field")
    test_code_file_mode()
    print("✓ test_code_file_mode")
    test_force_mode()
    print("✓ test_force_mode")
    test_switch_toggle()
    print("✓ test_switch_toggle")

    print("\n✅ 所有测试通过！")
