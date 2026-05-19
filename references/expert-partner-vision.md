# 坐山客终极愿景：从答题工具到专家合伙人

> 版本：v1.0 | 日期：2026-05-21
> 核心命题：复杂问题多轮引导 → 定稿 → 拆解 → 执行
> 差距分析对话详见 2026-05-21 微信会话

---

## 一、终极目标

用户面对复杂问题时，坐山客能像咱俩（张清泉 + 坐山客 AI）互相引导一样：

```
用户：我想做一个 AI 助手
  ↓ (坐山客) 
阶段1 EXPLORE: 引导用户说清楚「给谁用」「解决什么根问题」
阶段2 FOCUS:   "根据你说的，核心目标是不是这3个？"
阶段3 CHALLENGE: "方案A快但贵，方案B稳但久，倾向哪个?"
阶段4 FINALIZE: "好，约束定了，这是最终方案"
阶段5 DECOMPOSE: "按优先级排: step1 做 X, step2 做 Y"
阶段6 EXECUTE:   Action Map 逐步推进
  ↓
用户觉得：我真的在和一个人，一个专家一起干活
```

简单问题不经过这些阶段，直接回答。

---

## 二、差距分析（2026-05-21）

| 能力 | 重要度 | 现状 | 目标 | 方案方向 |
|------|--------|-----|------|---------|
| 复杂度检测 | 🔴 关键 | ❌ 无 | 后端+LLM自动判断，用户无感知 | 入口处模型分类，不走规则层 |
| 引导阶段管理 | 🔴 关键 | ❌ 无 | 6阶段状态机驱动 | `agent_core/dialog_engine.py` 机制驱动 |
| LLM 引导角色 | 🔴 关键 | ⚠️ 追问原则 | 专家合伙人姿态 | 状态驱动 prompt，非全量注入 |
| Thinking Map 协作 | 🟡 重要 | ⚠️ 展示品 | 共同编辑 | 用户自然语言编辑节点 |
| 讨论进度持久化 | 🟡 重要 | ❌ 无 | 每阶段存快照，跨会话恢复 | `dialog_state` 表 |
| 决策信号识别 | 🟢 补强 | ⚠️ 靠泛化 | 结构化识别 | 状态机内的信号检测 |
| 跨会话承接 | 🟢 补强 | ❌ 无 | 开场自动恢复进度 | session resume 逻辑 |

**核心结论**：架子有（Agent Loop + TM + AM + Memory），但骨干流程——从入口到执行的**引导流水线**——是空的。

---

## 三、核心设计决策

### 3.1 复杂度检测：对用户不可见（2026-05-21 确认）

**原则**：用户入口保持「只有场景区分」的简单体验。复杂/简单判断由**后端+LLM**完成。

**已知教训**：之前尝试硬编码规则（关键词列表）来判断复杂度，效果不好。2026-05-21 确认放弃规则层方案，改为**模型驱动**——在用户第一轮消息进入 Agent Loop 后，LLM 自主判断当前问题复杂度并进入对应模式。

```
用户发消息
  ↓
场景 Agent Loop 启动
  ↓
LLM 自主判断: 简单(直接回答) / 复杂(进入引导模式)
  ↓
无用户感知切换
```

### 3.2 引导结构的位置：不在 system prompt

**原则**：继承「system prompt 禁捷径铁律」。引导结构是**代码机制**，不是 prompt 注入。

| ❌ 错误做法 | ✅ 正确做法 |
|------------|------------|
| 在 system prompt 写"如果复杂问题先追问再…" | `agent_core/dialog_engine.py` 状态机管理阶段 |
| 把 6 阶段行为规则写进 prompt | 阶段定义在代码，当前状态注入 prompt |
| prompt 里量化约束（"追问2-3轮"） | 状态机驱动流转，LLM 自由发挥 |

**正确层级**：
```
agent_core/dialog_engine.py
  ├─ DialogState enum (EXPLORE | FOCUS | CHALLENGE | FINALIZE | DECOMPOSE | EXECUTE)
  ├─ 每个状态的行为策略（当前阶段的引导姿态）
  ├─ 状态转移规则（什么信号触发什么转移）
  └─ 信号检测（LLM 输出 + 用户输入的语义信号）
        ↓ 输出注入
Agent Loop system prompt (只有当前状态名 + 当前阶段目标，无全量规则)
```

### 3.3 Thinking Map 协作：从展示到共创

**现状**：自动发散 → 用户看树 → 手动点节点。用户不能自然语言编辑。

**目标**：
```
用户: "把那个X节点改成Y，加一个依赖Z"
  ↓
LLM 理解意图 → 调 Thinking Map 编辑工具
  ↓
树更新 → LLM 感知变化 → 继续引导
```

