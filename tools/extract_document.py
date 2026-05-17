"""文档提取工具 — 从 PDF/图片/文本文件中提取文字内容

功能：
- extract_text_from_pdf: PDF 文字提取（需要 PyMuPDF）
- extract_text_from_image: 图片 OCR（需要 pytesseract + tesseract-ocr）
- extract_text: 自动文件类型检测+提取
"""

import os
import json
import mimetypes

TOOLS_DIR = os.path.expanduser("~/zuoshanke/tools")


def _check_pymupdf():
    """检查 PyMuPDF 是否可用"""
    try:
        import fitz
        return True, fitz
    except ImportError:
        return False, None


def _check_tesseract():
    """检查 pytesseract 是否可用"""
    try:
        import pytesseract
        return True, pytesseract
    except ImportError:
        return False, None


def extract_text_from_pdf(file_path: str, max_pages: int = 10) -> dict:
    """从 PDF 文件中提取文字

    Args:
        file_path: PDF 文件路径
        max_pages: 最大提取页数（-1 表示全部）

    Returns:
        {"pages": [{page, text}, ...], "total_pages": N, "text": "...", "success": True}
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}"}

    ok, fitz = _check_pymupdf()
    if not ok:
        return {"success": False, "error": "需要安装 PyMuPDF，请运行: pip install PyMuPDF"}

    try:
        doc = fitz.open(file_path)
        total = len(doc)
        pages = []

        limit = min(total, max_pages) if max_pages > 0 else total
        for i in range(limit):
            page = doc[i]
            text = page.get_text().strip()
            pages.append({
                "page": i + 1,
                "text": text[:2000] if len(text) > 2000 else text,
            })

        doc.close()

        # 合并全文
        full_text = "\n\n".join(p["text"] for p in pages)
        if len(full_text) > 3000:
            full_text = full_text[:3000] + "\n\n...（以下内容已截断）"

        return {
            "success": True,
            "pages": pages,
            "total_pages": total,
            "text": full_text,
            "note": f"提取了 {limit}/{total} 页" if limit < total else "已提取全部页面",
        }
    except Exception as e:
        return {"success": False, "error": f"PDF 提取失败: {str(e)}"}


def extract_text_from_image(file_path: str) -> dict:
    """从图片中提取文字（OCR）

    Args:
        file_path: 图片文件路径（png/jpg/jpeg）

    Returns:
        {"text": "...", "success": True}
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}"}

    ok, pytesseract = _check_tesseract()
    if not ok:
        return {"success": False, "error": "需要安装 pytesseract + tesseract-ocr:\n"
                                            "  pip install pytesseract\n"
                                            "  sudo apt install tesseract-ocr tesseract-ocr-chi-sim"}

    try:
        from PIL import Image
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang='chi_sim+eng')
        text = text.strip()

        if not text:
            return {"success": True, "text": "未能从图片中识别出文字", "note": "图片可能不包含文字或质量不够"}

        if len(text) > 3000:
            text = text[:3000] + "\n\n...（以下内容已截断）"

        return {"success": True, "text": text}
    except Exception as e:
        return {"success": False, "error": f"OCR 识别失败: {str(e)}"}


def extract_text(file_path: str) -> dict:
    """自动检测文件类型并提取文字

    根据扩展名自动选择方法：
      .pdf → extract_text_from_pdf
      .png/.jpg/.jpeg → extract_text_from_image
      其他 → 作为纯文本读取

    Args:
        file_path: 文件路径

    Returns:
        {"text": "...", "method": "...", "success": True}
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}"}

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        result = extract_text_from_pdf(file_path)
        result["method"] = "pdf"
        return result
    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"):
        result = extract_text_from_image(file_path)
        result["method"] = "ocr"
        return result
    else:
        # 作为纯文本尝试读取
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            if len(text) > 3000:
                text = text[:3000] + "\n\n...（以下内容已截断）"
            return {"success": True, "text": text, "method": "text", "file_size": len(text)}
        except UnicodeDecodeError:
            return {"success": False, "error": f"无法解析文件 {file_path}，格式不支持",
                    "hint": "支持格式: .pdf, .png, .jpg, .jpeg, .txt"}
        except Exception as e:
            return {"success": False, "error": f"读取失败: {str(e)}"}
