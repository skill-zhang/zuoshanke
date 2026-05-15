# Thinking Map & Action Map — 数据结构 Schema v0.3

---

## 设计原则：Hermes 的边界

**Hermes 是单节点执行器，不是整图执行器。**

| Hermes 能做的 | Hermes 不能做的 |
|-------------|--------------|
| 收到一个明确单一任务 | 走多个节点 |
| 调用工具执行 | 判断"下一步走哪个分支" |
| 返回：成功/失败 + 结果 | 判断"这任务做得对不对" |
| | 自主决定重规划 |

**决策权全部留在坐山客。**

---

## 验证责任分层 🔥

| 时机 | 谁负责 | 验证什么 |
|------|--------|---------|
| **Action Map 生成时** | LLM（prompt 约束） | 提供的 URL 必须可访问、API 端点必须已知 |
| **exec 节点执行前** | 坐山客（程序化） | URL 实际连通性 + 本地命令前置条件 |
| **exec 节点执行中** | Hermes 子进程 | 命令实际执行结果 |

### Action Map 生成时的 Prompt 约束

坐山客向 LLM 请求生成 Action Map 时，prompt 内包含：

> - 所有 URL、API 端点必须在互联网上真实存在且可公开访问
> - 涉及本地命令时，标注前置条件（需要什么工具、什么版本）
> - 不可验证的方案不要提供

### exec 节点内置验证步骤

验证是 exec 节点生命周期的内置阶段，不是独立节点。每个 exec 节点执行前，坐山客自动跑验证：

```python
# 坐山客在 spawn Hermes 之前
for check in task.verification_checks:
    if check.type == "url":
        status = curl_head(check.target)
    elif check.type == "command":
        status = shell("which {check.target}")
    elif check.type == "file":
        status = shell("test -f {check.target}")
    
    if not status.passed:
        → 不发给 Hermes
        → 触发 fallback 或重试
```

---

## 一、Thinking Map（思维导图）