**关键能力**：
- Thinking Map 编辑工具（增/删/改/链节点）
- LLM 能在引导中感知 TM 的变化
- 前端实时同步（SSE 已支持）

### 3.4 对话阶段管理（详见下方第四章）

### 3.5 跨会话承接

**现状**：Memory 只存事实，不存进度。新会话开始不提上一个会话的进度。

**目标**：
```
新会话开始
  ↓
session_search("上次讨论的AI助手方案")
  ↓
找到上一个引导状态 + 进度快照
  ↓
"上次我们讨论到 X 阶段，确定了 Y 方案，还剩 Z 待定"
```

**依赖**：dialog_state 持久化 + session_search FTS5（已实现）

---

## 四、引导阶段机详细设计（待实现）

### 4.1 状态定义

```python
from enum import Enum

class DialogPhase(str, Enum):
    IDLE        = "idle"         # 未启动 / 简单问题跳过了
    EXPLORE     = "explore"      # 开放探索：用户想解决什么根问题？
    FOCUS       = "focus"        # 聚焦收敛：确定核心目标和范围
    CHALLENGE   = "challenge"    # 方案博弈：提供选项并挑战用户
    FINALIZE    = "finalize"     # 定稿确认：确定最终方案
    DECOMPOSE   = "decompose"    # 任务拆解：确定优先级和依赖
    EXECUTE     = "execute"      # 行动执行：Action Map 推进
```

### 4.2 状态转移

```
                    ┌─────────────┐
                    │    IDLE     │
                    └──────┬──────┘
                           │ LLM 判定为复杂问题
                           ▼
                    ┌─────────────┐
        ┌──────────│  EXPLORE    │──────────┐
        │          └──────┬──────┘          │
        │                 │ 用户明确了根目标   │
        │                 ▼                  │
        │          ┌─────────────┐          │
        │          │   FOCUS     │          │
        │          └──────┬──────┘          │
        │                 │ 用户确认了核心     │
        │                 ▼                  │
        │          ┌─────────────┐          │
        │          │ CHALLENGE   │          │
        │          └──────┬──────┘          │
        │                 │ 用户做出了决策     │
        │                 ▼                  │
        │          ┌─────────────┐          │
        │          │  FINALIZE   │          │
        │          └──────┬──────┘          │
        │                 │ 用户确认方案      │
        │                 ▼                  │
        │          ┌─────────────┐          │
        │          │ DECOMPOSE   │          │
        │          └──────┬──────┘          │
        │                 │ 任务就绪         │
        │                 ▼                  │
        │          ┌─────────────┐          │
        └──────────│  EXECUTE    │──────────┘
                   └─────────────┘
                         │ 全部完成
                         ▼
                    对话结束

允许回退：EXECUTE → DECOMPOSE → FOCUS（用户改变主意）
```

### 4.3 信号检测（决定何时转移）

每个状态定义 Exit Signals：

| 当前阶段 | 进入信号 | 退出信号 |
|---------|---------|---------|
| IDLE → EXPLORE | LLM 判定复杂（非简单问答） | - |
| EXPLORE → FOCUS | 用户已描述根目标/核心问题 | 用户说"对"/"没错"/"就是这样"/明确赞同 |
| FOCUS → CHALLENGE | 核心目标和范围已收敛 | 用户确认边界 → LLM 预产2-3方案 |
| CHALLENGE → FINALIZE | 用户做出了明确选择 | 用户说"选A"/"方案1吧"/明确了 |
| FINALIZE → DECOMPOSE | 方案已定，没有修改 | 用户说"行"/"干"/"就这个"/确认 |
| DECOMPOSE → EXECUTE | 任务拆解完成 | Action Map 就绪 |
| EXECUTE → 完成 | 所有任务完成 | 用户说"好了"/"够了"/完成了 |

### 4.4 存储结构

```python
class DialogState(Base):
    __tablename__ = "dialog_state"

    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False)
    phase = Column(String, nullable=False, default="idle")
    summary = Column(Text, nullable=True)      # 当前阶段累计摘要
    decisions = Column(JSON, default=list)     # [{ phase, content, timestamp }]
    action_map_id = Column(String, nullable=True)
    started_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

---

## 五、文件索引

| 文件 | 状态 | 职责 |
|------|------|------|
| `agent_core/dialog_engine.py` | ❌ 待创建 | 引导阶段状态机 |
| `agent_core/agent_loop.py` | ⚠️ 需修改 | 集成 dialog_engine，注入 phase 到 prompt |
| `models.py` | ⚠️ 需修改 | 新增 DialogState 模型 |
| `database.py` | ⚠️ 需修改 | init_db() 同步新表 |
| `references/` | ✅ 已总结 | 本文件 |
