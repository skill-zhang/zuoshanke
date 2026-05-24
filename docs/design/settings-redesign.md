# 系统设置重设计 v2 — Provider + 模型 + 路由三层架构

_设计日期: 2026-05-24 | 状态: 原型定稿(v2) | 原型: prototypes/prototype-settings.html(抽屉版) / prototypes/prototype-settings-v2.html(全屏版·最终定稿)_

## 1. 问题陈述

当前系统设置存在以下问题：

| 问题 | 现状 | 后果 |
|------|------|------|
| 模型/Provider 硬编码 | `models.py:DEFAULT_ROUTING` 写死 5 路由的 model+provider | 用户无法在页面上切换模型 |
| API Key 不可配 | `DEEPSEEK_API_KEY` 通过 `.env` 环境变量加载 | 改 Key 需登录服务器重启后端 |
| 仅支持 DeepSeek+Local | `ai_engine.py` 只有 `if provider=="deepseek"/"local"` 两个分支 | 无法扩展 OpenAI/Anthropic 等 |
| 参数跟路由不跟模型 | Temperature/MaxTokens 绑定在路由配置上 | 切换模型时不知道当前值是"模型默认"还是"用户覆盖" |
| 能力开关全局 | `features.vision_enabled` / `pdf_as_image` 在 Setting 表里 | 跟具体模型能力脱钩，开/关无意义 |
| 缺乏 Provider 管理 | 无 Provider 概念，Base URL/API Key 散落在 env/config | 无法在 UI 上增删改 |

## 2. 设计原则

1. **Provider 和路由解耦** — Provider 只管"谁能用"（凭据），路由只管"谁在哪用"（选择）
2. **参数跟模型走** — 每个模型声明自己的默认 Temperature/MaxTokens/ContextLength，路由可选覆盖
3. **能力是模型属性** — Vision/FunctionCalling 是模型自带能力声明，路由可选关闭
4. **OpenAI 兼容协议优先** — 大多数云 API（DeepSeek/OpenAI/本地 llama.cpp）都用同一套 OpenAI-compatible 协议，最大复用
5. **向后兼容** — 首次启动从环境变量自动创建默认 Provider，DB migration 不破坏已有数据

## 3. 数据模型

### 3.1 Provider

```typescript
interface Provider {
  id: string;            // 唯一标识
  name: string;          // 显示名，如 "DeepSeek"、"OpenAI"、"本地 Qwen"
  provider_type: string; // "openai_compatible"（目前仅此一种，后续可扩展 "anthropic"）
  base_url: string;      // API 端点，如 "https://api.deepseek.com"、"http://localhost:8083/v1"
  api_key: string;       // 存 DB（前端展示时 mask）
  icon: string;          // 显示图标，如 "☁"、"🟢"、"💻"
  is_active: boolean;    // 是否启用
  created_at: string;
  updated_at: string;
}
```

### 3.2 Model（Provider 的子对象，JSON 字段）

```typescript
interface ProviderModel {
  name: string;                     // 模型名，如 "deepseek-v4-flash"
  context_length: number;           // 上下文长度
  default_temperature: number;      // 默认温度 0.7
  default_max_tokens: number;       // 默认最大 Token
  default_repeat_penalty: number;   // 默认重复惩罚 1.05
  supports_vision: boolean;         // 是否支持视觉
  supports_function_calling: boolean; // 是否支持 Function Calling
  supports_streaming: boolean;      // 是否支持流式输出
}
```

### 3.3 RouteConfig（设置表的路由配置更新）

```typescript
interface RouteConfig {
  provider_id: string | null;   // 引用的 Provider，null=未配置
  model: string | null;         // 模型名（取自 Provider 的 model list）
  temperature: number | null;   // null=使用模型默认值
  max_tokens: number | null;
  repeat_penalty: number | null;
  // 能力覆盖（null=跟随模型，true/false=强制开关）
  overrides?: {
    vision?: boolean;
    function_calling?: boolean;
    streaming?: boolean;
  };
}
```

### 3.4 关系图

```
Provider（1）
  ├── base_url ───── 决定请求发到哪
  ├── api_key ────── 决定用什么凭据
  └── models[N] ──── 模型列表（JSON）
       ├── name ──── 模型标识
       ├── default_params
       └── capabilities

Route（5 个固定路由）
  ├── provider_id ── 引用哪个 Provider
  ├── model ──────── 用该 Provider 的哪个模型
  └── params ─────── 可选覆盖（null=用模型默认）
  └── overrides ──── 可选能力覆盖
```

## 4. UI 结构（4 Tab 抽屉）

`prototypes/prototype-settings.html` 呈现了完整 UI 原型。

### Tab 1: ☁ Provider 管理

