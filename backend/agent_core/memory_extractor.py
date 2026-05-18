"""记忆提取器 — LLM 驱动的跨会话记忆提取

架构：
  双通道提取：
    ① 快速通道（关键词匹配）：用户说"记住""很重要" → 秒存，不等 LLM
    ② LLM 通道：对话结束后，调用配罝的轻量模型做结构化提取

可配置项（通过 settings → routing → extraction）：
  - model: 模型名（默认 qwen3.5-9b）
  - provider: local | deepseek | openai 等
  - temperature: 0.1（默认，低温度保证一致性）
  - max_tokens: 1024
  - enabled: 是否启用（后续可在 features 中添加）

如果用户没有部署本地模型，可在设置中将 extraction 的路由指向远程模型，
或关闭此功能（仅保留快速通道）。
"""

import json
import requests
import re
from typing import Optional

from models import AgentMemory
from agent_core.memory_manager import MemoryManager
from logger import get_logger as _get_logger
from config.urls import QWEN_API
from config.matching_rules import MEMORY_FAST_TRIGGERS as FAST_TRIGGERS, TOPIC_DOMAINS
_log = _get_logger("memory_extractor")

# 快速通道模式 → topic 映射
_FAST_TOPIC_MAP = {
    "preference": ["我喜欢", "我爱", "我偏爱", "我倾向于", "偏好", "偏爱"],
    "personal_info": ["我叫", "我是", "我的名字叫", "名字叫", "英文名",
                      "我住在", "我居住在", "我家在", "居住在"],
    "habit": ["我习惯", "我通常", "我一般", "我总是", "我经常"],
}

# ── 提取器的 System Prompt ──
EXTRACTOR_SYSTEM_PROMPT = """你是记忆提取专家，负责从对话中提炼出值得长期记住的信息。

## 提取原则
只提取以下类型的信息（对未来的对话有价值）：
- 用户身份：姓名、年龄、职业、所在地、联系方式
- 用户偏好：喜欢的/不喜欢的风格、颜色、温度、食物、话题
- 用户习惯：常用工作方式、工具偏好、作息规律
- 项目约束：交付要求、技术限制、业务规则、架构决策
- 重要事实：需要长期记住的上下文、人物关系、关键日期
- 纠正信息：用户纠正过的错误认知

不要提取以下内容（属于一次性对话）：
- 日常问答（"今天天气怎么样"、"现在几点"）
- 工具调用结果（API返回的数据、查询结果）
- 闲聊寒暄（"吃了没"、"你好"）
- 临时状态（当前正在做的事）
- AI 的回复内容本身

## 输出格式
严格返回 JSON 数组，不要任何其他文字：
[
  {
    "action": "create | reinforce | ignore",
    "key": "唯一标识，英文小写，用下划线连接（如 user_name、preference_color）",
    "content": "记忆内容，清晰完整的陈述句",
    "category": "user",
    "tags": ["标签1", "标签2"],
    "topic": "personal_info | preference | habit | work | entertainment | food | travel | tech | shopping | health | education | general",
    "confidence": 0.0-1.0
  }
]

action 含义：
- create: 创建新记忆
- reinforce: 强化已有记忆（当新对话确认/补充了已有记忆时）
- ignore: 本条不处理（confidence < 0.6 时使用）

topic 含义：该记忆属于哪个话题域。用来在注入时做话题匹配，避免问电影时把"喜欢修仙"塞进来。
- personal_info: 姓名/年龄/职业/所在地等身份信息
- preference: 喜好、偏好
- habit: 习惯、日常作息
- entertainment: 娱乐、影视、游戏、小说、音乐
- food: 饮食、餐饮、烹饪
- travel: 旅游、出行、景点
- tech: 技术、编程、工具
- shopping: 购物、消费
- health: 健康、运动、养生
- education: 学习、课程、教学
- work: 工作、项目、技术约束
- general: 不属于以上任何分类时用这个兜底

confidence 含义：
- ≥0.9: 非常确定，直接入库
- 0.7-0.9: 较确定，标记低权重入库
- <0.7: 不确定，忽略（用 ignore）

## 约束
- 单次提取最多返回 3 条
- key 要稳定可复用（同类型信息用相同 key）
- content 要用简洁陈述句，20字以内，去掉冗余修饰词
  ✅ "用户喜欢火锅"
  ✅ "用户习惯早起写代码"
  ❌ "用户明确表示比较喜欢吃火锅。"
  ❌ "用户习惯早起写代码，此时效率最高。"
- 不要编造信息，不确定就 confidence 打低或 ignore
"""


