#!/usr/bin/env python3
"""
天津一日游方案 — 景点组合筛选 + 费用明细计算
基于 2026-05-16 调研数据
"""
import json, os, textwrap
from datetime import datetime

# ============================
# 1. 景点数据
# ============================
SPOTS = {
    "五大道文化旅游区（民园广场）": {
        "zone": "和平区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 2.0, "type": "文化/历史", "kid_friendly": True,
        "note": "可骑行/散步/野餐，马车观光另付80元/人"
    },
    "古文化街（津门故里）": {
        "zone": "南开区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 2.0, "type": "文化/美食", "kid_friendly": True,
        "note": "泥人张、糖人、熟梨糕，小吃密集"
    },
    "水上公园（+动物园）": {
        "zone": "南开区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 1.5, "type": "公园/休闲", "kid_friendly": True,
        "note": "公园免费，动物园30元/成人、15元/儿童"
    },
    "天津动物园": {
        "zone": "南开区", "free": False, "ticket_adult": 30, "ticket_child": 15,
        "time_hours": 2.0, "type": "动物园", "kid_friendly": True,
        "note": "熊猫馆必看，1.2m以下免票"
    },
    "天津自然博物馆": {
        "zone": "河西区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 2.0, "type": "博物馆", "kid_friendly": True,
        "note": "免费需预约，恐龙展厅，4D影院30元另付"
    },
    "天津科技馆": {
        "zone": "河西区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 2.0, "type": "博物馆", "kid_friendly": True,
        "note": "免费需预约，儿童科学体验区"
    },
    "天津文化中心公园": {
        "zone": "河西区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 1.0, "type": "公园/休闲", "kid_friendly": True,
        "note": "博物馆群环绕，地下餐饮区方便"
    },
    "天津博物馆/美术馆": {
        "zone": "河西区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 1.5, "type": "博物馆", "kid_friendly": True,
        "note": "免费需预约，周一闭馆"
    },
    "南翠屏公园（堆山公园）": {
        "zone": "南开区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 1.5, "type": "公园/户外", "kid_friendly": True,
        "note": "免费滑草坡（自带纸板），孩子超爱"
    },
    "海河沿线（解放桥→天津之眼）": {
        "zone": "和平区/河北区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 1.5, "type": "夜景/休闲", "kid_friendly": True,
        "note": "黄昏/夜景最佳，天津之眼100元/成人，儿童50元"
    },
    "天津之眼摩天轮": {
        "zone": "河北区", "free": False, "ticket_adult": 100, "ticket_child": 50,
        "time_hours": 0.5, "type": "景点", "kid_friendly": True,
        "note": "提前购票免排队"
    },
    "滨海新区图书馆": {
        "zone": "滨海新区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 1.0, "type": "文化/打卡", "kid_friendly": True,
        "note": "需预约，网红球形大厅，距市中心约1h车程"
    },
    "滨海新区海洋博物馆": {
        "zone": "滨海新区", "free": True, "ticket_adult": 0, "ticket_child": 0,
        "time_hours": 3.0, "type": "博物馆", "kid_friendly": True,
        "note": "免费需预约，距市中心1h车程，巨型鲸骨"
    },
}

# ============================
# 2. 路线方案配置
# ============================
ROUTES = [
    {
        "name": "路线A · 文化中心亲子线",
        "desc": "河西区文化中心片区，博物+科技一站式，适合学龄儿童",
        "spots": ["天津自然博物馆", "天津科技馆", "天津文化中心公园"],
        "meal_style": "经济小馆",
        "budget_tier": "经济",
        "target": "自然科学爱好者 / 学龄儿童",
    },
    {
        "name": "路线B · 老城风情漫游线",
        "desc": "南开区古文化街+水上公园，感受天津老城+自然休闲",
        "spots": ["古文化街（津门故里）", "水上公园（+动物园）", "天津动物园", "海河沿线（解放桥→天津之眼）"],
        "meal_style": "小吃街边吃",
        "budget_tier": "经济",
        "target": "喜欢人文+动物+夜景的家庭",
    },
    {
        "name": "路线C · 户外野趣线",
        "desc": "南翠屏滑草+水上公园野餐，纯户外免门票路线",
        "spots": ["南翠屏公园（堆山公园）", "水上公园（+动物园）", "五大道文化旅游区（民园广场）"],
        "meal_style": "自带野餐+简餐",
        "budget_tier": "极限省钱",
        "target": "户外爱好者 / 极简出行",
    },
    {
        "name": "路线D · 滨海远方探索线",
        "desc": "滨海新区海洋博物馆+图书馆，全天沉浸式（需早出发）",
        "spots": ["滨海新区海洋博物馆", "滨海新区图书馆", "海河沿线（解放桥→天津之眼）"],
        "meal_style": "滨海商圈餐饮",
        "budget_tier": "舒适",
        "target": "大龄儿童/青少年 / 自然科技迷",
    },
    {
        "name": "路线E · 精华精选线",
        "desc": "五大道+古文化街+自然博物馆，市区精华不赶路",
        "spots": ["五大道文化旅游区（民园广场）", "古文化街（津门故里）", "天津自然博物馆", "海河沿线（解放桥→天津之眼）"],
        "meal_style": "中档家常菜",
        "budget_tier": "舒适",
        "target": "时间有限想玩精华的首选",
    },
]

