---
name: proxy-aware-diagnostics
description: 服务/端口诊断时自动排除代理污染，避免误判
triggers:
  - 服务检查
  - 端口诊断
  - 503
  - 连接失败
  - curl
  - 后端挂了
  - 服务不可用
  - check_services
---

# 代理感知诊断技能

## 核心原则

系统可能设置了 `http_proxy` / `https_proxy` / `HTTP_PROXY` / `HTTPS_PROXY` 环境变量。用 curl 等工具检查本地服务时，请求可能被代理拦截，代理返回 503 等错误码，导致误判服务状态。

## 操作规范

### 1. 检查本地服务时，始终使用 `--noproxy '*'`

```bash
# ❌ 错误：可能被代理拦截
curl localhost:8000

# ✅ 正确：绕过代理直连
curl --noproxy '*' localhost:8000
```

### 2. 先确认代理环境变量是否存在

```bash
echo "http_proxy=$http_proxy"
echo "https_proxy=$https_proxy"
echo "HTTP_PROXY=$HTTP_PROXY"
echo "HTTPS_PROXY=$HTTPS_PROXY"
```

### 3. 区分不同错误码的含义

| 现象 | 可能原因 |
|------|---------|
| curl 返回 503 | 代理拦截（先查代理变量） |
| curl 返回 404 | 服务正常，只是路径无路由 |
| curl: Connection refused | 服务真的没在监听 |
| curl: No route to host | 服务进程可能挂了 |

### 4. 用 ss 确认进程存在

```bash
ss -tlnp | grep :8000
```

如果 ss 显示有进程在监听，但 curl 返回非预期状态码，**优先怀疑代理污染**。

## 触发场景

- 用户报告服务不可用
- check_services 返回异常
- 拨测失败
- 任何涉及 localhost 端口连通性的排查
