# 场景自省地图 — 方案设计

> 每个场景（分身）拥有一张属于自己的架构可视化图，由 LLM 通过 function calling 自主声明，复用 SelfMapView 渲染引擎。

---

## 1. 动机

**自省图不是本体的专利。** 当前 SelfMapView 只展示坐山客自己的系统架构（硬编码的树+流程图）。但用户的真实场景是：

> 在系统开发场景里，随时能看到当前正在做的系统的架构——组件、模块、业务逻辑——而不是干巴巴的设计文档文字。

**一个场景一张图。** 本体花园里的图画的「坐山客系统」，系统开发场景里的图画「当前项目的架构」，二手车场景里的图可以是「检测流程 + 数据源」。

LLM 在干活过程中自然冒出架构认知，用 function calling 声明的结构化数据驱动渲染，**不画 SVG，只描述节点和关系**。

---

## 2. 数据模型

新表 `scene_self_maps`（`models.py` 追加，`create_all()` 零破坏）：

```python
class SceneSelfMap(Base):
    """场景自省地图 — 每个场景一张架构图"""
    __tablename__ = "scene_self_maps"

    id = Column(String(32), primary_key=True)
    scene_id = Column(String(32), ForeignKey("scenes.id"), nullable=False, unique=True)
    title = Column(String(200), default="")

    # ═══ 树结构 ═══
    # LLM 声明的树节点列表
    # [{id, icon, label, sublabel?, children?[{id, icon, label, sublabel?, children?...}], detail?: {description, rows, codePath}}]
    tree = Column(JSON, default=list)

    # ═══ 流程图（可选）═══
    # 选中特定节点后展示的流程图
    # {nodeId: {title, nodes: [{id, x, y, w, h, icon, label, sub, style}], edges: [[from, to], ...]}, ...}
    diagrams = Column(JSON, default=dict)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

关键设计决策：
- **scene_id 唯一约束** — 一个场景只有一张自省图，最新的覆盖旧的
- **树和图合一** — `tree` 是左侧导航树，`diagrams` 是选中节点后的流程图（keyed by nodeId）
- **JSON 全量存储** — 非增量 diff，每次 LLM 声明/更新都是全量替换
- **变更历史不在本表** — 通过 message 上下文保留 LLM 的 tool call 记录

---

## 3. API 端点

### 3.1 查询

```
GET /api/scenes/{scene_id}/self-map
```

响应：
```json
{
  "id": "smp_xxx",
  "scene_id": "scn_xxx",
  "title": "Zuoshanke 系统架构",
  "tree": [...],
  "diagrams": {...},
  "updated_at": "2026-05-23T18:00:00"
}
```

未创建时返回 `404`（前端回退到空状态提示）。

### 3.2 保存/覆盖

```
PUT /api/scenes/{scene_id}/self-map
```

请求体：
```json
{
  "title": "Zuoshanke 系统架构",
  "tree": [...],
  "diagrams": {...}
}
```

响应：200 + 保存后的完整数据。

### 3.3 删除

```
DELETE /api/scenes/{scene_id}/self-map
```

响应：`{"status": "ok"}`。

---

## 4. LLM Function Calling 工具

在 `registry.json` 注册 2 个新工具，供场景 Avatar 自主调用。

### 4.1 `self_map_declare`（初始化 / 全量覆盖）

```json
{
  "name": "self_map_declare",
  "description": "声明当前场景的架构自省图（初始化或全量覆盖）。只有当前场景有效。调用后可在秘密花园或场景侧边栏查看可视化架构图。",
  "parameters": {
    "title": {"type": "string", "description": "架构图标题，如「Zuoshanke 系统架构」"},
    "tree": {
      "type": "array",
      "description": "左侧导航树。最多 3 层。",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string", "description": "唯一 ID"},
          "icon": {"type": "string", "description": "树节点图标（emoji）"},
          "label": {"type": "string", "description": "节点名称"},
          "sublabel": {"type": "string", "description": "副标签（可选）"},
          "children": {
            "type": "array",
            "description": "子节点（可选，最多 2 层子）",
            "items": {"$ref": "#/definitions/TreeNode"}
          },
          "detail": {
            "type": "object",
            "description": "点击节点后在右侧详情面板展示",
            "properties": {
              "description": {"type": "string", "description": "详细描述"},
              "rows": {
                "type": "array",
                "description": "键值对列表",
                "items": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2}
              },
              "codePath": {"type": "string", "description": "相关代码路径（可选）"}
            }
          },
          "hasDiagram": {
            "type": "boolean",
            "description": "是否有关联的流程图"
          }
        },
        "required": ["id", "icon", "label"]
      }
    },
    "diagrams": {
      "type": "object",
      "description": "流程图字典，key 为树节点 id，value 为流程图定义。只有 hasDiagram=true 的节点才需要。",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "nodes": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": {"type": "string"},
                "x": {"type": "integer", "description": "水平位置（px 坐标）"},
                "y": {"type": "integer"},
                "w": {"type": "integer", "default": 120},
                "h": {"type": "integer", "default": 42},
                "icon": {"type": "string"},
                "label": {"type": "string"},
                "sub": {"type": "string", "description": "副标签"},
                "style": {"type": "string", "enum": ["layer", "process", "highlight", "db", "external"], "default": "process"}
              },
              "required": ["id", "x", "y", "icon", "label"]
            }
          },
          "edges": {
            "type": "array",
            "items": {
              "type": "array",
              "items": {"type": "string"},
              "minItems": 2,
              "maxItems": 2,
              "description": "[from_node_id, to_node_id]"
            }
          }
        },
        "required": ["title", "nodes", "edges"]
      }
    }
  },
  "returns": "保存后的自省地图数据",
  "category": "data"
}
```

### 4.2 `self_map_update`（增量更新）

```json
{
  "name": "self_map_update",
  "description": "增量更新当前场景的自省图（节点/边增删改、标题修改）。适用于架构演进时局部修改。",
  "parameters": {
    "action": {
      "type": "string",
      "enum": ["add_node", "update_node", "remove_node", "add_diagram", "remove_diagram", "update_title"],
      "description": "操作类型"
    },
    "parent_id": {"type": "string", "description": "add_node 时的父节点 id（空=根级）"},
    "node": {"type": "object", "description": "add/update_node 时的节点数据，结构与 tree items 一致"},
    "node_id": {"type": "string", "description": "remove_node 时的节点 id"},
    "diagram_node_id": {"type": "string", "description": "add/remove_diagram 时的树节点 id"},
    "diagram": {"type": "object", "description": "add_diagram 时的流程图定义，结构与 diagrams values 一致"},
    "title": {"type": "string", "description": "update_title 时的新标题"}
  },
  "returns": "更新后的完整自省地图数据",
  "category": "data"
}
```

### 4.3 执行器

`tools/registry.json` 新增工具后，配套实现 2 个执行函数。

文件 `tools/self_map_tool.py`：

```python
"""场景自省地图工具 — 供 LLM function calling 调用"""

