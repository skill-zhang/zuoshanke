# Schema v1.3 — 工作台（Dashboard）

> **里程碑说明：** Schema v1.3 定义了坐山客工作台——用户的 AI 驱动首页。工作台取代聊天视图成为默认入口。工作台上的卡片就是场景广场里的场景，坐山客本体通过对话创建/修改场景来控制工作台内容。用户在工作台和空间（聊天/Sidebar）之间双向跳转。
>
> 设计日期：2026-05-25
> 核心贡献者：张清泉（需求设计）、坐山客（架构设计 & 原型实现）
>
> **核心洞察：工作台卡片 = 场景广场场景。不需要新建表、新建 API、新建引擎。是已有架构的重新组合，不是新系统的搭建。**
>
> 关联文件：
> - `prototypes/prototype-workbench-v1.1.html`（原型终版）
> - `prototypes/prototype-workbench.html`（原型初版，已存档）
> - `docs/design/schema-v1.2.md`（自省地图呈现）
> - `docs/design/schema-v1.1.md`（Session Management & Token Accounting）
> - `docs/design/schema-v1.0.md`（Context 组合架构）
> - `frontend/src/components/AgentCharacter.tsx`（Avatar 组件）
> - `frontend/src/components/PlazaView.tsx`（场景广场）
> - `frontend/src/components/Sidebar.tsx`（侧边栏）
> - `frontend/src/App.tsx`（路由入口）

---

## 1. 问题陈述

### 1.1 背景

坐山客当前默认入口是聊天视图：用户打开即看到 Sidebar + ChatView。但这有两个问题：

1. **新用户第一眼看到的是空聊天框**，需要先在 Sidebar 里找入口，认知负担高
2. **场景广场（Plaza）没有发挥应有的作用**——它只是一个浏览页，和首页没有关系

工作台解决这两个问题：场景广场里的场景直接渲染为卡片，用户进入即见，场景广场从浏览页升级为首页的数据源。

### 1.2 核心洞察

> **工作台卡片 = 场景广场场景。**
>
> 不新建表。不新建 CRUD API。不新建策展引擎。
> 场景表加两个字段（`show_on_workbench` / `workbench_position`），前端工作台视图读场景列表过滤渲染。
> 用户说「加一个 Github Trending 卡片」→ 坐山客建场景 → 勾上 `show_on_workbench` → 自动出现在工作台。

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **复用不新建** | 场景广场已有的场景就是工作台卡片的数据源，不加新表 |
| **对话驱动** | 用户通过底部输入栏跟坐山客说话，坐山客创建/修改场景 |
| **轻量优先** | 无 Topbar，Avatar 悬浮居中，内容撑满视口 |
| **双向跳转** | 工作台 ↔ 空间，通过按钮 + Sidebar 互为入口 |
| **渐进增强** | 未配置工作台时回退到当前聊天视图 |

---

## 2. 用户流程

### 2.1 入口决策

```
用户打开 zuoshanke
       │
       ▼
  ┌─────────────────┐
  │ 有 show_on_workbench │
  │ = true 的场景吗？    │
  └────────┬────────┘
           │
      ┌────┴────┐
     是         否
      │         │
      ▼         ▼
   工作台    当前聊天视图
      │      (ChatView)
      │
      ├── [点击卡片] ──→ 进入该场景聊天
      │
      ├── [进入坐山客空间 →] ──→ 聊天视图 + Sidebar
      │                          (默认闲聊频道)
      │
      └── 底部输入栏 ──→ 跟坐山客说话，创建新场景卡片
```

### 2.2 双向导航

```
 工作台                             空间（聊天 + Sidebar）
┌───────────────┐              ┌────────────────────┐
│ 晚上好 🌆     │              │ Sidebar             │
│               │  ──────→    │  · 闲聊              │
│ [进入空间 →]  │  点按钮      │  · 坐山客自开发       │
│               │              │  · 频道A             │
│ 卡片网格      │              │  ...                 │
│ (场景卡片)     │  ←──────    │  · 工作台 ← Sidebar   │
│               │  Sidebar     │  · 场景广场           │
│               │  点工作台     │  · 工坊              │
└───────────────┘              └────────────────────┘
```

### 2.3 移动端

- 卡片网格单列（`grid-template-columns: 1fr`）
- 输入栏底部固定，`⌘K` 外加点击切换
- 收起后仅 6px 可见 + ▼ 标签（48×24px，移动端可点击）

---

## 3. 页面结构

### 3.1 布局（无 Topbar）

```
┌───────────────────────────────────────────────┐
│                    🧑‍💻 [Avatar]                │  ← position:fixed, center-top
│                                               │
│  晚上好 🌆          14:30:00  [进入坐山客空间 →] │  ← greeting 行
│                                               │
│  ┌─🌤️ 天气──┐ ┌─✅ 待办──┐ ┌─📈 股票──┐       │
│  │ 场景卡片  │ │ 场景卡片  │ │ 场景卡片   │       │  ← card-grid
│  │ 点击进入  │ │ 点击进入  │ │ 点击进入   │       │     auto-fill
│  │ 该场景    │ │ 该场景    │ │ 该场景    │       │     min 340px
│  └──────────┘ └──────────┘ └──────────┘       │
│                                               │
├───────────────────────────────────────────────┤
│  ▲                              ⌘K 唤起       │  ← float-bar
│  [💬 跟坐山客说你想看什么...]           [发送]  │     position:fixed
└───────────────────────────────────────────────┘
```

