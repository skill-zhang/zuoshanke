# 坐山客业务流程 — 数据结构 Schema v0.4

> 版本: 2026-05-16
> 核心变更: 约束提取 + 复杂度判定 + 三路径路由 + 工具就绪检查

---

## 设计原则：任务复杂度决定流水线深度

**核心命题：不是所有问题都需要走完整流水线。**

用户问一个简单问题，系统拆成 11 个节点让人手工执行——这就是 v0.3 的问题。v0.4 在入口处加一个判定层，按任务复杂度分流：

```
用户消息
    │
    ▼
[① 约束提取] ─ 一次性提取并持久化所有约束
    │
    ▼
[② 复杂度判定] ─ LLM 打标签
    │
    ├── light  ──→ Qwen 直答（可能调 1-2 工具，不建树）
    ├── medium ──→ 简化树 → 工具就绪检查 → 自动全量执行 → 汇总
    └── heavy  ──→ 完整树 → 逐节点用户确认 → 执行 → 汇总
```

---

## 一、约束提取（新增核心阶段 🔥）

### 问题背景

用户问「天津旅游，一家三口，1000 预算，3 天假期」，LLM 追问两轮后就只记得「天津」了。1000 块和 3 天全部丢失，后续所有节点跑偏。

### 约束提取流程

```
用户第一条消息进入场景
    │
    ▼
LLM 分析 → 提取所有约束 + 一次性问清所有缺失信息
    │
    ▼
约束对象持久化到 Scene.constraints
    │
    ▼
后续每一个叶子节点生成时，constraints 快照注入 prompt
    │
    ▼
最终结果对照 constraints 校验：有没有跑偏
```

### 约束提取原则

1. **一次性问完**，不要一轮问一个。所有缺失信息在一回合内问清
2. **问完即锁**，后续不再追问基础信息
3. **每个子树都注入**，防止 LLM 中间忘记

### Constraints Schema

```json
{
  "constraints": [
    {
      "key": "budget",
      "value": 1000,
      "unit": "元",
      "description": "总预算",
      "scope": "total"
    },
    {
      "key": "duration",
      "value": 3,
      "unit": "天",
      "description": "旅行天数"
    },
    {
      "key": "travelers",
      "value": 3,
      "unit": "人",
      "description": "一家三口"
    },
    {
      "key": "destination",
      "value": "天津",
      "description": "目的地"
    },
    {
      "key": "purpose",
      "value": "旅游景点推荐 + 天气适配",
      "description": "任务目的"
    }
  ],
  "missing_info": ["出行日期", "住宿偏好"],
  "questions": [
    "请问你们计划什么日期出发？",
    "住宿方面有什么偏好吗？比如酒店还是民宿？"
  ],
  "extracted_at": "2026-05-16T21:00:00Z",
  "locked": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `constraints` | [{key, value, unit?, description, scope?}] | 已提取的约束列表 |
| `missing_info` | [string] | LLM 判定缺失的必要信息 |
| `questions` | [string] | 一次性向用户提问的清单 |
| `extracted_at` | string | 提取时间戳 |
| `locked` | bool | true 后不再提取（问完即锁） |

### DB 变更

**Scene 表新增字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `complexity` | string \| null | `light` / `medium` / `heavy` / null（未判定） |
| `constraints` | JSON \| null | 约束对象（见上） |
| `constraints_locked` | bool | 默认 false，问清后设为 true |

### 最终约束校验 & 追问增量 🔥

执行全部完成后，将最终结果与 `constraints` 逐条比对，写入总结消息中：

> ✅ 预算 1000 元内：总花费 856 元 ✓
> ✅ 3 天行程：D1 天津之眼 → D2 五大道 → D3 盘山 ✓
> ✅ 应对天气：Day1 晴→户外，Day2 雨→户内 ✓

**追问增量机制：**

如果用户觉得输出结果颗粒度不够（如「这些车能不能具体看看内饰照片？」「有没有哪台有完整的保养记录？」）：

```
用户追问 → 追加到 constraints.missing_info 和 constraints.questions
          → 判断是否需要新工具能力
            → 不需要 → 直接在当前数据基础上回答
            → 需要新工具 → 标记 constraints_locked=false
                          → 仅对新增能力做工具就绪检查
                          → 增量执行（不重新全量跑）
          → 补充到结果中
