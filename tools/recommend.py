"""推荐引擎 — 根据天气分类 → 查映射表 → 筛选匹配景点 → 排序输出

## 架构流程
1. 获取城市实时天气（复用 weather.get_weather）
2. 根据天气数据（desc, temp, wind, humidity）分类到 weather_categories
3. 根据分类查 weather_to_scene 映射表获取推荐场景
4. 从景点数据库/数据集中筛选匹配当前天气的景点
5. 按置信度排序输出

## 使用示例
    from recommend import recommend_attractions
    result = recommend_attractions("天津")
    # → {"city": "天津", "weather": {...}, "category": "sunny", "items": [...]}
"""

import json
import os
from typing import Optional

from weather import get_weather, get_cache_info

# ── 映射表加载 ──
YAML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "design", "weather_scene_mapping.yaml"
)

# ── 景点数据集（天津亲子景点） ──
ATTRACTIONS = [
    {"name": "天津方特欢乐世界", "category": "户外", "tags": ["主题乐园", "亲子"], "address": "天津市滨海新区中生大道4888号",
     "suitable_weather": ["sunny", "overcast"], "temp_range": [15, 30], "indoor": False, "note": "大型主题乐园，适合4岁以上"},
    {"name": "天津海昌极地海洋公园", "category": "户内", "tags": ["海洋馆", "亲子"], "address": "天津市滨海新区响螺湾中心商务区61号",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "全年均可，室内恒温"},
    {"name": "天津欢乐谷", "category": "户外", "tags": ["主题乐园", "水上项目"], "address": "天津市东丽区东丽之光大道",
     "suitable_weather": ["sunny"], "temp_range": [15, 30], "indoor": False, "note": "水上项目夏季开放"},
    {"name": "天津动物园", "category": "户外", "tags": ["动物园", "亲子"], "address": "天津市南开区水上公园路",
     "suitable_weather": ["sunny", "overcast"], "temp_range": [10, 28], "indoor": False, "note": "适合低龄儿童"},
    {"name": "天津水上公园", "category": "户外", "tags": ["公园", "免费"], "address": "天津市南开区水上公园路48号",
     "suitable_weather": ["sunny", "overcast"], "temp_range": [10, 30], "indoor": False, "note": "免费公园，有游乐区"},
    {"name": "天津科技馆", "category": "户内", "tags": ["科普", "亲子"], "address": "天津市河西区隆昌路94号",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "互动科普，适合学龄儿童"},
    {"name": "天津自然博物馆", "category": "户内", "tags": ["博物馆", "科普"], "address": "天津市河西区友谊路31号",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "恐龙化石、动物标本"},
    {"name": "天津博物馆", "category": "户内", "tags": ["博物馆", "历史"], "address": "天津市河西区平江道62号",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "历史文化展览"},
    {"name": "天津滨海图书馆", "category": "户内", "tags": ["图书馆", "网红打卡"], "address": "天津市滨海新区旭升路347号",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "网红打卡，儿童阅读区"},
    {"name": "天津之眼摩天轮", "category": "户外", "tags": ["观光", "地标"], "address": "天津市河北区三岔河口永乐桥上",
     "suitable_weather": ["sunny", "overcast"], "temp_range": [5, 35], "indoor": False, "note": "高空观景，排队较长"},
    {"name": "天津极地冰雪世界", "category": "户内", "tags": ["冰雪", "亲子"], "address": "天津市滨海新区海昌极地海洋公园内",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "冰雪主题，夏季避暑"},
    {"name": "天津光合谷旅游度假区", "category": "户外", "tags": ["农场", "亲子"], "address": "天津市静海区团泊新城东区",
     "suitable_weather": ["sunny", "overcast"], "temp_range": [10, 30], "indoor": False, "note": "亲子农场、动物互动"},
    {"name": "天津七彩滑道乐园", "category": "户外", "tags": ["拓展", "亲子"], "address": "天津市西青区杨柳青镇",
     "suitable_weather": ["sunny", "overcast"], "temp_range": [10, 30], "indoor": False, "note": "户外拓展项目"},
    {"name": "天津滨海新区航母主题公园", "category": "户外", "tags": ["主题公园", "军事"], "address": "天津市滨海新区汉沽八卦滩",
     "suitable_weather": ["sunny", "overcast"], "temp_range": [5, 28], "indoor": False, "note": "基辅号航母，有表演"},
    {"name": "天津热带植物观光园", "category": "户内", "tags": ["植物园", "亲子"], "address": "天津市西青区曹庄花卉市场旁",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "室内植物园，四季如春"},
    {"name": "天津图书馆儿童馆", "category": "户内", "tags": ["图书馆", "免费"], "address": "天津市河西区平江道58号",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "免费，亲子阅读"},
    {"name": "天津民园体育场", "category": "户外", "tags": ["散步", "历史建筑"], "address": "天津市和平区重庆道83号",
     "suitable_weather": ["sunny", "overcast"], "temp_range": [10, 30], "indoor": False, "note": "五大道区域，适合散步"},
    {"name": "天津国家海洋博物馆", "category": "户内", "tags": ["博物馆", "海洋"], "address": "天津市滨海新区荣盛路与海轩路交口",
     "suitable_weather": ["sunny", "overcast", "rainy", "snowy", "hot", "cold"], "temp_range": [0, 40], "indoor": True, "note": "免费预约，海洋科普"},
]

