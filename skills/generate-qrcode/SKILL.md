---
name: generate_qrcode
description: 二维码生成器 — 文本/URL/WiFi/电子名片转二维码 PNG 图片
version: 1.0
category: system
triggers: [二维码, 扫码, QR码, QR, 生成二维码, 扫一扫, 发二维码, 制作二维码, 二维码分享, 我的二维码, qrcode, QR code]
---

# 二维码生成器

## 配套工具

坐山客内置了 `generate_qrcode` 工具（⚙️ 系统分类），一键生成二维码 PNG 图片：

```bash
# 分享链接
generate_qrcode(content="https://zuoshanke.ai")

# WiFi 分享
generate_qrcode(content="MyWiFi:password123:WPA", mode="wifi")

# 电子名片
generate_qrcode(content="张三:13800138000:zhang@test.com:测试公司", mode="vcard")
```

## 支持的模式

| 模式 | 说明 | content 格式 |
|------|------|-------------|
| `text` | 文本或 URL（默认） | 任意文本 |
| `wifi` | WiFi 配置分享 | `SSID:密码:加密方式` |
| `vcard` | 电子名片 | `姓名:电话:邮箱:公司` |

## 输出

- `image_path` — PNG 图片文件路径
- `display_content` — 内容摘要（显示用）
- `file_size_bytes` — 文件大小
- `dimensions` — 图片尺寸

## 注意事项

- 依赖 qrcode + Pillow 库（已预装）
- 图片保存在 `data/qrcodes/` 目录
- 文本最多 2000 字符
