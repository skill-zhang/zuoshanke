# 坐山客 Schema v1.5 — 本体记忆选择注入

> 2026-07-03
> 核心命题：不朽 ≠ 全量注入。存储层保留永不过期，注入层增加智能选择。

---

## 一、问题陈述

### 1.1 当前矛盾

```
存储层：scope=zhu → is_immortal=True → 永不删除
注入层：list_all(limit=200) → 全量排序注入
                              ↑
               当本体记忆 > 500 条时，即使 limit=200
               也在膨胀。不相关的旧记忆挤掉新鲜信息，
               token 预算失控，LLM 注意力稀释。
```

当前代码（`context_builder.py:52`）：

```python
# 本体全量返回，分身取 Top-5
selected = memories if scope == "zhu" else memories[:5]
```

$记忆数 < 200$ 时没问题，$记忆数 \to 1000$ 时这条线就是死路。

### 1.2 什么不能变

| 原则 | 地位 | 不变原因 |
|------|------|---------|
| 本体记忆永不过期 | P0 | 失去记忆 = 失去 continuity = 坐山客不"记得"用户 |
| 修正即强化 | P0 | 每次纠正都是重要关系沉淀 |
| 分身不写本体 | P0 | 分身越界是系统性风险 |
| 三域隔离 | P0 | 场景间互不可见 |

### 1.3 什么可以变

| 项 | 现状 | 目标 |
|----|------|------|
| 注入方式 | 全量排序 | **选择性注入，按需召回** |
| 注入预算 | 无限制（随记忆增长） | **硬 token 预算 + 分层控制** |
| LLM 自检索 | 有但被动 | **LLM 主动召回是正式机制** |
| 记忆体积 | 原始文本 | **核心层可压缩摘要** |

---

## 二、核心设计：三层注入模型

### 2.1 总览

```
                          LLM Context
                               │
                    ┌──────────┴──────────┐
                    │                     │
               Core Tier           Context Tier
              [始终注入]           [选择性注入]
               P0 铁律              P1 架构决策
               本体 Identity         近期重要记忆
               ~5 条 / ~800 chars    话题匹配 top-N
                    │                     │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                   On-Demand Tier    Memory Cache
                  [不主动注入]        [全量 - 不朽]
                  P2/P3 通用偏好     存储所有记忆
                  LLM 调 memory(read)
```

### 2.2 Core Tier — 始终注入（核心画像）

**定义**：定义了坐山客「是谁」的记忆。可以不精确、不全面，但不能没有。

**筛选标准**：

| 条件 | 说明 |
|------|------|
| `is_core=True` | 显式标记为核心记忆 |
| 数量上限 | **≤ 5 条**（不是模糊的「尽量少」） |
| 体积上限 | **≤ 800 字符**合起来 |
| 内容类型 | 设计哲学、铁律、本体 Identity、用户核心画像 |
| 更新频率 | 低（月级），不随日常对话增长 |

**压缩机制**：Core Tier 的记忆如果原始文本 > 200 字符，由 LLM 生成 `compressed` 摘要字段存储。注入时使用摘要，原始文本仍然保留在全量存储中。

**示例**（当前 core 候选）：

```
🔒 设计哲学：LLM 自主决策优先，量化规则只用于纯数学场景
🔒 本体架构：坐山客是本体，场景是分身。分身不写本体记忆
🔒 用户偏好：MD 而非 JSON，干燥 CSS，AI 原生设计
🔒 验收标准：实机测试拿数据说话，不口述"应该能用"
🔒 身份认知：我不是 LLM，LLM 是我引擎。Avatar 是我的脸
```

### 2.3 Context Tier — 选择性注入（话题匹配）

**定义**：与当前对话相关的中等优先级记忆。注射与否取决于话题相关性 + 时效性。

**机制**：`memory_cache.get_for_context_injection(scope='zhu', query, max_chars=3000)`

**召回算法（三因子加权排序）**：

```python
def calc_injection_score(mem, query_keywords, recency_days):
    score = 0
    # 因子 1：关键词重叠（tags + key + content 前 50 字）
    kw_score = calc_keyword_overlap(mem, query_keywords) * 0.4
    # 因子 2：时效性（最近 7 天记忆 +0.3，30 天内 +0.15）
    recency_score = calc_recency_boost(recency_days) * 0.3
    # 因子 3：记忆自身重要性（base_weight + explicit_boost）
    importance = (mem.base_weight + (mem.explicit_boost or 0)) / 10 * 0.3
    score = kw_score + recency_score + importance
    return score
```

