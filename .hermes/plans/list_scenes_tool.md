# list_scenes 工具 — 设计方案

## 背景

当前 `list_scenes` 是后端 API（`GET /api/scenes`），仅供 Web 前端调用。LLM Agent 在自开发场景中无法直接获取场景列表。需要一个 Agent 可直接调用的工具函数，让 LLM 能查询所有场景信息。

## 设计目标

- 为 LLM Agent 提供 `list_scenes` 工具，可查询所有场景列表
- 支持可选过滤（按状态、按分类）
- 返回结构化 JSON，包含场景关键字段
- 参照 `tools/git_tool.py` 的模式：Schema 定义 + 函数实现 + 注册到 registry.json

## 架构方案

```
tools/scene_tool.py     ← 新文件，包含 list_scenes 实现
tools/registry.json     ← 追加 list_scenes 注册条目
```

## 组件划分

### 组件：tools/scene_tool.py
- 职责：提供 `list_scenes` 函数，查询数据库返回场景列表
- 接口函数：`list_scenes(status: str = "", category: str = "") -> str`
- 返回 JSON：包含场景列表，每个场景含 id/name/icon/description/category/version/pinned/created_at/updated_at

### 组件：registry.json 注册
- 追加一个工具条目，name="list_scenes", file="tools/scene_tool.py", function="list_scenes"

## 数据流

1. LLM 调用 `list_scenes(status="", category="")`
2. scene_tool.py 连接 SQLite 数据库（`~/zuoshanke/backend/zuoshanke.db`）
3. 执行 `SELECT id, name, icon, description, category, version, pinned, created_at, updated_at FROM scenes ORDER BY pinned DESC, updated_at DESC`
4. 可选过滤：category 过滤、version 过滤（"0.0"=草稿, "!0.0"=已发布）
5. 返回 JSON 字符串

## 接口设计

```python
LIST_SCENES_SCHEMA = {
    "name": "list_scenes",
    "description": "列出所有场景，支持按分类和状态过滤",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "分类过滤（life/ecommerce/work/learn/create/finance/media/other）",
                "optional": True,
            },
            "status": {
                "type": "string",
                "description": "状态过滤：draft（草稿version=0.0）/ published（已发布version!=0.0）/ all（全部，默认）",
                "optional": True,
            },
        },
    },
}

def list_scenes(category: str = "", status: str = "all") -> str:
    """查询场景列表"""
    # 1. 连接数据库
    # 2. 构建查询 + 过滤
    # 3. 返回 JSON
```

## 存储设计

- 直接读取 `~/zuoshanke/backend/zuoshanke.db`（SQLite）
- 使用 sqlalchemy 或直接 sqlite3 连接
- 与后端共用同一个数据库文件，只读查询