# ── 天气分类定义（从 YAML 提取，内联方便 Python 使用） ──

WEATHER_CATEGORIES = {
    "extreme": {
        "priority": 7,
        "condition_weather": ["台风", "沙尘暴", "冰雹", "暴雪", "暴雨"],
        "temp_range": [-40, 50],
        "rainfall_mm": [0, 500],
        "wind_speed_max": 50,
        "visibility_km": [0, 5],
        "default_category": "室内避险",
    },
    "snowy": {
        "priority": 6,
        "condition_weather": ["小雪", "中雪", "大雪", "暴雪"],
        "temp_range": [-20, 5],
        "rainfall_mm": [0, 50],
        "wind_speed_max": 10,
        "visibility_km": [0.3, 5],
        "default_category": "户内",
    },
    "rainy": {
        "priority": 5,
        "condition_weather": ["小雨", "中雨", "大雨", "暴雨", "雷阵雨"],
        "temp_range": [-5, 32],
        "rainfall_mm": [0.5, 200],
        "wind_speed_max": 15,
        "visibility_km": [0.5, 8],
        "default_category": "户内",
    },
    "hot": {
        "priority": 4,
        "condition_weather": ["晴", "多云", "阴"],
        "temp_range": [35, 50],
        "rainfall_mm": [0, 1],
        "wind_speed_max": 6,
        "visibility_km": [5, 25],
        "default_category": "户内",
    },
    "cold": {
        "priority": 3,
        "condition_weather": ["晴", "多云", "阴", "小雪"],
        "temp_range": [-30, 0],
        "rainfall_mm": [0, 5],
        "wind_speed_max": 8,
        "visibility_km": [1, 20],
        "default_category": "户内",
    },
    "overcast": {
        "priority": 2,
        "condition_weather": ["阴", "雾", "霾"],
        "temp_range": [0, 35],
        "rainfall_mm": [0, 2],
        "wind_speed_max": 8,
        "visibility_km": [2, 10],
        "default_category": "户内",
    },
    "sunny": {
        "priority": 1,
        "condition_weather": ["晴", "多云"],
        "temp_range": [5, 38],
        "rainfall_mm": [0, 0.5],
        "wind_speed_max": 5,
        "visibility_km": [10, 30],
        "default_category": "户外",
    },
}


# ═══════════════════════════════════════
#  核心函数
# ═══════════════════════════════════════

