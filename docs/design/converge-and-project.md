# 收敛机制与项目认知 — Schema v0.81

> 最终定稿 — 2026-05-20
>
> 核心设计：收敛由系统按轮数 + 量化规则自动触发，异步执行不干扰分身工作。
> 收敛的结果带回项目认知，LLM 在执行阶段知道自己正在做什么项目。

---

## 一、问题回顾

### 1.1 现有 converge 为什么从不触发

| 原因 | 说明 |
|------|------|
| LLM 不知道何时收敛 | converge 工具让 LLM 在「讨论充分后」自主调用，但对执行型任务 LLM 不觉得自己在「讨论」 |
| 没有自动触发机制 | diverge 有 auto-diverge（首次消息），converge 全凭 LLM 自觉 |
| 收敛与后续无关 | 收敛结果只有 PQ，LLM 后续写文件时毫无关联 |

### 1.2 核心认知转变

- **收敛不是一次性的**，可以多次渐进。每收敛一次，对全局认知更清晰一次
- **收敛结果带回项目认知**，LLM 知道自己在做什么项目
- **收敛不是 LLM 自主决策**，而是系统按规则自动判定

---

## 二、触发规则

### 2.1 基础轮数门槛

关键规则：**闲聊频道不计轮数；分身的闲聊内容也不计入**

| 分身回复次数 | 事件 |
|-------------|------|
| 第 1 ~ N-1 轮 | 纯聊天，不建树 |
| 第 N 轮（默认 2） | auto-diverge → 开始建思维导图 |
| 第 N+1 轮起（默认 3） | 每次回复后异步检查收敛条件 |

轮数统计方式：`SELECT COUNT(*) FROM messages WHERE scene_id = ? AND role = 'ai'`
- 仅统计该场景中的 AI 回复
- 闲聊频道直接跳过，不触发任何发散/收敛逻辑

### 2.2 收敛阈值规则

对每一层 domain 独立检查：

```
该层叶子数 >= 该层分支数 × 阈值
    条件满足 → 自动触发该层的收敛
```

- **叶子（leaf）**：没有任何子节点的节点
- **分支（branch）**：至少有一个子节点的非根节点
- **阈值（threshold）**：默认为 `2.0`（2 倍），每个场景可独立调节

### 2.3 多层 domain 的收敛逻辑

每层 domain 独立计算，互不干扰：

```
root
├── domain A1               → layer 1 分支: A1, C1 = 2
│   ├── domain A1-1         → layer 2 分支: A1-1, A1-2 = 2
│   │   ├── leaf 1
│   │   └── leaf 2          → layer 2 叶子: 1,2,3,4 = 4
│   └── domain A1-2         → layer 2: 4 >= 2×2=4 → 触发 layer 2 收敛
│       ├── leaf 3
│       └── leaf 4
├── domain B1
│   ├── leaf 5
│   └── leaf 6
└── domain C1               → layer 1 叶子: 5,6 = 2
                            → layer 1: 2 >= 2×2=4 → 不触发，继续发散
```

### 2.4 收敛后的演进

首次收敛后，分身继续回复/发散。当新叶子数再次满足条件时，再次触发收敛。

```
收敛 → 继续发散 → 再次满足条件 → 再次收敛 → ...
```

每次收敛是对当前认知的**更新**——新的合并、新的废弃、新的项目结构。

---

## 三、异步收敛工作流

### 3.1 分身回复的完整流程

```
分身一次回复的 SSE 流：
  ① Agent Loop 执行（LLM 调工具）
  ② 保存 AI 消息到 DB
  ③ 检测 HTML 产出（方式 A/B/C）
  ④ 同步的 auto-diverge（轮数达到 N 时触发）
  ⑤ 发 done 事件 → 前端展示回复

👇 分身回复结束

  ── 后台异步线程（不阻塞 SSE 流） ──
  ⑥ 检查当前场景的 AI 回复轮数
  ⑦ 轮数不够 N？→ 跳过
  ⑧ 轮数 >= N 且未建树？→ auto-diverge
  ⑨ 轮数 >= N+1？→ 检查叶子/分支比
  ⑩ 满足条件？→ auto_converge_and_prioritize
  ⑪ 检测到项目？→ 创建 OutputProject
  ⑫ 结果写入 DB → 前端下次轮询可见
```

