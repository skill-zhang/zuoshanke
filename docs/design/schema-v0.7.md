# Schema v0.7 — Agent Loop 仪表盘：6 面板收敛可视角

> 版本: v0.7  
> 日期: 2026-05-21  
> 状态: 方案已定，待实现  
> 关联文件: `router/scenes.py`, `agent_core/agent_loop.py`, `agent_core/context_builder.py`, `models.py`, `frontend/src/components/ChatView.tsx`, `frontend/src/stores/appStore.ts`, `frontend/src/api/client.ts`, `prototypes/agent-loop-v1.1.html`

---

## 一、背景

### 现状

坐山客的场景聊天已全量走 Agent Loop（v0.6 已上线），后端引擎（`run_agent_loop()` + Dialog Engine）运行正常。但用户可见的只有：
- 聊天消息气泡（流式输出）
- 工具执行状态条（tool_status 闪一下）
- Thinking Map（藏在 Drawer 里）
- Action Map（藏在另一个 Drawer 里，列表视图）

**问题**：Agent Loop 内部的发散→收敛→排序→聚焦→反馈过程对外是黑箱。用户看不到收敛结果、看不到优先级队列、看不到当前在做什么、看不到反馈记录。

### 目标

将原型 `agent-loop-v1.1.html` 的 6 面板仪表盘落地到场景聊天界面，让用户看一眼就知道 Agent Loop 当前状态。

### 原型参考

`prototypes/agent-loop-v1.1.html` — 完整设计参考（静态 HTML，所有交互逻辑需后端数据驱动）。

---

## 二、设计原则

### 2.1 AI 原生：零手动操作

| 操作 | 谁做 | 说明 |
|------|------|------|
| 发散（Thinking Map 拆解） | 系统自动 | 第一句话后自动触发（已有 ✅） |
| 收敛（合并相似节点） | 系统自动 | LLM 分析 TM 节点，聚类去重 |
| 排序（优先级队列） | 系统自动 | LLM 定 P1-P4 + 依赖链 |
| 聚焦执行（Agent Loop） | 系统自动 | 从 PQ 取 P1 自动执行 |
| 纠正 | 用户在聊天框打字 | 唯一用户操作，走对话 |

**原则**：用户只需要聊天输入框。6 张面板全是信息视图，没有任何按钮需要用户点击来触发下一步。

### 2.2 消息分层：存但不烦

| 层级 | 位置 | 用途 | 用户可见？ |
|------|------|------|-----------|
| 实时进度 | Action Map + Reflect Timeline | 当前执行细节 | ✅ 仪表盘 |
| 工具结果备注 | TM 节点详情 | 执行结果挂载到节点 | ✅ 点击节点 |
| 子任务结论摘要 | messages 表 (role=system, display=false) | 跨会话搜索 | ❌ 不显示，仅供 session_search |
| 最终结论 | 聊天消息 (role=ai) | 用户看到的回复 | ✅ 聊天框 |

**原则**：中间步骤（工具执行、收敛合并、任务跳转）只在仪表盘显示，不往聊天框刷消息。只有「结论」「需要用户决策」「用户纠正后确认」才在聊天框出现。

---

## 三、架构概览

### 3.1 页面布局

```
┌────────────────────────────────────────────────────┐
│  ① 阶段循环图                                       │
│  [发散]→[收敛]→[排序]→[聚焦]→[反馈]  高亮当前       │
├────────────────────────────────────────────────────┤
│  ▶ ② 思维导图 · 场景名 (可折叠)                     │
│  (N 节点 · M 组合并 · K 废弃 · P 反馈新增)           │
│  ┌──────────────────────────────────────────────┐   │
│  │  CustomMindMap 树图 (全貌)                    │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────┬──────────────────────────────┤
│  ③ TM 收敛结果列表   │  ④ Priority Queue           │
│  - ✅ P1 调研标准     │  P1 🔴 调研标准 (执行中)     │
│  - ✅ P2 静态检测     │  P2 🟠 静态检测 (依赖P1)    │
│  - 💭 估价检测       │  P3 🔵 手续检测 (依赖P2)    │
├─────────────────────┼──────────────────────────────┤
│  ⑤ Action Map 聚焦   │  ⑥ Reflect Timeline         │
│  ▶ 当前执行          │  ✅ 搜索完成                 │
│  调研标准 进度60%     │  💡 发现国标9条红线          │
│  [工具标签]           │  🔀 收敛合并××+××          │
└─────────────────────┴──────────────────────────────┘
┌────────────────────────────────────────────────────┐
│  ⑦ Status Bar: 阶段 · 循环数 · 步数 | ⚡ Token 用量  │
└────────────────────────────────────────────────────┘
```

