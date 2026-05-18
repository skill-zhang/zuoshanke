"""天气获取模块 — 集成 wttr.in API，缓存 + 异常回退 + 未来一周预报 + 对话上下文注入

## 功能
- 通过 wttr.in 获取城市实时天气（免费，无需 API Key）
- 内存缓存（60s TTL），减少重复请求
- API 异常时自动回退到模拟数据
- 支持未来一周天气预报（forecast_days 参数，最多 7 天）
- 对话上下文注入：检测用户输入中的天气意图并格式化天气数据

## 用法
    from weather import get_weather, maybe_weather_context
    r = get_weather("北京")              # → 当前天气
    r = get_weather("北京", forecast_days=7)  # → 当前天气 + 7天预报
    ctx = maybe_weather_context("北京天气怎么样")  # → 格式化天气上下文
"""

import json
import random
import time
import re
import datetime
import requests
from typing import Optional

# ── 缓存 ──
_cache: dict[str, dict] = {}         # city_key → {"data": {...}, "ts": float}
CACHE_TTL = 60                       # 秒

# ── API ──
WTTR_URL = "https://wttr.in/{city}?format=j1"
TIMEOUT = 10  # 秒

# ── 回退当前天气数据（9 城市保底） ──
FALLBACK_WEATHER: dict[str, dict] = {
    "北京": {"temp": "20°C", "desc": "晴朗", "humidity": "45%", "wind": "东风 3级"},
    "上海": {"temp": "22°C", "desc": "多云", "humidity": "65%", "wind": "南风 4级"},
    "深圳": {"temp": "26°C", "desc": "阵雨", "humidity": "80%", "wind": "西南风 3级"},
    "广州": {"temp": "25°C", "desc": "多云转阴", "humidity": "75%", "wind": "东南风 3级"},
    "成都": {"temp": "19°C", "desc": "阴天", "humidity": "70%", "wind": "东北风 2级"},
    "杭州": {"temp": "21°C", "desc": "小雨", "humidity": "78%", "wind": "西北风 3级"},
    "武汉": {"temp": "23°C", "desc": "多云", "humidity": "60%", "wind": "东风 3级"},
    "南京": {"temp": "20°C", "desc": "晴朗", "humidity": "50%", "wind": "北风 2级"},
    "重庆": {"temp": "24°C", "desc": "阴天", "humidity": "72%", "wind": "静风"},
}

FALLBACK_DEFAULT = {"temp": "N/A", "desc": "未知", "humidity": "N/A", "wind": "N/A"}

# ── 回退预报数据（7 天，9 城市） ──
FALLBACK_FORECAST: dict[str, list[dict]] = {
    "北京": [
        {"date": "第1天", "high": "28°C", "low": "15°C", "desc": "晴朗", "humidity": "30%", "wind": "西北风 3级"},
        {"date": "第2天", "high": "26°C", "low": "14°C", "desc": "多云", "humidity": "35%", "wind": "北风 3级"},
        {"date": "第3天", "high": "24°C", "low": "13°C", "desc": "阴天", "humidity": "45%", "wind": "东北风 2级"},
        {"date": "第4天", "high": "25°C", "low": "14°C", "desc": "多云转晴", "humidity": "40%", "wind": "南风 2级"},
        {"date": "第5天", "high": "27°C", "low": "16°C", "desc": "晴朗", "humidity": "35%", "wind": "西南风 3级"},
        {"date": "第6天", "high": "29°C", "low": "17°C", "desc": "晴间多云", "humidity": "30%", "wind": "南风 3级"},
        {"date": "第7天", "high": "26°C", "low": "15°C", "desc": "多云", "humidity": "40%", "wind": "东南风 2级"},
    ],
    "上海": [
        {"date": "第1天", "high": "24°C", "low": "18°C", "desc": "多云", "humidity": "65%", "wind": "东风 4级"},
        {"date": "第2天", "high": "22°C", "low": "17°C", "desc": "阵雨", "humidity": "75%", "wind": "东北风 4级"},
        {"date": "第3天", "high": "21°C", "low": "16°C", "desc": "小雨", "humidity": "80%", "wind": "北风 3级"},
        {"date": "第4天", "high": "23°C", "low": "17°C", "desc": "阴转多云", "humidity": "70%", "wind": "西北风 3级"},
        {"date": "第5天", "high": "25°C", "low": "18°C", "desc": "多云", "humidity": "60%", "wind": "西南风 3级"},
        {"date": "第6天", "high": "26°C", "low": "19°C", "desc": "晴间多云", "humidity": "55%", "wind": "南风 3级"},
        {"date": "第7天", "high": "24°C", "low": "18°C", "desc": "多云转阴", "humidity": "65%", "wind": "东南风 3级"},
    ],
}

