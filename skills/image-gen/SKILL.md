---
name: image_gen
description: AI 图片生成 — 文字描述生成图片。支持多种尺寸和风格，免费、无需 API Key
version: 1.0
category: data
triggers: [画, 生成图片, 图片, 插图, 画一个, 给我画, 帮我画, 画一张, 图, 做图, 设计图, 图像, 插画, 壁纸, 头像, 海报, create image, generate, draw, painting, 涂鸦]
---

# AI 图片生成

## 配套工具

坐山客内置了 `image_gen` 工具（📊 数据分类），把你的想象变成图片：

```bash
# 基础用法
image_gen(prompt="一只可爱的小猫坐在樱花树下")

# 指定尺寸
image_gen(prompt="日落海滩", size="1024x1024")

# 指定风格
image_gen(prompt="未来城市夜景", style="cyberpunk")
image_gen(prompt="山水画", style="ink_wash")
image_gen(prompt="动漫少女", style="anime")
image_gen(prompt="油画风景", style="oil_painting")

# 组合使用
image_gen(prompt="龙在云端飞翔", size="1792x1024", style="realistic")
```

## 支持尺寸

| 尺寸 | 宽高比 | 适用场景 |
|------|--------|---------|
| 256×256 | 1:1 | 头像、缩略图 |
| 512×512 | 1:1 | 社交分享 |
| 1024×1024 | 1:1 | 默认，高质量 |
| 1792×1024 | 16:9 | 横屏壁纸、海报 |
| 1024×1792 | 9:16 | 手机壁纸、竖屏 |

## 支持风格

| 风格 | 说明 |
|------|------|
| realistic | 📷 照片级真实风格 |
| anime | 🎀 日式动漫风格 |
| oil_painting | 🎨 油画风格 |
| watercolor | 💧 水彩画风格 |
| sketch | ✏️ 素描风格 |
| 3d_render | 🎲 3D 渲染风格 |
| pixel_art | 🕹️ 像素画风格 |
| cartoon | 🥜 卡通风格 |
| cyberpunk | 🌃 赛博朋克 |
| ink_wash | 🖌️ 水墨画风格 |

## 注意事项

- 基于 Pollinations.ai 免费 API，无需 API Key
- 需要网络连接
- 生成速度取决于网络情况，通常 10-30 秒
- 如果 AI 生成服务暂时不可用，会自动生成文字占位图
- 图片保存到 `data/images/` 目录
