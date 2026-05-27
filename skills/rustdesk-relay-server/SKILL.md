---
name: rustdesk-relay-server
description: RustDesk 中继服务器搭建指南 — Docker/podman 部署、客户端配置、国内环境镜像源、端口检测、nginx 反代
version: 1.0
category: system
triggers: [RustDesk, 中继服务器, 远程桌面, 自建中继, rustdesk, 中继部署, 远程连接, relay server, hbbs, hbbr]
---

# RustDesk 中继服务器搭建指南

## 配套工具

坐山客内置了 `rustdesk_generate_setup` 工具（⚙️ 系统分类），输入服务器 IP 即可一键生成完整部署配置：

```bash
# 示例：生成配置
rustdesk_generate_setup(server_ip="39.107.73.219", domain="relay.example.com", use_podman=True)
```

工具返回：部署步骤列表、docker/podman 命令、docker-compose.yml、客户端配置、nginx 配置、端口检测结果。

---

## 概述

在云 VPS 上用 Docker/podman 自建 RustDesk 中继服务器，解决公网中继无法连接的问题。适合国内服务器、Cellular 网络、跨 NAT 场景。

**端口说明：**

| 端口 | 协议 | 作用 |
|------|------|------|
| 21115 | TCP | NAT 类型测试 |
| 21116 | TCP+UDP | ID 注册/会合（rendezvous，核心端口） |
| 21117 | TCP | 中继数据转发（relay） |
| 21118 | TCP | Web 控制台（可选） |
| 21119 | TCP | Web 控制台 relay 端口（可选） |

## 部署步骤

### 1. 云控制台开放端口

在云平台安全组/防火墙开放上述端口。**注意**：
- 21116 必须同时开放 **TCP 和 UDP**
- 安全组规则可能绑定到错误的安全组上，检查实例实际关联的安全组

### 2. SSH 登录服务器

```bash
ssh root@<SERVER_IP>
```

### 3. 安装容器运行时

**Alibaba Cloud Linux / Anolis OS（不支持 Docker 官方脚本）：**

```bash
yum install -y podman
```

**Ubuntu/Debian/CentOS：**

```bash
curl -fsSL https://get.docker.com | sh
```

### 4. 拉取镜像（国内用 DaoCloud 镜像）

```bash
podman pull docker.m.daocloud.io/rustdesk/rustdesk-server-s6:latest
```

或配置永久镜像源（`/etc/containers/registries.conf`）：

```toml
unqualified-search-registries = ["docker.io"]
[[registry]]
prefix = "docker.io"
location = "docker.m.daocloud.io"
```

### 5. 启动容器

```bash
mkdir -p /root/rustdesk-data

podman run -d --name hbbs --restart=always \
  -p 21115:21115 -p 21116:21116 -p 21116:21116/udp -p 21118:21118 \
  -v /root/rustdesk-data:/data \
  docker.m.daocloud.io/rustdesk/rustdesk-server-s6:latest

podman run -d --name hbbr --restart=always \
  -p 21117:21117 -p 21119:21119 \
  -v /root/rustdesk-data:/data \
  docker.m.daocloud.io/rustdesk/rustdesk-server-s6:latest hbbr
```

### 6. [podman 专用] 配置 systemd 自启

```bash
podman generate systemd --name hbbs --files --new
podman generate systemd --name hbbr --files --new
cp /root/container-hbbs.service /etc/systemd/system/
cp /root/container-hbbr.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable container-hbbs container-hbbr
```

### 7. 验证运行

```bash
podman ps
# 两个容器都应为 Up 状态
```

### 8. 获取公钥

```bash
cat /root/rustdesk-data/id_ed25519.pub
```

保存输出的 Base64 密钥，客户端配置需要。

## 客户端配置

### 方式 A：GUI 配置（推荐）

1. 右击系统托盘 RustDesk 图标 → 设置 → 网络
2. ID/中继服务器填入 `<SERVER_IP>:21116`
3. Key 填入服务器公钥
4. 重启 RustDesk

### 方式 B：配置文件（脚本化）

编辑 `%APPDATA%\RustDesk\config\RustDesk2.toml`（Windows 路径）：

```toml
rendezvous_server = '<SERVER_IP>:21116'

[options]
custom-rendezvous-server = '<SERVER_IP>:21116'
```

**关键⚠️**：写完后必须将文件设为**只读**（属性勾选"只读" 或 `chmod 444`），否则 RustDesk 启动时会覆盖配置。

### 方式 C：固定密码（无人值守访问）

PowerShell（**非 WSL**，WSL 调用 GUI exe 无输出）：

```powershell
& 'C:\Users\Administrator\AppData\Local\rustdesk\rustdesk.exe' --password <密码>
```

## 常见坑

### 1. Docker Hub 被墙
国内 `docker.io` TCP 超时。用 `docker.m.daocloud.io` 或腾讯云内网 `mirror.ccs.tencentyun.com`。

### 2. podman 重启策略
podman 的 `--restart=always` 不保证重启持久化。必须 `podman generate systemd` 生成服务文件并 enable。

### 3. 安全组绑定错误
云平台安全组规则写在 A 组，但实例绑定了 B 组 — 端口永远不通。登录服务器 `curl -v` 或 `nc -zv` 验证。

### 4. GUI 配置最可靠
TOML 配置文件的 `relay_server` 和 `key` 字段不被 RustDesk 识别。用 GUI 的网络设置填入这些值，或者用 `[options]` 配 `custom-rendezvous-server`。

### 5. RustDesk 配置文件被覆盖
即使手动编辑 `RustDesk2.toml`，RustDesk 启动时会尝试写回配置。设为只读后日志会报 `Failed to store 2 config`，但**不影响**实际连接。

## 验证方法

部署完成后，在客户端查看日志（`%APPDATA%\RustDesk\log\`）：

```
start rendezvous mediator of <YOUR_IP>
```

如果只看到你的服务器 IP 而**没有** `rs-ny.rustdesk.com`，说明自定义中继配置成功。
