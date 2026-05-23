"""Browser Dial Test — 浏览器拨测工具

让 Agent 能像人一样「打开浏览器看页面」——但不是看图，是读结构化的
DOM 位置、CSS 计算值、Console 日志、Network 瀑布。

三个工具接口：
  - dial_test(url): 完整拨测，返回 DOM 快照 + Console + Network + 性能
  - dial_style(url, selectors): 提取特定元素的计算样式
  - dial_assert(url, rules): 断言式检查

依赖: pip install playwright && playwright install chromium
"""

import json
import os
import time
import uuid

# ── 全局浏览器实例（复用，不每次启动） ──

_browser = None
_PLAYWRIGHT_AVAILABLE = False


def _ensure_browser():
    """获取/创建全局 Chromium 浏览器实例"""
    global _browser, _PLAYWRIGHT_AVAILABLE
    if _browser is not None:
        return _browser
    try:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
        _PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        _PLAYWRIGHT_AVAILABLE = False
        raise RuntimeError("Playwright 未安装: pip install playwright && playwright install chromium")
    except Exception as e:
        _PLAYWRIGHT_AVAILABLE = False
        raise RuntimeError(f"浏览器启动失败: {e}")
    return _browser


def _parse_viewport(viewport_str: str) -> tuple:
    """解析视口字符串 '1440x900' → (1440, 900)"""
    try:
        parts = viewport_str.lower().split("x")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 1440, 900


def _extract_dom_snapshot(page, root=None, max_depth=3, depth=0):
    """递归提取 DOM 元素快照（rect/computedStyle/scroll）"""
    if depth > max_depth:
        return []

    import json as _json

    # 使用 page.evaluate 在浏览器上下文中执行
    script = """
    (selector) => {
        const root = selector ? document.querySelector(selector) : document.body;
        if (!root) return [];

        function extract(el, d, maxD) {
            if (d > maxD) return [];

            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            const tag = el.tagName ? el.tagName.toLowerCase() : '?';
            const isVisible = rect.width > 0 && rect.height > 0;

            // 构建唯一选择器
            let sel = tag;
            if (el.id) sel = '#' + el.id;
            else if (el.className && typeof el.className === 'string') {
                const cls = el.className.trim().split(/\\s+/).filter(c => c && !c.startsWith('_')).slice(0, 2).join('.');
                if (cls) sel = tag + '.' + cls;
            }

            const result = {
                selector: sel,
                tag: tag,
                rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                computed_style: {
                    display: style.display,
                    overflow: style.overflow,
                    overflowX: style.overflowX,
                    overflowY: style.overflowY,
                    position: style.position,
                    fontSize: style.fontSize,
                    color: style.color,
                    background: style.background,
                    opacity: style.opacity,
                    visibility: style.visibility,
                },
                visible: isVisible,
                children: [],
                text_content: (el.textContent || '').trim().substring(0, 200) || null,
            };

            // 容器元素的滚动信息
            if (el.scrollHeight !== el.clientHeight || el.scrollWidth !== el.clientWidth) {
                result.scroll = {
                    height: el.scrollHeight,
                    client_height: el.clientHeight,
                    width: el.scrollWidth,
                    client_width: el.clientWidth,
                };
            }

            // 子元素（只处理有意义的孩子，跳过文本节点和空节点）
            const children = [];
            for (const child of el.children) {
                if (d + 1 <= maxD) {
                    const sub = extract(child, d + 1, maxD);
                    if (sub) children.push(sub);
                }
            }
            if (children.length > 0) result.children = children;

            return result;
        }

        const r = extract(root, 0, """ + str(max_depth) + """);\x20
        return Array.isArray(r) ? r : [r];
    }
    """

    try:
        result = page.evaluate(script)
        return result if isinstance(result, list) else [result]
    except Exception:
        return []


def _collect_console_logs(page):
    """从页面收集控制台日志"""
    logs = []
    try:
        console_errors = page.evaluate("""() => {
            return window.__zuoshanke_console_errors || [];
        }""")
        if isinstance(console_errors, list):
            logs = console_errors
    except Exception:
        pass
    return logs


def _collect_network_logs(page):
    """从页面收集网络请求信息"""
    try:
        entries = page.evaluate("""() => {
            if (!window.performance || !window.performance.getEntries) return [];
            return window.performance.getEntries().map(e => ({
                url: (e.name || '').substring(0, 200),
                type: e.initiatorType || 'other',
                duration_ms: Math.round(e.duration || 0),
                size: Math.round(e.transferSize || e.encodedBodySize || 0),
            }));
        }""")
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


# ═══ 三个工具接口 ═══


