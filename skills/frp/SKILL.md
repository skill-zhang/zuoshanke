---
name: frp
description: frp（Fast Reverse Proxy）内网穿透方案 — 服务端 frps + 客户端 frpc 部署、Docker/k8s、TCP/HTTP/HTTPS 代理、面板监控、国内优化
version: 1.0
category: system
triggers: [frp, frps, frpc, 内网穿透, 反向代理, 端口映射, 公网访问, Fast Reverse Proxy, 穿透]
---

# frp 内网穿透方案

## 配套工具

坐山客内置了 `frp_generate_setup` 工具（⚙️ 系统分类），输入服务器 IP 即可生成完整配置：

```bash
# TCP 穿透（泛用，远程桌面、SSH 等）
frp_generate_setup(server_ip="39.107.73.219", local_port=5173, remote_port=8080)

# HTTP 穿透（Web 服务，可自定义域名）
frp_generate_setup(server_ip="39.107.73.219", proxy_type="http", local_port=5173, custom_domain="zuoshanke.com")
```

工具返回：frps/frpc 配置文件、Docker 命令、systemd 服务、面板信息、端口检测、部署步骤。

---

## 概述

frp 是一个高性能的反向代理应用，支持 TCP、UDP、HTTP、HTTPS 协议。frp 适合：
- 国内用户（服务器在国内，低延迟，没有境外绕路）
- 需要稳定长期公网暴露
- 自己有一台云 VPS

**架构：**
```
用户浏览器
    ↓
云服务器（frps） — 公网 IP，监听 7000/8080/7500
    ↑
frpc（内网机器） — 出站连接 frps:7000，映射本地服务
    ↓
本地服务（坐山客 :5173 / API :8000）
```

**端口说明：**

| 端口 | 作用 |
|------|------|
| 7000 | frps-frpc 通信端口（必开） |
| 7500 | 管理面板（可选，建议开） |
| 8080 | 映射后的公网服务端口（根据需求调整） |

## frps（服务端）部署

### Docker 部署（推荐）

```bash
# 1. SSH 登录服务器
ssh root@<SERVER_IP>

# 2. 创建配置目录和文件
mkdir -p /root/frp
cat > /root/frp/frps.toml << 'EOF'
bindPort = 7000
auth.token = "your_token_here"

webServer.addr = "0.0.0.0"
webServer.port = 7500
webServer.user = "admin"
webServer.password = "your_dashboard_pwd"
EOF

# 3. 启动 frps
docker run -d --name frps --restart=always \
  --network host \
  -v /root/frp/frps.toml:/etc/frp/frps.toml \
  snowdreamtech/frps

# 4. 验证
curl -u admin:your_dashboard_pwd http://<SERVER_IP>:7500/api/serverinfo
```

### 非 Docker 部署

```bash
# 1. 下载 frp
wget https://github.com/fatedier/frp/releases/latest/download/frp_linux_amd64.tar.gz
tar -xzf frp_linux_amd64.tar.gz
cd frp_*

# 2. 复制二进制
cp frps /usr/local/bin/frps

# 3. 创建 systemd 服务（见下方）
```

### systemd 服务

`/etc/systemd/system/frps.service`:
```ini
[Unit]
Description=frp server (frps)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/frps -c /root/frp/frps.toml
Restart=always
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable frps
systemctl start frps
```

## frpc（客户端）配置

`/root/frp/frpc.toml`:
```toml
serverAddr = "<SERVER_IP>"
serverPort = 7000
auth.token = "your_token_here"

[[proxies]]
name = "zuoshanke-web"
type = "tcp"
localIP = "127.0.0.1"
localPort = 5173
remotePort = 8080
```

在**内网机器**上启动 frpc：

```bash
# Docker
docker run -d --name frpc --restart=always \
  --network host \
  -v /root/frp/frpc.toml:/etc/frp/frpc.toml \
  snowdreamtech/frpc

# 或二进制
frpc -c /root/frp/frpc.toml
```

## HTTP 代理 + 自定义域名

frps.toml 需添加：
```toml
vhostHTTPPort = 8080
```

frpc.toml 代理改为：
```toml
[[proxies]]
name = "zuoshanke-web"
type = "http"
localIP = "127.0.0.1"
localPort = 5173
customDomains = ["zuoshanke.com"]
```

DNS 将域名指向 frps 服务器 IP，浏览器直接访问 `http://zuoshanke.com:8080`。

## 管理面板

浏览器打开 `http://<SERVER_IP>:7500`，可查看：
- 在线代理列表
- 流量统计
- 连接状态
- 实时日志

## 国内下载优化

GitHub Releases 国内可能慢，用镜像：

```bash
# GitHub 镜像
wget https://hub.fastgit.xyz/fatedier/frp/releases/latest/download/frp_linux_amd64.tar.gz

# 或 Gitee（第三方搬运，注意版本）
```

Docker 镜像用 DaoCloud:
```bash
docker pull docker.m.daocloud.io/snowdreamtech/frps
docker pull docker.m.daocloud.io/snowdreamtech/frpc
```

## frp vs Cloudflare Tunnel

| 维度 | frp | Cloudflare Tunnel |
|------|-----|-------------------|
| 是否需要 VPS | ✅ 需要 | ❌ 不需要 |
| 国内延迟 | ✅ 低（服务器在国内） | ⚠️ 200-400ms（绕境外） |
| 域名要求 | ❌ 不需要（直接用 IP:端口） | ✅ 需要域名 |
| 免费 | ✅ 是（VPS 自己付） | ✅ 是 |
| 配置复杂度 | ⚠️ 稍复杂（两端都需要配） | ✅ 简单（单条命令） |
| 协议支持 | TCP/UDP/HTTP/HTTPS | HTTP/HTTPS/SSH |
| HTTPS | 需自行配置证书 | ✅ 自动 |
| 面板监控 | ✅ 有 | ❌ 无 |

## 常见坑

### 1. 安全组忘记开端口
frps 的 bindPort、dashboardPort、remotePort 都需要在云控制台开放。三个端口各有用途，缺一不可。

### 2. --network host 与端口冲突
Docker 的 `--network host` 让容器直接使用宿主机网络。如果宿主机已有服务占用相同端口，会冲突。检查 `ss -tlnp`。

### 3. token 不匹配
frps.toml 和 frpc.toml 的 `auth.token` 必须一致，否则 frpc 连接会被拒绝。日志中会出现 `auth error`。

### 4. HTTP 代理需要 vhostHTTPPort
frps.toml 中必须显式设置 `vhostHTTPPort`，否则 HTTP 类型的代理无法工作。

### 5. frp v2 TOML vs v1 INI 格式
frp v2（当前最新）使用 TOML 格式（`key = "value"`）。v1 使用 INI 格式（`key = value`）。配置前确认 frp 版本。

### 6. 面板首次加载慢
面板页面首次加载可能需要几秒，因为 frps 需要加载静态资源。之后响应很快。

## 验证方法

1. **服务端运行**: `docker ps | grep frps` 或 `systemctl status frps`
2. **面板**: 浏览器 `http://<SERVER_IP>:7500`（用户名密码登录）
3. **代理状态**: `curl -u admin:pass http://<SERVER_IP>:7500/api/proxy/tcp`
4. **穿透测试**: TCP 用 `nc -zv <SERVER_IP> <remote_port>`，HTTP 直接浏览器
5. **日志**: `docker logs frps --tail 50` 或 `journalctl -u frps --no-pager -n 50`
