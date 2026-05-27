"""Provider Catalog — 从 providers.md 读取并解析已知 Provider/Model 目录

数据源: config/providers.md（MD 格式，人类可读可编辑）
提供: get_catalog() → list[ProviderCatalogItem]
缓存: 内存缓存 60 秒（开发时可调小）
"""

import os
import time
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path

_CACHE: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 60  # 秒


@dataclass
class ModelCatalogItem:
    name: str
    display_name: str
    temperature: float = 0.7
    max_tokens: int = 8192
    context_length: int = 32768
    repeat_penalty: float = 1.05
    vision: bool = False
    function_calling: bool = True


@dataclass
class ProviderCatalogItem:
    id: str          # 唯一标识，如 "deepseek"
    display_name: str
    base_url: str
    provider_type: str = "openai-compatible"  # openai-compatible | local
    models: list[ModelCatalogItem] = field(default_factory=list)


def _md_path() -> Path:
    """定位 providers.md（优先项目目录，其次 package 同级）"""
    # 优先从项目根目录找
    for base in [
        Path(os.environ.get("ZUOSHANKE_HOME", "")),
        Path.home() / "zuoshanke" / "backend",
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent.parent,
    ]:
        for p in [base / "config" / "providers.md", base / "providers.md"]:
            if p.exists():
                return p
    # 最后尝试显式路径
    fallback = Path.home() / "zuoshanke" / "backend" / "config" / "providers.md"
    if not fallback.exists():
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(_DEFAULT_CONTENT)
    return fallback


def parse_providers_md(text: str) -> list[ProviderCatalogItem]:
    """解析 providers.md → ProviderCatalogItem 列表

    格式:
        ## ProviderID          ← 新 Provider
        - key: value           ← Provider 属性
        ### model-id           ← 新模型
        - key: value           ← 模型属性
    """
    providers: list[ProviderCatalogItem] = []
    current_provider: Optional[ProviderCatalogItem] = None
    current_model: Optional[ModelCatalogItem] = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Provider 头部: ## deepseek
        if stripped.startswith("## ") and not stripped.startswith("### "):
            # 保存前一个模型
            if current_model and current_provider is not None:
                current_provider.models.append(current_model)
                current_model = None
            if current_provider is not None:
                providers.append(current_provider)

            pid = stripped[3:].strip()
            current_provider = ProviderCatalogItem(id=pid, display_name=pid, base_url="")
            continue

        # 模型头部: ### model-name
        if stripped.startswith("### "):
            if current_model and current_provider is not None:
                current_provider.models.append(current_model)
            model_name = stripped[4:].strip()
            current_model = ModelCatalogItem(name=model_name, display_name=model_name)
            continue

        # 键值对: - key: value
        if stripped.startswith("- "):
            colon = stripped.find(":", 2)
            if colon > 2:
                key = stripped[2:colon].strip()
                value = stripped[colon + 1:].strip()

                # Bool 转换
                if value.lower() in ("true", "yes", "✓", "✅"):
                    value_bool = True
                elif value.lower() in ("false", "no", "✗", "❌"):
                    value_bool = False
                else:
                    value_bool = None

                # 数值转换
                def _to_num(v: str):
                    try:
                        # 支持 "1M" → 1000000, "128K" → 128000
                        v = v.strip()
                        if v.endswith("M"):
                            return int(float(v[:-1]) * 1_000_000)
                        if v.endswith("K"):
                            return int(float(v[:-1]) * 1_000)
                        return int(v)
                    except ValueError:
                        try:
                            return float(v)
                        except ValueError:
                            return v

                # 分派到当前对象
                target = current_model if current_model is not None else current_provider
                if target is None:
                    continue

                val = value_bool if value_bool is not None else _to_num(value)

                if key == "display_name":
                    target.display_name = val if isinstance(val, str) else str(val)
                elif key == "base_url" and isinstance(target, ProviderCatalogItem):
                    target.base_url = val if isinstance(val, str) else str(val)
                elif key == "provider_type" and isinstance(target, ProviderCatalogItem):
                    target.provider_type = val if isinstance(val, str) else str(val)
                elif key == "temperature" and isinstance(target, ModelCatalogItem):
                    target.temperature = float(val)
                elif key == "max_tokens" and isinstance(target, ModelCatalogItem):
                    target.max_tokens = int(val)
                elif key == "context_length" and isinstance(target, ModelCatalogItem):
                    target.context_length = int(val)
                elif key == "repeat_penalty" and isinstance(target, ModelCatalogItem):
                    target.repeat_penalty = float(val)
                elif key == "vision" and isinstance(target, ModelCatalogItem):
                    target.vision = bool(val)
                elif key == "function_calling" and isinstance(target, ModelCatalogItem):
                    target.function_calling = bool(val)

    # 收尾
    if current_model and current_provider is not None:
        current_provider.models.append(current_model)
    if current_provider is not None:
        providers.append(current_provider)

    return providers


