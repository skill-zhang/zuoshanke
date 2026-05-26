# Thinking Map & Action Map — 数据结构 Schema v0.2

---

## 设计原则：边界

**是单节点执行器，不是整图执行器。**

|  能做的 | 不能做的 |
|-------------|--------------|
| 收到一个明确单一任务 | 走多个节点 |
| 调用工具执行 | 判断"下一步走哪个分支" |
| 返回：成功/失败 + 结果 | 判断"这任务做得对不对" |
| | 自主决定重规划 |

**决策权全部留在坐山客**：坐山客遍历 Action Map，每个 exec 节点 spawn 一次 Hermes。

---

## 一、Thinking Map（思维导图）

*(v0.1 不变)*

### 核心原则
- 树状结构为主体（parent-children 层级）
- 节点状态标记共识程度
- 叶子节点可标记为"可执行"，触发 Action Map
- 有全局锁定状态（Action 运行时变为 readonly）

### Schema

```json
{
  "id": "think-001",
  "title": "SaaS 产品需求梳理",
  "status": "editing",
  "version": 3,
  "created_at": "2026-05-15T09:00:00Z",
  "updated_at": "2026-05-15T10:30:00Z",
  
  "nodes": {
    "n-root": {
      "id": "n-root",
      "type": "root",
      "label": "SaaS 产品",
      "status": "confirmed",
      "context_ref": "msg-003",
      "children": ["n-user", "n-biz", "n-billing", "n-integration"]
    },
    "n-user": {
      "id": "n-user",
      "type": "domain",
      "label": "用户系统",
      "status": "mixed",
      "context_ref": "msg-005",
      "children": ["n-register", "n-permission", "n-multi-tenant"]
    },
    "n-multi-tenant": {
      "id": "n-multi-tenant",
      "type": "leaf",
      "label": "多租户方案",
      "status": "discussing",
      "actionable": true,
      "context_ref": "msg-012",
      "discussion": [
        "单租户够用吗？",
        "后期扩展成本如何？"
      ],
      "linked_action_map": "action-001",
      "action_status": "running"
    }
  },

  "cross_refs": [
    {
      "id": "xr-1",
      "from": "n-multi-tenant",
      "to": "n-billing",
      "label": "影响计费模型",
      "context_ref": "msg-015"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 图的唯一标识 |
| `title` | string | 图的名称 |
| `status` | enum | `editing` / `readonly`（Action 运行中）/ `archived` |
| `version` | int | 每次编辑 +1 |
| `nodes` | map<id, node> | 扁平化节点表，通过 children 数组关联 |
| `cross_refs` | array | 跨分支引用 |

### 节点字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 节点唯一标识 |
| `type` | enum | `root` / `domain` / `leaf` |
| `label` | string | 节点显示文本 |
| `status` | enum | `confirmed`(✓) / `discussing`(❓) / `unknown`(❌) / `mixed`(子节点混合) |
| `children` | [string] | 子节点 ID 数组 |
| `actionable` | bool | 仅 leaf 节点，是否可触发 Action Map |
| `context_ref` | string | 产生此节点的对话消息 ID（权重衰减用） |
| `discussion` | [string] | 待讨论的子问题 |
| `linked_action_map` | string | 关联的 Action Map ID |
| `action_status` | enum | 关联 Action 的执行状态快照 |

---

## 二、Action Map（行动图）v0.2 🔥

### 核心原则
- 有向图，坐山客逐节点遍历执行
- **每个 exec 节点 spawn 一次 Hermes（单一明确任务）**
- Hermes 返回后，坐山客根据结果判断下一节点
- 用户实时看到 Action Map 上每条节点的状态
- 用户只读，可暂停/停止，exec 节点可设置 requires_approval

### Action Map 执行循环

```
坐山客 遍历 Action Map:

  exec 节点:
    1. 构造单一任务 prompt
    2. spawn Hermes → 用户看到节点状态: running ⏳
    3. 等待结果（超时/重试/失败 实时可见）
    4. 写入 result_summary + artifacts
    5. 如果 requires_approval → 暂停，弹给用户
       [/approve | /approve always | /deny | 聊两句]
    6. 用户 approve → 继续下一节点

  decision 节点:
    1. 根据上游结果 + rules 自动判定分支
    2. 规则无法判定 → 升级为用户决策

  milestone 节点:
    1. 暂停，汇总已完成节点状态
    2. 问用户: 继续 / 暂停思考 / 停止改图

  end 节点:
    有 outcome: success → 标记完成
    有 outcome: rethink → 回流 Thinking Map
