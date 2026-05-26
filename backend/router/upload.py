"""文件上传端点 — 支持图片和文档上传，返回可访问的 URL"""

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

_log = logging.getLogger(__name__)

# 上传目录
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 允许的图片 MIME 类型
ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp",
}
# 允许的文档 MIME 类型
ALLOWED_DOC_TYPES = {
    "application/pdf",
    "text/plain",
    "application/json",
    "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/markdown",
    "application/zip",
    "application/gzip",
}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_DOC_EXT = {".pdf", ".txt", ".json", ".csv", ".doc", ".docx", ".xls", ".xlsx", ".md", ".zip", ".gz"}

router = APIRouter(tags=["上传"])


def _is_allowed(filename: str, content_type: str) -> tuple[bool, str]:
    """检查文件是否允许上传，返回 (ok, file_type) 其中 file_type 为 'image' / 'doc' / ''"""
    ext = Path(filename).suffix.lower()
    if content_type in ALLOWED_IMAGE_TYPES or ext in ALLOWED_IMAGE_EXT:
        return True, "image"
    if ext in ALLOWED_DOC_EXT:
        return True, "doc"
    return False, ""


@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文件，返回可访问的 URL

    Returns:
        {"url": "http://localhost:8000/uploads/xxx.jpg",
         "file_type": "image"|"doc",
         "filename": "xxx.jpg",
         "size": 12345}
    """
    if not file.filename:
        raise HTTPException(400, "文件名为空")

    # 检查文件类型
    content_type = file.content_type or ""
    ok, file_type = _is_allowed(file.filename, content_type)
    if not ok:
        raise HTTPException(400,
            f"不支持的文件类型: {content_type or file.filename}。"
            f"图片支持: {', '.join(sorted(ALLOWED_IMAGE_EXT))}；"
            f"文档支持: {', '.join(sorted(ALLOWED_DOC_EXT))}。"
        )

    # 生成唯一文件名
    ext = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / unique_name

    # 保存文件
    try:
        content = await file.read()
        # 文件大小限制：50MB
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, "文件过大，最大支持 50MB")
        save_path.write_bytes(content)
    except HTTPException:
        raise
    except Exception as e:
        _log.error(f"[upload] 保存文件失败: {e}")
        raise HTTPException(500, f"文件保存失败: {e}")

    # 构造访问 URL
    url = f"/uploads/{unique_name}"

    return JSONResponse({
        "url": url,
        "file_type": file_type,
        "filename": file.filename,
        "size": len(content),
    })
