"""Browser Dial Test — 浏览器拨测工具

让 Agent 能像人一样「打开浏览器看页面」——但不是看图，是读结构化的
DOM 位置、CSS 计算值、Console 日志、Network 瀑布。

四个工具接口：
  - dial_test(url): 完整拨测，返回 DOM 快照 + Console + Network + 性能
  - dial_style(url, selectors): 提取特定元素的计算样式
  - dial_assert(url, rules): 断言式检查
  - dial_flow(url, actions): 多步交互式流程，同一浏览器会话内执行动作序列

依赖: pip install playwright && playwright install chromium

线程模型：每次调用在新线程 + 新事件循环中执行，不共享 Playwright 实例。
简单可靠，避免了「cannot switch to a different thread」问题。
"""

import asyncio
import json
import os
import threading
import time
import uuid

from playwright.async_api import async_playwright

_HEADLESS_SHELL_PATH = os.path.expanduser(
    "~/.cache/ms-playwright/chromium_headless_shell-1223"
    "/chrome-headless-shell-linux64/chrome-headless-shell"
)


def _parse_viewport(viewport_str: str) -> tuple:
    """解析视口字符串 '1440x900' → (1440, 900)"""
    try:
        parts = viewport_str.lower().split("x")
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        raise ValueError(f"无效视口格式: {viewport_str}")


async def _create_browser_async():
    """创建 Playwright + 浏览器实例"""
    pw = await async_playwright().start()
    try:
        if os.path.exists(_HEADLESS_SHELL_PATH):
            browser = await pw.chromium.launch(
                headless=True,
                executable_path=_HEADLESS_SHELL_PATH,
                args=["--no-sandbox"],
            )
        else:
            browser = await pw.chromium.launch(headless=True)
        return pw, browser
    except ImportError:
        await pw.stop()
        raise RuntimeError("Playwright 未安装: pip install playwright && playwright install chromium")
    except Exception as e:
        await pw.stop()
        raise RuntimeError(f"浏览器启动失败: {e}")


async def _extract_dom_snapshot(page, root=None, max_depth=3, depth=0):
    """提取DOM快照（异步辅助函数）"""
    elements = []
    selector = root or "html"
    try:
        containers = await page.query_selector_all(selector)
    except Exception:
        return elements

    for el in containers:
        if depth >= max_depth:
            break
        try:
            tag = await el.evaluate("el => el.tagName ? el.tagName.toLowerCase() : 'unknown'")
            if tag in ("script", "style", "noscript", "link"):
                continue

            rect = await el.evaluate("""el => {
                const r = el.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)};
            }""")
            text = await el.evaluate("""el => {
                const t = (el.innerText || el.textContent || '').trim();
                return t.length > 120 ? t.slice(0, 120) + '...' : t;
            }""")
            visible = await el.is_visible()
            attrs = await el.evaluate("""el => {
                const a = {};
                for (const attr of ['id', 'class', 'href', 'src', 'alt', 'type', 'placeholder', 'aria-label', 'data-testid']) {
                    const v = el.getAttribute(attr);
                    if (v) a[attr] = v;
                }
                return a;
            }""")

            item = {
                "tag": tag,
                "text": text[:80] if text else "",
                "rect": rect,
                "visible": visible,
            }
            if attrs:
                item["attrs"] = attrs

            children = await _extract_dom_snapshot(page, root=selector, max_depth=max_depth, depth=depth + 1)
            if children:
                item["children"] = children[:10]

            elements.append(item)
        except Exception:
            continue

        if len(elements) >= 50:
            break

    return elements


async def _collect_network_logs(page):
    try:
        return await page.evaluate("""() => {
            const entries = performance.getEntriesByType('resource');
            return entries.slice(0, 20).map(e => ({
                url: e.name.slice(0, 80),
                type: e.initiatorType || 'other',
                duration_ms: Math.round(e.duration),
                size_bytes: e.transferSize || 0,
            }));
        }""")
    except Exception:
        return []