**硬约束**：

| 约束 | 值 | 说明 |
|------|----|------|
| `max_chars` | 3000 | Context Tier 总字符上限（含格式标记） |
| `max_items` | 15 | 最多注入 15 条 |
| `min_score` | 0.3 | 低于此分数的不注入 |
| 保底机制 | **最近 3 条** | 即使分数低也注入（防「沉默的新记忆永远不被看见」） |

**保底机制详解**：无论话题匹配分数如何，距离上次注入时间最长的 3 条记忆（或最近创建的 3 条）会强制加入 Context Tier。这解决了「新记忆话题不匹配 → 永远不注入 → LLM 不知道有这条记忆」的冷启动问题。

### 2.4 On-Demand Tier — 按需召回（安全网）

**定义**：P2/P3 级记忆、陈旧但可能相关的叙事、全量修正轨迹。

**不主动注入**。当 LLM 觉得 context 中缺少某项信息时，主动调 `memory(read, scope='zhu', query=...)` 检索。

**prompt 指令**（注入 `context_composer.py` 的 memory block 尾部）：

```
## 关于记忆的说明
当前 context 已包含你的核心 Identity（Core Tier）
和与本次对话最相关的记忆（Context Tier）。
如果你觉得还缺什么信息，可以用 memory(read, scope='zhu')
检索你的全部记忆池。
```

**配合修正**：如果 LLM 发现 context 中的记忆不准确，可调 `memory(action='correct_memory', ...)` 修正。

---

## 三、注入预算管理

### 3.1 硬预算

| 层级 | 字符上限 | 条数上限 | 说明 |
|------|---------|---------|------|
| Core Tier | 800 | 5 | 「你是谁」——不可省略 |
| Context Tier | 3000 | 15 | 「当前相关」——按话题匹配 |
| Profile Layer（v1.4） | 1500 | 10 | 用户画像（P0+P1 始终，P2 话题匹配） |
| **合计** | **5300** | **30** | 不能超过整体 context 的 15% |

### 3.2 超预算处理

Context Tier 超预算时：

1. 按分数排序，取 top-N 直到触达 `max_chars` 或 `max_items`
2. 保底 3 条**不受**字符预算限制（它们占用的空间从 Profile Layer 里扣）

Profile Layer 超预算时：
1. P0 始终保留
2. P1 按时间倒序保留最近 5 条
3. P2 全丢弃

### 3.3 动态调节（可选扩展）

当整体 context 接近 token 上限时，各层按比例压缩：

```
Core Tier: 不压缩（identity 不可丢）
Context Tier: 从 max_chars=3000 降为 2000
Profile Layer: 从 1500 降为 800
```

由调用方（`scene_stream.py` / `garden_chat.py`）传入 `token_budget_remaining` 参数。

---

## 四、DB 变更

### 4.1 AgentMemory 表新增字段

```python
# 已有
scope = Column(String, default="zhu")
is_immortal = Column(Boolean, default=False)
is_narrative = Column(Boolean, default=False)
correction_trail = Column(Text, default="[]")

# v1.5 新增
is_core = Column(Boolean, default=False)            # Core Tier 标记
compressed = Column(Text, nullable=True)             # Core Tier 压缩摘要（≤200 字）
keywords = Column(JSON, default=list)                # 自动提取的关键词数组，用于话题匹配
last_injected_at = Column(DateTime, nullable=True)   # 上次注入时间（用于保底机制）
```

**迁移策略**：`ALTER TABLE` 零破坏（SQLite 支持单列 ADD COLUMN）。

### 4.2 是否还需要 `last_injected_at`？

如果不记录注入时间，保底机制（最近 3 条）无法实现。

有两种实现方式：

| 方案 | 做法 | 优缺点 |
|------|------|--------|
| A: 新增字段 | `last_injected_at` 每注入更新一次 | 精准但每次 context 构建都写 DB |
| B: 内存 LRU | MemoryCache 中维护 `injected_history` 字典 | 不写 DB，但重启丢失 |

**结论**：用方案 A，但**不从 context_builder 写**——改为在 `MemoryCache.get_for_context_injection()` 中由缓存层写，走批量更新（`batch_update_injected_timestamps()` 循环外一次 `db.commit()`）。

### 4.3 现有记忆标记策略

| 策略 | 做法 |
|------|------|
| `is_core=True` | 由脚本或 SettingsView 手动标记（LLM 不建议自主标记自身 Identity） |
| `keywords` | 自动提取（存储时或 idle_extractor 批次处理） |
| `compressed` | LLM 单条生成（新记忆创建时）或 batch 生成（已有记忆） |

