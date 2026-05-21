# Schema v1.0 Context Composer 实现参考

## 核心文件

| 文件 | 作用 |
|------|------|
| `backend/agent_core/context_composer.py` | 7 层组合器：compose_context() + 各层构建函数 |
| `backend/agent_core/diff_extractor.py` | diff 提取 + 引导文本格式化 |
| `backend/agent_core/snapshot_manager.py` | 文件快照管理（DB + FS 双模式） |
| `backend/agent_core/priority_assigner.py` | `[P:high/normal/low]` 标记解析 |
| `backend/agent_core/document_summarizer.py` | 三级文档摘要（single_line/brief/full） |
| `backend/agent_core/config_injector.py` | 配置层叠注入 |
| `backend/agent_core/context_builder.py` | `build_agent_context_v1()` 入口 |
| `backend/tests/test_schema_v1.py` | 25 单元测试 |
| `backend/tests/test_scenario_v1.py` | 5 场景测试 |
| `backend/tests/test_converge_engine.py` | 26 converge 测试 |
| `docs/design/schema-v1.0.md` | 完整设计文档 |

## 7 层组装顺序

1. prompt_layer — 本体 prompt + 分身 prompt + 工具列表 + 使用说明 + 记忆能力 + 优先级指引 + 收敛说明 + TM 状态
2. memory_layer — 按场景 scope 检索持久记忆（最多 5 条）
3. config_layer — 当前生效的配置层叠（model/scene 参数）
4. document_layer — 从 scene_config.document_deps 读取的文档摘要
5. skill_layer — 按相关性检索的 skill 摘要（最多 2 条）
6. history_layer — 全部聊天带权重优先级（high → normal → low 合并）
7. work_output_layer — 最近 N 轮文件 diff 关键帧（从 file_snapshots 表读取）

## 接线点

场景消息入口：`scenes.py:1483` → `build_agent_context_v1()` → `compose_context()`

## 数据库变更

- `messages` 表新增 `priority` 列（high/normal/low）
- 新表：`file_snapshots`, `document_summaries`, `config_entries`
- `scenes` 表新增 `scene_config` JSON 字段

## 测试

`cd backend && .venv/bin/python -m unittest discover tests -v`
预期：56/56 pass
