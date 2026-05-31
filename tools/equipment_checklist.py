"""
晴朗天气装备建议子清单 — 按天气分类输出户外活动装备检查表

## 架构
equipment_checklist.py
├── EQUIPMENT_DB         # 装备数据库（按天气分类 + 场景分类）
├── get_checklist()      # 核心 API：根据天气分类 + 场景类型 → 装备清单
├── format_checklist()   # 格式化输出（终端友好版本）
└── __main__            # 命令行演示

## 用法
    from equipment_checklist import get_checklist, format_checklist

    # 按天气分类获取
    items = get_checklist(weather_category="sunny")
    print(format_checklist(items, title="晴朗出行装备清单"))

    # 按天气分类 + 场景类型过滤
    items = get_checklist(weather_category="sunny", scene_type="滨水")
    print(format_checklist(items, title="晴朗·滨水场景装备"))

## 场景类型选项
    - 通用户外       (所有 sunny 场景的通用项)
    - 滨水           （海河沿岸、水上项目）
    - 山地/徒步      （登山、徒步）
    - 公园/野餐      （城市公园、野餐）
    - 休闲            （露天咖啡馆、阅读）

## 设计原则
    1. 每个天气分类有独立的数据段，方便后续扩展
    2. 装备项包含：名称、必要性（必带/推荐/可选）、适用温度范围、备注
    3. 场景类型过滤：同一天气下不同场景需求不同装备
"""

# ─══════════════════════════════════════════
#  装备数据库
# ─══════════════════════════════════════════

# 装备项结构:
# {
#     "name": str,          # 装备名称
#     "necessity": "必带" | "推荐" | "可选",  # 必要程度
#     "temp_range": [min, max] | None,        # 适用温度范围，None=不限
#     "note": str,          # 备注说明
#     "tags": [str],        # 场景标签
#     "priority": int,      # 排序权重（越大越靠前）
# }

from typing import Optional