**keywords 自动提取算法**（`memory_manager.py` 新增方法）：

```python
def _extract_keywords(self, text: str) -> list[str]:
    """从记忆文本提取关键词用于话题匹配。
    不需要 NLP 库——用简单的词频统计 + 停用词过滤。
    """
    import re
    from collections import Counter
    
    # 中文分字 + 英文分单词
    # 取双字/双词组合（bigram）作为平衡点
    chars = re.findall(r'[\u4e00-\u9fff]', text)
    words = re.findall(r'[a-zA-Z]\w+', text.lower())
    
    # 双字组合
    bigrams = [chars[i] + chars[i+1] for i in range(len(chars)-1)]
    
    counter = Counter(bigrams + words)
    # 去掉停用词
    stopwords = {'的', '了', '是', '在', '有', '和', '也', '就', '不', '人',
                 '都', '一', '个', '上', '很', '到', '说', '要', '去', '你',
                 '我', '他', 'the', 'a', 'an', 'is', 'are', 'was', 'were',
                 'not', 'but', 'for', 'with', 'that', 'this', 'it'}
    return [w for w, c in counter.most_common(10) if w not in stopwords]
```

---

## 五、Context Builder 改造

### 5.1 新函数：`_build_zhu_memory_block()`

代替当前的 `scope == "zhu"` 分支。

```python
def _build_zhu_memory_block(db, query: str) -> str:
    """
    v1.5：本体记忆三层选择注入。
    - Core Tier: is_core=True 的记忆，用 compressed 摘要，始终注入
    - Context Tier: 按话题匹配 + 时效性排序，受 max_chars 约束
    - On-Demand Tier: 不注入，prompt 中提示 LLM 自行检索
    """
    cache = MemoryCache.get_instance()
    
    # === Phase 1: Core Tier ===
    core_memories = cache.get_core_memories(db)  # is_core=True, ≤5条
    core_lines = []
    for mem in core_memories:
        text = mem.compressed or mem.content[:200]
        core_lines.append(f"🔒 {mem.key}: {text}")
    
    # === Phase 2: Context Tier ===
    context_memories = cache.get_for_context_injection(
        db, scope="zhu", query=query,
        max_chars=3000, max_items=15,
        exclude_keys=[m.key for m in core_memories],  # 不重复
    )
    context_lines = []
    for mem in context_memories:
        icon = "📖" if mem.get("is_narrative") else ""
        level = mem.get("priority_level", "P1")
        prefix = {"P0": "🔒", "P1": "⭐", "P2": "📝"}.get(level, "📝")
        context_lines.append(f"- {icon}{prefix} {mem.key}: {mem.content[:150]}")
    
    # === Phase 3: 组装 ===
    parts = []
    if core_lines:
        parts.append("## 你（核心认知）")
        parts.extend(core_lines)
    if context_lines:
        parts.append("")
        parts.append("## 与当前对话相关的记忆")
        parts.extend(context_lines)
    if not core_lines and not context_lines:
        return ""
    
    # === 追加 On-Demand 提示 ===
    parts.append("")
    parts.append("> 如果你需要更详细的信息，可以用 memory(read, scope='zhu') 手动检索全部记忆。")
    
    return "\n".join(parts)
```

### 5.2 调用点变更

```python
# 旧（context_builder.py:51-52）
memories = cache.get_top_for_context(...)
selected = memories if scope == "zhu" else memories[:5]

# 新
if scope == "zhu":
    memory_block = _build_zhu_memory_block(db, query)
else:
    memories = cache.get_top_for_context(...)
    selected = memories[:5]
```

### 5.3 原 Profile Layer 的调整

v1.4 的 Profile Layer（用户画像）与本体记忆是两套独立数据。v1.5 中：

- `user_profiles` 表的 P0 + P1 自动同步为 `AgentMemory(scope='zhu', is_core=True)`
- Profile Layer 从独立的第 8 层变为 **Core Tier 的组成部分**
- 注入时不再重复：`_build_zhu_memory_block()` 已经包含核心画像
- 原 Profile Layer 代码保留但标记为 `@deprecated("v1.5: 合并入 Core Tier")`

---

## 六、MemoryCache 改造

### 6.1 新增方法

