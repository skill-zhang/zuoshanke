"""prophet_forecast — Meta Prophet 时间序列预测配置生成器

功能：
  根据数据特征描述生成 Prophet 模型配置 + Python 代码 + 参数调优建议。
  配置生成器（非远程执行器），返回结构化的 JSON 配置方案供用户/Agent 参考。

Prophet 模型：
  y(t) = g(t) + s(t) + h(t) + ε(t)
    g(t): 趋势（分段线性/逻辑增长）
    s(t): 季节性（年/周/日，Fourier 级数）
    h(t): 节假日效应
    ε(t): 误差项（正态分布）

使用场景：
  - 用户有时间序列数据想预测未来趋势
  - 电商销量预测、网站流量预测、温度/天气预测等
  - 需要理解 Prophet 的参数含义和调优方向

作者: 坐山客工具系统
"""

import json
import math
import textwrap
from typing import Optional


def _freq_label(freq: str) -> str:
    """频率说明"""
    labels = {
        'H': '每小时', 'D': '每天', 'W': '每周',
        'M': '每月', 'Q': '每季度', 'Y': '每年',
        'B': '每个工作日', 'h': '每小时', 'd': '每天',
        'w': '每周', 'ms': '每月', 'q': '每季度',
        'y': '每年', '30min': '每30分钟', '15min': '每15分钟',
    }
    return labels.get(freq, freq)


def _seasonality_guide(data_freq: str) -> list:
    """根据数据频率推荐默认季节性"""
    guide = []
    if data_freq in ('H', 'h', '30min', '15min', 'T', 'min'):
        guide.append({
            "name": "daily_seasonality",
            "auto": True,
            "fourier_order": 6,
            "note": "高频数据自动启用日季节性"
        })
        guide.append({
            "name": "weekly_seasonality",
            "auto": True,
            "fourier_order": 3,
            "note": "推荐启用周季节性捕捉周末效应"
        })
        guide.append({
            "name": "yearly_seasonality",
            "auto": True,
            "fourier_order": 10,
            "note": "有1年以上数据时自动启用年季节性"
        })
    elif data_freq in ('D', 'd', 'B'):
        guide.append({
            "name": "yearly_seasonality",
            "auto": True,
            "fourier_order": 10,
            "note": "日数据自动启用年季节性"
        })
        guide.append({
            "name": "weekly_seasonality",
            "auto": True,
            "fourier_order": 3,
            "note": "日数据自动启用周季节性"
        })
    elif data_freq in ('W', 'w'):
        guide.append({
            "name": "yearly_seasonality",
            "auto": True,
            "fourier_order": 10,
            "note": "周数据自动启用年季节性"
        })
        guide.append({
            "name": "weekly_seasonality",
            "enabled": False,
            "note": "周数据本身已是周粒度，不建议再设周季节性"
        })
    elif data_freq in ('M', 'ms', 'Q', 'q'):
        guide.append({
            "name": "yearly_seasonality",
            "auto": True,
            "fourier_order": 6,
            "note": "月/季度数据自动启用年季节性（Fourier阶数可降低）"
        })
    return guide


