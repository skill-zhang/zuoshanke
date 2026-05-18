# 自定义思维导图渲染器 · 设计实现

> 基于 d3-hierarchy 的自定义 SVG 思维导图渲染器，替换 markmap。
> 组件：`frontend/src/components/CustomMindMap.tsx`

---

## 背景

原有 Thinking Map 使用 `markmap-lib` + `markmap-view` 渲染。markmap 只能展示树结构，无法表达节点状态语义（收敛/废弃/反馈注入）、收敛合并记录等 Agent Loop 需要的交互信息。

## 目标

一个独立的 React 组件 `CustomMindMap`，接收扁平节点数据，渲染为带语义颜色、状态标记、收敛标注的自定义 SVG 树形图，支持缩放平移、节点点击交互。

## 关键设计决策

### 1. 独立组件，零耦合

组件不依赖任何 store、API 调用或后端数据结构。只通过 Props 接收数据，返回 SVG 渲染结果。这使得它可以：
- 在任意 React 页面独立使用
- 单元测试无需 mock 环境
- 未来可以独立发布为 npm 包

### 2. d3 原生渲染，不经过中间层

| 方案 | 决策 |
|------|------|
| ~~markmap + CSS hack~~ | 放弃 — 无法实现状态标记 |
| ~~React + SVG 纯 JSX~~ | 放弃 — 树布局计算量大，React re-render 开销高 |
| **d3-hierarchy 算布局 + d3-selection 操控 SVG** | ✅ |

d3 负责：布局计算、缩放监听、DOM 操作。React 只负责：组件挂载/卸载、props 传递。两者各司其职。

### 3. 样式映射表写死，不开放配置

6 种节点状态的样式全部内置于 `STYLE_RULES` 数组，按优先级匹配。原因：
- 调用方不需要关心样式细节
- 状态语义是业务定死的，不是可定制的 UI 主题
- 减少 API 复杂度

### 4. 收敛标注在 SVG 外渲染

收敛合并标注作为 React `div` 列表渲染在 SVG 下方，而非画在 SVG 内。原因：
- React 交互更方便（hover 变色、点击高亮）
- 文案可换行、可截断，不受 SVG text 限制
- 与节点点击共享同一个 `onNodeClick` 回调

## 渲染管线

```
┌──────────────┐
│ 扁平节点数组  │  ThinkNodeData[]
│  parent_id   │
└──────┬───────┘
       │ d3.stratify()
       ▼
┌──────────────┐
│ 层次结构树    │  HierarchyNode<ThinkNodeData>
│  parent      │
│  children[]  │
└──────┬───────┘
       │ d3.tree().nodeSize()
       ▼
┌──────────────┐
│ 布局坐标      │  每个节点有 {x, y}
│  防重叠      │  nodeSize + separation 保证
└──────┬───────┘
       │ d3-selection 遍历
       ▼
┌─────────────────────────────────┐
│ SVG 绘制                        │
│  ├─ defs/marker（箭头）         │
│  ├─ path（贝塞尔连接线）        │
│  ├─ rect（节点矩形）            │
│  └─ text（节点文本+前缀emoji）  │
└─────────────────────────────────┘
       +
┌─────────────────────────────────┐
│ React: 收敛标注列表              │
│  └─ MergeRecord[] → 可点击条目   │
└─────────────────────────────────┘
```

## 防重叠策略

同层节点相互遮挡是树布局的常见问题。解决方案：

```
d3.tree()
  .nodeSize([48, 68])         // 每个节点分配 48px 水平 × 68px 垂直空间
  .separation((a, b) => {
    return a.parent === b.parent
      ? 2.8    // 兄弟节点：48 * 2.8 = 134px 间距
      : 4.0;   // 非兄弟：48 * 4.0 = 192px 间距
  });
```

- 使用 `nodeSize` 而非 `size` — 前者固定每节点占用空间，后者只设整体画布大小
- `separation` 返回乘数，兄弟节点间距更紧凑，非兄弟间距更大
- 总宽度没有硬上限，但 `viewBox` 会自动缩放适配容器宽度