# ============================
# 3. 价格常量（2大1小）
# ============================
PRICE = {
    "meal": {
        "极限省钱": {"breakfast": 0, "lunch": 60, "dinner": 80, "snack": 15, "note": "自带部分餐食"},
        "经济":     {"breakfast": 30, "lunch": 100, "dinner": 150, "snack": 30, "note": "街边早点+小馆+小吃"},
        "舒适":     {"breakfast": 0, "lunch": 200, "dinner": 250, "snack": 50, "note": "酒店含早+中档餐厅"},
    },
    "transport_per_person": {
        "北京出发高铁二等座": 54.5,
        "小孩高铁半价": 27.0,
    },
    "transport_daily_city": {
        "极限省钱": 20,  # 全程共享单车/步行
        "经济":     40,  # 地铁为主
        "舒适":     80,  # 打车为主
    },
    "tips": {
        "高铁总价": "2大1小 = 54.5*2 + 27.0 = 136元（往返×2=272元）",
        "预约提示": "博物馆/图书馆均需提前在公众号预约（搜对应场馆名）",
        "周一提醒": "周一部分博物馆闭馆，请避开周一出行",
    },
}

# ============================
# 4. 计算引擎
# ============================
def cost_summary(route_name, spots_list, tier, meal_style):
    """计算一条路线的一日游费用明细"""
    
    # 门票
    total_ticket = 0
    ticket_detail = []
    for name in spots_list:
        s = SPOTS[name]
        if s["free"]:
            ticket_detail.append(f"  {name}: 免费")
        else:
            adult = s["ticket_adult"] * 2
            child = s["ticket_child"]
            subtotal = adult + child
            total_ticket += subtotal
            ticket_detail.append(f"  {name}: 2大{s['ticket_adult']}×2={adult} + 小{s['ticket_child']}={child} = {subtotal}元")
    
    # 餐饮
    m = PRICE["meal"][tier]
    total_meal = m["breakfast"] + m["lunch"] + m["dinner"] + m["snack"]
    
    # 交通（北京出发单程高铁+市内）
    hs_one_way = 54.5 * 2 + 27.0  # 2大1小单程
    city_t = PRICE["transport_daily_city"][tier]
    total_transport = hs_one_way * 2 + city_t  # 高铁往返+市内
    
    # 总计
    grand_total = total_ticket + total_meal + total_transport
    
    # 游玩时长估算
    total_time = sum(SPOTS[s]["time_hours"] for s in spots_list)
    
    return {
        "route": route_name,
        "tier": tier,
        "meal_style": meal_style,
        "spots": spots_list,
        "total_hours": round(total_time, 1),
        "ticket": {"total": total_ticket, "detail": ticket_detail},
        "meal": {
            "total": total_meal,
            "breakfast": m["breakfast"],
            "lunch": m["lunch"],
            "dinner": m["dinner"],
            "snack": m["snack"],
            "note": m["note"],
        },
        "transport": {
            "total": round(total_transport, 1),
            "高铁往返": round(hs_one_way * 2, 1),
            "市内交通": city_t,
            "高铁单程参考": f"北京→天津 二等座54.5元/成人, 27元/儿童",
        },
        "grand_total": round(grand_total, 1),
    }

