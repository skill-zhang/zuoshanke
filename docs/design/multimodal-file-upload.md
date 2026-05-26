# 多模态文件上传 — 设计与实现

## 架构概览

```
用户拖选图片/文件
    ↓
前端 HiddenInput (accept="image/*" 或 .pdf/.txt/...)
    ↓ uploadFile()
POST /api/upload  →  保存到 uploads/  →  返回 {url, file_type, filename}
    ↓
前端 attachments state → 预览条（缩略图/文件名）
    ↓  发送消息时传递
后端 MessageCreate.attachments → Message.file_attachments (JSON)
    ↓
```

## 两通道注入

### 1. 频道（闲聊）— 真正多模态
- 模型: 本地 Qwen3.5-9B (支持视觉)
- 流程: `ai_channel_chat_stream` → `format_message_content()` → 多模态 content 数组
- 图片: base64 data URI 注入到 `image_url` part
- 文档: 文本内容读取 → 注入到 text part
- 非视觉模型(DeepSeek): 降级为文本描述 `[图片: xxx.jpg]`

### 2. 场景（Agent Loop）— 文本描述
- 模型: DeepSeek (不支持视觉)
- 流程: 附件 → 文本描述 `[📷 图片: xxx.jpg]` → 拼接到 user_content → `build_agent_context_v1`
- 不走多模态 content 数组格式

## 关键文件

| 文件 | 作用 |
|------|------|
| `backend/router/upload.py` | 文件上传端点，返回 URL |
| `backend/agent_core/multimodal.py` | 多模态工具：模型视觉检测、content 格式化、base64 转换 |
| `backend/ai_engine.py` | `ai_channel_chat_stream`/`ai_channel_chat` 增加 attachments 参数 |
| `backend/router/channels.py` | 频道流式端点传递 attachments |
| `backend/router/scene_stream.py` | 场景流式端点保存 attachments + 文本描述注入 |
| `backend/schemas.py` | `MessageCreate.attachments` 字段 |
| `backend/models.py` | `Message.file_attachments` JSON 列 |
| `frontend/src/api/client.ts` | `Attachment` 接口、`uploadFile`、`sendSceneMessageStream` attachments 参数 |
| `frontend/src/stores/appStore.ts` | `sendSceneMsg`/`sendChannelMsg` attachments 参数 |
| `frontend/src/components/ChatView.tsx` | 文件选择器、预览条、发送链 |

## 模型视觉检测

`can_accept_images(provider_name, model_name)` 关键字匹配:
- qwen / qwen2 / qwen3 → True
- llava / cogvlm / internvl / minicpm → True
- gpt-4o / gpt-4-turbo → True
- claude-3 / claude-sonnet-4 → True
- gemini / pixtral → True
- deepseek → False (当前)

## 注意事项

1. **python-multipart 必须安装** — upload router 用 `UploadFile = File(...)` 需要此包
2. **后端启动用 .venv/bin/python** — 系统 Python 的 SQLAlchemy 版本可能过旧
3. **图片上限 20MB** — 超过的图片被跳过（LLM 无法处理）
4. **文档上限 10000 字符** — 仅文本类文件(.txt/.md/.json/.csv...)可读取内容