## 节点状态映射

| 优先级 | 条件 | 视觉 | 含义 |
|--------|------|------|------|
| 1 | `status='discarded'` | 灰色虚线 + 删除线 + 0.5 透明 | 已废弃 |
| 2 | `created_by='reflect'` | 粉色虚线 + 💡 | 反馈注入 |
| 3 | `status='confirmed'` | 绿色实线 + ✅ | 已确认 |
| 4 | `status='refined'` + `action_status='in_queue'` | 绿色实线 + ✅ | 已收敛→队列 |
| 5 | `status='refined'` | 橙色实线 + 🔀 | 已收敛 |
| 6 | 默认 | 蓝色实线 + 💭 | 头脑风暴 |

> 按优先级从上到下匹配，一票决定。

## 连接线颜色策略

连接线颜色取自 **子节点的边框色**，而非父节点。这样每个分支的颜色能直观反映该叶子节点的状态。

同时，为避免 marker（箭头）颜色与连接线不一致，每个颜色值在 `defs` 中注册唯一的 marker ID。

## 缩放与初始适配

```
d3.zoom()
  .scaleExtent([0.2, 4])    // 缩放范围
```

初始适配算法：
1. 计算所有节点的 bounding box
2. 计算适配比例：`min(svgW / contentW, svgH / contentH, 1.6)`
3. 计算平移量使内容居中
4. 用 `d3.zoomIdentity.translate(tx, ty).scale(scale)` 设置初始

## 与原型的关系

原型 `prototypes/agent-loop-v1.1.html` 中的 `<svg class="mm-tree">` 是固定坐标的手绘 SVG，展示了目标效果。本组件的目标是**用算法自动生成相同风格**的树。

相比原型，本组件的增强：
- 自动布局（不再是硬编码坐标）
- 交互式（缩放/平移/点击）
- 收敛标注可点击高亮
- 状态映射为代码规则而非手动设置

## 文件结构

```
frontend/src/components/CustomMindMap.tsx   ← 主文件（组件 + Demo + 类型 + 样式映射）
docs/api/custom-mindmap-renderer.md          ← API 接口文档
docs/design/custom-mindmap-renderer.md       ← 本文（设计实现文档）
```

## 集成路线

1. 在 `ThinkingMapDrawer.tsx` 中引入 `CustomMindMap`
2. 将 `nodesToMarkdown()` 逻辑替换为直接传 `nodes` + 组装 `merges`
3. 移除 `Transformer`、`Markmap.create()`、`markmap-lib` 依赖（可选）
4. `onNodeClick` 接入现有的节点设置面板

```tsx
// 替换前
const markdown = nodesToMarkdown(thinkingMap.nodes);
const result = transformer.transform(markdown);
const mm = Markmap.create(svg, {}, result.root);

// 替换后
<CustomMindMap
  nodes={thinkingMap.nodes}
  merges={buildMerges(thinkingMap.nodes)}
  onNodeClick={handleNodeClick}
/>
```

## 注意事项

- `d3.stratify()` 要求每个节点有唯一的 `id`，`parent_id` 必须指向存在的节点 ID，否则会抛出异常。代码中用 `nodes.some()` 做了存在性检查
- 非根节点如果 `parent_id` 为 null，会被强制设为孤儿节点，`stratify` 会将其作为根节点的兄弟（或独立成根）。建议外部保证数据完整性
- 组件使用 `useEffect` 进行 d3 渲染，`nodes` 引用变化时会全量重绘（没有 diff 优化）。对于频繁更新的场景，建议外部做浅比较或 debounce

## 参考

- 任务文档：`docs/tasks/custom-mindmap-renderer.md`
- 原型：`prototypes/agent-loop-v1.1.html`
- d3-hierarchy Tree API：https://d3js.org/d3-hierarchy/tree
- d3-zoom API：https://d3js.org/d3-zoom