def parse_temp(temp_str: str) -> Optional[float]:
    """从温度字符串中提取数值（如 '20°C' → 20.0）"""
    if not temp_str or temp_str == "N/A":
        return None
    cleaned = temp_str.replace("°C", "").replace("℃", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_wind_speed(wind_str: str) -> Optional[float]:
    """从风速描述中估算 m/s 值"""
    if not wind_str or wind_str == "N/A":
        return None
    wind_str = wind_str.lower()
    # 常见格式: "东风 3级" "南风 4级" "西南风 3级" "东风 15km/h"
    # 提取数字
    import re
    nums = re.findall(r'\d+\.?\d*', wind_str)
    if not nums:
        return None
    val = float(nums[0])
    # 如果是 km/h 转 m/s
    if "km/h" in wind_str:
        val *= 0.2778
    # 如果是「级」(蒲福风级)，粗略转换
    # 0级=0, 1级=1, 2级=2.5, 3级=4.5, 4级=6.5, 5级=9.5, 6级=12.5
    if "级" in wind_str and val <= 12:
        beaufort_to_ms = [0, 1, 2.5, 4.5, 6.5, 9.5, 12.5]
        val = beaufort_to_ms[int(val)] if int(val) < len(beaufort_to_ms) else val * 2
    return round(val, 1)


def classify_weather(weather_data: dict) -> str:
    """根据天气数据分类到 weather_categories 中的一个。

    Args:
        weather_data: get_weather() 返回的 dict，含 desc, temp, wind 等字段

    Returns:
        str: 分类名称（sunny, overcast, rainy, snowy, hot, cold, extreme）

    匹配策略（优先级从高到低）:
        1. desc 关键词匹配 condition_weather
        2. temp 值匹配 temp_range
        3. 取优先级最高的匹配项
    """
    desc = weather_data.get("desc", "").strip()
    temp_str = weather_data.get("temp", "")
    wind_str = weather_data.get("wind", "")

    temp_val = parse_temp(temp_str)
    wind_ms = parse_wind_speed(wind_str)

    # 按优先级从高到低匹配
    categories_sorted = sorted(WEATHER_CATEGORIES.items(), key=lambda x: x[1]["priority"], reverse=True)

    for cat_name, cat_def in categories_sorted:
        # Step 1: desc 关键词匹配
        desc_match = any(kw in desc for kw in cat_def["condition_weather"])

        # Step 2: 温度匹配
        temp_match = True
        if temp_val is not None:
            tr = cat_def["temp_range"]
            temp_match = tr[0] <= temp_val <= tr[1]

        # Step 3: 风速匹配
        wind_match = True
        if wind_ms is not None:
            wind_match = wind_ms <= cat_def["wind_speed_max"]

        if desc_match and temp_match and wind_match:
            return cat_name

    # 回退：用温度做简单分类
    if temp_val is not None:
        if temp_val >= 35:
            return "hot"
        elif temp_val <= 0:
            return "cold"
        elif temp_val >= 5:
            # 默认按 desc 判断晴/阴
            if any(kw in desc for kw in ["晴"]):
                return "sunny"
            return "overcast"

    return "sunny"  # 最终保底


def filter_attractions_by_weather(
    attractions: list,
    weather_category: str,
    temp_val: Optional[float],
) -> list:
    """从景点列表中筛选匹配当前天气的景点。

    筛选逻辑:
        1. 室内景点(indoor=True) → 几乎所有天气都匹配
        2. 户外景点 → 必须 weather_category 在 suitable_weather 中
        3. 温度不在 temp_range 内的排除
    """
    matched = []
    for att in attractions:
        # 室内景点：全天候
        if att.get("indoor", False):
            matched.append(att)
            continue

        # 户外景点：检查天气分类是否在适宜天气列表中
        suitable = att.get("suitable_weather", [])
        if weather_category not in suitable:
            continue

        # 检查温度范围
        tr = att.get("temp_range")
        if tr and temp_val is not None:
            if not (tr[0] <= temp_val <= tr[1]):
                continue

        matched.append(att)

    return matched


def score_attraction(att: dict, weather_category: str, temp_val: Optional[float]) -> float:
    """为景点计算推荐分数（0.0 - 1.0），用于排序。

    评分因子:
        - 室内/户外与天气分类的匹配度
        - 温度在适宜范围内的位置（中段最优）
        - 室内景点在恶劣天气下有加分
    """
    score = 0.5  # 基础分

    is_indoor = att.get("indoor", False)
    tr = att.get("temp_range", [0, 40])
    temp_str = att.get("note", "")

    # 恶劣天气下室内景点加分
    bad_weather = ("rainy", "snowy", "hot", "cold", "extreme", "overcast")
    if weather_category in bad_weather and is_indoor:
        score += 0.3

    # 好天气下户外景点加分
    good_weather = ("sunny",)
    if weather_category in good_weather and not is_indoor:
        score += 0.2

    # 温度在范围中段有额外加分
    if temp_val is not None and tr:
        mid = (tr[0] + tr[1]) / 2
        if abs(temp_val - mid) < 5:
            score += 0.15

    # 带"亲子"标签加小分（景点数据集主体就是亲子向）
    if "亲子" in att.get("tags", []):
        score += 0.05

    return min(score, 1.0)


def recommend_attractions(
    city: str,
    limit: int = 6,
) -> dict:
    """主入口：根据城市返回推荐景点列表。

    Args:
        city: 城市名称
        limit: 最大返回景点数

    Returns:
        dict: {
            "city": str,
            "weather": {...},          # get_weather 原始结果
            "category": str,           # 天气分类
            "category_label": str,     # 分类中文描述
            "default_category": str,   # 默认活动类别
            "items": [...]             # 景点列表（按评分排序）
        }
    """
    # Step 1: 检查城市是否有景点数据（当前仅天津有硬编码数据）
    SUPPORTED_CITIES = ["天津"]
    if city not in SUPPORTED_CITIES:
        return {
            "city": city,
            "error": f"景点数据库当前仅覆盖天津地区，暂不支持{city}的景点推荐。可尝试 web_search",
            "items": [],
            "total_matched": 0,
        }

    # Step 2: 获取实时天气
    weather_data = get_weather(city)

    # Step 2: 天气分类
    category = classify_weather(weather_data)

    # Step 3: 获取分类定义
    cat_def = WEATHER_CATEGORIES.get(category, WEATHER_CATEGORIES["sunny"])

    temp_val = parse_temp(weather_data.get("temp", ""))

    # Step 4: 筛选匹配景点
    matched = filter_attractions_by_weather(ATTRACTIONS, category, temp_val)

    # Step 5: 评分并排序
    for att in matched:
        att["_score"] = score_attraction(att, category, temp_val)

    matched.sort(key=lambda x: x["_score"], reverse=True)

    # Step 6: 格式化输出
    items = []
    for att in matched[:limit]:
        items.append({
            "name": att["name"],
            "category": att["category"],
            "tags": att.get("tags", []),
            "address": att.get("address", ""),
            "indoor": att.get("indoor", False),
            "note": att.get("note", ""),
            "score": round(att["_score"], 2),
        })

    # 分类中文标签
    CATEGORY_LABELS = {
        "sunny": "晴朗",
        "overcast": "阴天",
        "rainy": "雨天",
        "snowy": "雪天",
        "hot": "高温",
        "cold": "低温",
        "extreme": "极端天气",
    }

    return {
        "city": city,
        "weather": {
            "temp": weather_data.get("temp"),
            "desc": weather_data.get("desc"),
            "humidity": weather_data.get("humidity"),
            "wind": weather_data.get("wind"),
        },
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, category),
        "default_category": cat_def.get("default_category", "通用"),
        "total_matched": len(matched),
        "items": items,
    }


