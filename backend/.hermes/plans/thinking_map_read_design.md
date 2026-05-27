# Thinking Map Read 工具 设计方案

## 背景
当前系统已有 `diverge`（发散）和 `converge`（收敛）两个思维导图工具，但缺少一个**只读查询**工具。AI Agent 在对话中需要能读取当前场景的思维导图节点信息，以便了解已有哪些节点、结构如何，从而做出更合理的发散/收敛决策。

## 设计目标
- 提供一个只读工具，查询当前场景的 Thinking Map 节点
- 支持按场景 ID 查询，也支持查看当前场景
- 返回结构化的节点树信息
- 参照 `tools/git_tool.py` 的实现模式

## 架构方案
新增一个工具模块 `tools/thinking_map_tool.py`，通过 HTTP 请求调用后端的 Thinking Map API（GET 接口），返回节点数据。

## 组件划分

### tools/thinking_map_tool.py
- 职责：实现 `thinking_map_read` 工具函数
- 调用后端 API `GET /api/scenes/{scene_id}/thinking-map` 获取思维导图数据
- 返回格式化后的节点信息

### registry.json 注册
- 将 `thinking_map_read` 注册到工具注册表中

## API 接口设计

### 后端接口（假设存在）
- `GET /api/scenes/{scene_id}/thinking-map`
- 返回：`{ "nodes": [...], "edges": [...] }`

### 工具函数签名
```python
def thinking_map_read(scene_id: str = None) -> dict:
    """
    读取当前场景的 Thinking Map 思维导图节点信息。
    
    Args:
        scene_id: 场景ID，不传则使用当前场景
    
    Returns:
        包含节点树信息的字典
    """
```

## 实现步骤
1. 创建 `tools/thinking_map_tool.py`，参照 `tools/git_tool.py` 的模式
2. 在 `registry.json` 中注册新工具
3. git commit
