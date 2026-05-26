# 分身自主工具开发 — 速查

📌 `docs/design/fenshen-autonomous-tool-development.md` 完整报告

## 总览

6 个分身 | 9 个工具 + 3 个修复 | 44→55 个注册工具

## 新工具清单

| 工具 | 函数 | 文件 | 方法 |
|------|------|------|------|
| Thinking Map 读取 | `thinking_map_read(scene_id)` | `thinking_map_read_tool.py` | SQLAlchemy ORM |
| 场景列表 | `list_scenes(category?, status?)` | `scene_tool.py` | sqlite3 直连 |
| 知识沉淀 | `precipitate(content, tags?, source?)` | `precipitate_tool.py` | 写 ~/.hermes/precipitate/*.md |
| 数据库查询 | `db_query(sql, params?, limit?)` | `db_query.py` | sqlite3 直连，只读保护 |
| 容器列表/日志/重启 | 3 个函数 | `container_tools.py` | subprocess docker |
| RSS 抓取/摘要 | 2 个函数 | `rss_fetch.py` + `rss_summarize.py` | urllib + xml.etree |

## 关键修复

| 问题 | 修复 | 文件 |
|------|------|------|
| agent_loop 120s timeout | `timeout=None` | `agent_loop.py:277` |
| scene_stream UNIQUE 崩溃 | 三态复活策略 | `scene_stream.py:36-59` |
| gateway_config 导入失败 | `GATEWAY_ENV_FILE_NEW` | `gateway_config.py:12` |

## 分身编码 SOP

1. 创建场景 → PATCH user_context（含 mission + 方案 + 约束，400-800字）
2. 派发：`POST /api/scenes/{id}/stream` — 不要 `--max-time`
3. 等待完成 → 读 SSE 输出的 `done` 事件
4. 验收：读工具文件 + 调函数验证 + 检查 registry
5. 沉淀：memory + 设计文档 + skill