def catalog_to_dict(providers: list[ProviderCatalogItem]) -> list[dict]:
    """转为可 JSON 序列化的 dict"""
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "base_url": p.base_url,
            "provider_type": p.provider_type,
            "models": [
                {
                    "name": m.name,
                    "display_name": m.display_name,
                    "temperature": m.temperature,
                    "max_tokens": m.max_tokens,
                    "context_length": m.context_length,
                    "repeat_penalty": m.repeat_penalty,
                    "vision": m.vision,
                    "function_calling": m.function_calling,
                }
                for m in p.models
            ],
        }
        for p in providers
    ]


def get_catalog(force_refresh: bool = False) -> list[dict]:
    """获取 Provider 目录（带缓存）

    Args:
        force_refresh: 如果 True，跳过缓存重新读取文件
    """
    now = time.time()
    if not force_refresh and _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["data"]

    path = _md_path()
    text = path.read_text(encoding="utf-8")
    providers = parse_providers_md(text)
    result = catalog_to_dict(providers)

    _CACHE["data"] = result
    _CACHE["ts"] = now
    return result


def invalidate_cache():
    """强制下次读文件"""
    _CACHE["data"] = None
    _CACHE["ts"] = 0.0


def get_provider_catalog_item(provider_id: str) -> Optional[dict]:
    """按 id 查找单个 Provider 目录项"""
    for p in get_catalog():
        if p["id"] == provider_id:
            return p
    return None


def get_model_catalog_item(provider_id: str, model_name: str) -> Optional[dict]:
    """按 provider + model name 查找单个模型目录项"""
    p = get_provider_catalog_item(provider_id)
    if not p:
        return None
    for m in p["models"]:
        if m["name"] == model_name:
            return m
    return None


# ── 初始默认内容（文件不存在时写入） ──