```

**关键：不走全量重跑，只做增量。** 已经执行过的叶子节点除非约束本身变更，否则不重新执行。

---

## 二、复杂度判定（新增核心阶段 🔥）

### 判定方法

**LLM 判定，不用规则。** 每条用户消息进入场景时，由 AI 模型判定复杂度。

规则不可行原因：任务复杂性无法枚举。同样是「查天气」，问「今天天津多少度」→ light，问「分析过去三年天津 5 月天气趋势并给出出行建议」→ medium/heavy。

### 判定 Prompt 设计

```
分析用户的任务复杂度，仅返回以下 JSON：
{"complexity": "light"|"medium"|"heavy", "reason": "简短理由"}

判定依据：
- light: 单步骤、查 1-2 个信息、不需要拆解、答案简短
- medium: 需要 2-5 步、涉及多个工具调用、需要汇总
- heavy: 多步骤(>5)、跨领域、需要分支判断、输出物复杂
```

### 各等级特征

| 等级 | 树 | 执行 | 模型 | 工具 | 用户交互 |
|------|----|------|------|------|---------|
| **light** | 不建树，Qwen 直接答 | 无 | Qwen3.5-9B（本地） | 可调 1-2 个，不单独创建 | 无 |
| **medium** | 简化树（3-5 叶子） | 自动全量 | deepseek-v4-flash | 分析→补缺→执行 | 涉本地文件操作时暂停确认 |
| **heavy** | 完整树（不限节点） | 逐节点确认 | deepseek-v4-pro | 逐节点按需 | 每步需用户 /approve |

### 模型路由

| 用途 | v0.3 硬编码 | v0.4 按路由走 |
|------|-------------|---------------|
| 场景分析（约束提取） | Qwen3.5-9B | Qwen3.5-9B（本地） |
| 场景分析（复杂度判定） | Qwen3.5-9B | Qwen3.5-9B（本地） |
| Light 直答 | — | Qwen3.5-9B（本地） |
| Medium 任务 | deepseek-chat（已失效） | deepseek-v4-flash |
| Heavy 任务 | deepseek-chat（已失效） | deepseek-v4-pro |
| Action Map 生成 | deepseek-chat（已失效） | 继承任务等级对应模型 |
| Action Map 执行 | deepseek-chat（已失效） | 继承任务等级对应模型 |
| 工具生成 (skill) | deepseek-chat（已失效） | deepseek-v4-flash |
| 频道闲聊 | Qwen3.5-9B | Qwen3.5-9B（不变） |

> 注：`deepseek-chat` 已被 DeepSeek API 废弃（静默映射为 `deepseek-v4-flash`），不再使用。

---

## 三、三路径路由（新增核心阶段 🔥）

### Light 路径

```
用户消息
    │
    ▼
约束提取（快速，不追问）
    │
    ▼
复杂度判定 → light
    │
    ▼
Qwen3.5-9B 直接调用（不带 Thinking Map）
   ├── 可调工具（查天气、查新闻等 1-2 个）
   └── 返回完整答案给用户
    │
    ▼
约束校验（快速检查是否回答了问题）
```

**特点：**
- 用户全程只看到一次回复（流式输出，打字机效果）
- 后端不建树、不生成 Action Map、不 spawn Hermes
- 工具调用走内联（Qwen 自己调，不经过节点系统）

### Medium 路径 🔥

```
用户消息
    │
    ▼
约束提取 → 一次性问清缺失信息 → constraints_locked=true
    │
    ▼
复杂度判定 → medium
    │
    ▼
生成简化 Thinking Map（3-5 个叶子节点）
    │
    ▼