### 3.2 整体流程

```
用户第一次发消息
  ↓
① 发散 → 自动拆解 TM 节点（已有：diverge 端点）
  ↓
② 收敛 → LLM 分析 TM，合并相似/标记废弃 → 更新节点状态
  ↓
③ 排序 → LLM 定 P1-P4 + 依赖链 → 写入 PriorityQueue 表
  ↓
④ 聚焦 → Agent Loop 从 PQ 取 P1 开始执行 → 同步更新进度
  ↓
⑤ 反馈 → 工具执行结果 → Reflect Timeline + 可能的 TM 新节点
  ↑                                                    |
  └── 循环: 重新收敛+排序 → 继续执行 ← 用户可随时纠正 ──┘
```

---

## 四、数据模型

### 4.1 PriorityQueue 表（新增）

```python
class PriorityQueue(Base):
    """优先级队列"""
    __tablename__ = "priority_queues"

    id = Column(String(32), primary_key=True)
    scene_id = Column(String(32), ForeignKey("scenes.id"), nullable=False)
    node_id = Column(String(32), ForeignKey("think_nodes.id"), nullable=True)
    title = Column(String(200), nullable=False)
    priority = Column(Integer, default=2)       # 1=P1, 2=P2, 3=P3, 4=P4
    status = Column(String(20), default="pending")  # pending/running/completed/blocked
    deps = Column(Text, default="[]")           # JSON: ["node_id_1", "node_id_2"]
    wip_group = Column(Integer, default=0)      # 同一批进入执行的任务组
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
```

### 4.2 ReflectTimeline 表（新增）

```python
class ReflectTimeline(Base):
    """反馈时间线"""
    __tablename__ = "reflect_timelines"

    id = Column(String(32), primary_key=True)
    scene_id = Column(String(32), ForeignKey("scenes.id"), nullable=False)
    type = Column(String(20), nullable=False)    # success/fail/new/discover/correct/merge
    icon = Column(String(10), default="💡")
    title = Column(String(200), nullable=False)
    detail = Column(Text, default="")
    tag = Column(String(50), nullable=True)      # inject/blocked/queue_update
    tag_text = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 4.3 ThinkNode 变更（补充收敛相关字段）

```python
# ThinkNode 现有表已有 status 字段，补充收敛后的状态值：
# brainstorm — 刚发散/头脑风暴中
# active — 活跃节点
# converged_pending — 已收敛待分配优先级
# converged_queued — 已收敛已入队
# discarded — 已废弃
# feedback_new — 反馈注入新节点
#
# 新字段（可选）：
# merged_into_id = Column(String(32), nullable=True)  # 收敛合并到的目标节点ID
```

### 4.4 Message 表变更（隐藏消息支持）

```python
# Message 表新增字段：
# display = Column(Boolean, default=True)  # 是否在前端显示
#   True  — 正常聊天消息（默认）
#   False — 系统内部记录（tool_result 摘要），前端过滤不渲染
```

**⚠️ 迁移注意**：`display` 是已有 `messages` 表的新增列，SQLite 不支持 `ALTER TABLE ADD COLUMN` 以外的方式。部署时需要手动执行：
```sql
ALTER TABLE messages ADD COLUMN display BOOLEAN DEFAULT 1;
```
或通过 `database.init_db()` 后补一条 `ALTER TABLE`。用 `create_all()` 不会自动为已有表加列。

### 4.5 ThinkNode 节点创建约束

`ThinkNodeCreate` schema 中 `id` 字段是 **必填** 的（类型 `str`，无默认值）。通过 REST API 创建 TM 节点时必须提供 `id`，否则返回验证错误。建议调用方用 `make_id("n")` 生成。

---

## 五、后端实现

### 5.1 自动收敛+排序管线

**位置**：`router/scenes.py` 的 `stream_scene_message()`，在自动发散之后，Agent Loop 启动之前。

**触发**：第一次消息发散完成后（is_first_msg=true）或每次反馈注入新节点后。

```python
def auto_converge_and_prioritize(db, scene_id, think_map):
    """
    1. 读 TM 所有 brainstorm/active 节点
    2. 调 LLM 分析：哪些可合并、哪步可废弃、优先级怎么排
    3. 执行合并（更新 merged_into_id + 废弃标记）
    4. 写入 PriorityQueue（P1-P4 + 依赖链）
    5. 写入 ReflectTimeline（记录收敛合并）
    6. 返回 PQ 列表
    """
