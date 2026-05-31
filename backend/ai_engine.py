"""AI 引擎 — 调用 Qwen3.5-9B 处理用户输入，更新 Thinking Map"""
import json
import os
import subprocess
from typing import Optional
import requests
from sqlalchemy.orm import Session
from models import ThinkingMap, ThinkNode
from utils import make_id
from agent_core.context_builder import _build_memory_block
from logger import get_logger as _get_logger
from secret_redact import redact, redact_headers
_ai_log = _get_logger("ai_engine")

# ── 天气查询（直接调 weather.py） ──
def _weather_maybe(user_text: str) -> Optional[str]:
    """检测用户消息中的天气意图，调 weather.maybe_weather_context 获取实时数据"""
    import sys as _sys, os as _os
    try:
        from config.paths import TOOLS_DIR
        if TOOLS_DIR not in _sys.path:
            _sys.path.insert(0, TOOLS_DIR)
        from weather import maybe_weather_context
        return maybe_weather_context(user_text)
    except Exception:
        return None


from config.urls import QWEN_API, DEEPSEEK_BASE_URL

# ── DeepSeek 云 API 配置（读取环境变量） ──
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL_MAP = {
    "flash": "deepseek-chat",        # deepseek-v4-flash → 实际模型名
    "pro": "deepseek-chat",          # deepseek-v4-pro → 实际模型名（当前同 flash）
    "deepseek-v4-flash": "deepseek-chat",
    "deepseek-v4-pro": "deepseek-chat",
}

# ── 系统设置缓存 ──
_settings_cache: Optional[dict] = None

def invalidate_settings_cache():
    """外部调用来刷新缓存（PATCH 设置后调用）"""
    global _settings_cache
    _settings_cache = None

def get_settings(route: str = "channel") -> dict:
    """读取指定路由的设置（带内存缓存）

    Args:
        route: routing 中的 key（channel/scene/extraction/medium/heavy）

    Returns:
        {temperature: float, max_tokens: int, repeat_penalty: float, model: str, provider: str, provider_id: str, model_id: str}
        异常时返回默认值（不影响聊天功能）
    """
    global _settings_cache
    if _settings_cache is None:
        try:
            from database import SessionLocal
            from models import Setting, SETTINGS_ID, DEFAULT_ROUTING
            db = SessionLocal()
            try:
                s = db.query(Setting).filter(Setting.id == SETTINGS_ID).first()
                _settings_cache = s.routing if s else DEFAULT_ROUTING
                # 🆕 自动补全 provider_id/model_id（兼容旧数据）
                if isinstance(_settings_cache, dict):
                    try:
                        from models import AiProvider, AiModel
                        for cfg in _settings_cache.values():
                            if isinstance(cfg, dict) and (not cfg.get("provider_id") or not cfg.get("model_id")):
                                p = db.query(AiProvider).filter(
                                    (AiProvider.name.ilike(cfg.get("provider", ""))) |
                                    (AiProvider.name.ilike(f"%{cfg.get('provider', '')}%"))
                                ).first()
                                if not p:
                                    p = db.query(AiProvider).filter(
                                        AiProvider.provider_type == ("local" if cfg.get("provider") == "local" else "openai-compatible")
                                    ).first()
                                if p:
                                    cfg["provider_id"] = p.id
                                    m = db.query(AiModel).filter(
                                        AiModel.provider_id == p.id,
                                        AiModel.name.ilike(cfg.get("model", ""))
                                    ).first()
                                    if m:
                                        cfg["model_id"] = m.id
                    except Exception:
                        pass
            finally:
                db.close()
        except Exception:
            from models import DEFAULT_ROUTING
            _settings_cache = DEFAULT_ROUTING
    return _settings_cache.get(route, _settings_cache.get("channel", {
        "temperature": 0.7, "max_tokens": 4096, "repeat_penalty": 1.0,
        "model": "qwen3.5-9b", "provider": "local",
    }))


# ═══ 🆕 泛化 LLM 调用 ═══