async def _dial_test_coro(url: str, viewport: str = "1440x900", screenshot: bool = True) -> str:
    """完整拨测实现（在独立线程的 event loop 中执行）"""
    start = time.time()
    pw, browser = await _create_browser_async()
    w, h = _parse_viewport(viewport)

    page = await browser.new_page(viewport={"width": w, "height": h})
    try:
        console_entries = []
        page.on("console", lambda msg: console_entries.append({
            "level": msg.type,
            "text": msg.text,
        }))
        page.on("pageerror", lambda err: console_entries.append({
            "level": "error",
            "text": f"JS异常: {err}",
        }))

        # Track HTTP status and redirects
        response_info = {"status": None, "url_final": url, "redirected": False}
        async def _on_response(resp):
            if resp.url == url or resp.url == response_info["url_final"]:
                response_info["status"] = resp.status
        async def _on_request(req):
            if req.is_navigation_request() and req.url != url:
                response_info["url_final"] = req.url
                response_info["redirected"] = True
        page.on("response", _on_response)
        page.on("request", _on_request)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            # 额外等 JS 渲染（前端 websocket 会阻止 networkidle）
            try:
                await page.wait_for_timeout(2000)
            except Exception:
                pass
        except Exception as nav_err:
            return json.dumps({
                "url": url, "viewport": viewport,
                "error": f"页面加载失败: {nav_err}",
                "duration_ms": int((time.time() - start) * 1000),
                "_instruction": (
                    "⚠️ 拨测失败。请如实告知用户：浏览器无法加载此页面。"
                    "不要编造任何 DOM 结构、CSS 样式、Console 输出或截图路径。"
                    "你唯一能做的就是告知失败原因，并建议用户检查 URL 是否正确、服务是否运行。"
                ),
            }, ensure_ascii=False)

        dom = _extract_dom_snapshot(page)
        console_logs = console_entries
        network = _collect_network_logs(page)

        # ── 内容完整性检测 ──
        warnings = []
        page_title = await page.title()
        final_url = page.url
        http_status = response_info["status"]

        # 检测1: HTTP 非 2xx
        if http_status and (http_status < 200 or http_status >= 300):
            warnings.append(f"HTTP {http_status} — 页面返回非正常状态码，内容可能为错误页")

        # 检测2: 被重定向到不同域名
        from urllib.parse import urlparse
        if response_info["redirected"] and urlparse(final_url).netloc != urlparse(url).netloc:
            warnings.append(f"页面被重定向到: {final_url}")

        # 检测3: 标题包含登录/错误关键词
        lower_title = page_title.lower()
        auth_keywords = ["login", "sign in", "登录", "验证", "captcha", "403", "404", "500", "error", "blocked", "denied"]
        matched_auth = [kw for kw in auth_keywords if kw in lower_title]
        if matched_auth:
            warnings.append(f"页面标题包含: {', '.join(matched_auth)} — 可能遇到登录验证或拦截页")

        # 检测4: DOM 内容极少（< 10 个元素）
        dom_resolved = await dom if asyncio.iscoroutine(dom) else dom
        if isinstance(dom_resolved, dict):
            total_elements = dom_resolved.get("total_elements", 0)
            body_text = dom_resolved.get("body", "")
            if total_elements < 10:
                warnings.append(f"DOM 仅含 {total_elements} 个元素 — 页面内容异常稀少，可能未完成渲染或被拦截")
            # 检测5: body 文本包含登录特征
            login_texts = ["用户名", "密码", "password", "username", "验证码", "sign in", "log in"]
            body_lower = body_text.lower() if isinstance(body_text, str) else ""
            matched_login = [t for t in login_texts if t in body_lower]
            if matched_login:
                warnings.append(f"页面内容包含登录相关文本: {', '.join(matched_login)}")

        # ── 构建 _instruction ──
        if warnings:
            instruction = (
                "⚠️ 页面虽然返回了 HTTP 200，但内容可能不是用户期望的目标页面。"
                "原因可能是：网站需要登录验证、被拦截、或 SPA 未完成渲染。\n"
                "请如实告知用户你看到了什么（以及更重要的是——没看到什么），"
                "不要假设页面内容是正常的。如果没有获取到用户想要的信息，直接说出来。\n"
                "检测到的异常：" + "; ".join(warnings)
            )
        else:
            instruction = "✅ 拨测成功。以下数据可直接用于回复。"

        perf = {}
        try:
            perf = await page.evaluate("""() => {
                const entries = performance.getEntriesByType('paint');
                const fcp = entries.find(e => e.name === 'first-contentful-paint');
                return { fcp_ms: fcp ? Math.round(fcp.startTime) : 0 };
            }""")
        except Exception:
            perf = {"fcp_ms": 0}

        screenshot_path = None
        if screenshot:
            try:
                shots_dir = os.path.expanduser("~/.zuoshanke/dial_shots")
                os.makedirs(shots_dir, exist_ok=True)
                shot_name = f"dial_{uuid.uuid4().hex[:8]}.png"
                screenshot_path = os.path.join(shots_dir, shot_name)
                await page.screenshot(path=screenshot_path, full_page=False)
            except Exception as e:
                screenshot_path = f"截图失败: {e}"

        duration_ms = int((time.time() - start) * 1000)
        report = {
            "url": url,
            "final_url": final_url,
            "http_status": http_status,
            "viewport": viewport,
            "title": page_title,
            "duration_ms": duration_ms,
            "dom_snapshot": dom_resolved,
            "console_logs": console_logs,
            "network": await network if asyncio.iscoroutine(network) else network,
            "performance": perf,
            "screenshot_path": screenshot_path,
            "_instruction": instruction,
        }
        if warnings:
            report["_warnings"] = warnings
        return json.dumps(report, ensure_ascii=False, default=str)
    finally:
        await page.close()
        await browser.close()
        await pw.stop()