```

**LLM prompt（收敛+排序合一）**：

```
你是一个任务调度专家。分析以下思维导图节点：

{节点列表}

请：
1. 合并意思重复或高度相似的任务，合并后取最完整的名称
2. 标记不必要或可由 Agent 直接完成的任务为废弃
3. 为每个（合并后的）任务分配 P1-P4 优先级
4. 标注任务间的依赖关系

输出 JSON 格式：
{
  "merges": [
    {"source_ids": ["id1", "id2"], "target_title": "合并后标题"}
  ],
  "discarded_ids": ["id3"],
  "queue": [
    {"id": "id4", "title": "任务名", "priority": 1, "deps": []}
  ]
}
```

### 5.2 Agent Loop 同步钩子

在 `run_agent_loop()` 循环中，每完成一个工具调用，同步更新仪表盘：

| 事件 | 更新内容 |
|------|---------|
| tool_start | Action Map 显示正在使用 XX 工具 |
| tool_done | Reflect Timeline 添加 ✅ 记录 |
| tool_error | Reflect Timeline 添加 🔴 记录，Action Map 显示重试 |
| LLM 回复 | 检测是否该推进到下一步（从 PQ 取下一项） |

```python
# 每次 tool_done 后，检查当前 PQ item 是否该标记完成
def check_pq_advancement(agent_loop, scene_id, db):
    """检测当前 P1 是否应标记完成，自动启动 P2"""
    current = db.query(PriorityQueue).filter(
        PriorityQueue.scene_id == scene_id,
        PriorityQueue.status == "running"
    ).first()
    if current and should_mark_complete(current, agent_loop):
        current.status = "completed"
        current.completed_at = datetime.utcnow()
        # 找下一个可执行的任务
        next_item = find_next_ready(db, scene_id)
        if next_item:
            next_item.status = "running"
            # emit SSE 事件通知前端
```

### 5.3 SSE 事件扩展

新增 SSE 事件类型供仪表盘实时刷新：

| SSE 事件 | 触发时机 | 负载 |
|---------|---------|------|
| `dashboard:converge` | 收敛完成 | 节点合并列表、废弃列表 |
| `dashboard:queue_update` | 排序/PQ 变更 | 完整 PQ 列表 |
| `dashboard:action_update` | 正在执行的子任务更新 | 当前任务、进度、已用工具 |
| `dashboard:reflect` | 反馈记录新增 | type/title/detail/tag |
| `dashboard:phase` | 阶段切换 | 当前阶段名称 |
| `dashboard:loop_status` | 循环状态变更 | 循环次数、总步数 |

### 5.4 消息记录（第三层隐藏记录）

在 `stream_scene_message()` 中，Agent Loop 完成后，为每个完成的 PQ 子任务生成一条 tool_result 摘要消息：

```python
# 在 Agent Loop 结束后
for pq_item in completed_items:
    summary_msg = Message(
        id=make_id("msg"),
        scene_id=scene_id,
        role="system",
        content=build_task_summary(pq_item, agent_tool_results),
        session_id=data.session_id,
        model=model_name,
        display=False,  # 前端不渲染
    )
    db.add(summary_msg)
