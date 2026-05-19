# Schema v0.9 — Avatar 情绪驱动：本体感知

## 核心哲学

**不要分析 LLM 的情绪，LLM 自己知道。**

- ❌ 不要独立调 LLM 去"分析用户情绪"——那等于再请一个人来猜你在想啥
- ✅ 跟用户对话的 LLM 自己感知对话内容，自然输出心情标签

## 架构

```
用户发消息 → fenshen:started → watching 👀（机械反应，即时）
LLM 回复   → fenshen:done   → amused 😊（机械反应，即时）
           → LLM输出[心情: xxx]标签 → 解析 → 覆盖 avatar（语义，最终态）
           → 剥离标签，只留干净回复给用户
```

三层覆盖关系：
1. `fenshen:started` → `watching`（即时，必触发）
2. `fenshen:done` → `amused`（即时，必触发）
3. LLM 心情标签 → **覆盖**前两者（有则用，无则保留 2）

## System Prompt 注入

在 `ai_engine.py` 的 `_build_channel_messages()` 中，**两条路径都要加**：

```python
# is_default=True（闲聊/坐山客人格）
"重要——回复末尾必须加一行标签表达此刻心情："
"\n[心情: 情绪词] 内心独白（10-20字口语）"
"\n情绪词: idle|watching|amused|annoyed|thinking"
"\n如：[心情: amused] 哈哈哈清泉又讲冷笑话了😂"

# is_default=False（一般频道）
"重要——回复末尾必须加一行标签表达此刻心情："
"\n[心情: 情绪词] 内心独白（10-20字口语）"
"\n情绪词: idle|watching|amused|annoyed|thinking"
"\n如：[心情: amused] 这回答应该能让对方开心😄"
```

**Qwen 3.5-9B 行为特征**：
- 简短一行式指令（4行以内）能可靠跟随
- 太多示例/太长格式会丢弃不跟
- 示例中的频道名称（如"瞎扯淡"）只是参考，LLM 会自动适配实际频道名

## 后端解析

在 `channels.py` 和 `gateway.py` 的回复完成回调中：

```python
# 解析
m = re.search(r'\[心情:\s*(\w+)\]\s*(.+?)\s*$', reply, re.DOTALL)
# group(1) = 情绪词, group(2) = 内心独白

# 剥离（对用户不可见）
clean = re.sub(r'\s*\[心情:\s*\w+\]\s*.+?\s*$', '', reply, flags=re.DOTALL).strip()
```

**顺序重要**：先 `fenshen:done`（基础状态），后解析心情标签（覆盖状态）。

## 空闲超时

在 `ZhuAgentManager.get_status()` 中做查询时超时检测，不修改 DB：

- 非 `idle`/`resting` 状态持续 > 45 秒 → 返回 `idle/""`
- 每次 `update_mood()` 刷新 `updated_at` 计时
- **坑**：SQLite 存回的 `updated_at` 是 naive datetime，比较前需补 UTC 时区

## 事件映射表

| 事件 | 类型 | mood | observation | 触发时机 |
|------|------|------|-------------|----------|
| fenshen:started | 机械 | watching | 看着【X】分身开始干活 | LLM 开始回复前 |
| fenshen:done | 机械 | amused | 【X】分身任务完成 ✅ | LLM 回复完成后 |
| [心情: xxx] | 语义 | 由 LLM 定 | 【X】LLM写的内心独白 | LLM 回复完成后（覆盖机械反应） |

## 涉及文件

- `backend/ai_engine.py` — system prompt 注入心情指令
- `backend/router/channels.py` — 流式路径：解析+剥离
- `backend/router/gateway.py` — 网关路径：解析+剥离
- `backend/agent_core/zhu_agent.py` — 空闲超时检测
