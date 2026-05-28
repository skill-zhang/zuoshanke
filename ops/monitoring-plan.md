# 坐山客监控方案行动手册

> 版本：v1.0 | 创建日期：2025-07-10

---

## 一、背景与目标

### 1.1 背景

坐山客系统目前以**裸进程（nohup）**方式运行在服务器上，缺乏进程守护和异常告警机制。此前 SearXNG 服务已挂 9 天无人发现，暴露了可观测性的缺失。

### 1.2 目标

1. **实时可观测** — 服务挂了能在第一时间知道
2. **自动恢复** — 非 IT 用户也能一键修复服务
3. **渐进演进** — 当前开发阶段不强制 systemd，后续可平滑过渡

### 1.3 适用范围

| 服务 | 端口 | 运行方式 | 纳入监控 |
|------|------|---------|---------|
| 前端 (Vite) | :5173 | 裸进程 | ✅ |
| 后端 (FastAPI) | :8000 | 裸进程 | ✅ |
| Qwen LLM | :8083 | 裸进程 | ✅ |
| Hermes Gateway | — | 裸进程 | ✅ |
| Uptime Kuma | :3001 | Docker | ✅ 自监控 |

---

## 二、架构总览

```
┌─────────────────────────────────────────────────────┐
│                    坐山客服务器                        │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 前端     │  │ 后端     │  │ Qwen     │          │
│  │ :5173    │  │ :8000    │  │ :8083    │          │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘          │
│       │              │              │                │
│       └──────────────┼──────────────┘                │
│                      │ HTTP 健康检查                  │
│              ┌───────▼────────┐                      │
│              │  Uptime Kuma   │  ← Docker 容器       │
│              │  :3001         │                      │
│              └───────┬────────┘                      │
│                      │ 告警推送                       │
│              ┌───────▼────────┐                      │
│              │ 企业微信/钉钉   │                      │
│              │ 机器人通知      │                      │
│              └────────────────┘                      │
│                                                      │
│  ┌──────────────────────────────────────────┐        │
│  │ zuoshanke-ctl.sh  — 一键状态/修复脚本     │        │
│  └──────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

### 分层说明

| 层级 | 组件 | 职责 |
|------|------|------|
| **L1 进程守护** | systemd（待启用） | 进程崩溃自动重启、开机自启 |
| **L2 可观测性** | Uptime Kuma | 20秒间隔 HTTP 检查、可视化面板 |
| **L3 告警通知** | 企业微信/钉钉机器人 | 服务异常时即时推送 |
| **L4 一键恢复** | zuoshanke-ctl.sh | 非IT用户一键检测+修复 |

---

## 三、已部署组件

### 3.1 Uptime Kuma 监控面板

**部署方式：** Docker 容器

```bash
docker run -d --restart=always \
  -p 3001:3001 \
  -v uptime-kuma:/app/data \
  --name uptime-kuma \
  louislam/uptime-kuma:latest
```

**访问地址：** `http://服务器IP:3001`

**初始化步骤：**
1. 浏览器打开 `http://服务器IP:3001`
2. 创建管理员账号
3. 添加监控项（见下方）
4. 配置通知渠道

**推荐监控项配置：**

| 监控项 | 类型 | URL | 检查间隔 |
|-------|------|-----|---------|
| 前端 | HTTP(s) | `http://localhost:5173` | 20秒 |
| 后端 | HTTP(s) | `http://localhost:8000/docs` | 20秒 |
| Qwen LLM | HTTP(s) | `http://localhost:8083` | 30秒 |
| Gateway | TCP 端口 | 检查网关进程存活 | 30秒 |

**通知渠道配置（推荐）：**
- 企业微信机器人 Webhook
- 钉钉机器人 Webhook
- 邮件通知（可选）

### 3.2 zuoshanke-ctl.sh 一键运维脚本

**路径：** `~/zuoshanke/scripts/zuoshanke-ctl.sh`

**用法：**

```bash
# 查看所有服务状态（含 Uptime Kuma）
./zuoshanke-ctl.sh status

# 自动检测异常服务并重启（非IT用户专用）
./zuoshanke-ctl.sh fix

# 一键重启所有服务
./zuoshanke-ctl.sh restart

# 查看日志
./zuoshanke-ctl.sh logs              # 所有日志
./zuoshanke-ctl.sh logs backend      # 仅后端日志
./zuoshanke-ctl.sh logs frontend     # 仅前端日志
./zuoshanke-ctl.sh logs gateway      # 仅网关日志
./zuoshanke-ctl.sh logs kuma         # 仅 Uptime Kuma 日志
```

