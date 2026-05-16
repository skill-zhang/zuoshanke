"""天气桥接模块 — 为场景对话提供天气查询能力

在场景对话的 Pass 1 之前调用：检测用户输入是否包含城市名，
如果是则调用 get_weather() 并将结果注入 prompt。

用法:
    from tools.weather_bridge import maybe_weather_context
    weather_info = maybe_weather_context("北京今天天气如何")
    # → "【天气数据】北京: 21°C, 晴朗..."
"""
import sys
import os
import re

# 确保能找到 tools/ 下的 weather.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from weather import get_weather

# 常见中国城市列表（带"市"后缀匹配）
KNOWN_CITIES = [
    "北京", "上海", "深圳", "广州", "成都", "杭州", "武汉", "南京", "重庆",
    "天津", "苏州", "西安", "长沙", "郑州", "东莞", "青岛", "沈阳", "宁波",
    "昆明", "大连", "厦门", "合肥", "佛山", "福州", "哈尔滨", "济南", "温州",
    "长春", "石家庄", "常州", "泉州", "南宁", "贵阳", "南昌", "太原", "烟台",
    "嘉兴", "南通", "金华", "珠海", "惠州", "徐州", "海口", "乌鲁木齐", "绍兴",
    "中山", "台州", "兰州", "保定", "镇江", "无锡", "邯郸", "洛阳",
]

# 英文城市名支持
EN_CITIES = {
    "beijing": "北京", "shanghai": "上海", "shenzhen": "深圳",
    "guangzhou": "广州", "chengdu": "成都", "hangzhou": "杭州",
    "wuhan": "武汉", "nanjing": "南京", "chongqing": "重庆",
    "tianjin": "天津", "suzhou": "苏州", "xian": "西安",
    "london": "伦敦", "tokyo": "东京", "new york": "纽约",
    "paris": "巴黎", "seoul": "首尔", "singapore": "新加坡",
}


def is_weather_query(text: str) -> bool:
    """判断文本是否是查询某城市天气的意图"""
    t = text.strip()
    weather_keywords = [
        "天气", "温度", "气温", "下雨", "下雪", "刮风", "台风",
        "多少度", "热不热", "冷不冷", "weather", "temperature",
        "湿度", "pm", "空气", "雾霾", "晴", "雨", "雪", "阴",
        "天怎么样", "天如何", "预报",
    ]
    # 检查天气关键词
    has_weather_kw = any(kw in t for kw in weather_keywords)

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
    city_degree_pattern = re.search(r'[北|上|广|深|成|杭|武|南|重|天|苏|西|长|郑|东|青|沈|宁|昆|大|厦|合|佛|福|哈|济]', t)
    if city_degree_pattern:
        # 检查是否有数字+度的模式
        has_degree_num = bool(re.search(r'\d+°?[C度]', t)) or any(w in t for w in ["多少度", "几度", "气温", "温度"])
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
    # 排序：按长度降序（长城市名优先匹配）
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
            lines.append(f"  · {day.get('date', '?')}: {day.get('desc', 'N/A')} {day.get('high', '')}/{day.get('low', '')}")

    if source == "fallback":
        lines.append("(数据来源: 本地估算，非实时)")

    return "\n".join(lines)


def maybe_weather_context(user_text: str) -> str | None:
    """检测用户输入，如果是天气查询则返回天气数据上下文

    Returns:
        str: 格式化的天气数据字符串（可直接注入 prompt），
              如果不是天气查询则返回 None
    """
    if not is_weather_query(user_text):
        return None

    city = extract_city(user_text)
    if not city:
        return None

    try:
        weather_data = get_weather(city)
        return format_weather_for_prompt(weather_data)
    except Exception as e:
        return f"【天气查询失败】{city} 天气查询出错: {e}"


# ── 直接运行测试 ──
if __name__ == "__main__":
    tests = [
        "北京天气怎么样",
        "上海今天多少度",
        "明天深圳会下雨吗",
        "杭州气温多少",
        "你好，我想问个问题",
        "帮我查一下广州的天气",
        "成都冷不冷",
        "beijing weather",
        "今天天气不错",  # 没有城市名，不应触发
    ]
    for t in tests:
        result = maybe_weather_context(t)
        if result:
            print(f"[✓] '{t}' → 触发天气查询")
            print(f"     {result}")
        else:
            print(f"[ ] '{t}' → 未触发")
        print()
