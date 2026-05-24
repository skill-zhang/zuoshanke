# 子Agent契约文件模板 — 方案设计

> 父Agent在派发多模块并行任务前，自动生成标准化的 `shared/INTERFACE.md`，作为子Agent之间唯一的共享上下文。

---

## 1. 动机

Phase 3 已实现三层 Context 注入（L1 任务层 → L2 契约层 → L3 项目层），`contract_path` 字段和 `_build_child_prompt` 均已就位。但存在一个**格式真空**：

- `seed_dev_scene.py` 指导父Agent「用 write_file 创建 shared/INTERFACE.md（API 端点 + 数据模型 + 模块边界）」
- 但没有定义 INTERFACE.md **长什么样** → 每次父Agent凭直觉写，结构不一致
- 子Agent读到的契约信息完整度取决于父Agent当天的心情
- 无法做自动化验证（没有已知格式就无法写契约合规检查）

**目标**：定义一个标准化的 INTERFACE.md 模板，父Agent一次调用即可自动生成，无需手写。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **一张纸** | 模板长度控制在 60-120 行，不超一屏，避免子Agent看不完 |
| **子Agent友好** | 每个子Agent只读自己相关的部分，模板按模块分节 |
| **免工具依赖** | 核心模板纯 Markdown，LLM 原生理解，无需特殊解析器 |
| **可扩展节** | 标准节必须存在，额外节可选（用 `> Optional` 标题标记） |
| **版本可追踪** | 契约首行有版本号，变更可 diff |

---

## 3. 标准化模板结构

```
# 接口契约 v1.0
> 自动生成于 {timestamp} | 由 {parent_agent} 创建

## 1. 项目概览

{一句话的项目目标}

## 2. 模块架构

| 模块 | 目录 | 职责 | 依赖模块 |
|------|------|------|----------|
| {模块A} | {路径} | {职责描述} | {依赖列表} |
| {模块B} | {路径} | {职责描述} | {依赖列表} |

## 3. 数据模型

### {模型名}
```json
{
  "字段名": "类型 | 说明",
  "{field}": "string | 用户的唯一标识",
  ...
}
```

### 数据库表（如适用）
| 表名 | 字段 | 类型 | 说明 |
|------|------|------|------|
| {table} | {field} | {type} | {desc} |

## 4. API 端点

| 方法 | 路径 | 请求体 | 响应体 | 所属模块 |
|------|------|--------|--------|----------|
| POST | /api/xxx | {请求结构} | {响应结构} | {模块} |

### 请求/响应示例
```json
// POST /api/xxx 请求
{...}
// 响应
{...}
```

## 5. 模块边界

### {模块A}
- **负责**: {具体职责清单}
- **不负责**: {明确排除项}
- **接口**: {暴露给其他模块的接口}
- **假定**: {对其他模块的依赖假设}

### {模块B}
- ...

## 6. 约定

- **命名**: {命名规范，如 snake_case}
- **错误处理**: {错误码规范/错误响应格式}
- **状态码**: {HTTP 状态码使用约定}
- **日志**: {日志配置}

## 7. 注意事项

- {特定于当前开发的陷阱/风险}
- {已知的边界情况}
```

---

## 4. 填充示例

以下是一个真实场景的填充版 INTERFACE.md，假设正在开发**「用户笔记」多模块功能**：

```markdown
# 接口契约 v1.0
> 自动生成于 2026-05-24T11:00:00 | 由 自我迭代场景 Avatar 创建

## 1. 项目概览

为用户笔记功能增加标签系统，支持标签 CRUD、笔记-标签关联、标签云展示。

## 2. 模块架构

| 模块 | 目录 | 职责 | 依赖模块 |
|------|------|------|----------|
| 后端API | backend/router/notes.py | 标签 CRUD 端点 | 无 |
| 数据层 | backend/models.py | Tag + NoteTag 表定义 | 无 |
| 前端列表 | frontend/src/components/TagList.tsx | 标签列表/标签云组件 | 后端API |
| 前端编辑 | frontend/src/components/NoteEditor.tsx | 笔记编辑器中标签选择器 | 后端API |

## 3. 数据模型

### Tag
```json
{
  "id": "string | UUID",
  "name": "string | 标签名，唯一，max 32",
  "color": "string | 十六进制色值，如 #ff6600",
  "created_at": "string | ISO 8601"
}
```

### 数据库表
| 表名 | 字段 | 类型 | 说明 |
|------|------|------|------|
| tags | id | TEXT PK | UUID |
| tags | name | TEXT UNIQUE NOT NULL | 标签名 |
| tags | color | TEXT DEFAULT '#888' | 色值 |
| tags | created_at | TEXT | ISO 时间戳 |
| note_tags | note_id | TEXT FK → notes.id | 笔记ID |
| note_tags | tag_id | TEXT FK → tags.id | 标签ID |
| note_tags | — | PRIMARY KEY (note_id, tag_id) | 联合主键 |

## 4. API 端点

| 方法 | 路径 | 请求体 | 响应体 | 所属模块 |
|------|------|--------|--------|----------|
| GET | /api/notes/{id}/tags | — | Tag[] | 后端API |
| POST | /api/notes/{id}/tags | {tag_ids: string[]} | Tag[] | 后端API |
| DELETE | /api/notes/{id}/tags/{tag_id} | — | — | 后端API |
| GET | /api/tags | ?q=搜索词 | Tag[] | 后端API |
| POST | /api/tags | {name, color?} | Tag | 后端API |
| DELETE | /api/tags/{id} | — | — | 后端API |

### POST /api/tags 请求
```json
{"name": "javascript", "color": "#f7df1e"}
```
### 响应
```json
{"id": "abc-123", "name": "javascript", "color": "#f7df1e", "created_at": "2026-05-24T11:00:00Z"}
```

## 5. 模块边界

### 后端API (backend/router/notes.py)
- **负责**: 接收 HTTP 请求 → 校验参数 → 调数据层 → 返回 JSON
- **不负责**: 数据库建表、数据迁移（由数据层负责）
- **假定**: Tag + NoteTag 表已存在

### 数据层 (backend/models.py)
- **负责**: Tag + NoteTag 表的 SQLAlchemy 模型定义、create_all
- **不负责**: HTTP 路由逻辑
- **接口**: 其他模块通过 SQLAlchemy session 直接操作模型

### 前端列表 (frontend/src/components/TagList.tsx)
- **负责**: 渲染标签列表 + 标签云 + 增删标签
- **不负责**: 标签与笔记的关联（由 NoteEditor 负责）
- **接口**: fetch(`/api/tags?q=...`) → Tag[]

## 6. 约定

- **命名**: Python snake_case, TypeScript camelCase（API JSON字段用 snake_case）
- **错误**: `{"error": string, "detail": string}`，HTTP 4xx/5xx
- **分页**: 列表接口支持 `?offset=0&limit=20`，返回 `{items: [], total: number}`
- **颜色值**: 统一 7 字符 hex（#rrggbb），前端不做转换

## 7. 注意事项

- `tag_ids` 中的 ID 如果不存在 → 返回 404 + 具体哪个 ID 缺失
- 删除 tag 时级联删除 note_tags 关联数据
- 标签名大小写不敏感，存时全小写
```

