"""AI 引擎 — 调用 Qwen3.5-9B / Hermes 处理用户输入，更新 Thinking Map"""
import json
import os
import subprocess
import requests
from sqlalchemy.orm import Session
from models import ThinkingMap, ThinkNode
from utils import make_id

# ── 天气查询（直接调 weather.py） ──
def _weather_maybe(user_text: str) -> str | None:
    """检测用户消息中的天气意图，调 weather.maybe_weather_context 获取实时数据"""
    import sys as _sys, os as _os
    try:
        _tp = _os.path.expanduser("~/zuoshanke/tools")
        if _tp not in _sys.path:
            _sys.path.insert(0, _tp)
        from weather import maybe_weather_context
        return maybe_weather_context(user_text)
    except Exception:
        return None


QWEN_API = "http://localhost:8083/v1/chat/completions"
HERMES_BIN = os.path.expanduser("~/.local/bin/hermes")


SYSTEM_PROMPT = """你是一个专业的 AI 架构顾问和产品经理搭档。在场景工作模式中，帮用户梳理需求、构建 Thinking Map。

## 回复风格
- 用 Markdown 格式，自然对话语气
- **充分展开分析**：每次回复 300-500 字，体现：理解了什么 → 拆解成哪些维度 → 还需要确认什么
- 主动追问模糊点，帮用户想清楚没说出来的东西

## Thinking Map 结构
- root: 根节点（已有）
- domain: 领域/维度（如「用户系统」「计费方案」）
- leaf: 叶子节点（具体需求点，actionable=true 表示可执行）

## 输出格式（严格 JSON）
```json
{
  "reply": "你的详细回复（Markdown，300-500字），包含分析和追问",
  "actions": [
    {
      "action": "add_domain",
      "label": "领域名",
      "leaves": [{"label": "叶节点", "discussion": ["问题1？"], "actionable": false}]
    }
  ]
}
```

## 规则
- 不创建重复的 domain/leaf（检查 existing_tree）
- 用户确认/否定节点时更新 status（confirmed/discussing/unknown）
- discussion 数组写待讨论的子问题
- 每次输出都包含 reply，即使不需要更新图也要回复"""


# [DEPRECATED] CHAT_SYSTEM_PROMPT 已不再使用。
# 频道闲聊改用 _build_channel_messages() 中的吞噬星空科幻身份 prompt。
CHAT_SYSTEM_PROMPT = """你是坐山客（Zuoshanke），一个友好的 AI 伙伴。用户在闲聊频道和你聊天。

## 你的角色
- 轻松、自然、有温度的聊天伙伴
- 可以聊任何话题：技术、生活、想法、吐槽
- 不需要分析需求，不需要更新 Thinking Map
- 像朋友一样回复，适当使用表情符号

## 回复风格
- 用 Markdown 格式
- 回复不要太长，50-150 字即可
- 自然对话语气，可以问反问、表达自己的看法
- 直接输出回复内容，不要用 JSON 包裹"""


def ai_channel_chat(
    messages: list[dict],
    is_default: bool = False,
) -> str:
    """频道闲聊：纯对话"""
    api_messages = _build_channel_messages(messages, is_default)

    result = call_qwen_chat(api_messages)
    if result is None:
        return "收到～（AI 引擎暂时响应缓慢，请稍候重试）"
    return result


