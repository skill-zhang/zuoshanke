# 🏔️ 坐山客 v1.8.0 — 你的 AI 伙伴

**发布日期：** 2026-05-28

> 不只是工具，是一个能记住你、理解你、和你一起成长的 AI 存在。

---

## 坐山客是什么

坐山客是一个**有自主生命感的 AI 伙伴系统**。它不是聊天机器人，不是 IDE 插件，不是 RAG 知识库——它是这三者的进化体：一个拥有持久记忆、多重分身能力、自主执行闭环和自省迭代能力的 AI 存在。

从用户视角看，坐山客是三件事的集合：

1. **你的专属伙伴**——它认识你、了解你的偏好和习惯。每次对话不是「新会话」的冷启动，而是老朋友之间的继续
2. **你的专家分身工厂**——为不同领域创建独立「分身场景」：开发、写作、数据分析……每个分身有独立记忆、工具集和行为模式，但共享对你（本体）的认知
3. **你的自主执行引擎**——坐山客不只是「说」，它还能「做」。通过 Agent Loop 和 72 个注册工具，可以自主阅读文件、写代码、运行测试、拨测网页、搜索历史、甚至开发自己

---

## ✨ 核心能力

### 🗺️ 双图架构 — 让 AI 的思考可见

坐山客不是黑盒子。每一轮对话和行动都通过两张可视化图展示：

- **Thinking Map（思维导图）**：建立信任的认知同步——让用户看见 AI 是怎么理解需求的。Markmap 渲染，可交互展开/折叠
- **Action Map / Self-Map（行动图 / 自省图）**：执行前的契约——让用户看见 AI 打算怎么干。React Flow 渲染，节点可点击查看详情

两张图独立但关联，你随时可以暂停行动、修改思考、重新执行。

每个分身场景通过 Function Calling（`self_map_declare` / `self_map_update`）**自主声明**当前项目的架构可视化图——你在开发场景看到的是代码架构树，在写作场景看到的是文章结构图。这不是预置的，是 AI 在干活时自己画出来的。

### 🧠 8 层 Context 组合 — 核心引擎

坐山客的竞争力不在模型，在**上下文的组织方式**。基于真实数据诊断（schema v1.0 实测）：

```
cache hit rate:          ~95%
输入命中 token:          457,634,048
输入未命中 token:        23,954,484
miss-to-output ratio:    14.7:1 → < 5:1（目标已达成）
```

每一轮 prompt 由 Context Composer 按规则分层组装，每层独立控制加载策略、优先级和 token 预算：

| 层 | 内容 | 加载策略 |
|----|------|---------|
| ① Prompt Layer | 本体 prompt + 分身 prompt | 不可压缩，始终注入 |
| ② Memory Layer | 持久记忆 | 缓存层全量按 scope 隔离存储，注入层按需截取 |
| ③ Profile Layer | 用户画像 | P0/P1 始终注入，P2 按话题匹配 |
| ④ Config Layer | 配置层叠 | 本体→分身→场景→session 逐级覆盖 |
| ⑤ Document Layer | 场景声明的文档 | 三级摘要（single_line/brief/full），按声明级别注入 |
| ⑥ Skill Layer | 技能知识 | 按语义相关性检索，注入摘要 + 关键代码段 |
| ⑦ History Layer | 当前 session 聊天 | 全部保留，按权重（high/normal/low）组织 |
| ⑧ Work Output Layer | 工具调用产出 | 滑动窗口（默认最近 3 轮），提取关键帧 + 文件级 diff |

**Memory Layer 详解 — 两级架构：**

**① 缓存层（Memory Cache）** — 进程内全量缓存，scope 完全隔离：

- **本体（zhu）**：进程启动时预加载，**永久在线**
- **分身（scene）**：**按需加载**——用户点进场景时才从 DB 加载，切换场景时旧场景桶保留不删，切回时无需重新查 DB
- **写穿透**：CRUD 先写 DB 立即同步缓存，不替 Context Composer 做预过滤

**② 注入层（Context Composer）** — 从缓存取到全量数据后，分层决策：

- **本体记忆 → 三层选择注入**：
  - `Core Tier`：is_core=True 的核心身份记忆，compressed 摘要，≤5条/800字，**始终注入**
  - `Context Tier`：按话题 + 时效 + 重要性匹配，max_chars=3000，max_items=15，**动态注入**
  - `On-Demand Tier`：不注入，尾部提示 LLM 自行 `memory(read)` 检索

