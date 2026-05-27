# Schema v1.5 实现参考 — Phase 1

> 2026-07-03 | 本体记忆三层选择注入

## 核心原则

**不朽 ≠ 全量注入**。存储层保留 `is_immortal=True`（永不删除），注入层加三层选择逻辑。

## 数据模型

### AgentMemory 新增字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `is_core` | Boolean | False | Core Tier 标记，始终注入 |
| `compressed` | Text | nullable | 压缩摘要（≤200 字），Core Tier 注入用 |
| `keywords` | JSON | [] | 话题匹配用关键词，自动提取 |
| `last_injected_at` | DateTime | nullable | 上次注入时间，保底机制用 |

SQLite ALTER TABLE 是幂等的——迁移脚本会检测列是否存在再 ADD。

## 代码变更

### `backend/agent_core/memory_manager.py`

| 方法 | 变更 | 行号 |
|------|------|------|
| `extract_keywords(text, max_count=10)` | 🆕 公开方法，bigram 词频 + 停用词过滤 | ~107 |
| `add()` | 🆕 `is_core` 参数 + `keywords` 自动提取 | ~177 |
| `record_correction()` | 🆕 内容变更后重提取 keywords | ~392 |
| `_to_dict()` | 🆕 透传 4 个新字段 | ~659 |

### `backend/agent_core/memory_cache.py`

| 位置 | 变更 |
|------|------|
| `CachedMemory` dataclass | 🆕 `is_core`, `compressed`, `keywords`, `last_injected_at` 字段 |
| `from_orm()` | 映射新字段 |
| `to_dict()` | 透传新字段，`last_injected_at` 用 `.isoformat()` |

### `backend/models.py`

AgentMemory 类追加 4 个 Column 定义。

## 关键词提取算法

```
输入: "用户不喜欢弹窗交互，偏好极简设计"
→ 中文双字: ["用户", "户不", "不喜", "喜欢", "欢弹", "弹窗", "窗交", "交互", "互偏", "偏好", "好极", "极简", "简设", "设计"]
→ 英文单词: []（无英文）
→ 数字: []（无数字）
→ Counter → 过滤停用词 + 单字 → 输出: ["弹窗", "偏好", "极简", "交互", "设计"]
```

## 迁移脚本

`scripts/migrate_v15_memory_pool.py`：幂等执行

```bash
cd ~/zuoshanke && .venv/bin/python scripts/migrate_v15_memory_pool.py
```

Step 1: ALTER TABLE ADD COLUMN × 4（检测已存在则跳过）
Step 2: 标记 base_weight >= 8 且 scope='zhu' 的记忆为 is_core=True
Step 3: 为所有 scope='zhu' 的记忆提取 keywords

## 已知陷阱

### trap 1: patch 工具部分读取后失效

`patch` 工具在文件被 `read_file(offset/limit)` 部分读取后打补丁会有 warning。重读全文件后再 patch 可解决。如果发现改动未生效，检查 `git diff` 确认文件是否更改。

### trap 2: last_injected_at 序列化必须统一

两套序列化路径必须都用 `.isoformat()`：
- `memory_cache.py:CachedMemory.to_dict()` → 缓存层
- `memory_manager.py:_to_dict()` → 管理层

混用 `str()` 和 `.isoformat()` 会导致消费端拿到不同格式。

### trap 3: keywords 在修正后过时

`record_correction()` 修改了记忆内容但之前不会重提取 keywords。v1.5 已在 correction 路径追加 `self.extract_keywords(new_content)`。

### trap 4: `add()` 不支持 `is_core` 导致多余 commit

旧模式：`mm.add(...) → new_mem.is_core=True → mm.update(key, is_core=True)`（两次 commit）
新模式：`mm.add(is_core=True)`（一次 commit）

## 文件索引

```
docs/design/schema-v1.5.md                     # 完整设计文档
scripts/migrate_v15_memory_pool.py             # 迁移脚本（幂等）
backend/models.py                              # AgentMemory 表（4 新字段 L308-312）
backend/agent_core/memory_manager.py           # extract_keywords + add(is_core) + correction 重提 kw
backend/agent_core/memory_cache.py             # CachedMemory 同步
scripts/import_hermes_memory_to_zhu.py         # 导入脚本支持 is_core
```
