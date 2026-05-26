# 坐山客用户画像设计方案 v4 — LLM 判重 + 分层注入

> 2026-05-26

## 一、核心理念

本体和分身各司其职，不越界：

```
分身：发现用户偏好 → 提交原始描述到暂存区（只提取，不存正式库）
本体：定期从暂存区取出 → 去重 → 合并相似 → 审核 → 写入正式用户画像库
```

**分身不直接写用户画像**，跟「分身不能写 scope='zhu'」的现有规则一致。

## 二、数据模型

### 2.1 暂存区：`pending_user_traits` 表

分身提交的原始「生料」：

```python
class PendingUserTrait(Base):
    """分身提取的用户偏好——暂存区，待本体批量处理"""
    __tablename__ = "pending_user_traits"

    id = Column(String(32), primary_key=True)
    content = Column(Text, nullable=False)           # 分身提取的描述
    source_scene = Column(String(100))                # 来源场景名称
    source_scene_id = Column(String(32))              # 来源场景 ID
    confidence = Column(String(10), default="medium")  # high / medium / low
    context_snippet = Column(Text, nullable=True)      # 触发这条提取的对话片段（前3句）
    status = Column(String(10), default="pending")     # pending / merged / rejected
    merged_into = Column(String(64), nullable=True)    # 合入哪条正式画像的 key
    created_at = Column(DateTime, default=utcnow)
```

### 2.2 正式区：`user_profiles` 表

本体处理后入库的正式画像：

```python
class UserProfile(Base):
    """用户画像——正式库，经本体去重合并后的准确偏好"""
    __tablename__ = "user_profiles"

    id = Column(String(32), primary_key=True)
    key = Column(String(64), unique=True, index=True)   # 唯一标识
    content = Column(Text, nullable=False)               # 画像内容
    category = Column(String(20), default="preference")  # principle(原则) / preference(偏好) / habit(习惯) / context(临时)
    priority = Column(String(4), default="P2")           # P0/P1/P2/P3
    tags = Column(JSON, default=list)                    # 标签
    source_scenes = Column(JSON, default=list)            # 来源场景列表（来自多个分身）
    merged_from = Column(JSON, default=list)              # 从哪些 pending 条目合并而来
    is_active = Column(Boolean, default=True)             # 软删
    deprecated_by = Column(String(64), nullable=True)     # 被替代
    correction_trail = Column(JSON, default=list)         # 修正历史 [{old, reason, timestamp}]
    total_injections = Column(Integer, default=0)
    last_injected_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow)
```

### 2.3 关联关系

```
pending_user_traits                          user_profiles
┌────────────────────┐                    ┌──────────────────┐
│ content="不喜欢弹窗"│  ──合并──→        │ content="界面偏好:│
│ source_scene="二手车"│  (多条合一条)      │  不喜欢弹窗，    │
│ status=merged     │                    │  偏好极简交互"   │
│ merged_into="xxx"  │                    │ source_scenes=[  │
├────────────────────┤                    │   "二手车",      │
│ content="讨厌弹出窗"│                    │   "软件项目"     │
│ source_scene="项目" │  ──合并──→        │ ]               │
│ status=merged     │                    │ merged_from=[   │
└────────────────────┘                    │   "pending-1",  │
                                          │   "pending-2"   │
                                          │ ]               │
                                          │ priority="P2"   │
                                          └──────────────────┘
```

## 三、流程

### 3.1 分身提取（提取层）

场景分身聊天时，LLM 识别到用户偏好 → 调工具提交到暂存区：

```
你：我不喜欢弹窗，烦人
分身：明白了，以后不做弹窗交互。
     （同时内部调 pending_extract(content="用户不喜欢弹窗", confidence="high")）
     → pending_user_traits 表新增一条，status="pending"
```

```python
def pending_extract(content: str, confidence: str = "medium") -> str:
    """
    分身提取用户偏好，提交到暂存区。
    不直接写入用户画像，不触发 context 注入。
    """
```

**分身不需要管去重、合并、优先级。** 它只管提取和提交。

### 3.2 本体处理（沉淀层 — 全自动，用户无感）

本体后台自动处理暂存区，用户不需要手动触发。

**触发条件（双重保障，任一满足即执行）：**

- **条目数阈值**：暂存区 `status="pending"` 的条目 ≥ 5 条
- **时间窗口**：距离上次处理 ≥ 30 分钟
- 两个条件在 `idle_extractor` 的 60 秒循环中检查

**处理逻辑：**

