# 工作台 Avatar 对话回应系统 — Phase 1 实现参考

## 架构

```
用户输入 → 工作台聊天栏 → SSE POST /api/workbench/chat
  → 后端 ZhuAgentManager.update_mood("speaking", "")
  → 轻量LLM调用 (call_llm_stream, channel路由, temp=0.5)
  → yield SSE speech:token事件 → 流回前端
  → speech:done事件 → ZhuAgent.update_mood("amused", "")
  → done事件 → 前端3s后隐藏字幕
```

### 前端数据流

| SSE 事件 | 前端处理 |
|----------|---------|
| `speech:token` | `setAvatarSpeech(event.text)` ← 字幕条逐字更新 |
| `speech:done` | 字幕保持完整文本 |
| `done` | `setAgentSpeaking(false)` + `setTimeout(3000)` → 清空字幕 |

### 嘴动画

- `WorkbenchView` 在 SSE 开始前设 `setAgentSpeaking(true)`
- `AgentCharacter` 从 store 读 `agentSpeaking`
- `agentSpeaking=true` 时 200ms 间隔交替 `MOUTH.big` / `MOUTH.smile`
- `agentSpeaking=false` 时恢复 `STATE_MAP` 默认嘴形

### 气泡抑制

工作台说话时不显示气泡：
- **后端侧**: `zhu.update_mood("amused", "")` — observation 设空
- **前端侧**: `bubbleShow && !agentSpeaking` — 双保险

## 文件清单

| 文件 | 作用 |
|------|------|
| `backend/router/workbench_chat.py` | SSE 端点，轻量 LLM 调用 |
| `frontend/src/components/WorkbenchView.tsx` | SSE 连接 + 字幕条 JSX + 3s 超时 |
| `frontend/src/components/AgentCharacter.tsx` | `agentSpeaking` 嘴动画 + 气泡抑制 |
| `frontend/src/stores/appStore.ts` | `agentSpeaking: boolean` + `setAgentSpeaking` |
| `frontend/src/index.css` | `.wb-subtitle-wrapper/bar/text/name/hidden` |
| `docs/design/workbench-avatar-speech.md` | 完整设计文档 |

## 关键 CSS 结构

```css
/* 浮动覆盖层（不挤压卡片网格） */
.wb-subtitle-wrapper { position: relative; height: 0; overflow: visible; z-index: 10; }
.wb-subtitle-bar {
  position: absolute; top: -30px; left: 50%; transform: translateX(-50%);
  max-width: 520px; width: 90%;
  background: rgba(13,17,23,0.88); border: 1px solid #30363d; border-radius: 10px;
  padding: 14px 24px; text-align: center;
  transition: opacity 0.4s ease, transform 0.3s ease;
  pointer-events: none;
}
.wb-subtitle-hidden { opacity: 0; transform: translateY(-10px); pointer-events: none; }
.wb-subtitle-text { font-size: 15px; color: #c9d1d9; line-height: 1.6; min-height: 1.6em; }
.wb-subtitle-name { font-size: 11px; color: #484f58; margin-top: 5px; letter-spacing: 1px; }
```

## 🔴 陷阱清单

### 陷阱1: LLM 声称已执行而非仅回复
- **症状**: 用户说"调整顺序"，LLM 回"已经调整完毕"
- **原因**: prompt 只说"表示已收到"，LLM 本能编造"已完成"
- **修复**: prompt 加 ⚠️ 警告 + 正反案例
  ```python
  "⚠️ 重要：不要声称已经完成了任何操作——"
  "你只是收到了请求，后续会由系统执行。"
  "例如，用户说「调整顺序」，回复「好的，我来调整一下顺序」"
  "而不是「已经调整好了」。"
  ```

### 陷阱2: 气泡与字幕同时显示
- **症状**: 说话时字幕条和气泡都在
- **原因**: ZhuAgent 设了 observation → AgentCharacter 3s轮询 → 气泡弹出
- **修复(后端)**: `zhu.update_mood("amused", "")` — observation 设空
- **修复(前端冗余)**: `bubbleShow && !agentSpeaking` 双保险

### 陷阱3: 字幕挤压卡片网格
- **症状**: 字幕出现时卡片被推下，布局跳动
- **修复**: `height: 0; overflow: visible` wrapper + `position: absolute` 浮动

### 陷阱4: 长回复停留过长
- **症状**: 说完后字幕停留太久
- **修复**: `setTimeout(3000)` 固定超时，不依赖文本长度

## Phase 2 扩展点

在 `_generate_speech` 的 `yield sse_event("done")` 之前插入：

```python
# 意图解析：第二个轻量 LLM 调用
intent_prompt = f"用户说：{req.content}\n工作台有这些场景：{scene_summaries}\n返回 JSON: {{\"action\": \"reorder|pin|unpin|update\", ...}}"
# 执行场景操作
for action in parsed_actions:
    execute_via_api(action)
    yield sse_event(f"action:{action['type']}", **action['data'])
```

前端监听 `action:xxx` 事件后调 `loadScenes()` 刷新卡片。