FALLBACK_FORECAST_DEFAULT = [
    {"date": "第1天", "high": "N/A", "low": "N/A", "desc": "未知", "humidity": "N/A", "wind": "N/A"},
    {"date": "第2天", "high": "N/A", "low": "N/A", "desc": "未知", "humidity": "N/A", "wind": "N/A"},
    {"date": "第3天", "high": "N/A", "low": "N/A", "desc": "未知", "humidity": "N/A", "wind": "N/A"},
    {"date": "第4天", "high": "N/A", "low": "N/A", "desc": "未知", "humidity": "N/A", "wind": "N/A"},
    {"date": "第5天", "high": "N/A", "low": "N/A", "desc": "未知", "humidity": "N/A", "wind": "N/A"},
    {"date": "第6天", "high": "N/A", "low": "N/A", "desc": "未知", "humidity": "N/A", "wind": "N/A"},
    {"date": "第7天", "high": "N/A", "low": "N/A", "desc": "未知", "humidity": "N/A", "wind": "N/A"},
]

# ── 天气描述池（用于生成第 4~7 天的模拟预报） ──
_DESC_POOL = ["晴朗", "多云", "阴天", "小雨", "阵雨", "晴间多云", "多云转晴", "阴转多云"]

# ── 英文→中文天气映射 ──
_EN_TO_CN_WEATHER = {
    "sunny": "晴朗", "clear": "晴朗",
    "partly cloudy": "多云", "partly cloudy ": "多云",
    "cloudy": "阴天", "overcast": "阴天",
    "light rain": "小雨", "light drizzle": "小雨",
    "moderate rain": "中雨", "heavy rain": "大雨",
    "rain": "雨",
    "patchy rain possible": "阵雨", "patchy rain nearby": "阵雨",
    "mist": "薄雾", "fog": "雾",
    "thunder": "雷阵雨",
}

# ── 风向缩写→中文映射 ──
_WIND_DIR_CN = {
    "N": "北风", "NNE": "东北偏北", "NE": "东北风", "ENE": "东北偏东",
    "E": "东风", "ESE": "东南偏东", "SE": "东南风", "SSE": "东南偏南",
    "S": "南风", "SSW": "西南偏南", "SW": "西南风", "WSW": "西南偏西",
    "W": "西风", "WNW": "西北偏西", "NW": "西北风", "NNW": "西北偏北",
}

# ── 对话上下文注入：城市列表 ──
KNOWN_CITIES = [
    "北京", "上海", "深圳", "广州", "成都", "杭州", "武汉", "南京", "重庆",
    "天津", "苏州", "西安", "长沙", "郑州", "东莞", "青岛", "沈阳", "宁波",
    "昆明", "大连", "厦门", "合肥", "佛山", "福州", "哈尔滨", "济南", "温州",
    "长春", "石家庄", "常州", "泉州", "南宁", "贵阳", "南昌", "太原", "烟台",
    "嘉兴", "南通", "金华", "珠海", "惠州", "徐州", "海口", "乌鲁木齐", "绍兴",
    "中山", "台州", "兰州", "保定", "镇江", "无锡", "邯郸", "洛阳",
]

EN_CITIES = {
    "beijing": "北京", "shanghai": "上海", "shenzhen": "深圳",
    "guangzhou": "广州", "chengdu": "成都", "hangzhou": "杭州",
    "wuhan": "武汉", "nanjing": "南京", "chongqing": "重庆",
    "tianjin": "天津", "suzhou": "苏州", "xian": "西安",
    "london": "伦敦", "tokyo": "东京", "new york": "纽约",
    "paris": "巴黎", "seoul": "首尔", "singapore": "新加坡",
}


def _now() -> float:
    return time.time()


def _normalize_desc(desc: str) -> str:
    """统一天气描述：去空格 + 英文翻译为中文（支持逗号分隔）"""
    desc = desc.strip().lower()
    # 先尝试整段匹配
    if desc in _EN_TO_CN_WEATHER:
        return _EN_TO_CN_WEATHER[desc]
    # 逗号分隔逐段翻译
    parts = [p.strip() for p in desc.split(",")]
    translated = []
    for p in parts:
        if p in _EN_TO_CN_WEATHER:
            translated.append(_EN_TO_CN_WEATHER[p])
        else:
            translated.append(p)
    return "，".join(translated)