EQUIPMENT_DB = {
    # ═══════════════════════════════════════
    #  晴朗 (sunny)
    # ═══════════════════════════════════════
    "sunny": {
        "label": "晴朗",
        "icon": "☀️",
        "default_category": "户外",
        "common": [  # 所有晴朗场景通用
            {
                "name": "防晒霜 SPF30+",
                "necessity": "必带",
                "temp_range": [20, 50],
                "note": "出门前15分钟涂抹，每2小时补涂一次；建议SPF50+ PA+++",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 100,
            },
            {
                "name": "太阳镜（偏光镜）",
                "necessity": "推荐",
                "temp_range": [20, 50],
                "note": "偏光镜片可有效减少水面/路面眩光，UVA/UVB防护",
                "tags": ["通用户外", "滨水", "山地", "公园"],
                "priority": 95,
            },
            {
                "name": "遮阳帽/渔夫帽",
                "necessity": "推荐",
                "temp_range": [20, 50],
                "note": "宽檐帽最佳，保护面部和颈部",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 90,
            },
            {
                "name": "饮用水（500ml+）",
                "necessity": "必带",
                "temp_range": [18, 50],
                "note": "建议每人至少500ml，炎热天1L+；可携带电解质饮料",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 98,
            },
            {
                "name": "轻薄外套/防晒衣",
                "necessity": "推荐",
                "temp_range": [15, 35],
                "note": "UPF50+防晒衣或亚麻薄外套，透气优先",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 85,
            },
            {
                "name": "充电宝",
                "necessity": "推荐",
                "temp_range": None,
                "note": "户外导航、拍照耗电快，建议10000mAh+",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 70,
            },
            {
                "name": "便携纸巾/湿巾",
                "necessity": "推荐",
                "temp_range": None,
                "note": "擦汗、清洁用",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 60,
            },
            {
                "name": "垃圾袋",
                "necessity": "推荐",
                "temp_range": None,
                "note": "户外不乱丢垃圾，随身带走",
                "tags": ["通用户外", "滨水", "山地", "公园"],
                "priority": 50,
            },
        ],
        "scenes": {
            "滨水": [
                {
                    "name": "防水袋/手机防水套",
                    "necessity": "推荐",
                    "temp_range": [15, 40],
                    "note": "滨水活动防止手机、证件进水",
                    "tags": ["滨水"],
                    "priority": 92,
                },
                {
                    "name": "拖鞋/凉鞋",
                    "necessity": "可选",
                    "temp_range": [20, 40],
                    "note": "如需玩水或沙滩行走，方便替换",
                    "tags": ["滨水"],
                    "priority": 65,
                },
                {
                    "name": "毛巾/速干巾",
                    "necessity": "可选",
                    "temp_range": [20, 40],
                    "note": "玩水后擦干用",
                    "tags": ["滨水"],
                    "priority": 55,
                },
            ],
            "山地": [
                {
                    "name": "登山鞋/防滑鞋",
                    "necessity": "必带",
                    "temp_range": [5, 35],
                    "note": "防滑鞋底+高帮护踝，避免崴脚",
                    "tags": ["山地"],
                    "priority": 99,
                },
                {
                    "name": "登山杖",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "减轻膝盖负担，下坡时尤其有效",
                    "tags": ["山地"],
                    "priority": 80,
                },
                {
                    "name": "速干衣裤",
                    "necessity": "推荐",
                    "temp_range": [15, 35],
                    "note": "排汗速干，避免汗水浸湿后着凉",
                    "tags": ["山地"],
                    "priority": 78,
                },
                {
                    "name": "急救包",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "创可贴、碘伏棉签、纱布、消毒湿巾",
                    "tags": ["山地"],
                    "priority": 75,
                },
                {
                    "name": "能量棒/干粮",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "补充体力，建议带巧克力、坚果、能量棒",
                    "tags": ["山地"],
                    "priority": 72,
                },
                {
                    "name": "离线地图下载",
                    "necessity": "必带",
                    "temp_range": None,
                    "note": "山里信号可能弱，提前下载离线地图或轨迹",
                    "tags": ["山地"],
                    "priority": 97,
                },
            ],
            "公园": [
                {
                    "name": "野餐垫/防潮垫",
                    "necessity": "可选",
                    "temp_range": [15, 35],
                    "note": "如需在草坪上坐卧，建议带防潮垫",
                    "tags": ["公园"],
                    "priority": 68,
                },
                {
                    "name": "遮阳伞/天幕",
                    "necessity": "可选",
                    "temp_range": [22, 40],
                    "note": "长时间停留时提供阴凉",
                    "tags": ["公园"],
                    "priority": 62,
                },
                {
                    "name": "蓝牙音箱（小）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "野餐氛围组，注意音量不要影响他人",
                    "tags": ["公园"],
                    "priority": 40,
                },
                {
                    "name": "驱蚊液/驱蚊贴",
                    "necessity": "推荐",
                    "temp_range": [18, 35],
                    "note": "公园草丛蚊虫多，含避蚊胺(DEET)成分有效",
                    "tags": ["公园"],
                    "priority": 82,
                },
            ],
            "休闲": [
                {
                    "name": "书籍/Kindle",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "露天咖啡馆或公园长椅上阅读",
                    "tags": ["休闲"],
                    "priority": 45,
                },
                {
                    "name": "降噪耳机",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "户外环境音嘈杂时提升专注",
                    "tags": ["休闲"],
                    "priority": 42,
                },
            ],
        },
    },

    # ═══════════════════════════════════════
    #  阴天 (overcast)
    # ═══════════════════════════════════════
    "overcast": {
        "label": "阴天",
        "icon": "☁️",
        "default_category": "户内",
        "common": [
            {
                "name": "折叠伞",
                "necessity": "推荐",
                "temp_range": None,
                "note": "阴天可能转小雨，备伞防身",
                "tags": ["通用户外"],
                "priority": 85,
            },
            {
                "name": "薄外套",
                "necessity": "推荐",
                "temp_range": [5, 22],
                "note": "阴天体感温度比实际偏低",
                "tags": ["通用户外"],
                "priority": 80,
            },
            {
                "name": "相机/手机（街拍）",
                "necessity": "可选",
                "temp_range": None,
                "note": "阴天光线柔和，适合人文街拍",
                "tags": ["通用户外"],
                "priority": 65,
            },
        ],
    },

    # ═══════════════════════════════════════
    # ═══════════════════════════════════════
    # ═══════════════════════════════════════
    # ═══════════════════════════════════════
    #  闷热/高温 (hot_and_humid)
    # ═══════════════════════════════════════
    "hot_and_humid": {
        "label": "闷热/高温",
        "icon": "🥵",
        "default_category": "避暑",
        "common": [
            {
                "name": "便携小风扇/挂脖风扇",
                "necessity": "必带",
                "temp_range": [30, 50],
                "note": "户外移动降温首选，挂脖式解放双手；建议选可折叠/可拆洗款，电池容量5000mAh+",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 100,
            },
            {
                "name": "冰感毛巾/速冷巾",
                "necessity": "必带",
                "temp_range": [30, 50],
                "note": "浸湿后甩几下即降温，搭在颈后/额头可降3-5°C；建议每人至少1条",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 99,
            },
            {
                "name": "饮用水（1.5L+）",
                "necessity": "必带",
                "temp_range": [30, 50],
                "note": "闷热天出汗量大，建议每人1.5L起步；分次小口慢饮，大口猛喝反而加重心脏负担",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 98,
            },
            {
                "name": "电解质饮料/泡腾片",
                "necessity": "必带",
                "temp_range": [30, 50],
                "note": "大量出汗后补充钠/钾/镁；首选电解质泡腾片（方便携带），运动饮料次之",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 97,
            },
            {
                "name": "防晒霜 SPF50+ PA++++",
                "necessity": "必带",
                "temp_range": [25, 50],
                "note": "闷热天汗水冲走防晒快，2小时补涂一次；选防水抗汗型，兼顾UVA/UVB",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 96,
            },
            {
                "name": "宽檐遮阳帽+墨镜",
                "necessity": "必带",
                "temp_range": [28, 50],
                "note": "物理防晒优于化学防晒；宽檐帽+偏光墨镜+冰袖=户外三件套",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 95,
            },
            {
                "name": "冰袖/防晒臂套",
                "necessity": "推荐",
                "temp_range": [28, 50],
                "note": "UPF50+冰丝面料，比涂防晒霜清爽透气；湿水后更有降温效果",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 90,
            },
            {
                "name": "汗巾/速干运动毛巾",
                "necessity": "推荐",
                "temp_range": [28, 50],
                "note": "超细纤维速干材质，擦汗不粘腻；建议2条交替使用",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 88,
            },
            {
                "name": "透气速干衣裤",
                "necessity": "推荐",
                "temp_range": [28, 50],
                "note": "拒绝纯棉！选Polyester/Nylon速干面料，排汗快、不闷身；浅色系反射热量",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 85,
            },
            {
                "name": "免洗洗手液/湿巾",
                "necessity": "推荐",
                "temp_range": None,
                "note": "闷热天手部出汗黏腻，用餐前必备；选含酒精款消毒+清爽",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 75,
            },
            {
                "name": "止汗露/爽身粉",
                "necessity": "推荐",
                "temp_range": [28, 50],
                "note": "腋下/颈后等褶皱部位防汗臭；走珠型<滚珠型<喷雾型便携度递增",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 72,
            },
            {
                "name": "藿香正气水/防暑药",
                "necessity": "推荐",
                "temp_range": [32, 50],
                "note": "出现头晕、恶心、乏力等中暑前兆时立即服用；注意含酒精款不能开车",
                "tags": ["通用户外", "滨水", "山地"],
                "priority": 82,
            },
            {
                "name": "充电宝20000mAh+",
                "necessity": "推荐",
                "temp_range": None,
                "note": "小风扇+手机拍照+导航，闷热天设备耗电更快；大容量充电宝必备",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 70,
            },
            {
                "name": "小包装纸巾（多包）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "闷热天汗如雨下，擦汗擦手频率高；小包装随拿随用",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 60,
            },
            {
                "name": "降温喷雾/清凉喷雾",
                "necessity": "可选",
                "temp_range": [30, 50],
                "note": "喷在衣物/帽子/防晒袖上，利用蒸发吸热原理；注意不能直接喷皮肤",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 65,
            },
        ],
        "scenes": {
            "滨水": [
                {
                    "name": "速干沙滩裤/泳裤",
                    "necessity": "推荐",
                    "temp_range": [28, 45],
                    "note": "海河沿岸戏水或水上项目，下水后可沥水速干",
                    "tags": ["滨水"],
                    "priority": 92,
                },
                {
                    "name": "防水手机袋（可触屏）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "滨水+闷热双重出汗，防水袋还能防止汗水渗入手机；选IPX8级",
                    "tags": ["滨水"],
                    "priority": 85,
                },
                {
                    "name": "凉鞋/洞洞鞋（防滑）",
                    "necessity": "推荐",
                    "temp_range": [28, 45],
                    "note": "滨水步道地面被晒烫，厚底鞋底隔热；洞洞鞋透气排水",
                    "tags": ["滨水"],
                    "priority": 80,
                },
                {
                    "name": "防水蓝牙音箱",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "滨水休闲时听音乐，注意音量不影响他人",
                    "tags": ["滨水"],
                    "priority": 40,
                },
            ],
            "山地": [
                {
                    "name": "徒步登山鞋（透气网面）",
                    "necessity": "必带",
                    "temp_range": [20, 45],
                    "note": "闷热天登山鞋选网面透气款，拒绝全皮；GTX+网面最佳",
                    "tags": ["山地"],
                    "priority": 98,
                },
                {
                    "name": "速干运动袜（排汗）",
                    "necessity": "必带",
                    "temp_range": [20, 45],
                    "note": "棉袜闷热天=脚汗磨泡；选COOLMAX或羊毛混纺速干袜，备用1双",
                    "tags": ["山地"],
                    "priority": 93,
                },
                {
                    "name": "能量棒/盐丸",
                    "necessity": "必带",
                    "temp_range": [25, 50],
                    "note": "闷热天登山大量出汗+消耗，盐丸补充电解质比泡腾片更快；建议每45分钟补一次",
                    "tags": ["山地"],
                    "priority": 94,
                },
                {
                    "name": "离线地图+GPS",
                    "necessity": "必带",
                    "temp_range": None,
                    "note": "山里信号弱，闷热天更易体力透支走错路；提前下载轨迹",
                    "tags": ["山地"],
                    "priority": 97,
                },
                {
                    "name": "登山杖（双杖）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "闷热天体力消耗更大，双杖有效节省体能30%+",
                    "tags": ["山地"],
                    "priority": 86,
                },
                {
                    "name": "急救包（含烫伤/中暑药）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "闷热天中暑+烫伤双风险；备藿香正气水、风油精、烫伤膏",
                    "tags": ["山地"],
                    "priority": 78,
                },
                {
                    "name": "头灯",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "夏天白昼长但山间树荫下光线暗；头灯防迷路、防摔",
                    "tags": ["山地"],
                    "priority": 74,
                },
                {
                    "name": "防水袋（装替换衣）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "闷热天汗透全身，到山顶/阴凉处替换；衣物密封防潮",
                    "tags": ["山地"],
                    "priority": 68,
                },
            ],
            "公园": [
                {
                    "name": "野餐垫（铝箔防潮款）",
                    "necessity": "推荐",
                    "temp_range": [25, 45],
                    "note": "草坪被晒得烫且潮，铝箔层反射地热+隔潮",
                    "tags": ["公园"],
                    "priority": 88,
                },
                {
                    "name": "大号遮阳伞/天幕（银胶）",
                    "necessity": "推荐",
                    "temp_range": [30, 50],
                    "note": "树荫不够用，银胶天幕反射紫外线+降温，比普通伞凉快3-5°C",
                    "tags": ["公园"],
                    "priority": 84,
                },
                {
                    "name": "驱蚊液/驱蚊贴（避蚊胺）",
                    "necessity": "推荐",
                    "temp_range": [25, 40],
                    "note": "闷热天+公园=蚊虫密集；含DEET或派卡瑞丁成分有效",
                    "tags": ["公园"],
                    "priority": 76,
                },
                {
                    "name": "冰袋/冰包（保温袋）",
                    "necessity": "可选",
                    "temp_range": [30, 50],
                    "note": "带冰块或冰袋，冰镇饮料/水果；也可敷在手腕降温",
                    "tags": ["公园"],
                    "priority": 62,
                },
                {
                    "name": "西瓜/水果（切好冷藏）",
                    "necessity": "可选",
                    "temp_range": [30, 50],
                    "note": "解暑降温，冰镇西瓜是野餐的灵魂",
                    "tags": ["公园"],
                    "priority": 55,
                },
                {
                    "name": "花露水（六神劲凉提神款）",
                    "necessity": "可选",
                    "temp_range": [28, 50],
                    "note": "经典国货清凉神器，喷身上薄荷醇带来冰凉感+驱蚊",
                    "tags": ["公园"],
                    "priority": 58,
                },
            ],
            "休闲": [
                {
                    "name": "UVC遮阳伞/黑胶防晒伞",
                    "necessity": "推荐",
                    "temp_range": [30, 50],
                    "note": "黑胶涂层伞面UPF50+，晴雨两用；注意选大伞面覆盖全身",
                    "tags": ["休闲"],
                    "priority": 78,
                },
                {
                    "name": "便携风扇（桌面款）",
                    "necessity": "推荐",
                    "temp_range": [28, 45],
                    "note": "露天咖啡馆/长椅阅读时放桌上吹风，比手持款更方便",
                    "tags": ["休闲"],
                    "priority": 82,
                },
                {
                    "name": "冰咖啡/冰茶（保温杯）",
                    "necessity": "可选",
                    "temp_range": [28, 45],
                    "note": "保温杯装冰饮，保冷比保热更持久；建议加冰块续航",
                    "tags": ["休闲"],
                    "priority": 72,
                },
                {
                    "name": "鼻吸式清凉棒",
                    "necessity": "可选",
                    "temp_range": [30, 50],
                    "note": "薄荷/冰片配方，深吸一口瞬间提神醒脑，防中暑",
                    "tags": ["休闲"],
                    "priority": 48,
                },
                {
                    "name": "Kindle/书籍（务必室内或伞下）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "电子书在强光下阅读体验差，建议在伞下或室内阅读",
                    "tags": ["休闲"],
                    "priority": 35,
                },
            ],
        },
    },


    #  雨天 (rainy)
    # ═══════════════════════════════════════
    "rainy": {
        "label": "雨天",
        "icon": "🌧️",
        "default_category": "户内",
        "common": [
            {
                "name": "雨伞（坚固抗风）",
                "necessity": "必带",
                "temp_range": None,
                "note": "建议选骨架加固的自动伞，雨天风大易坏；折叠伞不如长柄伞抗风",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 100,
            },
            {
                "name": "雨衣/冲锋衣",
                "necessity": "必带",
                "temp_range": [0, 30],
                "note": "骑行或长时间户外活动的首选，比雨伞解放双手",
                "tags": ["通用户外", "滨水", "山地", "公园"],
                "priority": 99,
            },
            {
                "name": "防水鞋/鞋套",
                "necessity": "必带",
                "temp_range": None,
                "note": "保持脚部干燥，避免感冒和脚部不适",
                "tags": ["通用户外", "滨水", "山地", "公园"],
                "priority": 96,
            },
            {
                "name": "密封袋（多个尺寸）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "保护手机、钱包、证件等贵重物品；大号可装换洗衣物",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 88,
            },
            {
                "name": "干毛巾/替换袜",
                "necessity": "必带",
                "temp_range": None,
                "note": "淋湿后及时擦干更换，预防感冒",
                "tags": ["通用户外", "滨水", "山地", "公园"],
                "priority": 90,
            },
            {
                "name": "防水背包/背包罩",
                "necessity": "推荐",
                "temp_range": None,
                "note": "保护包内物品不被淋湿；普通背包可用背包罩替代",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 84,
            },
            {
                "name": "干湿分离收纳袋",
                "necessity": "推荐",
                "temp_range": None,
                "note": "将湿雨伞、湿衣服与干物品隔离收纳",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 72,
            },
            {
                "name": "纸巾/湿巾（防水包装）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "擦拭雨水、泥点等；建议防水包装防潮",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 65,
            },
            {
                "name": "反光条/夜行装备",
                "necessity": "推荐",
                "temp_range": None,
                "note": "雨天能见度低，反光条/发光臂环提升安全",
                "tags": ["通用户外", "山地", "公园"],
                "priority": 68,
            },
            {
                "name": "暖宝宝/保暖贴",
                "necessity": "可选",
                "temp_range": [0, 12],
                "note": "雨天气温可能骤降，贴于腰腹或脚底保暖",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 50,
            },
        ],
        "scenes": {
            "滨水": [
                {
                    "name": "防滑拖鞋/溯溪鞋",
                    "necessity": "推荐",
                    "temp_range": [15, 35],
                    "note": "滨水步道湿滑，防滑鞋底比普通鞋安全；雨停后可换穿",
                    "tags": ["滨水"],
                    "priority": 78,
                },
                {
                    "name": "手机防水套（专业级）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "滨水+雨天双重防水，IPX8级防水袋",
                    "tags": ["滨水"],
                    "priority": 76,
                },
                {
                    "name": "防水冲锋裤/快干裤",
                    "necessity": "推荐",
                    "temp_range": [5, 25],
                    "note": "海河边风大浪急，裤腿易被溅湿；建议快干面料",
                    "tags": ["滨水"],
                    "priority": 72,
                },
                {
                    "name": "急救保温毯",
                    "necessity": "可选",
                    "temp_range": [0, 15],
                    "note": "雨天失温风险高，应急保温",
                    "tags": ["滨水"],
                    "priority": 45,
                },
            ],
            "山地": [
                {
                    "name": "防水登山鞋（GTX）",
                    "necessity": "必带",
                    "temp_range": [-5, 25],
                    "note": "Gore-Tex防水内衬+防滑大底，泥泞山路必备",
                    "tags": ["山地"],
                    "priority": 99,
                },
                {
                    "name": "登山杖（带泥托）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "雨天山路湿滑，登山杖提供额外支撑；泥托防陷入泥地",
                    "tags": ["山地"],
                    "priority": 85,
                },
                {
                    "name": "防水冲锋衣裤",
                    "necessity": "必带",
                    "temp_range": [0, 25],
                    "note": "山风+雨水=快速失温；建议Gore-Tex或同等级防水透气面料",
                    "tags": ["山地"],
                    "priority": 98,
                },
                {
                    "name": "手套（防水保暖）",
                    "necessity": "推荐",
                    "temp_range": [-5, 15],
                    "note": "雨天握持登山杖/绳索，防水手套防滑保暖",
                    "tags": ["山地"],
                    "priority": 75,
                },
                {
                    "name": "离线地图/GPS轨迹",
                    "necessity": "必带",
                    "temp_range": None,
                    "note": "雨雾天能见度极低，容易迷路；提前下载轨迹",
                    "tags": ["山地"],
                    "priority": 97,
                },
                {
                    "name": "头灯/手电筒",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "阴雨天光线暗，提前天黑风险高；双AA或充电头灯",
                    "tags": ["山地"],
                    "priority": 82,
                },
                {
                    "name": "急救包（含防水创可贴）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "雨天滑倒擦伤概率增加，防水创可贴更实用",
                    "tags": ["山地"],
                    "priority": 74,
                },
                {
                    "name": "能量棒/高热量零食",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "雨天体温流失快，及时补充热量防失温",
                    "tags": ["山地"],
                    "priority": 70,
                },
                {
                    "name": "雨裙/防雨罩",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "套在背包外，防止雨水渗入背包和装备",
                    "tags": ["山地"],
                    "priority": 60,
                },
            ],
            "公园": [
                {
                    "name": "防水野餐垫/地垫",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "雨后湿草坪不可直接坐；防水底垫保持干爽",
                    "tags": ["公园"],
                    "priority": 74,
                },
                {
                    "name": "大号遮雨棚/天幕",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "如雨势不大想在户外停留，遮雨棚提供临时庇护",
                    "tags": ["公园"],
                    "priority": 50,
                },
                {
                    "name": "保温瓶/热水",
                    "necessity": "推荐",
                    "temp_range": [0, 20],
                    "note": "雨天户外停留湿冷，热水暖身",
                    "tags": ["公园"],
                    "priority": 76,
                },
                {
                    "name": "便携板凳（防水面料）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "公园长椅可能湿透；自带折叠板凳",
                    "tags": ["公园"],
                    "priority": 48,
                },
                {
                    "name": "游戏卡牌/桌游（防水）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "公园亭子/长廊下避雨时的室内活动备选",
                    "tags": ["公园"],
                    "priority": 40,
                },
            ],
            "休闲": [
                {
                    "name": "防水外套/风衣",
                    "necessity": "推荐",
                    "temp_range": [10, 25],
                    "note": "小雨穿街走巷，风衣比雨伞更方便灵活",
                    "tags": ["休闲"],
                    "priority": 78,
                },
                {
                    "name": "乐福鞋/德比鞋（防水款）",
                    "necessity": "推荐",
                    "temp_range": [10, 30],
                    "note": "日常皮鞋怕水，防水皮革面料的乐福鞋兼顾体面和实用",
                    "tags": ["休闲"],
                    "priority": 72,
                },
                {
                    "name": "小型便携伞收纳袋",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "进商场/咖啡馆后装湿伞，避免弄湿地板",
                    "tags": ["休闲"],
                    "priority": 60,
                },
                {
                    "name": "保温杯/热饮",
                    "necessity": "可选",
                    "temp_range": [0, 18],
                    "note": "雨中漫步后喝杯热茶/咖啡，提升幸福感",
                    "tags": ["休闲"],
                    "priority": 55,
                },
                {
                    "name": "电子书阅读器（防水）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "部分Kindle Oasis/Kobo支持IPX8防水，雨中或咖啡馆阅读",
                    "tags": ["休闲"],
                    "priority": 38,
                },
            ],
        },
    },
    # ═══════════════════════════════════════
    #  大风/降温 (windy_cold)
    # ═══════════════════════════════════════
    "windy_cold": {
        "label": "大风/降温",
        "icon": "🌬️",
        "default_category": "防风保暖",
        "common": [  # 所有大风/降温场景通用
            {
                "name": "防风外套/冲锋衣",
                "necessity": "必带",
                "temp_range": [-10, 18],
                "note": "大风天核心装备；优选带防风层(Shell)的冲锋衣，阻挡风寒效应(Wind Chill)；注意拉链处是否有防风条设计",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 100,
            },
            {
                "name": "保暖中层（抓绒/薄羽绒）",
                "necessity": "必带",
                "temp_range": [-10, 12],
                "note": "外层防风+中层保暖是经典三层穿衣法；推荐Polartec抓绒或800FP轻薄羽绒，透气不闷汗",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 99,
            },
            {
                "name": "防风面罩/围巾",
                "necessity": "推荐",
                "temp_range": [-5, 15],
                "note": "大风天冷空气直吹面部会导致面部皮肤迅速失温；Buff百变面罩或多功能围巾可护住口鼻和颈部",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 92,
            },
            {
                "name": "防风手套",
                "necessity": "推荐",
                "temp_range": [-10, 12],
                "note": "手指末端血液循环差，大风天手指冻僵最快；选触屏款方便用手机，内层翻绒保暖+外层防风",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 90,
            },
            {
                "name": "保暖帽子/毛线帽",
                "necessity": "必带",
                "temp_range": [-15, 12],
                "note": "头部散热占全身30%+，大风天有帽檐的帽子可防风同时护住耳朵；选抓绒内衬款",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 97,
            },
            {
                "name": "防风裤/软壳裤",
                "necessity": "推荐",
                "temp_range": [-10, 15],
                "note": "软壳裤防风+轻微防水+有一定弹性，比硬壳裤舒适；注意裤脚是否有收口或雪裙设计防灌风",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 85,
            },
            {
                "name": "保温杯（热水）",
                "necessity": "推荐",
                "temp_range": [-10, 12],
                "note": "大风天体感温度比实际低5-10°C，喝热水能有效维持核心体温；建议500ml+不锈钢真空保温",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 88,
            },
            {
                "name": "润唇膏（防干裂）",
                "necessity": "推荐",
                "temp_range": [-5, 15],
                "note": "大风天嘴唇干裂速度是正常天气的3倍；选含羊毛脂或凡士林成分的润唇膏",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 75,
            },
            {
                "name": "护手霜",
                "necessity": "可选",
                "temp_range": [-5, 15],
                "note": "手部暴露在风中易皲裂，含甘油+尿素成分的护手霜更有效",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 60,
            },
            {
                "name": "充电宝（低温备用）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "低温下锂电池放电效率下降30-50%；建议带20000mAh+，并将手机靠近身体保暖避免意外关机",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 70,
            },
            {
                "name": "防风沙眼镜/护目镜",
                "necessity": "推荐",
                "temp_range": [-5, 20],
                "note": "沙尘/强风天气下，普通墨镜密封性不足；选骑行防风镜或封闭式运动护目镜，防止异物入眼",
                "tags": ["通用户外", "滨水", "山地", "公园"],
                "priority": 82,
            },
            {
                "name": "轻薄羽绒马甲",
                "necessity": "可选",
                "temp_range": [5, 15],
                "note": "适温范围窄但实用：5-15°C有风天气，马甲保暖核心躯干+不限制手臂活动",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 55,
            },
        ],
        "scenes": {
            "通用户外": [
                {
                    "name": "防风口罩/N95口罩",
                    "necessity": "推荐",
                    "temp_range": [-5, 15],
                    "note": "大风夹带沙尘/花粉/PM2.5，N95或KN95同时防风和防颗粒物；非医用即可",
                    "tags": ["通用户外"],
                    "priority": 85,
                },
                {
                    "name": "暖宝宝/自发热贴",
                    "necessity": "可选",
                    "temp_range": [-10, 8],
                    "note": "贴后腰/腹部/脚底，注意不要直接接触皮肤防烫伤；发热持续时间8-12小时",
                    "tags": ["通用户外"],
                    "priority": 65,
                },
            ],
            "滨水": [
                {
                    "name": "防水防风冲锋裤",
                    "necessity": "必带",
                    "temp_range": [-10, 15],
                    "note": "滨水区域风力通常比陆地高1-2级+水雾扑面；硬壳冲锋裤+雪裙设计防灌风灌水",
                    "tags": ["滨水"],
                    "priority": 98,
                },
                {
                    "name": "防水登山鞋（高帮）",
                    "necessity": "必带",
                    "temp_range": [-10, 15],
                    "note": "滨水步道湿滑+大风天站稳更难；高帮防水鞋+Gore-Tex膜+深齿大底，防滑防湿",
                    "tags": ["滨水"],
                    "priority": 96,
                },
                {
                    "name": "速干保暖内衣",
                    "necessity": "推荐",
                    "temp_range": [-5, 12],
                    "note": "滨水湿度大，棉质内衣一旦出汗+湿冷风一吹≈体温快速下降；选美利奴羊毛或PowerDry速干",
                    "tags": ["滨水"],
                    "priority": 86,
                },
                {
                    "name": "防风绳/扎带（固定用）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "滨水露营/钓鱼时固定帐篷、天幕、遮阳伞用，防止大风掀翻",
                    "tags": ["滨水"],
                    "priority": 58,
                },
            ],
            "山地": [
                {
                    "name": "硬壳冲锋衣（Gore-Tex）",
                    "necessity": "必带",
                    "temp_range": [-15, 15],
                    "note": "山地风力通常比平地高3-5级+海拔每升100m气温降0.6°C；Gore-Tex Pro薄膜防风防水透湿三合一",
                    "tags": ["山地"],
                    "priority": 100,
                },
                {
                    "name": "登山杖（防风加固款）",
                    "necessity": "必带",
                    "temp_range": None,
                    "note": "大风天重心不稳，双登山杖提供额外3个支撑点；选7075铝合金或碳纤维款，避免大风中侧滑",
                    "tags": ["山地"],
                    "priority": 95,
                },
                {
                    "name": "雪套/防风腿套",
                    "necessity": "推荐",
                    "temp_range": [-10, 10],
                    "note": "防止冷风从裤管和鞋口灌入+泥水溅入裤腿；GTX面料+拉链式穿脱",
                    "tags": ["山地"],
                    "priority": 84,
                },
                {
                    "name": "防风打火机/防水火柴",
                    "necessity": "推荐",
                    "temp_range": [-15, 15],
                    "note": "极端大风天手机信号差+电子设备失温关机；应急点火工具能在紧急情况下生火取暖/求救信号",
                    "tags": ["山地"],
                    "priority": 80,
                },
                {
                    "name": "急救毯/保温毯",
                    "necessity": "必带",
                    "temp_range": [-15, 10],
                    "note": "山地大风天一旦失温，急救毯可反射80%以上体温；体积小重量轻（约50g），放背包夹层不占空间",
                    "tags": ["山地"],
                    "priority": 93,
                },
                {
                    "name": "高热量食品（巧克力/坚果）",
                    "necessity": "推荐",
                    "temp_range": [-10, 15],
                    "note": "低温+大风让身体能量消耗增加25-40%；随身携带高热量食物即时补充",
                    "tags": ["山地"],
                    "priority": 76,
                },
                {
                    "name": "冰爪/防滑链（鞋底）",
                    "necessity": "可选",
                    "temp_range": [-10, 2],
                    "note": "若大风伴随降雪/路面结冰，简易冰爪（12齿+）可大幅提升行走稳定性",
                    "tags": ["山地"],
                    "priority": 62,
                },
            ],
            "公园": [
                {
                    "name": "固定式帐篷/天幕（防风型）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "公园大风天普通遮阳伞会变降落伞；选防风天幕（鱼脊帐结构最佳）+多根防风绳+地钉45°斜插",
                    "tags": ["公园"],
                    "priority": 90,
                },
                {
                    "name": "重物压阵（水桶/石块）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "野餐垫/坐垫容易被风卷走，四角用背包/水桶/石块压住；优先选带地钉孔的野餐垫",
                    "tags": ["公园"],
                    "priority": 80,
                },
                {
                    "name": "防风炉/挡风板",
                    "necessity": "可选",
                    "temp_range": [-5, 15],
                    "note": "公园野餐用卡式炉时，大风会降低热效率40%+甚至吹灭火焰；铝合金三折挡风板必备",
                    "tags": ["公园"],
                    "priority": 65,
                },
            ],
            "休闲": [
                {
                    "name": "室内替代方案（咖啡馆/图书馆）",
                    "necessity": "推荐",
                    "temp_range": [-10, 10],
                    "note": "若风力>6级（10.8m/s）或体感温度<0°C，建议直接切换室内活动；选择带暖气的室内场所",
                    "tags": ["休闲"],
                    "priority": 85,
                },
                {
                    "name": "防风保暖围巾（可当披肩）",
                    "necessity": "可选",
                    "temp_range": [0, 15],
                    "note": "短途户外（如咖啡馆之间转移）时，大尺寸羊绒/羊毛围巾可同时护住颈部+肩部",
                    "tags": ["休闲"],
                    "priority": 50,
                },
                {
                    "name": "一次性暖足贴",
                    "necessity": "可选",
                    "temp_range": [-5, 8],
                    "note": "脚底是人体散热最快的部位之一；暖足贴持续发热6-8小时，适合露天咖啡/观景",
                    "tags": ["休闲"],
                    "priority": 48,
                },
            ],
        },
    },
    # ═══════════════════════════════════════
    #  沙尘/扬沙 (dust_storm)
    # ═══════════════════════════════════════
    "dust_storm": {
        "label": "沙尘/扬沙",
        "icon": "🏜️",
        "default_category": "减少外出 · 防护优先",
        "common": [
            {
                "name": "N95/KN95口罩",
                "necessity": "必带",
                "temp_range": None,
                "note": "沙尘天PM10浓度爆表，普通医用口罩密封性不足；N95可过滤95%以上的颗粒物，建议带呼气阀款减少闷热",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 100,
            },
            {
                "name": "防风沙护目镜/骑行镜",
                "necessity": "必带",
                "temp_range": None,
                "note": "沙尘入眼会引起结膜炎、角膜划伤；选封闭式运动护目镜（如骑行镜），侧面防风挡沙；普通墨镜缝隙太大",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 99,
            },
            {
                "name": "防风沙面罩/头巾（全脸款）",
                "necessity": "必带",
                "temp_range": None,
                "note": "口鼻+面部一起护住，比单独的口罩+帽子更方便；选透气速干面料+可调节松紧带，避免沙粒钻入缝隙",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 98,
            },
            {
                "name": "连帽防风外套（帽子可收紧）",
                "necessity": "必带",
                "temp_range": [0, 35],
                "note": "帽子必须有抽绳可收紧，防止风沙从帽沿钻入头发和衣领；面料选高密度尼龙/聚酯纤维防沙渗透",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 97,
            },
            {
                "name": "润眼液/人工泪液（单支装）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "即使佩戴护目镜，微尘仍可能刺激眼睛；选不含防腐剂的单支装人工泪液，沙尘入眼后冲洗；缓解沙尘引起的干涩",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 90,
            },
            {
                "name": "鼻腔清洗喷雾/生理盐水",
                "necessity": "推荐",
                "temp_range": None,
                "note": "沙尘颗粒吸入后沉积在鼻腔，可能引发过敏和鼻炎；生理盐水喷雾冲洗鼻腔，建议回到室内后使用",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 85,
            },
            {
                "name": "密封袋（保护电子设备）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "沙尘对相机镜头、手机扬声器/麦克风有磨蚀性；相机用密封袋+防尘罩，手机进沙后不要插充电口",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 82,
            },
            {
                "name": "护手霜/凡士林",
                "necessity": "推荐",
                "temp_range": [0, 25],
                "note": "沙尘天气加速手部皮肤水分流失，指缝易干裂；出门前涂抹凡士林形成保护膜",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 75,
            },
            {
                "name": "密封水瓶/吸管杯",
                "necessity": "推荐",
                "temp_range": None,
                "note": "沙尘天户外喝水，普通杯口会进沙；选带密封盖的吸管杯或按压式水瓶，单手操作防扬尘",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 78,
            },
            {
                "name": "防风沙帐篷/天幕（全封闭款）",
                "necessity": "可选",
                "temp_range": None,
                "note": "如需在沙尘天进行户外活动（如沙漠徒步），选全封闭式帐篷+雪裙设计防沙；天幕在这种天气下无效",
                "tags": ["山地"],
                "priority": 60,
            },
            {
                "name": "湿巾（多包）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "沙尘天洗脸洗手频率高，户外无水源时湿巾是刚需；选大包+独立包装备用",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 72,
            },
            {
                "name": "相机防沙套/防水袋替代",
                "necessity": "可选",
                "temp_range": None,
                "note": "摄影爱好者必备，沙尘对镜头镀膜和机身缝隙的伤害不可逆；单反/微单专用防沙套或保鲜膜+橡皮筋应急",
                "tags": ["山地", "公园"],
                "priority": 55,
            },
        ],
        "scenes": {
            "通用户外": [
                {
                    "name": "全罩式头盔/摩托车头盔",
                    "necessity": "可选",
                    "temp_range": [-5, 30],
                    "note": "若必须骑电动车/摩托车出行，全罩式头盔是应对沙尘天的最佳防护；普通头盔面罩需闭合",
                    "tags": ["通用户外"],
                    "priority": 65,
                },
                {
                    "name": "一次性浴帽（套鞋上防沙）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "沙尘天鞋子进沙后走路磨脚；一次性浴帽套在鞋外+橡皮筋固定，简易防沙套",
                    "tags": ["通用户外"],
                    "priority": 45,
                },
            ],
            "休闲": [
                {
                    "name": "室内替代方案（强烈建议）",
                    "necessity": "必带",
                    "temp_range": None,
                    "note": "沙尘天气PM10浓度≥150μg/m³时，建议取消所有户外活动；转去商场/博物馆/咖啡馆等室内空间，优先选带新风系统的场所",
                    "tags": ["休闲"],
                    "priority": 96,
                },
                {
                    "name": "空气净化器（居家/酒店）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "回到室内后空气净化器可快速降低室内PM10浓度；选CADR值≥300m³/h的机型",
                    "tags": ["休闲"],
                    "priority": 50,
                },
            ],
        },
    },

    # ═══════════════════════════════════════
    #  雾霾/霾 (haze_smog) — 与沙尘不同，雾霾以PM2.5为主，颗粒更小、毒性更大
    # ═══════════════════════════════════════
    "haze_smog": {
        "label": "雾霾/霾",
        "icon": "🌫️",
        "default_category": "减少外出 · 呼吸防护",
        "common": [
            {
                "name": "N95/KN95口罩（带呼气阀）",
                "necessity": "必带",
                "temp_range": None,
                "note": "雾霾主要污染物为PM2.5（≤2.5μm），N95可过滤95%以上细微颗粒；选带呼气阀款减少呼吸阻力，长时间佩戴才不闷",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 100,
            },
            {
                "name": "空气净化口罩/电动送风口罩",
                "necessity": "可选",
                "temp_range": None,
                "note": "重度雾霾天（AQI>200）可选电动送风口罩（如远大/BLW），内置HEPA滤芯+主动送风，呼吸阻力为零；但价格较高（¥200-800）",
                "tags": ["通用户外", "山地", "休闲"],
                "priority": 75,
            },
            {
                "name": "防雾霾帽子/假发帽（带面罩款）",
                "necessity": "可选",
                "temp_range": None,
                "note": "一体式防霾帽+面罩，比独立口罩+帽子更密封；部分款带呼吸阀+HEPA滤片，适合骑行/步行通勤",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 68,
            },
            {
                "name": "封闭式护目镜/防风镜",
                "necessity": "推荐",
                "temp_range": None,
                "note": "PM2.5颗粒会刺激眼表，导致干眼症、结膜炎加重；选封闭式护目镜+防雾涂层，防止镜片起雾影响视线",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 90,
            },
            {
                "name": "人工泪液/玻璃酸钠滴眼液",
                "necessity": "推荐",
                "temp_range": None,
                "note": "雾霾天眼表暴露在污染物中，干涩/异物感/眼痒高发；选单支装玻璃酸钠滴眼液（不含防腐剂），每小时滴1次",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 85,
            },
            {
                "name": "鼻腔过滤器/鼻用空气净化器",
                "necessity": "可选",
                "temp_range": None,
                "note": "微型鼻塞式过滤器（如First Defense/安氧），塞入鼻孔过滤吸入空气；隐蔽性好，但呼吸阻力略增",
                "tags": ["通用户外", "休闲"],
                "priority": 62,
            },
            {
                "name": "生理盐水鼻腔喷雾",
                "necessity": "推荐",
                "temp_range": None,
                "note": "雾霾颗粒沉积鼻腔黏膜→炎症→鼻腔干燥；早晚各喷一次清洗鼻腔，过敏体质者更需注意",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 82,
            },
            {
                "name": "保湿面霜/修复霜",
                "necessity": "推荐",
                "temp_range": [0, 25],
                "note": "雾霾中的多环芳烃(PAHs)会破坏皮肤屏障→干燥/敏感/加速衰老；出门前涂修护霜（含神经酰胺/角鲨烷），形成保护膜",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 80,
            },
            {
                "name": "密封水瓶/保温杯（防尘盖）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "雾霾天户外饮水，杯口暴露在霾中会沾染PM2.5颗粒；选按压式防尘盖水瓶或吸管杯",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 76,
            },
            {
                "name": "湿巾（多包）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "雾霾天面部和手部易吸附污染物，户外清洁用湿巾更安全；选不含酒精的温和配方",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 72,
            },
            {
                "name": "空气检测仪/霾表（便携）",
                "necessity": "可选",
                "temp_range": None,
                "note": "实时查看PM2.5/AQI浓度，决定是否出门/开窗；口袋大小，激光散射原理，精度±10μg/m³；充电款使用更灵活",
                "tags": ["通用户外", "休闲"],
                "priority": 50,
            },
            {
                "name": "绿植（室内放置）",
                "necessity": "可选",
                "temp_range": None,
                "note": "回到室内后，虎皮兰/绿萝/龟背竹等绿植可辅助吸附空气污染物（效果有限，主要靠净化器）；满足心理安慰+装饰",
                "tags": ["休闲"],
                "priority": 30,
            },
        ],
        "scenes": {
            "通用户外": [
                {
                    "name": "查看实时AQI（必备习惯）",
                    "necessity": "必带",
                    "temp_range": None,
                    "note": "出门前查看实时空气质量指数（推荐「在意空气」App或中国环境监测总站）；AQI>150建议减少外出，>200尽量避免外出",
                    "tags": ["通用户外"],
                    "priority": 98,
                },
                {
                    "name": "缩短户外停留时间",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "雾霾天户外每多停留1小时，PM2.5吸入量呈指数增加；计划路线时选最短步行段，中间换乘尽量走室内通道/地铁",
                    "tags": ["通用户外"],
                    "priority": 88,
                },
                {
                    "name": "回家后换衣+淋浴",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "PM2.5颗粒吸附在衣物和头发上，回家后第一时间换室外衣物+淋浴（重点洗头发、面部、手部）；室外衣物密封存放",
                    "tags": ["通用户外"],
                    "priority": 86,
                },
                {
                    "name": "高性能空气净化器（家用）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "回到室内后，HEPA H13级别净化器可有效降低室内PM2.5浓度；选CADR颗粒物值≥400m³/h的机型",
                    "tags": ["通用户外"],
                    "priority": 70,
                },
            ],
            "休闲": [
                {
                    "name": "室内替代方案（AQI>150时强制）",
                    "necessity": "必带",
                    "temp_range": None,
                    "note": "AQI>150时，博物馆/商场/书店等室内场所是最安全的选择；优先选带新风系统和HEPA过滤的大型公共场所",
                    "tags": ["休闲"],
                    "priority": 97,
                },
                {
                    "name": "新风系统（居家）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "关窗+新风系统是雾霾天居家标配；壁挂式新风（如小米/远大）可维持室内CO₂<1000ppm+PM2.5<35μg/m³",
                    "tags": ["休闲"],
                    "priority": 55,
                },
                {
                    "name": "室内运动（瑜伽/跳绳）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "雾霾天户外运动＝加速吸入污染物；转为室内Keep/瑜伽/跳绳/跑步机，保持运动习惯且不伤肺",
                    "tags": ["休闲"],
                    "priority": 52,
                },
                {
                    "name": "空气质量插座（带PM2.5显示）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "智能插座带PM2.5+CO₂+温湿度检测（¥100-200），连接净化器自动启停；适合疫情/霾季长期监测",
                    "tags": ["休闲"],
                    "priority": 42,
                },
            ],
        },
    },

    # ═══════════════════════════════════════
    #  早晚温差大 (diurnal_range) — 昼夜温差≥10°C的复合场景
    # ═══════════════════════════════════════
    "diurnal_range": {
        "label": "早晚温差大",
        "icon": "🌡️",
        "default_category": "分层穿衣 · 灵活增减",
        "common": [
            {
                "name": "三层穿衣法（贴身+中层+外层）",
                "necessity": "必带",
                "temp_range": None,
                "note": "早晚温差大的核心策略：贴身排汗层（速干/美利奴羊毛）+ 中间保暖层（抓绒/薄羽绒）+ 外层防风层（冲锋衣/风衣）；白天热了脱中层，傍晚冷了穿上",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 100,
            },
            {
                "name": "可收纳轻薄羽绒服/棉服",
                "necessity": "必带",
                "temp_range": [-5, 20],
                "note": "早晚气温低时的主力保暖层；选800FP+羽绒服压缩后可收纳到拳头大小，白天放包里不占空间；注意拒水羽绒遇潮仍保暖",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 99,
            },
            {
                "name": "速干T恤/打底衫",
                "necessity": "必带",
                "temp_range": [10, 35],
                "note": "白天热时单穿+傍晚冷了叠穿内层；选Polyester/Nylon速干面料，拒绝纯棉（出汗后湿冷→着凉）；浅色系反射日光",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 97,
            },
            {
                "name": "防风外套/软壳夹克",
                "necessity": "必带",
                "temp_range": [5, 30],
                "note": "外层防风是关键，选轻量化软壳（如Patagonia Houdini/北面防风夹克），可收纳+防风+轻微防水；昼夜温差大时不必上硬壳",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 98,
            },
            {
                "name": "叠穿式运动裤/两截裤",
                "necessity": "推荐",
                "temp_range": [5, 35],
                "note": "白天热=短裤/速干裤，傍晚冷=加穿保暖裤袜/压缩裤；两截拉链式徒步裤（拉链拆下变短裤）是最实用方案",
                "tags": ["通用户外", "滨水", "山地", "公园"],
                "priority": 85,
            },
            {
                "name": "围巾/丝巾（多功能）",
                "necessity": "推荐",
                "temp_range": [0, 20],
                "note": "早晚冷时护颈，可拆卸下来当作薄披肩/遮阳挡风；选羊绒混纺或轻薄羊毛材质，白天塞包里不占体积",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 82,
            },
            {
                "name": "可折叠背包/收纳袋",
                "necessity": "推荐",
                "temp_range": None,
                "note": "白天穿得少+傍晚加衣服，衣物存储量变化大；备一个10-15L可折叠收纳袋，脱下的衣物随时收进去，避免手忙脚乱",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 80,
            },
            {
                "name": "保温杯（热水/热茶）",
                "necessity": "推荐",
                "temp_range": [0, 15],
                "note": "早晚体感冷时喝一口热水瞬间提升核心体温；选500ml+不锈钢真空保温杯，保热12h+；白天装冷水也可保冷",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 78,
            },
            {
                "name": "暖宝宝/自发热贴（备用）",
                "necessity": "推荐",
                "temp_range": [-5, 8],
                "note": "若早晚温降超预期（如从25°C骤降到8°C），暖宝宝是最后一道防线；贴后腰/腹部/脚底，持续发热8-12小时",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 76,
            },
            {
                "name": "薄羊毛袜/美利奴袜（备用）",
                "necessity": "推荐",
                "temp_range": [0, 20],
                "note": "脚部保暖在大温差天容易被忽视；白天穿薄袜透气+晚上换厚羊毛袜保暖；美利奴羊毛袜排汗+天然抑菌防臭",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 74,
            },
            {
                "name": "便携折叠帽（可收纳）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "白天防晒遮阳+傍晚保暖；选可折叠渔夫帽或棒球帽，放包里随时取用",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 70,
            },
            {
                "name": "防晒霜（白天备用）",
                "necessity": "推荐",
                "temp_range": [20, 40],
                "note": "温差大的地区往往日照强（如高原/沙漠），白天紫外线不容忽视；SPF30+防水型，小瓶装随身携带",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 72,
            },
            {
                "name": "小包装纸巾（多包）",
                "necessity": "推荐",
                "temp_range": None,
                "note": "温差大容易流鼻涕（鼻黏膜受刺激），随身多包纸巾是刚需",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 65,
            },
            {
                "name": "薄手套/防晒手套",
                "necessity": "可选",
                "temp_range": [10, 25],
                "note": "早晚温差10-15°C时，早晨骑车/步行手指偏冷；薄款触屏手套既防晒又保暖",
                "tags": ["通用户外", "滨水", "山地", "公园"],
                "priority": 58,
            },
            {
                "name": "凡士林/润唇膏",
                "necessity": "推荐",
                "temp_range": [0, 15],
                "note": "大温差+干燥风=嘴唇干裂+手部皲裂的完美配方；出门前涂抹凡士林+带润唇膏随时补涂",
                "tags": ["通用户外", "滨水", "山地", "公园", "休闲"],
                "priority": 68,
            },
        ],
        "scenes": {
            "山地": [
                {
                    "name": "硬壳冲锋衣（极端温差山地区）",
                    "necessity": "必带",
                    "temp_range": [-10, 25],
                    "note": "山地昼夜温差可达15-25°C，且海拔每升100m气温降0.6°C；山顶可能比山脚低10°C+大风，硬壳冲锋衣防风防水一步到位",
                    "tags": ["山地"],
                    "priority": 99,
                },
                {
                    "name": "保暖抓绒帽/线帽",
                    "necessity": "必带",
                    "temp_range": [-10, 10],
                    "note": "山项傍晚/早晨气温可能≤5°C，头部散热巨大；戴压缩后可收纳的薄抓绒帽，比厚毛线帽更实用",
                    "tags": ["山地"],
                    "priority": 96,
                },
                {
                    "name": "排汗速干内衣（美利奴）",
                    "necessity": "必带",
                    "temp_range": [-5, 20],
                    "note": "山地温差大+运动出汗=着凉高风险；美利奴羊毛内衣排汗+天然抑菌，早晚贴身保暖不闷汗；150-200g/m²厚度最通用",
                    "tags": ["山地"],
                    "priority": 95,
                },
                {
                    "name": "急救保温毯",
                    "necessity": "推荐",
                    "temp_range": [-10, 5],
                    "note": "山地失温风险比平地高3倍；保温毯（约50g）可反射80%体温，偶遇气温断崖下降时保命",
                    "tags": ["山地"],
                    "priority": 88,
                },
                {
                    "name": "防水保暖手套",
                    "necessity": "推荐",
                    "temp_range": [-5, 10],
                    "note": "山间早晚+手部静止不动时最冷；选Primaloft/Thinsulate保暖棉+外层防风防水手套",
                    "tags": ["山地"],
                    "priority": 84,
                },
                {
                    "name": "能量补充（高热量零食）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "大温差下身体调节能耗增加30%+；坚果/巧克力/能量棒随时补充，别等饿了才吃",
                    "tags": ["山地"],
                    "priority": 76,
                },
                {
                    "name": "头灯/手电（天黑备用）",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "秋冬白天短+山地日照更短，温差大的季节通常日落早（17:00-18:00）；头灯防迷路+防摔",
                    "tags": ["山地"],
                    "priority": 80,
                },
            ],
            "滨水": [
                {
                    "name": "防风防水冲锋裤",
                    "necessity": "必带",
                    "temp_range": [0, 20],
                    "note": "滨水区域昼夜温差+水面风寒效应(Wind Chill)，体感温度比陆地低5-10°C；硬壳冲锋裤+可拆卸保暖内衬最实用",
                    "tags": ["滨水"],
                    "priority": 95,
                },
                {
                    "name": "防水徒步鞋（高帮）",
                    "necessity": "推荐",
                    "temp_range": [-5, 20],
                    "note": "早晚滨水步道露水重+近水潮气重，普通鞋在早晨被露水打湿后一天都不干；高帮GTX鞋+速干袜",
                    "tags": ["滨水"],
                    "priority": 86,
                },
                {
                    "name": "速干保暖内衣",
                    "necessity": "推荐",
                    "temp_range": [0, 15],
                    "note": "滨水湿度高+温差大=体感湿冷；棉质内衣吸湿后湿冷感加倍，美利奴羊毛/化纤速干是唯一选择",
                    "tags": ["滨水"],
                    "priority": 82,
                },
                {
                    "name": "防风围脖/面罩",
                    "necessity": "推荐",
                    "temp_range": [0, 15],
                    "note": "滨水早晚常有阵风，冷风直接灌入衣领；Buff多功能面罩护住颈部+口鼻",
                    "tags": ["滨水"],
                    "priority": 78,
                },
            ],
            "公园": [
                {
                    "name": "野餐垫（防潮款）",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "早晚温差大时草坪可能有露水或反潮，铝箔防潮垫隔潮+反射地温",
                    "tags": ["公园"],
                    "priority": 65,
                },
                {
                    "name": "保温便当盒/焖烧罐",
                    "necessity": "可选",
                    "temp_range": [0, 15],
                    "note": "早晚温差天带热食出门，中午可能凉了；真空焖烧罐装热汤/热粥/热饭，保热6h+；比冷餐幸福感翻倍",
                    "tags": ["公园"],
                    "priority": 62,
                },
                {
                    "name": "折叠坐垫/便携椅",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "早晚公园长椅冰凉不适合直接坐；带可折叠的隔冷坐垫（蛋巢泡沫/充气款）",
                    "tags": ["公园"],
                    "priority": 56,
                },
                {
                    "name": "防风帐篷/遮阳棚",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "如需在公园一整天，帐篷提供白天遮阳+傍晚防风挡寒的双重功能",
                    "tags": ["公园"],
                    "priority": 48,
                },
            ],
            "休闲": [
                {
                    "name": "室内-户外灵活切换方案",
                    "necessity": "推荐",
                    "temp_range": None,
                    "note": "温差大天最佳策略：白天户外（公园/茶馆）→傍晚转室内（咖啡馆/餐厅/图书馆）；提前规划好备选室内场所",
                    "tags": ["休闲"],
                    "priority": 90,
                },
                {
                    "name": "轻薄披肩/开衫（可放包里）",
                    "necessity": "推荐",
                    "temp_range": [10, 22],
                    "note": "逛商场/室内场所空调可能开得很冷，从户外29°C进室内22°C也算温差；轻薄开衫方便穿脱，比外套更优雅",
                    "tags": ["休闲"],
                    "priority": 72,
                },
                {
                    "name": "可折叠购物袋",
                    "necessity": "可选",
                    "temp_range": None,
                    "note": "白天户外活动买了东西+傍晚加穿的衣服，可能会多出一个包的容量；备用折叠袋解决",
                    "tags": ["休闲"],
                    "priority": 45,
                },
            ],
        },
    },
}

