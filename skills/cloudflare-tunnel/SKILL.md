---
name: cloudflare-tunnel
description: Cloudflare Tunnel 公网访问方案 — quick/named 隧道、Caddy Basic Auth、systemd 自启、Vite 配置、避坑指南
version: 1.0
category: system
triggers: [Cloudflare Tunnel, 公网访问, 内网穿透, 隧道, cloudflared, trycloudflare, Caddy, Basic Auth, 外网访问]
---

# Cloudflare Tunnel 公网访问方案

## 配套工具

坐山客内置了 `cloudflare_tunnel_setup` 工具（⚙️ 系统分类），输入本地端口和认证参数即可一键生成配置：

```bash
# Quick tunnel + Basic Auth（适合开发环境临时公网测试）
cloudflare_tunnel_setup(local_port=5173, auth_enabled=True, auth_user="admin", auth_pass="your_pass")

# Named tunnel（自有域名，永久隧道）
cloudflare_tunnel_setup(mode="named", domain="zuoshanke.yourdomain.com")
```

工具返回：cloudflared 安装检查、隧道运行命令、Caddyfile 配置、systemd 服务、Vite 配置调整、部署步骤。

---

## 概述

用 Cloudflare Tunnel 将本地开发服务（如坐山客工作台）暴露到公网，无需公网 IP，无需 VPS，自带 HTTPS。

**架构：**
```
用户手机/浏览器
    ↓ HTTPS
Cloudflare 边缘节点
    ↓ 安全隧道（出站连接）
cloudflared (WSL/服务器)
    ↓ (可选) HTTP
Caddy (Basic Auth 反向代理)
    ↓ HTTP
Vite 开发服务器 (:5173) / API 后端 (:8000)
```

## 两种模式对比

| 特性 | Quick Tunnel | Named Tunnel |
|------|-------------|-------------|
| 是否需要域名 | ❌ 不需要 | ✅ 需要 (已在 Cloudflare 管理) |
| 是否需要 Cloudflare 账号 | ❌ 不需要 | ✅ 需要 |
| URL | `xxx.trycloudflare.com`（随机） | 你的自定义域名 |
| 持久性 | 进程停止后域名失效 | 永久有效 |
| Basic Auth | 需 + Caddy | 可在 config.yml 加 |
| 适用场景 | 临时测试、演示 | 长期使用、生产 |

## Quick Tunnel 部署步骤

### 1. 安装 cloudflared

```bash
# Linux AMD64
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

### 2. 安装 Caddy（如需认证）

```bash
# Linux
apt install -y caddy
# 或手动下载
wget https://github.com/caddyserver/caddy/releases/latest -O /usr/bin/caddy
chmod +x /usr/bin/caddy
```

### 3. 创建 Caddyfile

`/tmp/Caddyfile`:
```
:8080 {
    basicauth * {
        admin $2a$14$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    }

    handle_path /api/* {
        reverse_proxy localhost:8000
    }

    handle {
        reverse_proxy localhost:5173
    }
}
```

生成密码哈希：
```bash
caddy hash-password --plaintext your_password
```

### 4. 启动 Caddy

```bash
caddy run --config /tmp/Caddyfile --adapter caddyfile
```

### 5. 启动 Tunnel

```bash
cloudflared tunnel --url http://localhost:8080
```

终端会显示 `https://xxx.trycloudflare.com`，浏览器打开即可访问。

### 6. 确认 Vite 配置

`frontend/vite.config.ts` 必须有：
```ts
server: {
  allowedHosts: true,  // 允许 Cloudflare Tunnel 域名
  port: 5173,
  proxy: { "/api": "http://localhost:8000" },
}
```

## Named Tunnel 部署步骤

```bash
# 1. 登录授权
cloudflared tunnel login
# 浏览器打开链接，授权域名

# 2. 创建隧道
cloudflared tunnel create zuoshanke-tunnel

# 3. 创建 ~/.cloudflared/config.yml
#    tunnel: zuoshanke-tunnel
#    credentials-file: /root/.cloudflared/zuoshanke-tunnel.json
#    ingress:
#      - hostname: zuoshanke.yourdomain.com
#        service: http://localhost:5173
#      - service: http_status:404

# 4. DNS 路由
cloudflared tunnel route dns zuoshanke-tunnel zuoshanke.yourdomain.com

# 5. 启动
cloudflared tunnel run zuoshanke-tunnel
```

## systemd 自启

```ini
[Unit]
Description=Cloudflare Tunnel (zuoshanke)
After=network.target

[Service]
Type=simple
User=root
ExecStart=cloudflared tunnel --url http://localhost:8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable cloudflared-tunnel
systemctl start cloudflared-tunnel
```

## 常见坑

### 1. Quick tunnel 不支持 --http-basic-auth
`cloudflared tunnel --http-basic-auth user:pass` 参数在 quick tunnel 模式下被忽略。必须用 Caddy 等反代层做认证。

### 2. Vite 域名白名单
Cloudflare Tunnel 域名不是 `localhost`，Vite 默认 host 检查会返回 403。添加 `server.allowedHosts: true` 解决。

### 3. Caddy 路由顺序
Caddyfile 中 `handle_path /api/*` 必须写在 `handle`（兜底）**之前**，否则 API 请求被当作静态文件处理。

### 4. API 路径
检查 Caddyfile 中 `handle_path` 的路径是否匹配后端实际路由（坐山客后端是 `/api/*`，不是 `/api/v1/*`）。

### 5. 微信浏览器限制
`trycloudflare.com` 域名在微信内置浏览器中无法打开（`net::ERR_HTTP_RESPONSE_CODE_FAILURE`）。Basic Auth 弹框在微信中也可能异常。用手机 Chrome 或其他浏览器。

### 6. 国内延迟
Cloudflare 边缘节点在国内可能延迟较高（200-400ms），但用于开发环境测试足够。

### 7. 心跳维持
Tunnel 需要保持终端进程运行。用 systemd 服务 + `Restart=always` 确保挂掉后自动重连。

## 验证方法

1. 浏览器打开 Tunnel 域名 → 应弹出 HTTP 登录框
2. 输入用户名密码 → 看到坐山客工作台
3. 打开开发者工具 → Network → 确认 `/api` 请求返回 200（不是 HTML）
4. 无认证时：直接看到页面，但公网任何人都能访问