class MemoryExtractor:
    """记忆提取器"""

    def __init__(self, db, route_cfg: Optional[dict] = None):
        self.db = db
        self.mm = MemoryManager(db)
        self.route_cfg = route_cfg or self._load_route_cfg()
        self.endpoint = self.route_cfg.get("_endpoint", QWEN_API)
        self.model = self.route_cfg.get("model", "qwen3.5-9b")
        self.temperature = self.route_cfg.get("temperature", 0.1)
        self.max_tokens = self.route_cfg.get("max_tokens", 1024)

    def _load_route_cfg(self) -> dict:
        """从 settings 加载 extraction 路由配置，支持环境变量覆盖"""
        cfg = {"temperature": 0.1, "max_tokens": 1024,
               "model": "qwen3.5-9b", "provider": "local"}
        try:
            from ai_engine import get_settings
            cfg.update(get_settings("extraction"))
        except Exception:
            pass
        # 环境变量覆盖端点
        import os as _os
        env_endpoint = _os.environ.get("MEMORY_EXTRACTOR_ENDPOINT")
        if env_endpoint:
            cfg["_endpoint"] = env_endpoint
        return cfg

    # ── 快速通道：关键词匹配 ──

    def _fast_path(self, user_content: str) -> list[dict]:
        """快速通道：检测显式"记住"信号，秒存不等 LLM

        Returns:
            已执行的记忆操作列表
        """
        results = []
        for signal in FAST_TRIGGERS:
            if signal in user_content:
                # 尝试从该句提取事实
                extracted = self.mm._extract_fact(user_content)
                if extracted:
                    key, content = extracted
                    # 推断 topic：根据匹配的模式确定话题域
                    topic = self._infer_topic_from_pattern(user_content, key)
                    tags = [topic]

                    existing = self.mm.get(key)
                    if existing:
                        self.mm.mark_explicit(key)
                        self.mm.update(key, content=content, tags=tags)
                        results.append({"action": "reinforce_pin",
                                        "key": key, "content": content, "boost": 3.0,
                                        "source": "fast_path", "topic": topic})
                    else:
                        self.mm.add("user", key, content, tags=tags,
                                    source="llm", base_weight=4)
                        self.mm.mark_explicit(key)
                        results.append({"action": "create",
                                        "key": key, "content": content, "boost": 3.0,
                                        "source": "fast_path", "topic": topic})
                # 至少处理一个信号，避免重复
                break
        return results

    def _infer_topic_from_pattern(self, text: str, key: str) -> str:
        """根据提取的关键词和模式推断话题域"""
        # 先看 key 前缀
        key_prefix_map = {
            "name": "personal_info",
            "city": "personal_info",
            "preference": "preference",
            "habit": "habit",
            "my_": "personal_info",
        }
        for prefix, topic in key_prefix_map.items():
            if key.startswith(prefix):
                return topic
        # 再看文本中的关键词
        for topic, triggers in _FAST_TOPIC_MAP.items():
            for t in triggers:
                if t in text:
                    return topic
        return "general"

    # ── LLM 通道 ──

    def _build_extract_messages(self, conversation: list[dict]) -> list[dict]:
        """构建提取用的 LLM 消息

        Args:
            conversation: 最近的对话消息 [{"role": ..., "content": ...}]

        Returns:
            [system, user] 格式的消息列表
        """
        # 压缩对话：保留最近的 3 轮（6 条消息）
        recent = conversation[-6:] if len(conversation) > 6 else conversation

        # 格式化对话文本
        dialogue_lines = []
        for m in recent:
            role_label = "用户" if m.get("role") in ("user", "human") else "AI"
            content = m.get("content", "").strip()
            if content:
                # 截断长内容
                if len(content) > 500:
                    content = content[:500] + "..."
                dialogue_lines.append(f"{role_label}: {content}")

        dialogue_text = "\n\n".join(dialogue_lines)

        user_prompt = f"""请分析以下对话，提取值得长期记住的信息：

--- 对话开始 ---
{dialogue_text}
--- 对话结束 ---

返回 JSON 数组，只输出包含有效提取项的数组。"""
        return [
            {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    def _call_extraction_llm(self, messages: list[dict]) -> Optional[str]:
        """调用 LLM 进行提取

        Args:
            messages: LLM 消息列表

        Returns:
            LLM 返回的文本（预期是 JSON），失败返回 None
        """
        try:
            resp = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            _log.error(f"[memory_extractor] LLM call failed: {e}")
            return None

    def _parse_response(self, text: Optional[str]) -> list[dict]:
        """解析 LLM 返回的 JSON

        Args:
            text: LLM 返回的原始文本

        Returns:
            解析后的操作列表，失败返回 []
        """
        if not text:
            return []

        # 尝试提取 JSON 数组（模型可能用 ```json 包裹）
        text = text.strip()
        if text.startswith("```"):
            # 去掉 markdown 代码块
            lines = text.split("\n")
            clean_lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(clean_lines)

        try:
            # 找到第一个 [ 和最后一个 ]
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                text = text[start:end + 1]
            return json.loads(text)
        except json.JSONDecodeError as e:
            _log.error(f"[memory_extractor] JSON parse failed: {e}")
            _log.debug(f"  Raw: {text[:300]}")
            return []

    def _apply_actions(self, actions: list[dict]) -> list[dict]:
        """执行记忆操作

        Args:
            actions: LLM 返回的操作列表

        Returns:
            实际执行结果列表
        """
        results = []
        for act in actions:
            action = act.get("action", "ignore")
            key = act.get("key", "")
            content = act.get("content", "")
            category = act.get("category", "user")
            tags = act.get("tags", ["general"])
            topic = act.get("topic", "general")
            # topic 作为 tags 的第一个元素，确保话题匹配可用
            if topic not in tags:
                tags = [topic] + [t for t in tags if t != topic]
            confidence = act.get("confidence", 0.5)

            if action == "ignore" or confidence < 0.7:
                continue

            try:
                existing = self.mm.get(key)
                if existing:
                    if action == "reinforce":
                        self.mm.reinforce(key)
                        self.mm.update(key, content=content)
                        results.append({"action": "reinforce", "key": key,
                                        "content": content, "boost": 2.0,
                                        "source": "llm_extract"})
                    else:
                        # create 但已存在 → 当作 reinforce
                        self.mm.reinforce(key)
                        self.mm.update(key, content=content)
                        results.append({"action": "reinforce", "key": key,
                                        "content": content, "boost": 2.0,
                                        "source": "llm_extract"})
                else:
                    if action == "create" and confidence >= 0.7:
                        base_w = 3 if confidence >= 0.9 else 2
                        self.mm.add(category, key, content,
                                    tags=tags, source="llm",
                                    base_weight=base_w)
                        results.append({"action": "create", "key": key,
                                        "content": content, "boost": 1.0,
                                        "source": "llm_extract"})
            except Exception as e:
                _log.error(f"[memory_extractor] apply action failed: {e}")

        return results

    # ── 主入口 ──

    def extract(self, conversation: list[dict], user_content: str) -> list[dict]:
        """从对话中提取记忆（双通道）

        Args:
            conversation: 完整对话历史 [{"role": ..., "content": ...}]
            user_content: 当前用户消息（用于快速通道）

        Returns:
            已执行的记忆操作摘要
        """
        all_results = []

        # ① 快速通道：关键词匹配
        fast_results = self._fast_path(user_content)
        all_results.extend(fast_results)
        if fast_results:
            _log.debug(f"[memory_extractor] fast_path matched: {fast_results}")

        # ② LLM 通道：调用模型智能提取
        try:
            llm_messages = self._build_extract_messages(conversation)
            llm_text = self._call_extraction_llm(llm_messages)
            actions = self._parse_response(llm_text)
            applied = self._apply_actions(actions)
            all_results.extend(applied)
            if applied:
                _log.info(f"[memory_extractor] llm extracted: {applied}")
        except Exception as e:
            _log.error(f"[memory_extractor] llm path error: {e}")

        return all_results