# ─══════════════════════════════════════════
#  核心 API
# ─══════════════════════════════════════════

def get_checklist(
    weather_category: str = "sunny",
    scene_type: Optional[str] = None,
    temp: Optional[float] = None,
) -> dict:
    """获取指定天气分类的装备建议清单。

    Args:
        weather_category: 天气分类名（sunny, overcast, rainy 等）
        scene_type: 场景类型过滤（如 "滨水", "山地", "公园", "休闲", "通用户外"）
                      None = 返回所有通用项 + 所有场景项
        temp: 当前温度(°C)，用于过滤 temp_range

    Returns:
        dict: {
            "category": str,          # 天气分类
            "label": str,             # 中文标签
            "icon": str,              # 天气图标
            "default_category": str,  # 默认活动类别
            "scene_type": str|None,   # 当前过滤的场景类型
            "total": int,             # 装备总数
            "must_have": int,         # 必带数
            "recommended": int,       # 推荐数
            "optional": int,          # 可选数
            "items": [ ... ],         # 装备列表（按必要性分组排序）
        }
    """
    cat_data = EQUIPMENT_DB.get(weather_category)
    if not cat_data:
        # 回退到 sunny
        cat_data = EQUIPMENT_DB["sunny"]

    items: list[dict] = []

    # 1. 通用项
    for item in cat_data.get("common", []):
        if scene_type and scene_type not in item.get("tags", []):
            continue
        if not _temp_filter(item, temp):
            continue
        items.append(item.copy())

    # 2. 场景专属项
    if scene_type:
        scenes = cat_data.get("scenes", {})
        scene_items = scenes.get(scene_type, [])
        for item in scene_items:
            if not _temp_filter(item, temp):
                continue
            items.append(item.copy())
    else:
        # 没有指定场景类型时，收集所有场景项（去重）
        seen_names = set()
        for scene_items in cat_data.get("scenes", {}).values():
            for item in scene_items:
                if item["name"] not in seen_names:
                    seen_names.add(item["name"])
                    if not _temp_filter(item, temp):
                        continue
                    items.append(item.copy())

    # 3. 排序：先按必要性（必带>推荐>可选），再按优先级
    necessity_order = {"必带": 0, "推荐": 1, "可选": 2}
    items.sort(key=lambda x: (necessity_order.get(x["necessity"], 9), -x.get("priority", 0)))

    # 4. 统计
    must_have = sum(1 for i in items if i["necessity"] == "必带")
    recommended = sum(1 for i in items if i["necessity"] == "推荐")
    optional = sum(1 for i in items if i["necessity"] == "可选")

    return {
        "category": weather_category,
        "label": cat_data.get("label", weather_category),
        "icon": cat_data.get("icon", "🌤️"),
        "default_category": cat_data.get("default_category", "通用"),
        "scene_type": scene_type,
        "total": len(items),
        "must_have": must_have,
        "recommended": recommended,
        "optional": optional,
        "items": items,
    }