async def _dial_style_coro(url: str, selectors: list[str], viewport: str = "1440x900") -> str:
    """样式提取实现"""
    start = time.time()
    pw, browser = await _create_browser_async()
    w, h = _parse_viewport(viewport)
    page = await browser.new_page(viewport={"width": w, "height": h})
    try:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as nav_err:
            return json.dumps({
                "error": f"页面加载失败: {nav_err}",
                "duration_ms": int((time.time() - start) * 1000),
                "_instruction": "⚠️ 拨测失败，无法获取样式。请如实告知用户，不要编造任何 CSS 数值。",
            }, ensure_ascii=False)

        results = {}
        for sel in selectors:
            try:
                els = await page.query_selector_all(sel)
                if not els:
                    results[sel] = [{"error": f"选择器 '{sel}' 未匹配到任何元素"}]
                    continue
                styles = []
                for el in els[:5]:
                    try:
                        style = await el.evaluate("""el => {
                            const cs = window.getComputedStyle(el);
                            return {
                                display: cs.display, position: cs.position,
                                visibility: cs.visibility, opacity: cs.opacity,
                                width: cs.width, height: cs.height,
                                color: cs.color, backgroundColor: cs.backgroundColor,
                                fontSize: cs.fontSize, fontWeight: cs.fontWeight,
                                zIndex: cs.zIndex, borderRadius: cs.borderRadius,
                            };
                        }""")
                        styles.append(style)
                    except Exception:
                        styles.append({"error": "样式提取失败"})
                results[sel] = styles
            except Exception as e:
                results[sel] = [{"error": str(e)}]

        # 检测结果是否全部为空
        all_empty = all(
            not v or all(isinstance(s, dict) and "error" in s for s in v)
            for v in results.values()
        )
        instruction = (
            "❌ 所有选择器均未匹配到元素。请如实告知用户：页面上没有找到指定的元素。"
            "不要编造任何 font-size、color 等 CSS 数值。"
        ) if all_empty else ""

        duration_ms = int((time.time() - start) * 1000)
        report = {
            "url": url, "selectors": selectors,
            "duration_ms": duration_ms, "styles": results,
        }
        if instruction:
            report["_instruction"] = instruction
        return json.dumps(report, ensure_ascii=False, default=str)
    finally:
        await page.close()
        await browser.close()
        await pw.stop()


async def _dial_assert_coro(url: str, rules: list[dict], viewport: str = "1440x900") -> str:
    """断言实现"""
    start = time.time()
    pw, browser = await _create_browser_async()
    w, h = _parse_viewport(viewport)
    page = await browser.new_page(viewport={"width": w, "height": h})
    try:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as nav_err:
            return json.dumps({
                "error": f"页面加载失败: {nav_err}",
                "duration_ms": int((time.time() - start) * 1000),
                "_instruction": "⚠️ 拨测失败，无法执行断言。请如实告知用户，不要编造任何断言结果。",
            }, ensure_ascii=False)

        report = []
        for rule in rules:
            selector = rule.get("selector", "")
            check = rule.get("check", "exists")
            expected = rule.get("expected")
            result = {"selector": selector, "check": check, "passed": False, "detail": ""}

            try:
                el = await page.query_selector(selector)
                if check == "exists":
                    result["passed"] = el is not None
                    result["detail"] = "存在" if el else "不存在"
                elif el is None:
                    result["detail"] = "元素不存在"
                elif check == "text":
                    text = await el.inner_text()
                    result["passed"] = expected and expected in text
                    result["detail"] = f"文本: '{text[:80]}'" + (f" 含 '{expected}'" if result["passed"] else f" 不含 '{expected}'")
                elif check == "visible":
                    vis = await el.is_visible()
                    result["passed"] = (expected is None) or (vis == expected)
                    result["detail"] = f"可见: {vis}"
                elif check == "count":
                    els = await page.query_selector_all(selector)
                    count = len(els)
                    result["passed"] = expected is None or count == expected
                    result["detail"] = f"数量: {count}"
                else:
                    result["detail"] = f"未知检查: {check}"
            except Exception as e:
                result["detail"] = f"错误: {e}"

            report.append(result)

        duration_ms = int((time.time() - start) * 1000)
        return json.dumps({
            "url": url, "duration_ms": duration_ms,
            "results": report, "all_passed": all(r["passed"] for r in report),
        }, ensure_ascii=False, default=str)
    finally:
        await page.close()
        await browser.close()
        await pw.stop()