[工具就绪检查] ─── 分析每个叶子需要的工具
    │                      │
    │                 ┌────┴────┐
    │                 ▼         ▼
    │             工具有      工具缺
    │                 │         │
    │                 │    自动工具生成
    │                 │         │
    │                 └────┬────┘
    │                      ▼
    │              工具准备就绪
    │                      │
    ▼                      ▼
告知用户：「已分析完成，开始执行…」
    │
    ▼
自动全量执行（遍历所有叶子 → 自动生成 Action Map → 自动执行）
    │
    ▼
汇总结果
    │
    ▼
约束校验（逐条核对）
    │
    ▼
生成最终答案（聊天消息）
```

**特点：**
- 用户收到：① 追问信息 → ② "已分析完成，开始执行…" → ③ 最终答案
- 中间 Thinking Map 和 Action Map **在界面上可见**，用户可展开查看进度，但不强制操作
- 中间所有 Thinking Map 生成、Action Map 生成、执行、工具创建**全自动串联**
- **涉本地文件操作**（删除、覆盖、修改系统文件）→ 暂停，弹确认给用户

**输出数据规范（新增 🔥）：**

执行结果按以下格式输出，每条数据必须带来源 URL：

```json
{
  "recommendations": [
    {
      "rank": 1,
      "title": "大众 Polo 1.5L 自动 2019",
      "price": "5.00万",
      "mileage": "5.5万公里",
      "region": "北京海淀",
      "source_url": "https://www.dongchedi.com/...",
      "source_platform": "懂车帝",
      "summary": "准新车，仅左后翼子板喷漆，个人一手",
      "tags": ["年份新", "里程低", "推荐"]
    }
  ]
}
```

**要求：**
1. 每条数据附带 `source_url`（直接跳转查看检测报告/联系卖家）
2. 每条数据附带 `summary` 列（车况、卖家背景等概括性描述）
3. `tags` 让用户一眼看懂特点（"年份新"/"价格低"/"燕郊方便"）
4. 格式不局限 JSON，前端渲染为表格即可

**工具就绪检查（新增子阶段 🔥核心设计）：**

```python
def check_tools_readiness(leaf_nodes):
    """
    分析每个叶子节点需要的工具能力
    
    流程:
    1. 分析叶子需要什么能力（语义匹配，非精确匹配）
    2. 查已有工具 registry，看能不能复用
    3. 查不到/不合适 → 自动生成新工具
    4. 新工具必须满足通用性要求
    
    返回 {ready: bool, missing_tools: [{capability, reason}], plan: str}
    """
    for leaf in leaf_nodes:
        capability = analyze_leaf_need(leaf.label, leaf.context)
        # ⭐ 先查已有工具，看能不能复用
        matched = search_tools_by_capability(capability)
        if matched:
            continue  # 有现成的
        # 找不到 → 自动生成
        missing.append({"capability": capability, "leaf_id": leaf.id})
    if missing:
        for m in missing:
            auto_generate_tool(m.capability)
        return check_tools_readiness(leaf_nodes)
    return {"ready": True}
```

**工具生成质量规范（新增 🔥）：**

自动生成的工具必须满足以下条件，不满足则打回重做：

| 规范 | 说明 | 反例 | 正例 |
|------|------|------|------|
| **通用参数化** | 地名/数据作为参数传入，不硬编码 | `tianjin_weather.py`（天津写死在代码里） | `query_weather.py`（接受 city 参数） |
| **复用性** | 其他地方也能用，不绑定特定任务 | `tianjin_travel_budget.py` | `trip_budget_calculator.py`（接受 people/days/budget） |
| **单一职责** | 一个工具只做一类事 | 天气+景点+预算混在一个文件 | 三个独立文件各干各的 |
| **命名规范** | 描述能力而非描述场景 | `tianjin_scenic_spot.py` | `query_scenic_spots.py`（接受 city 参数） |
| **SKILL.md 节制** | 只有真通用的工具才生成 SKILL.md | 每个工具都生成 SKILL.md | 存 registry 即可，只在确认通用后才生成 |

**注册先行，文档从缓：** 新工具先登记到 `tools/registry.json`（name + description + parameters），能跑通再说。SKILL.md 只在两种情况下生成：
1. 工具经过 2+ 次不同场景使用验证确实通用
2. 用户明确要求「把这个工具记录下来」

**Prompt 注入（工具生成时）：**
```
生成工具要求：
1. 所有可变数据必须作为函数参数传入，严禁硬编码
2. 工具名描述能力而非场景（query_weather 而非 tianjin_weather）
3. 异常处理完整（网络超时、API 限制、空数据）
4. 输出中文描述（非 raw JSON）
5. 单文件、无外部依赖（仅用 Python 标准库 + requests）
```

### Heavy 路径

```
用户消息
    │
    ▼
