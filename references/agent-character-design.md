# 坐山客 AI 角色动画 — 设计实现

## 概述

坐山客系统顶层浮空的科技男孩角色，是该 AI 的视觉具象化。不是 UI 装饰，是 AI 的外在表现——有生命感、自主性。

## 定位

```
┌──────────────────────────────────────┐
│     ┌──────┐  ← 气泡(右侧弹出)        │
│     │      │                          │
│     │  角色  │  ← position:fixed       │
│     │ 56px  │    z-index:100 浮在顶部  │
│     └──────┘                          │
├──────────────────────────────────────┤
│ [logo] 坐山客                [TM][AM] │  ← Topbar(46px)
└──────────────────────────────────────┘
```

- **定位**: `position:fixed; top:0` 叠在 Topbar 上层，不占布局空间
- **居中偏左**: `display:flex; justify-content:center; margin-left:-25px`
- **角色画布**: 56×56px，`top:-3px`（略高于页面边缘）
- **对话气泡**: 右侧 `left:68px; top:10px`，13px 字号

## 气泡动画

出场时 `opacity:0 → 1` + `scale(0.92 → 1)` + `translateX(-4px → 0)`，使用 `cubic-bezier(0.34, 1.56, 0.64, 1)` 缓出曲线。每次状态变化重新触发。

## 11 种表情状态

| 状态 | 眼睛 | 嘴巴 | 特效 | 触发条件 |
|------|------|------|------|---------|
| idle | 闭目 | 微笑 | 呼吸动画 | 默认/工作完成2.5s后 |
| greeting | 睁眼 | 大笑 | 弹跳×2 | 进入场景 |
| thinking | 斜上 | 嘟嘴 | 左右微倾 | (手动/预留) |
| working | 专注 | 中性 | 快速脉冲+💦汗珠 | isGenerating=true |
| done | 眯眼笑 | 大张 | 弹跳庆祝 | isGenerating→false |
| error | 担忧 | 下弯 | 摇头抖动 | (预留) |
| notify | 睁眼 | 微笑 | 光圈闪烁 | (预留) |
| resting | zzz | 微笑 | 呼吸 | (预留) |
| angry | ╲_╱ | 锯齿 | 摇头 | (手动) |
| laugh | ^_^ | 大张 | 💧泪花飞溅 | 空闲自娱自乐 |
| sad | u_u | 哭嘴 | 💧泪流长河 | 空闲自娱自乐 |

## AI 原生自洽（无人工管理）

角色自主管理可见性和行为：

1. **用户操作**（mousedown/keydown/touchstart）→ 唤醒角色，重置空闲计时
2. **25秒无操作** → 进入"无聊"模式
   - 随机间隔(5-12s)切换表情和气泡内容
   - 内容：讲冷笑话、唱歌、自言自语、闹情绪
   - 随机从 entertainment 数组中选取
3. **3分钟无操作** → 自动隐藏（去睡觉）
4. **用户再次操作** → 立即出现（醒来）
5. 无隐藏/显示按钮，无手动管理 UI

## 文件索引

| 文件 | 用途 |
|------|------|
| `frontend/src/components/AgentCharacter.tsx` | 组件本体：SVG渲染+表情切换+气泡动画 |
| `frontend/src/index.css` | 角色样式+动画 keyframes |
| `frontend/src/stores/appStore.ts` | agentStatus/agentMessage/agentHidden 状态管理 |
| `frontend/src/App.tsx` | 联动逻辑：isGenerating检测+空闲检测+用户活动监听 |
| `prototypes/zuoshanke-char-v2.3.html` | 设计原型（最终定稿版） |

## 关键坑

1. `breathe-sm` 等所有 animation keyframes 必须含 `translateX(-50%)`，否则角色水平偏移（动画覆盖 base transform）
2. SVG 必须显式 `width="56" height="56"` 属性，避免浏览器按默认 300×150 渲染
3. `position:fixed` 元素不影响页面布局，但用户可能感知为"页面缩放"——这是 UX 感知，非 CSS 问题
4. 空闲检测与 isGenerating 互斥：AI 处理期间不走空闲逻辑