### 3.2 异步实现

不使用 Celery 等重量级框架，直接用 Python `threading.Thread` 或在 FastAPI 响应返回后启动后台任务。

```python
def start_async_converge_check(scene_id: str):
    """在后台线程中检查并发起收敛"""
    thread = threading.Thread(
        target=_async_converge_worker,
        args=(scene_id,),
        daemon=True,
    )
    thread.start()

def _async_converge_worker(scene_id: str):
    """后台收敛检查 worker"""
    db = SessionLocal()
    try:
        # 1. 检查轮数
        round_count = db.query(Message).filter(
            Message.scene_id == scene_id,
            Message.role == "ai",
        ).count()
        # ... 检查条件、触发发散/收敛
    finally:
        db.close()
```

### 3.3 并发安全

- `auto_converge_and_prioritize` 操作在单个 DB session 内，SQLite 写锁会串行化
- 同一场景不会同时跑两个收敛线程（加锁或标志位保护）
- 收敛冷却期：同一场景两次收敛间隔至少 10 秒

---

## 四、数据模型变更

### 4.1 scenes 表加字段（ALTER TABLE，安全）

```python
# models.py — Scene 类新增
converge_threshold   = Column(Float, default=2.0)   # 收敛阈值
converge_enabled     = Column(Boolean, default=True) # 是否启用自动收敛
diverge_min_rounds   = Column(Integer, default=2)    # 发散建树所需最少 AI 回复轮数
```

### 4.2 新增 output_projects 表（CREATE TABLE，安全）

```python
class OutputProject(Base):
    """项目——一组相关产出的容器"""
    __tablename__ = "output_projects"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    converged_at = Column(DateTime, default=utcnow)
    is_active = Column(Boolean, default=True)
```

### 4.3 project_outputs 加 project_id（ALTER TABLE，安全）

```sql
ALTER TABLE project_outputs ADD COLUMN project_id VARCHAR REFERENCES output_projects(id);
```

### 4.4 Schemas 变更

```python
# SceneUpdate 新增字段
converge_threshold: Optional[float] = None
converge_enabled: Optional[bool] = None
diverge_min_rounds: Optional[int] = None

# SceneOut 新增字段（只读，供前端展示）
converge_threshold: float = 2.0
converge_enabled: bool = True
diverge_min_rounds: int = 2

# 新增 OutputProjectOut
class OutputProjectOut(BaseModel):
    id: str
    scene_id: str
    name: str
    description: str
    converged_at: str
    outputs: List[OutputOut] = []
    is_active: bool
```

---

## 五、多层 domain 的树构建

### 5.1 当前问题

**① diverge 输入仅用单条消息**
```python
d_ctx = data.content[:500]  # ← 只用了用户刚发的这一条
```
auto-diverge 只拿最新一条消息拆节点，完全没有利用全量场景对话历史和背景设定。导致拆解不充分，节点又粗又浅。

**② diverge 仅在首次消息触发一次**
`is_first_msg` 判断后永远不再 auto-diverge，后续全靠 LLM 自觉调工具。

**③ LLM prompt 固定输出两层**
```json
{"categories": [{"label": "类别", "nodes": [{"label": "子任务"}]}]}
```
一旦节点被标记为 `type=leaf`，后续 LLM 调 `diverge` 工具也只能在其下加 sibling leaf，不会自动升级为 domain。

### 5.2 改造方案

