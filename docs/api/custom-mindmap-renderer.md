# CustomMindMap API 文档

> 基于 d3-hierarchy 的自定义 SVG 思维导图渲染器，替代 markmap。
> 文件：`frontend/src/components/CustomMindMap.tsx`

---

## 导出接口

### `CustomMindMap`（主组件）

```tsx
import { CustomMindMap } from './CustomMindMap';

<CustomMindMap
  nodes={nodes}
  merges={merges}
  onNodeClick={(nodeId) => console.log('clicked:', nodeId)}
  height={420}
  className=""
/>
```

| Prop | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `nodes` | `ThinkNodeData[]` | ✅ | — | 扁平节点列表，组件内用 `parent_id` 建树 |
| `merges` | `MergeRecord[]` | 可选 | `[]` | 收敛合并记录，渲染在 SVG 下方 |
| `onNodeClick` | `(nodeId: string) => void` | 可选 | — | 点击节点回调 |
| `width` | `number` | 可选 | 自适应容器 | SVG viewBox 宽度 |
| `height` | `number` | 可选 | `400` | SVG viewBox 高度 |
| `className` | `string` | 可选 | `''` | 外层 div 的 CSS class |

---

### `CustomMindMapDemo`（独立预览组件）

```tsx
import { CustomMindMapDemo } from './CustomMindMap';

// 直接渲染，不依赖任何后端/store
<CustomMindMapDemo />
```

使用硬编码的天气推荐系统数据，覆盖所有节点状态类型。在 `App.tsx` 里临时挂载：

```tsx
// import { CustomMindMapDemo } from './components/CustomMindMap';
// 在 return 中：
//   <CustomMindMapDemo />
```

---

## 数据类型

### `ThinkNodeData`

组件接受的扁平节点格式：

```typescript
interface ThinkNodeData {
  id: string;                    // 唯一 ID
  parent_id: string | null;     // 父节点 ID，根节点为 null
  label: string;                // 显示文本
  status: string;               // 状态（见下方映射）
  created_by?: string;          // 'brainstorm' | 'reflect' | 'manual'
  action_status?: string | null;// 'in_queue' | null
  converged_from?: string[];    // 收敛来源节点名
}
```

> 其他字段（如 `priority`, `depends_on` 等）组件不关心，传入也无副作用。

### `MergeRecord`

```typescript
interface MergeRecord {
  target_node_id: string;   // 收敛到的目标节点 ID
  source_labels: string[];  // 被合并的原始节点名称列表
}
```

---

## 节点状态 → 样式映射

优先级从高到低（同时满足多条时取优先）：

| # | 条件 | 边框 | 背景 | 前缀 | 文字色 |
|---|------|------|------|------|--------|
| 1 | `status='discarded'` | 灰色虚线 `#555` | 半透明 | — | `#666`，删除线，opacity 0.5 |
| 2 | `created_by='reflect'` | 粉色虚线 `#ec4899` | 粉底 | 💡 | `#f472b6` |
| 3 | `status='confirmed'` | 绿色实线 `#22c55e` | 绿底 | ✅ | `#4ade80` |
| 4 | `status='refined'` + `action_status='in_queue'` | 绿色实线 `#22c55e` | 绿底 | ✅ | `#4ade80` |
| 5 | `status='refined'` | 橙色实线 `#f97316` | 橙底 | 🔀 | `#fb923c` |
| 6 | 默认（created / brainstorming） | 蓝色实线 `#3b82f6` | 默认 | 💭 | `#60a5fa` |

---

## 交互行为

- **缩放平移**：滚轮缩放，拖拽平移（d3-zoom），范围 0.2×–4×
- **初始适配**：首次渲染自动 fit 所有节点居中显示
- **节点点击**：触发 `onNodeClick(nodeId)`，鼠标变为 pointer
- **收敛标注点击**：触发同一个 `onNodeClick(target_node_id)`，hover 高亮

---

## 数据处理流程

```
[ThinkNode[] 扁平数组]
       │
       ▼ d3.stratify()
[层次结构 HierarchyNode]
       │
       ▼ d3.tree().nodeSize([48, 68])
[布局坐标 {x, y}]
       │
       ▼ 遍历渲染
[SVG: 连接线 + 矩形 + 文本]
       │
       ▼ 上方步骤 + merges
[React: 收敛标注列表]
```

- `d3.stratify()` 用 `parent_id` 建树
- `d3.tree().nodeSize()` 保证同层节点不重叠
- `.separation()` 设置兄弟节点间距 2.8×、非兄弟 4.0×

---

## 样式定制

### 基础主题色（写死，不提供 override）

| 用途 | 色值 |
|------|------|
| 容器背景 | `#16161e` |
| SVG 背景 | `#16161e` |
| 连接线颜色 | 取自子节点边框色 |
| 文本色 | 中性 `#e0e0e8` |
| 边界 | `#2a2a3a` (容器) |

若需要主题定制，可传 `className` 覆盖外层 div 样式，或 Fork 修改 `STYLE_RULES` 映射表。

---

## 文件改动清单

| 文件 | 操作 |
|------|------|
| `frontend/src/components/CustomMindMap.tsx` | **新建** |
| `frontend/package.json` | 追加 `d3` + `@types/d3` |
| 本文件 | **新建** API 文档 |

集成到项目时只需改动：
- 引入 `CustomMindMap` 替代 `ThinkingMapDrawer` 中的 markmap 渲染逻辑
- 传入 `nodes` 和 `merges` 即可

---

## 参考

- 任务文档：`docs/tasks/custom-mindmap-renderer.md`
- 原型：`prototypes/agent-loop-v1.1.html`（`<svg class="mm-tree">` 部分）
- d3-hierarchy Tree：https://d3js.org/d3-hierarchy/tree
