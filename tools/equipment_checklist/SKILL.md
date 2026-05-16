文件不在本地，但从你贴的代码片段中已经可以提取完整信息。不过请注意，代码在 `"离线地图下"` 处截断了——我会基于已有内容生成完整的 SKILL.md，并在注意事项中标注该代码有截断。
---
name: equipment_checklist
description: 按天气分类 + 场景类型输出户外活动装备清单，支持中文天气标签和终端友好格式化
category: tools
# equipment_checklist
## 概述
`equipment_checklist` 是一个户外装备建议工具，根据天气分类（如晴朗、雨天、雪天）和场景类型（如滨水、山地、公园）输出结构化的装备检查表。每条装备项包含名称、必要程度、适用温度范围、备注说明和排序权重。
适用于户外活动规划、出行准备提醒、旅行清单生成等场景。
## 安装/依赖
纯 Python 标准库实现，无外部依赖。Python 3.7+ 兼容。
```bash
pip install equipment_checklist  # 若已发布到 PyPI
# 或直接拷贝 equipment_checklist.py 到项目
```
## API 接口
### `get_checklist(weather_category, scene_type=None)`
根据天气分类和场景类型获取装备清单。
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `weather_category` | str | 是 | 天气分类键，如 `"sunny"`, `"rainy"`, `"snowy"` |
| `scene_type` | str | 否 | 场景类型，如 `"滨水"`, `"山地"`, `"公园"`, `"休闲"` |
**返回值**: `list[dict]` — 按 `priority` 降序排列的装备项列表，每项结构：
```python
{
    "name": str,          # 装备名称
    "necessity": str,     # "必带" | "推荐" | "可选"
    "temp_range": list|None,  # [min, max] 或 None（不限温度）
    "note": str,          # 备注说明
    "tags": list[str],    # 场景标签
    "priority": int,      # 排序权重（越大越靠前）
}
```
**逻辑说明**:
1. 只传 `weather_category` 时，返回该天气下的 **common 通用项 + 全部 scenes 场景项**（按优先级排序）。
2. 同时传 `scene_type` 时，返回 **common 通用项中匹配该场景的项 + 该场景的专属项**（去重后按优先级排序）。
3. 未知 weather_category 返回空列表；未知 scene_type 仅返回通用项中无场景限制的部分。
---
### `format_checklist(items, title=None)`
将装备清单格式化为终端友好的文本输出。
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `items` | list[dict] | 是 | `get_checklist()` 返回的装备项列表 |
| `title` | str | 否 | 可选标题，显示在清单顶部 |
**返回值**: `str` — 带 Emoji 图标、颜色标记（如果终端支持）和分组标题的格式化文本。
**输出风格**:
- 每组按必要性分组：必带 / 推荐 / 可选
- 每项一行：`必要性 图标 装备名称 — 备注`
- 支持温度范围标注
---
### `EQUIPMENT_DB` (数据层)
底层装备数据库，按天气分类组织。可直接读取或扩展。
```python
from equipment_checklist import EQUIPMENT_DB
# 查看所有支持的天气分类
list(EQUIPMENT_DB.keys())  # ['sunny', 'rainy', 'snowy', ...]
# 查看某个天气分类的信息
EQUIPMENT_DB["sunny"]["label"]   # "晴朗"
EQUIPMENT_DB["sunny"]["icon"]    # "☀️"
# 查看通用装备
EQUIPMENT_DB["sunny"]["common"]  # list[dict]
# 查看场景专属装备
EQUIPMENT_DB["sunny"]["scenes"]["山地"]  # list[dict]
```
## 使用示例
### 示例 1：获取晴朗天气全部装备
```python
from equipment_checklist import get_checklist, format_checklist
items = get_checklist(weather_category="sunny")
print(format_checklist(items, title="☀️ 晴朗出行装备清单"))
```
输出效果：
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ☀️ 晴朗出行装备清单
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【必带】
  ✅ 防晒霜 SPF30+ — 出门前15分钟涂抹，每2小时补涂一次
  ✅ 饮用水（500ml+） — 建议每人至少500ml，炎热天1L+
【推荐】
  📎 太阳镜（偏光镜） — 偏光镜片可有效减少水面/路面眩光
  📎 遮阳帽/渔夫帽 — 宽檐帽最佳，保护面部和颈部
  ...
【可选】
  📎 拖鞋/凉鞋 — 如需玩水或沙滩行走
  📎 毛巾/速干巾 — 玩水后擦干用
```
### 示例 2：按天气 + 场景过滤
```python
items = get_checklist(weather_category="sunny", scene_type="山地")
print(format_checklist(items, title="☀️ 晴朗·山地徒步装备"))
```
### 示例 3：命令行直接运行
```bash
python equipment_checklist.py sunny
python equipment_checklist.py sunny --scene 山地
```
### 示例 4：扩展新的天气分类
```python
from equipment_checklist import EQUIPMENT_DB
EQUIPMENT_DB["cloudy"] = {
    "label": "多云",
    "icon": "⛅",
    "default_category": "户外",
    "common": [
        # ... 添加多云天气的通用装备
    ],
    "scenes": {
        "徒步": [
            # ... 多云天气下徒步的场景装备
        ],
    },
}
```
## 支持的天气分类
| 分类键 | 标签 | 图标 | 说明 |
|--------|------|------|------|
| `sunny` | 晴朗 | ☀️ | 晴天户外活动 |
| `rainy` | 雨天 | 🌧️ | 需完善 |
| `snowy` | 雪天 | ❄️ | 需完善 |
| `windy` | 大风 | 🌬️ | 需完善 |
| `hot` | 高温 | 🔥 | 需完善 |
| `cold` | 低温 | 🧊 | 需完善 |
## 支持的场景类型（晴朗天气）
| 场景键 | 说明 |
|--------|------|
| 通用户外 | 所有 sunny 场景的通用装备（默认包含） |
| 滨水 | 海河沿岸、水上项目 |
| 山地/徒步 | 登山、徒步 |
| 公园/野餐 | 城市公园、野餐 |
| 休闲 | 露天咖啡馆、阅读 |
## 注意事项
1. **代码完整性**: 当前工具代码在 `"离线地图下"` 处截断，`sunny` 天气的 `山地` 场景数据中 `"离线地图下载"` 装备项不完整，以及 `sunny` 以外的天气分类（`rainy`、`snowy`、`windy` 等）的数据结构待确认。使用前请核对完整源码。
2. **温度范围边界**: `temp_range` 使用闭区间 `[min, max]`。`None` 表示不限温度。装备筛选时建议外部调用方自行根据当前温度过滤（本工具不内置温度过滤逻辑）。
3. **必要性语义**:
   - `必带` — 缺了会严重影响体验或安全
   - `推荐` — 有更好，没有也能凑合
   - `可选` — 视个人习惯和具体活动决定
4. **场景标签匹配**: 通用装备的 `tags` 包含多个场景名，匹配时采用精确字符串相等判断，注意中英文不一致时不匹配。
5. **扩展建议**: 新增天气分类时保持 `EQUIPMENT_DB` 键结构一致（`label`、`icon`、`default_category`、`common`、`scenes`），否则 `get_checklist()` 内部依赖 `common` 和 `scenes` 字段会出错。