**① auto-diverge 触发时机改建树而非首条消息**
- 在异步收敛检查线程中处理（不是 SSE 流内同步执行）
- 条件：场景中 AI 回复轮数 >= diverge_min_rounds，且当前没有活跃的 Thinking Map 节点
- 建树完毕后同样触发一次收敛检查

**② diverge 输入传全量场景上下文**
```python
# 不再是 data.content[:500]
d_ctx = build_diverge_context(db, scene_id)
# 包含：
#   - 场景名称 + 背景设定 (user_context)
#   - 最近 N 条对话摘要（用户 + AI）
#   - 用户当前这条消息
```

**③ auto-diverge LLM prompt** — 支持递归任意深度：

```
"输出 JSON 树形结构：{\"tree\": [{\"label\": \"根分类\", \"children\": [{\"label\": \"子分类\", \"children\": [{\"label\": \"最细项\"}]}]}]}"
```

解析时按深度自动分配 type：
- 没有 children 的节点 → `type=leaf`
- 有 children 的节点 → `type=domain`（不论深度）

**② diverge 工具** — 给 leaf 加子节点时，自动将其 type 从 `leaf` 升级为 `domain`

```python
if parent_node.type == "leaf" and children:
    parent_node.type = "domain"  # 自动升级
```

**③ 系统 prompt** — 告知 LLM 可以构建多层树结构

---

## 六、系统 Prompt 更新

在 `context_builder.py` 的 `build_agent_context()` 中，更新收敛相关部分：

```
## 🏗️ 复杂任务处理

当任务需要拆解时，系统会自动帮你建思维导图。
你不必刻意想"什么时候该发散/收敛"，按正常流程聊天即可。

### 思维导图能力
- 你可以调 diverge 工具添加节点，domain 下可继续加 domain（多层树）
- 给已有节点添加子节点时，该节点自动升级为 domain
- 系统在后台监测树的生长，条件满足时自动收敛

### 项目认知
- 收敛完成后，你可能会看到一个项目信息（project_id、名称、结构）
- 之后产出的 HTML 文件自动归入该项目
- 项目信息在工具结果中返回，你不需要自己维护
```

---

## 七、前端参数调节入口

### 7.1 位置

`AgentLoopDashboard.tsx` → `LoopDiagram` 组件 → 右侧 [⚙ 调整参数] 按钮

### 7.2 参数面板

| 参数 | 控件 | 默认 | 说明 |
|------|------|------|------|
| 发散建树轮数 | 滑块 | 2 | 分身回复 N 轮后才开始建思维导图 |
| 收敛检查轮数 | 滑块 | 3 | 建树后再过多少轮开始检查收敛 |
| 收敛阈值 | 滑块 | 2.0 | 叶子数 >= 分支数 × 此值 → 触发收敛 |
| 自动收敛 | 开关 | 开 | 是否启用自动收敛监测 |

### 7.3 API

```http
PATCH /api/scenes/{scene_id}
{
  "diverge_min_rounds": 2,
  "converge_threshold": 2.5,
  "converge_enabled": true
}
```

前端轮询场景信息时就已包含这些参数，无需额外接口。

---

## 八、Converge Engine 改造

### 8.1 收敛时创建项目

`auto_converge_and_prioritize` 的 LLM 分析中增加 project 字段：

```json
{
  "merges": [...],
  "discarded_ids": [...],
  "queue": [...],
  "project": {
    "is_project": true,
    "name": "三国时间线",
    "description": "三国历史交互式时间线，含6个独立页面",
    "structure": [
      {"sub": "首页", "desc": "导航与概览"},
      {"sub": "魏国篇", "desc": "曹操及魏国历史"},
      {"sub": "蜀汉篇", "desc": "刘备及蜀汉历史"}
    ]
  }
}
```

当 `project.is_project = true` 时，后端自动：
1. 在 `output_projects` 表创建记录
2. 将场景已有和未来的 `ProjectOutput` 关联到此项目
3. 前端下次轮询时可看到分组好的产出

### 8.2 多次收敛更新项目