```python
class MemoryCache:
    def get_core_memories(self, db, max_count=5) -> list[AgentMemory]:
        """获取 Core Tier 记忆（is_core=True），按 base_weight 降序"""
        return db.query(AgentMemory).filter(
            AgentMemory.scope == "zhu",
            AgentMemory.is_core == True,
        ).order_by(AgentMemory.base_weight.desc()).limit(max_count).all()
    
    def get_for_context_injection(
        self, db, scope, query, max_chars=3000, max_items=15,
        exclude_keys=None,
    ) -> list[dict]:
        """本体记忆的选择性注入——按三因子排序取 Top-N"""
        memories = db.query(AgentMemory).filter(
            AgentMemory.scope == scope,
            AgentMemory.is_core != True,  # 排除 Core Tier
        ).all()
        
        query_kw = self._extract_query_keywords(query)
        scored = []
        for mem in memories:
            score = self._calc_injection_score(mem, query_kw)
            if score >= 0.3:
                scored.append((score, mem))
        
        scored.sort(key=lambda x: (-x[0], x[1].created_at))
        
        # 保底 3 条（最近创建/修改的）
        safety_net = sorted(memories, key=lambda m: m.updated_at or m.created_at, reverse=True)[:3]
        safety_keys = {m.key for m in safety_net}
        
        # 合并：保底 + 高分，去重
        result = []
        seen_keys = set(exclude_keys or [])
        for _, mem in scored:
            if mem.key in seen_keys: continue
            result.append(mem)
            seen_keys.add(mem.key)
            if len(result) >= max_items: break
        
        # 补充保底（尽可能在预算内）
        for mem in safety_net:
            if mem.key in seen_keys: continue
            if len(result) >= max_items: break
            result.append(mem)
            seen_keys.add(mem.key)
        
        # 检查字符预算（超出则截断最后几条）
        total_chars = sum(len(self._format_for_injection(m)) for m in result)
        while total_chars > max_chars and len(result) > 3:
            removed = result.pop()
            total_chars -= len(self._format_for_injection(removed))
        
        # 更新 last_injected_at
        self._batch_update_injected(db, [m.key for m in result])
        
        return result
    
    def _calc_injection_score(self, mem, query_kw):
        """三因子加权排序"""
        score = 0
        # 关键词重叠
        mem_kw = set(mem.keywords or [])
        if query_kw and mem_kw:
            overlap = len(query_kw & mem_kw)
            score += (overlap / max(len(query_kw), 1)) * 0.4
        # 时效性
        if mem.updated_at:
            days = (datetime.utcnow() - mem.updated_at).days
            score += max(0, 1 - days / 90) * 0.3  # 90 天内线性衰减
        # 重要性
        importance = (mem.base_weight + (mem.explicit_boost or 0)) / 10.0
        score += min(importance, 1.0) * 0.3
        return score
    
    def _extract_query_keywords(self, query):
        """从用户查询提取关键词集合"""
        return set(re.findall(r'[\u4e00-\u9fff\w]+', query)) - STOPWORDS
    
    def _batch_update_injected(self, db, keys):
        """批量更新 last_injected_at（一次 commit）"""
        db.query(AgentMemory).filter(
            AgentMemory.key.in_(keys)
        ).update(
            {"last_injected_at": datetime.utcnow()},
            synchronize_session=False,
        )
```

---

## 七、Prompt 变更

### 7.1 记忆段尾部追加

在 `_build_memory_block()` 末尾追加指引（无论是 zhu 还是 scene）：

```python
# 仅在 scope='zhu' 时追加
if scope == "zhu":
    parts.append("")
    parts.append("> 以上是你核心 Identity（🔒）和当前相关记忆（⭐）。")
    parts.append("> 如果你需要查阅更早或更详细的记忆，请使用 memory(read, scope='zhu')。")
```

### 7.2 LLM 关于记忆的认知（system prompt 新增段）

```python
## 📝 记忆体系
坐山客拥有三层记忆体系：
1. 核心 Identity（🔒）你已经知道——你是谁、用户是谁、设计铁律
2. 当前相关记忆（⭐）——与本次对话主题相关的长期知识
3. 全部记忆池——可用 memory(read, scope='zhu') 手动检索

当你觉得缺少关键信息，或对某条记忆的准确性有疑问时：
- 用 memory(read, scope='zhu', query='...') 检索完整记忆
- 用 memory(action='correct_memory', ...) 修正不准确的记忆
```

---

## 八、LLM 自检索与保底机制的配合

### 8.1 场景举例

