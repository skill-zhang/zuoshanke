"""多模态支持 — 文件附件转为 LLM 可消费的内容格式"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

# 上传目录
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"

# 支持多模态的模型关键词（名称或 provider 中包含）
VISION_MODEL_KEYWORDS = [
    "qwen", "qwen2", "qwen3",        # Qwen 系列视觉能力
    "llava",                          # LLaVA
    "cogvlm", "cogview",             # CogVLM
    "internvl",                       # InternVL
    "minicpm",                        # MiniCPM-V
    "glm-4v", "glm-4vx",            # GLM-4V
    "gpt-4o", "gpt-4-turbo",         # OpenAI 视觉模型
    "claude-3", "claude-3.5",        # Claude 视觉模型 (sonnet, opus)
    "claude-3-haiku",                # Claude Haiku supports images
    "claude-sonnet-4",               # Claude Sonnet 4
    "gemini",                         # Gemini
    "pixtral",                        # Pixtral (Mistral)
]


def can_accept_images(provider_name: str, model_name: str) -> bool:
    """判断 provider/model 是否支持图片输入（多模态）

    Args:
        provider_name: provider 名称（如 local, deepseek, openai）
        model_name: 模型名（如 qwen3.5-9b, deepseek-chat）

    Returns:
        True 如果该模型支持多模态
    """
    combined = (provider_name + " " + model_name).lower()
    for kw in VISION_MODEL_KEYWORDS:
        if kw.lower() in combined:
            return True
    return False


def build_multimodal_content(text: str, attachments: list[dict]) -> list[dict]:
    """将纯文本 + 文件附件转为 OpenAI 多模态 content 数组

    Args:
        text: 用户输入的文本
        attachments: [{url: str, file_type: 'image'|'doc', filename: str}]

    Returns:
        OpenAI content 数组: [{"type": "text", "text": "..."}, {"type": "image_url", ...}]
    """
    parts = [{"type": "text", "text": text}] if text else []

    for att in attachments:
        url = att.get("url", "")
        file_type = att.get("file_type", "")
        filename = att.get("filename", url.split("/")[-1] if "/" in url else url)

        # 图片附件 → 转为 base64 data URI
        if file_type == "image":
            data_uri = _file_url_to_data_uri(url)
            if data_uri:
                # 检查图片大小
                import sys
                raw_size = len(base64.b64decode(data_uri.split(",")[1])) if "," in data_uri else len(data_uri)
                # 超过 20MB 的图片可能无法被 LLM 处理
                if raw_size > 20 * 1024 * 1024:
                    parts.append({"type": "text", "text": f"[图片过大: {filename}，已跳过 ({raw_size / 1024 / 1024:.1f}MB)]"})
                else:
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    })

        # 文档附件 → 读取内容作为文本注入
        elif file_type == "doc":
            file_text = _read_file_content(url)
            if file_text:
                parts.append({"type": "text", "text": f"[文件: {filename}]\n```\n{file_text[:10000]}\n```"})
            else:
                parts.append({"type": "text", "text": f"[文件: {filename}]"})

    return parts


def _file_url_to_data_uri(url: str) -> Optional[str]:
    """将文件 URL 转为 base64 data URI

    Args:
        url: 相对 URL 如 '/uploads/xxx.jpg' 或绝对路径

    Returns:
        data:image/png;base64,... 格式的 data URI，失败返回 None
    """
    # 本地文件路径
    if url.startswith("/uploads/"):
        file_path = UPLOAD_DIR / url[len("/uploads/"):]
    elif url.startswith("uploads/"):
        file_path = UPLOAD_DIR / url[len("uploads/"):]
    else:
        # 尝试直接作为绝对路径
        file_path = Path(url)
        if not file_path.exists():
            _log.warning(f"[multimodal] 文件不存在: {url}")
            return None

    if not file_path.exists():
        _log.warning(f"[multimodal] 文件不存在: {file_path}")
        return None

    try:
        data = file_path.read_bytes()
        ext = file_path.suffix.lower()
        mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".webp": "image/webp", ".bmp": "image/bmp",
        }.get(ext, "image/jpeg")
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        _log.error(f"[multimodal] 读取图片失败: {file_path}: {e}")
        return None


def _read_file_content(url: str) -> Optional[str]:
    """读取文档文件内容

    Args:
        url: 文件 URL

    Returns:
        文件文本内容（最多前 10000 字符），失败返回 None
    """
    if url.startswith("/uploads/"):
        file_path = UPLOAD_DIR / url[len("/uploads/"):]
    else:
        file_path = Path(url)

    if not file_path.exists():
        return None

    ext = file_path.suffix.lower()
    # 只读取文本类型文件
    text_exts = {".txt", ".md", ".json", ".csv", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".py", ".js", ".ts", ".html", ".css"}
    if ext not in text_exts:
        return None  # 二进制文件无法读取为文本

    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        _log.warning(f"[multimodal] 读取文档失败: {file_path}: {e}")
        return None


def should_use_multimodal_format(route_cfg: dict) -> bool:
    """判断是否应该使用多模态消息格式（content 为数组）

    Args:
        route_cfg: 路由配置

    Returns:
        True 表示模型支持多模态，可以使用 content 数组格式
    """
    provider_name = route_cfg.get("provider", "")
    model_name = route_cfg.get("model", "")
    return can_accept_images(provider_name, model_name)


def format_message_content(content: str | list,
                           attachments: Optional[list[dict]] = None,
                           route_cfg: Optional[dict] = None) -> str | list:
    """格式化消息 content 字段

    如果有附件且模型支持多模态，返回 content 数组（多模态格式）
    否则返回纯文本

    Args:
        content: 消息文本（或已有的 content 数组）
        attachments: 文件附件列表
        route_cfg: 路由配置，用于检测模型是否支持多模态

    Returns:
        str | list — 兼容 OpenAI API 格式
    """
    if not attachments:
        return content

    # 文本转为字符串
    text = content if isinstance(content, str) else (content[0]["text"] if isinstance(content, list) and len(content) > 0 else str(content))

    if route_cfg and should_use_multimodal_format(route_cfg):
        return build_multimodal_content(text, attachments)
    else:
        # 不支持多模态的模型：将附件信息作为文本描述追加
        descs = []
        for att in attachments:
            at = att.get("file_type", "")
            fn = att.get("filename", "")
            if at == "image":
                descs.append(f"[图片: {fn}]")
            else:
                descs.append(f"[文件: {fn}]")
        if descs:
            text = text + "\n\n" + "\n".join(descs) if text else "\n".join(descs)
        return text
