"""记忆提取器（v2）— LLM 驱动的记忆提取建议

v2 核心变化（2026-05-20）：
  ① 删除快速通道（关键词/正则匹配 → 不再依赖规则）
  ② LLM 通道改为「建议模式」— 只生成记忆建议，不直接入库
  ③ 实际写入由 LLM 通过 memory 工具自主完成

可配置项（通过 settings → routing → extraction）：
  - model: 模型名
  - provider: local | deepseek | openai 等
  - temperature: 0.1（默认）
  - max_tokens: 1024
"""

import json
import requests
import re
from typing import Optional

from agent_core.memory_manager import MemoryManager
from logger import get_logger as _get_logger
from config.urls import QWEN_API

_log = _get_logger("memory_extractor")

# ── 提取器的 System Prompt ──
EXTRACTOR_SYSTEM_PROMPT = """你是记忆提取专家，负责从对话中分析哪些信息值得长期记住。

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
    "action": "suggest",
    "key": "唯一标识，英文小写，用下划线连接（如 user_name、preference_color）",
    "content": "记忆内容，清晰完整的陈述句，20字以内",
    "category": "user",
    "tags": ["标签1", "标签2"],
    "topic": "personal_info | preference | habit | work | entertainment | food | travel | tech | shopping | health | education | general",
    "confidence": 0.0-1.0
  }
]

confidence 含义：
- ≥0.9: 非常确定，建议立即存入
- 0.7-0.9: 较确定，可作为候选
- <0.7: 不确定，忽略（不输出该条）

## 约束
- 单次最多返回 3 条
- key 要稳定可复用（同类型信息用相同 key）
- content 要用简洁陈述句，20字以内
  ✅ "用户喜欢火锅"
  ✅ "用户习惯早起写代码"
  ❌ "用户明确表示比较喜欢吃火锅。"
- 不要编造信息，不确定就 confidence 打低
- **这是建议，不是直接入库**——最终由 AI 自主决定是否保存
"""


class MemoryExtractor:
    """记忆提取器（v2 建议模式）"""

    def __init__(self, db, route_cfg: Optional[dict] = None):
        self.db = db
        self.mm = MemoryManager(db)
        self.route_cfg = route_cfg or self._load_route_cfg()
        self.endpoint = self.route_cfg.get("_endpoint", QWEN_API)
        self.model = self.route_cfg.get("model", "qwen3.5-9b")
        self.temperature = self.route_cfg.get("temperature", 0.1)
        self.max_tokens = self.route_cfg.get("max_tokens", 1024)

    def _load_route_cfg(self) -> dict:
        """从 settings 加载 extraction 路由配置"""
        cfg = {"temperature": 0.1, "max_tokens": 1024,
               "model": "qwen3.5-9b", "provider": "local"}
        try:
            from ai_engine import get_settings
            cfg.update(get_settings("extraction"))
        except Exception:
            pass
        import os as _os
        env_endpoint = _os.environ.get("MEMORY_EXTRACTOR_ENDPOINT")
        if env_endpoint:
            cfg["_endpoint"] = env_endpoint
        return cfg

    # ── LLM 通道 — 生成记忆建议（不直接入库） ──

    def _build_extract_messages(self, conversation: list[dict]) -> list[dict]:
        """构建提取用的 LLM 消息"""
        recent = conversation[-6:] if len(conversation) > 6 else conversation

        dialogue_lines = []
        for m in recent:
            role_label = "用户" if m.get("role") in ("user", "human") else "AI"
            content = m.get("content", "").strip()
            if content:
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
        """调用 LLM 生成记忆建议"""
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
        """解析 LLM 返回的 JSON"""
        if not text:
            return []

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            clean_lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(clean_lines)

        try:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                text = text[start:end + 1]
            return json.loads(text)
        except json.JSONDecodeError as e:
            _log.error(f"[memory_extractor] JSON parse failed: {e}")
            return []

    # ── 主入口 ──

    def extract(self, conversation: list[dict], user_content: str) -> list[dict]:
        """从对话中提取记忆建议（v2 建议模式，不直接入库）

        Args:
            conversation: 完整对话历史 [{"role": ..., "content": ...}]
            user_content: 当前用户消息

        Returns:
            记忆建议列表 [{"action": "suggest", "key": ..., "content": ...}]
            调用方可将这些建议展示给 LLM 或日志记录
        """
        try:
            llm_messages = self._build_extract_messages(conversation)
            llm_text = self._call_extraction_llm(llm_messages)
            suggestions = self._parse_response(llm_text)
            if suggestions:
                _log.info(f"[memory_extractor] v2 suggestions: {suggestions}")
            return suggestions
        except Exception as e:
            _log.error(f"[memory_extractor] llm path error: {e}")
            return []
