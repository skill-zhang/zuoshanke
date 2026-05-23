# Browser Dial Test — API 参考文档

_版本: v0.1 | 状态: 设计参考 | 关联: docs/design/self-dev-scene.md §3.3_

---

## 1. 安装

```bash
pip install playwright
playwright install chromium
```

安装后在 `tools/browser_dial_test.py` 文件中初始化一次浏览器实例（复用，不每次启动）：

```python
from playwright.sync_api import sync_playwright

_browser = None

def _get_browser():
    global _browser
    if _browser is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
    return _browser
```

**资源考量**：Chromium headless 约 200MB 内存，每次拨测 2-5 秒。单浏览器实例可复用，每次 `new_page()` + `close()` 即可。并发拨测限制每个场景 1 个。

---

## 2. Pydantic 响应模型

```python
# schemas.py — 新增

from pydantic import BaseModel
from typing import Optional


# ── Dial Test 完整响应 ──

class RectInfo(BaseModel):
    """元素位置和尺寸"""
    x: float
    y: float
    w: float
    h: float

class ScrollInfo(BaseModel):
    """滚动信息 — 用于检测内容溢出/截断"""
    height: int      # scrollHeight
    client_height: int   # clientHeight
    @property
    def overflowed(self) -> bool:
        return self.height > self.client_height

class ComputedStyle(BaseModel):
    """元素计算样式（精选字段，不返回全部）"""
    display: Optional[str] = None
    overflow: Optional[str] = None
    overflow_x: Optional[str] = None
    overflow_y: Optional[str] = None
    position: Optional[str] = None
    font_size: Optional[str] = None
    color: Optional[str] = None
    background: Optional[str] = None
    opacity: Optional[str] = None
    visibility: Optional[str] = None

class DOMElement(BaseModel):
    """DOM 元素快照"""
    selector: str           # Playwright 可复用的选择器（如 div.card-grid > div.card:nth-child(1)）
    tag: str                # HTML 标签名
    rect: RectInfo
    computed_style: ComputedStyle = ComputedStyle()
    scroll: Optional[ScrollInfo] = None    # 仅容器元素有
    children: list["DOMElement"] = []      # 仅包含直接子元素摘要
    text_content: Optional[str] = None     # 文本内容（截断到前 200 字）
    visible: bool = True                   # 是否可见

class ConsoleEntry(BaseModel):
    """控制台日志条目"""
    level: str           # "error" | "warning" | "info" | "log"
    text: str            # 日志文本
    count: int = 1       # 同级别同文本的重复次数（Playwright 可去重）

class NetworkEntry(BaseModel):
    """网络请求记录"""
    url: str
    status: int           # 0 = 未完成/失败
    method: str = "GET"
    type: str             # "xhr" | "script" | "stylesheet" | "image" | "document" | "fetch" | "other"
    duration_ms: float
    size: int = 0         # 响应体大小（bytes）
    success: bool = True  # status in [200, 399]

class PerformanceMetrics(BaseModel):
    """性能指标"""
    fcp_ms: float = 0     # First Contentful Paint
    lcp_ms: float = 0     # Largest Contentful Paint
    cls: float = 0        # Cumulative Layout Shift
    ttfb_ms: float = 0    # Time To First Byte

class DialAssertResult(BaseModel):
    """单条断言结果"""
    name: str
    passed: bool
    expected: Optional[str] = None
    actual: Optional[str] = None
    error: Optional[str] = None

class DialTestReport(BaseModel):
    """完整拨测报告"""
    url: str
    viewport: str = "1440x900"
    timestamp: str        # ISO 格式
    duration_ms: float    # 总耗时
    screenshot: Optional[str] = None  # 文件路径

    dom: list[DOMElement] = []        # 页面 DOM 根元素（含子元素递归摘要）
    console: list[ConsoleEntry] = []
    network: list[NetworkEntry] = []
    performance: PerformanceMetrics = PerformanceMetrics()

    # 内置断言摘要
    assertions: list[DialAssertResult] = []
    passed: bool = True               # 所有断言通过

    # 快速诊断摘要（LLM 不用逐条看时的首选）
    summary: str = ""                 # LLM 可读的一句话摘要


# ── Dial Style 响应 ──

class StyleSnapshot(BaseModel):
    """单个元素的样式快照"""
    selector: str
    visible: bool
    rect: RectInfo
    style: ComputedStyle

class DialStyleReport(BaseModel):
    """样式快照报告"""
    url: str
    elements: list[StyleSnapshot]
    timestamp: str


# ── Dial Assert 入参规则 ──

class StyleRule(BaseModel):
    """CSS 样式断言规则"""
    property: str          # CSS 属性名（如 "overflow", "font-size"）
    operator: str = "=="   # "==" | "!=" | "contains" | "regex"
    value: str             # 期望值

class CountRule(BaseModel):
    """元素数量断言规则"""
    selector: str
    operator: str = "gte"  # "eq" | "gte" | "lte" | "gt" | "lt"
    value: int

class AssertionRule(BaseModel):
    """单条断言规则"""
    name: str                                   # 可读名称
    type: str                                   # "style" | "count" | "console" | "condition"

    # style 类型
    selector: Optional[str] = None
    style_rules: Optional[list[StyleRule]] = None

    # count 类型
    count_selector: Optional[str] = None
    count_rule: Optional[CountRule] = None

    # console 类型
    console_errors: Optional[int] = 0          # 期望控制台错误数

    # condition 类型
    condition: Optional[str] = None            # 条件表达式字符串

class DialAssertRequest(BaseModel):
    """断言检卷入参"""
    url: str
    viewport: str = "1440x900"
    rules: list[AssertionRule]
```

