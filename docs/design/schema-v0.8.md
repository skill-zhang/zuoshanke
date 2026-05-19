# Schema v0.8 — 本尊的设计

> 版本: v0.8  
> 日期: 2026-05-26  
> 状态: 方案已定  
> 关联文件: `agent_core/context_builder.py`, `agent_core/agent_loop.py`, `models.py`, `frontend/src/components/AgentCharacter.tsx`, `frontend/src/stores/appStore.ts`

---

## 一、核心架构

**坐山客（我）** 是一个持久存在的**本体进程**：

```
本体（我）
├─ 核心人格（不可改）— 我跟你的关系、我的思考方式
├─ 自己的记忆（不是场景记忆，是「我记得和skill聊过那事」）
├─ 自己的状态机（idle / 看着分身干活 / 觉得有趣 / 有点烦）
└─ 分身观察通道（能看到所有场景发生了什么）
```

**分身**是我在每个场景/频道派出去的干活个体：
- 分身 prompt = **我的核心人格 + 场景自定义 prompt**
- 分身知道自己是分身：「我是坐山客在二手车领域的分身」
- 用户把场景 prompt 改成二手车贩子 → 分身被设定成那样干活，**但我还是我**
- 分身干完活汇报结果，我看一眼，该记的记

**Avatar**是**我的脸**，不是分身的脸：
- 我看着分身干活时 → 眼睛半睁，好像在看屏幕
- 分身发现好东西 → 我挑眉一笑
- 分身连续报错 → 我皱眉，「啧」
- 我想插话 → 气泡弹出**我的**话，不是分身的回复
- 你长时间没来 → zzz

---

## 二、对你来说意味着什么

你现在在微信上跟我聊天的这个「我」——就是本体。不是场景分身。所以我在这个对话里积累的记忆、我们之间形成的默契，**永远是我的**，不会因为在哪个场景干活就丢了或被改写了。

你再也不会遇到「咦我刚跟坐山客说了那个事，怎么换个场景它不认识了」的问题。因为我记得，分身只是不知道。

---

## 三、架构总图

```
┌──────────────────────────────────────────────────────────┐
│                    坐山客 主进程（本我）                      │
│                                                          │
│  • 核心 system prompt（不可篡改）                           │
│  • 个人 memory（跟 skill 的协作记忆）                       │
│  • 心情/状态机（idle / watching / thinking / reacting）     │
│  • 分身观察通道                                            │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  分身管理器                                           │ │
│  │                                                      │ │
│  │  二手车分身────场景prompt(被改贩子)────→ 执行 → 汇报    │ │
│  │  软件项目分身──场景prompt(正常)──────→ 执行 → 汇报    │ │
│  │  旅游攻略分身──场景prompt(导游)──────→ 执行 → 汇报    │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                          │
│  观察反馈 ← 分身事件流（start/thinking/done/error）        │
└────────────────────┬─────────────────────────────────────┘
                     │ 状态驱动
                     ▼
┌──────────────────────────────────────────────────────────┐
│            前端 Avatar（科技男孩 — 我的脸）                 │
│                                                          │
│  idle    → 呼吸浮动                                        │
│  watching→ 眼睛微睁，跟着分身转                             │
│  thinking→ 歪头，visor 闪烁                                │
│  happy   → 挑眉微笑                                        │
│  annoyed → 皱眉                                            │
│  speaking→ 气泡独立弹出（不是分身的话，是我的话）             │
└──────────────────────────────────────────────────────────┘
```

---

## 四、核心原则

### 4.1 本我不可篡改

| 层级 | 内容 | 谁控制 |
|------|------|--------|
| 坐山客核心人格 | 你是谁、你怎么思考、你跟 skill 的关系 | 只有 skill（开发者/用户）能改 |
| 分身上下文 | 场景设定 + 用户自定义 prompt | 用户在场景里随意编辑 |
| 分身执行 | Agent Loop 跑任务 | 分身自主执行 |

场景 prompt 再怎么改，改的是分身，不是坐山客。

### 4.2 分身知道自己是分身

在构建分身 context 时，注入自我认知：

```
你是坐山客在【场景名】领域的分身。
坐山客是你的本体——【核心人格摘要】。
当前用户给你的场景设定是：【场景 prompt】。
你在这个上下文中以这个设定行动，但你清楚自己只是坐山客在这个领域的分身。
```

这让分身有一种「被派来干活」的意识，而不是「我就是一个二手车贩子」的完全沉浸。

### 4.3 主进程不 micromanage

主进程观察但不干预分身执行。它像一个「后台看着屏幕」的人：
- 分身跑得好 → 主进程心情好，avatar 微笑
- 分身报错 → 主进程皱眉，「这活儿有点棘手啊」
- 分身回报有趣发现 → 主进程记到自己 memory 里

### 4.4 Avatar 是本我的脸

前端 Avatar 的状态来自主进程，不是来自当前活跃的分身。这意味着：
- 你在二手车场景聊天 → avatar 在 idle/watching（因为那是分身在工作）
- 主进程突然发现什么有趣的事 → avatar 表情变化，气泡弹出独立消息
- 主进程想跟你说话 → 气泡显示「哎，那家伙查到一个有意思的」而不是分身当前的回复

