# dial_flow — 多步交互式浏览器拨测工具

_版本: v1.0 | 状态: 设计稿 | 关联: docs/references/browser-dial-test-api.md_

---

## 1. 问题诊断

### 1.1 现有工具的能力边界

`browser_dial_test.py` 提供了三个工具，但都是**无状态单页快照**：

| 工具 | 做什么 | 做不到什么 |
|------|--------|-----------|
| `dial_test` | 打开 URL → 拍 DOM + Console + Network + 截图 | **不能**点击、输入、导航 |
| `dial_style` | 打开 URL → 取指定元素的 computed style | **不能**交互 |
| `dial_assert` | 打开 URL → 跑断言规则数组 | **不能**交互 |

每次调用都走 `_run_in_thread` → 新线程 → 新 event loop → **全新 Playwright 实例** → 用完销毁。三工具之间零状态共享。

### 1.2 分身的行为差异根因

用户观察到的现象：

- **成功那次**：LLM 判断正确，走了 `run_code` + 裸 Playwright 脚本，手动完成三步骤（首页截图 → 点击系统工具 → 截图 → 点击技能管理 → 截图）
- **失败那次（99 轮 Agent Loop）**：LLM 反复调 `dial_test(http://localhost:5173)`，每次新浏览器打开都是首页，永远拍不到技能管理页面

**本质不是分身变笨了，是工具设计把两条都不靠谱的路摆在了 LLM 面前**：

| 路径 | LLM 做的事 | 风险 |
|------|-----------|------|
| 反复调 `dial_test` | "我调一下看看" × N | 永远首页，无限循环 |
| 写 Playwright 脚本 | `run_code` 写 30+ 行 Playwright | selector 写错一行全挂 |

第一次 LLM 碰巧走对了第二条路，后面赌错了走第一条——这就是行为不一致的根因。

### 1.3 解决方案

新增第四个工具 `dial_flow`：**接收声明式动作序列，在同一浏览器会话内顺序执行，每步自动截图**。

LLM 只用描述"做什么"，不用写 Playwright 代码。

---

## 2. 设计目标

| 目标 | 说明 |
|------|------|
| **声明式** | LLM 传 action 数组，不写 Playwright 代码 |
| **有状态** | 单次 `dial_flow` 调用内，浏览器会话保持（页面不重建） |
| **每步截图** | 每个关键动作自动截图，带 label 命名 |
| **容错** | 某步失败不崩，返回失败步骤信息，后续步骤仍可执行（可配） |
| **简洁** | 沿用现有 `_run_in_thread` 线程模型，不引入新依赖 |
| **LLM 友好** | action 语义直白，描述清晰（含反例），防止 LLM 误用 |

---

## 3. Action 类型定义

### 3.1 `goto` — 导航到 URL

在同一次浏览器会话中导航（不是新开页面）。

```json
{"action": "goto", "url": "http://localhost:5173"}
```

参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | ✅ | 目标 URL |

### 3.2 `click` — 点击元素

通过可见文本或 CSS 选择器定位并点击元素。

```json
{"action": "click", "text": "系统工具"}
{"action": "click", "selector": ".sidebar-section-header:has-text(\"系统工具\")"}
{"action": "click", "text": "系统工具", "selector": ".sidebar-section-header"}
```

参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 二选一 | 元素的可见文本（用 `:has-text()` 匹配） |
| `selector` | string | 二选一 | CSS 选择器。同时传 text 时优先用 selector + `:has-text(text)` |
| `force` | boolean | 否 | 默认 false。true 时跳过可见性检查（force click） |

**实现细节**：
- 优先用 `selector` + `text` 组合（`page.locator(selector).filter(has_text=text).click()`）
- 纯 `text` → `page.get_by_text(text).click()`
- 纯 `selector` → `page.locator(selector).click()`
- 点击后自动等 300ms（让 UI 反应），如果 `screenshot` 为 true 则立即截图

### 3.3 `wait` — 等待条件

```json
{"action": "wait", "ms": 500}
{"action": "wait", "selector": ".sv-tab-panel.active"}
{"action": "wait", "text": "技能管理"}
```