| 场景 | Core Tier 够用？ | Context Tier 够用？ | 需要 On-Demand？ |
|------|-----------------|-------------------|-----------------|
| 用户聊日常话题 | ✅ 本体 Identity | ✅ 最近 3 条保底 | ❌ |
| 用户问设计决策 | ❌（不在 core） | ⚠️ 如果最近聊过→命中；没聊过→没命中 | ✅ LLM 应主动查 |
| 用户纠正记忆 | ❌ | ❌（correction 不自动触发） | ✅ LLM 应主动调用 correct_memory |
| 用户问很久前的约定 | ❌ | ❌ | ✅ LLM 应主动查 |

### 8.2 潜在地雷：LLM 不主动调 memory(read)

**问题**：LLM 可能不习惯主动检索记忆，认为「没注入就是不相关/不存在」。

**缓解措施**：

1. **Core Tier 注入效果比较段落**：在记忆段首加 `## 关于你（部分记忆已加载，完整池可检索）`
2. **失败后自动降级**：如果 LLM 连续 2 轮回复中表现出「缺失关键记忆」（怎么检测？），后端自动注入 `[系统提示：你似乎缺失了某些记忆，建议用 memory(read) 检索]`——但这个方案太"规则"，不符合设计哲学。先否掉。
3. **观察积累**：先上线 Core + Context Tier，观察 LLM 是否会主动使用 memory(read)。如果明显不会，再加入引导 prompt。

**好的，放一放。先上线再看。**

---

## 九、记忆质量：关键词提取的准确性与冷门词

### 9.1 关键词提取的局限

当前设计用简单的词频 + bigram 提取关键词。有问题：

- 「不喜欢弹窗交互」→ bigrams: `[不喜欢, 喜欢弹, 欢弹窗, 弹窗交, 窗交互]` → 保留 `不喜欢`、`弹窗`
- 「保持`_CORE_PERSONALITY` 在 `_build_prompt_layer()` 而非硬编码」→ bigrams: 散乱，没有有效关键词

**改善方案**：`keywords` 字段支持**手动标注**。用户/本体现在 SettingsView 编辑记忆时，可以补关键词。自动提取只是第一轮粗筛。

**决策**：自动提取 + 可手动补。不追求完美关键词，够用就行。

### 9.2 关键词数量与存储

- 默认提取 10 个 bigram/word
- `keywords` 字段存为 JSON `["弹窗", "界面", "偏好"]`
- 手动补时追加，不依赖自动提取结果

---

## 十、冻结原则（不会因 v1.5 修改）

| 原则 | 原因 |
|------|------|
| 本体记忆永不过期 | 本体 continuity 的根本保证 |
| 修正即强化 | 每一条纠正都珍贵 |
| 分身不写本体 | 分身越界=系统风险 |
| 三域隔离 | 场景隐私+纯净 |
| 分身只提取不沉淀 | 暂存区-本体处理链路不变 |
| 用户画像走暂存区 | 分身不得直接写 user_profiles |

---

## 十一、边界情况

### 11.1 启动冷启动

本体重建/换服务器后，`is_core=True` 的记忆从种子数据恢复。当前 Hermes 批量导入脚本需追加 `is_core=True` 标记。

### 11.2 Core Tier 太少（< 3 条）

新装系统：`is_core` 标记为空。此时 Core Tier 退化为「base_weight 最高且 is_immortal=True 的 3 条记忆」，并显示降级标记：

```
## 你（核心认知 — ⚠️ Core Tier 未配置，使用自动选）
```

### 11.3 Core Tier 溢出（> 5 条）

设置 SettingsView 的限制：最多标记 8 条为 `is_core`。注入时取 weight 最高的 5 条。

### 11.4 Context Tier 全空

`get_for_context_injection()` 返回空（所有记忆分数 < 0.3 且创建时间足够早）。此时：
- 保底 3 条机制确保至少有一些记忆注入
- 如果保底的 3 条也被 `exclude_keys` 排除（core 正好占了最后的 3 条），则 Context Tier 为空
- 不报错，Core Tier 单独出现

### 11.5 记忆定期注入回访

有些记忆可能因为话题不匹配数周不被访问。保底 3 条机制确保它们**最终**会被看到，但时间不确定。

**可选增强**：idle_extractor 扫描时，如果某条 P0 记忆超过 30 天未被注入，将其加入下一次的 Context Tier 强制注入（不计入 max_items）。这个先放下，不纳入 v1.5 第一期。

---

## 十二、实施顺序