---

## 5. 生成策略

### 何时生成

父Agent在 `seed_dev_scene.py` 的**契约阶段**调 `write_file` 生成。触发条件：

1. 设计方案已确认（方案阶段完成）
2. 涉及 ≥2 个子Agent并行开发
3. 子Agent之间存在共享结构（数据库表/API端点/数据模型）

### 生成流程

```
父Agent确认方案
  ↓
父Agent根据设计方案，在脑中填充模板的 7 个章节
  ↓
父Agent调 write_file(path='shared/INTERFACE.md', content=填充好的契约)
  ↓
父Agent调 delegate_task(tasks=[
    {goal: '实现后端', contract_path: 'shared/INTERFACE.md'},
    {goal: '实现前端', contract_path: 'shared/INTERFACE.md'},
  ])
  ↓
子Agent通过 L2 Context 拿到契约文件路径 → 读文件 → 按契约实现
```

### 不需要专用工具

当前的 `seed_dev_scene.py` 指引 + `write_file` 工具已经够用。**不新增专用工具**，理由：
- 父Agent（LLM）自然能理解模板格式并按需填充
- 新增工具 = 多一个注册 + 维护点，收益不大
- 模板本身就足够标准化，父Agent按模板写不会走样

> ⚠️ 如果未来出现以下情况，可考虑新增 `generate_contract` 工具：
> - 父Agent频繁产出格式不完整的契约
> - 需要从设计方案自动提取模块/端点信息
> - 需要契约合规自动校验

---

## 6. 版本管理

| 场景 | 做法 |
|------|------|
| **初始生成** | `# 接口契约 v1.0` |
| **非破坏性变更**（加字段、加端点） | `v1.1` — 子Agent兼容，不需通知 |
| **破坏性变更**（改字段名、删端点） | `v2.0` — 必须终止已有子Agent并发起新任务 |
| **并行子Agent发现矛盾** | 父Agent看到子Agent中间结果时发现 → 更新契约 + 重新调度受影响的子Agent |

版本变更记录建议放在文件尾（可选节）：

```markdown
## 8. 变更记录
- v1.0 (2026-05-24): 初始版本
- v1.1 (2026-05-25): 新增 GET /api/tags/stats 端点
- v2.0 (2026-05-26): tag_id 字段类型从 int 改为 UUID
```

---

## 7. 模板正式定义（供 seed_dev_scene 引用）

将此模板的浓缩版嵌入 `seed_dev_scene.py` 的契约阶段指引中，作为父Agent写契约时的参考骨架：

```python
CONTRACT_TEMPLATE_SKELETON = """
# 接口契约 v1.0

## 1. 项目概览
{一句话目标}

## 2. 模块架构
| 模块 | 目录 | 职责 | 依赖 |

## 3. 数据模型
### {模型}
{JSON schema 或 数据库表定义}

## 4. API 端点
| 方法 | 路径 | 请求体 | 响应体 | 所属模块 |

## 5. 模块边界
### {模块}
- **负责**: ...
- **不负责**: ...
- **假定**: ...

## 6. 约定
{命名/错误处理/状态码}

## 7. 注意事项
{已知陷阱}
"""
```

---

## 8. 文件改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `docs/design/contract-template.md` | **🆕 新增** — 本文 | ~200 |
| `scripts/seed_dev_scene.py` | 在契约阶段指引中嵌入 `CONTRACT_TEMPLATE_SKELETON` 参考 | ~30 |

**合计新增 ~230 行，零重构。**

---

## 9. 验证

| 验证项 | 方法 |
|--------|------|
| 父Agent能产出标准契约 | 在自我迭代场景口头提需求，观察是否生成格式正确的 INTERFACE.md |
| 子Agent能正确理解 | 派 delegate_task 后检查子Agent的 `_build_child_prompt` 输出是否包含契约引用 |
| 模板完整性 | 手动检查生成的 INTERFACE.md 是否包含全部 7 个标准节 |
