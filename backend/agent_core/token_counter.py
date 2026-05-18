"""Token 计数器 — 估算 LLM 上下文的 Token 用量

设计原则：
- 不需要精确到个位数，误差在 10-20% 以内即可用于显示和预警
- 支持中英文混合文本
- 系统 prompt + 记忆 + 工具定义 + 对话历史的综合估算

已知模型的 Context 上限（预设值，可从 routing 配置覆盖）:
  qwen3.5-9b:           32,768  (32K)
  deepseek-chat:       1,048,576 (1M)
  deepseek-v4-pro:     1,048,576 (1M)
"""
from typing import Optional


# ── 中英文 token 估算因子 ──
# 中文一个字符 ≈ 1.5-2 token
# 英文 4 个字符 ≈ 1 token
# 标点/空格/换行 ≈ 0.5 token
from config.constants import TOKEN_CHINESE_RATE as CHINESE_RATE, TOKEN_ASCII_RATE as ASCII_RATE, TOKEN_PER_MESSAGE_OVERHEAD as PER_MESSAGE_OVERHEAD


def estimate_tokens(text: str) -> int:
    """估算一段文本的 token 数

    对中英文混合文本做粗略估算：
      tokens ≈ 中文数 × 2 + 英文数 × 0.3
    """
    if not text:
        return 0
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
    ascii_count = sum(1 for c in text if c.isascii() and c not in ('\n', '\r', '\t'))
    other = len(text) - chinese - ascii_count  # 换行、空格等
    return int(chinese * CHINESE_RATE + ascii_count * ASCII_RATE + other * 0.5)


def estimate_message_tokens(role: str, content: str) -> int:
    """估算一条消息的 token 数（含 role 开销）"""
    return estimate_tokens(content) + PER_MESSAGE_OVERHEAD


def estimate_messages_tokens(messages: list[dict]) -> int:
    """估算多条消息的总 token 数

    Args:
        messages: [{"role": "...", "content": "..."}, ...]
    Returns:
        总 token 数
    """
    total = 0
    for m in messages:
        total += estimate_message_tokens(m.get("role", ""), m.get("content", ""))
    return total


def context_usage_str(total: int, max_context: int) -> str:
    """格式化为可读的 Token 用量字符串

    Returns:
        "2.3K / 32K (7%)"
    """
    def fmt(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1000:
            return f"{n / 1000:.1f}K"
        return str(n)

    pct = round(total / max_context * 100, 1) if max_context > 0 else 0
    return f"{fmt(total)} / {fmt(max_context)} ({pct}%)"


def progress_bar(percentage: float, width: int = 20) -> str:
    """生成进度条字符串

    Args:
        percentage: 0-100 的百分比值
        width: 进度条总字符数

    Returns:
        "████████░░░░░░ 40%"
    """
    filled = int(percentage / 100 * width)
    filled = max(0, min(filled, width))
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"{bar} {percentage:.0f}%"


def get_context_length_from_route(route_cfg: Optional[dict]) -> int:
    """从路由配置获取模型的 context_length

    Args:
        route_cfg: routing 配置字典，应包含 model 和可选的 context_length

    Returns:
        context_length 值（有配置就用配置值，否则用预设值）
    """
    if not route_cfg:
        return 32768  # 默认 32K

    # 如果配置里显式设置了 context_length，直接返回
    explicit = route_cfg.get("context_length")
    if explicit and isinstance(explicit, (int, float)):
        return int(explicit)

    # 否则根据 model 名称查预设表
    model = (route_cfg.get("model", "") or "").lower()
    return MODEL_PRESET_CONTEXT_LENGTH.get(model, 32768)


# ── 已知模型预设 context_length ──
MODEL_PRESET_CONTEXT_LENGTH = {
    "qwen3.5-9b": 32768,
    "qwen3.5-9b-cuda": 32768,
    "deepseek-chat": 1048576,
    "deepseek-v4-flash": 1048576,
    "deepseek-v4-pro": 1048576,
}