# ═══ 便捷查询 ═══

def get_recommended_scenes_by_category(category: str) -> list:
    """根据天气分类返回推荐场景列表（weather_to_scene 映射）"""
    SCENE_MAP = {
        "sunny": [
            {"name": "海河沿岸漫步", "type": "户外 · 滨水", "tags": ["散步", "拍照", "骑行"],
             "tips": "注意防晒，建议上午10点前或下午4点后出行"},
            {"name": "城市公园", "type": "户外 · 绿地", "tags": ["野餐", "跑步", "亲子"],
             "tips": "周末人流量大，建议工作日前往"},
            {"name": "登山/徒步", "type": "户外 · 山地", "tags": ["徒步", "自然", "运动"]},
            {"name": "露天咖啡馆", "type": "户外 · 休闲", "tags": ["阅读", "社交", "下午茶"]},
        ],
        "overcast": [
            {"name": "老街/胡同漫步", "type": "户外 · 人文", "tags": ["漫步", "摄影", "探店"],
             "tips": "阴天光线柔和，适合街拍"},
            {"name": "室内美术馆/画廊", "type": "户内 · 文化", "tags": ["看展", "艺术", "安静"]},
            {"name": "书店/图书馆", "type": "户内 · 学习", "tags": ["阅读", "自习", "咖啡"]},
        ],
        "rainy": [
            {"name": "博物馆/科技馆", "type": "户内 · 文化", "tags": ["展览", "知识", "亲子"],
             "tips": "雨天的最佳选择，建议提前预约"},
            {"name": "商场/购物中心", "type": "户内 · 商业", "tags": ["购物", "美食", "电影"]},
            {"name": "室内运动馆", "type": "户内 · 运动", "tags": ["羽毛球", "游泳", "攀岩"]},
            {"name": "咖啡馆听雨", "type": "户内 · 休闲", "tags": ["阅读", "写作", "放空"]},
        ],
        "snowy": [
            {"name": "室内温泉/汗蒸", "type": "户内 · 养生", "tags": ["放松", "温暖"]},
            {"name": "雪景公园", "type": "户外 · 冬季限定", "tags": ["拍照", "玩雪"],
             "tips": "注意保暖，穿防滑鞋"},
            {"name": "火锅店/暖锅", "type": "户内 · 美食", "tags": ["聚餐", "温暖"]},
        ],
        "hot": [
            {"name": "博物馆（有空调）", "type": "户内 · 文化", "tags": ["避暑", "展览"],
             "tips": "建议全天在室内活动"},
            {"name": "水上乐园/游泳馆", "type": "户外 · 水上", "tags": ["戏水", "避暑", "亲子"]},
            {"name": "夜间夜市/步行街", "type": "户外 · 夜间", "tags": ["夜市", "美食", "夜景"]},
            {"name": "电影院", "type": "户内 · 娱乐", "tags": ["电影", "避暑"]},
        ],
        "cold": [
            {"name": "室内滑冰场", "type": "户内 · 运动", "tags": ["滑冰", "冬季限定"]},
            {"name": "温泉/汤泉", "type": "户内 · 养生", "tags": ["放松", "温暖"]},
            {"name": "室内书吧", "type": "户内 · 学习", "tags": ["阅读", "咖啡", "安静"]},
        ],
        "extreme": [
            {"name": "居家活动", "type": "室内 · 居家", "tags": ["安全", "休息"],
             "tips": "极端天气请避免外出"},
            {"name": "室内停车场/避难所", "type": "室内 · 避险", "tags": ["安全", "应急"]},
        ],
    }
    return SCENE_MAP.get(category, [])


