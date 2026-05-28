"""🎤 文本转语音（TTS）— 基于 Edge TTS（免费，无需 API Key）

支持中英文语音合成，默认使用中文女声（zh-CN-XiaoxiaoNeural），
输出为 MP3 格式文件，返回文件路径供播放。

## 用法
    from tools.text_to_speech import text_to_speech
    r = json.loads(text_to_speech("你好，世界"))
    r = json.loads(text_to_speech("Hello world", voice="en-US-AriaNeural"))

## 支持的语音
中文语音：
- zh-CN-XiaoxiaoNeural  (女声，默认)
- zh-CN-YunxiNeural     (男声)
- zh-CN-XiaohanNeural   (女声，活泼)
- zh-CN-YunjianNeural   (男声，沉稳)

英文语音：
- en-US-AriaNeural      (女声)
- en-US-GuyNeural       (男声)
- en-GB-SoniaNeural     (英式女声)
"""

import asyncio
import json
import os
import traceback
from pathlib import Path

# ── 默认值 ──
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
OUTPUT_DIR = str(Path.home() / "zuoshanke" / "data" / "tts_output")
MAX_TEXT_LENGTH = 5000  # edge-tts 实际限制

# ── 支持的语音 → 语言映射（供 UI 展示） ──
SUPPORTED_VOICES = {
    "zh-CN-XiaoxiaoNeural": {"label": "中文女声 (晓晓)", "lang": "zh-CN"},
    "zh-CN-YunxiNeural":    {"label": "中文男声 (云希)", "lang": "zh-CN"},
    "zh-CN-XiaohanNeural":  {"label": "中文女声 (晓涵-活泼)", "lang": "zh-CN"},
    "zh-CN-YunjianNeural":  {"label": "中文男声 (云健-沉稳)", "lang": "zh-CN"},
    "en-US-AriaNeural":     {"label": "英语女声 (Aria)", "lang": "en-US"},
    "en-US-GuyNeural":      {"label": "英语男声 (Guy)", "lang": "en-US"},
    "en-GB-SoniaNeural":    {"label": "英式女声 (Sonia)", "lang": "en-GB"},
    "ja-JP-NanamiNeural":   {"label": "日语女声 (Nanami)", "lang": "ja-JP"},
    "ko-KR-SunHiNeural":    {"label": "韩语女声 (Sun-Hi)", "lang": "ko-KR"},
}


def _ensure_output_dir() -> str:
    """确保输出目录存在，返回路径"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


def text_to_speech(text: str, voice: str = DEFAULT_VOICE, speed: str = "0") -> str:
    """文本转语音，返回 JSON 字符串

    Args:
        text:       要合成的文本（最多 5000 字符）
        voice:      语音名称，默认为 zh-CN-XiaoxiaoNeural
        speed:      语速调整，范围 -100~100，默认 0（正常），正数加快，负数减慢

    Returns:
        JSON string:
        {
            "success": true/false,
            "audio_path": "/path/to/output.mp3",  # 成功时
            "duration_sec": 3.5,                   # 成功时，估计时长
            "voice": "zh-CN-XiaoxiaoNeural",
            "text_length": 5,
            "error": "错误信息"                     # 失败时
        }
    """
    try:
        if not text or not text.strip():
            return json.dumps({"success": False, "error": "文本不能为空"}, ensure_ascii=False)

        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH]
            truncated = True
        else:
            truncated = False

        # 参数校验
        if voice not in SUPPORTED_VOICES:
            voice = DEFAULT_VOICE

        # 语速参数转 edge-tts 格式（+0% / -10% 等）
        try:
            speed_val = int(speed)
            speed_str = f"+{speed_val}%" if speed_val >= 0 else f"{speed_val}%"
        except (ValueError, TypeError):
            speed_str = "+0%"

        # 生成输出文件名
        out_dir = _ensure_output_dir()
        # 用 text 前 20 字符做文件名 hash
        text_hash = str(hash(text.strip()[:40]))[-8:]
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tts_{timestamp}_{text_hash}.mp3"
        output_path = os.path.join(out_dir, filename)

        # 调用 edge-tts
        async def _synthesize():
            import edge_tts
            communicate = edge_tts.Communicate(text, voice, rate=speed_str)
            await communicate.save(output_path)

        asyncio.run(_synthesize())

        # 检查输出文件
        if not os.path.exists(output_path):
            return json.dumps({
                "success": False,
                "error": "音频文件生成失败（edge-tts 未输出文件）",
            }, ensure_ascii=False)

        file_size = os.path.getsize(output_path)

        # 粗略估计时长（基于文件大小估算，MP3 ~16kbps 压缩比近似）
        estimated_duration = round(file_size / 2000, 1) if file_size > 0 else 0

        result = {
            "success": True,
            "audio_path": output_path,
            "duration_sec": estimated_duration,
            "voice": voice,
            "voice_label": SUPPORTED_VOICES.get(voice, {}).get("label", voice),
            "text_length": len(text),
            "file_size_bytes": file_size,
        }
        if truncated:
            result["truncated"] = True
            result["original_length"] = len(text)

        return json.dumps(result, ensure_ascii=False)

    except ImportError as e:
        return json.dumps({
            "success": False,
            "error": f"缺少依赖库: {e}。请运行 pip install edge-tts",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"TTS 合成失败: {str(e)}",
            "detail": traceback.format_exc(),
        }, ensure_ascii=False)