*(v0.2 不变)*

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
    "n-multi-tenant": {
      "id": "n-multi-tenant",
      "type": "leaf",
      "label": "多租户方案",
      "status": "discussing",
      "actionable": true,
      "context_ref": "msg-012",
      "discussion": ["单租户够用吗？", "后期扩展成本如何？"],
      "linked_action_map": "action-001",
      "action_status": "running"
    }
  },

  "cross_refs": [
    {"id": "xr-1", "from": "n-multi-tenant", "to": "n-billing", "label": "影响计费模型", "context_ref": "msg-015"}
  ]
}
```

### 节点字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 节点唯一标识 |
| `type` | enum | `root` / `domain` / `leaf` |
| `label` | string | 节点显示文本 |
| `status` | enum | `confirmed` / `discussing` / `unknown` / `mixed` |
| `children` | [string] | 子节点 ID 数组 |
| `actionable` | bool | 仅 leaf，是否可触发 Action Map |
| `context_ref` | string | 产生此节点的对话消息 ID |
| `discussion` | [string] | 待讨论的子问题 |
| `linked_action_map` | string | 关联的 Action Map ID |
| `action_status` | enum | 关联 Action 的状态快照 |

---

## 二、Action Map（行动图）v0.3 🔥

### 核心原则
- 有向图，坐山客逐节点遍历执行
- 每个 exec 节点 spawn 一次 Hermes
- **exec 节点内置验证步骤，执行前自动校验 URL/命令/文件**
- **执行中可动态追加节点**（方案 A 失败 → 追加方案 B）
- 用户实时看到 Action Map 每条节点状态 + 动态变化
- 用户只读，可暂停/停止

### Action Map 执行循环

```
坐山客 遍历 Action Map:

  exec 节点:
    1. 提取 verification_checks
    2. 逐条验证（URL 连通性、命令存在性、文件存在性）
    3. 验证失败 → retry / 动态追加 fallback 节点 / 升级问用户
    4. 验证通过 → 构造单一任务 prompt
    5. spawn Hermes → 用户看到状态: running ⏳
    6. 等待结果（超时可见、重试可见、失败可见）
    7. 写入 result_summary + artifacts
    8. requires_approval → 弹给用户 [/approve | /approve always | /deny]
    9. 继续下一节点

  decision 节点:
    1. 根据上游结果 + rules 程序化判定分支
    2. 无法判定 → 升级为用户决策

  milestone 节点:
    1. 暂停，汇总已完成节点
    2. 问: 继续 / 暂停思考 / 停止改图

  end 节点:
    success → 标记完成
    rethink → 回流 Thinking Map
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
  "replan_count": 1,
  "dynamic_nodes": ["a-fallback-schema"],
  "created_at": "2026-05-15T10:00:00Z",
  "updated_at": "2026-05-15T10:20:00Z",

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
      "retry_count": 0,
      "verification": {
        "status": "passed",
        "checks": [
          {"type": "url", "target": "https://www.postgresql.org/docs/current/ddl-schemas.html", "result": "200", "passed": true},
          {"type": "command", "target": "pg_config", "result": "found", "passed": true}
        ]
      },
      "result_summary": "DB-per-tenant / Schema-per-tenant / RLS 三种可选",
      "artifacts": ["/tmp/tenant-research.md"],
      "context_ref": "msg-020",
      "started_at": "2026-05-15T10:01:00Z",
      "completed_at": "2026-05-15T10:05:00Z"
    },
    "a-do-rls": {
      "id": "a-do-rls",
      "type": "exec",
      "label": "采用 RLS 方案实现",
      "status": "failed_verify",
      "requires_approval": true,
      "timeout": 600,
      "retry": 1,
      "retry_count": 0,
      "verification": {
        "status": "failed",
        "checks": [
          {"type": "url", "target": "https://api.supabase.com/v1", "result": "timeout", "passed": false},
          {"type": "command", "target": "pg_config", "result": "found", "passed": true}
        ],
        "failed_count": 1
      },
      "fallback_node": "a-fallback-schema"
    },
    "a-fallback-schema": {
      "id": "a-fallback-schema",
      "type": "exec",
      "label": "采用 Schema 隔离方案（备选）",
      "status": "pending",
      "requires_approval": true,
      "timeout": 600,
      "retry": 1,
      "retry_count": 0,
      "verification": {
        "status": "pending",
        "checks": [
          {"type": "command", "target": "pg_config", "result": null, "passed": null}
        ]
      },
      "origin": "fallback_from_a-do-rls"
    },
    "a-decision-1": {
      "id": "a-decision-1",
      "type": "decision",
      "label": "客户数据量级？",
      "status": "pending",
      "rules": [
        {"condition": "result_summary contains '租户数 < 100' or '小规模'", "target": "a-do-rls"},
        {"condition": "result_summary contains '租户数 100-1000'", "target": "a-do-schema"},
        {"condition": "result_summary contains '租户数 > 1000'", "target": "a-do-db"}
      ],
      "fallback": "ask_user"
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
        "message": "RLS + Schema 方案均无法验证通过，需重新评估"
      }
    }
  },

  "edges": [
    {"id": "e-1", "from": "a-start", "to": "a-research", "type": "flow"},
    {"id": "e-2", "from": "a-research", "to": "a-decision-1", "type": "flow"},
    {"id": "e-3", "from": "a-decision-1", "to": "a-do-rls", "type": "decision", "condition": "小规模"},
    {"id": "e-4", "from": "a-decision-1", "to": "a-do-schema", "type": "decision", "condition": "中规模"},
    {"id": "e-5", "from": "a-decision-1", "to": "a-do-db", "type": "decision", "condition": "大规模"},
    {"id": "e-6", "from": "a-do-rls", "to": "a-milestone", "type": "flow"},
    {"id": "e-20", "from": "a-fallback-schema", "to": "a-milestone", "type": "fallback"},
    {"id": "e-7", "from": "a-milestone", "to": "a-end-ok", "type": "flow", "condition": "通过"},
    {"id": "e-8", "from": "a-milestone", "to": "a-end-fail", "type": "flow", "condition": "未通过"}
  ]
}
```

---

### 🔥 exec 节点完整字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 节点唯一标识 |
| `type` | string | `"exec"` |
| `label` | string | 节点显示文本 |
| `status` | enum | `pending` / `verifying` / `verified` / `failed_verify` / `running` / `completed` / `failed` / `timeout` / `retrying` / `awaiting_approval` / `approved` / `denied` |
| `requires_approval` | bool | 执行后是否暂停等用户确认 |
| `timeout` | int | 单次 Hermes 调用超时秒数 |
| `retry` | int | 最大重试次数 |
| `retry_count` | int | 当前已重试次数 |
| `verification` | object | 验证步骤与结果（见下） |
| `fallback_node` | string | 验证失败后的备选节点 ID |
| `origin` | string | 节点来源：`"original"` / `"fallback_from_{node_id}"` |
| `result_summary` | string | 结果摘要（给人看） |
| `artifacts` | [string] | 产出物路径列表 |
| `context_ref` | string | 关联对话消息 ID |
| `started_at` | string | 开始时间 |
| `completed_at` | string | 完成时间 |

### verification 字段

```json
{
  "status": "passed" | "failed" | "pending",
  "checks": [
    {
      "type": "url",
      "target": "https://api.example.com",
      "result": "200" | "404" | "timeout" | "dns_error",
      "passed": true | false
    },
    {
      "type": "command",
      "target": "pg_config",
      "result": "found" | "not_found" | "version_mismatch: need 14+",
      "passed": true | false
    },
    {
      "type": "file",
      "target": "/etc/config.yaml",
      "result": "exists" | "not_found",
      "passed": true | false
    }
  ],
  "failed_count": 1
}
```

### 🔥 exec 节点完整状态机

```
pending
  → verifying          （坐山客验证前置条件）
    → verified         （验证通过，准备 spawn Hermes）
    → failed_verify    （验证失败）
      → retrying       （还有剩余重试次数）
        → verifying
      → (exhausted)    （重试耗尽）
        → 如果 fallback_node 存在 → 切换到 fallback 节点
        → 否则 → 升级问用户 / 标记 failed