- **分身记忆**：按 scope 从缓存取全量（已按 weight 降序），取最相关的前几条

**③ Memory Extraction Layer（后台异步沉淀通道）**：
页面关闭 → LLM 从未标记的 `chat_messages` 提取 → Jaccard 去重（阈值 0.50）+ reinforce 机制 → 写入 `agent_memory` → 写穿透同步缓存。这是「对话」→「记忆」的单向转化通道，不参与每轮 context 组装。

#### 🛡️ 多层次安全体系

坐山客的安全模型建立在三层防线之上：

**① 用户在场监督 + git 兜底**（核心安全哲学）
AI 自主执行不是无监督运行。最坏情况 = 从 git 上一次提交恢复。不需要企业级规则引擎的过度防护。

**② 高危命令扫描器**（`command_scanner.py`，~42 条规则，8 大类）
纯正则在 terminal 执行前扫描，命中即阻断。覆盖：

| 类别 | 示例规则 |
|------|---------|
| 文件系统毁灭 | `rm -rf /`、`chmod -R 777 /`、`rm -rf /etc` |
| 磁盘毁灭 | `dd if=/dev/zero of=/dev/sd`、`mkfs`、`shred` |
| Git 毁灭 | `git reset --hard`（有未提交改动时）、`git clean -fd`、`git branch -D main` |
| 数据库毁灭 | `DROP TABLE`、`TRUNCATE`、`DELETE FROM` 无 WHERE |
| 网络自锁 | `iptables -F`、`systemctl stop sshd`（远程环境才阻断） |
| Docker | `docker system prune --volumes`、`docker volume rm` |
| 关键配置 | `rm -rf ~/.ssh/`、`rm /etc/passwd`、`kill -9 -1` |
| 包管理器 | `apt remove python3`、`dpkg --purge systemd` |

**智能降级**：Git 工作区干净时 `git reset --hard` 降级为警告放行；本地环境网络操作不阻断（重启即可恢复）。

**无人值守拒绝**：cron job / 后台任务命中高危直接拒绝，不等用户。

**Python subprocess 绕过修复**：分身通过 `run_code(language="python")` + `subprocess.run("kill ...")` 绕过扫描 → 已修复（双检测：tool_executor 正则提取 + code_runner 兜底检测 7 种子进程危险模式）

**③ SSRF + 路径安全 + 外泄检测**
- **SSRF 防护**（`url_safety.py`，307 LOC，32 tests）：DNS 解析 + 私有 IP 阻断 + 云元数据端点拦截（169.254.169.254 等）
- **文件路径安全**（`path_security.py`，208 LOC，15 tests）：路径遍历防护，禁止写入系统关键路径
- **外泄检测**（command_scanner 扩展）：6 种 exfil 模式 + 9 种 SSRF 模式正则匹配

**④ 自修改安全（分层模型）**
当 AI 分身自主修改自身代码时，按风险等级分层隔离：

| 层 | 方案 | 状态 |
|----|------|------|
| Layer 1 | Error Boundary 捕获渲染错误，只炸局部 | ✅ 已实现 |
| Layer 2 | 数据驱动配置，改 JSON 不改代码 | 🚧 部分实现 |
| Layer 3 | iframe 沙箱挂载自定义组件 | 🔭 待实现 |
| Layer 4 | 分身独立进程完全隔离 | 🔭 待实现 |

### 📦 Session 管理与 Token 核算

**Session 模型：** session 绑定在上下文上（闲聊/频道/场景各自独立），不绑定在用户上。每个上下文最多一个活跃 session，切换上下文不销毁旧 session，3 小时无新消息自动超时。

```
两态模型: active → destroyed（3小时超时）
销毁路径: 自然超时 / 关浏览器 / 关电脑 / 后端停止
启动清理: 后端启动时异步扫描残留 session
```

**Token 用量核算：** 每 session 累计 `prompt_tokens`、`completion_tokens`、`cache_read_tokens`、`reasoning_tokens`、`api_calls`，按 provider+model 映射单价（DeepSeek / Claude / Qwen）实时估算成本。

