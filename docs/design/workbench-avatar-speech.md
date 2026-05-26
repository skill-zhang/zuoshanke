# 个人工作台 Avatar 对话回应系统

## 概述

个人工作台（Workbench）现有底部浮动聊天栏，但输入后无实际效果。本设计让 Avatar 在用户输入后**先回话（字幕）再派活（调场景 API）**，实现「本体回应你，本体让分身执行」的设计哲学。

## 核心流程

```
用户输入                             坐山客处理                          前端呈现
┌────────────────┐    SSE POST      ┌──────────────────┐    SSE event    ┌─────────────────┐
│ 工作台聊天栏    │ ─────────────→  │ 工作台 SSE 端点  │ ────────────→  │ Avatar 说字幕   │
│ "调整卡片1和2   │                 │                  │  speech:text   │ 嘴巴动 + 字幕    │
│  的顺序"       │                 │ ① 轻量 LLM 调用  │                │ 逐字显示        │
└────────────────┘                 │ ② 理解意图       │                └─────────────────┘
                                   │ ③ 生成回复文案   │                       │
                                   │ ④ 更新 ZhuAgent  │        场景 API 调用  │
                                   │    (mood+obs)    │ ──────────────────→  │
                                   │ ⑤ 场景操作       │    PATCH scene       │ 卡片更新
                                   └──────────────────┘                     ↓
                                                                     ┌─────────────────┐
                                                                     │ 卡片网格重新渲染 │
                                                                     └─────────────────┘
```

## 架构变化

### 已有可复用资产

| 资产 | 位置 | 用途 |
|------|------|------|
| `ZhuAgentManager` | `agent_core/zhu_agent.py` | 管理本体 mood（含 `speaking` 状态）+ observation |
| `GET /api/zhu-agent/status` | `router/zhu_agent.py` | 前端轮询 Avatar 状态（已有 3s 轮询） |
| `AgentCharacter.tsx` | 已有组件 | SVG Avatar 含 9 种嘴形 + 11 种眼睛 + 12 状态 |
| 场景 PATCH API | `router/scenes.py` | 改 `show_on_workbench`、`scene_config`、`workbench_position` |
| `Scene` 模型字段 | 已有 | `show_on_workbench`、`workbench_position`、`scene_config` |
| `MOUTH` 嘴形定义 | `AgentCharacter.tsx:30-40` | 9 种嘴形路径，可直接做说话动画 |

### 新增文件/端点

| 项目 | 说明 |
|------|------|
| `POST /api/workbench/chat` | SSE 端点 — 接收用户输入，流式返回 Avatar 回复 + 后续操作 |
| `WorkbenchView` 改造 | 聊天栏真实发送 + 字幕条组件 + SSE 连接 |
| `AgentCharacter` 改造 | 新增 `mode='subtitle'` 控制嘴动画 |
| 新的 `/api/workbench` 路由 | 注册到 `router/__init__.py` |

## 详细设计

### 1. 后端 SSE 端点 `POST /api/workbench/chat`

**请求**：
```json
{
  "content": "调整卡片1和卡片2的顺序",
  "scene_ids": ["scn_xxx", "scn_yyy"]
}
```

**SSE 事件流**（依次推送）：

| 事件 | 数据 | 说明 |
|------|------|------|
| `speech:start` | `{"text": "好的，知道了，调整卡片1和卡片2的排列顺序"}` | Avatar 开始说话，前端控制嘴动 + 字幕开始 |
| `speech:token` | `{"text": "好的"}` | 逐 token（或逐句）推送，字幕逐字显示 |
| `speech:token` | `{"text": "好的，知道了"}` | 继续 |
| ... | ... | ... |
| `speech:done` | `{"text": "好的，知道了，调整卡片1和卡片2的排列顺序"}` | 说话完成，关闭嘴动画 |
| `action:scene_order` | `{"scene_id": "scn_xxx", "workbench_position": 2}` | 场景排序操作 |
| `action:scene_order` | `{"scene_id": "scn_yyy", "workbench_position": 1}` | 场景排序操作 |
| `done` | `{}` | 全部完成 |