约束提取 → 一次性问清 → constraints_locked=true
    │
    ▼
复杂度判定 → heavy
    │
    ▼
生成完整 Thinking Map（不限节点数）
    │
    ▼
逐节点审核（用户确认哪些叶子要生成 Action Map）
    │
    ▼
Action Map 生成（用户逐节点确认/生成）
    │
    ▼
Action Map 执行（用户逐节点确认/执行）
    │
    ▼
汇总结果
    │
    ▼
约束校验
```

**特点：**
- 即 v0.3 的完整流程，保持用户对每步的控制
- 约束提取前置，所有子树共享约束快照
- 专门面向复杂多步骤项目

---

## 四、追加调整

### ThinkNode 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `constraints_snapshot` | JSON \| null | 此节点生成时**当时**的约束快照（防止后续约束变更影响历史） |

### ActionMap 生成 Prompt 变更

每个 Action Map 生成 prompt 头部必须插入约束快照：

```
任务约束（原始用户输入）:
- 总预算: 1000 元
- 旅行天数: 3 天
- 人数: 3 人（一家三口）
- 目的地: 天津
- 目的: 旅游景点推荐 + 天气适配

请基于以上约束生成 Action Map。
```

### 约束校验执行

最终校验放在 `action_map` 或 `scene` 的汇总阶段：

```python
def validate_constraints(result_text, constraints):
    checks = []
    for c in constraints:
        if c.key == "budget":
            checks.append(check_budget(result_text, c.value))
        elif c.key == "duration":
            checks.append(check_duration(result_text, c.value))
        # ...
    return {"passed": all(c.passed for c in checks), "checks": checks}
```

---

## 五、模型选择配置（预留）

当前硬编码，后续 UI 化配置：

```json
{
  "model_routing": {
    "light": {"provider": "local", "model": "qwen3.5-9b"},
    "medium": {"provider": "deepseek", "model": "deepseek-v4-flash"},
    "heavy": {"provider": "deepseek", "model": "deepseek-v4-pro"},
    "tool_gen": {"provider": "deepseek", "model": "deepseek-v4-flash"}
  }
}
```

这个配置层未来放在坐山客 UI 的「系统设置」中，场景级别可覆盖。

---

## 六、数据结构变更总览

### 新增

| 项目 | 说明 |
|------|------|
| `Scene.complexity` | 字段: string \| null |
| `Scene.constraints` | 字段: JSON |
| `Scene.constraints_locked` | 字段: bool |
| `ThinkNode.constraints_snapshot` | 字段: JSON \| null |
| 约束提取 prompt | 新增 system prompt 类型 |
| 复杂度判定 prompt | 新增 system prompt 类型 |
| 工具就绪检查 | 新增函数 `check_tools_readiness()` |
| 约束校验 | 新增函数 `validate_constraints()` |

### 修改

| 项目 | 变更 |
|------|------|
| 消息入口处理 | 增加约束提取 → 复杂度判定 → 路由分支 |
| Action Map 生成 prompt | 注入约束快照 |
| `deepseek-chat` 全部替换 | → `deepseek-v4-flash` / `deepseek-v4-pro` |

### 不变

| 项目 | 原因 |
|------|------|
| Thinking Map 数据结构 | 树状结构不变，仅加约束字段 |
| Action Map 数据结构 | 节点类型/状态机不变 |
| Action Map 执行引擎 | 沙箱/重试/日志机制不变 |
| 频道闲聊 | 独立不走这个流程 |

---

## 七、边界场景

### 🚫 用户修改约束（新消息覆盖旧任务）

用户先问「天津3天1000元」，执行一半说「预算改成2000」：

```
→ 检测到 constraints 已 locked 但用户新消息包含约束变更
→ 标记 constraints stale
→ 重新提取约束
→ 检查已有 Thinking Map 是否与旧约束耦合过深
   → 浅 → 通知用户「约束已更新，继续执行」
   → 深 → 通知用户「约束变更较大，建议重新生成计划」