def _run_in_thread(coro_fn, *args, timeout: float = 30):
    """在新线程 + 新事件循环中执行协程，返回结果"""
    result_container = []
    error_container = []

    def _target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(coro_fn(*args))
            result_container.append(res)
        except Exception as e:
            error_container.append(e)
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if error_container:
        raise error_container[0]
    if result_container:
        return result_container[0]
    raise TimeoutError(f"拨测超时 ({timeout}s)")


# ── dial_flow 辅助函数 ──

def _build_locator(page, action: dict):
    """根据 action 参数构建 Playwright locator"""
    text = action.get("text", "")
    selector = action.get("selector", "")

    if selector and text:
        return page.locator(selector).filter(has_text=text)
    elif selector:
        return page.locator(selector)
    elif text:
        return page.get_by_text(text)
    else:
        raise ValueError("click action 缺少 text 或 selector")


async def _do_wait(page, action: dict):
    """执行等待动作"""
    ms = action.get("ms")
    selector = action.get("selector", "")
    text = action.get("text", "")
    timeout = action.get("timeout", 5000)

    if ms is not None:
        await page.wait_for_timeout(ms)
    elif selector:
        await page.wait_for_selector(selector, state="visible", timeout=timeout)
    elif text:
        await page.locator(f"text={text}").first.wait_for(state="visible", timeout=timeout)
    else:
        await page.wait_for_timeout(500)  # 无参数时默认等 500ms


def _auto_screenshot(action_type: str) -> bool:
    """goto 和 click 后自动截图"""
    return action_type in ("goto", "click")


async def _save_screenshot(page, flow_id: str, step_index: int, label: str) -> str:
    """保存截图，返回文件路径"""
    shots_dir = os.path.expanduser("~/.zuoshanke/dial_shots")
    os.makedirs(shots_dir, exist_ok=True)
    safe_label = label.replace(" ", "_")[:30] if label else f"step{step_index}"
    shot_name = f"{flow_id}_step{step_index}_{safe_label}.png"
    shot_path = os.path.join(shots_dir, shot_name)
    await page.screenshot(path=shot_path, full_page=False)
    return shot_path


# ── dial_flow 核心协程 ──

