"""坐山客 — URL / 端口 / 网络配置

所有 URL、端口、API 端点、CORS 来源 集中在此。
"""
import os

# ── Qwen 本地推理 ──
QWEN_API = os.environ.get(
    "QWEN_API_URL",
    "http://localhost:8083/v1/chat/completions",
)

# ── DeepSeek 云 API ──
DEEPSEEK_BASE_URL = os.environ.get(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com",
)

# ── 后端自身 ──
BACKEND_BASE_URL = os.environ.get("ZUOSHANKE_BACKEND_URL", "http://localhost:8000")

# ── CORS 允许来源 ──
CORS_ORIGINS = [
    os.environ.get("CORS_ORIGIN", "http://localhost:5173"),
    "http://127.0.0.1:5173",
]

# ── 天气 API ──
WTTR_URL = os.environ.get("WTTR_URL", "https://wttr.in")