```

### 🚫 工具生成失败

工具自动生成时 Hermes 超时/报错：

```
→ 重试 1 次（走 deepseek-v4-pro）
→ 仍失败 → 告知用户「需要 xxx 工具但自动创建失败，请检查」
→ 降级为纯 LLM 分析（不执行）
```

### 🚫 工具质量不合格（硬编码/非通用）

自动生成的工具被检测为 `tianjin_xxx.py` 等硬编码产物：

```
→ 工具生成完成后自动质量扫描
→ 检查条件：文件名含地名？参数列表为空？数据含硬编码常量？
→ 不合格 → 打回重生成，prompt 强化通用性要求
→ 仍不合格（2 次后）→ 显示给用户：「工具已生成但通用性不足」
→ 此时工具可临时使用但不入 registry
```

### 🚫 用户中途打断

全自动执行中用户发新消息：

```
→ 是否与当前执行相关？
   → 是 → 追加到当前场景上下文（不影响执行）
   → 否 → 提示「当前有任务正在执行，是否中断？」
```

---

---

## 八、v0.3 → v0.4 核心变化

| 维度 | v0.3 | v0.4 |
|------|------|------|
| **入口** | 所有消息走同一流水线 | 约束提取→判定→三路分流 |
| **模型** | 硬编码 deepseek-chat（已失效） | 按等级路由 flash/pro/本地 |
| **约束** | 无约束管理，追问后丢失 | 显式提取+持久化+快照+校验+追问增量 |
| **执行** | 用户逐节点手动 | light/medium 自动串联 |
| **输出规范** | 纯文本 | 每条数据带 URL + 说明列 + tags |
| **地图可见性** | 用户必须操才能推进 | 地图可见但不强制操作，可展开查看进度 |
| **工具** | 执行中涌现，质量不可控 | 先查 registry → 找不到再生成（找→造） |
| **工具质量** | 生成硬编码专用工具 | 强制通用参数化+复用性+规范命名 |
| **SKILL.md** | 每个工具都生成 SKILL.md | 仅通用工具生成，其余只入 registry |
| **用户视角** | 看我拆了 11 个节点，要手动点 | 看最终答案，地图备查 |

---

## 九、性能瓶颈分析与优化方向 🔥

### 现状（v0.3 问题）

| 环节 | 延迟 | 原因 |
|------|------|------|
| Qwen3.5-9B **首 token** | 30-60s | 本地 llama.cpp 推理，模型加载+slot 分配 |
| Hermes **子进程冷启动** | 8-12s | subprocess.Popen + Python 解释器启动 |
| Action Map **生成** | 30-90s | Hermes 调用 deepseek 模型，串行 JSON 输出 |
| Action Map **执行** | 30-120s/节点 | 每个节点独立 spawn Hermes |
| **串行累积** | 3-5min+ | 建树→生成 AM→执行，全部串行 |

**对比：本文会话（直调 deepseek API）**

| 环节 | 延迟 | 原因 |
|------|------|------|
| 复杂度判定 | ~1s | cloud API 即时响应 |
| 并行搜索 | ~24s | delegate_task 两个子任务同时跑 |
| 汇总输出 | ~2s | 纯文本整理 |
| **总耗时** | **~27s** | |

### 瓶颈根因

**1. Qwen3.5-9B 本地推理太慢**
- 对比：cloud API（deepseek-v4-flash）首 token < 1s，Qwen 本地 30-60s
- 即使 Qwen 是免费本地方，但每次消息处理都要等它，体验差

**2. Hermes 子进程启动成本高**
- 每个叶子节点都 spawn 一个新 Hermes 子进程
- Python 解释器启动 + 模型加载 + 配置初始化 = 8-12s 纯开销
- 10 个叶子节点 = 80-120s 在等启动

**3. 功能路径串联长**
- 用户消息 → Qwen 分析 → 建树 → Hermes 生成 AM → 用户确认 → Hermes 执行 → 汇总
- 每个箭头都是一次网络/进程调用

### v0.4 可缓解的部分

| 措施 | 预计提速 | 实现复杂度 |
|------|---------|-----------|
| Medium 路径**自动串联** | 省去用户操作等待 | 中 |
| 叶子节点**并行执行** | N 倍（2-3x） | 中 |
| Light 路径**不走 Qwen 建树** | 省 30-60s | 低 |
| 工具生成走 **deepseek-v4-flash** 而非本地方 | 省 10-20s/次 | 低 |

### 后续架构建议（非 v0.4 范围）

几个方向，可以后面专门讨论：

**A. Qwen 只做轻量判定**
- 消息进来先让 deepseek-v4-flash **打标签**（1-2s）
- Light → deepseek 直答（不限 Qwen）
- Medium/Heavy → Qwen 建树（反正要等 30s 建树，Qwen 够用）
- 执行阶段全部走 cloud API（deepseek-v4-flash/pro）

**B. Hermes 子进程池化**
- 启动 2-3 个常驻 Hermes 子进程（类似 worker pool）
- 任务投递到 pool，不用每次重新 spawn
- 消除 8-12s 冷启动

**C. 替换 Qwen 为更快的本地模型**
- Qwen3.5-9B 对本地硬件来说太大了
- 更小的模型（如 Qwen2.5-7B-Q4 或 phi-4）首 token 快很多
- 或 GPU 推理（但受限于硬件）

### 当前 v0.4 的务实选择

| 优先级 | 做什么 | 预期收益 |
|--------|--------|---------|
| P0 | Light 路径跳过 Qwen 建树 | Medium 以下任务快 30-60s |
| P1 | Medium 自动串联+并行叶子执行 | 消除用户等待 + N 倍提速 |
| P2 | 工具生成走 deepseek-v4-flash | 每个工具节省 10-20s |
| P3 | Hermes 子进程池化 | 消除 8-12s 冷启动 |


## 十、数据备份策略

### 当前风险

| 风险点 | 状态 |
|--------|------|
| WSL 虚拟磁盘在 D 盘单个 VHDX 文件 | ⚠️ D 盘故障 = 全丢 |
| 项目无 git remote | ⚠️ 纯本地无备份 |
| 项目大小 372MB | ✅ 可接受，不算大 |

### 建议方案

| 优先级 | 措施 | 命令 |
|--------|------|------|
| **每日** | C 盘建 git bare repo 做 backup remote | `git init --bare /mnt/c/backup/zuoshanke.git` → `git remote add backup /mnt/c/backup/zuoshanke.git` → `git push backup` |
| **每周** | wsl --export 全量导出 WSL | `wsl --export Ubuntu /mnt/c/wsl-backup/zuoshanke-wsl.tar` |
| **可选** | rsync 项目到 C 盘（无版本历史） | `rsync -av ~/zuoshanke/ /mnt/c/backup/zuoshanke/` |

建议**至少做每日 git push**，C 盘是 SSD 且和 D 盘物理隔离，D 盘挂了也不会丢。`wsl --export` 可每周跑，但文件较大（整个 WSL 虚拟磁盘）。

---

## 十一、系统设置设计（v0.4 新增 🔥）

> **设计原则：** 坐山客的设置不是「llama-server 参数编辑器」。坐山客是 Agent 工作台，用户对采样参数（Top K / Min P / XTC / DRY）没有直接感知兴趣。设置页只暴露**有业务语义的、不同路由需要不同值的**参数。

### 与 llama-server WebUI Settings 的对比

llama-server 内置 WebUI（`http://localhost:8083/`）有一个 Settings 页面，列出了 20+ 的底层采样参数（Temperature / Top K / Min P / Repeat Penalty / DRY / XTC 等）。它通过 `/props` API 实时写入 `server.webui_settings`，覆盖 `default_generation_settings`，**不修改启动参数，只在当前会话生效**。