def _resolve_llm(route_cfg: dict) -> tuple:
    """从路由配置解析出 LLM 调用的连接信息

    Args:
        route_cfg: get_settings() 返回的路由配置

    Returns:
        (base_url: str, api_key: str, model_name: str)
        失败时基于字符串 fallback
    """
    provider_id = route_cfg.get("provider_id", "")
    model_id = route_cfg.get("model_id", "")
    fallback_provider = route_cfg.get("provider", "local")
    fallback_model = route_cfg.get("model", "qwen3.5-9b")

    # 优先从 DB 查找
    if provider_id and model_id:
        try:
            from database import SessionLocal
            from models import AiProvider, AiModel
            db = SessionLocal()
            try:
                p = db.query(AiProvider).filter(AiProvider.id == provider_id).first()
                m = db.query(AiModel).filter(AiModel.id == model_id).first()
                if p and m:
                    base_url = p.base_url.rstrip("/")
                    # 标准化：移除某些配置已含的 /v1 后缀（llama-server 等）
                    if base_url.endswith("/v1"):
                        base_url = base_url[:-3]
                    api_key = p.api_key or ""
                    model_name = m.name
                    return base_url, api_key, model_name
            finally:
                db.close()
        except Exception:
            pass

    # Fallback: 字符串方式
    if fallback_provider == "deepseek":
        return DEEPSEEK_BASE_URL.rstrip("/"), DEEPSEEK_API_KEY, DEEPSEEK_MODEL_MAP.get(fallback_model, "deepseek-chat")
    else:
        fb_url = QWEN_API.rstrip("/")
        if fb_url.endswith("/v1"):
            fb_url = fb_url[:-3]
        return fb_url, "", fallback_model


def call_llm(messages: list[dict], route_cfg: dict, temperature: float = 0.7,
             max_tokens: Optional[int] = None, stream: bool = False) -> Optional[str]:
    """泛化 LLM 调用 — 通过 provider_id/model_id 自动查找连接信息

    Args:
        messages: OpenAI 格式消息列表
        route_cfg: 路由配置（含 provider_id/model_id）
        temperature: 温度
        max_tokens: 最大 Token（None = 从 route_cfg 读取）
        stream: 是否流式（暂只支持非流式返回）

    Returns:
        回复文本，失败返回 None
    """
    base_url, api_key, model_name = _resolve_llm(route_cfg)
    if not base_url:
        _ai_log.error(f"[call_llm] 无法解析 provider，route_cfg={route_cfg}")
        return None

    # ── Prompt Caching: 检测 Claude 模型自动注入 cache_control ──
    from agent_core.prompt_caching import inject_prompt_cache_markers
    cached_messages = inject_prompt_cache_markers(messages, model_name=model_name)

    mt = max_tokens if max_tokens is not None else route_cfg.get("max_tokens", 8192)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_name,
        "messages": cached_messages,
        "max_tokens": mt,
        "temperature": temperature,
    }

    _ai_log.debug(f"[call_llm] {base_url} {model_name} headers={redact_headers(headers)}")

    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        _ai_log.error(f"[call_llm] {base_url} {model_name}: {e}")
        return None


def call_llm_stream(messages: list[dict], route_cfg: dict, temperature: float = 0.7,
                    max_tokens: Optional[int] = None):
    """泛化 LLM 流式调用，逐 token yield

    Args:
        messages: OpenAI 格式消息列表
        route_cfg: 路由配置
        temperature: 温度
        max_tokens: 最大 Token

    Yields:
        str: token 文本
        None: 出错
    """
    base_url, api_key, model_name = _resolve_llm(route_cfg)
    if not base_url:
        _ai_log.error(f"[call_llm_stream] 无法解析 provider，route_cfg={route_cfg}")
        yield None
        return

    # ── Prompt Caching: 检测 Claude 模型自动注入 cache_control ──
    from agent_core.prompt_caching import inject_prompt_cache_markers
    cached_messages = inject_prompt_cache_markers(messages, model_name=model_name)

    mt = max_tokens if max_tokens is not None else route_cfg.get("max_tokens", 8192)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_name,
        "messages": cached_messages,
        "max_tokens": mt,
        "temperature": temperature,
        "stream": True,
    }

    _ai_log.debug(f"[call_llm_stream] {base_url} {model_name} headers={redact_headers(headers)}")

    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=300,
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
        _ai_log.error(f"[call_llm_stream] {base_url} {model_name}: {e}")
        yield None


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
    db=None,
    attachments: Optional[list[dict]] = None,
) -> str:
    """频道闲聊：纯对话"""
    api_messages = _build_channel_messages(messages, is_default, db=db)

    # 🆕 处理附件：如果模型支持多模态，将最后一条用户消息的 content 转为数组格式
    if attachments:
        route_cfg = get_settings("channel")
        from agent_core.multimodal import format_message_content
        for i in range(len(api_messages) - 1, -1, -1):
            if api_messages[i].get("role") in ("user", "assistant"):
                api_messages[i]["content"] = format_message_content(
                    api_messages[i]["content"], attachments, route_cfg
                )
                break

    # ── 注入实时数据（天气等）──
    if messages and isinstance(messages[-1], dict):
        user_text = messages[-1].get("content", "")
        weather_ctx = _weather_maybe(user_text)
        if weather_ctx:
            # llama.cpp/Jinja 不允许多个 system 消息块，追加到第一个 system prompt 里
            api_messages[0] = {
                "role": "system",
                "content": api_messages[0]["content"]
                    + f"\n\n【实时数据，请基于此回答，不要编造】\n{weather_ctx}"
            }

    result = call_qwen_chat(api_messages, route="channel")
    if result is None:
        return "收到～（AI 引擎暂时响应缓慢，请稍候重试）"
    return result


