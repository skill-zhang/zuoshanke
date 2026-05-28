---
title: Schema v1.8 — 个人工作台独立沙箱化
description: 个人工作台从坐山客主系统中彻底剥离，成为独立的前端+后端沙箱进程。用户可自由修改工作台代码而不影响核心系统。
tags:
  - schema
  - workbench
  - sandbox
  - architecture
---

# Schema v1.8 — 个人工作台独立沙箱化

## 动机

### 问题

个人工作台（WorkbenchView）与坐山客核心系统在同一个前端 bundle 和后端进程中运行。用户修改工作台代码时：

| 风险 | 当前 | 目标 |
|------|------|------|
| 渲染崩溃 | Error Boundary 兜底 | 工作台进程独立，完全隔离 |
| 代码错误炸前端 | 影响整个 SPA | 只炸工作台页面 |
| API 改动误伤核心 | 共享同一后端 | 工作台有自己的后端进程 |
| DB 写坏 | 读写同一 SQLite | 工作台独立 DB |

根本原因是**进程级耦合**——共享内存、共享端口、共享 DB。

### 方案

将个人工作台剥离为**独立的沙箱进程**：

```
┌─ 坐山客核心系统 ─────────────────┐    ┌─ 个人工作台（沙箱）──────────┐
│  :8000（FastAPI）                 │    │  :8001（小 FastAPI）          │
│  ├── 本体 / 记忆 / Agent Loop     │    │  ├── widget CRUD             │
│  ├── 场景 / 频道 / 对话           │    │  ├── 布局配置                │
│  └── 全量路由                     │    │  └── 独立 SQLite              │
├───────────────────────────────────┤    ├──────────────────────────────┤
│  :5173（Vite SPA）                │    │  :5174（Vite SPA）            │
│  ├── ChatView / Sidebar           │    │  ├── WidgetGrid              │
│  ├── Plaza / Garden / Settings    │    │  ├── WidgetRegistry          │
│  └── 核心 UI                      │    │  └── 用户可改的代码          │
└───────────────────────────────────┘    └──────────────────────────────┘
                                                  ↑
                                           炸了只崩这里
```

## 架构

### 目录结构

```
zuoshanke/
├── backend/             ← 主系统后端（原封不动）
├── frontend/            ← 主系统前端（原封不动）
└── workbench/           ← 🆕 独立工作台
    ├── backend/
    │   ├── main.py      ← FastAPI 入口（端口 8001）
    │   ├── models.py    ← 独立数据模型
    │   ├── database.py  ← 独立 SQLite（workbench.db）
    │   └── routes/
    │       ├── widgets.py   ← widget 配置 CRUD
    │       ├── layout.py    ← 布局配置 CRUD
    │       └── assets.py    ← 用户上传资源
    ├── frontend/
    │   ├── package.json
    │   ├── vite.config.ts
    │   ├── index.html
    │   └── src/
    │       ├── main.tsx
    │       ├── App.tsx
    │       ├── components/
    │       │   ├── WidgetGrid.tsx
    │       │   ├── WidgetCard.tsx
    │       │   ├── AddWidgetDialog.tsx
    │       │   └── WidgetSettings.tsx
    │       ├── widgets/       ← Widget 注册表（用户可改）
    │       │   ├── index.ts       ← 注册入口
    │       │   ├── HelloWidget.tsx
    │       │   ├── ClockWidget.tsx
    │       │   └── StockWidget.tsx
    │       └── api.ts
    └── scripts/
        ├── start.sh
        └── stop.sh
```

### 进程隔离

| 维度 | 主系统 | 工作台 |
|------|--------|--------|
| 后端端口 | 8000 | 8001 |
| 前端端口 | 5173 | 5174 |
| DB 文件 | zuoshanke.db | workbench.db |
| Python 进程 | main.py | workbench/backend/main.py |
| Vite 进程 | frontend/ | workbench/frontend/ |
| 启动/停止 | 独立 | 独立 |

### 数据模型

```python
# workbench/backend/models.py

class WidgetConfig(Base):
    """widget 实例配置"""
    __tablename__ = "widget_configs"

    id = Column(String, primary_key=True)
    widget_type = Column(String, nullable=False)  # 注册表中的 widget 类型
    title = Column(String, default="")
    config = Column(Text, default="{}")          # widget 自己的配置 JSON
    position = Column(Integer, default=0)         # 排序
    width = Column(Integer, default=1)            # 网格宽度 (1-4)
    height = Column(Integer, default=1)           # 网格高度 (1-4)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow)


class LayoutConfig(Base):
    """整体布局配置"""
    __tablename__ = "layout_configs"

    id = Column(String, primary_key=True, default="default")
    columns = Column(Integer, default=3)          # 网格列数
    gap = Column(Integer, default=16)             # 网格间距
    max_widgets = Column(Integer, default=20)     # 最大 widget 数量
    theme = Column(String, default="dark")        # dark / light
    updated_at = Column(DateTime, default=utcnow)
```