# ═══ 独立测试 ═══
if __name__ == "__main__":
    import sys
    city = sys.argv[1] if len(sys.argv) > 1 else "天津"
    result = recommend_attractions(city)
    print(f"\n🌤  天气: {result['weather']['desc']} | {result['weather']['temp']}")
    print(f"📊 分类: {result['category_label']} ({result['category']})")
    print(f"🏷  推荐类型: {result['default_category']}")
    print(f"🎯 匹配景点: {result['total_matched']} 个")
    print(f"\n{'='*60}")
    for i, item in enumerate(result['items'], 1):
        icon = "🏠" if item["indoor"] else "🌳"
        print(f"  {i}. {icon} {item['name']} [{item['score']:.2f}]")
        print(f"     分类: {item['category']} | 标签: {', '.join(item['tags'][:3])}")
        if item.get("note"):
            print(f"     {item['note']}")
    print()

# ── Appended: 英文天气描述映射（wttr.in 可能返回英文） ──
EN_CONDITION_MAP = {
    # sunny/clear
    "sunny": ["sunny", "clear", "fine"],
    "overcast": ["cloudy", "overcast", "partly cloudy", "fog", "mist", "haze", "drizzle"],
    "rainy": ["rain", "rainy", "shower", "thunderstorm", "thundery", "heavy rain", "light rain"],
    "snowy": ["snow", "snowy", "sleet", "blizzard"],
    "hot": ["hot", "very hot"],
    "cold": ["cold", "freezing", "frost"],
    "extreme": ["storm", "tornado", "hurricane", "sandstorm"],
}


