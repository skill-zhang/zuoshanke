# 工作台 Avatar 对话回应系统 — 完整实现参考 (Phase 1 + 2)

## 架构

```
用户输入 → 工作台聊天栏 → SSE POST /api/workbench/chat
  │
  ├─ Phase 1: Avatar 回话
  │   ZhuAgentManager.update_mood("speaking", "")
  │   → 轻量 LLM 调用 (call_llm_stream, channel路由, temp=0.5, max_tokens=200)
  │   → yield speech:token → 流回前端字幕条
  │   → speech:done → ZhuAgent.update_mood("amused", "")
  │
  └─ Phase 2: 意图解析 + 执行操作
      ZhuAgent.update_mood("thinking", "分析你的需求…")
      → 二次 LLM 调用 (call_llm, temp=0.1, max_tokens=800)
      → 场景列表作为 context 注入 prompt
      → _parse_actions 3 层容错解析 JSON
      → _execute_action 逐一执行（不独立 commit）
      → db.commit() 统一提交
      → yield action:reload → 前端 loadScenes()
      → yield done
```

## SSE 事件序列

| 事件 | 数据 | 说明 |
|------|------|------|
| `speech:token` | `{ text: "好的" }` | 逐 token 推送，字幕逐字显示 |
| `speech:done` | `{ text: "好的，我来调整顺序" }` | Avatar 说完，字幕保持 |
| `reorder` | `{ scene_id, new_position }` | Phase 2 执行的操作事件 |
| `action:reload` | `{}` | 触发前端 `loadScenes()` |
| `done` | `{}` | 全流程完成，3s 后字幕消失 |

## 文件清单

| 文件 | 作用 |
|------|------|
| `backend/router/workbench_chat.py` | SSE 端点，Phase 1 + 2 全链路 |
| `frontend/src/components/WorkbenchView.tsx` | SSE 连接 + 字幕条 + 忙锁 + 刷新 |
| `frontend/src/components/AgentCharacter.tsx` | `agentSpeaking` 嘴动画 + 气泡抑制 |
| `frontend/src/stores/appStore.ts` | `agentSpeaking: boolean` + `setAgentSpeaking` |
| `frontend/src/index.css` | `.wb-subtitle-wrapper/bar/text/name/hidden` |
| `docs/design/workbench-avatar-speech.md` | 完整设计文档 |

## 关键 CSS

```css
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
```

## 🔴 陷阱清单

### 陷阱1: LLM 声称已执行而非仅回复
- **修复**: prompt 加 ⚠️ 警告 + 正反案例
  ```python
  "⚠️ 重要：不要声称已经完成了任何操作——"
  "你只是收到了请求，后续会由系统执行。"
  "例如，用户说「调整顺序」，回复「好的，我来调整一下顺序」"
  "而不是「已经调整好了」。"
  ```

### 陷阱2: 气泡与字幕同时显示
- **根因**: ZhuAgent 设了 observation → AgentCharacter 3s 轮询 → 气泡弹出
- **后端修复**: `zhu.update_mood("amused", "")` — observation 设空
- **前端冗余**: `bubbleShow && !agentSpeaking` 双保险

### 陷阱3: 字幕挤压卡片网格
- **修复**: `height: 0; overflow: visible` wrapper + `position: absolute` 浮动

### 陷阱4: 事务边界不统一
- **根因**: `_execute_action` 内每个操作独立 `db.commit()`，部分失败不可回滚
- **修复**: 函数内不 commit，调用方 `try/commit/rollback` 统一事务

### 陷阱5: 快速连续输入竞态
- **根因**: 多次 SSE 请求并行执行，意图解析 + 操作同时进行
- **修复**: 前端 `processingRef` 忙锁，处理中拒绝新请求，字幕提示 "⏳ 上一个任务还在处理"

### 陷阱6: 客户端断连导致 GeneratorExit
- **根因**: 用户在 SSE 流中断开，Python 抛出 `GeneratorExit`（不继承 Exception），`yield done` 不执行
- **修复**: 所有 yield 点包裹 `try/except GeneratorExit: return`，DB commit 不回滚

## Phase 2 意图解析 prompt

```python
intent_prompt = (
    f"你是一个工作台管理助手。工作台当前场景列表（按显示顺序）：\n{scene_list}\n\n"
    f"用户说：{req.content}\n\n"
    "理解用户意图，返回 JSON 格式的操作列表。\n\n"
    "支持的操作类型：\n"
    "- reorder: 调整场景顺序，需指定 scene_id + new_position（从0开始）\n"
    "- pin: 将场景添加到工作台 (show_on_workbench=true)\n"
    "- unpin: 从工作台移除场景 (show_on_workbench=false)\n"
    "- update: 更新场景的 scene_config，需指定 scene_id + config dict\n\n"
    '返回格式：{"actions": [{"type": "reorder", "scene_id": "...", "new_position": 0}]}'
)
```

## 安全保护机制

| 机制 | 实现位置 | 触发条件 |
|------|---------|---------|
| 事务原子性 | `_generate_speech` try/commit/rollback | 多操作中某步异常 |
| 忙锁 | 前端 `processingRef` | 第二道指令在 SSE 流未结束时 |
| GeneratorExit 兜底 | `except GeneratorExit: return` | 客户端断连 |
| 气泡抑制 | 后端设空 observation + 前端 `!agentSpeaking` | 说话期间 |
| prompt 诚实性 | 正反案例引导 | LLM 声称已执行 |
