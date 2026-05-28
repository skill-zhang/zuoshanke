"""📱 二维码生成器 — 文本/URL/WiFi 配置转二维码图片

基于 qrcode + Pillow，生成 PNG 格式二维码图片。
适用于分享链接、文本内容、WiFi 连接信息等场景。

## 用法
    from tools.qrcode_tool import generate_qrcode
    r = json.loads(generate_qrcode("https://example.com"))
    r = json.loads(generate_qrcode("WiFi:MyNetwork", mode="wifi"))
"""

import json
import os
import traceback
from pathlib import Path

# ── 输出目录 ──
OUTPUT_DIR = str(Path.home() / "zuoshanke" / "data" / "qrcodes")

# ── 模式说明 ──
MODE_HELP = {
    "text": "纯文本或 URL",
    "wifi": 'WiFi 配置，格式：SSID:密码:加密方式(WPA/WEP/nopass)',
    "vcard": "电子名片，格式：姓名:电话:邮箱:公司",
}


def _ensure_output_dir() -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


def generate_qrcode(content: str, mode: str = "text", size: int = 10, border: int = 2) -> str:
    """生成二维码图片，返回 JSON 字符串

    Args:
        content:  二维码内容（必填）
                  text 模式：任意文本或 URL
                  wifi 模式："SSID:密码:加密方式"（如 "MyWiFi:password123:WPA"）
                  vcard 模式："姓名:电话:邮箱:公司"
        mode:     内容模式：text(默认) / wifi / vcard
        size:     二维码尺寸（模块大小），默认 10
        border:   边框宽度，默认 2

    Returns:
        JSON string:
        {
            "success": true/false,
            "image_path": "/path/to/qrcode.png",
            "content": "原始内容",
            "mode": "text",
            "display_content": "显示的内容摘要",
            "error": "错误信息"
        }
    """
    try:
        if not content or not content.strip():
            return json.dumps({"success": False, "error": "内容不能为空"}, ensure_ascii=False)

        content = content.strip()
        if len(content) > 2000:
            content = content[:2000]

        # 根据模式处理内容
        display_content = content[:60]
        qr_data = content

        if mode == "wifi":
            parts = content.split(":")
            ssid = parts[0] if len(parts) > 0 else ""
            password = parts[1] if len(parts) > 1 else ""
            auth = parts[2] if len(parts) > 2 else "WPA"
            if auth.lower() not in ("wpa", "wep", "nopass"):
                auth = "WPA"
            # WiFi 二维码格式
            qr_data = f"WIFI:T:{auth};S:{ssid};P:{password};;"
            display_content = f"WiFi: {ssid}"

        elif mode == "vcard":
            parts = content.split(":")
            name = parts[0] if len(parts) > 0 else ""
            phone = parts[1] if len(parts) > 1 else ""
            email = parts[2] if len(parts) > 2 else ""
            org = parts[3] if len(parts) > 3 else ""
            qr_data = (
                "BEGIN:VCARD\n"
                "VERSION:3.0\n"
                f"FN:{name}\n"
                f"TEL:{phone}\n"
                f"EMAIL:{email}\n"
                f"ORG:{org}\n"
                "END:VCARD"
            )
            display_content = f"名片: {name}"

        # 生成二维码
        import qrcode
        from PIL import Image

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=size,
            border=border,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # 保存
        out_dir = _ensure_output_dir()
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = str(hash(content))[-8:]
        filename = f"qrcode_{timestamp}_{content_hash}.png"
        output_path = os.path.join(out_dir, filename)

        img.save(output_path, "PNG")
        file_size = os.path.getsize(output_path)

        result = {
            "success": True,
            "image_path": output_path,
            "content": qr_data,
            "display_content": display_content,
            "mode": mode,
            "file_size_bytes": file_size,
            "dimensions": f"{img.width}x{img.height}",
        }

        return json.dumps(result, ensure_ascii=False)

    except ImportError as e:
        return json.dumps({
            "success": False,
            "error": f"缺少依赖: qrcode 或 Pillow。请运行 pip install qrcode Pillow",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"二维码生成失败: {str(e)}",
            "detail": traceback.format_exc(),
        }, ensure_ascii=False)