```
┌──────────────────────────────────────────┐
│ ☁ DeepSeek                            ✏️🔗│
│   Base: https://api.deepseek.com          │
│   Key: sk-***********************T3Bl  更换│
│   ✓ 已验证                                │
│   模型:                                   │
│   ┌ deepseek-v4-flash · 1M · 0.7T | 🖼🔧┐│
│   └ deepseek-v4-pro     · 1M · 0.5T | 🖼🔧┘│
├──────────────────────────────────────────┤
│ 🟢 OpenAI                              ✏️🔗│
│   ...                                     │
├──────────────────────────────────────────┤
│ 💻 本地 Qwen                            ✏️🔗│
│   ...                                     │
├──────────────────────────────────────────┤
│      [+ 添加 Provider]                    │
└──────────────────────────────────────────┘
```

每个 Provider 卡片可折叠/展开。支持：新增、编辑、删除、验证 API Key。

### Tab 2: 🔀 路由配置

```
┌────┬────────┬────────┬────────┬────┬──────┬──┬────┐
│    │ 路由   │Provider│ 模型   │温度│Token │惩罚│能力│
├────┼────────┼────────┼────────┼────┼──────┼──┼────┤
│ ▶  │频道闲聊│DeepSeek│v4-flash│0.70│ 8192 │1.05│🖼🔧│
│ │  │        │        │        │默认│ 默认 │默认│    │
│ ▼  │        │ ⚡ 能力覆盖（可选）             │    │
│ │  │        │ ☑ 🖼 Vision  ☑ 🔧 FC  ☐ 📤流式│    │
├────┼────────┼────────┼────────┼────┼──────┼──┼────┤
│ ▶  │场景分析│DeepSeek│v4-flash│0.30│16384 │1.05│🖼🔧│
│ │  │        │        │        │蓝框│ 蓝框 │默认│    │
└────┴────────┴────────┴────────┴────┴──────┴──┴────┘
```

关键交互：
- **Provider 下拉**变化 → **模型下拉**的选项随之切换
- **模型下拉**变化 → 三个参数输入框自动填入该模型的默认值，`默认 X.X` 提示更新
- 输入框值 ≠ 默认值 → 蓝色边框
- 输入框值超出安全范围 → 红色边框
- 每行可展开「能力覆盖」，默认跟随模型能力，可手动关闭

### Tab 3: 📝 系统人设

保持原有功能不变：频道/场景两段人设编辑。

### Tab 4: 💻 服务状态

显示本地服务状态 + 秘密花园入口。**特性开关已移除**，能力归模型。

## 5. 后端架构变更

### 5.1 新增表 `providers`

```sql
CREATE TABLE providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider_type TEXT NOT NULL DEFAULT 'openai_compatible',
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '☁',
    models TEXT NOT NULL DEFAULT '[]',  -- JSON: ProviderModel[]
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 5.2 变更 `settings.routing` 存储结构

```
旧: { "provider": "deepseek", "model": "deepseek-v4-flash", "temperature": 0.7, ... }
新: { "provider_id": "<uuid>", "model": "deepseek-v4-flash", 
      "temperature": null, "max_tokens": null, "repeat_penalty": null,
      "overrides": { "vision": null, "function_calling": null, "streaming": null } }
```

### 5.3 新增 API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/providers` | 列出所有 Provider |
| POST | `/api/providers` | 新增 Provider |
| GET | `/api/providers/{id}` | 获取单个 Provider |
| PUT | `/api/providers/{id}` | 更新 Provider |
| DELETE | `/api/providers/{id}` | 删除 Provider |
| POST | `/api/providers/{id}/verify` | 验证 API Key 连通性 |
| GET | `/api/providers/{id}/models` | 获取 Provider 的模型列表（含默认参数） |

### 5.4 变更 `ai_engine.py` 调用逻辑

```
当前: get_settings("scene")
       → route_cfg["provider"] → if provider=="deepseek" | if provider=="local"

改后: get_settings("scene")
       → route_cfg["provider_id"] → db.query(Provider).get(provider_id)
       → 从 Provider 拿 base_url + api_key + model 的实际模型名
       → 统一 OpenAI-compatible HTTP 调用
```

核心变化：**不再有 provider 硬编码分支**。所有 OpenAI-compatible 的 Provider 共享同一段请求代码，仅 URL/Key/Model 参数不同。