```

每条格式示例：
```
【P1 事故车判定与出险调研 — 完成】
国标GB/T 30323-2013: 9条判定红线
3类事故: 碰撞/泡水/火烧
检测方法: 外观/结构件/功能性检查
决策: 采用国标为判定依据
```

---

## 六、前端实现

### 6.1 场景聊天页面重构

当前 `ChatView.tsx` 结构：
```
[Topbar]
[场景标签行]
[消息列表]
[输入框]
```

改为：
```
[Topbar]
[场景标签行]
[Loop Diagram]          ← 新增
[可折叠 Mind Map]       ← 新增（现有 CustomMindMap 改位置）
[2×2 仪表盘网格]        ← 新增
[消息列表 (缩短)]        ← 现有，高度减少
[输入框]                 ← 现有
[Status Bar]             ← 扩展 Token 条
```

### 6.2 组件树

```
ChatView.tsx
├── AgentLoopDashboard
│   ├── LoopDiagram          — 5 阶段 SVG 图，高亮当前
│   ├── CollapsibleMindMap   — 可折叠 CustomMindMap + badge
│   └── DashboardGrid
│       ├── TMResultsCard    — 收敛结果列表
│       ├── PriorityQueueCard— PQ 列表 + WIP 控制
│       ├── ActionMapCard    — 聚焦执行卡片 + 进度
│       └── ReflectCard      — 反馈时间线
├── MessageList              — 聊天消息（缩短）
├── ChatInput                — 输入框
└── StatusBar                — 阶段 + Token
```

### 6.3 关键交互

| 交互 | 行为 |
|------|------|
| 点击 Loop Diagram 某阶段 | 高亮显示对应面板 |
| 展开/折叠 Mind Map | 切换 SVG 树显示 |
| 点击 TM 收敛列表节点 | 展开详情（含 Merge 来源、备注） |
| PQ 拖拽调整 | 触发后端重排序（可选，v1 暂不实现） |
| WIP 输入框 | 修改并行执行数（默认 1） |

### 6.4 实时刷新

通过 SSE 事件的 StreamConsumer（现有 `sendSceneMsg()` 的 for-await 循环）接收仪表盘事件，更新对应 store 字段。

**Store 新增字段**：
```typescript
{
  // 仪表盘状态
  dashboardPhase: string          // 当前阶段
  dashboardLoopCount: number
  dashboardStepCount: number
  
  // PQ
  priorityQueue: PriorityItem[]   // PQ 完整列表
  
  // Action Map
  activeTask: ActionTask | null   // 当前执行任务
  taskProgress: number            // 0-100
  taskTools: string[]             // 已用工具列表
  nextUpPreview: string[]         // 下一步队列预览
  
  // Reflect
  reflectTimeline: ReflectItem[]  // 时间线记录
  
  // 折叠状态
  mindMapOpen: boolean
}
```

---

## 七、实施阶段

### Phase 1：数据模型 + 后端管线（优先级：最高）

| 任务 | 文件 | 描述 |
|------|------|------|
| 1.1 | `models.py` | 新增 PriorityQueue、ReflectTimeline 表，Message 加 display 字段 |
| 1.2 | `router/scenes.py` | 实现 `auto_converge_and_prioritize()` 函数 |
| 1.3 | `agent_core/agent_loop.py` | 添加 PQ 同步钩子（tool_done 后检查推进） |
| 1.4 | `router/scenes.py` | 新增 SSE 事件发射 |
| 1.5 | `api/scenes.py` | 新增 PQ / Reflect / LoopStatus 的 REST 端点 |

### Phase 2：前端仪表盘组件（优先级：高）

| 任务 | 文件 | 描述 |
|------|------|------|
| 2.1 | `components/LoopDiagram.tsx` | 5 阶段 SVG 循环图 |
| 2.2 | `components/CollapsibleMindMap.tsx` | 可折叠包装器 + badge |
| 2.3 | `components/TMResultsCard.tsx` | 收敛结果列表卡 |
| 2.4 | `components/PriorityQueueCard.tsx` | PQ 卡片 |
| 2.5 | `components/ActionMapCard.tsx` | 聚焦执行卡片 |
| 2.6 | `components/ReflectCard.tsx` | 反馈时间线 |
| 2.7 | `components/DashboardGrid.tsx` | 2×2 网格容器 |
| 2.8 | `components/AgentLoopDashboard.tsx` | 仪表盘根组件（组合以上所有）|

### Phase 3：SSE 对接 + 实时刷新（优先级：高）

| 任务 | 文件 | 描述 |
|------|------|------|
| 3.1 | `appStore.ts` | 新增仪表盘 store 字段 + SSE handler |
| 3.2 | `api/client.ts` | 新增 API 端点 |
| 3.3 | `ChatView.tsx` | 整合 Dashboard、调整消息列表高度 |

### Phase 4：收敛排序管线调试（优先级：中）

| 任务 | 描述 |
|------|------|
| 4.1 | 用「查二手车」测试自动收敛+排序 |
| 4.2 | 测用户纠正后重排序 |
| 4.3 | 测反馈注入新节点后自动遍历 |

---

## 八、未解决问题（待确认）

| 问题 | 状态 |
|------|------|
| WIP（并行执行数）默认为 1，是否需要在前端可配置？ | 原型有，先保留 |
| PQ 拖拽重排是否做？ | v1 不做，只展示静态 |
| Status Bar 中的「循环次数」指什么？一次 Agent Loop 循环？ | 待定义 |
| Reflect Timeline 是否支持展开更多历史？（超过 10 条时）| 可行，支持 scroll |

---

## 九、相关引用

- `prototypes/agent-loop-v1.1.html` — 原型设计（布局、配色、交互参考）
- `docs/design/schema-v0.6.md` — Context 管线 + Dialog Engine（v0.7 之前的上一个 schema）
- `references/dialog-engine-design.md` — Dialog Engine 阶段机（与 dashboard phase 联动）
- `references/session-search-records.md` — 第三层隐藏消息的 session_search 使用
