"""
geo_tools.py - 地图/POI 工具

提供地理编码、逆地理编码、POI搜索和路线规划功能。
使用公开免费 API (Nominatim, Overpass, OSRM)，无需 API Key。
"""

import json
import os
import time
from typing import Optional

import requests

# ============================================================
# 缓存
# ============================================================
_geocode_cache: dict[str, list[dict]] = {}

# ============================================================
# 常量
# ============================================================
USER_AGENT = "zuoshanke/1.0"
TIMEOUT = 10  # 每个请求超时秒数

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/{profile}/{coords}?overview=false"

# POI 类别 → Overpass 查询标签映射
POI_TAGS = {
    "attraction": '["tourism"="attraction"]',
    "restaurant": '["amenity"="restaurant"]',
    "shop": '["shop"]',
    "park": '["leisure"="park"]',
    "hotel": '["tourism"="hotel"]',
}

# 路线模式 → OSRM profile 映射
ROUTE_PROFILES = {
    "driving": "driving",
    "walking": "walking",
    "cycling": "cycling",
}


# ============================================================
# 辅助函数
# ============================================================
def _nominatim_request(params: dict) -> Optional[dict]:
    """发送 Nominatim 请求，遵守 1 请求/秒限速。"""
    time.sleep(1)  # 限速：每秒最多 1 请求
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(
            NOMINATIM_SEARCH_URL if "q" in params else NOMINATIM_REVERSE_URL,
            params=params,
            headers=headers,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": f"请求失败: {str(e)}"}


def _geocode_address(address: str, limit: int = 5) -> list[dict]:
    """内部地理编码，带缓存。"""
    cache_key = f"geocode:{address.lower().strip()}"
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    result = _nominatim_request({"q": address, "format": "json", "limit": limit})
    if isinstance(result, dict) and "error" in result:
        return [result]

    data = result if isinstance(result, list) else []
    items = []
    for item in data[:limit]:
        items.append({
            "地址": item.get("display_name", ""),
            "纬度": item.get("lat", ""),
            "经度": item.get("lon", ""),
            "类型": item.get("type", ""),
            "重要性": item.get("importance", ""),
        })
    _geocode_cache[cache_key] = items
    return items


def _resolve_location(location: str) -> tuple[Optional[float], Optional[float]]:
    """将地址或 'lat,lng' 字符串解析为 (lat, lng)。"""
    # 先尝试解析为 "lat,lng" 格式
    if "," in location:
        parts = [p.strip() for p in location.split(",")]
        if len(parts) == 2:
            try:
                lat = float(parts[0])
                lng = float(parts[1])
                return lat, lng
            except ValueError:
                pass

    # 否则当作地址进行地理编码
    items = _geocode_address(location, limit=1)
    if items and "纬度" in items[0] and items[0]["纬度"]:
        try:
            return float(items[0]["纬度"]), float(items[0]["经度"])
        except (ValueError, TypeError):
            pass
    return None, None


# ============================================================
# 公开函数
# ============================================================
def geo_geocode(query: str, limit: int = 5) -> list[dict]:
    """
    地理编码：将地址转换为经纬度坐标。

    参数:
        query: 地址查询字符串 (如 "北京市天安门")
        limit: 返回结果数量上限，默认 5

    返回:
        list[dict]，每个 dict 包含：
            - 地址: 完整地址描述
            - 纬度: 纬度
            - 经度: 经度
            - 类型: 地点类型
            - 重要性: 重要性评分
    """
    return _geocode_address(query, limit=limit)


def geo_reverse_geocode(lat: float, lng: float) -> dict:
    """
    逆地理编码：将经纬度坐标转换为地址描述。

    参数:
        lat: 纬度
        lng: 经度

    返回:
        dict，包含：
            - 地址: 完整地址描述
            - 纬度: 纬度
            - 经度: 经度
            - 地名: 地点名称
            - 类别: 地点类别
    """
    result = _nominatim_request({
        "lat": lat,
        "lon": lng,
        "format": "json",
    })
    if isinstance(result, dict) and "error" in result:
        return {"地址": result["error"]}

    data = result if isinstance(result, dict) else {}
    address_data = data.get("address", {})
    return {
        "地址": data.get("display_name", ""),
        "纬度": str(lat),
        "经度": str(lng),
        "地名": address_data,
        "类别": data.get("type", ""),
    }


def geo_search_poi(city: str, category: str = "attraction", limit: int = 10) -> list[dict]:
    """
    搜索指定城市的 POI（兴趣点）。

    参数:
        city: 城市名称 (如 "北京")
        category: POI 类别，可选值：
            - "attraction"  景点 (默认)
            - "restaurant"  餐厅
            - "shop"        购物/商店
            - "park"        公园
            - "hotel"       酒店
        limit: 返回结果数量上限，默认 10

    返回:
        list[dict]，每个 dict 包含：
            - 名称: POI 名称
            - 地址: 详细地址
            - 纬度: 纬度
            - 经度: 经度
            - 类别: 类别标签
    """
    tag = POI_TAGS.get(category)
    if tag is None:
        return [{"error": f"不支持的类别: {category}，可选: attraction/restaurant/shop/park/hotel"}]

    # 先通过地理编码获取城市边界
    geocode_results = _geocode_address(f"{city}", limit=1)
    if not geocode_results or "纬度" not in geocode_results[0] or not geocode_results[0]["纬度"]:
        return [{"error": f"无法定位城市: {city}"}]

    lat = float(geocode_results[0]["纬度"])
    lng = float(geocode_results[0]["经度"])

    # 用 Overpass API 查询附近 POI
    # 搜索半径约 5000 米
    overpass_query = f"""
    [out:json];
    (
      node{tag}(around:5000,{lat},{lng});
      way{tag}(around:5000,{lat},{lng});
      relation{tag}(around:5000,{lat},{lng});
    );
    out center {limit};
    """

    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": overpass_query},
            headers=headers,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return [{"error": f"POI 搜索失败: {str(e)}"}]

    elements = data.get("elements", [])
    results = []
    for elem in elements[:limit]:
        # 获取坐标
        lat_poi = elem.get("lat") or (elem.get("center", {}).get("lat") if isinstance(elem.get("center"), dict) else None)
        lng_poi = elem.get("lon") or (elem.get("center", {}).get("lon") if isinstance(elem.get("center"), dict) else None)
        tags = elem.get("tags", {})

        name = tags.get("name", tags.get("name:zh", "(未命名)"))
        address_parts = []
        for key in ("addr:full", "addr:street", "addr:city", "addr:district"):
            if tags.get(key):
                address_parts.append(tags[key])
        address = " ".join(address_parts) if address_parts else ""

        results.append({
            "名称": name,
            "地址": address or f"{city} (附近)",
            "纬度": str(lat_poi) if lat_poi else "",
            "经度": str(lng_poi) if lng_poi else "",
            "类别": category,
        })

    return results if results else [{"info": f"在 {city} 未找到 {category} 类 POI"}]


def geo_route(origin: str, destination: str, mode: str = "driving") -> dict:
    """
    路线规划：计算两点之间的行驶/步行/骑行路线。

    参数:
        origin: 起点，可以是地址字符串 (如 "北京站") 或 "lat,lng" 格式
        destination: 终点，可以是地址字符串或 "lat,lng" 格式
        mode: 出行模式，可选：
            - "driving"  驾车 (默认)
            - "walking"  步行
            - "cycling"  骑行

    返回:
        dict，包含：
            - 起点: 起点坐标 "lat,lng"
            - 终点: 终点坐标 "lat,lng"
            - 距离(米): 总距离（米）
            - 距离(公里): 总距离（公里，保留1位小数）
            - 时长(秒): 总时长（秒）
            - 时长(分钟): 总时长（分钟，保留1位小数）
            - 模式: 出行模式（中文）
    """
    profile = ROUTE_PROFILES.get(mode)
    if profile is None:
        return {"error": f"不支持的出行模式: {mode}，可选: driving/walking/cycling"}

    # 解析起点和终点坐标
    orig_lat, orig_lng = _resolve_location(origin)
    dest_lat, dest_lng = _resolve_location(destination)

    if orig_lat is None or orig_lng is None:
        return {"error": f"无法解析起点坐标: {origin}"}
    if dest_lat is None or dest_lng is None:
        return {"error": f"无法解析终点坐标: {destination}"}

    # 调用 OSRM API
    coords = f"{orig_lng},{orig_lat};{dest_lng},{dest_lat}"
    url = OSRM_ROUTE_URL.format(profile=profile, coords=coords)

    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"error": f"路线规划失败: {str(e)}"}

    if data.get("code") != "Ok" or not data.get("routes"):
        return {"error": f"路线规划失败: {data.get('message', '未知错误')}"}

    route = data["routes"][0]
    distance_m = route.get("distance", 0)
    duration_s = route.get("duration", 0)

    mode_names = {"driving": "驾车", "walking": "步行", "cycling": "骑行"}
    return {
        "起点": f"{orig_lat},{orig_lng}",
        "终点": f"{dest_lat},{dest_lng}",
        "距离(米)": round(distance_m),
        "距离(公里)": round(distance_m / 1000, 1),
        "时长(秒)": round(duration_s),
        "时长(分钟)": round(duration_s / 60, 1),
        "模式": mode_names.get(mode, mode),
    }


# ============================================================
# 自测（仅在直接运行时执行）
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("geo_tools 自测")
    print("=" * 60)

    print("\n--- 地理编码 ---")
    results = geo_geocode("北京天安门", limit=2)
    for r in results:
        print(json.dumps(r, ensure_ascii=False, indent=2))

    print("\n--- 逆地理编码 ---")
    rev = geo_reverse_geocode(39.9042, 116.4074)
    print(json.dumps(rev, ensure_ascii=False, indent=2))

    print("\n--- POI 搜索 (北京景点) ---")
    pois = geo_search_poi("北京", category="attraction", limit=3)
    for p in pois:
        print(json.dumps(p, ensure_ascii=False, indent=2))

    print("\n--- 路线规划 (北京站→天安门) ---")
    route = geo_route("北京站", "天安门", mode="driving")
    print(json.dumps(route, ensure_ascii=False, indent=2))

    print("\n--- 路线规划 (坐标到坐标, 步行) ---")
    route2 = geo_route("39.9042,116.4074", "39.9150,116.3970", mode="walking")
    print(json.dumps(route2, ensure_ascii=False, indent=2))