```
1. 取所有 status="pending" 的条目，打包发送给 LLM
2. LLM 自行判断哪些重复/相似/无关，返回合并方案（JSON 格式）
3. 按 LLM 返回的方案执行：
   - 同类合并 → 一条正式画像，confidence 取最高，content 取最完整描述
   - 独立保留 → 直接入库（1 条 pending → 1 条 profile）
   - 无关/噪音 → 标记 rejected 或直接丢弃
4. 合并/入库完成后，从暂存区**彻底删除**已处理的条目（不是标记 status）
5. 处理结果写入 user_profiles 表后，下次场景 context 构建时自动包含新画像

**判重方式：** 不依赖向量库 / Embedding / 相似度算法。LLM 对自然语言的语义理解足以判断
"喜欢简洁界面" ≈ "热爱极简设计" ≠ "代码审查严格"。
```

**关键：用户全程无感知。** 分身提取 → 后台自动处理 → 分身下一次对话自动看到更新的用户画像。不需要用户打开 SettingsView 确认，不需要弹气泡问「这条对吗」。

### 3.3 处理后的清理

已处理的 pending 条目**标记为 merged/rejected 状态**（不物理删除），保留审计追踪：

```python
# 处理完成后
processed_ids = [t.id for group in merged_groups for t in group]
db.query(PendingUserTrait).filter(
    PendingUserTrait.id.in_(processed_ids)
).update({"status": "merged"}, synchronize_session=False)
db.commit()
```

理由：保留已合并的记录作为审计追踪。暂存区只标记状态，不影响下次扫描（查询时只取 `status="pending"` 的条目）。如日后需要清理历史数据，可单独写清理脚本。

### 3.4 注入（消费层 — 第 8 层，插在 Memory 之后、Config 之前）

在 `context_composer.py` 中新增第 8 层 `_build_profile_layer()`，插入位置：

```
1. Prompt Layer       (system)   ← 角色+工具+指令
2. Memory Layer       (user)     ← 持久记忆（原始、不确定）
3. Profile Layer      (user)     ← 正式画像（结构化、高置信度） ← 🆕 插在这
4. Config Layer       (user)     ← 当前配置
5. Document Layer     (user)     ← 参考文档
6. Skill Layer        (user)     ← 技能
7. History Layer                 ← 对话历史
8. Work Output Layer  (user)     ← 最近操作
```

**顺序不能错的原因：** Memory Layer 是碎片化的原始记忆（可能过时），Profile Layer 是本体审核过的结构化画像。LLM 先读记忆碎片再看整合画像，形成「碎片→全景」的认知递进，不会混淆两个来源的置信度差异。

注入时按优先级分两组：

```
─────────────────────────────────
👤 用户画像（你正在跟这样的用户对话）
─────────────────────────────────
【P0 原则】
- 先讨论形成设计文档再动手
- 验收要实机测试拿数据说话
─────────────────────────────────
【P1 偏好】
- 不喜欢弹窗交互
- 偏好极简表单
─────────────────────────────────
（P2 按话题匹配后选择性注入）
```

- P0 + P1 **始终注入**（核心特征，不多）
- P2 **按话题匹配**（仅当前对话话题相关时才注入，控制 token 开销）

## 四、去重策略

分身各自提交，很可能出现「同一个偏好不同分身都记了」。

### 4.1 暂存区去重（写入时）

分身提交 `pending_extract()` 时，做**轻量精确匹配**（不做语义判断，那留给 LLM 批量处理）：

```python
# 仅做精确去重（避免同一场景反复提交「一模一样」的内容）
exact_dupe = db.query(PendingUserTrait).filter(
    PendingUserTrait.status == "pending",
    PendingUserTrait.content == new_content,
).first()

if exact_dupe:
    return {"deduped": True, "merged_into": exact_dupe.id}
```

至于「意思相同但措辞不同」的语义去重，**不需要在写入时处理**——LLM 批量处理时会统一判断。

### 4.2 正式库去重（本体处理时 — LLM 批量判重）

idle extractor 触发时，将暂存区所有 pending 条目打包发给 LLM，附上当前正式库中的活跃画像。LLM 自行判断去重和合并：

```json
// LLM 返回示例
{
  "merged_groups": [
    {
      "pending_ids": ["pt-001", "pt-003"],
      "action": "merge",
      "reason": "两条都说的是界面偏好，一模一样",
      "content": "不喜欢弹窗，偏好极简交互",
      "category": "preference",
      "priority": "P1",
      "extra_rows": []
    },
    {
      "pending_ids": ["pt-005"],
      "action": "new_profile",
      "reason": "独立发现，暂存区唯一，正式库无匹配",
      "content": "代码审查要求严格",
      "category": "principle",
      "priority": "P2",
      "extra_rows": []
    },
    {
      "pending_ids": ["pt-002"],
      "action": "merge_into_existing",
      "reason": "与正式库已有画像重复",
      "existing_key": "design-philosophy-document-first",
      "extra_rows": []
    },
    {
      "pending_ids": ["pt-004"],
      "action": "discard",
      "reason": "纯闲聊感慨，不能算是用户偏好",
      "extra_rows": []
    }
  ]
}
```