---

## 3. 三个工具接口的详细签名

### 3.1 `dial_test(url, viewport, screenshot=True)`

```python
def dial_test(
    url: str,
    viewport: str = "1440x900",       # 视口尺寸 "宽x高"
    screenshot: bool = True,          # 是否保存截图
) -> DialTestReport:
    """
    完整拨测：打开页面，返回 DOM 快照 + Console + Network + 性能 + 可选截图。

    内部流程：
      1. 创建新页面，设置 viewport
      2. 启动 console 监听（page.on("console")）
      3. 启动 network 监听（page.on("request") + page.on("response")）
      4. 导航到 url（wait_until="networkidle"）
      5. 提取 DOM 快照（page.evaluate 递归取 rect + computedStyle + scroll）
      6. 收集 Console 日志（去重）
      7. 收集 Network 瀑布
      8. 提取 Performance 指标（page.evaluate 取 performance.getEntriesByType）
      9. 截图（page.screenshot）
      10. 关闭页面
      11. 生成 LLM 可读的 summary 文本
      12. 返回 DialTestReport

    Notes:
      - 耗时 2-5 秒
      - Chrome headless 无需显示器
      - screenshot 存 /tmp/screenshots/dial_{timestamp}.png
    """
```

### 3.2 `dial_style(url, selectors, viewport)`

```python
def dial_style(
    url: str,
    selectors: list[str],             # CSS 选择器列表，如 [".card-grid", ".sidebar > nav"]
    viewport: str = "1440x900",
) -> DialStyleReport:
    """
    只提取特定元素的计算样式。比 dial_test 更快（不收集 network/console）。
    用于快速排查 CSS 问题。

    每个选择器提取：
      - rect（位置 + 尺寸）
      - computedStyle（精选字段：display, overflow, font-size, color, background, ...）
      - visible（是否可见）
    """
```

### 3.3 `dial_assert(url, rules, viewport)`

```python
def dial_assert(
    url: str,
    rules: list[AssertionRule],       # 断言规则列表
    viewport: str = "1440x900",
) -> list[DialAssertResult]:
    """
    断言式检查。每条规则独立执行，全部报告通过/失败。

    规则类型:
      type="style":   检查元素的 CSS 属性值
        例: {type:"style", selector:".card-grid",
             style_rules:[{property:"overflow", operator:"==", value:"hidden auto"}]}

      type="count":   检查匹配选择器的元素数量
        例: {type:"count", count_selector:".card", count_rule:{operator:"gte", value:3}}

      type="console": 检查控制台错误数量
        例: {type:"console", console_errors:0}

      type="condition": 检查条件表达式（JS eval 在页面上下文中）
        例: {type:"condition", name:"滚动可见", condition:"document.querySelector('.card-grid').scrollHeight > document.querySelector('.card-grid').clientHeight"}
        注意：condition 类型有安全风险，只在自开发场景中可用
    """
```

