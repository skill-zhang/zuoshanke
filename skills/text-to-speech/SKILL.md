---
name: text-to-speech
description: 文本转语音（TTS）工具 — 基于 Edge TTS（免费，无需 API Key），支持中英日韩多语种，输出 MP3 音频文件
version: 1.0
category: system
triggers: [朗读, 读出来, 语音, 语音合成, TTS, 念给我听, 播报, 发声, 帮我读, 阅读文章, speak, text to speech, tts, read aloud]
---

# 文本转语音（TTS）

## 配套工具

坐山客内置了 `text_to_speech` 工具（⚙️ 系统分类），输入文本即可合成语音：

```bash
# 中文女声（默认）
text_to_speech(text="你好，今天天气真好")

# 中文男声
text_to_speech(text="欢迎使用坐山客", voice="zh-CN-YunxiNeural")

# 英语女声
text_to_speech(text="Hello, welcome to Zuoshanke!", voice="en-US-AriaNeural")

# 加快语速
text_to_speech(text="这段文字读快一点", speed="30")
```

## 支持的语音

| 语音名称 | 标签 | 语言 |
|----------|------|------|
| zh-CN-XiaoxiaoNeural | 中文女声 (晓晓) | 🇨🇳 中文 |
| zh-CN-YunxiNeural | 中文男声 (云希) | 🇨🇳 中文 |
| zh-CN-XiaohanNeural | 中文女声 (晓涵-活泼) | 🇨🇳 中文 |
| zh-CN-YunjianNeural | 中文男声 (云健-沉稳) | 🇨🇳 中文 |
| en-US-AriaNeural | 英语女声 (Aria) | 🇺🇸 英语 |
| en-US-GuyNeural | 英语男声 (Guy) | 🇺🇸 英语 |
| en-GB-SoniaNeural | 英式女声 (Sonia) | 🇬🇧 英语 |
| ja-JP-NanamiNeural | 日语女声 (Nanami) | 🇯🇵 日语 |
| ko-KR-SunHiNeural | 韩语女声 (Sun-Hi) | 🇰🇷 韩语 |

## 返回值说明

工具返回 JSON，包含以下字段：

- `success` — 布尔值，是否成功
- `audio_path` — 生成的 MP3 文件绝对路径
- `duration_sec` — 估计的音频时长（秒）
- `voice` / `voice_label` — 使用的语音名称和标签
- `text_length` — 文本字符数
- `file_size_bytes` — 文件大小

## 注意事项

- 需要网络连接（Edge TTS 为云端服务）
- 文本最多 5000 字符，超出自动截断
- 音频文件保存在 `data/tts_output/` 目录
- 依赖库：`edge-tts`（已预装）
