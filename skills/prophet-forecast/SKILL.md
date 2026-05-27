---
name: prophet-forecast
description: Meta Prophet 时间序列预测 — 模型配置生成、参数调优指南、Python 代码片段、安装部署。适合销量/流量/温度等有强周期性的数据预测
version: 1.0
category: system
triggers: [Prophet, 时间序列, 预测, 时序预测, 销量预测, 流量预测, 趋势预测, 季节性分析, 节假日效应, 预报, forecast, time series, 未来预测, 数据预测]
---

# Meta Prophet 时间序列预测

## 配套工具

坐山客内置了 `prophet_forecast` 工具（📈 系统分类），输入数据描述即可生成完整配置方案：

```bash
# 示例：电商日销量预测
prophet_forecast(
    data_description="某电商平台2023-2025年日销售额",
    data_freq="D",
    forecast_periods=90,
    seasonality_mode="multiplicative",
    growth="logistic",
    changepoint_prior_scale=0.1,
    cap_value=500000,
    country_holidays="CN"
)
```

工具返回：模型配置、Python 代码、季节性推荐、参数调优指南、安装验证步骤。

---

## 概述

**Prophet** 是 Meta（原 Facebook）开源的时间序列预测算法，2017 年发布。
专为业务预测场景设计，对缺失值、异常值、趋势变化有较好的鲁棒性。

### 核心公式

```
y(t) = g(t) + s(t) + h(t) + ε(t)
```

| 分量 | 符号 | 说明 | 控制参数 |
|------|------|------|----------|
| 趋势 | g(t) | 分段线性或 Logistic 增长 | `growth`, `changepoint_prior_scale` |
| 季节性 | s(t) | Fourier 级数分解的年/周/日周期 | `yearly_seasonality`, `seasonality_prior_scale` |
| 节假日 | h(t) | 脉冲 + 窗口效应 | `add_country_holidays()`, `holidays_prior_scale` |
| 误差 | ε(t) | 正态分布残差 | `interval_width`, `mcmc_samples` |

### 适用场景

- ✅ 有 2 个以上完整季节周期的历史数据
- ✅ 数据有明显的日、周、年周期性
- ✅ 存在节假日效应（如春节、双11销量暴增）
- ✅ 趋势可能分段变化（产品生命周期、政策调整）
- ❌ 纯随机/白噪声序列
- ❌ 高度依赖外部变量（Prophet 可通过 `add_regressor` 扩展）
- ❌ 高频实时预测（毫秒级 tick 数据）

---

## 安装

```bash
pip install prophet
# 或
conda install -c conda-forge prophet
```

验证安装：

```bash
python -c "from prophet import Prophet; print('Prophet OK')"
```

> ⚠️ Prophet 依赖 pystan（贝叶斯推理框架），首次安装需编译 C++ 代码，耗时较长。
> 推荐 Python 3.9~3.12 环境。

---

## 快速入门

```python
import pandas as pd
from prophet import Prophet

# 1. 准备数据：必须含 ds（日期）和 y（数值）两列
df = pd.read_csv('sales.csv')
df['ds'] = pd.to_datetime(df['ds'])

# 2. 初始化模型
model = Prophet(
    growth='linear',
    seasonality_mode='multiplicative',
    changepoint_prior_scale=0.05,
    seasonality_prior_scale=10.0,
    holidays_prior_scale=10.0,
    yearly_seasonality='auto',
    weekly_seasonality='auto',
    daily_seasonality='auto',
)

# 3. 添加中国节假日效应
model.add_country_holidays(country_name='CN')

# 4. 拟合
model.fit(df)

# 5. 预测未来 90 天
future = model.make_future_dataframe(periods=90, freq='D')
forecast = model.predict(future)

# 6. 查看结果
print(forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(10))

# 7. 可视化
fig1 = model.plot(forecast)
fig2 = model.plot_components(forecast)
```

---

## 参数详解

### 趋势参数

| 参数 | 默认值 | 范围 | 作用 |
|------|--------|------|------|
| `growth` | `linear` | `linear` / `logistic` | 趋势形态。`logistic` 需设 `cap`（饱和上限） |
| `n_changepoints` | 25 | 5~100 | 潜在趋势变化点数量 |
| `changepoint_range` | 0.8 | 0.1~1.0 | 变化点可放置的历史比例 |
| `changepoint_prior_scale` | 0.05 | 0.001~0.5 | **趋势灵活度**。最关键的趋势调优参数 |