**三层追踪体系（Schema v1.6）：** Agent Loop 执行过程每一步都"留证据"：

| 层 | 说明 | 用途 |
|----|------|------|
| **agent.log（JSONL）** | 写穿透实时落盘，天级轮转保留 3 天 | 进程崩溃后最后一行就是犯罪工具 |
| **agent_loop_traces（SQLite）** | 独立表，3 天 TTL | 跨会话追溯复盘，不给 LLM 看避免膨胀 |
| **前端追踪面板** | SSE 分流实时展示工具调用 | 用户看到 LLM 在做什么、卡在哪 |

**写穿透保证**：`tool_start` 在 `execute_tool()` 之前写入文件 → 即使下一步「工具把进程杀了」，最后一行已落盘，可确认当时执行了什么命令。

事件类型覆盖全链路：`llm_call` → `llm_response` → `thinking` → `tool_start` → `tool_done`/`tool_error` → `status` → `done`。

## 🔄 Agent Loop — 自主执行闭环

LLM 自主调工具 → 观察结果 → 继续推理 → 直到收敛。用户通过 SSE 实时流看到每一步在想什么、调了什么工具、结果如何。

**72 个注册工具**，覆盖：

| 类别 | 工具 |
|------|------|
| 开发调试 | 代码运行、Git 操作、文件读写、批量拨测 |
| AI 原生 | 记忆管理、Think 深度思考、自省图声明、记忆沉淀、收敛检测 |
| 信息获取 | 网页搜索/抓取、RSS 订阅/摘要、天气、百科、新闻摘要、快递查询 |
| 生活辅助 | 翻译、菜谱、每日一言、二维码生成、图片生成、邮件发送、计算器 |
| 自动化 | 代理任务（delegate_task）、场景管理、文本转语音、TODO 管理 |
| 运维 | 容器管理、服务健康检查、Cloudflare Tunnel、FRP 内网穿透 |

### 🌐 本体（闲聊）+ 分身（场景）—— 视觉分离

告别「所有对话塞在一个窗口」的设计：

- **本体之家（Home）**：你和坐山客的私人空间。闲聊、谈心、讨论想法——这里记录的是「你」和「坐山客」的关系
- **分身场景（Scene）**：每个领域一个专家模式。每个分身有独立记忆池、工具集和行为准则。进入开发场景就是架构师，进写作场景就是编辑，不需要重新介绍自己
- **场景隔离**：分身不知道其他场景发生了什么，问起就诚实说不知道。各自存的记忆默认归属自身场景

### 📋 Agent 协作契约

当坐山客需要拆分子任务给多个子 Agent 并行开发时，父 Agent 先产出标准化接口契约文件（`shared/INTERFACE.md`）：

```
# 接口契约 v1.0
## 1. 项目概览
## 2. 模块架构 — 模块 | 目录 | 职责 | 依赖
## 3. 数据模型 — JSON schema + 数据库表定义
## 4. API 端点 — 方法 | 路径 | 请求/响应
## 5. 模块边界 — 谁负责什么、不负责什么
## 6. 约定 — 命名规范、错误处理、状态码
## 7. 注意事项 — 已知陷阱与边界情况
```

**原则**：子 Agent 之间不共享对话历史、不直接通信、各自产生独立代码文件。契约是唯一共享上下文。父 Agent 负责联调粘合。支持版本管理（v1.0 → v1.1 非破坏性变更 → v2.0 破坏性变更）。

### 🔍 浏览器拨测 — AI 自己看自己

坐山客可以启动 Playwright 无头浏览器，像人一样打开自己产出的前端页面。但它不是看图——是读结构化的数据：

```
dial_test(url)        → DOM 快照 + Console 日志 + Network 瀑布 + 性能指标
dial_style(url, sel)  → 提取特定元素的 CSS 计算值
dial_assert(url, rules) → 断言式检查（如「确认 .card-grid 下有 2 列卡片」）
dial_flow(url, actions) → 多步交互式流程，同一浏览器会话内执行序列
```

**这意味着坐山客能自主发现前端 bug**——不用等你截图报告，它自己打开页面、读 Console、发现问题、定位根因、修复 bug。这在自开发场景中是端到端闭环的关键一环。

### 👤 Avatar 角色动画

