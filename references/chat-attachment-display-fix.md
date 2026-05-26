# 聊天附件显示修复 — 文件/图片在消息气泡中呈现

## 问题

用户上传图片/文件后，附件在发送预览条中可见，但发送后的消息气泡和历史聊天记录中不显示附件。

## 根因（3 层）

### 第 1 层：MessageBubble 不渲染附件

`frontend/src/components/ChatView.tsx` — `MessageBubble` 组件只渲染了：
- toolCards / toolLogs
- asset card / outputRef card
- markdown content
- map_ref button
- model name

**没有渲染 `msg.attachments`。**

修复：在 ReactMarkdown 后、map_ref 前插入附件渲染块。
- `file_type === 'image'` → inline `<img>`，max-width 100%，点击新标签打开
- 其他 → 📄 文件卡片（output-ref-card 风格）+ ↗ 打开按钮
- 图片加载失败 → onError 自动隐藏

### 第 2 层：SSE `user_msg` 事件携带附件

前后端在流式发送中通过 SSE 事件同步消息状态。SSE `user_msg` 事件不含 `attachments` 字段：

```python
# ❌ 原来
yield sse_event("user_msg", id=user_msg.id, role="user",
                content=user_msg.content, created_at=iso_utc(user_msg.created_at))

# ✅ 修复后
attachments_json = json.loads(user_msg.file_attachments) if user_msg.file_attachments else None
yield sse_event("user_msg", id=user_msg.id, role="user",
                content=user_msg.content, created_at=iso_utc(user_msg.created_at),
                attachments=attachments_json)
```

涉及文件：`channels.py` + `scene_stream.py`

### 第 3 层（最关键）：历史 API 序列化丢失附件

`GET /api/channels/{id}/messages` 和 `GET /api/scenes/{id}/messages` 使用：

```python
MessageOut.model_validate(m).model_dump()
```

其中 `m` 是 SQLAlchemy `Message` 对象。问题：

1. **字段名不匹配** — `MessageOut.attachments` vs SQLAlchemy `Message.file_attachments`
   Pydantic v2 `from_attributes=True` 用 `getattr(m, 'attachments')`，但 SQLAlchemy 模型没有 `attachments` 属性，只有 `file_attachments`。结果永远取到 `None`。

2. **类型不匹配** — `file_attachments` 列是 TEXT（存 JSON 字符串如 `'[{"url":"...","file_type":"image","filename":"x.jpg"}]'`），但 `MessageOut.attachments` 期望 `Optional[list[dict]]`。即使能读到值，字符串直接赋给 `list[dict]` 字段会验证失败。

**修复（`schemas.py`）：**

```python
attachments: Optional[list[dict]] = Field(default=None, alias='file_attachments')

@field_validator('attachments', mode='before')
@classmethod
def parse_file_attachments(cls, v):
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return v

class Config:
    from_attributes = True
    populate_by_name = True  # 允许 JSON 输入用 'attachments'
```

## 涉及文件

| 文件 | 改动 |
|------|------|
| `frontend/src/api/client.ts` | StreamEvent.user_msg 加 attachments 字段 ✅（已存在，验证通过） |
| `frontend/src/components/ChatView.tsx` | MessageBubble 渲染附件（图片行内 + 文档卡片） ✅ |
| `frontend/src/stores/appStore.ts` | sendSceneMsg/sendChannelMsg 乐观更新 + user_msg handler merge attachments ✅ |
| `frontend/src/index.css` | .msg-attachment-image / .msg-file-card 等样式 ✅（已存在） |
| `backend/schemas.py` | MessageOut.attachments 加 alias + validator ✅ |
| `backend/router/channels.py` | SSE user_msg 事件带 attachments ✅ |
| `backend/router/scene_stream.py` | SSE user_msg 事件带 attachments ✅ |

## 验证

- 发送图片：气泡中行内显示，点击新标签打开
- 发送文档：📄 文件卡片 + ↗ 打开按钮
- 刷新后重载历史：附件仍然可见
- 老消息（无附件）：attachments=null 安全不渲染
- Vite build: ✓ built in 1.83s
- Python backend: 全语法检查通过
