---
name: weather-bridge
description: 天气桥接模块 — 为场景对话注入实时天气上下文，智能检测用户天气意图并自动获取结构化天气数据
category: tools
---
# weather_bridge
## 概述
`weather_bridge` 是一个轻量级天气上下文注入模块，专为场景对话系统（如坐山客 AI 工作台）设计。它在对话流中充当"中间件"：检测用户输入是否包含天气查询意图，如果是则自动调用 `weather.get_weather()` 获取实时数据，并将结果格式化为标准化的 prompt 上下文片段，供 LLM 消费。
核心场景：在 Agent 对话的 Pass 1 之前调用，将天气数据作为背景知识注入系统 prompt，使模型能基于真实天气而非训练数据记忆做出回应。
## 安装/依赖
- 无外部包依赖（仅使用 Python 标准库 `re`）
- 依赖同目录下的 `weather.py` 模块中的 `get_weather(city)` 函数
- `weather.py` 应当返回包含以下字段的 dict：
  - `city` (str): 城市名
  - `temp` (str): 当前温度
  - `desc` (str): 天气描述
  - `humidity` (str): 湿度
  - `wind` (str): 风力描述
  - `_source` (str, optional): 数据来源标识（`"api"` 或 `"fallback"`）
  - `forecast` (list[dict], optional): 未来预报数组，每项含 `date`/`desc`/`high`/`low`
## API / 接口
### `is_weather_query(text: str) -> bool`
判断文本是否包含天气查询意图。
**匹配策略（三层）：**
1. 必须同时包含天气关键词 **和** 城市名（中文城市列表 / 英文城市映射），否则返回 `False`
2. 例外：如果文本包含城市常见汉字 + 数字+度模式（如"北京20度"），即使没有天气关键词也触发
3. 纯"今天天气不错"（无城市名）→ 不触发
| 输入 | 结果 |
|------|------|
| `"北京天气怎么样"` | `True` |
| `"今天天气不错"` | `False` |
| `"上海20度"` | `True`（度数匹配） |
| `"beijing weather"` | `True`（英文+英关键词） |
| `"伦敦天气"` | `True`（英文城市映射） |
### `extract_city(text: str) -> str | None`
从文本中提取城市名。
- 优先匹配英文城市名（如 `beijing` → `"北京"`）
- 中文城市按名称长度降序匹配（避免"南京"被"南宁"截胡）
- 返回标准中文城市名
### `format_weather_for_prompt(weather_data: dict) -> str`
将天气 dict 格式化为结构化的 prompt 上下文片段。
输出示例：
```
【天气数据 - 北京】
- 温度: 21°C
- 天气: 晴朗
- 湿度: 45%
- 风力: 东北风 3级
- 未来预报:
  · 明天: 多云 22°C/15°C
  · 后天: 小雨 18°C/12°C
```
如果 `_source == "fallback"`，末尾追加 `(数据来源: 本地估算，非实时)`。
### `maybe_weather_context(user_text: str) -> str | None`
**主入口**。一次调用完成"检测→提取→查询→格式化"全流程。
| 参数 | 类型 | 说明 |
|------|------|------|
| `user_text` | str | 用户输入的对话文本 |
| **返回** | str \| None | 格式化天气字符串，非天气查询返回 `None` |
异常安全：如果 `get_weather()` 抛出异常，返回 `"【天气查询失败】{city} 天气查询出错: {e}"`，不会中断调用方。
## 使用示例
### 在场景对话中集成
```python
from tools.weather_bridge import maybe_weather_context
def build_scene_prompt(user_input: str) -> str:
    base_prompt = "你是一个天气助手..."
    weather_info = maybe_weather_context(user_input)
    if weather_info:
        base_prompt += f"\n\n{weather_info}\n\n请基于以上实时天气数据回答。"
    return base_prompt
```
### 直接运行测试（CLI）
```bash
cd path/to/tools/
python weather_bridge.py
```
输出：
```
[✓] '北京天气怎么样' → 触发天气查询
     【天气数据 - 北京】
     ...
[ ] '今天天气不错' → 未触发
```
## 注意事项
1. **城市覆盖有限**：目前内置约 67 个中国城市的中文名称 + 19 个常见英文城市映射。小城市/县级市需要扩展 `KNOWN_CITIES` 或 `EN_CITIES`。
2. **意图识别不是 AI 级别**：`is_weather_query()` 基于关键词和正则匹配，无法理解"明天出门要带伞吗？"这种隐式天气询问（不含"天气"关键词且无城市名）。如果你的场景需要更强语义理解，考虑替换为 LLM 分类。
3. **"市"后缀问题**：用户说"北京市"不触发（城市列表中没有带"市"的条目）。如果需要支持，加 `"北京市": "北京"` 映射或修改匹配逻辑去掉尾部"市"字。
4. **`weather.py` 必须同目录**：工具通过 `sys.path.insert(0, dirname)` 引入同级模块。如果项目结构变化（如 `weather.py` 移走），需要调整 import 路径。
5. **异常不吞没**：所有调用链上的异常（网络超时、API 密钥错误、解析失败）都会以带 `【天气查询失败】` 前缀的字符串返回，调用方可根据 `"【天气查询失败】"` 前缀判断异常场景。
6. **性能**：`is_weather_query()` 每次遍历完整的城市列表，约 67 次字符串包含判断 + 约 19 次英文映射。单次调用 < 1ms，可作为每条对话的 Pass 1 前置调用。