第二次及后续收敛时：
- 该场景已有活跃 OutputProject → 更新 name/description
- 或标记旧项目为 `is_active = false`，创建新项目

---

## 九、API 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/projects` | GET | 列出项目（可 scene_id 过滤） |
| `/api/projects` | POST | 手动创建项目 |
| `/api/projects/{id}` | PATCH | 更新项目信息 |
| `/api/projects/{id}` | DELETE | 删除项目（级联取消 output 关联） |
| `/api/projects/{id}/outputs` | GET | 项目下的所有产出 |
| `/api/scenes/{id}/converge-status` | GET | 获取场景的收敛状态（轮数、是否已建树、是否已收敛） |

---

## 十、闲聊频道排除逻辑

```python
def should_process_scene_tasks(scene: Scene) -> bool:
    """判断该场景是否需要发散/收敛处理"""
    # 闲聊频道不进行处理
    if scene.scene_name == "闲聊" or "闲聊" in scene.name or "chat" in scene.name.lower():
        return False
    return True
```

轮数统计排除条件：
- 场景名为「闲聊」
- 消息内容属于纯闲聊（由 LLM 判断，暂不实现，后续可考虑）

---

## 十一、变更清单

| 层面 | 变更 | 影响 |
|------|------|------|
| models.py | Scene 加 `converge_threshold`, `converge_enabled`, `diverge_min_rounds` | ALTER TABLE ADD COLUMN，安全 |
| models.py | 新增 `OutputProject` 表 | CREATE TABLE，安全 |
| models.py | `ProjectOutput` 加 `project_id` | ALTER TABLE ADD COLUMN，安全 |
| schemas.py | `SceneUpdate`/`SceneOut` 加新字段 | 向后兼容 |
| schemas.py | 新增 `OutputProjectOut` | 纯新增 |
| converge_engine.py | CONVERGE_SYSTEM_PROMPT 加 `project` 字段 | 向后兼容 |
| converge_engine.py | `auto_converge_and_prioritize` 加 `target_layers` 参数 | 接口变更 |
| converge_engine.py | 收敛结果写 `output_projects` 表 | 新增逻辑 |
| diverge_tool.py | 给 leaf 加子节点时自动升级为 domain | 行为增强 |
| diverge_tool.py | 返回后触发异步收敛检查 | 行为增强 |
| scenes.py | auto-diverge LLM prompt 支持递归多层 | prompt 变更 |
| scenes.py | auto-diverge 改为按轮数触发（非首次消息） | 触发条件变更 |
| scenes.py | SSE done 后启动异步收敛线程 | 新增逻辑 |
| scenes.py | update_scene 处理新字段 | 向后兼容 |
| context_builder.py | 更新系统 prompt 文案 | 无破坏 |
| AgentLoopDashboard.tsx | 参数面板 UI + 轮询 | 纯新增 |
| router/scenes.py | `/api/scenes/{id}/converge-status` | 纯新增 |
| router/outputs.py | `/api/projects` CRUD | 纯新增 |

---

## 十二、边界情况

| 场景 | 处理 |
|------|------|
| 闲聊场景 | 不计轮、不建树、不收敛。完全跳过。 |
| 纯执行型任务（无发散） | 轮数到 N 后 auto-diverge 建树；叶子不够多则不触发收敛 |
| 用户删除 project_outputs | 不影响 project，project 重新统计 |
| 删除场景 | cascade 删除关联所有数据 |
| 同一场景短时间内多次满足收敛 | 10 秒冷却期，防止频繁收敛 |
| 阈值调为 0 | 每次检查都收敛（极敏感） |
| 阈值调为极大 (≥10) | 自动收敛永不触发 |
| 发散轮数调为 1 | 第 1 轮回复就建树（类似现在行为） |
| 收敛轮数 = 发散轮数 + 1 | 建树的下一轮就开始检查 |
| 分身重启/场景重新加载 | 轮数通过 DB 记录重算，不丢失状态 |