def _parse_wttr_json(raw: dict) -> Optional[dict]:
    """从 wttr.in 的 JSON 响应中提取天气信息"""
    try:
        current = raw.get("current_condition", [{}])[0]
        city_info = raw.get("nearest_area", [{}])[0]
        city_name = city_info.get("areaName", [{}])[0].get("value", "未知")

        temp = current.get("temp_C", "N/A") + "°C"
        # 当前天气描述：先 normalize 再处理逗号
        raw_desc = current.get("weatherDesc", [{}])[0].get("value", "未知")
        desc = _normalize_desc(raw_desc)
        humidity = current.get("humidity", "N/A") + "%"
        wind_dir_raw = current.get("winddir16Point", "未知")
        wind_dir_cn = _WIND_DIR_CN.get(wind_dir_raw, wind_dir_raw)
        wind_speed = current.get("windspeedKmph", "0")
        wind = f"{wind_dir_cn} {wind_speed}km/h"

        result = {
            "city": city_name,
            "temp": temp,
            "desc": desc,
            "humidity": humidity,
            "wind": wind,
        }

        # 从当前时刻起跨天取 8 个 3 小时间隔时段
        weather_days = raw.get("weather", [])
        if weather_days:
            now = datetime.datetime.now()
            cur_hour = now.hour
            # 当前所属的 3 小时间隔起点
            start_slot = (cur_hour // 3) * 3
            hourly = []
            for day_data in weather_days:
                if len(hourly) >= 8:
                    break
                hourly_raw = day_data.get("hourly", [])
                for h in hourly_raw:
                    if len(hourly) >= 8:
                        break
                    raw_time = h.get("time", "0")
                    time_val = int(raw_time) if raw_time.isdigit() else 0
                    hour = time_val // 100
                    if time_val == 2400:
                        hour = 0
                    # 第一天跳过已过时段
                    if day_data is weather_days[0] and hour < start_slot:
                        continue
                    hour_str = f"{hour:02d}:00"
                    hourly.append({
                        "time": hour_str,
                        "temp": h.get("tempC", "N/A") + "°C",
                        "temp_c": h.get("tempC", "N/A"),
                        "desc": _normalize_desc(h.get("weatherDesc", [{}])[0].get("value", "未知")),
                        "humidity": h.get("humidity", "N/A") + "%",
                        "wind": f"{_WIND_DIR_CN.get(h.get('winddir16Point', '未知'), h.get('winddir16Point', '未知'))} {h.get('windspeedKmph', '0')}km/h",
                    })
            result["hourly"] = hourly

        return result
    except (IndexError, KeyError, TypeError) as e:
        print(f"[weather] JSON 解析失败: {e}")
        return None


def _parse_forecast(raw: dict, city: str, days: int) -> list[dict]:
    """从 wttr.in JSON 中提取未来多天预报。

    wttr.in j1 格式默认返回 3 天预报。如果 days > 3，
    第 4~7 天基于第 3 天数据做合理推算。
    """
    raw_weather = raw.get("weather", [])
    forecast = []

    for i, day in enumerate(raw_weather):
        if i >= days:
            break
        date = day.get("date", f"第{i+1}天")
        max_c = day.get("maxtempC", "N/A")
        min_c = day.get("mintempC", "N/A")
        avg_c = day.get("avgtempC", "N/A")

        # 从当天中午左右的 hourly 取描述、湿度、风向
        hourly = day.get("hourly", [])
        mid_hour = hourly[len(hourly) // 2] if hourly else {}
        desc = _normalize_desc(
            mid_hour.get("weatherDesc", [{}])[0].get("value", "未知")
            if mid_hour else "未知")
        humidity = (mid_hour.get("humidity", "N/A") + "%"
                    if mid_hour else "N/A%")
        wind_dir_raw = mid_hour.get("winddir16Point", "未知") if mid_hour else "未知"
        wind_dir = _WIND_DIR_CN.get(wind_dir_raw, wind_dir_raw)
        wind_speed = mid_hour.get("windspeedKmph", "0") if mid_hour else "0"
        wind = f"{wind_dir} {wind_speed}km/h"

        forecast.append({
            "date": date,
            "high": f"{max_c}°C",
            "low": f"{min_c}°C",
            "avg": f"{avg_c}°C",
            "desc": desc,
            "humidity": humidity,
            "wind": wind,
        })

    # 如果 days > API 返回的天数，模拟剩余天数
    api_days = len(raw_weather)
    if days > api_days and api_days > 0:
        last = forecast[-1]
        # 从最后一天的日期推算后续日期
        from datetime import datetime as _dt, timedelta as _td
        try:
            last_date = _dt.strptime(last["date"], "%Y-%m-%d")
        except ValueError:
            last_date = _dt.now()
        # 从最后一天的数值做微小波动
        _random = random.Random(city + "_forecast_extrapolation")
        for i in range(api_days, days):
            offset = i - api_days + 1
            ext_date = (last_date + _td(days=offset)).strftime("%Y-%m-%d")
            # 温度在 ±3°C 范围波动
            high_delta = _random.randint(-3, 3)
            low_delta = _random.randint(-3, 3)

            def _add_temp(val: str, delta: int) -> str:
                try:
                    base = int(val.replace("°C", ""))
                    return f"{base + delta}°C"
                except (ValueError, AttributeError):
                    return val

            desc = _random.choice(_DESC_POOL)
            humidity_val = _random.randint(30, 85)

            forecast.append({
                "date": ext_date,
                "high": _add_temp(last["high"], high_delta),
                "low": _add_temp(last["low"], low_delta),
                "avg": _add_temp(last["avg"], (high_delta + low_delta) // 2),
                "desc": desc,
                "humidity": f"{humidity_val}%",
                "wind": last["wind"],
            })

    return forecast[:days]


def _build_fallback_forecast(city: str, days: int) -> list[dict]:
    """构建回退预报数据"""
    fb = FALLBACK_FORECAST.get(city, FALLBACK_FORECAST_DEFAULT)
    result = []
    for i in range(min(days, len(fb))):
        entry = fb[i].copy()
        # 用占位日期替换
        if entry["date"].startswith("第"):
            entry["date"] = f"第{i+1}天"
        result.append(entry)
    # 如果 fallback 数据不够，补默认
    while len(result) < days:
        idx = len(result)
        result.append({
            "date": f"第{idx+1}天",
            "high": "N/A", "low": "N/A", "avg": "N/A",
            "desc": "未知", "humidity": "N/A", "wind": "N/A",
        })
    return result


def get_weather(city: str, forecast_days: int = 0) -> dict:
    """获取指定城市的天气信息和可选的多日预报。

    Args:
        city: 城市名称（中文或英文，如 "北京" 或 "Beijing"）
        forecast_days: 预报天数（0=仅当前天气，1~7=当前天气+预报）

    Returns:
        dict: {
            "city": str,
            "temp": str,
            "desc": str,
            "humidity": str,
            "wind": str,
            "forecast": list[dict] | None  # 当 forecast_days > 0 时
        }
    """
    key = city.strip()

    # 1. 检查缓存（仅对 forecast_days=0 的情况使用缓存，否则重新请求）
    #    简化处理：只要请求预报就走 API，不用缓存
    if forecast_days == 0:
        cached = _cache.get(key)
        if cached and (_now() - cached["ts"] < CACHE_TTL):
            return cached["data"]

    # 2. 调用 wttr.in API
    try:
        url = WTTR_URL.format(city=key)
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        raw = resp.json()
        parsed = _parse_wttr_json(raw)

        if parsed:
            parsed["city"] = key
            # 解析预报
            if forecast_days > 0:
                parsed["forecast"] = _parse_forecast(raw, key, forecast_days)

            # 仅 forecast_days=0 时写缓存
            if forecast_days == 0:
                _cache[key] = {"data": parsed, "ts": _now()}
            return parsed
        else:
            print(f"[weather] wttr.in 返回格式异常，尝试回退")
    except requests.exceptions.RequestException as e:
        print(f"[weather] API 请求失败: {e}")
    except json.JSONDecodeError as e:
        print(f"[weather] JSON 解码失败: {e}")

    # 3. 回退到本地数据
    fallback = FALLBACK_WEATHER.get(key, FALLBACK_DEFAULT).copy()
    fallback["city"] = key
    fallback["_source"] = "fallback"

    if forecast_days > 0:
        fallback["forecast"] = _build_fallback_forecast(key, forecast_days)

    if forecast_days == 0:
        _cache[key] = {"data": fallback, "ts": _now()}
    return fallback


def clear_cache():
    """清空天气缓存"""
    _cache.clear()


def get_cache_info() -> dict:
    """返回缓存状态"""
    return {
        "size": len(_cache),
        "keys": list(_cache.keys()),
        "ttl": CACHE_TTL,
    }


# ═══════════════════════════════════════════════════
# 对话上下文注入 — 检测用户输入中的天气意图并格式化
# ═══════════════════════════════════════════════════

_WEATHER_KEYWORDS = [
    "天气", "温度", "气温", "下雨", "下雪", "刮风", "台风",
    "多少度", "热不热", "冷不冷", "weather", "temperature",
    "湿度", "pm", "空气", "雾霾", "晴", "雨", "雪", "阴",
    "天怎么样", "天如何", "预报",
]


def is_weather_query(text: str) -> bool:
    """判断文本是否是查询某城市天气的意图"""
    t = text.strip()
    has_weather_kw = any(kw in t for kw in _WEATHER_KEYWORDS)

    # 检查是否包含城市名
    has_city = False
    for city in KNOWN_CITIES:
        if city in t:
            has_city = True
            break
    if not has_city:
        for en_city in EN_CITIES:
            if en_city in t.lower():
                has_city = True
                break

    # 如果只有城市名没有天气关键词，也尝试匹配（"北京现在多少度"）
    city_degree_pattern = re.search(
        r'[北|上|广|深|成|杭|武|南|重|天|苏|西|长|郑|东|青|沈|宁|昆|大|厦|合|佛|福|哈|济]', t)
    if city_degree_pattern:
        has_degree_num = bool(re.search(r'\d+°?[C度]', t)) or any(
            w in t for w in ["多少度", "几度", "气温", "温度"])
        if has_degree_num:
            return True

    return has_weather_kw and has_city


def extract_city(text: str) -> str | None:
    """从文本中提取城市名"""
    t = text.strip()
    # 先匹配英文城市
    t_lower = t.lower()
    for en_city, cn_city in EN_CITIES.items():
        if en_city in t_lower:
            return cn_city

    # 匹配中文城市（优先匹配更长的，避免"南京"被"南宁"先匹配）
    sorted_cities = sorted(KNOWN_CITIES, key=len, reverse=True)
    for city in sorted_cities:
        if city in t:
            return city

    return None


def format_weather_for_prompt(weather_data: dict) -> str:
    """将天气数据格式化为适合注入 prompt 的字符串"""
    city = weather_data.get("city", "未知")
    temp = weather_data.get("temp", "N/A")
    desc = weather_data.get("desc", "N/A")
    humidity = weather_data.get("humidity", "N/A")
    wind = weather_data.get("wind", "N/A")
    source = weather_data.get("_source", "api")

    lines = [
        f"【天气数据 - {city}】",
        f"- 温度: {temp}",
        f"- 天气: {desc}",
        f"- 湿度: {humidity}",
        f"- 风力: {wind}",
    ]

    # 如果有预报信息
    forecast = weather_data.get("forecast")
    if forecast:
        lines.append("- 未来预报:")
        for day in forecast[:3]:  # 最多显示3天
            lines.append(
                f"  · {day.get('date', '?')}: {day.get('desc', 'N/A')} "
                f"{day.get('high', '')}/{day.get('low', '')}"
            )

    if source == "fallback":
        lines.append("(数据来源: 本地估算，非实时)")

    return "\n".join(lines)


def _extract_forecast_days(text: str) -> int:
    """从用户文本中提取预报天数

    Args:
        text: 用户输入文本

    Returns:
        int: 预报天数（0=仅当前，1~7=预报天数）
    """
    import re
    # 匹配 "最近N天" "接下来N天" "N天" "未来N天"
    m = re.search(r'(?:最近|未来|接下来|后|近)(\d+)\s*天', text)
    if m:
        days = int(m.group(1))
        return min(max(days, 1), 7)
    # 匹配 "N天天气" "N天预报"
    m = re.search(r'(\d+)\s*天(?:天气|预报|的天气)?', text)
    if m:
        days = int(m.group(1))
        return min(max(days, 1), 7)
    return 0


def maybe_weather_context(user_text: str) -> str | None:
    """检测用户输入，如果是天气查询则返回天气数据上下文

    Args:
        user_text: 用户输入的对话文本

    Returns:
        str: 格式化的天气数据字符串（可直接注入 prompt），
              如果不是天气查询则返回 None
    """
    if not is_weather_query(user_text):
        return None

    city = extract_city(user_text)
    if not city:
        return None

    forecast_days = _extract_forecast_days(user_text)

    try:
        weather_data = get_weather(city, forecast_days=forecast_days)
        return format_weather_for_prompt(weather_data)
    except Exception as e:
        return f"【天气查询失败】{city} 天气查询出错: {e}"
