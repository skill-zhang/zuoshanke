# 工作台 v1.3 实现总结 — 2026-05-26

## 架构总览

```
[场景] → 发布(version≠0.0) → [场景广场] → 钉(show_on_workbench=true) → [工作台]
                                                                              ↓
                                                                 8种卡片按category分派渲染
```

## 8种卡片类型

| category | 卡片 | scene_config key | 数据源 |
|----------|------|-----------------|--------|
| `life` | 今日天气 🌤️ | `.weather` | 后端写入（或 Agent Loop 完成后更新） |
| `todo` | 待办事项 ✅ | `.todo[]` | 静态/手工维护 |
| `news` | 今日咨询 📰 | `.news[]` | 需互联网实时抓取 |
| `game` | 小村庄大冒险 🎮 | `.game` | 链接到独立 HTML 页面 |
| `analysis` | AI用量仪表 📊 | `.analysis` | 需 DeepSeek API |
| `git` | 代码提交 🔨 | `.git` | `git log` 实时采集 |
| `stock` | 小米股价 📈 | `.stock` | 需互联网实时行情 |
| `shopping` | 618热销榜 🛒 | `.shopping[]` | 需互联网抓取 |

## 核心文件变迁

| 文件 | 角色 |
|------|------|
| `backend/schemas.py` | SceneOut + SceneUpdate 加 `show_on_workbench`, `workbench_position` |
| `backend/models.py` | Scene 模型加对应字段 |
| `backend/router/scenes.py` | update_scene 处理新字段 |
| `frontend/src/api/client.ts` | Scene 接口加 `scene_config`, `show_on_workbench`, `workbench_position` |
| `frontend/src/stores/appStore.ts` | 加 `'workbench'` ViewPage, `scenes` 状态, `loadScenes` 方法 |
| `frontend/src/App.tsx` | 启动调用 `loadScenes()` + 默认首页路由(initialRouteRef) |
| `frontend/src/components/WorkbenchView.tsx` | 8种卡片渲染 + header/footer 分派 |
| `frontend/src/components/PlazaView.tsx` | 广场卡片钉按钮 |
| `frontend/src/components/Sidebar.tsx` | 工作台导航入口 |
| `frontend/src/index.css` | 全部卡片类型样式 |
| `docs/design/schema-v1.3.md` | 设计文档 |
| `prototypes/prototype-workbench-v2.0.html` | 原型（8种卡片+多入口） |

## 关键决策

1. **JSON 数据源**：所有卡片数据从 `scene.scene_config` JSON 读，零文本正则——用户明确纠正"前后端用json，为啥要用正则"
2. **独立页面**：`view==='workbench'` 时不渲染 Topbar/Sidebar/.main
3. **默认首页**：有工作台场景时首次进入自动跳转（`initialRouteRef` 防循环）
4. **三区域**：header(聊天入口)/body(类型自适应)/footer(产出入口)
5. **Header 友好标题**：天气卡片显示"今日天气"而非场景名"天气查询"
6. **无 pin 按钮**：工作台卡片已钉选，右侧只显示场景相关操作（如城市+刷新）
7. **后端存 JSON**：需实时数据（天气/股票/新闻）通过 PATCH 写入 scene_config