| 情况 | LLM 的处理 |
|------|-----------|
| 多条 pending 说同一件事 | `merge` → 合为一条，confidence 取最高 |
| 单条 pending，正式库无匹配 | `new_profile` → 直接入库 |
| pending 与正式库已有画像重复 | `merge_into_existing` → 追加 source_scene |
| 噪音/闲聊感慨 | `discard` → 直接丢弃 |

**优势：** 零外部依赖、语义理解准确、可处理复杂关系（矛盾检测、版本进化）。

### 4.3 版本进化

用户偏好会变：
1. 分身提交了新版本（「最近喜欢亮色了」）
2. 本体处理时对比旧版
3. 旧版 `deprecated_by=<new_key>`
4. 新版 `priority + 1`（更新的信息权重更高）

## 五、API 端点

```http
# 分身调用（提取层）
POST /api/user-profile/pending
  body: {content, confidence, source_scene, source_scene_id, context_snippet?}

# 本体/用户调用（沉淀层）
GET  /api/user-profile/pending           → 列出待处理条目
POST /api/user-profile/pending/process   → 触发批量处理（去重+合并+入库）
POST /api/user-profile/pending/{id}/accept   → 用户逐条确认
POST /api/user-profile/pending/{id}/reject   → 用户拒绝

# 前端
GET    /api/user-profile                 → 按优先级分组列出
GET    /api/user-profile/{key}           → 单条详情（含修正历史、来源场景）
PUT    /api/user-profile/{key}           → 编辑
DELETE /api/user-profile/{key}           → 软删
```

## 六、工具函数

```python
# tools/user_profile_tool.py

def pending_extract(content: str, confidence: str = "medium") -> str:
    """分身提取用户偏好，提交到暂存区（不直接写入）"""

def profile_list(priority: str = "", tag: str = "") -> str:
    """查询正式用户画像"""
```

注册两个函数到 `registry.json`。

## 七、前端

SettingsView 第 5 Tab「👤 画像」，只展示正式画像（暂存区对用户不可见）：

```
┌──────────────────────────────────────────────┐
│  ...Tab...                           👤 画像  │
├──────────────────────────────────────────────┤
│                                              │
│  ⭐ P0 铁律 (2)                             │
│  ┌─ "先讨论再动手" ── 已获 3 个场景确认 ─┐   │
│  │  来源：自开发场景/仪表盘/闲聊            │   │
│  └──────────────────────────────────────┘   │
│  ┌─ "验收要实机测试" ── 已获 2 个场景确认 ─┐  │
│  └──────────────────────────────────────┘   │
│                                              │
│  📌 P1 偏好 (3)                             │
│  📋 P2 参考 (2)                             │
│                                              │
│  共计 7 条                                   │
│                                              │
└──────────────────────────────────────────────┘
```

## 八、实施顺序

```
Phase 1（表 + 提取层）：
  1. models.py → PendingUserTrait + UserProfile 表
  2. tools/user_profile_tool.py → pending_extract + profile_list
  3. registry.json 注册

Phase 2（沉淀层 — LLM 批量判重合并）：
  4. router/user_profile.py → 所有 API
  5. idle extractor：定时扫描 pending 区 → 打包发给 LLM → 解析返回的 JSON 合并方案 → 写入 user_profiles → 清理暂存区
     （判重：不依赖向量库，LLM 自主判断。见 4.2 节）

Phase 3（注入层 — 第 8 层，插在 Memory 之后 Config 之前）：
  7. context_builder.py → 追加用户画像段落

Phase 4（前端）：
  8. SettingsView 加第 5 Tab（只展示正式画像，暂存区不可见）
```

## 九、跟设计哲学的关系

| 原则 | 体现 |
|------|------|
| 分身不知本体事 | 分身只管提取提交，不知道最终画像长什么样 |
| 本体观察分身 | 本体从暂存区里看到分身们发现了什么用户偏好 |
| 本体单向沉淀 | 本体把分身提交的「生料」处理成正式画像 |
| 分身不写本体记忆 | `pending_extract` 写在暂存区，不是 scope='zhu' |