from typing import Optional
from models import SceneSelfMap
from database import SessionLocal
from utils import make_id


def do_self_map_declare(
    scene_id: str,
    title: str,
    tree: list,
    diagrams: Optional[dict] = None,
) -> dict:
    """声明/覆盖场景自省图"""
    db = SessionLocal()
    try:
        existing = db.query(SceneSelfMap).filter(
            SceneSelfMap.scene_id == scene_id
        ).first()
        if existing:
            existing.title = title
            existing.tree = tree
            existing.diagrams = diagrams or {}
        else:
            sm = SceneSelfMap(
                id=make_id("smp"),
                scene_id=scene_id,
                title=title,
                tree=tree,
                diagrams=diagrams or {},
            )
            db.add(sm)
        db.commit()
        return {"status": "ok", "title": title, "node_count": len(tree)}
    finally:
        db.close()


def do_self_map_update(
    scene_id: str,
    action: str,
    parent_id: Optional[str] = None,
    node: Optional[dict] = None,
    node_id: Optional[str] = None,
    diagram_node_id: Optional[str] = None,
    diagram: Optional[dict] = None,
    title: Optional[str] = None,
) -> dict:
    """增量更新场景自省图"""
    db = SessionLocal()
    try:
        sm = db.query(SceneSelfMap).filter(
            SceneSelfMap.scene_id == scene_id
        ).first()
        if not sm:
            return {"status": "error", "message": "自省图尚未初始化，请先调用 self_map_declare"}

        if action == "update_title" and title:
            sm.title = title
        elif action == "add_node" and node:
            sm.tree = _add_node(sm.tree, node, parent_id)
        elif action == "update_node" and node:
            sm.tree = _update_node(sm.tree, node)
        elif action == "remove_node" and node_id:
            sm.tree = _remove_node(sm.tree, node_id)
            sm.diagrams.pop(node_id, None)
        elif action == "add_diagram" and diagram_node_id and diagram:
            sm.diagrams[diagram_node_id] = diagram
        elif action == "remove_diagram" and diagram_node_id:
            sm.diagrams.pop(diagram_node_id, None)

        db.commit()
        return {"status": "ok", "title": sm.title, "node_count": len(sm.tree)}
    finally:
        db.close()