def dial_test(url: str, viewport: str = "1440x900", screenshot: bool = True) -> str:
    """完整拨测：打开页面，返回 DOM 快照 + Console + Network + 性能

    Args:
        url: 页面 URL（如 http://localhost:5173/scenes）
        viewport: 视口尺寸 "宽x高"，默认 1440x900
        screenshot: 是否保存截图（路径在报告中返回）

    Returns:
        JSON 字符串 DialTestReport
    """
    start = time.time()
    browser = _ensure_browser()
    w, h = _parse_viewport(viewport)

    page = browser.new_page(viewport={"width": w, "height": h})
    try:
        # 安装 console 监听（必须在导航前注册）
        console_entries = []
        page.on("console", lambda msg: console_entries.append({
            "level": msg.type,
            "text": msg.text,
        }))
        page.on("pageerror", lambda err: console_entries.append({
            "level": "error",
            "text": f"JS异常: {err}",
        }))

        # 导航
        try:
            page.goto(url, wait_until="networkidle", timeout=15000)
        except Exception as nav_err:
            return json.dumps({
                "url": url, "viewport": viewport,
                "error": f"页面加载失败: {nav_err}",
                "duration_ms": int((time.time() - start) * 1000),
            }, ensure_ascii=False)

        # DOM 快照
        dom = _extract_dom_snapshot(page)

        # Console 日志（从 page.on 监听收集）
        console_logs = console_entries

        # Network
        network = _collect_network_logs(page)

        # 性能指标
        perf = {}
        try:
            perf = page.evaluate("""() => {
                const entries = performance.getEntriesByType('paint');
                const fcp = entries.find(e => e.name === 'first-contentful-paint');
                return {
                    fcp_ms: fcp ? Math.round(fcp.startTime) : 0,
                };
            }""") or {}
        except Exception:
            pass

        # 截图
        screenshot_path = None
        if screenshot:
            os.makedirs("/tmp/screenshots", exist_ok=True)
            screenshot_path = f"/tmp/screenshots/dial_{uuid.uuid4().hex[:12]}.png"
            try:
                page.screenshot(path=screenshot_path, full_page=True)
            except Exception:
                screenshot_path = None

        # 生成 summary
        errors = [e for e in console_logs if isinstance(e, dict) and e.get("level") == "error"]
        warns = [e for e in console_logs if isinstance(e, dict) and e.get("level") == "warning"]
        overflowed = 0
        for el in dom:
            if el.get("scroll") and el["scroll"].get("height", 0) > el["scroll"].get("client_height", 0):
                overflowed += 1

        summary_parts = []
        if errors:
            summary_parts.append(f"{len(errors)} 个控制台错误")
        if warns:
            summary_parts.append(f"{len(warns)} 个控制台警告")
        if overflowed:
            summary_parts.append(f"{overflowed} 个容器内容溢出")
        if not summary_parts:
            summary_parts.append("页面加载正常")

        report = {
            "url": url,
            "viewport": viewport,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": int((time.time() - start) * 1000),
            "screenshot": screenshot_path,
            "dom": dom,
            "console": console_logs,
            "network": network,
            "performance": perf,
            "summary": " | ".join(summary_parts),
        }

        return json.dumps(report, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "url": url, "viewport": viewport,
            "error": f"拨测异常: {e}",
            "duration_ms": int((time.time() - start) * 1000),
        }, ensure_ascii=False)
    finally:
        page.close()


def dial_style(url: str, selectors: list[str], viewport: str = "1440x900") -> str:
    """只提取特定元素的计算样式。比 dial_test 更快。

    Args:
        url: 页面 URL
        selectors: CSS 选择器列表，如 [".card-grid", ".sidebar > nav"]
        viewport: 视口尺寸

    Returns:
        JSON 字符串 DialStyleReport
    """
    start = time.time()
    browser = _ensure_browser()
    w, h = _parse_viewport(viewport)

    page = browser.new_page(viewport={"width": w, "height": h})
    try:
        page.goto(url, wait_until="networkidle", timeout=15000)

        elements = []
        for sel in selectors:
            try:
                el_info = page.evaluate(f"""() => {{
                    const el = document.querySelector({json.dumps(sel)});
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return {{
                        selector: {json.dumps(sel)},
                        visible: rect.width > 0 && rect.height > 0,
                        rect: {{x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}},
                        style: {{
                            display: style.display,
                            overflow: style.overflow,
                            overflowX: style.overflowX,
                            overflowY: style.overflowY,
                            position: style.position,
                            fontSize: style.fontSize,
                            color: style.color,
                            background: style.background,
                            opacity: style.opacity,
                        }},
                        text: (el.textContent || '').trim().substring(0, 200),
                    }};
                }}""")
                if el_info:
                    elements.append(el_info)
            except Exception:
                elements.append({"selector": sel, "error": "查询失败"})

        return json.dumps({
            "url": url,
            "elements": elements,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": int((time.time() - start) * 1000),
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "url": url, "error": f"拨测异常: {e}",
            "duration_ms": int((time.time() - start) * 1000),
        }, ensure_ascii=False)
    finally:
        page.close()


