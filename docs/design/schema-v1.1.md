# Schema v1.1 — Session Management & Token Accounting

> **里程碑说明：** Schema v1.1 补完坐山客的 session 管理体系——覆盖 Web 前端与外部平台网关的统一会话管理，包括 session 生命周期、活跃追踪、超时销毁、token 用量核算。
>
> 设计日期：2026-05-21
> 核心贡献者：张清泉（需求设计）、坐山客（架构设计）
>
> 关联设计：docs/design/schema-v1.0.md (Context 组合架构)
> 参考实现：Hermes Agent session token tracking

---

## 目录

1. [问题陈述](#1-问题陈述)
2. [Session 核心概念](#2-session-核心概念)
3. [Session 生命周期](#3-session-生命周期)
4. [Server 启动清理](#4-server-启动清理)
5. [记忆提取兜底策略](#5-记忆提取兜底策略)
6. [Token 用量核算](#6-token-用量核算)
7. [数据模型变更](#7-数据模型变更)
8. [与 Schema v1.0 的关系](#8-与-schema-v10-的关系)
9. [迁移步骤](#9-迁移步骤)

---

## 1. 问题陈述

### 1.1 当前缺失

| 缺失项 | 后果 |
|--------|------|
| 无统一的 session 管理 | Web 前端和外部平台各自为政 |
| 无超时销毁机制 | 用户关电脑走了，session 永远挂在那 |
| 无 token 核算 | 不知道每场对话花了多少钱 |
| 提取兜底与 session 脱钩 | idle_extractor 只能猜，实际条件不清楚 |

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| 统一管理 Web + Gateway 的 session | 一个模型，两种入口 |
| 每个上下文有且最多一个活跃 session | 闲聊/频道/场景各自独立 |
| 3 小时无新消息自动超时销毁 | 可配置，不硬编码 |
| Server 重启时清理残留 session | 启动时异步扫描 |
| 记忆提取兜底与 session 状态挂钩 | 用户的[闲聊][频道][场景]及Gateway中有不活跃 session + 其有未提取的聊天记录 → 触发记忆提取 |

---

## 2. Session 核心概念

### 2.1 Session 绑定上下文

Session 不是绑定在"用户"上的，而是绑定在**上下文**上的。不管是 Web 前端还是 Gateway，共用同一模型：

| 入口 | 上下文 | 标识 | 说明 |
|------|--------|------|------|
| Web 前端 | 闲聊 | `context_type="channel", context_id=闲聊频道ID` | 本体之家 |
| Web 前端 | 频道 | `context_type="channel", context_id=具体频道ID` | 频道分身 |
| Web 前端 | 场景 | `context_type="scene", context_id=具体场景ID` | 场景分身 |
| Gateway | 频道/场景 | `platform="weixin/telegram/...", platform_user_id=用户ID, mode=channel/scene` | 外部平台消息，当前在哪个上下文由 mode 决定 |

**Web 前端：** 用户点击 sidebar 菜单（闲聊/频道/场景）时触发 session 的激活或创建。

**Gateway：** 外部平台消息到达网关时触发 session 的查找或创建。Gateway session 的 `mode` 和 `channel_id`/`scene_id` 记录当前所处上下文。

### 2.2 核心规则

| 规则 | 说明 |
|------|------|
| 一个上下文最多一个活跃 session | 闲聊 = 1 个，频道A = 1 个，场景B = 1 个。Web 和 Gateway 共享同一套上下文标识 |
| 切换上下文不销毁旧 session | 从场景A切到场景B，A的session仍在，3小时后才超时 |
| Gateway session 随模式切换 | 网关中从频道切到场景时，`mode` 变化但 session 复用（同一平台同一用户） |
| session 不因页面关闭而立即销毁 | 只是停止了 last_active_at 刷新，等 3 小时超时 |
| 超时时间可配置 | 默认 3 小时，存在配置中不硬编码 |

---

## 3. Session 生命周期

### 3.1 两态模型

```
[点击sidebar菜单]
       │
       ▼
检查该上下文（闲聊/频道/场景）是否有 status=active 的 session
       │
       ├── 有 → 复用（刷新 last_active_at）
       │
       └── 无 → 创建新 session，status=active
       
对话进行中，每发一条消息更新 last_active_at

超过 3 小时无新消息 → status = destroyed（超时销毁）
```

### 3.2 创建

| 触发 | 操作 |
|------|------|
| 用户点击 sidebar | 查该上下文的 session，无则创建，有则复用 |
| 外部平台消息 | 查 GatewaySession，无则创建，有则复用 |

创建时写入 `started_at`，初始化 token 计数器。

### 3.3 活跃更新

每次用户交互更新 `last_active_at`：

| 交互类型 | 更新时机 |
|---------|---------|
| 发送消息 | 点击发送 / 回车 |
| LLM 回复完成 | SSE 流结束 |
| 外部平台消息 | 网关收到消息时 |

### 3.4 超时销毁

超过 3 小时无任何新消息 → session 标记为 `destroyed`：

```python
# 定时检查逻辑
stale_sessions = db.query(Session).filter(
    Session.status == "active",
    Session.last_active_at < now - timedelta(hours=SESSION_TIMEOUT_HOURS),
).all()
for s in stale_sessions:
    s.status = "destroyed"
    s.ended_at = now
    s.duration_seconds = int((now - s.started_at).total_seconds())
db.commit()
```

超时会话的聊天记录仍然保留，只是不再属于活跃 session。

### 3.5 多种销毁路径

| 路径 | 说明 | 是否准确 |
|------|------|---------|
| 自然超时 | 3小时无新消息 | ✅ 后端定时扫到 |
| 用户关浏览器 | last_active_at 停在关闭时 | ✅ 等超时触发 |
| 用户关电脑 | 同上 | ✅ 等超时触发 |
| 后端停止服务 | session 未及时销毁 | ✅ 见第 4 节启动清理 |

---

## 4. Server 启动清理

### 4.1 启动时异步扫描

Zuoshanke 服务启动后，立即启动一个异步线程，按优先级扫描所有 status=active 的 session，判断是否已失效：

```
扫描顺序优先级：
  1. 闲聊频道
  2. 所有场景
  3. 所有频道（非闲聊）
```

### 4.2 判断逻辑

```python
for ctx_type in ["channel(闲聊)", "scene", "channel(非闲聊)"]:
    active_sessions = db.query(Session).filter(
        Session.context_type == ctx_type,
        Session.status == "active",
    ).all()
    
    for s in active_sessions:
        # 取该上下文最后一条消息的时间
        last_msg = db.query(func.max(Message.created_at)).filter(
            Message.scene_id == s.scene_id  # 按上下文过滤
        ).scalar()
        
        if last_msg and (now - last_msg > timedelta(hours=SESSION_TIMEOUT_HOURS)):
            s.status = "destroyed"
            s.ended_at = now
```

如果启动时发现某个 session 的最后一条消息距现在已超过 3 小时，直接标记为 destroyed。

---

## 5. 记忆提取兜底策略

### 5.1 定位

这是 Memory Extraction Layer（v1.0 4.8）的兜底安全网，覆盖前端触发丢失的情况。

**与 session 状态挂钩：** 如果某上下文已经没有活跃 session，还有未提取的聊天记录，才触发提取。

### 5.2 定时任务

```python
SCAN_INTERVAL_SECONDS = 60  # 每1分钟扫一次
```

每次扫描：

```
1. 找所有 status=destroyed 的 session（包括超时销毁和启动清理的）
2. 对每个销毁的 session，查其关联上下文是否有 memory_extracted=false 的消息
3. 有 → 执行提取 → 打标
4. 无 → 跳过
```

### 5.3 与页面关闭触发的关系

| 触发方式 | 时机 | 定位 |
|---------|------|------|
| visibilitychange | 页面关闭时 | 主链路 |
| 5分钟定时扫描 | 每5分钟 | 兜底 |

主链路先跑，兜底覆盖丢失场景。兜底只处理已经没有活跃 session 的上下文——如果用户还在聊，session 是 active 的，兜底不会碰。

---

## 6. Token 用量核算

### 6.1 核算维度

每 session 累计：

| 字段 | 类型 | 说明 |
|------|------|------|
| `prompt_tokens` | int | 输入 token（不含缓存命中） |
| `completion_tokens` | int | 输出 token |
| `total_tokens` | int | prompt + completion |
| `input_tokens` | int | 输入 token（含缓存命中） |
| `output_tokens` | int | 同 completion |
| `cache_read_tokens` | int | 缓存读取命中量 |
| `cache_write_tokens` | int | 缓存写入量 |
| `reasoning_tokens` | int | reasoning/thinking token |
| `api_calls` | int | LLM 调用次数 |
| `estimated_cost_usd` | float | 预估成本 |
| `cost_status` | string | free / estimated / precise |
| `cost_source` | string | 计价依据 |

### 6.2 累加时机

每次 LLM 回复后，解析 API 返回的 `usage` 字段：

```python
session.prompt_tokens += response.usage.prompt_tokens
session.completion_tokens += response.usage.completion_tokens
session.total_tokens += response.usage.total_tokens
session.api_calls += 1
session.estimated_cost_usd += calc_cost(model, response.usage)
```

### 6.3 成本计算

按 provider+model 映射单价：

```python
PRICING_TABLE = {
    "deepseek:deepseek-v4-flash": {
        "input": 0.15,      # $/M tokens
        "output": 0.60,
        "cache_read": 0.075,
    },
    "local:qwen3.5-q4": {
        "free": True,       # 本地不计费
    },
}
```

---

## 7. 数据模型变更

### 7.1 GatewaySession 扩展

```python
class GatewaySession(Base):
    __tablename__ = "gateway_sessions"

    # 原有字段
    id = Column(String, primary_key=True)
    platform = Column(String, nullable=False)       # weixin | telegram | web
    platform_user_id = Column(String, nullable=False)
    mode = Column(String, default="channel")         # channel | scene
    channel_id = Column(String, ForeignKey("channels.id"), nullable=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=True)
    scene_name = Column(String, nullable=True)
    platform_username = Column(String, nullable=True)
    last_active_at = Column(DateTime, default=utcnow) # 最后活跃时间（原有，v1.1 Web 也需更新）

    # 🆕 v1.1 新增
    status = Column(String, default="active")        # active | destroyed
    started_at = Column(DateTime, default=utcnow)     # session 创建时间
    ended_at = Column(DateTime, nullable=True)        # session 销毁时间
    duration_seconds = Column(Integer, nullable=True) # ended_at - started_at

    # 🆕 v1.1 token 用量
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)
    cache_write_tokens = Column(Integer, default=0)
    reasoning_tokens = Column(Integer, default=0)
    api_calls = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    cost_status = Column(String, default="unknown")
    cost_source = Column(String, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

**说明：** `last_active_at` 字段已有，但之前只在 gateway 路由中更新。v1.1 要求 **Web 前端也更新此字段**。

Web session (`platform="web"`) 的查找通过 `(mode, channel_id/scene_id)` 定位，`platform_user_id` 固定为 `"default"`（单用户系统）。

### 7.2 配置项

超时时间放在配置中，不硬编码：

```python
# config/constants.py 或 settings 表
SESSION_TIMEOUT_HOURS = 3          # session 超时时间（小时）
EXTRACTION_SCAN_INTERVAL = 60       # 提取兜底扫描间隔（秒）
```

### 7.3 DB 迁移

```sql
ALTER TABLE gateway_sessions ADD COLUMN status VARCHAR(20) DEFAULT 'active';
ALTER TABLE gateway_sessions ADD COLUMN started_at TIMESTAMP;
ALTER TABLE gateway_sessions ADD COLUMN ended_at TIMESTAMP;
ALTER TABLE gateway_sessions ADD COLUMN duration_seconds INTEGER;
-- token 字段
ALTER TABLE gateway_sessions ADD COLUMN prompt_tokens INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN completion_tokens INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN total_tokens INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN input_tokens INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN output_tokens INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN cache_read_tokens INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN cache_write_tokens INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN reasoning_tokens INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN api_calls INTEGER DEFAULT 0;
ALTER TABLE gateway_sessions ADD COLUMN estimated_cost_usd REAL DEFAULT 0.0;
ALTER TABLE gateway_sessions ADD COLUMN cost_status VARCHAR(20) DEFAULT 'unknown';
ALTER TABLE gateway_sessions ADD COLUMN cost_source VARCHAR(50);
```

---

## 8. 与 Schema v1.0 的关系

### 8.1 Memory Extraction Layer（v1.0 4.8）

提取兜底策略的触发条件从「消息时间 > 20 分」改为 **「该上下文无活跃 session + 有未提取消息」**：

```python
# 旧：猜用户没在打字了就提
messages_older_than_20min → extract

# 新：session 已经死了才提
no_active_session AND has_unextracted_messages → extract
```

### 8.2 History Layer（v1.0 4.6）

> 保留当前 session 会话有效期内的全部聊天内容，不做截断处理

session 活跃期内，消息全部保留。session 销毁后，消息仍在 DB 中，但不再视为"活跃上下文的一部分"。

历史消息可通过消息管理界面按 session 查看。

---

## 9. 迁移步骤

| 步骤 | 操作 | 影响 |
|------|------|------|
| 1 | ALTER TABLE GatewaySession 加列 | SQLite 安全，默认值填充 |
| 2 | models.py GatewaySession 加字段 | 已有数据兼容 |
| 3 | 后端启动时异步清理线程 | 新模块，不阻塞启动 |
| 4 | sidebar 点击 → session 创建/复用逻辑 | 前后端协作 |
| 5 | Web 前端发消息 → 更新 last_active_at | 后端统一写 |
| 6 | LLM 调用后累加 token 用量 | 新增累加逻辑 |
| 7 | 提取兜底改为 session 状态判断 | 替换旧 idle_extractor 逻辑 |
| 8 | 管理端 session/用量展示 | 新 UI 组件 |

---

## 改动记录

| 日期 | 改动 |
|------|------|
| 2026-05-21 | 初版 — 张清泉一次性说明完整设计 |