**坐山客不做这种设计。** 差异：

| 维度 | llama-server WebUI Settings | 坐山客 Settings |
|------|----------------------------|-----------------|
| 面向用户 | 直接聊天的终端用户 | Agent 工作台用户 |
| 参数粒度 | 底层采样参数（20+ 项） | 业务语义参数（<7 项） |
| 生效范围 | 所有对话共用一个设置 | **按路由独立**（频道/场景/约束提取各不同） |
| 修改目的 | 调当前聊天的输出风格 | 调 Agent 行为的可靠性与效率 |
| 持久化 | 浏览器 localStorage + server 运行时内存 | **持久化到 DB**，重启不丢 |

### 设置不采用的内容

| 类别 | 设置项 | 不采用原因 |
|------|--------|-----------|
| llama 采样参数 | Top K / Top P / Min P / XTC / Typical P | 保持默认即可，用户调了看不出效果 |
| | DRY / Mirostat | 9B 模型不需要额外复杂度 |
| | Dynamic Temperature | 坐山客每个路由已独立设温，不需要动态调整 |
| | Backend Sampling | 实验性 |
| llama 采样顺序 | Samplers order | 保持默认链即可 |
| llama 惩罚 | Presence / Frequency Penalty | 只保留 `Repeat Penalty` 够用 |
| WebUI 显示类 | Theme / Always show sidebar / Show microphone | 坐山客有自己的前端 |
| Developer | MCP servers / Raw output toggle | 坐山客不走这个路径 |
| 服务安全 | API Key / SSL | 本地开发环境不需要 |

