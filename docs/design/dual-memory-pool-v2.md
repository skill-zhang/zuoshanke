# 双重记忆池 v2 — 本体关系记忆系统

## 动机

当前记忆系统是扁平的键值存储，每条记忆独立、权重随时间衰减、超 500 条 prune。
但**本体记忆不应遗忘**——清泉纠正说「我不记得我们造了多少规则又拆了多少」，
根因是 Hermes 的记忆只保留了近期快照，丢失了「共同历程」的连续性。

## 核心转变

| 维度 | 旧 | 新 |
|------|----|----|
| 本体记忆 | 参与衰减、参与清理 | **不朽** — 不过期、不衰减、不清理 |
| 修正 | 无记录 | **修正即强化** — 每次纠正追加轨迹 |
| 叙事型 | 无 | **is_narrative** — 存历程/决策/迭代故事 |
| 分身记忆 | — | 维持现有衰减机制不变 |

## 数据模型变更

### AgentMemory 表新增字段

```python
# 已有
scope = Column(String, default="zhu")        # zhu | scene | channel
# 新增
is_narrative = Column(Boolean, default=False)  # 是否为叙事型关系记忆
correction_trail = Column(Text, default="[]")  # JSON: [{old, new, reason, timestamp}]
is_immortal = Column(Boolean, default=False)   # 不衰减不清理（scope=zhu 自动 True）
```

### MemoryManager 改造

**calc_weight()** — immortal 跳过 recency 衰减：
```python
def calc_weight(self, mem: AgentMemory) -> float:
    if mem.is_immortal:
        recency = 1.0  # 不衰减
    else:
        # 原有衰减逻辑
        days = (utcnow() - mem.last_accessed_at).days if mem.last_accessed_at else 30
        recency = math.exp(-days / DECAY_HALF_LIFE)
    # frequency, boost 保持不变
    return mem.base_weight * recency * frequency * boost
```

**record_correction(key, new_content, reason)** — 修正轨迹：
```python
def record_correction(self, key: str, new_content: str, reason: str):
    mem = self.get(key)
    trail = json.loads(mem.correction_trail or "[]")
    trail.append({
        "old": mem.content[:200],
        "new": new_content[:200],
        "reason": reason,
        "timestamp": str(utcnow()),
    })
    mem.correction_trail = json.dumps(trail, ensure_ascii=False)
    mem.content = new_content
    mem.explicit_boost += 2  # 修正即强化
    self._recalc(mem)
```

**清理** — 跳过 is_immortal：
```python
def _prune_if_needed(self):
    immortal_count = self.db.query(AgentMemory).filter(
        AgentMemory.is_immortal == True).count()
    total = self.db.query(AgentMemory).count()
    if total - immortal_count > MAX_MEMORY:
        # 只淘汰非 immortal 的最低权重 P3
```

### 新增 API

```python
POST /api/memory/{key}/correct
  body: {new_content, reason}
  → 追加修正轨迹 + 更新内容 + 强化

POST /api/memory 新增参数
  is_narrative: bool = False    # 标记为叙事型记忆
  is_immortal: bool = None      # None=scope=="zhu" 时自动 True
```

### memory_tool.py 新增 action: `correct_memory`

LLM 在闲聊频道自主调用：
```json
{
  "action": "correct_memory",
  "key": "user_work_style",
  "new_content": "正确内容...",
  "reason": "用户纠正说我先造规则再拆规则的历程我忘了"
}
```

### context_builder.py

本体记忆（scope=zhu）注入 context 时，**不做权重裁剪**——全量注入本体级记忆。
分身场景继续按 top-N 权重筛选。

## 影响范围

| 文件 | 改动 |
|------|------|
| `models.py` | AgentMemory 加 3 个字段（create_all 零破坏） |
| `memory_manager.py` | calc_weight, record_correction, prune, 迁移 is_immortal |
| `router/memory.py` | MemoryCreate 加参数, 新增 correct 端点 |
| `tools/memory_tool.py` | 新增 correct_memory action |
| `context_builder.py` | 本体记忆全量注入 |
| `router/zhu_agent.py` | 秘密花园展示 is_narrative + correction_trail |

## 验证方法

1. 创建一条叙事型记忆 → 秘密花园可见
2. 对已有记忆调用 correct → 检查 correction_trail
3. 持续不访问 scope=zhu 记忆 → 权重不衰减（秘密花园权重不变）
4. 超 500 条记忆 → immortal 不被清理
