"""📊 结构化报告生成器 — 从结构化数据生成多格式报告

支持生成 Markdown、HTML、PDF、纯文本四种格式的报告。
适合数据分析汇总、进度报告、对比分析等场景。
输出到 zuoshanke 项目下的 output/ 目录。

## 用法
    from tools.gen_report import gen_report
    r = json.loads(gen_report(
        title="周报",
        sections=[{"heading":"完成", "content":"- 任务A\\n- 任务B"}],
        format="markdown"
    ))
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 中文字体路径 ──
CJK_FONTS = [
    "/usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf",
    "/usr/share/fonts/truetype/arphic-bkai00mp/bkai00mp.ttf",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]


def _find_cjk_font() -> str:
    """找可用的中文字体（优先 TTF 单文件，避免 TTC 兼容问题）"""
    for fp in CJK_FONTS:
        if os.path.exists(fp):
            return fp
    try:
        import subprocess
        out = subprocess.check_output(["fc-list", ":lang=zh", "-f", "%{file}\n"],
                                      text=True, stderr=subprocess.DEVNULL)
        for line in out.strip().split("\n"):
            line = line.strip()
            if line and os.path.exists(line):
                return line
    except Exception:
        pass
    return ""


def _get_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _make_markdown(title: str, sections: list, metadata: dict) -> str:
    """生成 Markdown 格式报告"""
    lines = [f"# {title}", "", f"> 生成时间: {_get_timestamp()}"]
    for k, v in metadata.items():
        lines.append(f"> {k}: {v}")
    lines.append("")

    for sec in sections:
        heading = sec.get("heading", "")
        level = sec.get("level", 2)
        lines.append(f"{'#' * level} {heading}")
        lines.append("")
        content = sec.get("content", "")
        if content:
            lines.append(content)
        lines.append("")

    return "\n".join(lines)


def _html_escape(text: str) -> str:
    """HTML 实体转义"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _make_html(title: str, sections: list, metadata: dict) -> str:
    """生成 HTML 格式报告"""
    meta_lines = "".join(f"<p><strong>{_html_escape(k)}:</strong> {_html_escape(v)}</p>" for k, v in metadata.items())
    body = ""
    for sec in sections:
        heading = sec.get("heading", "")
        level = min(sec.get("level", 2), 4)
        content = sec.get("content", "")
        # 粗略 Markdown → HTML
        content_html = _html_escape(content)
        content_html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", content_html, flags=re.M)
        content_html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", content_html, flags=re.M)
        content_html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", content_html, flags=re.M)
        content_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content_html)
        content_html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content_html)
        content_html = re.sub(r"`(.+?)`", r"<code>\1</code>", content_html)
        content_html = re.sub(r"^- (.+)$", r"<li>\1</li>", content_html, flags=re.M)
        # 段落
        content_html = re.sub(r"\n\n", r"</p><p>", content_html)
        body += f"<h{level}>{_html_escape(heading)}</h{level}><p>{content_html}</p>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{_html_escape(title)}</title>