### 3.2 关键 CSS 决策

| 决策 | 值 | 理由 |
|------|-----|------|
| `.main` top padding | 3px | 最大化首屏内容 |
| `.main` bottom padding | 110px | 为浮动输入栏留白，滑到底不遮挡 |
| Avatar z-index | 100 | 浮在内容之上，pointer-events: none 不拦截点击 |
| Float-bar z-index | 200 | 浮在 Avatar 之上 |
| Float-bar collapsed | `translateY(calc(100% - 6px))` | 收起后只留 6px |
| Toggle 尺寸 | 48×24px | 移动端手指可点 |
| Card grid | `repeat(auto-fill, minmax(340px, 1fr))` | 桌面多列，移动单列 |
| Greeting font-size | 28px | 无 Topbar 后需要足够大的视觉锚点 |

### 3.3 配色体系

- **金色渐变**（logo 文本 + 主按钮 + 发送按钮）：`linear-gradient(135deg, #e6c84a 0%, #c8a84e 50%, #a08030 100%)`
- **按钮 hover**：边框 `#ffd700` + opacity 0.9
- **输入框 focus**：边框 `#c8a84e`
- **Logo 文本**：`linear-gradient(180deg, #ffd700 0%, #f0c040 30%, #c8a84e 60%, #a08030 100%)` + `drop-shadow(0 0 6px rgba(255,215,0,0.3))`

---

## 4. 卡片即场景

### 4.1 数据模型

**不新建表。** 已有 `scenes` 表加两个字段：

```sql
ALTER TABLE scenes ADD COLUMN show_on_workbench BOOLEAN DEFAULT 0;
ALTER TABLE scenes ADD COLUMN workbench_position INTEGER DEFAULT 0;
```

### 4.2 现有场景 Schema 被选入工作台的场景

```
scenes 表（已有）
├── id
├── name              → 卡片标题
├── icon              → 卡片图标
├── description       → 卡片副标题
├── category          → 卡片分类（生活/工作/金融...）
├── pinned            → （不影响工作台显示）
├── show_on_workbench → ★ 是否在工作台显示（新增）
├── workbench_position→ ★ 排序（新增）
└── ...其他字段不变
```

### 4.3 如何创建卡片

用户通过底部输入栏跟坐山客说话，坐山客用已有的场景创建流程：

```
用户: "加一个 Github Trending 卡片"
    │
    ▼
坐山客本体 Agent Loop:
  1. POST /api/scenes 创建场景 "Github Trending"
  2. 设 show_on_workbench = true
  3. 设 workbench_position = 自动排序到末尾
  4. 如果需要数据（如 GitHub API），在场景内跑
    │
    ▼
前端工作台自动刷新 → 新卡片出现
```

### 4.4 如何删卡片

```
用户: "隐藏股票卡片"
    │
    ▼
坐山客: PATCH /api/scenes/{id} { show_on_workbench: false }
    │
    ▼
前端工作台过滤掉 → 卡片消失
（场景本身还在场景广场里，只是不在工作台显示了）
```

### 4.5 如何调顺序

```
用户: "把天气放到最下面"
    │
    ▼
坐山客: PATCH /api/scenes/{id} { workbench_position: 999 }
```

### 4.6 卡片点击行为

点击工作台上的卡片 → `handleEnterScene(scene)` → 进入该场景的聊天视图。和场景广场里点卡片的行为完全一致，复用已有逻辑。

### 4.7 卡片内容渲染

每张卡片渲染场景的「产出」内容：

```
┌─🌤️ 今日天气──────────────────────────┐
│ 场景名称: 天气查询                     │
│ 最新产出: 26°C 晴朗 · 北京              │  ← 场景的 output 或最新消息摘要
│ 点击进入 →                            │
└───────────────────────────────────────┘
```

如果场景还没有产出，显示占位提示「坐山客正在准备中…」。

---

## 5. Avatar 集成

### 5.1 位置

- `position: fixed; top: 0; left: 0; width: 100%; display: flex; justify-content: center`
- 与空间中一致：浮在顶部正中，56×56px SVG，护目镜赛博朋克风
- `pointer-events: none` 在外层，`pointer-events: auto` 在容器层——不拦截页面交互

### 5.2 状态

- **默认 idle**：闭眼微笑，气泡「在线待命」
- **hover**：护目镜发光增强，气泡弹性弹出
- **工作中**（未来）：轮询本体 mood API，切换为 thinking/working 态

### 5.3 与空间的一致性

工作台的 Avatar 渲染的是**同一个 AgentCharacter 组件**，轮询 `/api/zhu-agent/status` 获取本体 mood（9 态），不是工作台专属副本。

---

## 6. Sidebar 集成

### 6.1 新增「工作台」导航

