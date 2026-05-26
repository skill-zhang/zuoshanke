# Hermes Agent vs 坐山客 — 系统对比（2026-05-26）

> 基于双方真实代码阅读，禁止脑补。

## 宏观

| | Hermes Agent | 坐山客 |
|---|---|---|
| 本质 | 通用 CLI Agent 框架 | 自定义 AI 伙伴 Web 应用 |
| 形态 | CLI + Gateway + TUI | FastAPI + React SPA |
| 代码量 | ~60-70万行（含17K测试） | ~20万行 |
| 入口 | cli.py / run_agent.py | main.py (uvicorn) |
| 核心设计哲学 | 插件化、多 provider、企业级安全 | 思维可视化、分身/本体、记忆权重衰减 |

## 架构差异

1. **架构范式**: Hermes 插件化 (16+ plugins) vs 坐山客单体分层
2. **Provider**: Hermes 20+ adapter / 坐山客 3 种硬编码
3. **工具系统**: Hermes 自注册 (registry.py) / 坐山客 JSON 注册表 (registry.json)
4. **工具复杂度**: Hermes 工具更深（MCP 139K, browser 152K, delegate 117K）/ 坐山客偏轻量
5. **Agent Loop**: Hermes 同步循环 + budget/interrupt / 坐山客 Generator yield SSE

## 坐山客独有（Hermes 无对应）

- Thinking Map（树形思维导图 + 发散收敛）
- 双重记忆池（本体不朽 vs 分身衰减）
- 场景系统（场景/频道/广场/工坊/工作台）
- Avatar NPC（角色动画 + 9态 mood）
- 产出成果管理（ProjectOutput + output gallery）
- 预执行引擎（keyword trigger pre-execute）
- 用户画像（Profile Layer）
- MemoryCache 预热（启动全量加载）

## Hermes 独有（坐山客无对应）

- MCP 客户端（139K 实现）
- 20+ provider adapter（Anthropic/Gemini/Codex 独立 adapter 各~50-80K）
- 插件生态（memory/kanban/achievements/metrics 等）
- 企业级扫描（Tirith 26K）
- ACP 协议（VS Code/JetBrains 集成）
- 模型定价（usage_pricing.py 32K）
- Checkpoint 系统（checkpoint_manager.py 60K）
- 自动上下文压缩（context_compressor.py 72K）
- TUI Ink React 界面
- RL 训练环境（Atropos）

## 工具系统对比

| | Hermes | 坐山客 |
|---|---|---|
| 注册方式 | Python 自注册 | JSON 显式注册表 |
| MCP 支持 | ✅ 完整客户端 | ❌ |
| 工具集/分组 | ✅ toolsets.py 分层组合 | ❌ 仅有 exclude 列表 |
| 预执行 | ❌ | ✅ keyword trigger |
| 安全 | Tirith + approval + url | url_safety + path + command |

## 记忆系统对比

| | Hermes | 坐山客 |
|---|---|---|
| 存储 | 外部 provider 插件 | 本地 SQLite + MemoryCache |
| 权重 | 无（依赖 provider） | frequency × recency × boost |
| 双重池 | ❌ | ✅ 本体不朽 + 分身衰减 |
| 自动提取 | post-turn sync | 提取器 + 兜底调度器 |

## 可借鉴点（双向）

**坐山客可从 Hermes 学**:
- 插件化 provider 系统（而非硬编码）
- MCP 客户端（工具即插即用生态）
- 多平台 gateway 适配器数量（20+ vs 3）

**Hermes 可从坐山客学**:
- 思维可视化（Thinking Map）
- 双重记忆池设计
- 预执行引擎（减少 LLM 调用轮次）
- 前端 Avatar 交互
