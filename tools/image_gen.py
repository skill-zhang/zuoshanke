"""🎨 图片生成 — 基于 AI 文本生成图片

通过 Pollinations.ai API（免费，无需 API Key）将文字描述转为图片。
支持调整尺寸、风格等参数。包含自动重试和备选方案。

## 用法
    from tools.image_gen import image_gen
    r = json.loads(image_gen("一只可爱的小猫"))
    r = json.loads(image_gen("日落海滩", size="1024x1024"))
"""

import json
import os
import time
import traceback
import urllib.request
import urllib.parse
import urllib.error

# ── 输出目录 ──
OUTPUT_DIR = os.path.expanduser("~/zuoshanke/data/images")

# ── 支持的尺寸 ──
SUPPORTED_SIZES = {
    "256x256": (256, 256),
    "512x512": (512, 512),
    "1024x1024": (1024, 1024),
    "1792x1024": (1792, 1024),
    "1024x1792": (1024, 1792),
}

# ── 风格标签 ──
STYLE_HINTS = {
    "realistic": "photorealistic, highly detailed",
    "anime": "anime style, cel shading, vibrant colors",
    "oil_painting": "oil painting style, thick brush strokes",
    "watercolor": "watercolor painting, soft, transparent",
    "sketch": "pencil sketch, line art",
    "3d_render": "3D render, octane render, game asset",
    "pixel_art": "pixel art style, retro 8-bit",
    "cartoon": "cartoon style, bold outlines",
    "cyberpunk": "cyberpunk, neon lights, futuristic",
    "ink_wash": "Chinese ink wash painting, sumi-e",
}

TIMEOUT = 90
MAX_RETRIES = 2


def _generate_placeholder(prompt: str, width: int, height: int, color: tuple[int, int, int]) -> str:
    """备用方案：用 Pillow 生成一个带提示文字的占位图片"""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (width, height), color)
        draw = ImageDraw.Draw(img)

        # 尝试加载中文字体
        font = None
        for fp in ["/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]:
            try:
                font = ImageFont.truetype(fp, 20)
                break
            except Exception:
                continue

        # 文字换行
        words = prompt
        if width < 400:
            lines = [words[:20]]
        else:
            lines = []
            while words:
                lines.append(words[:30])
                words = words[30:]

        y = height // 2 - len(lines) * 15
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font) if font else draw.textbbox((0, 0), line)
            tw = bbox[2] - bbox[0]
            draw.text(((width - tw) // 2, y), line, fill=(255, 255, 255), font=font)
            y += 30

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        prompt_hash = str(hash(prompt))[-8:]
        filename = f"placeholder_{timestamp}_{prompt_hash}.jpg"
        output_path = os.path.join(OUTPUT_DIR, filename)
        img.save(output_path, "JPEG", quality=85)
        return output_path
    except ImportError:
        return ""


def image_gen(prompt: str, size: str = "1024x1024", style: str = "") -> str:
    """根据文字描述生成图片，返回 JSON 字符串

    Args:
        prompt: 图片描述词（必填），支持中英文
        size:   图片尺寸，默认 1024x1024
                可选：256x256 / 512x512 / 1024x1024 / 1792x1024 / 1024x1792
        style:  风格提示（可选），如 realistic / anime / oil_painting / cyberpunk 等

    Returns:
        JSON string:
        {
            "success": true/false,
            "image_path": "/path/to/image.jpg",
            "prompt": "原始描述",
            "size": "1024x1024",
            "file_size_bytes": 123456,
            "is_placeholder": false,   // 是否备选占位图
            "error": "错误信息"
        }
    """
    try:
        if not prompt or not prompt.strip():
            return json.dumps({"success": False, "error": "描述词不能为空"}, ensure_ascii=False)

        prompt = prompt.strip()
        if len(prompt) > 500:
            prompt = prompt[:500]

        if size not in SUPPORTED_SIZES:
            size = "1024x1024"

        width, height = SUPPORTED_SIZES[size]

        # 构建完整 prompt
        full_prompt = prompt
        if style and style in STYLE_HINTS:
            full_prompt = f"{prompt}, {STYLE_HINTS[style]}"

        # 尝试 Pollinations API（含重试）
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                encoded_prompt = urllib.parse.quote(full_prompt)
                image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"

                req = urllib.request.Request(
                    image_url,
                    headers={"User-Agent": "Zuoshanke/1.0 ImageGen"},
                )
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    image_data = resp.read()

                if image_data and len(image_data) >= 100:
                    # 保存
                    os.makedirs(OUTPUT_DIR, exist_ok=True)
                    timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
                    prompt_hash = str(hash(prompt))[-8:]
                    filename = f"img_{timestamp}_{prompt_hash}.jpg"
                    output_path = os.path.join(OUTPUT_DIR, filename)

                    with open(output_path, "wb") as f:
                        f.write(image_data)

                    return json.dumps({
                        "success": True,
                        "image_path": output_path,
                        "prompt": prompt,
                        "full_prompt": full_prompt,
                        "size": size,
                        "width": width,
                        "height": height,
                        "file_size_bytes": len(image_data),
                        "is_placeholder": False,
                    }, ensure_ascii=False)

                last_error = "生成的图片数据不完整"
            except urllib.error.HTTPError as e:
                last_error = f"API 返回 {e.code}: {e.reason}"
                if e.code == 402:
                    break  # 402 不用重试
            except urllib.error.URLError as e:
                last_error = f"网络错误: {e.reason}"

            if attempt < MAX_RETRIES:
                time.sleep(2)

        # AI 生成失败，尝试生成占位图
        placeholder_path = _generate_placeholder(prompt, width, height, (45, 55, 72))
        if placeholder_path and os.path.exists(placeholder_path):
            file_size = os.path.getsize(placeholder_path)
            return json.dumps({
                "success": True,
                "image_path": placeholder_path,
                "prompt": prompt,
                "full_prompt": full_prompt,
                "size": size,
                "width": width,
                "height": height,
                "file_size_bytes": file_size,
                "is_placeholder": True,
                "note": f"AI 生成暂时不可用（{last_error}），已生成占位图",
            }, ensure_ascii=False)

        # 全部失败
        return json.dumps({
            "success": False,
            "error": f"图片生成失败: {last_error}",
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"图片生成失败: {str(e)}",
            "detail": traceback.format_exc(),
        }, ensure_ascii=False)