参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ms` | number | 三选一 | 等待毫秒数 |
| `selector` | string | 三选一 | 等待该 CSS 选择器可见 |
| `text` | string | 三选一 | 等待包含该文本的元素可见 |
| `timeout` | number | 否 | 超时毫秒数，默认 5000 |

### 3.4 `screenshot` — 截图

当前页面状态截图，带 label 标识。

```json
{"action": "screenshot", "label": "首页"}
{"action": "screenshot", "label": "技能管理页面", "full_page": true}
```

参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `label` | string | ✅ | 截图标签（用于结果中标识哪一步） |
| `full_page` | boolean | 否 | 默认 false。true 时截整页（含滚动内容） |
| `selector` | string | 否 | 只截指定元素区域 |

### 3.5 `snapshot` — DOM 快照

获取当前页面的结构化 DOM 快照（不含截图）。

```json
{"action": "snapshot"}
{"action": "snapshot", "selector": ".sidebar"}
```

参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `selector` | string | 否 | 默认 body。提取该元素及其子元素的 DOM 结构 |

### 3.6 `screenshot` 的隐式触发

为简化 LLM 调用，以下动作**自动在完成后截图**（除非显式传 `screenshot: false`）：

| 动作 | 自动截图？ | 原因 |
|------|-----------|------|
| `goto` | ✅ | 到达新页面，自然要记录 |
| `click` | ✅ | 点击后状态变化，需要记录 |
| `wait` | ❌ | 等待只是过渡，不自动截图 |
| `snapshot` | ❌ | 取 DOM 数据，不一定是视觉变化 |

每个动作可以显式传 `screenshot: true/false` 覆盖默认行为。

---

## 4. API 签名

### 4.1 函数签名

```python
def dial_flow(
    url: str,                              # 起始 URL
    actions: list[dict],                    # 动作序列
    viewport: str = "1440x900",             # 视口尺寸
    screenshot: bool = True,                # 全局截图开关（false 时不自动截图）
    stop_on_error: bool = False,            # true 时第一步失败就停止
) -> str:                                   # 返回 JSON 字符串
```

### 4.2 返回结构

```json
{
  "url": "http://localhost:5173",
  "viewport": "1440x900",
  "duration_ms": 8450,
  "total_steps": 4,
  "completed_steps": 4,
  "success": true,
  "steps": [
    {
      "index": 0,
      "action": "goto",
      "label": "",
      "success": true,
      "url_after": "http://localhost:5173",
      "title_after": "坐山客",
      "screenshot_path": "/home/administrator/.hermes/dial_shots/dial_flow_a1b2c3d4_step0.png",
      "duration_ms": 3100
    },
    {
      "index": 1,
      "action": "click",
      "text": "系统工具",
      "success": true,
      "url_after": "http://localhost:5173",
      "title_after": "坐山客",
      "screenshot_path": "/home/administrator/.hermes/dial_shots/dial_flow_a1b2c3d4_step1.png",
      "clicked_selector": ".sidebar-section-header >> text=系统工具",
      "duration_ms": 800
    },
    {
      "index": 2,
      "action": "click",
      "text": "技能管理",
      "success": true,
      "url_after": "http://localhost:5173",
      "title_after": "坐山客",
      "screenshot_path": "/home/administrator/.hermes/dial_shots/dial_flow_a1b2c3d4_step2.png",
      "clicked_selector": ".sidebar-nav >> text=技能管理",
      "duration_ms": 750
    },
    {
      "index": 3,
      "action": "screenshot",
      "label": "技能管理页面",
      "success": true,
      "screenshot_path": "/home/administrator/.hermes/dial_shots/dial_flow_a1b2c3d4_step3.png",
      "duration_ms": 400
    }
  ],
  "flow_id": "dial_flow_a1b2c3d4"
}
```

**失败步骤示例**：

```json
{
  "index": 1,
  "action": "click",
  "text": "不存在的按钮",
  "success": false,
  "error": "找不到文本为'不存在的按钮'的可点击元素",
  "duration_ms": 5200
}
```

---

## 5. 工具描述（给 LLM 看的）

LLM 通过 function calling 看到的工具描述，必须清晰说明使用场景和反例：

> **dial_flow** — 多步交互式浏览器拨测。在同一个浏览器会话中按顺序执行点击、导航、截图等动作，每步自动截图。用于需要多步操作才能到达的目标页面（如「点击系统工具→点击技能管理→截图」）。
>
> **何时用 dial_flow 而非 dial_test**：
> - ✅ 需要点击、导航才能到达的页面 → dial_flow
> - ✅ 需要分步骤截图的操作流程 → dial_flow
> - ❌ 只看当前页面状态（不交互） → dial_test
> - ❌ 只查某个元素的 CSS 样式 → dial_style
>
> **关键提醒**：不要反复调 dial_test 来"等页面变化"——dial_test 每次开新浏览器，永远是初始状态。多步交互必须用 dial_flow。

---

## 6. 完整调用示例

### 6.1 用户场景：验证「技能管理」页面

LLM 调用：

```python
dial_flow(
    url="http://localhost:5173",
    actions=[
        {"action": "goto", "url": "http://localhost:5173"},
        {"action": "click", "text": "系统工具"},
        {"action": "wait", "ms": 500},
        {"action": "click", "text": "技能管理"},
        {"action": "wait", "ms": 1000},
        {"action": "screenshot", "label": "技能管理页面"},
    ]
)
```

### 6.2 用户场景：验证设置面板路由配置

```python
dial_flow(
    url="http://localhost:5173",
    actions=[
        {"action": "goto", "url": "http://localhost:5173"},
        {"action": "click", "selector": ".topbar-btn[title='系统设置']"},
        {"action": "wait", "ms": 1000},
        {"action": "screenshot", "label": "设置页面"},
        {"action": "click", "text": "路由配置"},
        {"action": "wait", "ms": 500},
        {"action": "screenshot", "label": "路由配置Tab"},
        {"action": "snapshot", "selector": ".sv-routing-table"},
    ]
)
```

### 6.3 简单场景：只截图不交互

LLM 也可以传空 actions 数组（等效于 `dial_test`，但保留在一个 browser session 内）：

```python
dial_flow(
    url="http://localhost:5173/settings",
    actions=[
        {"action": "screenshot", "label": "设置页"},
    ]
)
```

---

## 7. 实现要点

### 7.1 线程模型：沿用 `_run_in_thread` 模式

一次 `dial_flow` 调用 = 一个线程 + 一个 event loop + 一个浏览器实例。所有 action 在这个实例内顺序执行。执行完毕销毁。

```python
async def _dial_flow_coro(url, actions, viewport, screenshot, stop_on_error):
    pw, browser = await _create_browser_async()
    w, h = _parse_viewport(viewport)
    page = await browser.new_page(viewport={"width": w, "height": h})
    
    steps = []
    flow_id = f"dial_flow_{uuid.uuid4().hex[:8]}"
    
    try:
        for i, action in enumerate(actions):
            step_start = time.time()
            step = {"index": i, "action": action.get("action", "unknown")}
            
            try:
                if action["action"] == "goto":
                    await page.goto(action["url"], wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1500)
                    step["url_after"] = page.url
                    step["title_after"] = await page.title()
                
                elif action["action"] == "click":
                    locator = _build_locator(page, action)
                    await locator.click(timeout=5000)
                    await page.wait_for_timeout(300)
                    step["clicked_selector"] = _describe_locator(action)
                
                elif action["action"] == "wait":
                    await _do_wait(page, action)
                
                elif action["action"] == "snapshot":
                    sel = action.get("selector", "body")
                    dom = await _extract_dom_snapshot(page, root=sel)
                    step["dom"] = dom
                
                elif action["action"] == "screenshot":
                    # handled below
                    pass
                
                # Auto-screenshot if applicable
                should_screenshot = action.get("screenshot", _auto_screenshot(action["action"]))
                if should_screenshot and screenshot:
                    shot_path = _save_screenshot(page, flow_id, i, action.get("label", ""))
                    step["screenshot_path"] = shot_path
                
                step["success"] = True
            
            except Exception as e:
                step["success"] = False
                step["error"] = str(e)[:200]
                if stop_on_error:
                    steps.append(step)
                    break
            
            step["duration_ms"] = int((time.time() - step_start) * 1000)
            steps.append(step)
        
        return {"flow_id": flow_id, "steps": steps, "success": all(s["success"] for s in steps), ...}
    
    finally:
        await page.close()
        await browser.close()
        await pw.stop()
