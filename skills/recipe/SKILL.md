---
name: recipe
description: 菜谱推荐 — 根据食材/菜名/菜系生成完整家常菜谱，含食材清单、步骤、小贴士
version: 1.0
category: data
triggers: [菜谱, 怎么做, 做菜, 做饭, 煮, 炒, 下厨, 菜, 家常菜, 食材, 好吃的, 怎么做好吃, 怎么煮, 料理, 烹饪, 想吃什么, 做饭教程, recipe, 菜单]
---

# 菜谱推荐

## 配套工具

坐山客内置了 `recipe` 工具（📊 数据分类），想吃什么都帮你搞定：

```bash
# 按已有食材推荐
recipe(ingredients="鸡蛋,番茄,葱")

# 按菜名搜索
recipe(dish="麻婆豆腐")

# 指定菜系和难度
recipe(dish="宫保鸡丁", cuisine="sichuan", difficulty="medium")

# 食材+菜名组合
recipe(ingredients="土豆,胡萝卜,牛肉", dish="土豆炖牛肉", difficulty="easy")
```

## 输出内容

| 字段 | 说明 |
|------|------|
| `dish_name` | 菜名 |
| `cuisine` | 菜系标签 |
| `difficulty` | 难度 |
| `prep_time` / `cook_time` | 准备和烹饪时间 |
| `ingredients` | 食材清单（含用量） |
| `steps` | 分步操作说明 |
| `tips` | 小贴士 |
| `nutrition` | 营养信息 |

## 支持菜系

| 代码 | 菜系 |
|------|------|
| sichuan | 🌶️ 川菜（麻辣） |
| cantonese | 🥟 粤菜（清淡鲜美） |
| jiangzhe | 🐟 江浙菜（甜鲜） |
| hunan | 🔥 湘菜（香辣） |
| northern | 🥬 北方菜（咸香） |
| japanese | 🍣 日式料理 |
| western | 🥩 西餐 |
| fusion | 🎨 创意融合菜 |

## 注意事项

- 用本地 Qwen LLM 生成菜谱，无需网络
- 如只提供食材，LLM 会自动推荐合适的菜
- 食材至少 3 种，LLM 会补充调味料
- 每道菜至少 4 个步骤
