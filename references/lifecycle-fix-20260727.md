# Thinking Map / Action Map 生命周期修复（Lifecycle Fix）

**日期**: 2026-07-27
**现象**: 用户在测试中发现，无论写出多少产出，Thinking Map 永远显示「发散进行中」、Action Map 永远显示「第一步」
**根因**: 三个缺失叠加——工具说明缺生命周期指引、prompt 缺推进指令、后端缺兜底提醒

---

## 修复的三个层面

### 层面1：Tool Description 生命周期指引

| 工具 | 原有问题 | 修复 |
|------|---------|------|
| `diverge` | 只说「创建节点」，没说这不会推进进度 | 加 ⚠️「发散只创建节点，只有 converge() 能标记完成」 |
| `converge` | 只说「合并整理」，没说它是唯一的完成标记 | 加「只有调 converge() 才能标记已完成」，加 HTML 完成验证后调用 |
| `self_map_declare` | 只说「声明架构图」 | 加 ⚠️「不调 self_map_update 则永远显示第一步」 |
| `self_map_update` | 只说「增删节点」 | 加 ⚠️「每完成一步用 update_node 推进进度」，附完整示例 |

**文件**: `tools/registry.json`（4 个 entry 的 description 字段）

### 层面2：Prompt 引导

`context_composer.py:_build_prompt_layer()` 在「收敛能力说明」段后新增 **「🗺️ 自省图（Action Map）进度推进」** 章节：

- 核心规则：每完成一步 → `self_map_update` 标记 completed / in_progress / blocked
- 检查清单：每次调完有产出的工具后问自己：
  1. Action Map 是否存在？→ 更新当前步骤
  2. Thinking Map 本轮发够了吗？→ 够了调 converge()

**文件**: `backend/agent_core/context_composer.py:300-315`

### 层面3：后端轻量兜底

`scene_stream.py` 新增 `_self_map_nudge()` 函数，在每轮 Agent Loop 完成后自动检测：

```
本轮有 write_file/patch/run_code（产出类工具）?
  → 同时有 self_map_update/decleare/converge? → 跳过
  → 查 DB 中 SceneSelfMap / ThinkingMap 是否存在?
    → 存在且未推进 → yield sse_event("thought", ...)
    → LLM 下一轮能看到这个提醒
```

**函数签名**: `_self_map_nudge(db, scene_id, tool_results) -> str | None`

**函数位置**: `backend/router/scene_stream.py:389`
**调用位置**: `backend/router/scene_stream.py:735-746`（generate() 内，tool_cards 之后、done 事件之前）

---

## Code Review 中发现的 3 个问题

| 问题 | 初始版本 | 修复 |
|------|---------|------|
| nudge 只 print 到后端日志 | `print(f"[nudge] {msg}")`，LLM 永远看不到 | 改为返回 str，在 generate() 中 yield thought SSE 事件 |
| 双花括号 `{{'id':'xxx'}}` | 非 f-string 中的 `{{` 是字面量，LLM 看到非法语法 | 改成单 `{'id':'xxx'}` |
| 无用 `scene` 参数 | 函数接受 `scene` 但从未使用 | 移除 |

---

## 配套：Meta Prophet 工具

同 session 还创建了 `tools/prophet_tool.py` + `skills/prophet-forecast/SKILL.md`，提供 Prophet 时间序列预测配置生成器（14 个参数，返回完整 JSON 配置方案）。

**注册**: `tools/registry.json`（category: system, verified: true）
**图标**: `frontend/src/components/ToolsView.tsx`（ICON_MAP: '📈'）

---

## 相关文件清单

| 文件 | 改动类型 |
|------|---------|
| `tools/registry.json` | 4 个 description 修改 + 1 个新 entry |
| `tools/prophet_tool.py` | 新建 |
| `frontend/src/components/ToolsView.tsx` | ICON_MAP 新增 |
| `skills/prophet-forecast/SKILL.md` | 新建 |
| `backend/agent_core/context_composer.py` | prompt 新增「自省图进度推进」章节 |
| `backend/router/scene_stream.py` | 新增 `_self_map_nudge()` + 调用点 |