def format_output(results):
    """格式化为可读报告"""
    lines = []
    lines.append("=" * 72)
    lines.append("  天津一日游 · 方案筛选与费用明细")
    lines.append(f"  生成日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  游客: 2大1小（儿童按6-12岁）")
    lines.append("=" * 72)
    lines.append("")
    
    for r in results:
        lines.append(f"▶ {r['route']}")
        lines.append(f"  预算档位: {r['tier']}  |  餐饮类型: {r['meal_style']}")
        lines.append(f"  适合人群: {r['target']}")
        lines.append(f"  路线说明: {r['desc']}")
        lines.append("  ─────────────────────────────────────────")
        lines.append(f"  景点顺序: {' → '.join(r['spots'])}")
        lines.append(f"  游玩时长: 约 {r['total_hours']} 小时（不含交通/餐饮时间）")
        lines.append("")
        lines.append("  【费用明细】")
        lines.append(f"  ├ 门票:")
        for d in r['ticket_detail']:
            lines.append(f"  │  {d}")
        lines.append(f"  ├ 门票小计: {r['ticket_total']}元")
        lines.append(f"  ├ 餐饮小计: {r['meal_total']}元")
        lines.append(f"  │   - 早餐 {r['meal_breakfast']}元  午餐 {r['meal_lunch']}元  晚餐 {r['meal_dinner']}元  零食 {r['meal_snack']}元")
        lines.append(f"  │   ({r['meal_note']})")
        lines.append(f"  ├ 交通小计: {r['transport_total']}元")
        lines.append(f"  │   - 高铁往返: {r['transport_hs']}元（北京出发）")
        lines.append(f"  │   - 市内交通: {r['transport_city']}元（{r['tier']}档）")
        lines.append(f"  └{'─'*30}")
        lines.append(f"    ✅ 一日游总计: {r['grand_total']}元")
        lines.append(f"    （折合人均: {round(r['grand_total']/3, 1)}元/人）")
        lines.append("")
    
    # 省钱建议
    lines.append("=" * 72)
    lines.append("  省钱建议")
    lines.append("-" * 72)
    lines.append("  1. 天津多数博物馆免费（需提前在公众号预约）")
    lines.append("  2. 餐饮避开景区核心区，步行5分钟到周边街区更实惠")
    lines.append("  3. 地铁覆盖主要景点，2-5元/次，儿童1.2m以下免票")
    lines.append("  4. 高铁二等座往返272元（2大1小），提前12306购票")
    lines.append("  5. 自带水杯和零食，景区溢价较高")
    lines.append("  6. 非节假日出行，酒店价格可省30-40%")
    lines.append("")
    
    lines.append("=" * 72)
    lines.append("  数据来源: 马蜂窝、携程、12306 调研 (2026-05-16)")
    lines.append("=" * 72)
    
    return "\n".join(lines)

# ============================
# 5. 主流程
# ============================
def main():
    results = []
    for route in ROUTES:
        c = cost_summary(
            route["name"], route["spots"],
            route["budget_tier"], route["meal_style"]
        )
        # flatten for output
        results.append({
            "route": c["route"],
            "tier": c["tier"],
            "meal_style": c["meal_style"],
            "target": route["target"],
            "desc": route["desc"],
            "spots": c["spots"],
            "total_hours": c["total_hours"],
            "ticket_detail": c["ticket"]["detail"],
            "ticket_total": c["ticket"]["total"],
            "meal_total": c["meal"]["total"],
            "meal_breakfast": c["meal"]["breakfast"],
            "meal_lunch": c["meal"]["lunch"],
            "meal_dinner": c["meal"]["dinner"],
            "meal_snack": c["meal"]["snack"],
            "meal_note": c["meal"]["note"],
            "transport_total": c["transport"]["total"],
            "transport_hs": c["transport"]["高铁往返"],
            "transport_city": c["transport"]["市内交通"],
            "grand_total": c["grand_total"],
        })
    
    report = format_output(results)
    
    # 保存报告
    out_path = os.path.join(os.path.dirname(__file__) or ".", "tianjin_daytrip_report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"✓ 报告已生成: {out_path}")
    print(f"  共筛选 {len(results)} 条一日游路线")
    
    # 打印摘要
    print("\n" + "─" * 50)
    print("路线费用速览:")
    print(f"{'路线':<30} {'总计(元)':<12} {'人均(元)':<10}")
    print("─" * 50)
    for r in results:
        print(f"{r['route']:<30} {r['grand_total']:<12} {round(r['grand_total']/3, 1):<10}")
    print("─" * 50)
    
    return results

if __name__ == "__main__":
    main()