verified
  → running            （Hermes 执行中）
    → completed        （成功）
      → awaiting_approval（需要用户确认）
        → approved → 继续下一节点
        → denied → 停止
    → failed           （Hermes 返回失败）
      → retrying（有重试）→ running
      → (exhausted) → 升级
    → timeout          （超时）
      → retrying（有重试）→ running
      → (exhausted) → 升级
```

### Action Map 顶层新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `replan_count` | int | 执行过程中重规划次数。过多 → 提示用户 Thinking Map 可能有问题 |
| `dynamic_nodes` | [string] | 执行过程中动态追加的节点 ID（非原始计划） |

---

## 三、执行中的动态图变化（用户可见）

```
用户屏幕上的 Action Map 实时变化:

  时刻 T0: 原始计划
    START → 调研 → 实现RLS → 验证 → END ✅

  时刻 T1: RLS 验证失败
    START → 调研✅ → 实现RLS ❌(verify: url timeout)
                        │
                        └→ 实现Schema(备选) ⏳  ← 动态追加，橙色边框

  时刻 T2: 备选方案执行中
    origin: "fallback_from_a-do-rls"
    用户可看到: "RLS 因为 API 不可达，自动切换到 Schema 隔离方案"
```

**失败的路径不消失，留在图上。备选路径用不同颜色标记。** 这是"我们试过 A，失败了，所以用 B"的完整痕迹。

---

## 四、图的关联与回流

```
Thinking Map                     Action Map
───────────────────────────      ─────────────────────
n-multi-tenant                   action-001
  .actionable = true  ────────→   .think_node_id = "n-multi-tenant"
  .action_status = "running" ←── .status = "running"

Action Map 回流:
  end(outcome=rethink) → Thinking Map 节点 discussion 追加
  replan_count > 阈值 → Thinking Map 节点标记为 "可能需要重新讨论"
```

---

## 五、为后续预留

| 预留 | 用途 |
|------|------|
| `version_history` | 版本管理 |
| `schedule` | 周期性执行 |
| `permissions` | 企业版多人协作 |