```

### Schema

```json
{
  "id": "action-001",
  "title": "确定多租户方案",
  "think_map_id": "think-001",
  "think_node_id": "n-multi-tenant",
  "status": "running",
  "version": 1,
  "created_at": "2026-05-15T10:00:00Z",
  "updated_at": "2026-05-15T10:15:00Z",

  "nodes": {
    "a-start": {
      "id": "a-start",
      "type": "start",
      "label": "START"
    },
    "a-research": {
      "id": "a-research",
      "type": "exec",
      "label": "调研多租户方案",
      "status": "completed",
      "requires_approval": false,
      "timeout": 300,
      "retry": 2,
      "result_summary": "DB-per-tenant / Schema-per-tenant / RLS 三种可选",
      "artifacts": ["/tmp/tenant-research.md"],
      "context_ref": "msg-020",
      "started_at": "2026-05-15T10:01:00Z",
      "completed_at": "2026-05-15T10:05:00Z",
      "retry_count": 0
    },
    "a-decision-1": {
      "id": "a-decision-1",
      "type": "decision",
      "label": "客户数据量级？",
      "status": "pending",
      "rules": [
        {
          "condition": "result_summary contains '租户数 < 100' or '小规模'",
          "target": "a-do-rls"
        },
        {
          "condition": "result_summary contains '租户数 100-1000' or '中规模'",
          "target": "a-do-schema"
        },
        {
          "condition": "result_summary contains '租户数 > 1000' or '大规模'",
          "target": "a-do-db"
        }
      ],
      "fallback": "ask_user"
    },
    "a-do-rls": {
      "id": "a-do-rls",
      "type": "exec",
      "label": "采用 RLS 方案实现",
      "status": "pending",
      "requires_approval": true,
      "timeout": 600,
      "retry": 1
    },
    "a-milestone": {
      "id": "a-milestone",
      "type": "milestone",
      "label": "租户隔离验证",
      "status": "pending",
      "auto_continue": false
    },
    "a-end-ok": {
      "id": "a-end-ok",
      "type": "end",
      "label": "租户模型确定",
      "outcome": "success"
    },
    "a-end-fail": {
      "id": "a-end-fail",
      "type": "end",
      "label": "需重新讨论",
      "outcome": "rethink",
      "feedback_to_think": {
        "node_id": "n-multi-tenant",
        "message": "RLS 方案在大于 1000 租户时性能不可接受"
      }
    }
  },

  "edges": [
    {"id": "e-1", "from": "a-start", "to": "a-research", "type": "flow"},
    {"id": "e-2", "from": "a-research", "to": "a-decision-1", "type": "flow"},
    {"id": "e-3", "from": "a-decision-1", "to": "a-do-rls", "type": "decision", "condition": "小规模: < 100 租户"},
    {"id": "e-4", "from": "a-decision-1", "to": "a-do-schema", "type": "decision", "condition": "中规模: 100-1000 租户"},
    {"id": "e-5", "from": "a-decision-1", "to": "a-do-db", "type": "decision", "condition": "大规模: > 1000 租户"},
    {"id": "e-6", "from": "a-do-rls", "to": "a-milestone", "type": "flow"},
    {"id": "e-7", "from": "a-milestone", "to": "a-end-ok", "type": "flow", "condition": "验证通过"},
    {"id": "e-8", "from": "a-milestone", "to": "a-end-fail", "type": "flow", "condition": "验证未通过"}
  ]
}
```

### 节点类型与特有字段

| type | 含义 | 特有字段 |
|------|------|---------|
| `start` | 起点 | 无 |
| `end` | 终点 | `outcome`: `success` / `rethink` / `cancelled`；`feedback_to_think` |
| **`exec`** 🔥 | **单次 Hermes 子进程执行** | `requires_approval`, `timeout`, `retry`, `result_summary`, `artifacts`, `started_at`, `completed_at`, `retry_count` |
| **`decision`** 🔥 | **坐山客程序化判定分支** | `rules` (condition → target 规则列表), `fallback` (`ask_user` / 默认分支) |
| `milestone` | 阶段验收点 | `auto_continue`: false（默认暂停等用户确认） |

### exec 节点新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `requires_approval` | bool | 执行完成后是否暂停等用户确认（默认 false） |
| `timeout` | int | 单次 Hermes 调用超时秒数 |
| `retry` | int | 失败/超时后最多重试次数 |
| `retry_count` | int | 当前已重试次数 |
| `result_summary` | string | 结构化结果摘要（给人看） |
| `artifacts` | [string] | 产出物路径列表 |

### exec 节点状态机 🔥

```
pending  →  running  →  completed   → (requires_approval? → awaiting_approval → approved)
                     →  failed      → (retry_count < retry? → retrying → running)
                     →  timeout     → (retry_count < retry? → retrying → running)
                     →  denied      →  stopped（用户拒绝）