```

### 7.2 Locator 构建逻辑

```python
def _build_locator(page, action):
    """根据 action 参数构建 Playwright locator"""
    text = action.get("text", "")
    selector = action.get("selector", "")
    force = action.get("force", False)
    
    if selector and text:
        return page.locator(selector).filter(has_text=text)
    elif selector:
        return page.locator(selector)
    elif text:
        return page.get_by_text(text)
    else:
        raise ValueError("click action 缺少 text 或 selector")

def _auto_screenshot(action_type):
    """判断是否自动截图"""
    return action_type in ("goto", "click")
```

### 7.3 截图命名规则

```
~/.hermes/dial_shots/dial_flow_{flow_id}_step{index}_{label}.png
```

例：`dial_flow_a1b2c3d4_step0_home.png`、`dial_flow_a1b2c3d4_step2_技能管理.png`

### 7.4 错误处理策略

| 场景 | 行为 |
|------|------|
| goto 超时/不可达 | 标记失败，默认继续（stop_on_error=false 时） |
| click 找不到元素 | 5 秒超时，标记失败，记录查找的 text/selector |
| wait 超时 | 超时后继续（不标记失败），记录实际等待时长 |
| screenshot 失败 | 标记失败，记录错误原因（磁盘满/权限等） |
| Playwright 崩溃 | 整个 flow 终止，返回已完成步骤 + 致命错误 |

---

## 8. registry.json 注册

```json
{
  "name": "dial_flow",
  "description": "多步交互式浏览器拨测。在同一浏览器会话中按顺序执行一系列动作（导航、点击、等待、截图、DOM快照），每步自动截图。用于需要点击/导航才能到达的目标页面验证，不要用反复调dial_test来「等页面变化」——dial_test每次开新浏览器永远是初始状态。",
  "file": "tools/browser_dial_test.py",
  "function": "dial_flow",
  "parameters": {
    "url": {
      "type": "string",
      "description": "起始页面URL（如 http://localhost:5173）"
    },
    "actions": {
      "type": "array",
      "items": {"type": "object"},
      "description": "动作序列。每个动作含 action 字段（goto/click/wait/screenshot/snapshot）。goto需url，click需text或selector，wait需ms/selector/text之一，screenshot需label。"
    },
    "viewport": {
      "type": "string",
      "description": "视口尺寸 宽x高，默认 1440x900",
      "optional": true
    },
    "screenshot": {
      "type": "boolean",
      "description": "全局截图开关，默认true。false时不自动截图。",
      "optional": true
    },
    "stop_on_error": {
      "type": "boolean",
      "description": "默认false。true时第一步失败即停止后续步骤。",
      "optional": true
    }
  },
  "returns": "JSON报告 {flow_id, steps[{action,success,screenshot_path,error}], success, duration_ms}",
  "category": "browser",
  "verified": false
}
```

---

## 9. 与现有工具的协作关系

```
                    ┌─────────────────────────────────────┐
                    │        browser_dial_test.py          │
                    │                                      │
                    │  dial_test   — 单页全貌快照          │
                    │  dial_style  — 单页指定元素样式      │
                    │  dial_assert — 单页断言检查          │
                    │  dial_flow   — 多步交互式流程 🆕     │
                    └─────────────────────────────────────┘