### 5.5 影响的文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/models.py` | 新增 | `Provider` ORM 模型 |
| `backend/schemas.py` | 新增+修改 | `ProviderSchema`, `RouteConfig` 更新 |
| `backend/router/providers.py` | 新增 | Provider CRUD 路由 |
| `backend/router/settings.py` | 修改 | `PATCH /api/settings` 接收新 schema |
| `backend/router/__init__.py` | 修改 | 注册 providers_router |
| `backend/ai_engine.py` | 重构 | 移除 provider 硬编码分支，改为泛化调用 |
| `backend/agent_core/agent_loop.py` | 修改 | `call_llm_with_tools` 从 provider_id 解析 |
| `backend/agent_core/memory_extractor.py` | 修改 | 同样使用泛化调用 |
| `backend/main.py` | 修改 | 启动时从环境变量创建默认 Provider |
| `frontend/src/api/client.ts` | 修改 | 新增 Provider API 类型+函数，更新 Settings 类型 |
| `frontend/src/stores/appStore.ts` | 修改 | 新增 providers state + actions |
| `frontend/src/components/SettingsDrawer.tsx` | 重写 | 4 Tab 布局 |

## 6. 启动迁移策略

首次启动/DB 为空时，`main.py` 自动创建默认 Provider：

```python
def seed_default_providers(db: Session):
    """从环境变量自动创建默认 Provider"""
    existing = db.query(Provider).count()
    if existing > 0:
        return  # 已有配置，不覆盖

    # DeepSeek
    deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    deepseek = Provider(
        id="provider-deepseek",
        name="DeepSeek",
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        api_key=deepseek_api_key,
        icon="☁",
        models=json.dumps([
            {"name": "deepseek-v4-flash", "context_length": 1048576,
             "default_temperature": 0.7, "default_max_tokens": 8192,
             "default_repeat_penalty": 1.05,
             "supports_vision": True, "supports_function_calling": True, "supports_streaming": True},
            {"name": "deepseek-v4-pro", "context_length": 1048576,
             "default_temperature": 0.5, "default_max_tokens": 8192,
             "default_repeat_penalty": 1.05,
             "supports_vision": True, "supports_function_calling": True, "supports_streaming": True},
        ])
    )
    db.add(deepseek)

    # Local Qwen
    local = Provider(
        id="provider-local",
        name="本地 Qwen",
        base_url=os.environ.get("QWEN_API_URL", "http://localhost:8083/v1"),
        api_key="",
        icon="💻",
        models=json.dumps([
            {"name": "Qwen3.5-9B", "context_length": 32768,
             "default_temperature": 0.7, "default_max_tokens": 4096,
             "default_repeat_penalty": 1.05,
             "supports_vision": True, "supports_function_calling": True, "supports_streaming": True},
        ])
    )
    db.add(local)
    db.commit()

    # 更新路由配置指向新 provider
    s = db.query(Setting).filter(Setting.id == SETTINGS_ID).first()
    if s:
        for key, cfg in s.routing.items():
            # 旧: provider="deepseek" → 新: provider_id="provider-deepseek"
            old_provider = cfg.get("provider", "")
            if old_provider == "deepseek":
                cfg["provider_id"] = deepseek.id
            else:
                cfg["provider_id"] = local.id
            cfg.pop("provider", None)
            # 清空参数（用模型默认）
            cfg["temperature"] = None
            cfg["max_tokens"] = None
            cfg["repeat_penalty"] = None
            cfg["overrides"] = {"vision": None, "function_calling": None, "streaming": None}
        s.routing = s.routing
        db.commit()
```

## 7. Provider API Key 安全

- API Key 在 DB 中明文存储（当前 MVP 阶段，无加密基础设施）
- 前端展示时 mask 处理（`sk-************...` 只显示后 4 位）
- 编辑时只能替换整 key，不可读取已有 key
- 后续可加 AES-256 加密存储（`cryptography` 库）

## 8. 未覆盖的设计决策

- **Anthropic 协议支持**：目前只做 OpenAI-compatible，Anthropic 的 `/v1/messages` API 格式不同，后续视需求加
- **自动模型发现**：有些 Provider（如 OpenAI）有 `/v1/models` 端点，未来可自动发现并填充模型列表
- **模型参数高级覆盖**：如 `top_p`、`frequency_penalty`、`stop` 序列等，第一阶段不做
- **Provider 分组/标签**：当前只是平铺列表

## 9. 实现顺序建议

1. **阶段 1 — 后端 Provider CRUD**：新表 + API + 迁移逻辑（最小可工作）
2. **阶段 2 — 后端调用重构**：`ai_engine.py` 泛化，删除硬编码分支
3. **阶段 3 — 前端 Provider 管理 Tab**：Provider 列表 + 新增/编辑
4. **阶段 4 — 前端路由配置 Tab**：Provider+Model 下拉联动 + 参数默认值 + 展开行能力覆盖
5. **阶段 5 — 收尾**：人设/服务状态 Tab 适配新抽屉布局

---

**参考原型**：`prototypes/prototype-settings.html`  
**参考文档**：`references/model-routing.md`（当前路由架构说明）