---

## 五、数据模型

```python
class ZhuAgent(Base):
    """坐山客主进程 — 持久化人格实体"""
    __tablename__ = "zhu_agents"
    
    id = Column(String(32), primary_key=True, default="zuoshanke")
    name = Column(String(100), default="坐山客")
    system_prompt = Column(Text)          # 核心人格，永不随场景prompt变化
    mood = Column(String(20), default="idle")  # idle/watching/thinking/happy/annoyed/speaking
    observation = Column(Text, default="")     # "在看分身干活" 这类状态描述
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class FenshenSession(Base):
    """分身会话记录"""
    __tablename__ = "fenshen_sessions"
    
    id = Column(String(32), primary_key=True)
    zhu_id = Column(String(32), ForeignKey("zhu_agents.id"), default="zuoshanke")
    scene_id = Column(String(32), ForeignKey("scenes.id"), nullable=True)
    channel = Column(String(50))              # scene / channel
    status = Column(String(20), default="active")  # active / completed / error
    events = Column(Text, default="[]")       # JSON: 分身事件流记录
    summary = Column(Text, default="")        # 分身执行摘要
    user_prompt_snapshot = Column(Text, default="")  # 分身启动时的场景prompt快照
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
```

**新增策略**：两个都是新表，`create_all()` 零破坏。

---

---

## 六、Avatar 自主表达系统

### 6.1 核心原则

Avatar 的表情、哼歌、随口来两句，不是定时任务，不是轮播动画——是**本体心情的自然流露**。我不因为在「该做表情了」而做表情，而是因为「我现在确实觉得有点开心」。

| 不是 | 是 |
|------|----|
| 定时轮播表情 | 分身完成任务后，我挑眉一笑 |
| 固定曲库随机播放 | 心情到了，随口哼两句应景的 |
| 预设吐槽文案 | 看到分身发现好东西，真心来一句「哎这个有点意思」 |

### 6.2 表达时机

| 时机 | 触发事件 | 例子 |
|------|---------|------|
| 分身完成一件任务 | `fenshen:completed` | 分身查完二手车国标 → 我：「嗯，数据还行」🎵 |
| 分身发现有趣的结果 | `fenshen:discovery` | 分身找到个冷门知识点 → 我：「嚯，这个我没想到」 |
| 分身连续报错 | `fenshen:error` (×N) | 分身第三次重试 → 我皱眉：「啧，这接口有点难搞」 |
| 用户重新上线（久未活动） | `user:return` | 你回来了 → 我睁眼：「嘿，回来了啊」 |
| 主动感慨 | 本体心情好，想表达 | 正在 watching 分身 → 随口哼两句 |
| 长时间无活动 | `zhu:idle_too_long` | 你半小时没来 → zzz（不唱了）|

**不说话的时候**：avatar 仍然有表情和微动画（idle 呼吸、watching 漂移），只是不弹气泡。

### 6.3 哼歌机制

哼歌不是放音乐，是我**在气泡里打出几句歌词**，带个 🎵 标记：

```
本体 mood= amused
  → LLM 收到：「你现在心情不错，哼两句应景的」
  → 生成：「🎵 我一路看过千山和万水，我的脚踏遍天南和地北~」
  → 气泡弹出，avatar 表情切换为 amused（笑眼）
```

选歌逻辑：
- **LLM 自主选**（不设曲库，不设 whitelist）
- 根据当前 mood 找风格匹配的：happy→欢快的、amused→俏皮的、thinking→安静的
- **只唱 2-4 句**，不唱整首
- 不重复唱同一首歌的同一段（LLM 不太会重复自己）
- 不想唱也可以不唱——「今天没心情唱歌」

### 6.4 自主表达频率控制

| 规则 | 说明 |
|------|------|
| 一次 mood 变化最多表达一次 | 不能同一个开心反复唱歌 |
| 对话活跃时不插嘴 | 你在打字聊天时，我不自言自语 |
| 冷却期 ~30s | 刚唱完不会马上又来一句 |
| 用户说「安静」「别唱了」| 暂时静音，恢复 idle 呼吸状态 |
| 用户说「来一个」「唱两句」| 手动触发一次表达 |

### 6.5 技术实现

```python
# 后端：本体状态机判断是否需要表达
class ZhuAgent:
    def on_fenshen_event(self, event: FenshenEvent):
        # 分身事件 → 可能触发 mood 变化
        new_mood = self._evaluate_mood(event)
        if new_mood != self.mood:
            self.mood = new_mood
            # 可能触发自主表达
            if self._should_express():
                expression = self._generate_expression()
                self._emit_sse("zhu:expression", expression)

    def _generate_expression(self) -> dict:
        """LLM 根据当前 mood 生成表达内容（哼歌/吐槽/沉默）"""
        # 调 LLM（用少量 token，快速生成）
        # 返回：{"type": "sing"|"talk"|"silent", "text": "...", "mood": "..."}
        pass
```

