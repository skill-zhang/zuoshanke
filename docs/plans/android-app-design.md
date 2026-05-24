# 坐山客安卓 APP 设计方案

## 背景
在已有坐山客后端（FastAPI + SQLite）和 Web 前端（React）的基础上，开发一款安卓原生 APP，通过 WiFi 内网连接后端，实现双端互通。

## 目标
- 安卓手机通过 WiFi 内网连接坐山客后端 API
- 实现三大核心功能：**讨论·频道【闲聊】**、**工坊（场景广场）**、**产出成果**
- 与 Web 端数据完全互通（同一 DB）
- 轻量、流畅、符合移动端交互习惯

## 技术选型

### 推荐方案：Flutter（跨平台）
- **理由**：一套代码同时覆盖 Android / iOS，后续可扩展桌面端
- HTTP 请求用 `dio` 或 `http` 包
- 状态管理用 `Provider` 或 `Riverpod`
- 本地缓存用 `sqflite` 或 `hive`
- SSE 流式聊天用 `flutter_client_sse` 或原生 `EventSource`

### 备选方案：原生 Kotlin
- 更轻量，无跨平台开销
- 但后续维护两套代码成本高

**推荐 Flutter**，理由：后续可以扩展到 iOS，且与后端 JSON API 天然适配。

## 后端 API 对接分析

坐山客后端运行在 `http://<内网IP>:8000`，已有以下相关 API：

### 1. 讨论·频道（闲聊）
| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/channels` | GET | 列出所有频道 |
| `/api/channels` | POST | 创建频道 |
| `/api/channels/{id}` | PATCH | 更新频道 |
| `/api/channels/{id}/messages` | GET | 获取频道消息 |
| `/api/channels/{id}/messages` | POST | 发送消息 |
| `/api/channels/{id}/messages/stream` | GET(SSE) | 流式聊天 |

- **闲聊频道**：可以固定一个名为"闲聊"的默认频道，或者让用户选择频道
- **SSE 流式**：移动端需要支持 Server-Sent Events 接收 AI 流式回复

### 2. 工坊（场景广场）
| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/scenes` | GET | 列出所有场景（工坊列表） |
| `/api/scenes` | POST | 创建场景 |
| `/api/scenes/{id}` | GET | 场景详情 |
| `/api/scenes/{id}` | PATCH | 更新场景 |
| `/api/scenes/{id}/chat` | POST | 场景内对话 |
| `/api/scenes/{id}/chat/stream` | GET(SSE) | 场景内流式对话 |

- 场景列表展示：图标、名称、描述、分类
- 点击进入场景详情/对话
- 场景内支持流式对话

### 3. 产出成果
| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/outputs` | GET | 列出产出成果（可过滤场景） |
| `/api/outputs/{id}` | GET | 产出成果详情 |
| `/api/outputs` | POST | 创建产出成果 |

- 产出成果列表展示（标题、描述、类型）
- 支持查看产出成果内容（HTML 等）
- 通过 `/outputs/` 静态文件服务访问实际文件

### 其他可能需要的 API
| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/health` | GET | 健康检查/连通性测试 |
| `/api/zhu-agent/garden/chat/history` | GET | 起居室聊天历史 |

## 网络层设计

### WiFi 内网连接
1. **服务发现**：APP 启动时扫描局域网，或让用户手动输入后端 IP
2. **连接方式**：
   - 用户输入 `http://192.168.x.x:8000`
   - 保存到 SharedPreferences / 本地存储
   - 首次连接自动检测 `/api/health`
3. **网络切换处理**：
   - 监听网络状态变化
   - 断线时显示提示，自动重连
4. **安全性**：
   - 内网场景，暂不涉及 HTTPS（如需外网访问可加 Nginx 反代 + Let's Encrypt）

### 连接配置
```
后端地址: http://{手机可访问的服务器IP}:8000
```

## APP 页面结构

```
┌─────────────────────┐
│    底部导航栏        │
├─────────────────────┤
│ 📱 闲聊  │ 🏭 工坊 │ 📦 成果 │ ⚙️ 设置 │
└─────────────────────┘

### 页面 1：闲聊（讨论·频道）
- 频道列表（侧拉或顶部 Tab）
- 消息列表（气泡样式）
- 底部输入框 + 发送按钮
- SSE 流式接收 AI 回复

### 页面 2：工坊（场景广场）
- 场景卡片网格/列表
- 每个卡片：图标 + 名称 + 简介
- 点击进入场景详情页
- 场景内：对话界面（同闲聊样式）

### 页面 3：产出成果
- 成果列表（时间倒序）
- 卡片：标题 + 描述 + 类型标签 + 时间
- 点击查看详情（WebView 加载 HTML 内容）

### 页面 4：设置
- 后端地址配置
- 连接状态显示
- 关于信息
```

## 数据流设计

```
┌──────────────┐    HTTP/SSE     ┌──────────────┐
│  安卓 APP     │ ────────────→  │  坐山客后端   │
│  (Flutter)   │ ←──────────── │  (FastAPI)    │
└──────────────┘                └──────┬───────┘
                                       │
                              ┌────────▼───────┐
                              │   SQLite DB     │
                              └────────────────┘
```

- APP 不直接操作 DB，全部通过 REST API
- SSE 用于流式聊天
- 产出成果的 HTML 文件通过静态文件服务访问

## 实现计划

### Phase 1：项目脚手架 + 网络层（1-2天）
- 创建 Flutter 项目
- 实现 HTTP 客户端封装（base URL 配置、错误处理）
- 实现健康检查/连通性检测
- 底部导航框架

### Phase 2：闲聊模块（2-3天）
- 频道列表
- 消息列表 + 发送消息
- SSE 流式接收 AI 回复
- 消息气泡 UI

### Phase 3：工坊模块（2天）
- 场景列表
- 场景详情页
- 场景内对话

### Phase 4：产出成果模块（1天）
- 成果列表
- 成果详情（WebView）

### Phase 5：设置 + 打磨（1天）
- 后端地址配置
- 连接状态显示
- UI 细节优化
- 断线重连处理

## 文件结构（Flutter 项目）

```
zuoshanke_app/
├── lib/
│   ├── main.dart              # 入口
│   ├── config/
│   │   └── api_config.dart    # API 地址配置
│   ├── services/
│   │   ├── api_client.dart    # HTTP 客户端封装
│   │   ├── channel_service.dart  # 频道 API
│   │   ├── scene_service.dart    # 场景 API
│   │   ├── output_service.dart   # 产出成果 API
│   │   └── sse_service.dart      # SSE 流式处理
│   ├── models/
│   │   ├── channel.dart
│   │   ├── message.dart
│   │   ├── scene.dart
│   │   └── output.dart
│   ├── pages/
│   │   ├── home_page.dart     # 底部导航壳
│   │   ├── chat/
│   │   │   ├── chat_list_page.dart
│   │   │   └── chat_detail_page.dart
│   │   ├── workshop/
│   │   │   ├── scene_list_page.dart
│   │   │   └── scene_detail_page.dart
│   │   ├── outputs/
│   │   │   └── output_list_page.dart
│   │   └── settings/
│   │       └── settings_page.dart
│   └── widgets/
│       ├── message_bubble.dart
│       ├── scene_card.dart
│       └── output_card.dart
├── pubspec.yaml
└── README.md
```