def _temp_filter(item: dict, temp: Optional[float]) -> bool:
    """根据温度范围过滤装备项"""
    tr = item.get("temp_range")
    if tr is None or temp is None:
        return True
    return tr[0] <= temp <= tr[1]


# ─══════════════════════════════════════════
#  格式化输出
# ─══════════════════════════════════════════

def format_checklist(
    result: dict,
    title: Optional[str] = None,
    compact: bool = False,
) -> str:
    """将装备清单格式化为终端友好的字符串输出。

    Args:
        result: get_checklist() 的返回值
        title: 自定义标题，None 则自动生成
        compact: 精简模式（只输出装备名+必要性）

    Returns:
        str: 格式化后的多行文本
    """
    if not title:
        title = f"{result['icon']} {result['label']}天气 · 装备建议清单"

    lines = []
    lines.append("=" * 60)
    lines.append(f"  {title}")
    lines.append(f"  活动建议: {result['default_category']}  |  ")
    lines.append(f"  统计: {result['total']}项装备")
    lines.append(f"        {result['must_have']}项必带  {result['recommended']}项推荐  {result['optional']}项可选")
    if result["scene_type"]:
        lines.append(f"  场景过滤: {result['scene_type']}")
    lines.append("=" * 60)
    lines.append("")

    if not result["items"]:
        lines.append("  (当前条件下无匹配装备)")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    # 按必要性分组输出
    necessity_groups = ["必带", "推荐", "可选"]
    group_labels = {"必带": "🔴 必带装备", "推荐": "🟡 推荐装备", "可选": "🟢 可选装备"}

    for nec in necessity_groups:
        group = [i for i in result["items"] if i["necessity"] == nec]
        if not group:
            continue

        lines.append(f"  ── {group_labels[nec]} ({len(group)}项) ──")
        lines.append("")

        for item in group:
            name = item["name"]
            note = item.get("note", "")
            tr = item.get("temp_range")

            temp_info = ""
            if tr:
                temp_info = f" [适温 {tr[0]}~{tr[1]}°C]"

            if compact:
                lines.append(f"    ✅ {name}{temp_info}")
            else:
                lines.append(f"    ✅ {name}{temp_info}")
                if note:
                    lines.append(f"       📝 {note}")
                lines.append("")

        lines.append("")

    lines.append("=" * 60)
    lines.append(f"  共 {result['total']} 项 · 请根据实际情况调整")
    lines.append("=" * 60)

    return "\n".join(lines)


# ─══════════════════════════════════════════
#  便捷查询（模块内部用）
# ─══════════════════════════════════════════

def list_available_categories() -> list[str]:
    """列出所有支持的天气分类"""
    return list(EQUIPMENT_DB.keys())


def list_scene_types(weather_category: str = "sunny") -> list[str]:
    """列出某天气分类下支持的场景类型"""
    cat_data = EQUIPMENT_DB.get(weather_category)
    if not cat_data:
        return []
    return list(cat_data.get("scenes", {}).keys())


# ─══════════════════════════════════════════
#  CLI 入口
# ─══════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # 解析参数: python equipment_checklist.py [weather_category] [scene_type]
    weather = sys.argv[1] if len(sys.argv) > 1 else "sunny"
    scene = sys.argv[2] if len(sys.argv) > 2 else None
    temp_str = sys.argv[3] if len(sys.argv) > 3 else None
    temp = float(temp_str) if temp_str else None

    result = get_checklist(weather_category=weather, scene_type=scene, temp=temp)
    print(format_checklist(result))
    print("")
    print(f"  可用天气分类: {', '.join(list_available_categories())}")
    if result["scene_type"] is None:
        print(f"  可用场景类型({weather}): {', '.join(list_scene_types(weather))}")