**脚本功能：**
- 检测各端口是否监听
- 后端额外做 API 健康检查（curl /api/channels）
- 自动调用 `start-zuoshanke.sh` 重启异常服务
- 彩色输出，一目了然

---

## 四、待启用组件

### 4.1 systemd 进程守护

> ⚠️ 当前开发阶段暂未启用，因调试时需频繁启停服务。
> 待开发稳定后启用。

**已创建的 systemd 单元文件：**

| 单元文件 | 服务 | 路径 |
|---------|------|------|
| `zuoshanke-gateway.service` | Hermes 网关 | `/etc/systemd/system/` |
| `zuoshanke-backend.service` | 后端 :8000 | `/etc/systemd/system/` |
| `zuoshanke-frontend.service` | 前端 :5173 | `/etc/systemd/system/` |
| `zuoshanke-qwen.service` | Qwen LLM :8083 | `/etc/systemd/system/` |

**启用步骤（开发稳定后执行）：**

```bash
# 1. 停掉当前 nohup 进程
kill <当前各服务 PID>

# 2. 启用并启动 systemd 服务
sudo systemctl enable --now zuoshanke-gateway.service
sudo systemctl enable --now zuoshanke-backend.service
sudo systemctl enable --now zuoshanke-frontend.service
sudo systemctl enable --now zuoshanke-qwen.service

# 3. 验证状态
sudo systemctl status "zuoshanke-*"

# 4. 查看日志
sudo journalctl -u zuoshanke-backend -f
```

**systemd 优势：**
- 进程崩溃后自动重启（Restart=always，5秒内）
- 开机自启（systemctl enable）
- 统一日志管理（journalctl）
- 依赖控制（前端依赖后端先启动）
- 零额外依赖（Linux 自带）

---

## 五、故障处理流程

### 5.1 非 IT 用户流程

```
服务访问异常
      │
      ▼
执行 ./zuoshanke-ctl.sh fix
      │
      ├── 脚本自动检测各服务状态
      ├── 自动重启异常服务
      └── 显示修复后的状态
      │
      ▼
  服务恢复 ✅
```

### 5.2 开发者排查流程

```bash
# 1. 查看整体状态
./zuoshanke-ctl.sh status

# 2. 查看异常服务日志
./zuoshanke-ctl.sh logs backend

# 3. 查看 Uptime Kuma 面板
# 浏览器打开 http://服务器IP:3001

# 4. 手动重启
./zuoshanke-ctl.sh restart
```

### 5.3 常见问题

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| 后端端口占用 | 上次进程未清理 | `kill $(lsof -ti :8000)` 后重启 |
| Qwen 启动慢 | 模型加载需 2-3 分钟 | 等待后检查 `./zuoshanke-ctl.sh status` |
| Uptime Kuma 连不上 | Docker 未启动 | `docker start uptime-kuma` |
| 企业微信没收到通知 | Webhook 配置错误 | 检查 Uptime Kuma 通知设置 |

---

## 六、后续规划

### 短期（当前已覆盖）
- [x] Uptime Kuma 监控面板部署
- [x] zuoshanke-ctl.sh 一键运维脚本
- [ ] Uptime Kuma 监控项配置（Web 界面操作）
- [ ] 企业微信/钉钉通知配置

### 中期（开发稳定后）
- [ ] 启用 systemd 进程守护
- [ ] 后端添加 `/health` 健康检查接口
- [ ] 配置 Uptime Kuma JSON 查询断言（深度检测）

### 长期
- [ ] 日志集中收集（如 Loki + Grafana）
- [ ] 性能指标采集（如 Prometheus + Node Exporter）
- [ ] 自动化告警升级策略

---

## 七、相关文件索引

| 文件 | 说明 |
|------|------|
| `~/zuoshanke/scripts/zuoshanke-ctl.sh` | 一键运维脚本 |
| `~/zuoshanke/scripts/start-zuoshanke.sh` | 服务启停脚本 |
| `/etc/systemd/system/zuoshanke-*.service` | systemd 单元文件（待启用） |
| `docs/ops/README.md` | 运维目录说明 |