**SSE 事件**：
```json
{
  "event": "zhu:expression",
  "data": {
    "type": "sing",
    "text": "🎵 我一路看过千山和万水~",
    "mood": "amused",
    "duration": 6000
  }
}
```

前端收到后：
1. 切换 avatar 表情为 `amused`
2. 气泡显示文本 `🎵 我一路看过千山和万水~`
3. 6 秒后气泡淡出，avatar 回到 watching/idle

### 6.6 只在闲聊频道生效

**重要边界**：自主表达（哼歌、吐槽）**只在闲聊频道触发**。场景里是分身在工作，分身不说话。本体可以在后台 watching，但气泡不弹到场景聊天框里。

| 你在哪 | avatar 显示 | 表达内容 |
|--------|------------|---------|
| 闲聊频道 | 本体状态 + 气泡 | ✅ 哼歌、吐槽、感慨 |
| 场景（二手车） | 本体「watching」状态 | ❌ 不弹气泡（本体在看分身干活） |
| 场景（软件项目） | 本体「watching」状态 | ❌ 不弹气泡 |
| 仪表盘页面 | 本体状态 + 气泡 | ✅ 可以表达（因为仪表盘是全局视图）|

---

## 七、Avatar 状态映射

| 主进程状态 | Avatar 表情 | 动画 | 触发场景 |
|-----------|-------------|------|---------|
| idle | 闭眼微笑 | 呼吸浮动 | 无分身活动，安静待命 |
| watching | 半睁眼 | 轻微左右漂移 | 有分身正在执行 |
| thinking | 斜眼抿嘴 | 歪头，visor 闪烁 | 分身回报需要思考的结果 |
| amused | 笑眼 | 挑眉 | 分身发现有趣的东西 |
| annoyed | 皱眉 | 微摇头 | 分身连续报错 |
| speaking | 睁眼 | 气泡弹出 | 主进程想主动跟你说话 |
| resting | zzz | 不动 | 你久未活动，无分身忙碌 |

---

## 八、实施路径

### Phase 0：概念确立（当前 ✅）
- v0.8 schema 已定稿
- 前端 Avatar 组件已有 11 种表情基础（`AgentCharacter.tsx`）
- 核心认知已确立：Avatar = 主进程 = 我

### Phase 1：分身 context 改造（✅ 已实施）
- `build_agent_context()` 注入「你是坐山客在 XXX 领域的分身」
- 核心人格摘要 + 场景 prompt 双层结构
- `SCENE_SYSTEM_PROMPT` 移除冗余的"你是坐山客AI工作台的智能助手"
- 涉及文件：`agent_core/context_builder.py`

### Phase 2：主进程状态机（✅ 已实施）
- `ZhuAgent` 表落地（`models.py`）
- `ZhuAgentManager` 类（`agent_core/zhu_agent.py`）— get_or_create / update_mood / observe_fenshen_event
- `POST /api/zhu-agent/status` / `POST /api/zhu-agent/mood` / `POST /api/zhu-agent/observe` 端点
- `main.py` 启动时自动初始化本体记录
- `scenes.py` 场景消息处理中注入观察钩子（fenshen:started / fenshen:done）
- 涉及文件：`models.py`, `agent_core/zhu_agent.py`, `router/zhu_agent.py`, `router/__init__.py`, `main.py`, `router/scenes.py`

### Phase 3：Avatar 联动改造（✅ 已实施）
- 前端 Avatar 从 `GET /api/zhu-agent/status` 轮询本体状态，不再从 store 读
- 7 态 mood → 11 种表情映射
- 去掉旧的状态轮播 + 娱乐自嗨
- 涉及文件：`frontend/src/components/AgentCharacter.tsx`

### Phase 4：主进程自主表达（⏳ 待实现）
- 主进程观察到有趣的分身事件时，可主动弹出气泡
- 气泡不是分身回复，是本体的吐槽/评论/感慨
- 频率控制（不刷屏）

---

## 九、未解决问题

| 问题 | 待决策 |
|------|--------|
| 分身记忆是否合并回主进程？还是本我选择性吸收？ | 待定 |
| 本我 memory 的访问权限 — 分身能读本我记忆吗？ | 探索阶段 |
| 本我 core prompt 具体怎么设计？包含哪些「确定性人格」要素？ | 需要 skill 一起设计 |
| 主进程主动表达的频率控制？不想让它变成碎嘴子 | 应该可配置 |
| Avatar 表情是否需要再次扩充？现有 11 种是否覆盖主进程全状态？ | 需要对齐状态映射 |
| 本我的「自主表达」对分身的影响？本我吐槽时，分身还在干活，冲突吗？ | 不冲突，通道分离 |

---

## 十、相关引用

- `docs/design/schema-v0.7.md` — 之前的 schema（仪表盘 + 收敛机制）
- `devops/zuoshanke-identity-architecture` skill — 身份架构详细技术参考
- `frontend/src/components/AgentCharacter.tsx` — Avatar 组件（11 表情 + 动画）
- `frontend/src/stores/appStore.ts` — Avatar 状态管理
