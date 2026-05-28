---
name: express-tracking
description: 快递物流查询 — 基于快递100 API，支持 50+ 快递公司实时轨迹查询
version: 1.0
category: data
triggers: [快递, 物流, 快递单号, 查快递, 包裹, 到哪了, 物流信息, 运单, 快递查询, 物流跟踪, 快递到哪了, 我的快递, 查物流, tracking, 物流状态, 发货, 签收]
---

# 快递物流查询

## 配套工具

坐山客内置了 `express_tracking` 工具（📊 数据分类），随时查快递：

```bash
# 指定快递公司
express_tracking(tracking_no="YT1234567890", company="圆通")

# 自动识别（SF→顺丰、YT→圆通、JD→京东）
express_tracking(tracking_no="SF1234567890")
express_tracking(tracking_no="YT1234567890")
express_tracking(tracking_no="JD1234567890")

# 传中文名
express_tracking(tracking_no="1234567890", company="顺丰速运")
```

## 支持的公司（部分）

| 公司 | 编码 | 运单号前缀 |
|------|------|-----------|
| 顺丰速运 | shunfeng | SF |
| 圆通速递 | yuantong | YT |
| 申通快递 | shentong | 数字 |
| 中通快递 | zhongtong | 数字 |
| 韵达快递 | yunda | 数字 |
| 京东物流 | jd | JD |
| EMS | ems | EA~EN / VA~VH |
| 极兔速递 | jtexpress | JT |
| 德邦快递 | debang | 数字 |
| 百世快递 | huitong | 数字 |
| 天天快递 | tiantian | 数字 |
| 丹鸟物流 | danniao | 数字 |

## 输出字段

| 字段 | 说明 |
|------|------|
| `company_name` | 快递公司中文名 |
| `state` | 物流状态（在途/已揽收/已签收/派送中） |
| `is_signed` | 是否已签收 |
| `record_count` | 物流轨迹条数 |
| `records` | 完整的物流轨迹（时间+地点+描述） |

## 注意事项

- 基于快递100免费API，无需 API Key
- 需要网络连接
- 自动识别仅支持部分公司（SF/YJ/JD/EMS等前缀明显的）
- 纯数字单号建议手动指定快递公司
