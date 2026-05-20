# Schema v0.81 — 收敛机制与项目认知

> 版本: 0.81
> 日期: 2026-05-20
> 状态: 设计定稿，待实现
>
> 本 schema 定义了坐山客分身场景中自动发散→收敛→项目认知的完整工作流。
> 核心变更：收敛由系统按轮数 + 量化规则自动触发，异步执行不干扰分身。

---

## 一、权责模型

| 角色 | 职责 |
|------|------|
| 系统 | 监控 AI 回复轮数、叶子/分支比、自动触发发散/收敛 |
| 分身（LLM） | 正常聊天、调工具干活、diverge 建节点 |
| 用户 | 调参（轮数、阈值、开关） |

### 闲聊排除

闲聊频道（scene 名为「闲聊」或包含「chat」）不计轮数、不建树、不收敛。

---

## 二、触发规则

### 2.1 轮数门槛

```
分身 AI 回复轮数统计: SELECT COUNT(*) FROM messages WHERE scene_id=? AND role='ai'

 第 N 轮（默认 2）  → auto-diverge 建思维导图
 第 N+1 轮起（默认 3）→ 每次回复后检查收敛条件
```

### 2.2 收敛阈值规则

```
对每一层 domain 独立检查:
    该层叶子数 >= 该层分支数 × 阈值
    满足 → 自动触发该层收敛

 叶子: 无子节点的节点
 分支: 有子节点的非根节点
 阈值: 默认 2.0，每个场景独立可调
```

### 2.3 多次收敛

## 三、异步工作流

```
分身回复
  ① Agent Loop 执行
  ② 保存消息 + 检测 HTML
  ③ 同步 auto-diverge（轮数到 N）
  ④ SSE done

  ── 异步线程 ──
  ⑤ 检查轮数
  ⑥ 轮数 >= N 且未建树？→ diverge
  ⑦ 轮数 >= N+1？→ 检查叶子/分支比
  ⑧ 满足条件？→ auto_converge
  ⑨ 检测项目？→ 创建 OutputProject
  ⑩ 写入 DB → 前端轮询可见
```

---

## 四、新增表

### output_projects

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR PK | |
| scene_id | VARCHAR FK→scenes | |
| name | VARCHAR(200) | 项目名称 |
| description | TEXT | 项目描述 |
| converged_at | DATETIME | 收敛诞生时间 |
| is_active | BOOLEAN | 是否活跃 |

### project_outputs 加字段

| 字段 | 类型 | 说明 |
|------|------|------|
| project_id | VARCHAR FK→output_projects | 可为 NULL |

### scenes 加字段（ALTER TABLE）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| converge_threshold | Float | 2.0 | 收敛阈值 |
| converge_enabled | Boolean | true | 自动收敛开关 |
| diverge_min_rounds | Integer | 2 | 发散所需最少 AI 回复轮数 |

---

## 五、API

```
PATCH /api/scenes/{id}     → 调参（converge_threshold 等）
GET   /api/projects        → 列表（scene_id 过滤）
POST  /api/projects        → 手动创建
GET   /api/projects/{id}   → 详情
PATCH /api/projects/{id}   → 更新
DELETE /api/projects/{id}  → 删除
GET   /api/projects/{id}/outputs → 项目下的产出
GET   /api/scenes/{id}/converge-status → 收敛状态
```

---

## 六、前终端点

- 仪表盘 → 阶段循环图右侧 → [⚙ 调整参数] 弹出面板
- 三个滑块：发散轮数 / 收敛轮数 / 收敛阈值 + 自动收敛开关
- 产出视图按项目分组，前端轮询展示

---

## 七、设计约束

- 不发散、不创建 Thinking Map 的场景不进行收敛
- 收敛结果仅用于项目创建和产出分组，不干预分身行为
- auto-diverge 触发时传全量场景上下文（场景设定 + 对话摘要），非单条消息
- 所有新字段可用 `ALTER TABLE ADD COLUMN` 添加
- 新表通过 `Base.metadata.create_all()` 创建