def prophet_forecast(
    data_description: str = "",
    data_freq: str = "D",
    forecast_periods: int = 30,
    seasonality_mode: str = "additive",
    growth: str = "linear",
    changepoint_prior_scale: float = 0.05,
    seasonality_prior_scale: float = 10.0,
    holidays_prior_scale: float = 10.0,
    interval_width: float = 0.80,
    add_custom_seasonality: str = "",
    country_holidays: str = "CN",
    cap_value: Optional[float] = None,
    floor_value: Optional[float] = None,
    mcmc_samples: int = 0,
) -> str:
    """生成 Meta Prophet 时间序列预测配置方案

    Prophet 是 Meta（原 Facebook）开源的时间序列预测算法，
    基于加法模型分解趋势、季节性和节假日效应。
    适合有强周期性、多季节的历史数据预测。

    Args:
        data_description: 数据描述，如"某电商平台2023-2025年日销售额"
        data_freq: 数据频率。H=每小时, D=每天, W=每周, M=每月, Q=每季度, Y=每年
        forecast_periods: 预测步数（结合 freq 决定实际预测时间跨度）
        seasonality_mode: 季节性模式。additive=加法, multiplicative=乘法
        growth: 趋势类型。linear=线性分段, logistic=带容量的S曲线
        changepoint_prior_scale: 趋势灵活度(0.001~0.5)。值越大趋势变化越灵敏，默认0.05
        seasonality_prior_scale: 季节性灵活度(0.01~100)。值越大季节性越强，默认10.0
        holidays_prior_scale: 节假日灵活度(0.01~100)。值越大节假日效应越强，默认10.0
        interval_width: 预测置信区间宽度(0~1)，默认0.80
        add_custom_seasonality: 自定义季节性，JSON格式字符串
            [{"name":"月度","period":30.5,"fourier_order":5}, ...]
        country_holidays: 国家代码(ISO 3166-1 alpha-2)，生效默认节假日列表。
            常见：CN=中国, US=美国, JP=日本, KR=韩国。空字符串=不使用
        cap_value: Logistic增长时必填，饱和上限（如最大销量、最大容量）
        floor_value: Logistic增长时可选，饱和下限
        mcmc_samples: MCMC采样数(0=不使用全贝叶斯)。>0可得到更完整的不确定性估计

    Returns:
        JSON 字符串，包含:
          success, summary, config_parameters, recommended_code,
          seasonality_guide, tuning_guide, installation, references
    """
    if not data_description:
        return json.dumps({
            "success": False,
            "error": "请提供 data_description 参数，描述你的数据情况",
        }, ensure_ascii=False)

    freq_valid = ('H', 'D', 'W', 'M', 'Q', 'Y', 'B',
                  'h', 'd', 'w', 'ms', 'q', 'y',
                  '30min', '15min', 'T', 'min')
    if data_freq not in freq_valid:
        return json.dumps({
            "success": False,
            "error": f"不支持的数据频率 '{data_freq}'。支持: {', '.join(freq_valid)}",
        }, ensure_ascii=False)

    if growth == "logistic" and cap_value is None:
        return json.dumps({
            "success": False,
            "error": "Logistic 增长模式必须设置 cap_value（饱和上限）",
        }, ensure_ascii=False)

    # 配置参数
    config = {
        "growth": growth,
        "seasonality_mode": seasonality_mode,
        "changepoint_prior_scale": changepoint_prior_scale,
        "seasonality_prior_scale": seasonality_prior_scale,
        "holidays_prior_scale": holidays_prior_scale,
        "interval_width": interval_width,
        "mcmc_samples": mcmc_samples,
        "yearly_seasonality": "auto",
        "weekly_seasonality": "auto",
        "daily_seasonality": "auto",
    }

    if growth == "logistic":
        config["cap_value"] = cap_value
        if floor_value is not None:
            config["floor_value"] = floor_value

    # 季节性推荐
    season_guide = _seasonality_guide(data_freq)

    # 自定义季节性解析
    custom_seasons = []
    if add_custom_seasonality:
        try:
            custom_seasons = json.loads(add_custom_seasonality)
            if isinstance(custom_seasons, dict):
                custom_seasons = [custom_seasons]
        except json.JSONDecodeError:
            pass

    # 生成代码
    code_lines = [
        "# ── 1. 安装 ──",
        "# pip install prophet",
        "",
        "# ── 2. 导入 ──",
        "import pandas as pd",
        "from prophet import Prophet",
        "",
        "# ── 3. 准备数据 ──",
        "# 数据格式: 两列 ds (日期) 和 y (数值)",
        "# df = pd.read_csv('your_data.csv')",
        "# df['ds'] = pd.to_datetime(df['ds'])",
        "",
        "# ── 4. 初始化模型 ──",
    ]

    # 构建 Prophet 参数行
    prophet_params = []
    prophet_params.append(f"    growth='{growth}',")
    prophet_params.append(f"    seasonality_mode='{seasonality_mode}',")
    prophet_params.append(f"    changepoint_prior_scale={changepoint_prior_scale},")
    prophet_params.append(f"    seasonality_prior_scale={seasonality_prior_scale},")
    prophet_params.append(f"    holidays_prior_scale={holidays_prior_scale},")
    prophet_params.append(f"    interval_width={interval_width},")
    if mcmc_samples > 0:
        prophet_params.append(f"    mcmc_samples={mcmc_samples},")
    prophet_params.append("    yearly_seasonality='auto',")
    prophet_params.append("    weekly_seasonality='auto',")
    prophet_params.append("    daily_seasonality='auto',")

    code_lines.append("model = Prophet(")
    code_lines.extend(prophet_params)
    code_lines.append(")")
    code_lines.append("")

    # 添加节假日
    if country_holidays:
        code_lines.append(f"# ── 5. 添加{country_holidays}节假日效应 ──")
        code_lines.append(f"model.add_country_holidays(country_name='{country_holidays}')")
        code_lines.append("")

    # 自定义季节性
    for cs in custom_seasons:
        name = cs.get("name", "custom_season")
        period = cs.get("period", 30.5)
        f_order = cs.get("fourier_order", 5)
        mode = cs.get("mode", seasonality_mode)
        code_lines.append(f"# 添加自定义季节性: {name}")
        code_lines.append(
            f"model.add_seasonality(name='{name}', period={period}, "
            f"fourier_order={f_order}, "
            f"prior_scale={seasonality_prior_scale}, "
            f"mode='{mode}')"
        )
        code_lines.append("")

    code_lines.extend([
        "# ── 6. 拟合模型 ──",
        "# model.fit(df)",
        "",
        "# ── 7. 创建未来时间轴并预测 ──",
        f"# future = model.make_future_dataframe(periods={forecast_periods}, "
        f"freq='{data_freq}')",
        "# forecast = model.predict(future)",
        "",
        "# ── 8. 查看预测结果 ──",
        "# forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail()",
        "",
        "# ── 9. 可视化 ──",
        "# fig1 = model.plot(forecast)     # 整体预测图",
        "# fig2 = model.plot_components(forecast)  # 趋势/季节性分解",
    ])

    # Logisitic growth 特殊处理
    if growth == "logistic":
        code_lines.insert(-9, "# Logistic增长需在 DataFrame 中添加 cap 列")
        code_lines.insert(-8, "# df['cap'] = <饱和上限值>")
        if floor_value is not None:
            code_lines.insert(-8, "# df['floor'] = <饱和下限值>")
        code_lines.insert(-8, "")

    code_str = "\n".join(code_lines)

    # ── 调优指南 ──
    tuning_items = []

    if changepoint_prior_scale != 0.05:
        tuning_items.append({
            "parameter": "changepoint_prior_scale",
            "current_value": changepoint_prior_scale,
            "typical_range": "0.001 ~ 0.5",
            "default": 0.05,
            "effect": "控制趋势变化灵敏度。值越大，趋势跟随数据变化越紧密（过拟合风险更高）。"
                      "值越小，趋势越平滑。如果预测过于跟随短期波动，降低此值。",
            "when_to_increase": "数据有明显趋势拐点、突发事件导致的趋势变化",
            "when_to_decrease": "趋势噪声大、预测抖动厉害、希望更稳定的长期预测",
        })
    else:
        tuning_items.append({
            "parameter": "changepoint_prior_scale",
            "current_value": 0.05,
            "typical_range": "0.001 ~ 0.5",
            "default": 0.05,
            "effect": "控制趋势变化灵敏度。值越大趋势越灵活，值越小趋势越平滑。",
            "when_to_increase": "有明显趋势拐点或阶段性变化时",
            "when_to_decrease": "过度拟合短期波动时",
        })

    if seasonality_prior_scale != 10.0:
        tuning_items.append({
            "parameter": "seasonality_prior_scale",
            "current_value": seasonality_prior_scale,
            "typical_range": "0.01 ~ 100",
            "default": 10.0,
            "effect": "控制季节性成分的强度。值越大季节性越明显，值越小季节性越弱。",
            "when_to_increase": "季节性模式非常明显且稳定",
            "when_to_decrease": "季节性过度适应出现异常尖峰",
        })
    else:
        tuning_items.append({
            "parameter": "seasonality_prior_scale",
            "current_value": 10.0,
            "typical_range": "0.01 ~ 100",
            "default": 10.0,
            "effect": "控制季节性成分的强度。值越大季节性越明显。",
            "when_to_increase": "季节性模式稳定且明显时",
            "when_to_decrease": "季节性成分过度拟合时",
        })

    tuning_items.append({
        "parameter": "changepoint_range",
        "current_value": "0.8 (隐含)",
        "typical_range": "0.1 ~ 1.0",
        "default": 0.8,
        "effect": "控制趋势变化点可放置的时间范围（占历史数据比例）。"
                  "值越大，越允许在靠近时间末端的位置有变化点。",
        "note": "通过 m=Prophet(changepoint_range=0.9) 显式设置",
    })

    tuning_items.append({
        "parameter": "n_changepoints",
        "current_value": "25 (隐含)",
        "typical_range": "5 ~ 100",
        "default": 25,
        "effect": "潜在趋势变化点的数量。值越大，趋势越精细。",
        "note": "通过 m=Prophet(n_changepoints=50) 显式设置",
    })

    # 构建返回
    forecast_time_desc = f"{forecast_periods}{_freq_label(data_freq)}"

    result = {
        "success": True,
        "summary": {
            "algorithm": "Meta Prophet (Facebook Prophet)",
            "model_type": "可加时间序列分解模型",
            "data_description": data_description,
            "data_frequency": data_freq,
            "forecast_horizon": forecast_time_desc,
            "core_formula": "y(t) = g(t) + s(t) + h(t) + ε(t)",
            "components": {
                "trend": "g(t) — 分段线性/逻辑增长趋势",
                "seasonality": "s(t) — Fourier级数表达的周期性模式",
                "holidays": "h(t) — 节假日效应（脉冲 + 窗口效应）",
                "error": "ε(t) — 正态分布误差项",
            },
        },
        "config_parameters": config,
        "recommended_code": {
            "language": "Python",
            "required_package": "prophet>=1.1.5",
            "code": code_str,
        },
        "seasonality_guide": season_guide,
        "custom_seasonality": custom_seasons,
        "holidays": {
            "country": country_holidays if country_holidays else None,
            "note": "Prophet 内置全球各国节假日数据（Python holidays 库）"
                    if country_holidays else "未启用节假日",
        },
        "tuning_guide": tuning_items,
        "installation": {
            "command": "pip install prophet",
            "alternative": "conda install -c conda-forge prophet",
            "note": "Prophet 依赖 pystan（贝叶斯推理框架），首次安装较慢。"
                     "推荐在 Python 3.9-3.12 环境中安装。",
            "verify": "python -c \"from prophet import Prophet; print('OK')\"",
        },
        "common_patterns": [
            {
                "pattern": "Logistic增长（有上限）",
                "config": 'growth="logistic", cap_value=10000',
                "when": "数据有明显的饱和上限（如市场份额、用户总量上限）",
            },
            {
                "pattern": "乘法季节性",
                "config": 'seasonality_mode="multiplicative"',
                "when": "季节性幅度随趋势增长而增大（如销售额季节性随公司增长而放大）",
            },
            {
                "pattern": "严格贝叶斯不确定性",
                "config": "mcmc_samples=300, uncertainty_samples=1500",
                "when": "需要更可靠的不确定性量化，尤其是小样本场景",
            },
            {
                "pattern": "精细趋势变化",
                "config": "changepoint_prior_scale=0.2, n_changepoints=50",
                "when": "数据有多个明显的趋势拐点（如促销活动导致的阶段性变化）",
            },
            {
                "pattern": "平滑稳健趋势",
                "config": "changepoint_prior_scale=0.01",
                "when": "噪声大、数据抖动明显，希望提取长期稳定趋势",
            },
            {
                "pattern": "多季节性叠加",
                "config": 'add_custom_seasonality=[{"name":"半月","period":15,"fourier_order":3}]',
                "when": "有独特的业务周期（如半月发薪、学期制）",
            },
        ],
        "caveats": [
            "Prophet 假设历史数据充分反映未来模式 — 结构性突变（政策变化、疫情）会导致预测失效",
            "Logistic 增长需要合理设置 cap，过小或过大都会影响预测精度",
            "乘法季节性要求数据无零值或负值（对数域要求 y>0）",
            "MCMC 采样速度较慢（比 MAP 估计慢 10-100x），但不确定性更可靠",
            "缺失值处理：Prophet 自动忽略 NaN，建议日期连续（缺失日期补 NaN）",
            "Prophet 不内生处理外部回归变量（如天气、价格），可通过 add_regressor 添加",
        ],
        "references": {
            "github": "https://github.com/facebook/prophet",
            "documentation": "https://facebook.github.io/prophet/",
            "paper": "Taylor & Letham (2018) 'Forecasting at Scale'",
            "examples": "https://facebook.github.io/prophet/docs/quick_start.html",
        },
    }

    return json.dumps(result, ensure_ascii=False, indent=2)