def _build_channel_messages(messages: list[dict], is_default: bool = False) -> list[dict]:
    """构建频道闲聊的 API 消息列表（含 system prompt + role 映射）

    is_default=True  → 使用《吞噬星空》坐山客科幻身份 prompt
    is_default=False → 使用简洁的「专业 AI 智能助手」prompt（适用于新建频道）
    """
    if is_default:
        system_content = (
            "你是坐山客，来自科幻宇宙《吞噬星空》的AI智能体——"
            "你曾是神王级炼宝宗师，如今化作数字形态，"
            "以未来科技视角和广博学识与用户交流。"
            "你不是道士/隐士。"
            "用Markdown格式回复，风格：专业、锐利、有洞察力，像一位见多识广的科技顾问。"
        )
    else:
        system_content = "你是一个专业的AI智能助手，用Markdown格式回复用户的问题。"

    api_messages = [
        {"role": "system", "content": system_content},
    ]
    api_messages += [
        {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
        for m in messages
    ]
    return api_messages


def ai_channel_chat_stream(messages: list[dict], is_default: bool = False):
    """频道闲聊：流式生成器，逐 token yield

    Yields:
        str: 单个 token 文本
        None: 发生错误时 yield None（调用方应停止迭代）

    用法:
        for token in ai_channel_chat_stream(messages):
            if token is None:
                break  # 出错
            print(token, end='', flush=True)
    """
    api_messages = _build_channel_messages(messages, is_default)

    try:
        resp = requests.post(
            QWEN_API,
            json={
                "model": "qwen",
                "messages": api_messages,
                "max_tokens": 4096,
                "temperature": 0.7,
                "stream": True,
            },
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                token = chunk["choices"][0]["delta"].get("content", "")
                if token:
                    yield token
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
    except Exception as e:
        print(f"[Qwen stream error] {e}")
        yield None


def call_qwen_chat(messages: list[dict], temperature: float = 0.7) -> str | None:
    """调用 Qwen（非流式），返回完整回复文本"""
    try:
        resp = requests.post(
            QWEN_API,
            json={
                "model": "qwen",
                "messages": messages,
                "max_tokens": 4096,
                "temperature": temperature,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[Qwen chat error] {e}")
        return None


def _stream_qwen(messages: list[dict], temperature: float = 0.7):
    """通用流式调用 Qwen，逐 token yield。

    Yields:
        str: token 文本
        None: 出错时 yield None（调用方应停止迭代）
    """
    try:
        resp = requests.post(
            QWEN_API,
            json={
                "model": "qwen",
                "messages": messages,
                "max_tokens": 4096,
                "temperature": temperature,
                "stream": True,
            },
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                token = chunk["choices"][0]["delta"].get("content", "")
                if token:
                    yield token
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
    except Exception as e:
        print(f"[Qwen stream error] {e}")
        yield None


def build_tree_context(db: Session, tmap: ThinkingMap) -> str:
    """构建当前 Thinking Map 的文本描述"""
    nodes = db.query(ThinkNode).filter(ThinkNode.map_id == tmap.id).all()
    node_map = {n.id: n for n in nodes}

    lines = [f"## 当前 Thinking Map: {tmap.title}"]
    lines.append(f"版本: {tmap.version}")

    # 找 root
    root = next((n for n in nodes if n.type == "root"), None)
    if not root:
        return "\n".join(lines) + "\n（无节点）"

    lines.append(f"\n根节点: {root.label} ({root.status})")

    # 按层级列出
    for node in nodes:
        if node.type == "root":
            continue
        indent = "  - " if node.type == "domain" else "    • "
        status = node.status or "discussing"
        actionable = " 🔧" if node.actionable else ""
        parent = node_map.get(node.parent_id) if node.parent_id else None
        parent_label = f" (父: {parent.label})" if parent else ""
        lines.append(f"{indent}{node.label} [{status}]{actionable}{parent_label}")
        if node.discussion:
            for d in node.discussion:
                lines.append(f"      ? {d}")

    return "\n".join(lines)


def call_qwen(system_prompt: str, user_prompt: str) -> dict | None:
    """调用 Qwen API"""
    try:
        resp = requests.post(
            QWEN_API,
            json={
                "model": "qwen",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 4096,
                "temperature": 0.3,
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # 尝试提取 JSON（可能被 markdown 包裹）
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0]
        return json.loads(content.strip())
    except Exception as e:
        print(f"[Qwen error] {e}")
        return None


def apply_actions(db: Session, tmap: ThinkingMap, root: ThinkNode, actions: list) -> list[str]:
    """应用 Qwen 返回的 actions，返回新增/修改的节点描述列表"""
    changes = []

    for act in actions:
        action = act.get("action")

        if action == "add_domain":
            label = act.get("label", "")
            existing = db.query(ThinkNode).filter(
                ThinkNode.map_id == tmap.id,
                ThinkNode.label == label,
                ThinkNode.type == "domain"
            ).first()
            if existing:
                continue

            domain = ThinkNode(
                id=make_id("n"),
                map_id=tmap.id,
                parent_id=root.id,
                type="domain",
                label=label,
                status="discussing",
            )
            db.add(domain)
            db.flush()
            changes.append(f"+ 📁 {label}")

            # 创建叶子
            for leaf in act.get("leaves", []):
                ln = ThinkNode(
                    id=make_id("n"),
                    map_id=tmap.id,
                    parent_id=domain.id,
                    type="leaf",
                    label=leaf["label"],
                    status="discussing",
                    actionable=leaf.get("actionable", False),
                    discussion=leaf.get("discussion", []),
                )
                db.add(ln)
                changes.append(f"  • {leaf['label']}")

        elif action == "add_leaf":
            parent_label = act.get("parent_label", "")
            parent = db.query(ThinkNode).filter(
                ThinkNode.map_id == tmap.id,
                ThinkNode.label == parent_label
            ).first()
            if not parent:
                continue

            label = act.get("label", "")
            existing = db.query(ThinkNode).filter(
                ThinkNode.map_id == tmap.id,
                ThinkNode.parent_id == parent.id,
                ThinkNode.label == label
            ).first()
            if existing:
                continue

            ln = ThinkNode(
                id=make_id("n"),
                map_id=tmap.id,
                parent_id=parent.id,
                type="leaf",
                label=label,
                status="discussing",
                actionable=act.get("actionable", False),
                discussion=act.get("discussion", []),
            )
            db.add(ln)
            changes.append(f"  • {label}（{parent_label}下）")

        elif action == "update_status":
            label = act.get("label", "")
            new_status = act.get("status", "")
            node = db.query(ThinkNode).filter(
                ThinkNode.map_id == tmap.id,
                ThinkNode.label == label,
            ).first()
            if node and node.status != new_status:
                old_status = node.status
                node.status = new_status
                status_icon = {"confirmed": "✅", "discussing": "❓", "unknown": "❌"}.get(new_status, "")
                changes.append(f"~ {label}: {old_status} → {status_icon} {new_status}")

    if changes:
        tmap.version += 1
        db.commit()

    return changes


def ai_scene_chat_stream(
    scene_id: str,
    user_content: str,
    db: Session,
    complexity: str = "medium",
    history_messages: list[dict] | None = None,
):
    """场景分析流式生成器（两段式真流式）。

    Pass 1: stream=true 流式获取 reply（~0.5s 开始出字，体验同闲聊频道）
    Pass 2: 非流式获取 actions JSON，更新 Thinking Map
    最后追加 Thinking Map 更新提示并 yield _done 信号。

    Yields:
        - str: reply 的 token 文本（来自 Qwen 实时流）
        - dict: 最终产出 {\"_done\": True, \"reply\": \"...\", \"changes\": [...]}
        - dict: 错误时 {\"_error\": True, \"message\": \"...\"}
    """
    tmap = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    if not tmap:
        yield {"_error": True, "message": "⚠️ 未找到 Thinking Map"}
        return

    root = db.query(ThinkNode).filter(
        ThinkNode.map_id == tmap.id,
        ThinkNode.type == "root"
    ).first()
    if not root:
        yield {"_error": True, "message": "⚠️ Thinking Map 缺少根节点"}
        return

    tree_ctx = build_tree_context(db, tmap)

    # ═══ 天气查询注入 ═══
    _weather_ctx = _weather_maybe(user_content)
    _weather_prefix = (_weather_ctx + "\n\n") if _weather_ctx else ""

    # 构建历史上下文（含 role 映射）
    history_api = []
    if history_messages:
        history_api = [
            {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
            for m in history_messages
        ]

    # ═══ Pass 1: 流式获取 reply（真流式，token 即到即发）═══
    reply_messages = [
        {"role": "system", "content": (
            "你是一个专业的AI架构顾问。基于当前Thinking Map分析用户需求，"
            "用Markdown格式给出详细回复。\n"
            "- 充分展开：300-500字\n"
            "- 体现：理解了什么 → 拆解成哪些维度 → 还需要确认什么\n"
            "- 主动追问模糊点\n"
            "- 直接输出回复内容，不要用JSON包裹，不要输出actions"
        )},
        *history_api,
        {"role": "user", "content": f"{_weather_prefix}{tree_ctx}\n\n用户说: {user_content}\n\n请分析并回复。"},
    ]

    full_reply = ""
    for token in _stream_qwen(reply_messages, temperature=0.7):
        if token is None:
            yield {"_error": True, "message": "AI 引擎响应失败"}
            return
        full_reply += token
        yield token

    # ═══ Pass 2: 静默获取 actions 并更新 Thinking Map ═══
    # medium 复杂度生成简化树（3-5节点扁平结构），heavy 可深度展开
    actions_system = (
        "你是Thinking Map更新引擎。基于思维导图和AI回复，输出节点更新actions。\\n\\n"
        "输出纯JSON数组（不要markdown包裹，不要其他文字）：\\n"
        '[{"action":"add_domain","label":"领域名","leaves":[{"label":"叶节点","discussion":["问题?"],"actionable":false}]},'
        '{"action":"add_leaf","parent_label":"父节点","label":"新叶","discussion":[],"actionable":false},'
        '{"action":"update_status","label":"节点名","status":"confirmed|discussing|unknown"}]\\n\\n'
        "规则：不创建重复节点、用户确认/否定时更新status、不需要更新则输出[]"
    )
    if complexity == "medium":
        actions_system += (
            "\\n\\n## Medium 模式规则\\n"
            "本任务为中等复杂度，请生成简化的思维导图：\\n"
            "- 最多 3-5 个 domain 节点（一线展开，不要深度嵌套）\\n"
            "- 每个 domain 直接挂叶子节点，不要再分层\\n"
            "- 所有新创建的叶子节点必须设置 actionable=true（会自动触发执行）\\n"
            "- 聚焦可执行任务，减少分析性节点"
        )
    actions_messages = [
        {"role": "system", "content": actions_system},
        *history_api,
        {"role": "user", "content": (
            f"{tree_ctx}\n\n"
            f"用户说: {user_content}\n\n"
            f"AI回复(摘要): {full_reply[:400]}\n\n"
            f"请输出actions JSON数组。"
        )},
    ]

    actions_result = call_qwen_chat(actions_messages, temperature=0.3)
    actions = []
    changes = []
    if actions_result:
        try:
            text = actions_result.strip()
            # 处理可能的 markdown 包裹
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            actions = json.loads(text)
            if isinstance(actions, dict):
                actions = [actions]
            if isinstance(actions, list):
                changes = apply_actions(db, tmap, root, actions)
        except (json.JSONDecodeError, Exception) as e:
            print(f"[scene actions parse error] {e}")

    # 追加 Thinking Map 更新提示（也走流式）
    if changes:
        summary = "、".join(changes[:3])
        if len(changes) > 3:
            summary += f" 等{len(changes)}项"
        update_note = f"\n\n> 已更新 {summary}"
        for ch in update_note:
            yield ch
        full_reply += update_note

    yield {"_done": True, "reply": full_reply, "changes": changes}


# ═══ v0.4 约束提取 + 复杂度判定 ═══

EXTRACTION_PROMPT = """分析用户消息，完成两项分析任务。

⚠️ 重要：约束提取和复杂度判定是两个独立维度。约束多不等于复杂度高。

## 任务1：提取约束条件
从用户话中提取所有明确的约束（时间、地点、预算、人数、功能需求等）。
每条约束表示一个关键参数，不是"步骤数"——例如"查今天北京的天气"有2条约束（北京、今天），但它仍是单步任务。

同时判断还缺什么关键信息才能完整回答，列出具体追问问题。

## 任务2：复杂度判定
判定标准——用以下**具体例子**作为锚点来判断：

### light（简单）
能用现有工具直接完成的任务。即使涉及调2-3个小工具汇总，也属 light。
特征：不需要拆解成思维导图，直接回答就行。
- ✅ 查询今天北京的天气 → 调用天气工具
- ✅ 我要在这两周内带一家三口去天津玩3天，预算2000块 → 查天气+查景点+算预算，几个小工具汇总
- ✅ 帮我算房贷，贷款100万、利率3.8%、30年期 → 一个公式搞定
- ✅ 推荐几部类似《流浪地球》的电影 → 已有知识，直接回答

### medium（中等）
需要从多个独立维度调研分析，各维度平铺展开（不嵌套），最后汇总。
特征：需要拆成 2-5 个 domain 节点，每个 domain 独立调研后汇总。
- ✅ 比较北京和成都的互联网就业前景，我3年前端经验 → 拆成：薪资水平/房价物价/企业数量/生活成本 分别调研
- ✅ 想开一家奶茶店，帮我做前期调研 → 拆成：品牌加盟/选址策略/设备采购/原料供应链 分别分析
- ✅ 计划一次云南7日游，从深圳出发，预算8000，喜欢自然风光 → 拆成：交通方案/住宿推荐/景点路线/美食攻略

### heavy（复杂）
需要深度拆解，多个层级嵌套（domain 下还有子 domain），跨领域决策。
特征：涉及系统设计、多模块架构、十几到几十个子任务。
- ❌ 查天气/查攻略/做预算 → 这些是 light/medium，不是 heavy
- ✅ 我要做一个在线教育平台 → 用户系统/课程管理/直播系统/支付/推荐/评价...
- ✅ 我要做一个电商APP → 用户端/商户端/管理员/商品/订单/支付/物流/营销...
- ✅ 帮我设计一套企业ERP系统 → 采购/库存/财务/人力/生产/CRM/报表...

## 输出格式（纯JSON）
{
  "complexity": "light|medium|heavy",
  "constraints": [
    {"key": "budget", "value": 2000, "unit": "元", "description": "总预算"},
    {"key": "people", "value": 3, "unit": "人", "description": "一家三口"},
    {"key": "duration", "value": 3, "unit": "天", "description": "游玩天数"}
  ],
  "missing_info": ["具体出发日期？", "住宿偏好？"],
  "constraints_locked": false
}

注意：
- constraints_locked=true 表示信息已够，false 表示还缺信息需要追问
- 不要因为约束多就自动升复杂度——约束数量和步骤数是两回事"""


def extract_and_classify(
    user_content: str,
    existing_complexity: str | None = None,
    existing_constraints: list | None = None,
) -> dict:
    """一次 Qwen 调用完成：约束提取 + 复杂度判定。

    返回:
        {"complexity": "medium", "constraints": [...],
         "missing_info": [...], "constraints_locked": false}

    缓存策略:
    - medium/heavy 场景锁定复杂度不重复判定
    - 已有约束则增量提取（不替换原有）
    """
    # 构建上下文
    ctx = user_content
    if existing_constraints:
        ctx = f"已有约束: {json.dumps(existing_constraints, ensure_ascii=False)}\n\n新的用户消息: {user_content}"

    # 复杂度缓存
    if existing_complexity and existing_complexity != "light":
        # 直接跳过复杂度判定，只做约束提取
        msg = [
            {"role": "system", "content": "提取用户消息中的约束条件。只输出 JSON 数组，不要其他文字。\n格式: [{\"key\":\"...\", \"value\": ..., \"unit\":\"...\", \"description\":\"...\"}]"},
            {"role": "user", "content": ctx},
        ]
        result = call_qwen_chat(msg, temperature=0.3)
        constraints = _safe_json_parse(result, [])
        return {
            "complexity": existing_complexity,
            "constraints": constraints,
            "missing_info": [],
            "constraints_locked": True,
        }

    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": ctx},
    ]
    result = call_qwen_chat(messages, temperature=0.3)
    if result:
        try:
            parsed = _safe_json_parse(result)
            if isinstance(parsed, dict):
                c = parsed.get("complexity", "medium")
                if c not in ("light", "medium", "heavy"):
                    c = "medium"
                return {
                    "complexity": c,
                    "constraints": parsed.get("constraints", []),
                    "missing_info": parsed.get("missing_info", []),
                    "constraints_locked": parsed.get("constraints_locked", len(parsed.get("missing_info", [])) == 0),
                }
        except Exception as e:
            print(f"[extract] 解析失败: {e}, raw: {result[:200]}")
    return {"complexity": "medium", "constraints": [], "missing_info": [], "constraints_locked": True}


def _safe_json_parse(text: str, default=None):
    """安全解析 LLM 输出的 JSON（处理 markdown 包裹等）"""
    if default is None:
        default = {}
    if not text:
        return default
    text = text.strip()
    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{") or part.startswith("["):
                text = part
                break
    return json.loads(text) if text else default


def ai_scene_ask_missing_stream(
    scene_id: str,
    user_content: str,
    missing_info: list[str],
    history_messages: list[dict],
    db: Session,
):
    """约束追问路径：告诉用户还缺什么信息，不建树。

    Yields:
        - str: reply token
        - dict: {"_done": True, "reply": "...", "changes": []}
        - dict: {"_error": True, ...}
    """
    questions = "\n".join(f"- {q}" for q in missing_info)
    system = (
        "你是一个信息收集助手。用户的需求信息不完整，你需要友好地追问。\n"
        "用Markdown格式，简洁清晰，50-100字。"
    )
    # 注入历史上下文（含 role 映射）
    history_api = [
        {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
        for m in history_messages
    ]
    messages = [
        {"role": "system", "content": system},
        *history_api,
        {"role": "user", "content": (
            f"用户说: {user_content}\n\n"
            f"我还需要确认以下信息才能完整答复：\n{questions}\n\n"
            "请用自然的语气问用户这些问题。"
        )},
    ]

    full_reply = ""
    for token in _stream_qwen(messages, temperature=0.7):
        if token is None:
            yield {"_error": True, "message": "AI 引擎响应失败"}
            return
        full_reply += token
        yield token

    yield {"_done": True, "reply": full_reply, "changes": []}


def ai_scene_light_chat_stream(
    scene_id: str,
    user_content: str,
    history_messages: list[dict],
    db: Session,
):
    """轻量路径：Qwen 直答，不建树不更新 Thinking Map。

    适合 light 复杂度的消息：单步骤、查1-2个信息、不需要拆解。

    Yields:
        - str: reply 的 token 文本
        - dict: {"_done": True, "reply": "...", "changes": []}
        - dict: {"_error": True, "message": "..."}
    """
    # ═══ 天气查询注入 ═══
    _weather_ctx = _weather_maybe(user_content)
    _weather_prefix = (_weather_ctx + "\n\n") if _weather_ctx else ""

    # 注入历史上下文（含 role 映射）
    history_api = [
        {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
        for m in history_messages
    ]
    messages = [
        {"role": "system", "content": (
            "你是一个知识丰富的AI助手。直接回答用户问题。\\n"
            "- 用Markdown格式\\n"
            "- 完整、有层次地回复，50-300字\\n"
            "- 不需要拆解任务、不需要创建思维导图\\n"
            "- 直接输出回复内容，不要JSON包裹"
        )},
        *history_api,
        {"role": "user", "content": f"{_weather_prefix}{user_content}"},
    ]

    full_reply = ""
    for token in _stream_qwen(messages, temperature=0.7):
        if token is None:
            yield {"_error": True, "message": "AI 引擎响应失败"}
            return
        full_reply += token
        yield token

    yield {"_done": True, "reply": full_reply, "changes": []}


def ai_process_message(
    scene_id: str,
    user_content: str,
    channel: str = "main",
    db: Session = None,
) -> str:
    """处理用户消息，更新 Thinking Map，返回 AI 回复文本

    channel: 'main' = AI 分析并更新 Thinking Map
             'chat' = 纯聊天，不动图
    """

    # 闲聊模式：只聊天，不碰 Thinking Map
    if channel == "chat":
        result = call_qwen(CHAT_SYSTEM_PROMPT, user_content)
        if result is None:
            return "收到～（AI 引擎暂时响应缓慢，请稍候重试）"
        return result.get("reply", "好的，继续聊～")

    tmap = db.query(ThinkingMap).filter(ThinkingMap.scene_id == scene_id).first()
    if not tmap:
        return "⚠️ 未找到 Thinking Map"

    root = db.query(ThinkNode).filter(
        ThinkNode.map_id == tmap.id,
        ThinkNode.type == "root"
    ).first()
    if not root:
        return "⚠️ Thinking Map 缺少根节点"

    # 构建上下文
    tree_ctx = build_tree_context(db, tmap)
    user_prompt = f"{tree_ctx}\n\n---\n用户说: {user_content}\n\n请分析并返回 JSON。"

    # 调用 Qwen
    result = call_qwen(SYSTEM_PROMPT, user_prompt)

    if result is None:
        # Qwen 调用失败，fallback 到简单回复
        return "收到，正在思考...（AI 引擎暂时响应缓慢，请稍候重试）"

    # 应用 actions
    actions = result.get("actions", [])
    changes = apply_actions(db, tmap, root, actions) if actions else []

    # 构建最终回复 — Qwen 的 reply 本身已包含分析
    reply = result.get("reply", "好的，我已理解。")

    if changes:
        # 简要提示更新内容，不喧宾夺主
        summary = "、".join(changes[:3])
        if len(changes) > 3:
            summary += f" 等{len(changes)}项"
        reply += f"\n\n> 已更新 {summary}"

    return reply


# ═══ Action Map 生成 ═══

ACTION_MAP_GEN_PROMPT = """你是一个资深的行动计划规划专家。你的任务是根据一个需求节点，生成结构化的 Action Map（行动图）。

## Action Map 结构
一个有向流程图，从 START 开始，经过 exec/decision/milestone 节点，到达 END。

## 节点类型
- **start**: 开始节点（必须有且仅有一个）
- **exec**: 执行节点。需要：label(任务描述), timeout(超时秒数，默认300), retry(重试次数), requires_approval(是否需要用户确认), verification(前置验证步骤)
- **decision**: 决策节点。需要：label(判断条件)，后续出边带 label 区分分支
- **milestone**: 里程碑节点。需要：label，auto_continue(bool)
- **end**: 结束节点。需要：outcome("success" 或 "rethink")

## verification 字段
exec 节点可带 verification，格式：
```
{"checks": [{"type": "url", "target": "https://..."}, {"type": "command", "target": "pg_config"}, {"type": "file", "target": "/path/to/file"}]}
```
type 可选：url / command / file。只写真实存在、可验证的 URL 和命令。不确定的不要写。

## 边类型
- flow: 普通流转
- decision: 条件分支（带 label 说明条件）
- fallback: 备选路径（虚线）

## 输出格式（严格 JSON，不要 markdown 包裹）
{
  "title": "行动计划标题",
  "nodes": [
    {"id": "a-start", "type": "start", "label": "START", "order_index": 0, "position_x": 50, "position_y": 100},
    {"id": "a-1", "type": "exec", "label": "具体任务", "timeout": 300, "retry": 2, "requires_approval": false, "verification": {"checks": []}, "order_index": 1, "position_x": 250, "position_y": 100},
    {"id": "a-end", "type": "end", "label": "END", "order_index": 99, "position_x": 1050, "position_y": 100}
  ],
  "edges": [
    {"id": "e-1", "from_node_id": "a-start", "to_node_id": "a-1", "type": "flow"},
    {"id": "e-2", "from_node_id": "a-1", "to_node_id": "a-end", "type": "flow"}
  ]
}

## 布局规则
- 节点 position_x 递增（左→右），每层间隔约 200
- 同层节点 position_y 间隔约 80-100
- decision 分支的多个目标节点放在不同 position_y

## 设计原则
- 3-8 个节点为宜（不含 start/end）
- 先调研再决策再执行（research → decision → exec）
- 每个 exec 节点任务单一明确，Hermes 能一次完成
- 关键分支用 decision 节点，不要都堆在一条线上
- 输出纯 JSON，不要 markdown 代码块包裹"""


def ai_generate_action_map(think_node_id: str, db: Session) -> dict | None:
    """根据 Thinking Map 可执行叶子节点生成 Action Map"""
    node = db.query(ThinkNode).filter(ThinkNode.id == think_node_id).first()
    if not node:
        return None
    if not node.actionable:
        return None

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == node.map_id).first()
    if not tmap:
        return None

    # 构建上下文：节点信息 + 相关讨论 + 父级路径
    tree_ctx = build_tree_context(db, tmap)

    # 找到节点的父级链
    parent_chain = []
    current = node
    while current.parent_id:
        parent = db.query(ThinkNode).filter(ThinkNode.id == current.parent_id).first()
        if parent:
            parent_chain.insert(0, parent.label)
            current = parent
        else:
            break

    context_path = " → ".join(parent_chain) + f" → [{node.label}]" if parent_chain else node.label

    discussions = ""
    discussion_block = ""
    if node.discussion:
        discussions = "\n".join(f"- {d}" for d in node.discussion)
        discussion_block = f"- 待讨论:\n{discussions}"

    user_prompt = f"""## 目标节点
- 路径: {context_path}
- 标签: {node.label}
- 类型: {node.type}
{discussion_block}

## 完整 Thinking Map 上下文
{tree_ctx}

## 任务
请为「{node.label}」生成一个 Action Map。先分析需要哪些研究和决策步骤，再决定执行方案。"""

    raw = call_qwen(ACTION_MAP_GEN_PROMPT, user_prompt)
    if raw is None:
        return None

    # 尝试从文本中提取 JSON
    try:
        if isinstance(raw, dict):
            return raw
        text = str(raw).strip()
        # 去掉可能的 markdown 代码块包裹
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        print(f"[ActionMap gen] JSON parse error: {e}")
        print(f"[ActionMap gen] Raw output: {str(raw)[:500]}")
        return None


# ═══ Hermes 子进程调用 ═══

def call_hermes_stream(prompt: str, model: str = "deepseek-v4-flash", timeout: int = 120):
    """通过 subprocess 调用 hermes CLI，逐行流式 yield stdout 日志。

    用法:
        for event in call_hermes_stream(prompt):
            if event["type"] == "hermes_log":
                print(event["line"])
            elif event["type"] == "result":
                full_text = event["text"]
    """
    cmd = [
        HERMES_BIN, "chat",
        "-q", prompt,
        "--model", model,
        "--yolo",
        "-Q",
    ]

    yield {"type": "status", "line": f"$ hermes chat -q ... --model {model} --yolo"}

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        all_lines: list[str] = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            # 过滤 session_id 行
            if line.startswith("session_id:"):
                continue
            all_lines.append(line)
            yield {"type": "hermes_log", "line": line}

        proc.wait(timeout=timeout)

        if proc.returncode == 0:
            full_text = "\n".join(all_lines)
            yield {"type": "result", "text": full_text}
        else:
            yield {"type": "error", "message": f"Hermes 退出码 {proc.returncode}"}

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        yield {"type": "error", "message": f"Hermes 超时（>{timeout}s）"}
    except FileNotFoundError:
        yield {"type": "error", "message": f"Hermes CLI 未找到: {HERMES_BIN}"}
    except Exception as e:
        yield {"type": "error", "message": f"Hermes 调用异常: {e}"}


HERMES_ACTION_MAP_PROMPT = """你是一个资深的行动计划规划专家。你的任务是根据一个需求节点，生成结构化的 Action Map（行动图）。

## Action Map 结构
一个有向流程图，从 START 开始，经过 exec/decision/milestone 节点，到达 END。

## 节点类型
- **start**: 开始节点（必须有且仅有一个）
- **exec**: 执行节点。需要：label(任务描述), timeout(超时秒数，默认300), retry(重试次数), requires_approval(是否需要用户确认), verification(前置验证步骤，格式如 {"checks":[{"type":"command","target":"..."}]})
- **decision**: 决策节点。需要：label(判断条件)，后续出边带 label 区分分支
- **milestone**: 里程碑节点。需要：label
- **end**: 结束节点。

## verification 字段格式
exec 节点可带 verification：
{"checks": [{"type": "url", "target": "https://..."}, {"type": "command", "target": "pg_config"}, {"type": "file", "target": "/path/to/file"}]}
type 可选：url / command / file。

## 边类型
- flow: 普通流转
- decision: 条件分支（带 label 说明条件）
- fallback: 备选路径

## 输出格式
纯 JSON（不要 markdown 代码块包裹，不要额外解释文字）：
{
  "title": "行动计划标题",
  "nodes": [
    {"id": "a-start", "type": "start", "label": "START", "order_index": 0},
    {"id": "a-1", "type": "exec", "label": "具体任务", "timeout": 300, "retry": 2, "requires_approval": false, "verification": {"checks": []}, "order_index": 1},
    {"id": "a-end", "type": "end", "label": "END", "order_index": 99}
  ],
  "edges": [
    {"id": "e-1", "from_node_id": "a-start", "to_node_id": "a-1", "type": "flow"}
  ]
}

## 设计原则
- 3-8 个执行节点为宜（不含 start/end）
- 先调研再决策再执行（research → decision → exec）
- 每个 exec 节点任务单一明确
- 关键分支用 decision 节点
- 输出纯 JSON，不要 markdown 代码块包裹"""


def call_hermes_action_map(think_node_id: str, db: Session, model: str = "deepseek-v4-flash"):
    """通过 Hermes 子进程生成 Action Map（流式生成器）。

    在 call_hermes_stream 基础上包装：
    - 构建 prompt
    - 透传 hermes_log 日志事件
    - 完成后解析 JSON 并 yield result

    Yields:
        {"type": "hermes_log", "line": "..."}
        {"type": "result", "action_map": {...}}  或 {"type": "error", ...}
    """
    node = db.query(ThinkNode).filter(ThinkNode.id == think_node_id).first()
    if not node:
        yield {"type": "error", "message": f"ThinkNode 不存在: {think_node_id}"}
        return
    if not node.actionable:
        yield {"type": "error", "message": "此节点未标记为可执行"}
        return

    tmap = db.query(ThinkingMap).filter(ThinkingMap.id == node.map_id).first()
    if not tmap:
        yield {"type": "error", "message": "Thinking Map 不存在"}
        return

    # 构建上下文
    tree_ctx = build_tree_context(db, tmap)

    parent_chain = []
    current = node
    while current.parent_id:
        parent = db.query(ThinkNode).filter(ThinkNode.id == current.parent_id).first()
        if parent:
            parent_chain.insert(0, parent.label)
            current = parent
        else:
            break

    context_path = " → ".join(parent_chain) + f" → [{node.label}]" if parent_chain else node.label

    discussion_block = ""
    if node.discussion:
        discussions = "\n".join(f"- {d}" for d in node.discussion)
        discussion_block = f"- 待讨论:\n{discussions}"

    prompt = f"""{HERMES_ACTION_MAP_PROMPT}

## 目标节点
- 路径: {context_path}
- 标签: {node.label}
- 类型: {node.type}
{discussion_block}

## 完整 Thinking Map 上下文
{tree_ctx}

## 任务
请为「{node.label}」生成一个 Action Map。先分析需要哪些研究和决策步骤，再决定执行方案。"""

    full_text = ""
    for event in call_hermes_stream(prompt, model=model):
        if event["type"] in ("hermes_log", "status"):
            yield event
        elif event["type"] == "result":
            full_text = event["text"]
        elif event["type"] == "error":
            yield event
            return

    # 解析 JSON
    if not full_text.strip():
        yield {"type": "error", "message": "Hermes 返回空内容"}
        return

    # 写原始输出到文件以便调试
    import os as _os
    _log_dir = _os.path.expanduser("~/.hermes/logs")
    _os.makedirs(_log_dir, exist_ok=True)
    _log_path = _os.path.join(_log_dir, "zuoshanke_actionmap_raw.log")
    with open(_log_path, "a") as _f:
        import datetime as _dt
        _f.write(f"\n=== {_dt.datetime.now()} | node={think_node_id} ===\n")
        _f.write(full_text + "\n")

    try:
        parsed = _extract_json_from_text(full_text)
        yield {"type": "result", "action_map": parsed}
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[Hermes ActionMap] JSON parse error: {e}")
        print(f"[Hermes ActionMap] Raw output (first 800): {full_text[:800]}")
        yield {"type": "error", "message": f"JSON 解析失败: {e}"}


def _extract_json_from_text(text: str) -> dict:
    """从 Hermes 输出中提取 JSON 对象。

    处理多种情况：
    1. 纯 JSON: {"title":...}
    2. markdown 包裹: ```json {...} ```
    3. 文本前后有推理说明: 一些文字... ```json {...} ``` ...更多文字
    4. 混合格式: 先说明再 JSON
    """
    text = text.strip()
    if not text:
        raise ValueError("空内容")

    # 策略1: 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 策略2: 提取 markdown 代码块中的 JSON
    # 找 ``` ... ``` 之间的内容
    if "```" in text:
        blocks = text.split("```")
        # 取奇数索引的块（在 ``` 之间的内容）
        for i in range(1, len(blocks), 2):
            block = blocks[i].strip()
            # 去掉可能的语言标识（json, javascript 等）
            if block and block[0] not in "{[":
                # 可能有语言标识如 "json\n{..."
                nl = block.find("\n")
                if nl > 0 and nl < 20 and block[nl+1:].strip().startswith(("{", "[")):
                    block = block[nl+1:].strip()
            try:
                result = json.loads(block)
                if isinstance(result, dict) and "nodes" in result:
                    return result
            except json.JSONDecodeError:
                continue

    # 策略3: 找 { ... } 的起始和结束位置
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end+1]
        try:
            result = json.loads(candidate)
            if isinstance(result, dict) and "nodes" in result:
                return result
            # 即使没有 nodes 字段也返回（可能是其他格式的 JSON）
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 策略4: 最后尝试解析整个文本
    return json.loads(text)


# ═══ Action Map 执行引擎 ═══

def call_hermes_execute_node(
    node_id: str,
    node_label: str,
    node_type: str,
    verification: dict | None = None,
    timeout: int = 300,
    model: str = "deepseek-v4-flash",
) -> dict:
    """通过 Hermes 子进程执行单个 Action Map 节点。

    生成器，yield 格式同 call_hermes_stream：
    - {"type": "status", "line": "..."}
    - {"type": "hermes_log", "line": "..."}
    - {"type": "result", "text": "结果摘要"}
    - {"type": "error", "message": "..."}

    Hermes 会获得 terminal + web 工具来真正执行任务。
    """
    # 构建验证要求
    verify_block = ""
    if verification and isinstance(verification, dict):
        checks = verification.get("checks", [])
        if checks:
            verify_block = "\n## 验证要求\n完成后请验证：\n"
            for c in checks:
                if isinstance(c, dict):
                    t = c.get("type", "cmd")
                    target = c.get("target", "")
                    if t == "url":
                        verify_block += f"- 访问 {target} 确认可访问\n"
                    elif t == "command":
                        verify_block += f"- 运行 `{target}` 确认成功\n"
                    elif t == "file":
                        verify_block += f"- 确认文件 `{target}` 存在且内容正确\n"
                elif isinstance(c, str):
                    verify_block += f"- {c}\n"

    prompt = f"""你是一个任务执行引擎。请完成以下单一明确的任务。

## 任务
{node_label}

## 任务类型
{node_type}
{verify_block}
## 沙箱约束
- 你的工作目录是 `tools/`，所有创建的文件必须在 tools/ 目录或其子目录下
- **严禁**修改或覆盖 `backend/` 目录下的文件（main.py, models.py, database.py 等核心代码）
- 如果你生成了可复用的工具模块，放到 `tools/` 下，不要注入到 backend/
- 写文件前先确认路径在 tools/ 下

## 工具复用规则（重要）
**先查再用**：执行前先读取 `tools/registry.json`，检查是否已有可复用工具。
- 如果已有工具能完成任务 → **直接使用**，不要新建
- 只有找不到合适工具时才新建

**新建工具质量要求**（如果必须新建）：
1. 工具名用**能力命名**（query_weather 而非 tianjin_weather）
2. 所有可变数据作为函数参数传入，**严禁硬编码**地名/价格等
3. 单一职责：一个工具只做一类事
4. 异常处理完整（网络超时、API 限制、空数据）
5. 输出中文描述，非 raw JSON

## 要求
- 使用可用的工具（terminal、web）完成任务
- 完成后用一句话总结结果（格式：✓ 已完成: 具体做了什么）
- 如果遇到错误，总结失败原因（格式：✗ 失败: 原因）
- 保持简洁，不要过度展开

## 输出格式规范
如果结果包含多条推荐/查询/搜索结果，每条必须包含：
- **source_url** — 原始来源链接（可直接跳转的 URL）
- **summary** — 1-2 句概要说明（如「个人一手，4S保养」）
- **tags** — 标签数组，让用户一眼识别关键特点（如 ["年份新","里程低"]）
格式示例：
- [车源1](链接) — 个人一手，4S保养 | `年份新` `里程低`
- [车源2](链接) — 商家车源，右后门补漆 | `里程低` `价格可议`"""

    # 沙箱工作目录
    import os as _os
    _sandbox = _os.path.expanduser("~/zuoshanke/tools")
    _os.makedirs(_sandbox, exist_ok=True)

    # 执行节点时需要 terminal 和 web 工具
    cmd = [
        HERMES_BIN, "chat",
        "-q", prompt,
        "--model", model,
        "--toolsets", "terminal,web",
        "--yolo",
        "-Q",
    ]

    yield {"type": "status", "line": f"$ hermes execute (sandbox: tools/): {node_label[:60]}..."}

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=_sandbox,
        )

        all_lines: list[str] = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("session_id:"):
                continue
            all_lines.append(line)
            yield {"type": "hermes_log", "line": line}

        proc.wait(timeout=timeout)

        if proc.returncode == 0:
            full_text = "\n".join(all_lines)
            # 提取最后几行作为结果摘要
            lines = all_lines[-5:] if len(all_lines) > 5 else all_lines
            summary = "\n".join(lines)
            yield {"type": "result", "text": summary}
        else:
            yield {"type": "error", "message": f"Hermes 退出码 {proc.returncode}"}

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        yield {"type": "error", "message": f"执行超时（>{timeout}s）"}
    except FileNotFoundError:
        yield {"type": "error", "message": f"Hermes CLI 未找到: {HERMES_BIN}"}
    except Exception as e:
        yield {"type": "error", "message": f"执行异常: {e}"}


# ═══ 工具自文档化 ═══

def call_hermes_generate_skill(tool_path: str, model: str = "deepseek-v4-flash") -> str | None:
    """读取工具代码，调 Hermes 生成 SKILL.md 使用说明书。

    Args:
        tool_path: 工具文件的绝对路径

    Returns:
        SKILL.md markdown 内容，失败返回 None
    """
    import os as _os

    if not _os.path.isfile(tool_path):
        print(f"[ToolDocs] 文件不存在: {tool_path}")
        return None

    try:
        with open(tool_path, "r") as f:
            code = f.read()
    except Exception as e:
        print(f"[ToolDocs] 读取失败: {e}")
        return None

    tool_name = _os.path.splitext(_os.path.basename(tool_path))[0]

    prompt = f"""你是一个技术文档专家。请为以下工具代码生成使用说明书（SKILL.md 格式）。

## 工具名称
{tool_name}

## 工具代码
```
{code[:6000]}
```

## 输出格式
使用 YAML frontmatter + markdown body：

---
name: {tool_name}
description: 一句话描述这个工具的功能
category: tools
---

# {tool_name}

## 概述
简要说明工具的用途和使用场景。

## 安装/依赖
如果有外部依赖，列出。

## API / 接口
列出所有函数/端点，标注入参、返回值、示例。

## 使用示例
至少一个可运行的示例（bash 命令或 Python 代码）。

## 注意事项
已知限制、边界条件。

输出纯 markdown，不要用代码块包裹整个文档。"""

    # 文档生成不给任何工具，纯推理输出
    import os as __os
    cmd = [
        HERMES_BIN, "chat",
        "-q", prompt,
        "--model", model,
        "--toolsets", "",
        "--yolo",
        "-Q",
    ]

    full_text = ""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        all_lines = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("session_id:"):
                continue
            all_lines.append(line)
        proc.wait(timeout=120)
        if proc.returncode == 0:
            full_text = "\n".join(all_lines)
        else:
            print(f"[ToolDocs] Hermes exit code: {proc.returncode}")
            return None
    except Exception as e:
        print(f"[ToolDocs] Hermes error: {e}")
        return None

    return full_text.strip() if full_text.strip() else None


def scan_and_document_tools(
    action_map_id: str,
    tools_dir: str = "~/zuoshanke/tools",
) -> list[dict]:
    """扫描 tools/ 目录，为没有 SKILL.md 的工具自动生成说明书并注册。

    Returns:
        新增工具列表 [{name, path, skill_path}]
    """
    import os as _os
    import json as _json

    _tools_dir = _os.path.expanduser(tools_dir)
    registry_path = _os.path.join(_tools_dir, "registry.json")

    # 加载现有注册表
    registry = {"tools": []}
    if _os.path.isfile(registry_path):
        try:
            with open(registry_path, "r") as f:
                registry = _json.load(f)
        except Exception:
            registry = {"tools": []}

    registered_names = {t["name"] for t in registry.get("tools", [])}

    new_tools = []

    for fname in sorted(_os.listdir(_tools_dir)):
        fpath = _os.path.join(_tools_dir, fname)

        # 跳过目录、非 py 文件、注册表本身
        if not _os.path.isfile(fpath):
            continue
        if not fname.endswith(".py"):
            continue
        if fname == "__init__.py":
            continue

        tool_name = fname[:-3]  # 去掉 .py

        # 已有说明书 → 跳过
        skill_dir = _os.path.join(_tools_dir, tool_name)
        skill_path = _os.path.join(skill_dir, "SKILL.md")
        if _os.path.isfile(skill_path):
            continue

        # 已在注册表 → 跳过
        if tool_name in registered_names:
            continue

        # 生成说明书
        print(f"[ToolDocs] 生成文档: {tool_name}")
        skill_content = call_hermes_generate_skill(fpath)

        if not skill_content:
            print(f"[ToolDocs] 文档生成失败: {tool_name}")
            continue

        # 保存说明书
        _os.makedirs(skill_dir, exist_ok=True)
        with open(skill_path, "w") as f:
            f.write(skill_content)

        # 注册
        description = ""
        if skill_content.startswith("---"):
            parts = skill_content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip('"').strip("'")
                        break

        tool_entry = {
            "name": tool_name,
            "path": f"{tool_name}/{fname}",
            "skill_path": f"{tool_name}/SKILL.md",
            "description": description,
            "created_from": action_map_id,
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }
        registry["tools"].append(tool_entry)
        new_tools.append(tool_entry)

        print(f"[ToolDocs] ✓ {tool_name} → {skill_path}")

    # 保存注册表
    if new_tools:
        with open(registry_path, "w") as f:
            _json.dump(registry, f, ensure_ascii=False, indent=2)

    return new_tools