### 设置采用的五项

| # | 设置项 | 来自 llama WebUI | 说明 |
|---|--------|-----------------|------|
| 1 | **Temperature** | ✅ 保留，等价 | 每个路由独立值，先内部调好，未来可放开给用户 |
| 2 | **Repeat Penalty** | ✅ 保留 | 多轮对话防重复，1.0~1.15，不同路由可独立设置 |
| 3 | **System Prompt** | ✅ 保留但 disable | 可预览当前人设，暂不可编辑。保留交互入口为后续「频道人设自定义」做准备 |
| 4 | **Max Tokens** | ✅ 等效 | 最大生成长度，每个路由独立 |
| 5 | **PDF as Image** | ✅ 保留但 disable | 多模态 Vision 预留，等真的支持图片理解时启用 |

> **「保留但 disable」的设计意图：** 功能相关项在界面上可见但不可交互（灰色打底 + lock 图标），让用户知道「这个功能有计划」，而不是根本不存在。等实现后自然解锁。

### 设置架构：三层分层

```
┌─ ① 服务运维层（只读 + 操作按钮）─────────────┐
│  llama-server   ✅ 运行中  :8083             │
│  Flash Attention: on   |   Cache Reuse: 512  │
│  VRAM: 4.1/11.9 GB   |   上下文: 16384 ctx    │
│  [重启] [停止] [查看日志]                      │
│  数据来源: llama-server /health + /slots API  │
│  不存 DB，每次打开时实时拉取                     │
└─────────────────────────────────────────────┘
                        ↕ 松耦合
┌─ ② 模型路由层（持久化到 DB）──────────────────┐
│  ┌──────────┬──────────────┬──────┬────────┐ │
│  │ 路由     │ 模型          │ 温度 │ 最大   │ │
│  │          │               │      │ Token  │ │
│  ├──────────┼──────────────┼──────┼────────┤ │
│  │ 频道闲聊 │ Qwen3.5 本地  │ 0.7  │ 2048   │ │
│  │ 场景分析 │ Qwen3.5 本地  │ 0.3  │ 4096   │ │
│  │ 约束提取 │ Qwen3.5 本地  │ 0.1  │ 1024   │ │
│  │ Medium   │ DeepSeek Flash│ 0.3  │ 4096   │ │
│  │ Heavy    │ DeepSeek Pro  │ 0.3  │ 8192   │ │
│  └──────────┴──────────────┴──────┴────────┘ │
│  数据来源: settings 表（或 config 文件）        │
│  变更立即生效（下次请求使用新参数）              │
└─────────────────────────────────────────────┘
                        ↕ 紧耦合
┌─ ③ 人设/能力层（预览态）─────────────────────┐
│  ■ System Prompt（频道人设）                   │
│  ┌─ 你是坐山客，来自科幻宇宙《吞噬星空》……… ──┐ │
│  │ [锁定 🔒 — 暂不可编辑]                    │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ■ 多模态                                    │
│  ┌─ PDF as Image  ──────── [OFF] (预留) ──┐  │
│  └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### DB 结构（settings 表）

```sql
CREATE TABLE IF NOT EXISTS settings (
    id            VARCHAR PRIMARY KEY,
    -- 模型路由设置
    routing       JSON NOT NULL DEFAULT '{
        "channel":    {"model": "qwen3.5-9b",  "provider": "local",     "temperature": 0.7, "max_tokens": 2048, "repeat_penalty": 1.0},
        "scene":      {"model": "qwen3.5-9b",  "provider": "local",     "temperature": 0.3, "max_tokens": 4096, "repeat_penalty": 1.05},
        "extraction": {"model": "qwen3.5-9b",  "provider": "local",     "temperature": 0.1, "max_tokens": 1024, "repeat_penalty": 1.0},
        "medium":     {"model": "deepseek-v4-flash", "provider": "deepseek", "temperature": 0.3, "max_tokens": 4096, "repeat_penalty": 1.05},
        "heavy":      {"model": "deepseek-v4-pro",   "provider": "deepseek", "temperature": 0.3, "max_tokens": 8192, "repeat_penalty": 1.05}
    }',
    -- 人设（暂不可编辑，但存了备查）
    system_prompts JSON DEFAULT '{
        "channel": "你是坐山客，来自科幻宇宙《吞噬星空》的AI智能体……",
        "scene": "你是 Qwen3.5（通义千问），部署在本地服务器上的 AI 架构顾问……"
    }',
    -- 特性开关（预留）
    features      JSON DEFAULT '{
        "pdf_as_image": false,
        "vision_enabled": false
    }',
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

