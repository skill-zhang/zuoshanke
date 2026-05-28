---
name: calculator
description: 计算器 & 单位换算 — 长度/重量/温度/体积/面积/速度/数据/时间/压力/能量换算 + 数学计算 + 日期计算
version: 1.0
category: data
triggers: [计算, 换算, 转换, 等于, 多少, 多大, 多重, 几天, 多少天, 年龄, 倒计时, 公式, 面积, 体积, 速度, 温度, 压力, 热量, 卡路里, 汇率, 单位, calculator, convert, calculate, countdown, 日期差, 多少岁]
---

# 计算器 & 单位换算

## 配套工具

坐山客内置了 `calculator` 工具（📊 数据分类），三种模式：

### 单位换算

```bash
calculator(mode="convert", value=100, from_unit="cm", to_unit="m")
calculator(mode="convert", value=1, from_unit="kg", to_unit="斤")
calculator(mode="convert", value=25, from_unit="c", to_unit="f")
calculator(mode="convert", value=1, from_unit="GB", to_unit="MB")
calculator(mode="convert", value=1, from_unit="亩", to_unit="平方米")
calculator(mode="convert", value=100, from_unit="大卡", to_unit="kJ")
```

### 数学计算

```bash
calculator(mode="calc", expression="12 * 3 + 5")
calculator(mode="calc", expression="sqrt(144)")
calculator(mode="calc", expression="2**10")
```

### 日期计算

```bash
# 今天日期
calculator(mode="date", operation="today")
# 日期差
calculator(mode="date", operation="diff", date1="2026-01-01", date2="2026-12-31")
# 日期加减
calculator(mode="date", operation="add", date="2026-05-28", amount=7, unit="天")
# 年龄
calculator(mode="date", operation="age", birthday="1995-05-28")
# 倒计时
calculator(mode="date", operation="countdown", target_date="2027-01-01")
```

### 列出所有单位

```bash
calculator(mode="list")
```

## 支持的换算类别

| 类别 | 包含单位 |
|------|---------|
| 📏 长度 | mm/cm/m/km/英寸/英尺/码/英里/里/丈/尺/寸 |
| ⚖️ 重量 | mg/g/kg/吨/斤/两/磅/盎司 |
| 🌡 温度 | ℃/℉/K |
| 🫗 体积 | ml/升/立方米/加仑/杯/汤匙/茶匙 |
| 📐 面积 | ㎡/km²/公顷/亩/平方英尺/英亩 |
| 🚗 速度 | m/s/km/h/mph/节 |
| 💾 数据 | bit/B/KB/MB/GB/TB |
| ⏱ 时间 | ms/秒/分钟/小时/天/周/月/年 |
| 💨 压力 | Pa/kPa/MPa/bar/atm/mmHg/psi |
| 🔥 能量 | J/kJ/cal/kcal/kWh/eV |

## 注意事项

- 纯 Python 实现，无需网络，无需 LLM
- 温度换算使用精确公式（非近似值）
- 日期计算考虑闰年/大小月