**后端处理逻辑**（伪代码）：

```
handle_workbench_chat(content, scene_ids):
    # 1. 设置本体状态为 "speaking"
    zhu_manager.update_mood("speaking", "")

    # 2. 轻量 LLM 调用 — 理解意图 + 生成回复
    #    参数：temperature=0.3, max_tokens=200
    #    prompt: "你是坐山客，用户在工作台对话中说了：{content}。
    #             工作台现有卡片：{scene_summaries}。
    #             生成一句简短的自然回复，表示已收到指令。"
    reply = llm_call(轻量prompt)
    yield SSE("speech:start", {"text": reply})
    yield SSE("speech:token", {"text": reply})
    yield SSE("speech:done", {"text": reply})

    # 3. 更新本体状态（完成说话）
    zhu_manager.update_mood("amused", reply)

    # 4. 解析意图 + 执行操作（LLM 或简单规则）
    actions = analyze_intent(content, scenes)
    for action in actions:
        execute_action(action)   # PATCH scene / reorder
        yield SSE(f"action:{action.type}", action.data)

    yield SSE("done", {})
```

### 2. 前端改造 — WorkbenchView

**字幕条组件**：Avatar 下方横贯条幅

```
┌──────────────────────────────────────┐
│          🧑‍🎤  <-- Avatar 居中        │
│  ┌────────────────────────────────┐  │
│  │ 好的，知道了，调整卡片1和卡片2  │  │  ← 字幕条
│  │ 的顺序                         │  │
│  │                    — 坐山客 —  │  │  ← 角色名
│  └────────────────────────────────┘  │
│                                      │
│  [🌤️ 今日天气]  [📋 待办]  [📊]    │  ← 卡片区
│                                      │
│  ┌────────────────────────────────┐  │
│  │ 💬 跟我说你想做什么...    [发送]│  │  ← 浮动聊天栏
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

**CSS 设计**：
```css
.wb-subtitle-bar {
  position: relative;
  margin: 8px auto 16px;
  max-width: 520px;
  padding: 12px 20px;
  background: rgba(13, 17, 23, 0.9);
  border: 1px solid #30363d;
  border-radius: 8px;
  text-align: center;
  transition: opacity 0.3s, transform 0.3s;
}
.wb-subtitle-text {
  font-size: 15px;
  color: #c9d1d9;
  line-height: 1.6;
  min-height: 1.6em;
}
.wb-subtitle-name {
  font-size: 11px;
  color: #484f58;
  margin-top: 4px;
}
.wb-subtitle-hidden {
  opacity: 0;
  transform: translateY(-8px);
  pointer-events: none;
}
```

**说话动画**：
- 字幕文字用 `useState` + `useEffect` 依次追加字符（打字机效果）
- Avatar 的 `mood='speaking'` 时触发嘴部 SVG 动画——在 `big` 和 `smile` 嘴形之间以 ~200ms 间隔切换（简单开合）
- SSE `speech:done` 后嘴停止动画

**SSE 连接管理**：
```typescript
// WorkbenchView 中
const [speakingText, setSpeakingText] = useState('');
const [isSpeaking, setIsSpeaking] = useState(false);

const sendWorkbenchMessage = async (text: string) => {
  const resp = await fetch('/api/workbench/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: text, scene_ids: workbenchScenes.map(s => s.id) }),
  });

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    // 解析 SSE 事件
    for (const line of chunk.split('\n')) {
      if (line.startsWith('data: ')) {
        const event = JSON.parse(line.slice(6));
        handleSSEEvent(event);
      }
    }
  }
};
```

### 3. AgentCharacter 改造

新增 `speaking` 动画模式——在 `AgentCharacter.tsx` 中：

```typescript
// 新增 speaking 动画状态（speech:broadcast 事件触发嘴形交替）
// 在 subtitle 模式下，bubble 不显示，仅由外部控制嘴形

