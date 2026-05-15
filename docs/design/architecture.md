# 架构设计决策 — 双图架构

> 日期: 2026-05-15
> 状态: 草案

---

## 一、问题定义

### 当前 AI Agent 的三个痛点

1. **事前不可见** — AI 收到任务后直接执行，用户不知道整体规划
2. **事中不可追踪** — 执行过程是黑盒日志，没有结构化的行动追踪
3. **出错恢复靠蛮力** — 失败后靠 prompt 追加上下文重新推理，没有显式的计划偏离检测

### 根本矛盾

- **工作流范式（Coze/Dify）**：可观测、可控制，但是预定义的、不 AI Native
- **自主范式（Hermes/Claude Code）**：灵活、智能，但是黑盒、不可控

## 二、核心架构：双图

```
Thinking Map（思维导图）              Action Map（行动图）
─────────────────────────          ─────────────────────
状态: Read/Write ↔ Read-only       状态: Running / Paused / Stopped
用户: 可拖拽改、可讨论改            用户: 只能暂停/停止，不能改
AI:   可提议改                      AI:   自主执行、发现问题回流
方向: 无流向，网状发散              方向: 有流向，START→决策→END
```

### 两张图的关系

- **独立数据结构**，通过引用关联
- Thinking Map 的「可执行」叶子节点 → 触发 Action Map 生成
- Action Map 执行结果可回流 Thinking Map（发现新信息、假设不成立等）
- 非先后顺序，是同一认知过程的两种视图

### 状态锁

Action Map 一旦运行 → Thinking Map 锁定为 Read-only。
解锁只能通过：暂停 Action Map / 停止 Action Map。

## 三、数据层级

```
项目（Project）
  └─ 场景（Scene）                         1:N
       └─ Thinking Map（1:1，多版本）      1:1 per Scene
            └─ 可执行叶子节点
                 │
                 └────────── 触发 ──────────┐
                                            ▼
       └─ Action Map（1:N per Scene）     Task（N:1 per Action Map）
            ├─ 纯结构（图纸）               ├─ 运行时状态
            ├─ 节点 + 边（含条件）           ├─ 执行日志
            └─ AI 可重规划 → 出新版本       ├─ result_summary
                                           └─ artifacts[path]
```

## 四、会话模型

Chat 和 Task 是两套并行会话空间，不是先后顺序：

```
项目
  ├─ Chat Session 001（闲聊）
  ├─ Chat Session 002（闲聊，续接或新建）
  ├─ Action Map 执行中的 Chat（用户等待时闲聊）
  └─ Task 执行日志
```

## 五、引擎集成

Hermes 作为子进程被调用，不修改 Hermes 代码：

```
坐山客                          Hermes（子进程）
──────                          ────────────────
Task 调度  ──spawn──→          hermes chat -q "..."
                              ↓ 返回结果
                              tool calling 自己处理
```

## 六、技术栈

| 层 | 选择 | 理由 |
|---|------|------|
| 前端 | React + Markmap + React Flow | Markmap 思维导图，React Flow 流程图，一套 React |
| 后端 | Python FastAPI | Hermes 同生态，subprocess 零摩擦 |
| 存储 | SQLite + Alembic | 零配置，够用到企业版 |
| 引擎 | Hermes（子进程） | 复用 Provider/Gateway/Tool/Memory |

## 七、开发路线

1. **Phase 1**: Thinking Map 交互原型（前端 + 后端 CRUD）
2. **Phase 2**: Action Map 生成与展示
3. **Phase 3**: Hermes 子进程集成，Task 执行
4. **Phase 4**: 双图联动、回流、版本管理