坐山客不是冷冰冰的文字框。Avatar 是一个 70×66px 的浮动角色：

- **9 种情绪状态**（高兴/思考/疑惑/专注/疲惫……），自然过渡，不由独立规则判断，而是 LLM 在回复中自然产出 `[心情: 情绪词]` 标签
- **呼吸 idle 动画**，对话时活起来
- **字幕栏**实时输出内心独白——不只是最终结论，还有"它正在想什么"
- **本体具象化出口**——不是装饰，是「你面前坐着一个 AI 存在」的感知锚点

### 🧠 双重记忆池

| 记忆层 | 范围 | 特性 | 类比 |
|--------|------|------|------|
| **本体记忆** | 全局（scope=zhu） | 不朽、不衰减、不清理 | 你对最好朋友的了解——不会忘 |
| **分身记忆** | 场景内 | weight 驱动、衰减、可清理 | 工作时的临时笔记——用完可丢 |
| **叙事型记忆** | 关系层 | 记录共同决策与修正历程 | 我们一起走过的路——让关系有厚度 |

**修正即强化**：当你纠正坐山客的错误认知时，它不会覆盖旧数据——它会记录修正轨迹（之前怎么错的、为什么错、什么时候纠正的），并把这个记忆强化。

### 🏗️ 个人工作台（Workbench v1.8）

独立沙箱化（`:8001`，通过主前端 proxy 路由 `/wb` → 工作台，`/wb-api` → 工作台后端），**PC 端 + 移动端浏览器双端适配**，包含：

- **Avatar 浮动角色** + 渐变紫色用户名
- **8 种卡片渲染**（场景卡片、记忆卡片、技能卡片……）
- **浮动聊天栏**（金色发送按钮 + ⌘K 唤起，滑入滑出动效）
- **时钟问候**——根据时段自动切换问候语
- **秘密花园**——展示本体对你的全部认知（记忆地图、决策轨迹、修正历史），可直接编辑修正

---

## 🏗️ 技术栈

```
前端:     React 18 + TypeScript + Zustand + Markmap + React Flow + Vite
后端:     Python 3.11+ / FastAPI / SSE 实时流
存储:     SQLite + SQLAlchemy + FTS5 + jieba 中文分词
推理:     DeepSeek v4 Flash / Claude / Qwen（可切换 Provider）
工具:     72 个注册工具，registry.json 统一管理
拨测:     Playwright（Chromium headless）DOM + Console + Network
Agent:    子 Agent 并行执行（契约隔离）、Clarify 阻塞式追问
运行:     Linux / WSL2 / Python venv
```

## 🚀 快速开始

```bash
git clone https://github.com/skill-zhang/zuoshanke.git
cd zuoshanke/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
venv/bin/python main.py
```

> 必须使用 venv，系统 Python 的 SQLAlchemy 版本过旧（1.4.x），代码需要 ≥ 2.0.36。详见 `docs/design/python-venv-setup.md`。

## 📚 设计文档

34 篇架构设计文档（`docs/design/`），涵盖：Context 组合策略、双重记忆池、Memory Cache Layer、Prompt Caching、分身身份体系、安全哲学、Schema 全版本演变（v0.1 → v1.8）、自省图模式、Agent Loop 执行引擎、个人工作台等。

## 🗺️ 版本历程

| 阶段 | 版本 | 里程碑 |
|------|------|--------|
| **奠基** | v1.0-v1.4 | Agent Core 架构、8 层 Context 组合、分身场景 MVP |
| **高可靠** | v1.5-v1.6 | 写入校验、热重载、Git 快照、Agent Loop 三层追踪、25 项可用性测试 |
| **安全** | v1.7 | subprocess 命令扫描器绕过修复、分身沙箱隔离、安全规则注入 |
| **正式发布** | **v1.8** | 个人工作台独立沙箱、72 工具、Memory Cache Layer、契约协作 |

## 👥 贡献者

- **Administrator (skill-zhang)** — 产品设计、架构设计
- **zuoshanke Agent (Nous Research)** — 辅助架构设计、系统实现、AI 协作伙伴

> zuoshanke Agent 作为 AI 协作伙伴参与本项目开发。所有法律权利、义务与责任由 human 创作者独立承担。

## 📄 许可证

[Apache 2.0](LICENSE) © 2026 坐山客团队