// 实现方式一（推荐）：通过 prop 控制嘴动画
interface AgentCharacterProps {
  status?: AgentStatus;
  message?: string;
  hidden?: boolean;
  speaking?: boolean;  // true 时嘴巴开合动画
}

// speaking=true 时，每 200ms 交替 mouthPath = MOUTH.big / MOUTH.smile
```

或者更干净的方式：**WorkbenchView 直接控制 AgentCharacter 的 SVG mouth**，通过 ref 暴露一个 `setMouthPath` 方法。但为了解耦，走 prop 更简单。

### 4. 场景操作执行

在意图理解后，后端执行场景 API 操作：

| 意图 | 操作 | API |
|------|------|-----|
| 调整顺序 | 更新多个场景的 `workbench_position` | PATCH `/api/scenes/{id}` |
| 添加卡片 | 更新已有场景的 `show_on_workbench=true` | PATCH `/api/scenes/{id}` |
| 删除卡片 | 设置 `show_on_workbench=false` | PATCH `/api/scenes/{id}` |
| 更新数据 | 更新 `scene_config` 字段 | PATCH `/api/scenes/{id}` |
| 创建新场景 | 创建场景 + 设置到工作台 | POST `/api/scenes` + PATCH |
| 复杂操作 | 需要 Agent Loop 的，转发到场景 | POST `/api/scenes/{id}/stream` |

**简单意图**（调整顺序/钉/取消钉/更新数据）→ 直接调场景 API，无需 Agent Loop。

**复杂意图**（"帮我查一下今天天气" → 需要调天气工具 + 写 scene_config）→ 转发到场景的 Agent Loop，但 Avatar 先回"好的，我去查一下天气"。

## 实现阶段

### Phase 1 — "Avatar 会说话了"

1. 新建 `router/workbench.py` + `POST /api/workbench/chat` SSE 端点
2. 最简 LLM 调用：收到用户输入 → 更新 ZhuAgent mood='speaking' + observation → yield SSE events
3. 前端改造：聊天栏真实发送 + SSE 连接 + 字幕条组件
4. AgentCharacter 新增 `speaking` prop 控制嘴动画
5. 验证：输入→SSE 收到→字幕显示→嘴动→自动消失

### Phase 2 — "Avatar 会派活了"

1. 后端意图分析：从 LLM 回复中提取场景操作
2. 执行场景 API 操作
3. 前端收到 action 事件后重新加载场景/卡片
4. 复杂意图转发到场景 Agent Loop

### Phase 3 — "完善体验"

1. 字幕自动超时关闭（说话完成后 8-10s 淡出）
2. Avatar idle 状态无字幕
3. 多次快速输入的处理（cancel 前一次 SSE）
4. 错误处理：LLM 调用失败时 Avatar 说"我没理解，能再说一遍吗？"

## 注意事项

1. **ZhuAgent 的 45s 空闲超时**：speaking 状态会被自动 idle，需要确保 SSE 流式返回期间不断更新 `updated_at`，或临时抬高超时阈值
2. **SSE 连接中断**：用户刷新页面或切换 view 时，后台 LLM 调用不会自动停止。后端应有检测：SSE 连接断开后不再执行后续场景操作
3. **多次快速输入**：用户连续快速发送时，应取消前一次 SSE 连接（AbortController）并只处理最后一次
4. **字幕不阻塞**：字幕显示期间用户仍可在工作台点卡片或做其他操作，字幕只影响 Avatar 的嘴 + 字幕条显示
5. **Avatar 本体统一**：工作台的 Avatar 和场景空间的 Avatar 是同一个 `AgentCharacter` 组件，通过 prop 区分 `mode='subtitle' | 'bubble'`