_DEFAULT_CONTENT = """# Provider 目录

> 坐山客已知的 AI Provider 和模型列表。
> 覆盖市面上所有主流 AI 模型提供商。
> 每日自动检查更新。
>
> 最后更新: 2026-05-27

## DeepSeek
- display_name: DeepSeek
- base_url: https://api.deepseek.com
- provider_type: openai-compatible

### deepseek-v4-flash
- display_name: DeepSeek v4 Flash
- temperature: 0.7
- max_tokens: 8192
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### deepseek-v4-pro
- display_name: DeepSeek v4 Pro
- temperature: 0.5
- max_tokens: 8192
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

## OpenAI
- display_name: OpenAI
- base_url: https://api.openai.com/v1
- provider_type: openai-compatible

### gpt-4o
- display_name: GPT-4o
- temperature: 0.7
- max_tokens: 16384
- context_length: 128000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gpt-4o-mini
- display_name: GPT-4o Mini
- temperature: 0.7
- max_tokens: 16384
- context_length: 128000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### o3-mini
- display_name: o3 Mini
- temperature: 1.0
- max_tokens: 102400
- context_length: 200000
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Anthropic
- display_name: Anthropic
- base_url: https://api.anthropic.com
- provider_type: openai-compatible

### claude-sonnet-4
- display_name: Claude Sonnet 4
- temperature: 0.7
- max_tokens: 8192
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-haiku-3.5
- display_name: Claude Haiku 3.5
- temperature: 0.7
- max_tokens: 8192
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

## Google
- display_name: Google Gemini
- base_url: https://generativelanguage.googleapis.com
- provider_type: openai-compatible

### gemini-2.5-pro
- display_name: Gemini 2.5 Pro
- temperature: 0.7
- max_tokens: 8192
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gemini-2.5-flash
- display_name: Gemini 2.5 Flash
- temperature: 0.7
- max_tokens: 8192
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

## xAI
- display_name: xAI Grok
- base_url: https://api.x.ai
- provider_type: openai-compatible

### grok-3
- display_name: Grok 3
- temperature: 0.7
- max_tokens: 131072
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### grok-3-mini
- display_name: Grok 3 Mini
- temperature: 0.7
- max_tokens: 131072
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Mistral
- display_name: Mistral AI
- base_url: https://api.mistral.ai
- provider_type: openai-compatible

### mistral-large-3.1
- display_name: Mistral Large 3.1
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### mistral-small-3.1
- display_name: Mistral Small 3.1
- temperature: 0.7
- max_tokens: 8192
- context_length: 32768
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Alibaba
- display_name: 通义千问 (Alibaba)
- base_url: https://dashscope.aliyuncs.com/compat-mode/v1
- provider_type: openai-compatible

### qwen-max
- display_name: Qwen Max
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen-plus
- display_name: Qwen Plus
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen-turbo
- display_name: Qwen Turbo
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## ByteDance
- display_name: 豆包 (ByteDance)
- base_url: https://ark.cn-beijing.volces.com/api/v3
- provider_type: openai-compatible

### doubao-pro-32k
- display_name: 豆包 Pro 32K
- temperature: 0.7
- max_tokens: 4096
- context_length: 32000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### doubao-pro-128k
- display_name: 豆包 Pro 128K
- temperature: 0.7
- max_tokens: 4096
- context_length: 128000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### doubao-lite-32k
- display_name: 豆包 Lite 32K
- temperature: 0.7
- max_tokens: 4096
- context_length: 32000
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Zhipu
- display_name: 智谱 AI (Zhipu)
- base_url: https://open.bigmodel.cn/api/paas/v4
- provider_type: openai-compatible

### glm-4-plus
- display_name: GLM-4 Plus
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### glm-4-air
- display_name: GLM-4 Air
- temperature: 0.7
- max_tokens: 4096
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Yi
- display_name: 零一万物 Yi
- base_url: https://api.lingyiwanwu.com
- provider_type: openai-compatible

### yi-lightning
- display_name: Yi Lightning
- temperature: 0.7
- max_tokens: 4096
- context_length: 16384
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### yi-vision
- display_name: Yi Vision
- temperature: 0.7
- max_tokens: 4096
- context_length: 16384
- repeat_penalty: 1.05
- vision: true
- function_calling: true

## Moonshot
- display_name: 月之暗面 Moonshot
- base_url: https://api.moonshot.cn
- provider_type: openai-compatible

### moonshot-v1-8k
- display_name: Moonshot v1 8K
- temperature: 0.7
- max_tokens: 4096
- context_length: 8192
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### moonshot-v1-32k
- display_name: Moonshot v1 32K
- temperature: 0.7
- max_tokens: 4096
- context_length: 32768
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### moonshot-v1-128k
- display_name: Moonshot v1 128K
- temperature: 0.7
- max_tokens: 4096
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Stepfun
- display_name: 阶跃星辰 Stepfun
- base_url: https://api.stepfun.com
- provider_type: openai-compatible

### step-2-16k
- display_name: Step 2 16K
- temperature: 0.7
- max_tokens: 4096
- context_length: 16384
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### step-1-8k
- display_name: Step 1 8K
- temperature: 0.7
- max_tokens: 4096
- context_length: 8192
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## SiliconFlow
- display_name: SiliconFlow
- base_url: https://api.siliconflow.cn
- provider_type: openai-compatible

### deepseek-ai/DeepSeek-V3
- display_name: DeepSeek V3 (硅基流动)
- temperature: 0.7
- max_tokens: 4096
- context_length: 65536
- repeat_penalty: 1.05
- vision: false
- function_calling: false

### Qwen/Qwen2.5-72B-Instruct
- display_name: Qwen2.5 72B (硅基流动)
- temperature: 0.7
- max_tokens: 4096
- context_length: 32768
- repeat_penalty: 1.05
- vision: false
- function_calling: false

## Groq
- display_name: Groq
- base_url: https://api.groq.com/openai
- provider_type: openai-compatible

### llama-3.3-70b-versatile
- display_name: Llama 3.3 70B (Groq)
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### deepseek-r1-distill-llama-70b
- display_name: DeepSeek R1 Distill 70B (Groq)
- temperature: 0.6
- max_tokens: 16384
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Xiaomi
- display_name: 小米 MiMo
- base_url: https://api.mi.com/ai
- provider_type: openai-compatible

### mimo-pro
- display_name: MiMo Pro
- temperature: 0.7
- max_tokens: 4096
- context_length: 32768
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### mimo-lite
- display_name: MiMo Lite
- temperature: 0.7
- max_tokens: 4096
- context_length: 16384
- repeat_penalty: 1.05
- vision: false
- function_calling: true
"""  # noqa: E501
