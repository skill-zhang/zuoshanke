# 自动 HTML 产出 — AI 回复中的 HTML 代码自动提取为可访问页面

## 背景

用户分身（查二手车场景）生成了一份完整的 HTML checklist，但以 markdown 代码块形式嵌在聊天回复中。用户需要手动复制→创建文件→改后缀→保存后才能使用，体验割裂。

## 方案

AI 消息保存后，自动扫描 `full_reply` 中的 ` ```html ... ``` ` 代码块，提取 HTML 内容→写文件→注册 ProjectOutput→前端渲染卡片。

## 架构

```
AI 回复 → stream_scene_message() generate()
  ↓
步骤 5: 保存 Message (ai_msg_id)
  ↓  yield "done" SSE 事件
  ↓
步骤 5.5 (🆕): 检测 HTML 代码块
  ├─ re.search(r'```html\s*\n(.*?)```', full_reply, re.DOTALL)
  ├─ 长度 > 50 字符 → 有效
  ├─ 写文件: outputs/<scene_id>/<msg_id>.html
  ├─ 创建 ProjectOutput 记录
  └─ yield "output:created" SSE 事件
  ↓
步骤 6: 记忆提取（不变）
```

### 前端处理

`sendSceneMsg()` 中处理 `output:created` 事件：
- 找到最后一条非 temp 的 AI 消息
- 附加 `outputRef: { outputId, title, filePath }`
- ChatView 中 `msg.outputRef` → 渲染 `.output-ref-card`（📄 带「↗ 打开」按钮）
- 点「打开」→ `window.open('/outputs/<file_path>', '_blank')`

## 修改文件

| 文件 | 改动 |
|------|------|
| `backend/router/scenes.py` | +import os, Path, ProjectOutput；done 事件后新增 HTML 检测块 |
| `frontend/src/api/client.ts` | Message 类型新增 `outputRef` 字段 |
| `frontend/src/stores/appStore.ts` | sendSceneMsg 新增 `output:created` 事件分支 |
| `frontend/src/components/ChatView.tsx` | msg 渲染新增 `.output-ref-card` |
| `frontend/src/index.css` | `.chat-msg` + `.chat-msg-content` 加 `min-width: 0`；新增 `.output-ref-card` 样式 |

## CSS 溢出修复

根因：flex 容器默认 `min-width: auto`，flex 子项不会收缩到内容尺寸以下。长代码行撑宽 `.chat-msg`（`max-width: 82%`）→ sidebar 被挤出。

修复：`.chat-msg { min-width: 0 }` + `.chat-msg-content { min-width: 0 }`，让 `max-width` 约束真正生效。

## 关键细节

- 正则用 `re.DOTALL` 跨行匹配
- 短 HTML（<50 字符）忽略，防止误抓单行标签
- 异常被 `try/except` 包裹，不中断 generator 主流程
- 文件名用 `ai_msg_id.html` 保证唯一
- 场景名 sanitize 后作为标题前缀
- 写文件路径：`outputs/{scene_id}/{msg_id}.html`，自动创建目录
- `/outputs/` 静态挂载点在 `main.py`（StaticFiles）

## 未来扩展

- 支持 ` ```javascript ... ``` ` 等其他语言
- 支持 LLM 通过 `run_code` 写文件后手动调 `register_output` 工具注册
