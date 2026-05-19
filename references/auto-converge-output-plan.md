# 自动收敛 + 产出闭环设计方案

> 2026-05-27 讨论产出
> 背景：查二手车场景下，分身引导用户到「下载APP、用组合条件筛选目标车型」阶段后，仍未触发收敛。用户需要：① 无感自动收敛 ② 收敛后自动产出可交付物（PDF/HTML/清单）送到聊天记录

## 一、现状问题

| 问题 | 描述 |
|------|------|
| **收敛用户无感** | 现在靠 LLM 问「要不要整理？」用户说「走起」才触发。用户根本不知道收敛是什么 |
| **迟迟不触发** | 分身到"你下个APP我来教你用"的阶段了，信息充分、建议到位、下一步是用户动手——但没人收敛 |
| **产出缺失** | 收敛完出了 PQ，但聊天里啥也没多，用户感觉「聊完了就完了？」 |
| **Dialog Engine 空转** | [PHASE:] 转移标记存在但 LLM 实际不写，阶段机形同虚设 |

## 二、设计原则

1. **零用户感知收敛** — 用户只管聊，收敛是后台行为，不打断对话
2. **零规则匹配** — 不写 if-场景名 的硬编码，所有判断走 LLM 或模型分类
3. **LLM 自决产出** — 产什么格式、产什么内容全由 LLM 根据对话内容定
4. **产物 = 新一条 AI 消息** — 产物直接发进聊天记录，用户打开就能用

## 三、触发机制：LLM 自然收敛标记

### 核心思路

取代「LLM 问用户要不要收敛」，改为 **LLM 在回复末尾输出收敛就绪标记**，后台自动触发收敛管线：

```
[CONVERGE: ready, summary="已覆盖车源平台、预算分配、车况检测流程"]
```

### 标记位置

跟 `[心情:]` 标签同一层级——在 LLM 回复的尾部，由 LLM 自然判断是否输出。后端检测剥离，不暴露给用户。

### LLM 什么时候自然输出这个标记？

不是靠 system prompt 写死规则，而是**在收敛工具的 tool description 中引导**。当前 `converge` 工具的 description 写的是：

> "收敛整理当前场景的 Thinking Map——合并相似节点、标记废弃、生成优先级队列。**在讨论充分、信息足够、用户同意收敛时调用。**"

那 LLM 觉得「该问用户要不要收」才会调。改为：

> "收敛整理当前场景的 Thinking Map——合并相似节点、标记废弃、生成优先级队列。**当对话从探索进入行动阶段、用户需要一份可执行的行动方案时，在回复末尾输出 `[CONVERGE: ready, summary="..."]` 标记来触发自动收敛。**"

这样 LLM 在以下时机自然输出标记：
- 发现自己给了一堆建议、用户下一步是去现实世界动手（下载APP、实地看车、联系卖家）
- 信息已经覆盖了主要方面，再聊就是重复
- 用户说「好了」「就这样」「先这样」

**不靠规则**——LLM 自己判断「该进入行动了」，这是它的常识。

### 后台处理

```python
# scenes.py stream_scene_message() 中，Agent Loop done 后
CONVERGE_READY_RE = re.compile(r'\[CONVERGE:\s*ready\s*,\s*summary="([^"]*)"\]')

match = CONVERGE_READY_RE.search(full_reply)
if match:
    summary = match.group(1)
    full_reply = CONVERGE_READY_RE.sub("", full_reply).strip()
    # 自动触发收敛
    from agent_core.converge_engine import auto_converge_and_prioritize
    from tools.converge_tool import _do_converge
    pq_items = auto_converge_and_prioritize(db, scene_id, tmap, summary=summary)
    # 然后触发产出（见第四节）
```

**标记剥离**：正则匹配后从 `full_reply` 中移除 `[CONVERGE: ...]` 标记，用户看到的回复是干净的。

## 四、产出机制：收敛后自动生成可交付物

### 流程

```
收敛完成（得到 PQ + 对话上下文）
  ↓
调 LLM（deepseek flash, temp=0.3），传入：
  - 场景名、对话摘要 (summary)
  - PQ 列表（任务 + 优先级 + 依赖）
  - 用户背景设定
  ↓
LLM 输出结构化产出提案：
  [OUTPUT: type="checklist", title="二手车行动手册"]
  ## 第一步：下载APP并筛选车源
  1. 下载懂车帝/瓜子二手车
  2. 筛选条件：3-8万、北京、个人卖家...
  ## 第二步：看车检测清单
  1. 查4S店保养记录
  2. 查保险公司出险记录
  ...
  [/OUTPUT]
  ↓
后端解析 [OUTPUT] 块：
  - 存入 SceneAsset 表（scene_id, type, title, content, format）
  - 追加为一条新的 AI 消息（带富文本或下载链接）
  - 前端渲染为可交互卡片
```

### 产出格式

`[OUTPUT]` 块格式设计：