def _classify_by_english_desc(desc: str) -> Optional[str]:
    """用英文关键词匹配天气分类。"""
    desc_lower = desc.lower().strip()
    # 按优先级从高到低
    cat_order = ["extreme", "snowy", "rainy", "hot", "cold", "overcast", "sunny"]
    for cat in cat_order:
        keywords = EN_CONDITION_MAP.get(cat, [])
        for kw in keywords:
            if kw in desc_lower:
                return cat
    return None


# Monkey-patch the original classify_weather to add English support
_original_classify = classify_weather

def classify_weather(weather_data: dict) -> str:
    """增强版：支持中英文天气描述的天气分类"""
    desc = weather_data.get("desc", "").strip()

    # 先尝试中文匹配（原逻辑）
    for cat_name, cat_def in sorted(WEATHER_CATEGORIES.items(),
                                      key=lambda x: x[1]["priority"], reverse=True):
        for kw in cat_def["condition_weather"]:
            if kw in desc:
                # 找到关键词匹配，再检查温度和风速
                temp_str = weather_data.get("temp", "")
                wind_str = weather_data.get("wind", "")
                temp_val = parse_temp(temp_str)
                wind_ms = parse_wind_speed(wind_str)

                temp_match = True
                if temp_val is not None:
                    tr = cat_def["temp_range"]
                    temp_match = tr[0] <= temp_val <= tr[1]

                wind_match = True
                if wind_ms is not None:
                    wind_match = wind_ms <= cat_def["wind_speed_max"]

                if temp_match and wind_match:
                    return cat_name
                # 温度/风速不匹配时继续尝试其他分类

    # 再尝试英文匹配
    en_cat = _classify_by_english_desc(desc)
    if en_cat:
        # 检查温度范围
        cat_def = WEATHER_CATEGORIES.get(en_cat)
        if cat_def:
            temp_str = weather_data.get("temp", "")
            temp_val = parse_temp(temp_str)
            if temp_val is not None:
                tr = cat_def["temp_range"]
                if tr[0] <= temp_val <= tr[1]:
                    return en_cat
                # temp out of range for this category, fall through
            else:
                return en_cat

    # 回退：纯温度分类
    temp_str = weather_data.get("temp", "")
    temp_val = parse_temp(temp_str)
    if temp_val is not None:
        if temp_val >= 35:
            return "hot"
        elif temp_val <= 0:
            return "cold"
        elif temp_val >= 5:
            # 从 desc 判断晴/阴
            if any(kw in desc.lower() for kw in ["sunny", "clear", "晴"]):
                return "sunny"
            return "overcast"

    return "sunny"  # 最终保底