```
Phase 1（DB + 模型层）：
  ├─ AgentMemory 表新增：is_core, compressed, keywords, last_injected_at
  ├─ 迁移脚本：标记现有 P0 级记忆为 is_core=True
  └─ keywords 自动提取：_extract_keywords() 落地

Phase 2（注入层）：
  ├─ MemoryCache 新增：get_core_memories(), get_for_context_injection()
  ├─ context_builder.py：_build_zhu_memory_block() 替换旧的全量注入
  ├─ _calc_injection_score() 三因子排序
  └─ 保底 3 条机制

Phase 3（prompt + LLM 自检索）：
  ├─ 记忆段尾部追加 "可自行检索" 指引
  ├─ system prompt 新增记忆体系说明
  └─ 观察 LLM 是否主动调 memory(read)

Phase 4（前端）：
  ├─ SettingsView 画像 Tab 标记 is_core
  ├─ 显示注入统计（core/context/保底数量）
  └─ 手动编辑 keywords

Phase 5（收割 + 迭代——靠观察）：
  ├─ 收集 LLM 自检索的使用率数据
  ├─ 如果 < 10% → 加强 prompt 引导
  └─ 如果 P1 命中率低 → 优化 _calc_injection_score 权重
```

---

## 十三、设计文档演变

| 版本 | 日期 | 核心变化 |
|------|------|---------|
| v1.0 | 2026-05-20 | 7 层 Context 组合架构 |
| v1.1 | 2026-05-22 | Context 组合器实现 + 记忆萃取层 |
| v1.2 | 2026-05-24 | 工作台 + 场景元数据扩展 |
| v1.3 | 2026-05-25 | 前端重构 + 场景发布流程 |
| v1.4 | 2026-05-26 | 用户画像管线 + LLM 判重 + SettingView Tab |
| **v1.5** | **2026-07-03** | **本体记忆三层选择注入** |

---

## 十四、与现有架构的兼容性

| 系统 | 是否受影响 | 改什么 |
|------|-----------|--------|
| 场景分身（scene） | ❌ 不受影响 | 仍然走 `scope="scene"` → top-5 |
| 闲聊频道 | ✅ 受影响 | `scope="zhu"` 从全量变为选择注入 |
| 秘密花园起居室 | ✅ 受影响 | 同上 |
| 用户画像管线（v1.4） | ✅ 受影响 | P0+P1 合并到 Core Tier，原 Profile Layer 标记 deprecated |
| 记忆缓存层 | ⚠️ 需适配 | MemoryCache 加新接口，get_top_for_context 不变 |
| 记忆萃取 | ❌ 不受影响 | 萃取写入 AgentMemory，不改变注入决策 |
| 外部 API（GET /api/memory） | ❌ 不受影响 | 全量返回不变 |
| Hermes 批量导入脚本 | ⚠️ 追加 is_core | scripts/import_hermes_memory_to_zhu.py 加 is_core=True 标记 |

---

## 十五、验收标准

### 15.1 单元测试

| 测试 | 覆盖内容 |
|------|---------|
| `test_core_tier_always_injected` | is_core=True 的记忆总是出现在 memory block 中 |
| `test_context_tier_sorted_by_score` | Context Tier 按三因子分数降序 |
| `test_context_tier_max_chars` | 不超 max_chars=3000 |
| `test_context_tier_safety_net` | 保底 3 条永远在 |
| `test_injection_score_keywords` | 关键词匹配对分数的影响 |
| `test_injection_score_recency` | 时效性对分数的影响 |
| `test_no_core_memories_fallback` | Core Tier 空时退化为权重最高记忆 |
| `test_extract_keywords` | 中英文关键词提取 |

### 15.2 端到端验证

```bash
# 1. 验证 Core Tier 注入
curl http://localhost:8000/api/zhu-agent/status
# → context 构建日志应包含 "Core Tier: 5 entries"

# 2. 验证记忆检索
curl -s http://localhost:8000/api/scenes/{id}/stream \
  -d '{"content": "我什么时候说过MD偏好？"}' -N
# → SSE 流中应出现 memory(read) 工具调用

# 3. 保底机制验证
# 创建 20 条与当前话题无关的新记忆
# 发送话题无关消息 → Context Tier 应包含最近 3 条

# 4. 回归
# 现有场景聊天不受影响（scope=scene 仍走 top-5）
```

---

*本设计不追求冷启动期就完美。Core Tier + Context Tier + 保底 3 条已在 0→500 条记忆范围内能正常工作。500+ 后观察 LLM 自检索行为，再决定是否加强指引。*
