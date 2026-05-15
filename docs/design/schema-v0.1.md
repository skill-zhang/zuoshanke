# Thinking Map & Action Map — 数据结构 Schema v0.1

---

## 一、Thinking Map（思维导图）

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
    "n-register": {
      "id": "n-register",
      "type": "leaf",
      "label": "注册登录",
      "status": "confirmed",
      "actionable": false,
      "context_ref": "msg-008"
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
| `status` | enum | `editing`（可编辑）/ `readonly`（Action 运行中）/ `archived` |
| `version` | int | 每次编辑 +1，为版本管理预留 |
| `nodes` | map<id, node> | 扁平化节点表（不嵌套），通过 children 数组关联 |
| `cross_refs` | array | 跨分支引用（表达网状关系） |

### 节点字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 节点唯一标识 |
| `type` | enum | `root` / `domain` / `leaf` |
| `label` | string | 节点显示文本 |
| `status` | enum | `confirmed`(✓) / `discussing`(❓) / `unknown`(❌) / `mixed`(子节点混合) |
| `children` | [string] | 子节点 ID 数组 |
| `actionable` | bool | 仅 leaf 节点有，是否可触发 Action Map |
| `context_ref` | string | 产生此节点的对话消息 ID（权重衰减用） |
| `discussion` | [string] | 待讨论的子问题列表 |
| `linked_action_map` | string | 关联的 Action Map ID |
| `action_status` | enum | 关联 Action 的执行状态快照 |

### 设计理由

1. **节点用 map 不用嵌套数组** — 方便 O(1) 查找节点、局部更新不重传整棵树
2. **children 用 ID 数组** — 表达树结构，但渲染时可按任意顺序排列
3. **cross_refs 独立** — 不污染树结构，专门表达"影响""依赖"等跨分支关系
4. **context_ref 挂节点上** — 修改节点时就知道该降权哪段对话
5. **action_status 是快照** — 避免每次查 Action Map 状态，但非权威（实际状态以 Action Map 为准）

---

## 二、Action Map（行动图）

### 核心原则
- 有向图，START → 执行/决策/里程碑 → END(s)
- 每条边可标注条件
- 执行节点有状态 + 结果
- 关联回 Thinking Map 叶子节点
- 用户只读，可暂停/停止

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
      "result": "DB-per-tenant / Schema-per-tenant / RLS 三种可选",
      "context_ref": "msg-020",
      "started_at": "2026-05-15T10:01:00Z",
      "completed_at": "2026-05-15T10:05:00Z"
    },
    "a-decision-1": {
      "id": "a-decision-1",
      "type": "decision",
      "label": "客户数据量级？",
      "status": "pending"
    },
    "a-do-rls": {
      "id": "a-do-rls",
      "type": "exec",
      "label": "采用 RLS 方案实现",
      "status": "pending"
    },
    "a-milestone": {
      "id": "a-milestone",
      "type": "milestone",
      "label": "租户隔离验证",
      "status": "pending"
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
    {
      "id": "e-1",
      "from": "a-start",
      "to": "a-research",
      "type": "flow"
    },
    {
      "id": "e-2",
      "from": "a-research",
      "to": "a-decision-1",
      "type": "flow"
    },
    {
      "id": "e-3",
      "from": "a-decision-1",
      "to": "a-do-rls",
      "type": "decision",
      "condition": "小规模: < 100 租户"
    },
    {
      "id": "e-7",
      "from": "a-decision-1",
      "to": "a-end-fail",
      "type": "flow",
      "condition": "验证未通过"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 图的唯一标识 |
| `think_map_id` | string | 关联的 Thinking Map ID |
| `think_node_id` | string | 关联的 Thinking Map 可执行叶子节点 ID |
| `status` | enum | `pending` / `running` / `paused` / `stopped` / `completed` |
| `version` | int | AI 重规划时 +1 |
| `nodes` | map<id, node> | 扁平化节点表 |
| `edges` | array | 有向边列表 |

### 节点类型与特有字段

| type | 含义 | 特有字段 |
|------|------|---------|
| `start` | 起点 | 无 |
| `end` | 终点 | `outcome`: `success` / `rethink` / `cancelled`；`feedback_to_think`（回流给 Thinking Map 的消息） |
| `exec` | 执行节点 | `result`, `started_at`, `completed_at` |
| `decision` | 决策节点 | 无（条件标在边上） |
| `milestone` | 里程碑 | 无（验收点，通过则继续） |

### 节点状态机（exec 节点）

```
pending  →  running  →  completed
                     →  failed  →  (AI 重规划)
```

### 图状态机

```
pending  →  running  →  completed
                    →  paused  →  running（恢复）
                              →  stopped（放弃，修改 Thinking Map）
                    →  stopped（直接终止）
```

---

## 三、两张图的关联

```
Thinking Map                     Action Map
───────────────────────────      ─────────────────────
n-multi-tenant                   action-001
  .actionable = true  ────────→   .think_node_id = "n-multi-tenant"
  .linked_action_map = "action-001"
  .action_status = "running" ←── .status = "running"（快照同步）

Action Map 回流:
  end 节点 .feedback_to_think ──→ Thinking Map 对应节点的 discussion 字段追加
                                  Thinking Map 对应节点 status 变为 "discussing"
```

### 状态锁联动

| Action Map 状态 | Thinking Map 状态 | 用户可编辑 Thinking Map？ |
|----------------|-------------------|-------------------------|
| `pending` | `editing` | ✅ 可 |
| `running` | `readonly` | ❌ 不可（除非先暂停/停止） |
| `paused` | `readonly` | ❌ 不可（但可以讨论下一步） |
| `stopped` | `editing` | ✅ 可 |
| `completed` | `editing` | ✅ 可 |

---

## 四、为后续预留的字段（本次不实现）

| 预留 | 用途 |
|------|------|
| `version_history` | 版本管理 — 存储每次编辑的完整快照 |
| `schedule` | 周期性执行（cron-like） |
| `permissions` | 企业版多人协作权限 |
| `workspace_id` | 企业版工作空间隔离 |