<style>
body {{ font: 14px/1.6 'Microsoft YaHei','Noto Sans CJK SC',sans-serif; max-width: 800px; margin: 20px auto; padding: 0 20px; color: #333; }}
h1 {{ color: #1a3a6b; border-bottom: 2px solid #1a3a6b; padding-bottom: 8px; }}
h2 {{ color: #2a5298; margin-top: 24px; }}
code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }}
li {{ margin: 4px 0; }}
.meta {{ color: #888; font-size: 12px; }}
</style></head>
<body>
<h1>{_html_escape(title)}</h1>
<div class="meta">{meta_lines}<p>生成时间: {_get_timestamp()}</p></div>
{body}
</body></html>"""


class PDF(FPDF):
    def __init__(self, font_path: str):
        super().__init__()
        self._font_path = font_path
        self.set_auto_page_break(auto=True, margin=20)
        if font_path:
            self.add_font("CJK", "", font_path)
            self.add_font("CJK", "B", font_path)

    def _has_cjk(self):
        return bool(self._font_path)

    def _cj(self, style="", size=10):
        if self._has_cjk():
            self.set_font("CJK", style, size)
        else:
            self.set_font("Helvetica", style, size)
        self.set_x(self.l_margin)

    def _mc(self, w, h, txt, **kw):
        self.set_x(self.l_margin)
        return self.multi_cell(w, h, txt, **kw)

    def add_sections(self, title, sections):
        self.add_page()
        self._cj("B", 20)
        self._mc(0, 10, title, align="C")
        self.ln(5)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

        for sec in sections:
            heading = sec.get("heading", "")
            level = sec.get("level", 2)
            content = sec.get("content", "")
            size = {1: 16, 2: 14, 3: 12, 4: 10}.get(level, 12)
            self._cj("B", size)
            self._mc(0, 8, heading)
            self.ln(2)

            self._cj("", 10)
            for line in content.split("\n"):
                stripped = line.strip()
                if not stripped:
                    self.ln(2)
                elif stripped.startswith("- "):
                    self._mc(0, 5.5, "    " + stripped[2:])
                else:
                    self._mc(0, 5.5, stripped)
            self.ln(4)


def _make_pdf(title: str, sections: list, metadata: dict, output_path: str) -> str:
    """生成 PDF 格式报告"""
    if FPDF is None:
        return ""
    font_path = _find_cjk_font()
    pdf = PDF(font_path)
    pdf.add_sections(title, sections)
    pdf.output(output_path)
    return output_path


def gen_report(
    title: str = "报告",
    sections: list = None,
    format: str = "markdown",
    metadata: dict = None,
    output_name: str = "",
) -> str:
    """生成结构化报告

    Args:
        title: 报告标题
        sections: 章节列表 [{"heading": "章节名", "content": "内容(支持Markdown)", "level": 2}]
        format: 输出格式 — "markdown" / "html" / "pdf" / "text"
        metadata: 元数据 {"key": "value", ...}
        output_name: 输出文件名（不含扩展名，默认自动生成）

    Returns:
        JSON: {success, file_path, format, content?, error?}
    """
    try:
        if sections is None:
            sections = []
        if metadata is None:
            metadata = {}
        if not output_name:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r"[^\w\u4e00-\u9fff_-]", "_", title)[:30]
            output_name = f"report_{safe_title}_{ts}"

        fmt = format.lower()
        if fmt == "markdown":
            content = _make_markdown(title, sections, metadata)
            output_path = str(OUTPUT_DIR / f"{output_name}.md")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            return json.dumps({
                "success": True, "file_path": output_path,
                "format": "markdown", "content": content[:500],
            }, ensure_ascii=False)

        elif fmt == "html":
            content = _make_html(title, sections, metadata)
            output_path = str(OUTPUT_DIR / f"{output_name}.html")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            return json.dumps({
                "success": True, "file_path": output_path,
                "format": "html", "content": content[:500],
            }, ensure_ascii=False)

        elif fmt == "pdf":
            output_path = str(OUTPUT_DIR / f"{output_name}.pdf")
            result_path = _make_pdf(title, sections, metadata, output_path)
            if not result_path:
                return json.dumps({"success": False, "error": "PDF 生成失败（fpdf2 未安装或字体缺失）"})
            return json.dumps({
                "success": True, "file_path": result_path, "format": "pdf",
            }, ensure_ascii=False)

        elif fmt == "text":
            lines = [f"=== {title} ===", f"生成时间: {_get_timestamp()}"]
            for k, v in metadata.items():
                lines.append(f"{k}: {v}")
            lines.append("")
            for sec in sections:
                lines.append(f"\n{'=' * 40}")
                lines.append(f"  {sec.get('heading', '')}")
                lines.append(f"{'=' * 40}")
                lines.append(sec.get("content", ""))
            content = "\n".join(lines)
            output_path = str(OUTPUT_DIR / f"{output_name}.txt")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            return json.dumps({
                "success": True, "file_path": output_path,
                "format": "text", "content": content[:500],
            }, ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"不支持的格式: {format}，可选: markdown/html/pdf/text"})

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
