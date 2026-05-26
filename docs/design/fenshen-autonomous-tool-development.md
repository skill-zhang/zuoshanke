# 分身自主工具开发 — 验证报告

> 2026-05-26 实测验证

## 一、背景

坐山客现有工具库 44 个，通过分析发现缺少 10 个关键工具。采用**分身自主开发**模式：
创建场景（分身）→ 注入详细 user_context（含 mission + 技术方案 + 约束）→ 通过 SSE stream 派发任务 → 分身自主调工具编码 → git 提交。

## 二、两轮成果

### 第一轮：3 个分身，3 个工具

| 分身 | 工具 | 文件 | 行数 | 提交 |
|------|------|------|------|------|
| 🔍 Thinking Map 读取器 | `thinking_map_read(scene_id)` | `tools/thinking_map_read_tool.py` | 173 | `9005733` |
| 🧩 分身管理器 | `list_scenes(category?, status?)` | `tools/scene_tool.py` | 125 | `bc62982`（被兜底） |
| 💧 知识沉淀器 | `precipitate(content, tags?, source?)` | `tools/precipitate_tool.py` | 143 | `bc62982` |

### 第二轮：3 个分身，6 个工具

| 分身 | 工具 | 文件 | 行数 | 提交 |
|------|------|------|------|------|
| 🗄️ db_query | `db_query(sql, params?, limit?)` | `tools/db_query.py` | 94 | `5f3acb9` |
| 🐳 容器管理 | `container_list` `container_logs` `container_restart` | `tools/container_tools.py` | 145 | `fb36e91` |
| 📡 RSS监控 | `rss_fetch` `rss_summarize` | `tools/rss_fetch.py` + `rss_summarize.py` | 169+125 | `5f3acb9` |

### 顺手修复

| 问题 | 文件 | 修复 |
|------|------|------|
| agent_loop API 120s 超时硬编码 | `agent_core/agent_loop.py:277` | `timeout=None` |
| scene_stream UNIQUE 约束崩溃 | `router/scene_stream.py:36-59` | 三态 session 复活策略 |
| gateway_config 导入 `GATEWAY_ENV_FILE` 丢失 | `router/gateway_config.py:12` | 改为 `GATEWAY_ENV_FILE_NEW` |

## 三、工具注册统计

```
变更前: 44 个
变更后: 55 个 (+11)
git 提交: 5 条新记录
```

每批次分别提交：
- `9005733` feat: 新增 thinking_map_read 工具
- `bc62982` feat: 新增 precipitate 知识沉淀工具
- `fb36e91` feat(tools): 新增 container_list/container_logs/container_restart
- `5f3acb9` feat: add db_query tool + rss_fetch + rss_summarize

## 四、实测验证

### 4.1 db_query — 直接调工具层验证

```python
db_query("SELECT count(*) as cnt FROM scenes") → {"rows": [{"cnt": 25}]}
db_query("SELECT count(*) as cnt FROM messages") → {"rows": [{"cnt": 132}]}
db_query("DELETE FROM scenes")  → {"success": False}  # 写保护拒绝
```

### 4.2 分身全链路测试

三个场景分别接收用户消息 → Agent Loop 自主调用工具 → 返回格式化结果：

- **db_query 场景**：分身自动跑了 2 次 db_query（查表列表 + 查行数），返回 Markdown 表格
- **容器管理场景**：分身调 container_list，查得 8 个容器（0 运行中），自动区分 Exited vs Dead
- **RSS 监控场景**：分身调 rss_fetch 抓取 Hacker News（墙内成功！），自动生成热度排名+亮点点评，甚至自动收敛出了优先级队列

### 4.3 容器工具

```bash
container_list() → 8 containers (0 running, 8 stopped)
# searxng → Exited (7 days ago)
# livekit-dev → Exited (2 weeks ago)
# dify-api/web/sandbox/weaviate/squid → Dead
```

### 4.4 RSS 工具

```python
rss_fetch("https://hnrss.org/frontpage?count=10")
# 返回 10 条 HN 首页新闻，含标题/链接/描述/评分
# 支持 RSS 2.0 + Atom 1.0 双格式
```

## 五、关键经验

### 5.1 分身编码稳定，但依赖 prompt 质量

- **成功因子**：user_context 必须包含具体技术方案 + 参考实现 + 约束条件（约 400-800 字）
- **失败模式**：只给一句话「写个工具」→ 分身不知道该参考什么模式
- **超时保护**：agent_loop.py 的 timeout=120 已改为 None；派发时 curl 不用 --max-time

### 5.2 已知问题

1. **precipitate 只是笔记工具**，没实现完整的「三步仪式」（memory + 设计文档 + skill），需要后续加强
2. **分身风格不统一**：db_query 用纯 sqlite3 直连 + 返回 json.dumps；rss_fetch 返回 dict 不走 json.dumps；container_tools 又用了 json.dumps。需要工具开发 SOP
3. **scene_stream 死灰复燃**：两套 session 入口不同步的问题反复出现，最终修复方案已落地

### 5.3 剩余缺口

第一梯队（本体元工具）：
- 记忆池监控工具
- Avatar 状态工具
- Mermaid 图表生成
- Markdown 预览

## 六、附录

### 6.1 场景列表（25 个）

```
scene-5aaadc47  🗄️ db_query 工具
scene-0be00c7c  🐳 容器管理工具
scene-52c8d085  📡 RSS监控工具
scene-f417ff04  🔍 Thinking Map 读取工具
scene-3e108521  🧩 分身管理工具
scene-0000601c  💧 知识沉淀工具
...
```

### 6.2 涉及文件清单

| 文件 | 操作 |
|------|------|
| `tools/db_query.py` | 新建 |
| `tools/container_tools.py` | 新建 |
| `tools/rss_fetch.py` | 新建 |
| `tools/rss_summarize.py` | 新建 |
| `tools/thinking_map_read_tool.py` | 新建 |
| `tools/scene_tool.py` | 新建 |
| `tools/precipitate_tool.py` | 新建 |
| `tools/registry.json` | 修改 (+11 条目) |
| `backend/agent_core/agent_loop.py` | 修改 (timeout) |
| `backend/router/scene_stream.py` | 修改 (session 复活) |
| `backend/router/gateway_config.py` | 修改 (import 修复) |
