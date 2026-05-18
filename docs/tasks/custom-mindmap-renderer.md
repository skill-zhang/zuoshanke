# 自定义思维导图渲染器 · 任务说明

> 基于 d3-hierarchy 替换 markmap，实现带语义颜色/状态标记/收敛标注的自定义 SVG 思维导图
> 参考原型：`prototypes/agent-loop-v1.1.html`

---

## 背景

当前 Thinking Map 用 `markmap-lib` + `markmap-view` 渲染，只能展示树结构，无法表达：

- 节点状态（已收敛/已废弃/反馈新增/头脑风暴中/已排入队列）
- 收敛合并记录（哪几个节点合成了哪一个）
- 已废弃的虚线+删除线
- 反馈注入节点的特殊标记

原型 `agent-loop-v1.1.html` 中有一段纯手绘 SVG 展示了目标效果（展开"思维导图"折叠区域即可见）。

---

## 技术方案

### 核心依赖（已安装）

- `d3-hierarchy` — `d3.tree()` / `d3.cluster()` 计算树布局坐标
- `d3-zoom` — 缩放平移
- `d3-selection` — SVG 操作
- 上述均已包含在 `d3` 包中，项目已安装 `d3`（来自 markmap 的依赖）

### 目标输出

一个 React 组件 `CustomMindMap`，替换 `ThinkingMapDrawer.tsx` 中的 markmap 渲染逻辑。

---

## 组件接口

```typescript
interface CustomMindMapProps {
  nodes: ThinkNode[];         // 当前 TM 的节点列表（扁平数组）
  merges?: MergeRecord[];     // 收敛合并记录
  onNodeClick?: (nodeId: string) => void;
  width?: number;
  height?: number;
}

interface MergeRecord {
  target_node_id: string;     // 合并到的目标节点
  source_labels: string[];    // 被合并的原始节点名称列表（如 ["天气API选择", "免费天气接口", "OpenWeather评估"]）
}
```

### 渲染逻辑

1. 用 `d3.stratify()` 将扁平 `nodes` 转为层次结构（`parent_id` 字段）
2. 用 `d3.tree().size([width, height])` 计算每个节点的 `x, y` 坐标
3. 遍历节点，根据 `node.status` 和 `node.action_status` 决定样式：
4. 在 SVG 中绘制连线 + 节点 + 文本 + 状态标记

---

## 节点样式表

| 状态组合 | 视觉样式 | 参考原型中的效果 |
|---------|---------|----------------|
| `status='refined'` + `action_status='in_queue'` | 🟢 绿色实线边框，绿色填充背景（淡），节点文本带 ✅ 前缀 | 原型中"推荐算法"样式 |
| `status='refined'` | 🟠 橙色实线边框，橙色填充背景（淡），节点文本带 🔀 前缀 | 原型中"调研天气API"样式 |
| `status='created'`（默认风暴中） | 🔵 蓝色实线边框，默认背景 | 原型中"设计数据模型"样式 |
| `status='discarded'` | ⚪ 灰色虚线边框，文本删除线，透明度 0.5 | 原型中"自建爬虫"样式 |
| 来自反馈注入（`created_by='reflect'`） | 💗 粉色虚线边框（`stroke-dasharray="4,3"`），节点文本带 💡 前缀 | 原型中"缓存层设计"样式 |
| `status='confirmed'` | 维持现有，绿色边框 + ✅ | ThinkingMapDrawer 现有 |

---

## 收敛标注

当 `merges` 数组不为空时，在 SVG 底部或侧边绘制收敛标注：

```
🔀 调研天气 API ← "天气API选择" + "免费天气接口" + "OpenWeather评估"
```

参考原型中底部蓝色半透明框的标注区域。

交互：点击收敛标注可高亮对应的目标节点。

---

## 附加功能

### 缩放平移
- 使用 `d3-zoom` 实现
- 默认 `fit()` 显示全图
- 双指/滚轮缩放，拖拽平移

### 节点点击
- 点击节点触发 `onNodeClick(nodeId)`
- 保持现有的"节点设置"面板交互（标记可执行/不可执行）

### 响应式
- SVG 容器 `width: 100%; height: 100%`
- 用 `viewBox` + `preserveAspectRatio` 自适应

### 深色主题
- 保持 `#16161e` 背景
- 连线颜色 `#4a4a6a`
- 文本颜色 `#d0d0d8`

---

## 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/components/CustomMindMap.tsx` | **新建** | 核心组件，~300 行 |
| `frontend/src/components/ThinkingMapDrawer.tsx` | 修改 | 引入 CustomMindMap 替换 markmap 渲染 |
| `frontend/src/api/client.ts` | 追加（可选） | 加 `MergeRecord` 接口定义 |

---

## 测试方法

1. 启动 dev server（`cd frontend && ~/.hermes/node/bin/pnpm run dev`）
2. 打开场景 → 点击侧边栏 Thinking Map → 看到新的自定义渲染效果
3. 对比原型 `agent-loop-v1.1.html` 的效果

---

## 参考文件

- 原型：`prototypes/agent-loop-v1.1.html` — 思维导图部分（`<svg class="mm-tree">`）展示了目标效果
- 现有代码：`frontend/src/components/ThinkingMapDrawer.tsx` — 完整的 TM 抽屉组件，可参考节点数据处理逻辑
- 数据接口：`frontend/src/api/client.ts` 中 `ThinkNode` 接口定义了节点字段
- d3-hierarchy 文档：https://d3js.org/d3-hierarchy/tree