def _build_channel_messages(messages: list[dict], is_default: bool = False,
                            db=None) -> list[dict]:
    """构建频道闲聊的 API 消息列表（含 system prompt + role 映射）

    优先级: DB 用户自定义 → config/prompts.json 后台配置
    """
    from prompts import get_channel_prompt
    base_prompt = get_channel_prompt(is_default, db)

    system_content = (
        base_prompt
        + "\n\n重要——回复末尾必须加一行标签表达此刻心情："
          "\n[心情: 情绪词] 内心独白（10-20字口语）"
          "\n情绪词: idle|watching|amused|annoyed|thinking"
          "\n如：[心情: amused] 哈哈哈清泉又讲冷笑话了😂"
    )

    api_messages = [
        {"role": "system", "content": system_content},
    ]
    api_messages += [
        {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
        for m in messages
    ]
    return api_messages


def ai_channel_chat_stream(messages: list[dict], is_default: bool = False,
                           db=None, attachments: Optional[list[dict]] = None):
    """频道闲聊：流式生成器，逐 token yield

    支持附件（图片/文档）多模态输入。

    Yields:
        str: 单个 token 文本
        None: 发生错误时 yield None（调用方应停止迭代）
    """
    api_messages = _build_channel_messages(messages, is_default, db=db)
    route_cfg = get_settings("channel")

    # 🆕 处理附件：如果模型支持多模态，将最后一条用户消息的 content 转为数组格式
    if attachments:
        from agent_core.multimodal import format_message_content
        for i in range(len(api_messages) - 1, -1, -1):
            if api_messages[i].get("role") in ("user", "assistant"):
                api_messages[i]["content"] = format_message_content(
                    api_messages[i]["content"], attachments, route_cfg
                )
                break

    yield from call_llm_stream(api_messages, route_cfg, temperature=route_cfg.get("temperature", 0.7))


def call_qwen_chat(messages: list[dict], temperature: Optional[float] = None, route: str = "scene") -> Optional[str]:
    """调用 LLM（非流式），返回完整回复文本

    通过 provider_id/model_id 自动路由到正确的 Provider。

    Args:
        messages: 消息列表
        temperature: 温度（None = 从 settings 读取 route 对应的值）
        route: 路由名称（channel/scene/extraction/medium/heavy），用于查设置
    """
    route_cfg = get_settings(route)
    temp = temperature if temperature is not None else route_cfg.get("temperature", 0.7)
    return call_llm(messages, route_cfg, temperature=temp)


# ── web_search 兜底判断（模型驱动） ──

def should_web_search(text: str) -> bool:
    """用 Qwen 判断用户消息是否需要搜索互联网

    返回 True = 需要搜，False = 不需要搜（闲聊/追问/元问题等）。
    极端情况调用失败时保守返回 False（不搜）。
    """
    if not text or not text.strip():
        return False
    t = text.strip()

    # 极简预过滤：太短或纯语气词，省一次模型调用
    if len(t) < 4:
        return False
    stopwords = {"嗯","哦","好","行","是","不","嗨","哈","嘿",
                 "好的","好吧","是的","不是","谢谢","你好","再见"}
    if t in stopwords:
        return False

    # 调 Qwen 做二分类
    prompt = (
        "判断以下用户消息是否需要搜索互联网才能回答。\n"
        "只需要回复\"是\"或\"否\"，不要其他内容。\n\n"
        f"消息：{t}\n\n"
        "回复："
    )
    try:
        result = call_qwen_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            route="extraction",
        )
        if result is None:
            return False
        result = result.strip()
        _ai_log.debug(f"[should_web_search] \"{t[:30]}...\" → {result}")
        return result.startswith("是")
    except Exception as e:
        _ai_log.warning(f"[should_web_search] error: {e}")
        return False