def _add_node(tree: list, node: dict, parent_id: Optional[str]) -> list:
    if not parent_id:
        return tree + [node]
    for item in tree:
        if item["id"] == parent_id:
            item.setdefault("children", []).append(node)
            return tree
        if "children" in item:
            _add_node(item["children"], node, parent_id)
    return tree


def _update_node(tree: list, node: dict) -> list:
    for i, item in enumerate(tree):
        if item["id"] == node["id"]:
            tree[i] = {**item, **node}
            return tree
        if "children" in item:
            _update_node(item["children"], node)
    return tree


def _remove_node(tree: list, node_id: str) -> list:
    return [item for item in tree if item["id"] != node_id and
            ("children" not in item or item.pop("children", None) or True)]
```

---

## 5. 前端改动

### 5.1 SelfMapView.tsx — 数据源可注入

```typescript
interface SelfMapViewProps {
  onBack: () => void;
  // 新增：可选的数据源。不传则使用本体硬编码树
  sceneId?: string;
}
```

改动：

| 逻辑 | 改前 | 改后 |
|------|------|------|
| 数据来源 | 硬编码 `TREE_DATA` + `DIAGRAMS` | `sceneId` 时从 API `/api/scenes/{id}/self-map` 拉取 |
| 数据状态 | 常量 | `useState` + `useEffect` 异步加载 |
| 未创建时的表现 | N/A | 展示空状态提示「场景尚未声明自省地图，让分身在对话中描述架构即可自动生成」 |
| 渲染 | 完全同步 | 加载中展示 skeleton / 同风格 loading |

**数据流**：

```
SelfMapView mounted
  ├── sceneId? ──yes──→ fetch GET /api/scenes/{id}/self-map
  │                      ├── 200 → 用动态 tree + diagrams 渲染
  │                      └── 404 → 展示空状态 + 引导
  └── no sceneId ──→ 用硬编码 TREE_DATA + DIAGRAMS（本体模式，不动）
