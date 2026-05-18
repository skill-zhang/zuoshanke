"""坐山客 — 数字常量配置

通用数字常量、超时、阈值、权重等集中在此。
各模块特定的常量（如天气缓存TTL）仍可留在原文件，但建议逐步迁入。
"""

# ── 天气服务 ──
WEATHER_CACHE_TTL = 60      # 天气缓存过期时间（秒）
WEATHER_TIMEOUT = 10        # 天气 API 超时（秒）

# ── 记忆系统权重 & 阈值 ──
MEMORY_DEFAULT_BASE_WEIGHT = 2     # 新建记忆默认权重
MEMORY_DECAY_HALF_LIFE = 14        # 半衰期（天）
MEMORY_MAX_INJECT_COUNT = 5        # 每次最多注入条数
MEMORY_REINFORCE_BOOST = 2.0       # 用户反复提及倍率
MEMORY_EXPLICIT_BOOST = 3.0        # "记住这个" 倍率

# ── Token 计数估算 ──
TOKEN_CHINESE_RATE = 2.0           # 每个中文字符约 2 tokens
TOKEN_ASCII_RATE = 0.3             # 每个 ASCII 字符约 0.3 tokens
TOKEN_PER_MESSAGE_OVERHEAD = 4     # 每条消息的 role/元数据开销

# ── 网关／长轮询 ──
GATEWAY_LONG_POLL_TIMEOUT_MS = 35_000
GATEWAY_API_TIMEOUT_MS = 15_000
GATEWAY_MAX_CONSECUTIVE_FAILURES = 3
GATEWAY_RETRY_DELAY_SECONDS = 2
GATEWAY_BACKOFF_DELAY_SECONDS = 30

# ── 频道／场景 ──
SCENE_SESSION_TIMEOUT_MINUTES = 5  # 场景模式下无消息自动回到频道

# ── Agent Loop ──
AGENT_LOOP_MAX_STEPS = 25          # 单次 Agent Loop 最大步数