```

### decision 节点判定规则

```json
"rules": [
  { "condition": "result_summary contains 'xxx'", "target": "node-id" },
  { "condition": "artifacts has .py file", "target": "node-id" }
],
"fallback": "ask_user"
```

- 规则按顺序匹配，第一个命中的生效
- `fallback` 决定所有规则都不命中时的行为：`ask_user` 或指定默认目标节点 ID

### 图状态机

```
pending  →  running  →  completed
                    →  paused  →  running（恢复）
                              →  stopped（放弃，修改 Thinking Map）
                    →  stopped（直接终止）
```

---

## 三、Hermes 子进程调用规范

### 调用格式

```
坐山客构造 prompt:

任务: {exec_node.label}
背景: {thinking_map_node.discussion}
上游结果: {upstream_exec_nodes.result_summary}
产出要求: {task 描述}

坐山客 spawn:
  hermes chat -q "{prompt}" --model deepseek-chat --timeout {exec_node.timeout}
```

### 返回处理

Hermes 返回文本 → 坐山客用**轻量 LLM 结构化提取**：
- `result_summary`：一句话摘要
- `artifacts`：提取文件路径列表
- `success`：判断是否成功

不需要 DeepSeek Pro，轻量模型足够。

---

## 四、两张图的关联

```
Thinking Map                     Action Map
───────────────────────────      ─────────────────────
n-multi-tenant                   action-001
  .actionable = true  ────────→   .think_node_id = "n-multi-tenant"
  .linked_action_map = "action-001"
  .action_status = "running" ←── .status = "running"（快照同步）

Action Map 回流:
  end 节点 .feedback_to_think ──→ Thinking Map 对应节点 discussion 追加
                                  status 变为 "discussing"
```

### 状态锁联动

| Action Map 状态 | Thinking Map 状态 | 用户可编辑 Thinking Map？ |
|----------------|-------------------|-------------------------|
| `pending` | `editing` | ✅ 可 |
| `running` | `readonly` | ❌ 不可 |
| `paused` | `readonly` | ❌ 不可（可讨论下一步） |
| `stopped` | `editing` | ✅ 可 |
| `completed` | `editing` | ✅ 可 |

---

## 五、为后续预留

| 预留 | 用途 |
|------|------|
| `version_history` | 版本管理 — 完整快照 |
| `schedule` | 周期性执行 |
| `permissions` | 企业版多人协作 |