```

**渲染逻辑** 95% 复用：

| 子组件 | 复用度 | 说明 |
|--------|--------|------|
| TreeNodeItem | 100% | 树结构完全一致（id/icon/label/children/detail/hasDiagram） |
| DiagramView | 100% | 流程图渲染逻辑完全一致（节点/边/颜色/居中） |
| DetailDrawer | 100% | 详情面板完全一致 |
| 中间面板 | 100% | 布局、分隔条、搜索、拖拽 |
| API 客户端 | 新增 | `fetchSelfMap(sceneId)` / `getSceneSelfMapApiUrl(sceneId)` |

**最终组件签名**：

```typescript
export function SelfMapView({ onBack, sceneId }: SelfMapViewProps) {
  // 如果 sceneId 存在，从 API 拉动态数据
  // 否则用硬编码 TREE_DATA
}
```

### 5.2 场景入口（Sidebar / Scene 页面）

在场景侧边栏或场景详情页增加「自省地图」入口按钮。图标 🗺️，点击打开 SelfMapView 传入 `sceneId={当前场景id}`。

位置参考：场景标签页的「设置/开发工具/自省」操作入口。

### 5.3 前端 API 客户端

```typescript
// api/client.ts 新增
export async function fetchSceneSelfMap(sceneId: string): Promise<SceneSelfMapData | null> {
  try {
    const res = await fetch(`/api/scenes/${sceneId}/self-map`);
    if (res.status === 404) return null;
    return await res.json();
  } catch {
    return null;
  }
}
```

---

## 6. 渲染引擎复用分析

当前 SelfMapView 结构：

```
SelfMapView（三栏主布局）
├── 左栏：搜索栏 + 树（TreeNodeItem）
├── 中栏：图标题栏 + DiagramView
└── 右栏：DetailDrawer
```

**改动清单**（最小化）：

| 文件 | 改动 | 行数估计 |
|------|------|---------|
| `frontend/src/components/SelfMapView.tsx` | 新增 `sceneId` prop + 异步数据加载 | +~30 行 |
| `frontend/src/api/client.ts` | 新增 `fetchSceneSelfMap()` | +~15 行 |
| `backend/models.py` | 追加 `SceneSelfMap` 表 | +~30 行 |
| `backend/router/scene_self_map.py` | 新路由文件，3 个端点 | +~80 行 |
| `backend/router/__init__.py` | 注册新路由 | +2 行 |
| `tools/self_map_tool.py` | 2 个工具执行函数 | +~120 行 |
| `tools/registry.json` | 注册 2 个 function calling 工具 | +~100 行 |

**总计新增 ~380 行，改动 7 个文件，零重构。**

---

## 7. 场景入口设计（Sidebar / 场景内操作）

方案 A（推荐）：**场景详情面板内入口**

在场景点击后展开的详情/标签栏中，新增「🗺️ 自省」标签或按钮。点击即打开 SelfMapView 传入 sceneId。

- 位置：和场景设置、编辑等操作同级
- 视觉：小图标 🗺️ + 文字「架构图」
- 行为：覆盖全屏（fixed overlay，同本体自省图）

方案 B（备选）：**侧边栏右键菜单**

在场景列表右键弹出「查看自省图」选项。发现性较低，不推荐。

---

## 8. 边界情况

| 情形 | 行为 |
|------|------|
| 场景从未调用过 `self_map_declare` | 展示空状态引导文案 |
| LLM 声明了欠完整的数据（无 diagrams） | 树正常渲染，选中 hasDiagram 节点但无图→展示「无流程图」提示 |
| LLM 声明了 3 层以上节点 | 后端不限制，前端渲染深度限制为 3 层（多余的隐藏） |
| 场景被删除 | 级联删（cascade），关联清理清单补充 `SceneSelfMap` |
| 用户手动编辑场景自省图 | 暂不支持；后续可考虑「UI 编辑模式」Phase 2 |
| 本体自省图（花园版） | **完全不受影响**——不传 sceneId 时走全量硬编码 |

---

## 9. 实施步骤

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1 | `models.py` 追加 `SceneSelfMap` 表 | 无 |
| 2 | `router/scene_self_map.py` 新增 3 个 API 端点 | Step 1 |
| 3 | `router/__init__.py` 注册新路由 | Step 2 |
| 4 | `tools/self_map_tool.py` 写 2 个工具执行函数 | Step 1 |
| 5 | `tools/registry.json` 注册 2 个工具 | Step 4 |
| 6 | `frontend/src/api/client.ts` 新增 `fetchSceneSelfMap()` | 无 |
| 7 | `SelfMapView.tsx`：新增 `sceneId` prop + 异步加载分支 | Step 6 |
| 8 | 场景内入口按钮（Sidebar/场景详情） | Step 7 |

Step 1-3 可以并行，Step 4-5 可并行，Step 6-7 需等 API 确定。

---

## 10. 未来 Phase 设想（不做，仅备忘）

- **UI 编辑模式**：右键拖拽、增删节点，类似 mindmap 编辑器
- **自省快照**：每次 `self_map_declare` 保留历史版本，支持回溯
- **自动提取**：从场景的设计文档自动提取架构骨架作为初始图
- **联动收敛**：自省图节点变更自动触发 Thinking Map 的收敛/发散关联

---

## 附录：数据结构对比

| 维度 | 本体自省图（硬编码） | 场景自省图（API） |
|------|--------------------|------------------|
| 数据定义 | 常量 `TREE_DATA` + `DIAGRAMS` | 从 `GET /api/scenes/{id}/self-map` 拉取 |
| 更新方式 | 改源代码 | LLM 调 `self_map_declare` / `self_map_update` |
| 持久性 | 编译到 JS 包 | 存 DB，跨重启保持 |
| 定制度 | 固定不可变 | 每个场景独立 |
| 渲染组件 | SelfMapView | **同一组件** |