def dial_assert(url: str, rules: list[dict], viewport: str = "1440x900") -> str:
    """断言式检查：验证页面元素 CSS、数量、控制台状态。

    Args:
        url: 页面 URL
        rules: 断言规则列表
        viewport: 视口尺寸

    规则格式:
        {"name": "描述", "type": "style", "selector": ".card", "style_rules": [{"property": "overflow", "operator": "==", "value": "hidden auto"}]}
        {"name": "描述", "type": "count", "count_selector": ".card", "count_rule": {"operator": "gte", "value": 3}}
        {"name": "描述", "type": "console", "console_errors": 0}

    Returns:
        JSON 字符串 [DialAssertResult, ...]
    """
    start = time.time()
    browser = _ensure_browser()
    w, h = _parse_viewport(viewport)

    page = browser.new_page(viewport={"width": w, "height": h})
    try:
        page.goto(url, wait_until="networkidle", timeout=15000)

        # 安装 console 收集
        console_entries = []
        page.on("console", lambda msg: console_entries.append({
            "level": msg.type,
            "text": msg.text,
        }))

        # 等一帧让 console 事件收集
        page.wait_for_timeout(500)

        results = []
        for rule in rules:
            rtype = rule.get("type", "")
            name = rule.get("name", "")

            if rtype == "style":
                sel = rule.get("selector", "")
                style_rules = rule.get("style_rules", [])
                try:
                    computed = page.evaluate(f"""() => {{
                        const el = document.querySelector({json.dumps(sel)});
                        if (!el) return null;
                        const style = window.getComputedStyle(el);
                        return {val: style[{json.dumps(style_rules[0]["property"])}] if {json.dumps(style_rules)} else ""};
                    }}""".replace("\\n\\", " "))
                    # 简化处理：逐个检查属性
                    all_pass = True
                    for sr in style_rules:
                        prop = sr["property"]
                        expected = sr["value"]
                        op = sr.get("operator", "==")
                        actual = page.evaluate(f"""() => {{
                            const el = document.querySelector({json.dumps(sel)});
                            if (!el) return null;
                            return window.getComputedStyle(el).getPropertyValue({json.dumps(prop)});
                        }}""")
                        if actual is None:
                            results.append({"name": name, "passed": False, "error": f"元素 {sel} 未找到"})
                            all_pass = False
                            break
                        actual_str = str(actual).strip()
                        if op == "==" and actual_str != expected:
                            results.append({"name": name, "passed": False, "expected": expected, "actual": actual_str})
                            all_pass = False
                        elif op == "contains" and expected not in actual_str:
                            results.append({"name": name, "passed": False, "expected": f"包含 {expected}", "actual": actual_str})
                            all_pass = False
                        elif op == "!=" and actual_str == expected:
                            results.append({"name": name, "passed": False, "expected": f"不等于 {expected}", "actual": actual_str})
                            all_pass = False
                    if all_pass:
                        results.append({"name": name, "passed": True})
                except Exception as e:
                    results.append({"name": name, "passed": False, "error": str(e)})

            elif rtype == "count":
                count_sel = rule.get("count_selector", "")
                count_rule = rule.get("count_rule", {})
                op = count_rule.get("operator", "eq")
                expected_count = count_rule.get("value", 0)
                try:
                    actual_count = page.evaluate(f"""() => {{
                        return document.querySelectorAll({json.dumps(count_sel)}).length;
                    }}""")
                    passed = False
                    if op == "eq" and actual_count == expected_count: passed = True
                    elif op == "gte" and actual_count >= expected_count: passed = True
                    elif op == "lte" and actual_count <= expected_count: passed = True
                    elif op == "gt" and actual_count > expected_count: passed = True
                    elif op == "lt" and actual_count < expected_count: passed = True
                    results.append({
                        "name": name, "passed": passed,
                        "expected": f"{op} {expected_count}",
                        "actual": actual_count,
                    })
                except Exception as e:
                    results.append({"name": name, "passed": False, "error": str(e)})

            elif rtype == "console":
                max_errors = rule.get("console_errors", 0)
                actual_errors = [c for c in console_entries if c["level"] == "error"]
                passed = len(actual_errors) <= max_errors
                results.append({
                    "name": name, "passed": passed,
                    "expected": f"控制台错误 <= {max_errors}",
                    "actual": len(actual_errors),
                })

            else:
                results.append({"name": name, "passed": False, "error": f"未知断言类型: {rtype}"})

        return json.dumps(results, ensure_ascii=False)

    except Exception as e:
        return json.dumps([{"name": "_global_", "passed": False, "error": f"断言执行异常: {e}"}],
                          ensure_ascii=False)
    finally:
        page.close()