async def _dial_flow_coro(url: str, actions: list, viewport: str = "1440x900",
                          screenshot: bool = True, stop_on_error: bool = False) -> str:
    """多步交互式拨测实现（在独立线程的 event loop 中执行）"""
    start = time.time()
    pw, browser = await _create_browser_async()
    w, h = _parse_viewport(viewport)

    page = await browser.new_page(viewport={"width": w, "height": h})

    flow_id = f"dial_flow_{uuid.uuid4().hex[:8]}"
    steps = []

    try:
        # 第一步：导航到起始 URL
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
        except Exception as nav_err:
            return json.dumps({
                "flow_id": flow_id, "url": url, "viewport": viewport,
                "error": f"初始页面加载失败: {nav_err}",
                "duration_ms": int((time.time() - start) * 1000),
                "steps": [], "success": False,
            }, ensure_ascii=False)

        # 逐步执行动作序列
        for i, action in enumerate(actions):
            step_start = time.time()
            action_type = action.get("action", "unknown")
            step = {
                "index": i,
                "action": action_type,
                "label": action.get("label", ""),
                "success": False,
            }

            # 记录动作参数到 step
            for key in ("text", "selector", "url", "ms"):
                if key in action:
                    step[key] = action[key]

            try:
                if action_type == "goto":
                    target_url = action.get("url", "")
                    if not target_url:
                        raise ValueError("goto action 缺少 url")
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1500)
                    step["url_after"] = page.url
                    step["title_after"] = await page.title()

                elif action_type == "click":
                    locator = _build_locator(page, action)
                    force = action.get("force", False)
                    await locator.click(timeout=5000, force=force)
                    await page.wait_for_timeout(300)
                    step["url_after"] = page.url
                    # 记录实际使用的定位方式
                    if action.get("selector") and action.get("text"):
                        step["clicked_via"] = f"selector + text"
                    elif action.get("selector"):
                        step["clicked_via"] = "selector"
                    else:
                        step["clicked_via"] = "text"

                elif action_type == "wait":
                    await _do_wait(page, action)

                elif action_type == "snapshot":
                    sel = action.get("selector", "body")
                    dom = await _extract_dom_snapshot(page, root=sel)
                    step["dom"] = dom

                elif action_type == "screenshot":
                    pass  # 截图在下面统一处理

                else:
                    step["error"] = f"未知动作类型: {action_type}"
                    steps.append(step)
                    if stop_on_error:
                        break
                    continue

                # 自动截图判断
                should_shot = action.get("screenshot", None)
                if should_shot is None:
                    # screenshot 动作强制截图，goto/click 自动截图
                    should_shot = (action_type == "screenshot") or _auto_screenshot(action_type)
                if should_shot and screenshot and action_type != "snapshot":
                    step_label = action.get("label", "") or action_type
                    try:
                        step["screenshot_path"] = await _save_screenshot(page, flow_id, i, step_label)
                    except Exception as e:
                        step["screenshot_error"] = str(e)[:100]

                step["success"] = True

            except Exception as e:
                step["success"] = False
                step["error"] = str(e)[:200]
                if stop_on_error:
                    step["duration_ms"] = int((time.time() - step_start) * 1000)
                    steps.append(step)
                    break

            step["duration_ms"] = int((time.time() - step_start) * 1000)
            steps.append(step)

        duration_ms = int((time.time() - start) * 1000)
        return json.dumps({
            "flow_id": flow_id,
            "url": url,
            "viewport": viewport,
            "duration_ms": duration_ms,
            "total_steps": len(actions),
            "completed_steps": len(steps),
            "success": all(s.get("success", False) for s in steps) if steps else False,
            "steps": steps,
        }, ensure_ascii=False, default=str)

    finally:
        await page.close()
        await browser.close()
        await pw.stop()


# ── 四个公开接口 ──

def dial_test(url: str, viewport: str = "1440x900", screenshot: bool = True) -> str:
    """完整拨测：打开页面，返回 DOM 快照 + Console + Network + 性能

    Args:
        url: 页面 URL
        viewport: 视口尺寸 "宽x高"，默认 1440x900
        screenshot: 是否保存截图

    Returns:
        JSON 字符串 DialTestReport
    """
    return _run_in_thread(_dial_test_coro, url, viewport, screenshot)


def dial_style(url: str, selectors: list[str], viewport: str = "1440x900") -> str:
    """提取指定元素的计算样式"""
    return _run_in_thread(_dial_style_coro, url, selectors, viewport)


def dial_assert(url: str, rules: list[dict], viewport: str = "1440x900") -> str:
    """断言式检查：检查页面元素"""
    return _run_in_thread(_dial_assert_coro, url, rules, viewport)


def dial_flow(url: str, actions: list, viewport: str = "1440x900",
              screenshot: bool = True, stop_on_error: bool = False) -> str:
    """多步交互式拨测：在同一浏览器会话中顺序执行动作序列，每步自动截图

    用于需要点击、导航才能到达的目标页面验证。
    不要用反复调 dial_test 来「等页面变化」——dial_test 每次开新浏览器永远是初始状态。

    Args:
        url: 起始页面 URL
        actions: 动作序列，每个含 action 字段:
            goto      - {"action":"goto", "url":"..."}
            click     - {"action":"click", "text":"..."} 或 {"action":"click", "selector":"..."}
            wait      - {"action":"wait", "ms":500} 或 {"action":"wait", "selector":"..."}
            screenshot - {"action":"screenshot", "label":"..."}
            snapshot  - {"action":"snapshot", "selector":"..."}  取 DOM 结构
        viewport: 视口尺寸
        screenshot: 全局截图开关，默认 true
        stop_on_error: 默认 false，某步失败继续执行后续步骤

    Returns:
        JSON 字符串 {flow_id, steps[{action,success,screenshot_path,error}], success, duration_ms}
    """
    return _run_in_thread(_dial_flow_coro, url, actions, viewport, screenshot, stop_on_error)