def _stream_qwen(messages: list[dict], temperature: Optional[float] = None, route: str = "scene"):
    """通用流式调用，逐 token yield。

    通过 provider_id/model_id 自动路由到正确的 Provider。

    Args:
        messages: 消息列表
        temperature: 温度（None = 从 settings 读取 route 对应的值）
        route: 路由名称

    Yields:
        str: token 文本
        None: 出错时 yield None（调用方应停止迭代）
    """
    route_cfg = get_settings(route)
    temp = temperature if temperature is not None else route_cfg.get("temperature", 0.7)
    yield from call_llm_stream(messages, route_cfg, temperature=temp)


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


def call_qwen(system_prompt: str, user_prompt: str) -> Optional[dict]:
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
        _ai_log.error(f"[Qwen error] {e}")
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
    existing_complexity: Optional[str] = None,
    existing_constraints: Optional[list] = None,
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
            _ai_log.warning(f"[extract] 解析失败: {e}, raw: {result[:200]}")
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


def ai_generate_action_map(think_node_id: str, db: Session) -> Optional[dict]:
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
        _ai_log.error(f"[ActionMap gen] JSON parse error: {e}")
        _ai_log.error(f"[ActionMap gen] Raw output: {str(raw)[:500]}")
        return None


# ═══════════════════════════════════════════
#  DeepSeek 云 API 直调（替换 Hermes 子进程）
# ═══════════════════════════════════════════

def call_deepseek_chat(
    messages: list[dict],
    model: str = "flash",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    route: str = "medium",
) -> Optional[str]:
    """直调 DeepSeek API（非流式），返回完整回复文本

    Args:
        messages: OpenAI 格式的消息列表
        model: 'flash' 或 'pro'
        temperature: 温度
        max_tokens: 最大 token 数
        route: 路由名（用于读取 settings 覆盖）

    Returns:
        完整回复文本，失败返回 None
    """
    # 从 settings 读取覆盖参数
    try:
        route_cfg = get_settings(route)
        model_key = route_cfg.get("model", f"deepseek-v4-{model}")
        _model = DEEPSEEK_MODEL_MAP.get(model, "deepseek-chat")
        temp = route_cfg.get("temperature", temperature)
        mt = route_cfg.get("max_tokens", max_tokens)
    except Exception:
        _model = DEEPSEEK_MODEL_MAP.get(model, "deepseek-chat")
        temp = temperature
        mt = max_tokens

    if not DEEPSEEK_API_KEY:
        _ai_log.warning("[DeepSeek] API key 未配置")
        return None

    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": _model,
                "messages": messages,
                "temperature": temp,
                "max_tokens": mt,
            },
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        _ai_log.error(f"[DeepSeek chat] {e}")
        return None


def propose_tool(query: str, ai_reply: str, tool_was_used: bool = False) -> dict:
    """轻量判断是否需要创建新工具

    Args:
        query: 用户原始查询
        ai_reply: AI 的回复内容
        tool_was_used: 本轮是否使用了工具

    Returns:
        {"need_tool": false} 或
        {"need_tool": true, "tool_name": "...", "reason": "...", "complexity": "simple"}
    """
    # 如果已经用了工具，且回复充分，大概率不需要新工具
    if tool_was_used and len(ai_reply) > 50:
        return {"need_tool": False}

    try:
        messages = [
            {"role": "system", "content": TOOL_PROPOSAL_JUDGE_PROMPT},
            {"role": "user", "content": (
                f"## 用户查询\n{query}\n\n"
                f"## AI 回复\n{ai_reply[:500]}\n\n"
                f"## 工具使用情况\n{'已使用 web_search 搜索' if tool_was_used else '未使用任何工具'}\n\n"
                f"请判断是否需要创建新工具。"
            )},
        ]
        result = call_qwen_chat(messages, temperature=0.1, route="extraction")
        if result:
            import json as _json
            parsed = _json.loads(result)
            if isinstance(parsed, dict) and parsed.get("need_tool"):
                return {
                    "need_tool": True,
                    "tool_name": parsed.get("tool_name", "unknown"),
                    "reason": parsed.get("reason", ""),
                    "complexity": parsed.get("complexity", "simple"),
                }
        return {"need_tool": False}
    except Exception as e:
        _ai_log.error(f"[tool_proposal] 判断失败: {e}")
        return {"need_tool": False}
