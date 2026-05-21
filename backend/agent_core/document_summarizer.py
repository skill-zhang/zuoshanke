"""
文档摘要器 — 管理知识文档的三级摘要

预生成三级摘要：
  - single_line (50 chars): 一句话概括
  - brief (500 chars): 简短说明
  - full (5000 chars): 完整摘要

按场景声明的 document_deps 注入对应级别。
"""

from typing import Optional


def get_document(
    doc_name: str,
    level: str = "brief",
    db=None,
) -> str:
    """获取文档指定级别的摘要

    Args:
        doc_name: 文档名称（如 "schema-v1.0.md"）
        level: 摘要级别（single_line | brief | full）
        db: 数据库会话

    Returns:
        摘要文本
    """
    if db is None:
        return _read_file_fallback(doc_name, level)

    try:
        from models import DocumentSummary
        entry = db.query(DocumentSummary).filter(
            DocumentSummary.doc_name == doc_name
        ).first()
        if entry:
            return getattr(entry, level, entry.brief) or entry.brief or doc_name
    except Exception:
        pass

    return _read_file_fallback(doc_name, level)


def refresh_document(
    doc_name: str,
    file_path: str,
    db=None,
) -> bool:
    """从文件刷新文档摘要（预生成三级）

    Args:
        doc_name: 文档名称
        file_path: 文档文件路径
        db: 数据库会话

    Returns:
        是否成功
    """
    if db is None:
        return False

    content = _read_file_content(file_path)
    if content is None:
        return False

    summaries = _generate_summaries(content, doc_name)

    try:
        from models import DocumentSummary
        entry = db.query(DocumentSummary).filter(
            DocumentSummary.doc_name == doc_name
        ).first()
        if entry:
            entry.single_line = summaries["single_line"]
            entry.brief = summaries["brief"]
            entry.full = summaries["full"]
        else:
            from models import DocumentSummary as DS
            import uuid
            entry = DS(
                id=f"doc_{uuid.uuid4().hex[:12]}",
                doc_name=doc_name,
                single_line=summaries["single_line"],
                brief=summaries["brief"],
                full=summaries["full"],
            )
            db.add(entry)
        db.commit()
        return True
    except Exception as e:
        print(f"[document_summarizer] Failed to refresh {doc_name}: {e}")
        return False


def _generate_summaries(content: str, doc_name: str) -> dict:
    """生成三级摘要（简单提取，后续可升级为 LLM 摘要）"""
    lines = content.splitlines()
    non_empty = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    text = " ".join(non_empty)

    # single_line: 首句或文件名
    first_sentence = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
            first_sentence = stripped[:50]
            break
    single_line = first_sentence or doc_name

    # brief: 前 500 字符
    brief = text[:500]

    # full: 前 5000 字符
    full = text[:5000]

    return {
        "single_line": single_line,
        "brief": brief,
        "full": full,
    }


def _read_file_content(file_path: str) -> Optional[str]:
    """读取文件内容"""
    import os
    if not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _read_file_fallback(doc_name: str, level: str) -> str:
    """备选：从 docs/design/ 直接读取文件截取"""
    import os
    base_paths = [
        os.path.expanduser(f"~/zuoshanke/docs/design/{doc_name}"),
    ]
    for path in base_paths:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if level == "single_line":
                    return content[:50]
                elif level == "brief":
                    return content[:500]
                else:
                    return content[:5000]
            except Exception:
                pass
    return doc_name
