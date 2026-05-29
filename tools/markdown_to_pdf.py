"""📄 Markdown → PDF — 将 Markdown 文本或文件转换为 PDF 文档

支持中文（文泉驿正黑）、代码块、表格、标题层级、列表、粗斜体。
输出到 zuoshanke 项目下的 output/ 目录。

## 用法
    from tools.markdown_to_pdf import markdown_to_pdf
    r = json.loads(markdown_to_pdf("# Hello\\n\\nWorld", title="我的文档"))
    r = json.loads(markdown_to_pdf(file_path="/path/to/doc.md"))
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

# ── 输出目录 ──
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
    # fallback: fc-list
    import subprocess
    try:
        out = subprocess.check_output(["fc-list", ":lang=zh", "-f", "%{file}\n"],
                                      text=True, stderr=subprocess.DEVNULL)
        for line in out.strip().split("\n"):
            line = line.strip()
            if line and os.path.exists(line):
                return line
    except Exception:
        pass
    return ""


class PDF(FPDF):
    """支持中文的 PDF 生成器"""

    def __init__(self, font_path: str):
        super().__init__()
        self._font_path = font_path
        self.set_auto_page_break(auto=True, margin=20)
        if font_path:
            self.add_font("CJK", "", font_path)
            self.add_font("CJK", "B", font_path)
        self._is_code_block = False

    def _has_cjk(self) -> bool:
        return bool(self._font_path)

    def _cjk(self, style: str = "", size: float = 10):
        if self._has_cjk():
            self.set_font("CJK", style, size)
        else:
            self.set_font("Helvetica", style, size)
        self.set_x(self.l_margin)  # 重置 x 避免 fpdf2 bug (multi_cell 后 x 不归位)

    def _mc(self, w, h, txt, **kw):
        """安全的 multi_cell — 先重置 x 到左边界"""
        self.set_x(self.l_margin)
        return self.multi_cell(w, h, txt, **kw)

    def write_markdown(self, md_text: str):
        """解析并写入 Markdown 内容"""
        lines = md_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # ── 代码块 ──
            if stripped.startswith("```"):
                self._is_code_block = not self._is_code_block
                if self._is_code_block:
                    self._cjk("", 8)
                else:
                    self._cjk("", 10)
                    self.ln(2)
                i += 1
                continue

            if self._is_code_block:
                # 代码内容用 CJK 字体（支持中文）
                self._cjk("", 8)
                self._mc(0, 4.5, self._escape(line))
                i += 1
                continue

            # ── 空行 ──
            if not stripped:
                self.ln(3)
                i += 1
                continue

            # ── 标题 ──
            h_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if h_match:
                level = len(h_match.group(1))
                text = h_match.group(2)
                sizes = {1: 18, 2: 15, 3: 13, 4: 11, 5: 10, 6: 9}
                size = sizes.get(level, 12)
                if level <= 2:
                    self.ln(3)
                self._cjk("B", size)
                self._mc(0, size * 0.55, text)
                self.ln(2)
                # 分隔线 under h1/h2
                if level <= 2:
                    self.set_draw_color(200, 200, 200)
                    self.line(self.get_x(), self.get_y(),
                              self.get_x() + self.w - 2 * self.l_margin, self.get_y())
                    self.ln(3)
                i += 1
                continue

            # ── 无序列表 ──
            ul_match = re.match(r"^[\s]*[-*+]\s+(.+)$", line)
            if ul_match:
                self._cjk("", 10)
                x0 = self.get_x()
                self.cell(8, 6, "  - " if not stripped.startswith("  ") else "   - ")
                self._mc(0, 5.5, self._inline_format(ul_match.group(1)))
                self.set_x(x0)
                i += 1
                continue

            # ── 有序列表 ──
            ol_match = re.match(r"^[\s]*(\d+)\.\s+(.+)$", line)
            if ol_match:
                self._cjk("", 10)
                x0 = self.get_x()
                self.cell(8, 6, f"  {ol_match.group(1)}.  ")
                self._mc(0, 5.5, self._inline_format(ol_match.group(2)))
                self.set_x(x0)
                i += 1
                continue

            # ── 分隔线 ──
            if re.match(r"^[-*_]{3,}$", stripped):
                self.set_draw_color(180, 180, 180)
                y = self.get_y()
                self.line(self.get_x(), y, self.get_x() + self.w - 2 * self.l_margin, y)
                self.ln(5)
                i += 1
                continue

            # ── 表格 ──
            if stripped.startswith("|") and stripped.endswith("|"):
                i = self._write_table(lines, i)
                continue

            # ── 普通段落 ──
            self._cjk("", 10)
            self._mc(0, 5.5, self._inline_format(stripped))
            i += 1

    def _write_table(self, lines, start_idx):
        """解析并写入 Markdown 表格"""
        rows = []
        while start_idx < len(lines):
            line = lines[start_idx].strip()
            if not (line.startswith("|") and line.endswith("|")):
                break
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
            start_idx += 1

        if len(rows) < 1:
            return start_idx

        # 跳过表头分隔行
        header = rows[0]
        data = rows[2:] if len(rows) > 2 and re.match(r"^[\s:-]+$", rows[1][0]) else rows[1:]

        # 计算列宽
        col_count = min(len(header), 6)
        col_w = (self.w - 2 * self.l_margin) / col_count

        # 表头
        self.set_fill_color(230, 230, 240)
        self._cjk("B", 9)
        for h in header[:col_count]:
            self.cell(col_w, 7, h[:12], border=1, fill=True, align="C")
        self.ln()

        # 数据行
        self._cjk("", 9)
        for row in data[:20]:  # 最多 20 行
            for c in row[:col_count]:
                self.cell(col_w, 6, c[:16], border=1, align="L")
            self.ln()

        self.ln(4)
        return start_idx

    def _inline_format(self, text: str) -> str:
        """处理粗体、斜体、行内代码 → 纯文本输出（fpdf 不支持混合样式时的降级）"""
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        text = re.sub(r"~~(.+?)~~", r"\1", text)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        # 截断过长行
        if len(text) > 200:
            text = text[:197] + "..."
        return text

    def _escape(self, text: str) -> str:
        return text.replace("\t", "    ")


def markdown_to_pdf(
    content: str = "",
    file_path: str = "",
    title: str = "文档",
    author: str = "坐山客",
    output_name: str = "",
) -> str:
    """将 Markdown 转换为 PDF 文档

    Args:
        content: Markdown 文本内容（与 file_path 二选一）
        file_path: Markdown 文件路径（与 content 二选一）
        title: 文档标题（用于 PDF 元信息，默认"文档"）
        author: 文档作者（默认"坐山客"）
        output_name: 输出文件名（不含 .pdf，默认自动生成）

    Returns:
        JSON: {success, file_path, title, pages?, error?}
    """
    if FPDF is None:
        return json.dumps({"success": False, "error": "fpdf2 未安装，请运行: pip install fpdf2"})

    try:
        # ── 获取 Markdown 内容 ──
        md_text = ""
        source_desc = ""
        if file_path:
            if not os.path.exists(file_path):
                return json.dumps({"success": False, "error": f"文件不存在: {file_path}"})
            with open(file_path, "r", encoding="utf-8") as f:
                md_text = f.read()
            source_desc = os.path.basename(file_path)
        elif content:
            md_text = content
            source_desc = "直接输入"
        else:
            return json.dumps({"success": False, "error": "请提供 content 或 file_path"})

        # ── 查找字体 ──
        font_path = _find_cjk_font()

        # ── 生成 PDF ──
        pdf = PDF(font_path)
        pdf.set_title(title)
        pdf.set_author(author)

        # ── 封面页 ──
        pdf.add_page()
        pdf.ln(40)
        pdf._cjk("B", 24)
        pdf._mc(0, 12, title, align="C")
        pdf.ln(10)
        pdf._cjk("", 12)
        pdf._mc(0, 8, f"作者: {author}", align="C")
        pdf._mc(0, 8, f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")
        pdf._mc(0, 8, f"来源: {source_desc}", align="C")

        # ── 正文 ──
        pdf.add_page()
        pdf.write_markdown(md_text)

        # ── 保存 ──
        if not output_name:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r"[^\w\u4e00-\u9fff_-]", "_", title)[:30]
            output_name = f"{safe_title}_{ts}"
        output_path = str(OUTPUT_DIR / f"{output_name}.pdf")
        pdf.output(output_path)

        return json.dumps({
            "success": True,
            "file_path": output_path,
            "title": title,
            "pages": pdf.page,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