在 Sidebar「你的伙伴」区域新增：

```
你的伙伴
  ├── 💬 闲聊
  ├── ⚒️ 坐山客自开发
  └── 🏠 工作台          ← 新增
```

- 点击 → `setView('workbench')`
- active 态：当前 view === 'workbench' 时高亮
- 从工作台点 [进入空间 →] 后，Sidebar 保持可见，「工作台」入口始终可点

### 6.2 ViewPage 类型扩展

```typescript
// appStore.ts
export type ViewPage = 'chat' | 'plaza' | 'workshop' | 'tools' | 
  'capability-verify' | 'skills' | 'memory' | 'dashboard' | 
  'outputs' | 'delegate-results' | 'secret-garden' | 'settings' |
  'workbench';  // ← v1.3 新增
```

### 6.3 路由

```typescript
// App.tsx
{
  view === 'workbench' ? <WorkbenchView /> :
  view === 'chat' ? <ChatView /> :
  // ... 其他视图
}
```

---

## 7. API

### 7.1 不需要新建 API

工作台不需要新端点。全部复用已有的场景 API：

| 已有端点 | 工作台用途 |
|----------|-----------|
| `GET /api/scenes` | 前端过滤 `show_on_workbench=true` → 渲染工作台卡片 |
| `POST /api/scenes` | 坐山客创建新场景 → 自动出现在工作台 |
| `PATCH /api/scenes/{id}` | 切换显隐 / 调整排序 |
| `GET /api/scenes/{id}/messages` | 获取场景最新产出用于卡片摘要 |
| `GET /api/scenes/{id}/outputs` | 获取场景产出文件用于卡片展示 |

### 7.2 Schema 新增字段

`PATCH /api/scenes/{id}` 请求体新增可选字段：

```json
{
  "show_on_workbench": true,
  "workbench_position": 3
}
```

`GET /api/scenes` 响应中每条场景新增：

```json
{
  "id": "scn_xxx",
  "name": "天气查询",
  "icon": "🌤️",
  "show_on_workbench": true,
  "workbench_position": 0,
  "...其他字段不变"
}
```

---

## 8. 回退兼容

### 8.1 未配置工作台

所有场景 `show_on_workbench = false` → 前端渲染聊天视图（当前默认行为）。

### 8.2 渐进迁移

1. v1.3 上线后，`appStore` 默认 view 从 `'chat'` 改为 `'workbench'`
2. 后端 `init_db` 可预置几个种子场景并设 `show_on_workbench=true`（天气、待办等）
3. 现有用户默认无工作台场景 → 自动回退到聊天视图
4. 用户第一次说「加一个卡片」→ 坐山客建第一个工作台场景 → 下次进入即见工作台

---

## 9. 文件清单

| 层 | 文件 | 变更类型 |
|----|------|----------|
| 原型 | `prototypes/prototype-workbench-v1.1.html` | 新增（定稿） |
| 原型 | `prototypes/prototype-workbench.html` | 新增（初版，已存档） |
| 设计 | `docs/design/schema-v1.3.md` | 本文档 |
| 前端 | `frontend/src/components/WorkbenchView.tsx` | 新增 |
| 前端 | `frontend/src/App.tsx` | 修改（+workbench 路由） |
| 前端 | `frontend/src/stores/appStore.ts` | 修改（+ViewPage 类型 + 默认 view） |
| 前端 | `frontend/src/components/Sidebar.tsx` | 修改（+工作台 导航项） |
| 前端 | `frontend/src/api/client.ts` | 修改（Scene 类型 + 字段） |
| 前端 | `frontend/src/index.css` | 修改（+workbench 样式） |
| 后端 | `backend/models.py` | 修改（Scene 模型 + 2 字段） |
| 后端 | `backend/schemas.py` | 修改（SceneCreate/Update + 2 字段） |
| 后端 | `backend/router/scenes.py` | 无需改动（PATCH 自动支持新字段） |
| 后端 | `backend/database.py` | 修改（`create_all()` 自动加列，种子数据） |

12 个文件。后端只改 3 个，前端 6 个。

---

## 10. 实现阶段

| 阶段 | 内容 | 涉及文件 |
|------|------|----------|
| Phase 1 | Scene 模型加字段 + 种子数据 | models.py, schemas.py, database.py |
| Phase 2 | 前端 Scene 类型 + client.ts | client.ts |
| Phase 3 | WorkbenchView 组件 | WorkbenchView.tsx, index.css |
| Phase 4 | 路由 + appStore + Sidebar | App.tsx, appStore.ts, Sidebar.tsx |
| Phase 5 | 坐山客对话建场景 → 自动上工作台 | 已有流程，无需改代码 |
| Phase 6 | 移动端适配 + 动画 | CSS 调整 |

---

## 11. 已确认的决策

| 问题 | 结论 |
|------|------|
| 「进入空间 →」后 Sidebar 状态 | 默认展开「你的伙伴」区域 |
| 工作台对话 session 策略 | 每次用新 session |
| 卡片排序和显隐 | 用户可通过对话调整 |
| 多用户 | 当前单用户架构，不考虑 |
