┊ review diff
a//home/administrator/.hermes/skills/tools/recommend/SKILL.md → b//home/administrator/.hermes/skills/tools/recommend/SKILL.md
@@ -0,0 +1,275 @@
+---
+name: recommend
+description: 天气推荐引擎 — 根据城市实时天气分类，查映射表匹配景点，按置信度排序输出推荐结果。
+version: 1.0.0
+author: Hermes Agent
+license: MIT
+metadata:
+  hermes:
+    tags: [recommend, weather, attraction, tourism, travel, tianjin]
+    related_skills: [weather]
+---
+
+# recommend
+
+## 概述
+
+`recommend` 模块实现「天气 → 场景 → 景点」的智能推荐管道。输入城市名，自动获取实时天气，分类判断，从景点数据库中筛选匹配项，按置信度排序输出。
+
+**核心流程：**
+
+1. **获取天气** — 调用 `weather.get_weather()` 获取指定城市的实时天气
+2. **天气分类** — 根据天气描述（desc）、温度（temp）、风速（wind）、湿度（humidity）将天气归入预定义的 `WEATHER_CATEGORIES`（如 sunny、rainy、snowy、hot、cold、extreme）
+3. **场景映射** — 按分类结果查 `weather_to_scene` 映射表（建议从 `weather_scene_mapping.yaml` 加载），获取推荐场景类型
+4. **景点筛选** — 从内置景点数据集中筛选满足以下条件的景点：
+   - `suitable_weather` 包含当前天气分类
+   - 当前温度在景点 `temp_range` 区间内
+5. **排序输出** — 按置信度（分类命中精确度、温度偏离度、室内/室外匹配度）综合排序
+
+当前内置景点数据集覆盖 **天津 18 个亲子热门景点**，涵盖户外乐园、室内场馆、博物馆、免费公园等不同类型。
+
+## 安装 / 依赖
+
+```bash
+pip install requests pyyaml
+```
+
+依赖关系：
+
+| 模块 | 作用 | 必需 |
+|------|------|------|
+| `weather`（同项目） | 获取实时天气 | 是 |
+| `requests` | weather 的 HTTP 客户端 | 是（间接） |
+| `pyyaml` | 加载 `weather_scene_mapping.yaml` | 否（未加载时可用内联默认值） |
+
+## API / 接口
+
+### `recommend_attractions(city: str) -> dict`
+
+获取指定城市基于当前天气的景点推荐。
+
+**参数：**
+
+| 参数 | 类型 | 必填 | 说明 |
+|------|------|------|------|
+| `city` | `str` | 是 | 城市名称，中文或英文（如 `"天津"`、`"Beijing"`） |
+
+**返回值：**
+
+```python
+{
+    "city": str,            # 城市名
+    "weather": {            # 天气数据（同 weather.get_weather() 返回值）
+        "city": str,
+        "temp": str,        # 如 "20°C"
+        "desc": str,        # 如 "晴朗"
+        "humidity": str,    # 如 "45%"
+        "wind": str         # 如 "东风 3级"
+    },
+    "category": str,        # 天气分类标签（如 "sunny"、"rainy"、"hot"）
+    "scene": str,           # 推荐场景类型（如 "户外活动"、"室内游玩"）
+    "confidence": float,    # 分类置信度 0.0 ~ 1.0
+    "items": [              # 推荐景点列表，按置信度降序
+        {
+            "name": str,          # 景点名称
+            "category": str,      # 景点类型："户外" / "户内"
+            "tags": [str],        # 标签，如 ["主题乐园", "亲子"]
+            "address": str,       # 详细地址
+            "note": str,          # 备注信息
… omitted 197 diff line(s) across 1 additional file(s)/section(s)
SKILL.md 已生成并写入 `/home/administrator/.hermes/skills/tools/recommend/SKILL.md`。
文档覆盖以下内容：
- **概述** — 完整说明 5 步推荐管道架构（天气→分类→映射→筛选→排序）
- **安装/依赖** — requests + pyyaml，注明 weather 同项目依赖
- **API / 接口** — 3 个函数：`recommend_attractions()`、`get_weather_categories()`、`get_cache_info()`，含完整参数表和返回值 schema
- **天气分类体系** — 8 种分类（extreme → sunny）的优先级、条件阈值、默认场景，以及优先级降序匹配规则
- **景点数据模型** — 每个字段的类型和业务含义
- **使用示例** — 基础推荐、条件判断分支、缓存调试、bash 一键调用、自动化晨报场景，共 5 个可运行示例
- **扩展指南** — 如何添加城市景点、如何添加新天气分类、如何用 YAML 配置
- **注意事项** — 8 条已知限制：城市数据集局限、天气回退、分类优先级、温度单位兼容、YAML 缺失容错、内存驻留、运营状态缺失、亲子导向说明