### 季节性参数

| 参数 | 默认值 | 范围 | 作用 |
|------|--------|------|------|
| `yearly_seasonality` | `auto` | bool/int | 年季节性 Fourier 阶数（默认 10） |
| `weekly_seasonality` | `auto` | bool/int | 周季节性 Fourier 阶数（默认 3） |
| `daily_seasonality` | `auto` | bool/int | 日季节性 Fourier 阶数（默认 4） |
| `seasonality_prior_scale` | 10.0 | 0.01~100 | **季节性强度** |
| `seasonality_mode` | `additive` | additive/multiplicative | 加法 vs 乘法季节性 |

### 节假日参数

| 参数 | 默认值 | 范围 | 作用 |
|------|--------|------|------|
| `holidays_prior_scale` | 10.0 | 0.01~100 | 节假日效应强度 |
| `add_country_holidays()` | — | country_name | 内置全球节假日，CN/US/JP 等 |

### 不确定性参数

| 参数 | 默认值 | 范围 | 作用 |
|------|--------|------|------|
| `interval_width` | 0.80 | 0~1 | 预测区间宽度 |
| `mcmc_samples` | 0 | 0~1000+ | 全贝叶斯采样数（0=MAP 估计） |
| `uncertainty_samples` | 1000 | — | 不确定性模拟采样数 |

---

## 调优策略

### 步骤 1：确定趋势灵活度（CHANGEPOINT_PRIOR_SCALE）

```
过小（0.001）→ 趋势太刚，跟不上数据变化
适中（0.05）  → Prophet 默认值，大多数场景适用
过大（0.5）  → 过度拟合短期波动
```

**经验法则**：通过 `plot(model, forecast)` 观察趋势线。如果趋势线几乎是一条直线→增大；如果趋势线抖动得像股票K线→减小。

### 步骤 2：确定季节性强度（SEASONALITY_PRIOR_SCALE）

- 季节性非常规律（如空调销量）→ 增大到 20~50
- 季节性不稳定（如时尚服装）→ 减小到 1~5

### 步骤 3：检查残差

```python
from prophet.diagnostics import cross_validation, performance_metrics
df_cv = cross_validation(model, initial='365 days', period='90 days', horizon='90 days')
df_p = performance_metrics(df_cv)
print(df_p[['horizon', 'mape', 'rmse', 'coverage']])
```

---

## 常见模式

| 模式 | 配置 | 适用场景 |
|------|------|----------|
| **基础线性** | `growth='linear'` | 无明显增长上限的时序 |
| **带上限增长** | `growth='logistic', cap=MAX` | 市场占有率、用户量 |
| **乘法季节性** | `seasonality_mode='multiplicative'` | 季节性幅度随趋势增长 |
| **强节假日效应** | `holidays_prior_scale=30` + `add_country_holidays('CN')` | 零售、旅游 |
| **贝叶斯不确定性** | `mcmc_samples=300` | 小样本、需要可靠置信区间 |
| **多季节性叠加** | `add_seasonality(name='半月', period=15, fourier_order=3)` | 半月/学期等独特周期 |
| **添加外部变量** | `model.add_regressor('price')` | 考虑价格、天气等影响因素 |

---

## 边界与限制

1. **结构性突变** — 如疫情、政策变化，Prophet 无法预测（用 `changepoint_prior_scale` 事后适应）
2. **零值/负值** — 乘法季节性要求 y > 0
3. **数据长度** — 至少 1 个完整周期（年季节性至少 365 天数据）
4. **长周期预测** — 超过 2-3 倍历史长度时精度急剧下降
5. **MCMC 速度** — mcmc_samples>0 比 MAP 慢 10-100 倍，生产环境慎用
6. **非线性交互** — Prophet 本质是加法分解，变量间非线性交互需预处理

---

## 参考资料

- GitHub: https://github.com/facebook/prophet
- 官方文档: https://facebook.github.io/prophet/
- 论文: Taylor & Letham (2018) "Forecasting at Scale" (American Statistician)
- 快速入门: https://facebook.github.io/prophet/docs/quick_start.html
- 案例: https://facebook.github.io/prophet/docs/quick_start.html#python-api