> **为什么用单行 JSON 不用多表？** 设置项数量稳定（<20 项），JSON 字段可以一次性读写在内存中缓存，不需要多次 join。API 返回直接 `settings.routing` 即可，前端几个 select/input 对号入座。

### API 设计

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/settings` | 读取全部设置（含服务状态） |
| `PATCH` | `/api/settings` | 部分更新（传什么改什么） |
| `GET` | `/api/settings/service` | 只读：服务状态（不存 DB，实时拉 llama-server） |

### 代码集成点

设置值在 `ai_engine.py` 的每个入口函数中读取：

```python
# 启动时加载一次到内存，避免每次请求都查 DB
settings_cache = None

def get_settings():
    global settings_cache
    if settings_cache is None:
        with Session() as db:
            s = db.query(Setting).first()
            settings_cache = json.loads(s.routing) if s else DEFAULT_ROUTING
    return settings_cache

def call_qwen(messages, route="channel", **kwargs):
    s = get_settings().get(route, DEFAULT_ROUTING)
    temperature = kwargs.get("temperature", s["temperature"])
    max_tokens = kwargs.get("max_tokens", s["max_tokens"])
    # ...
```

**变更时刷新缓存**：`PATCH /api/settings` 更新 DB 后设置 `settings_cache = None`，下次请求自动重新加载。