### API 端点

```
GET    /api/widgets          → 列出所有 widget 配置
POST   /api/widgets          → 新增 widget 实例
PUT    /api/widgets/:id      → 更新 widget 配置
DELETE /api/widgets/:id      → 删除 widget 实例
PUT    /api/widgets/reorder  → 批量更新顺序

GET    /api/layout           → 获取布局配置
PUT    /api/layout           → 更新布局配置

GET    /api/widget-types     → 列出可用的 widget 类型（从注册表读取）
```

### Widget 注册表模式

每个 widget 是一个独立的 React 组件，在 `workbench/frontend/src/widgets/index.ts` 中注册：

```typescript
// widgets/index.ts — Widget 注册表
export interface WidgetMeta {
  type: string;
  name: string;
  icon: string;
  defaultConfig: Record<string, any>;
  component: React.ComponentType<WidgetProps>;
}

export interface WidgetProps {
  config: Record<string, any>;
  onConfigChange: (config: Record<string, any>) => void;
}

const registry: WidgetMeta[] = [
  {
    type: 'hello',
    name: '你好世界',
    icon: '👋',
    defaultConfig: { text: '你好！' },
    component: HelloWidget,
  },
  {
    type: 'clock',
    name: '数字时钟',
    icon: '🕐',
    defaultConfig: { format: '24h' },
    component: ClockWidget,
  },
];

export function getWidgetMeta(type: string): WidgetMeta | undefined {
  return registry.find(w => w.type === type);
}

export function getWidgetTypes(): WidgetMeta[] {
  return registry;
}
```

用户新增 widget 只需在 `widgets/` 目录下新建文件 + 在 `index.ts` 注册。

### 集成方式

主系统前端通过**新标签页**方式打开工作台，不做 iframe：

```typescript
// 主系统 WorkbenchView.tsx — 变为跳转入口
export function WorkbenchView() {
  useEffect(() => {
    window.open('http://localhost:5174', '_self');
  }, []);
  return <div className="workbench-redirect">跳转工作台…</div>;
}
```

用 `_self` 替换当前页面（工作台本身全屏），或 `_blank` 打开新标签页（让主系统在后台保持）。

### 启动/停止

```bash
# 启动工作台
bash workbench/scripts/start.sh
# 停止
bash workbench/scripts/stop.sh

# 整合到主启动脚本中可选
bash scripts/start-zuoshanke.sh --with-workbench
```

## 实现路线

### Phase 1（本文档 — 骨架搭建）

| 步骤 | 内容 |
|------|------|
| 1 | workbench/backend/ — main.py + database.py + models.py + 基本 CRUD |
| 2 | workbench/frontend/ — vite 初始化 + WidgetGrid + 基本注册表 |
| 3 | 主前端 WorkbenchView → 跳转入口 |
| 4 | 启动脚本 + 验证 |

### Phase 2（后续）

- 从主系统导入现有场景作为 widgets
- widget 互相通信
- 工作台版 Error Boundary
- 用户自定义代码沙箱（iframe 内运行）

## 安全性

| 攻击面 | 防护 |
|--------|------|
| 工作台后端被攻破 | 独立进程、独立 DB（zuoshanke.db 不受影响） |
| 工作台前端 XSS | 影响范围仅限于工作台，核心系统 token/数据不受影响 |
| 端口占用 | 8001/5174 先检测是否已被占用 |
| 资源消耗 | 工作台进程可单独限制内存/CPU（通过 systemd/cgroups） |

## 设计决策记录

### 新标签页 vs iframe

选新标签页（`window.open`），理由：

| 方案 | 优点 | 缺点 |
|------|------|------|
| iframe | 在同一页面内嵌 | `sandbox` 严格限制通信，大小适配麻烦，浏览器策略限制 |
| **新标签页** ✅ | **彻底的进程隔离，用户可直观感知切换** | 非内嵌，需要切 Tab |
| `_self` 跳转 | 最轻量、无跨页面问题 | 完全离开主系统 |

### 独立前端 vs 主前端懒加载

不选懒加载，理由：懒加载 chunk 仍在同一个 bundle 和内存空间内，Error Boundary 兜底但进程不隔离。

独立前端 = **真正的沙箱**。

## 历史记录

- **2026-05-28**：初版设计。起因：WorkbenchView 渲染逻辑硬编码 8 种卡片类型，用户改工作台代码可能炸整个 SPA。方案：剥离为独立进程。
- **2026-05-28**：Error Boundary（Layer 1）先行落地。
- **2026-05-28**：Schema v1.8 设计文档定稿。