```

| 场景 | 推荐工具 |
|------|---------|
| 打开页面看一眼 DOM/Console/截图 | `dial_test` |
| 查某个按钮的 font-size 对不对 | `dial_style` |
| 验证「至少有 3 张卡片」「无 JS 报错」 | `dial_assert` |
| 验证「点击系统工具 → 展开 → 点击技能管理 → 进入页面」的完整流程 | **`dial_flow`** |
| 需要点 3 个不同 Tab 分别截图 | **`dial_flow`** |
| 表单填写 + 提交 + 验证结果页 | **`dial_flow`** |

---

## 10. 后续扩展空间

| 扩展 | 说明 | 优先级 |
|------|------|--------|
| `input` action | 填写输入框（`{"action":"input","selector":"...","value":"xxx"}`） | 🟡 中 |
| `hover` action | 悬停触发 tooltip/dropdown | 🟢 低 |
| `scroll` action | 滚动到指定位置 | 🟢 低 |
| `assert` action | 流程内断言（不通过则终止） | 🟡 中 |
| `extract` action | 提取页面数据（表格/列表 → JSON） | 🟡 中 |

当前 v1.0 的 `goto + click + wait + screenshot + snapshot` 已覆盖 90% 的多步拨测场景。

---

## 11. LLM 使用指引（内嵌 tool description）

为避免 LLM 再次陷入「反复调 dial_test 等页面变化」的陷阱，`dial_flow` 的 tool description 需包含以下关键句：

> ⚠️ 重要：不要用反复调用 dial_test 来「等待页面变化」——dial_test 每次打开全新浏览器，永远是初始状态。任何需要点击、导航、展开才能看到的内容，必须用 dial_flow 的一次性动作序列来完成。一次 dial_flow 调用 = 一个浏览器会话内的完整操作流程。

同时 `dial_test` 的 description 也应加一句：

> ⚠️ 这是单页快照工具，每次调用打开全新浏览器。如果需要点击、导航等交互操作，请使用 dial_flow。