---

## 4. 断言语法速查

### 4.1 CSS 属性断言 (type="style")

| operator | 含义 | 示例 |
|----------|------|------|
| `==` | 等于（精确匹配） | `overflow == hidden auto` |
| `!=` | 不等于 | `display != none` |
| `contains` | 包含子串 | `background contains rgba` |
| `regex` | 正则匹配 | `font-size regex \d+px` |

### 4.2 数量断言 (type="count")

| operator | 含义 | 示例 |
|----------|------|------|
| `eq` | 精确等于 | `.card count eq 6` |
| `gte` | 大于等于 | `.card count gte 3` |
| `lte` | 小于等于 | `.sidebar-item count lte 20` |
| `gt` | 大于 | `.message count gt 0` |
| `lt` | 小于 | `.toast count lt 3` |

### 4.3 控制台断言 (type="console")

```python
# 验证无错误
{"type": "console", "console_errors": 0}

# 验证无警告
{"type": "console", "console_errors": 0, "console_warnings": 0}

# 验证特定错误不在 console 中
{"type": "console", "forbidden_pattern": "Uncaught TypeError"}
```

### 4.4 条件断言 (type="condition")

在页面 DOM 上下文中执行 JavaScript 表达式：

```python
# 验证滚动条存在
{"type": "condition",
 "name": "卡片容器有滚动",
 "condition": "document.querySelector('.card-grid').scrollHeight > document.querySelector('.card-grid').clientHeight"}

# 验证特定元素不在视口外
{"type": "condition",
 "name": "所有卡片可见",
 "condition": "document.querySelectorAll('.card').length === document.querySelectorAll('.card:visible').length"}
```

---

## 5. LLM summary 生成策略

`DialTestReport.summary` 是给 LLM 快速阅读的一句话诊断摘要，由后端自动生成：

```python
def _generate_summary(report: DialTestReport) -> str:
    parts = []

    # 控制台错误
    errors = [e for e in report.console if e.level == "error"]
    if errors:
        parts.append(f"控制台 {len(errors)} 个错误: {' | '.join(e.text[:80] for e in errors[:3])}")

    # 网络失败
    fails = [n for n in report.network if not n.success]
    if fails:
        parts.append(f"网络 {len(fails)} 个失败: {' | '.join(f.url for f in fails[:3])}")

    # 布局溢出
    overflowed = [e for e in report.dom if e.scroll and e.scroll.overflowed]
    if overflowed:
        parts.append(f"{len(overflowed)} 个容器内容溢出: {' | '.join(e.selector for e in overflowed[:3])}")

    # 性能告警
    if report.performance.lcp_ms > 2500:
        parts.append(f"LCP 较慢({report.performance.lcp_ms}ms)")
    if report.performance.cls > 0.1:
        parts.append(f"CLS 偏高({report.performance.cls:.2f})")

    if not parts:
        return "✅ 页面加载正常，无错误，无溢出，性能良好"

    return "⚠️ " + " | ".join(parts)
```

---

## 6. registry.json 注册格式

