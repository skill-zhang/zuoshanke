# browser_dial_test 线程模型修复记录

## 问题

`browser_dial_test` 工具在 Hermes Agent / 坐山客 Agent Loop 中调用时，
报错 `cannot switch to a different thread (which happens to have exited)`。

## 根因分析

### 旧代码线程模型（引发问题的）

```python
def dial_test(url, viewport, screenshot):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有 running loop → 正常
        return asyncio.run(_dial_test_internal(...))

    # 有 running loop（如在 Agent Loop 异步上下文中）
    # → 开新线程 + 新 event loop
    result_container = []
    def _run_in_thread():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        res = new_loop.run_until_complete(_dial_test_internal(...))
        result_container.append(res)

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()
    thread.join(timeout=30)
```

问题关键：**全局 `_PW` 单例**（`async_playwright().start()` 结果）。

| 调用 | 线程 | 事件 | 问题 |
|------|------|------|------|
| 第1次 | 新线程A | `_PW = None` → 创建 Playwright | ✅ `_PW` 绑定线程A |
| 第2次 | 新线程B | `_PW is not None` → 复用 | ❌ Playwright 检测线程切换 → 抛错 |

Playwright 的 `_PW` 对象绑定创建它的线程/event loop，从其他线程访问即报错。

### 第一版修复（也失败的）

专用守护线程 + `run_coroutine_threadsafe`：

```python
def _get_playwright_loop():
    # 启动一个 daemon thread 跑 loop.run_forever()
    # 所有 Playwright 操作都调度到这个线程

def _run_on_pw_loop(coro, timeout=30):
    loop = _get_playwright_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)
```

**失败原因**：仅重启 FastAPI backend 不够。坐山客的进程链是：

```
Hermes Agent Gateway (PID 442)
  → 处理 WeChat 消息
  → 可能自己就有旧模块缓存
Zuoshanke Gateway (backend.gateway.run, PID 32216)
  → 轮询微信消息，转发到 backend API
  → 虽不直接 import 工具，但参与了消息链路
FastAPI Backend (uvicorn main:app, PID 43844)
  → 实际执行工具
```

必须**全链路重启**（backend + zuoshanke Gateway），否则旧进程的模块缓存仍在。

## 最终方案

**不共享任何 Playwright 状态。每次调用独立线程 + 独立 event loop + 全新 Playwright 实例。用完彻底销毁。**

```python
def _run_in_thread(coro_fn, *args, timeout=30):
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

    if error_container: raise error_container[0]
    if result_container: return result_container[0]
    raise TimeoutError(f"拨测超时 ({timeout}s)")
```

每次调用：
1. 创建新线程、新 event loop
2. 全新 `async_playwright().start()` + 全新 `browser`
3. 执行完 `pw.stop()` + `browser.close()` + `loop.close()` 彻底清理
4. 性能：~2-5s/次（Playwright 启动占主要开销）

### 附带修复：networkidle → domcontentloaded

坐山客前端使用 WebSocket 长连接（SSE stream），`wait_until="networkidle"` 永远等不到空闲，导致 15s 超时。改为 `domcontentloaded`（DOM 加载完即可）+ `wait_for_timeout(2000)` 等待 JS 渲染。

## 进程重启清单

改 `tools/browser_dial_test.py`（或任何工具文件）后：

```bash
# 1. 找进程
ss -tlnp | grep 8000           # backend PID
ps aux | grep "gateway.run"    # zuoshanke Gateway PID

# 2. 全链路重启
kill <zuoshanke_gateway_pid>
fuser -k 8000/tcp
sleep 2

# 3. 重启
cd ~/zuoshanke/backend
.venv/bin/python main.py &              # backend
.venv/bin/python -m backend.gateway.run  # zuoshanke Gateway

# 4. 验证
curl -s http://localhost:8000/api/health
```

## 验证方法

```python
from browser_dial_test import dial_test
import json

for i in range(3):
    r = dial_test('http://localhost:5173/', screenshot=False)
    d = json.loads(r)
    print(f'拨测{i+1}: {d["duration_ms"]}ms, 错误: {d.get("error", "无")}')
```

预期输出（无线程错误）：
```
拨测1: 4060ms, 错误: 无
拨测2: 4235ms, 错误: 无
拨测3: 2834ms, 错误: 无
```
