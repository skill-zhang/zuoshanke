"""测试秘密遮盖系统"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from secret_redact import (
    redact,
    SecretRedactFilter,
    redact_headers,
    _is_sensitive_key,
    _redact_value,
    _redact_string,
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


if __name__ == "__main__":
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
    print("\n✅ 所有测试通过！")