```json
{
  "name": "browser_dial_test",
  "description": "浏览器拨测 —— 打开指定URL，返回完整的页面状态报告：DOM快照（位置/尺寸/CSS/溢出）、Console日志、Network瀑布、性能指标。返回结构化JSON供AI分析。不要手动输入url（LLM自己拼接localhost地址）。用于验证前端页面渲染正确性。",
  "file": "tools/browser_dial_test.py",
  "function": "dial_test",
  "parameters": {
    "url": {"type": "string", "description": "页面URL（如 http://localhost:5173/scenes）"},
    "viewport": {"type": "string", "description": "视口尺寸，格式: 宽x高，默认 1440x900", "optional": true},
    "screenshot": {"type": "boolean", "description": "是否保存截图（截图路径在报告中返回）", "optional": true}
  },
  "category": "browser",
  "verified": false
},
{
  "name": "dial_style",
  "description": "只提取特定元素的CSS计算样式和位置。比dial_test更快，用于快速排查CSS问题。",
  "file": "tools/browser_dial_test.py",
  "function": "dial_style",
  "parameters": {
    "url": {"type": "string", "description": "页面URL"},
    "selectors": {"type": "array", "items": {"type": "string"}, "description": "CSS选择器列表"},
    "viewport": {"type": "string", "description": "视口尺寸", "optional": true}
  },
  "category": "browser",
  "verified": false
},
{
  "name": "dial_assert",
  "description": "断言式检查：验证页面元素CSS属性、数量、控制台状态。返回每个断言的通过/失败。",
  "file": "tools/browser_dial_test.py",
  "function": "dial_assert",
  "parameters": {
    "url": {"type": "string", "description": "页面URL"},
    "rules": {"type": "array", "items": {"type": "object"},
              "description": "断言规则列表。规则格式见工具文档。"},
    "viewport": {"type": "string", "description": "视口尺寸", "optional": true}
  },
  "category": "browser",
  "verified": false
}
```

> **注意**：tool description 的负向引导——拨测工具只验证**前端页面**，不是用于后端接口测试（后端用 curl）。url 参数是 LLM 自己拼接的 localhost 地址，不是用户提供的任意 URL。

---

## 7. 断言在 Agent Loop 中的典型用法

### 场景：Agent 改完 .card-grid 的 overflow

```python
# Agent 写代码后
report = dial_test("http://localhost:5173/scenes")
# 看 summary → "⚠️ 1 个容器内容溢出: div.card-grid"
# 看 dom → .card-grid: overflow="hidden"（没写 auto）

# Agent 修复
patch("card-grid", old="overflow: hidden", new="overflow: hidden auto")

# 断言验证
results = dial_assert("http://localhost:5173/scenes", rules=[
    {"name": "卡片容器滚动正常",
     "type": "style",
     "selector": ".card-grid",
     "style_rules": [{"property": "overflow", "operator": "contains", "value": "auto"}]},
    {"name": "无控制台错误",
     "type": "console",
     "console_errors": 0},
    {"name": "至少有 3 张卡片",
     "type": "count",
     "count_selector": ".card",
     "count_rule": {"operator": "gte", "value": 3}},
])
# 全部 passed ✅
```

---

## 8. 拨测工具在 registry.json 的定位

| 层级 | 工具 | 可见性 |
|------|------|--------|
| **核心工具** | weather, web_search, get_current_time | 所有场景 |
| **核心工具 ⭐** | browser_dial_test, dial_style, dial_assert | 所有场景 |
| **自开发专属** | clarify, delegate_task, git_tool | 仅自开发场景 |

`browser_dial_test` 是核心工具，因为它适用于任何会产生前端输出的场景。自开发场景里它用于验证坐山客自身的前端代码，旅游场景里它用于验证生成的景点页面。

---

## 9. 错误处理

| 错误场景 | 返回 | LLM 应如何处理 |
|----------|------|---------------|
| URL 不可达 | `{error: "Connection refused: http://localhost:5173"}` | 检查前端 dev server 是否启动，用 code_runner 启动后重试 |
| 页面加载超时（15s） | `{error: "Timeout: page did not fully load in 15s"}` | 检查 URL 是否正确，或页面是否有死循环 |
| 选择器不匹配 | `dial_style` 返回 `{element: {selector: "...", error: "not found"}}` | 检查选择器是否正确，或元素可能是动态渲染的 |
| 断言失败 | `dial_assert` 返回 `{passed: false, actual: "hidden", expected: "hidden auto"}` | 根据 actual 值调整代码 |
| 浏览器无响应 | `{error: "Browser engine not available"}` | 检查 playwright 是否已安装 |