```json
[OUTPUT: type="checklist", title="二手车行动手册"]
content...
[/OUTPUT]
```

| type | 含义 | 前端渲染 | 是否支持导出 |
|------|------|---------|------------|
| `checklist` | 可勾选清单 | 带 checkbox 的列表 | PDF / 纯文本 |
| `guide` | 步骤指南 | 带序号和说明的卡片 | PDF / HTML |
| `table` | 对比表格 | 表格组件 | PDF / CSV |
| `html_page` | 独立 HTML 页面 | iframe 预览 + 下载按钮 | `.html` 文件 |
| `pdf` | LLM 直接产出 PDF 内容 | 下载按钮 | `.pdf` |

**不限制** LLM 选什么——它根据场景内容自主判断哪种格式最合适。

### 存储

新增 `SceneAsset` 表：

```python
class SceneAsset(Base):
    __tablename__ = "scene_assets"
    id: str = Column(String, primary_key=True)
    scene_id: str = Column(String, ForeignKey("scenes.id"))
    type: str = Column(String)        # checklist / guide / table / html_page / pdf
    title: str = Column(String)
    content: str = Column(Text)       # markdown 内容主体
    format: str = Column(String)      # 产出格式标记
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
```

### 送到聊天记录

产出生成后，后端构造一条特殊的 AI 消息：

```python
# SSE 事件
yield sse_event("asset", type=asset.type, title=asset.title,
                content=asset.content, asset_id=asset.id)
```

前端 `appStore.ts` 的 `sendSceneMsg()` 新增 `asset` 事件分支：
```tsx
if (event.type === 'asset') {
  // 追加到消息列表，作为新的 AI 消息
  appendMessage({
    id: event.asset_id,
    role: 'ai',
    content: '',  // 主内容由产出卡片展示
    asset: { type: event.type, title: event.title, content: event.content }
  });
}
```

## 五、全链路流程

```
用户：我想做二手车，没车，从哪弄车…

  ↓ 多轮对话（Agent Loop + LLM 引导）

分身：建议你下载懂车帝和瓜子二手车，
      用这几个筛选条件找车源，
      看车时注意这几个点…
      [CONVERGE: ready, summary="已覆盖车源平台推荐、预算分配、看车检测流程"]

  ↓ 后端检测 [CONVERGE:] → 剥离标记
  ↓ 自动触发收敛管线 → converge_engine 合并/排 PQ
  ↓ LLM 生成产出（checklist/guide/table）
  ↓ 存入 SceneAsset + 发送 SSE asset 事件

前端聊天框：
  坐山客：建议你下载懂车帝和瓜子二手车，用这几个筛选条件找车源…
  ┌──────────────────────────────────┐
  │ 📋 二手车行动手册                │
  │                                  │
  │ ✅ 第一步：下载APP              │
  │ ☐ 第二步：筛选车源              │
  │ ☐ 第三步：看车检测              │
  │ ☐ 第四步：谈价格签合同          │
  │                                  │
  │ [📥 下载PDF] [📄 查看完整版]     │
  └──────────────────────────────────┘

用户：打开看看 → 打开手册 → 
用户到车场了 → 打开手机看手册 → 逐项打勾
```

## 六、实施路径（分步走）

### Phase 1：自动收敛触发 ✅（当前可做）

1. `converge` 工具的 `description` 改为引导 LLM 输出 `[CONVERGE: ready, summary="..."]` 标记
2. `scenes.py` 的 `stream_scene_message()` 中，Agent Loop 完成后检测标记
3. 匹配到标记 → 自动调 `auto_converge_and_prioritize()` 
4. 剥离标记，用户看到干净回复

### Phase 2：产出生成（本方案主体）

1. 新增 `SceneAsset` 表（`create_all()`，零破坏）
2. 收敛完成后调 LLM 生成 `[OUTPUT]` 块
3. 后端解析、存表、发 SSE `asset` 事件
4. 前端 `ChatView` 渲染产出卡片

### Phase 3：前端渲染

1. 前端 `sendSceneMsg()` 新增 `asset` 事件分支
2. ChatView 新增 `AssetCard` 组件（按 type 渲染不同 UI）
3. checkbox 联动（可选持久化勾选状态）
4. PDF/HTML 导出按钮

## 七、关键设计决策

| 决策 | 选型 | 理由 |
|------|------|------|
| 触发标记位置 | 回复末尾 `[CONVERGE:]` | 与 `[心情:]` 同一机制，后端正则解析剥离 |
| 产出判定 | LLM 自主选格式 | 零规则匹配，LLM 知道场景内容该产什么 |
| 是否放 system prompt | **不放** | 这是机制驱动（工具 description + 后端处理），不是 prompt 注入 |
| 产物送达 | SSE 事件 + 聊天记录 | 用户打开场景就能看到，不需要另找入口 |
| SceneAsset 表 | Base.metadata.create_all() | 新增表，零破坏，无需重建 DB |
