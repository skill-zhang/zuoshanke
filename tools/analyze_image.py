"""图片分析工具 — 使用视觉语言模型分析图片

功能：
- analyze_image: 分析图片内容（描述、识别对象、读取文字）
- analyze_image_url: 分析网络图片

使用 Qwen VLM（通过 llama.cpp 的 /v1/chat/completions 接口，支持多模态）
或 OpenAI 兼容 API（通过环境变量 VLM_API_KEY + VLM_BASE_URL 配置）。
"""

import base64
import json
import os

# ── 配置 ──
# Qwen VLM 端点（如果本地 llama-server 加载了视觉模型）
VLM_BASE_URL = os.environ.get("VLM_BASE_URL", "http://localhost:8083/v1")
VLM_API_KEY = os.environ.get("VLM_API_KEY", "not-needed")
VLM_MODEL = os.environ.get("VLM_MODEL", "")
# 是否用本地 Qwen VLM（true=走 /v1/chat/completions 传 base64 图片）
USE_LOCAL_VLM = os.environ.get("USE_LOCAL_VLM", "0") == "1"


def _encode_image(file_path: str) -> str | None:
    """将图片文件编码为 base64"""
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return None


def _detect_image_format(file_path: str) -> str:
    """检测图片格式"""
    ext = os.path.splitext(file_path)[1].lower()
    fmt_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return fmt_map.get(ext, "image/jpeg")


def analyze_image(file_path: str, prompt: str = "请详细描述这张图片的内容") -> dict:
    """分析本地图片

    Args:
        file_path: 图片文件路径
        prompt: 分析提示词

    Returns:
        {"description": "...", "success": True/False, ...}
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}"}

    img_format = _detect_image_format(file_path)
    img_b64 = _encode_image(file_path)

    if img_b64 is None:
        return {"success": False, "error": "图片编码失败"}

    # 检查图片大小（base64 体积 ≈ 文件大小 × 1.37）
    estimated_size = len(img_b64)
    if estimated_size > 20 * 1024 * 1024:  # 20MB base64 ≈ 14MB 图片
        return {"success": False, "error": f"图片太大（约 {estimated_size//1024//1024}MB），请压缩后再试"}

    return _call_vlm_api(img_b64, img_format, prompt)


def analyze_image_url(image_url: str, prompt: str = "请详细描述这张图片的内容") -> dict:
    """分析网络图片

    注意：需要 VLM 端点的 URL 访问能力，本地 Qwen 可能通过代理。

    Args:
        image_url: 图片 URL
        prompt: 分析提示词

    Returns:
        {"description": "...", "success": True/False}
    """
    if not image_url.startswith(("http://", "https://")):
        return {"success": False, "error": "URL 格式无效"}

    return _call_vlm_api(image_url, "url", prompt)


def analyze_image_ocr(file_path: str) -> dict:
    """专门对图片做文字识别（OCR 模式）

    用 VLM 读取图片中的文字，适合截图、文档照片等

    Args:
        file_path: 图片文件路径

    Returns:
        {"text": "...", "success": True/False}
    """
    result = analyze_image(file_path, prompt="请完整读取这张图片中的所有文字内容，保持原文格式")
    return result


def _call_vlm_api(image_data: str, image_type: str, prompt: str) -> dict:
    """调用 VLM API

    Args:
        image_data: base64 字符串（本地）或 URL（网络图片）
        image_type: "image/png"/"image/jpeg"/"url" 等
        prompt: 分析提示词
    """
    # ── 构建消息 ──
    if image_type == "url":
        content = [
            {"type": "image_url", "image_url": {"url": image_data}},
            {"type": "text", "text": prompt},
        ]
    else:
        content = [
            {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{image_data}"}},
            {"type": "text", "text": prompt},
        ]

    messages = [
        {"role": "system", "content": "你是一个专业的图片分析助手，请用中文描述图片内容。"},
        {"role": "user", "content": content},
    ]

    # ── 调用 API ──
    try:
        import requests

        # 默认用本地 Qwen VLM
        if USE_LOCAL_VLM:
            api_url = f"{VLM_BASE_URL}/chat/completions"
        else:
            # 兼容 OpenAI 格式的 VLM 端点
            api_url = f"{VLM_BASE_URL}/chat/completions"

        headers = {
            "Authorization": f"Bearer {VLM_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": VLM_MODEL if VLM_MODEL else "gpt-4o-mini",
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.3,
        }

        resp = requests.post(api_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()

        data = resp.json()
        description = data["choices"][0]["message"]["content"].strip()

        return {
            "success": True,
            "description": description,
            "model": VLM_MODEL if VLM_MODEL else "auto",
        }
    except ImportError:
        return {"success": False, "error": "需要安装 requests 库"}
    except Exception as e:
        return {"success": False, "error": f"API 调用失败: {str(e)}",
                "hint": "请确认 VLM 端点可用，或设置环境变量 VLM_BASE_URL"}


# CLI 测试
if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2:
        path = sys.argv[1]
        result = analyze_image(path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("用法: python analyze_image.py <图片路径>")
        print("或设置环境变量:\n  VLM_BASE_URL=http://localhost:8083/v1 (默认)\n  VLM_MODEL=gpt-4o-mini\n  USE_LOCAL_VLM=1")
