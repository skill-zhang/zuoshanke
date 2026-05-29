#!/usr/bin/env python3
"""Generate PDF report for 坐山客 vs 国内外AI平台 comparison"""
from fpdf import FPDF

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_font("CJK", "", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", uni=True)
pdf.add_font("CJK", "B", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", uni=True)

with open("/home/administrator/zuoshanke/坐山客_vs_国内外AI平台_对比分析报告.md", "r", encoding="utf-8") as f:
    content = f.read()

pdf.add_page()
pdf.set_font("CJK", "B", 18)
pdf.cell(0, 10, "坐山客 vs 国内外 AI Agent 平台", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 10, "能力对比分析报告", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("CJK", "", 10)
pdf.cell(0, 8, "生成日期：2025年7月 | 数据来源：各平台官方文档/产品说明/官网", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)

lines = content.split("\n")
for line in lines:
    stripped = line.strip()
    
    if stripped.startswith("### "):
        pdf.set_font("CJK", "B", 13)
        pdf.cell(0, 8, stripped.replace("### ", ""), new_x="LMARGIN", new_y="NEXT")
    elif stripped.startswith("## "):
        pdf.set_font("CJK", "B", 15)
        pdf.ln(3)
        pdf.cell(0, 9, stripped.replace("## ", ""), new_x="LMARGIN", new_y="NEXT")
    elif stripped.startswith("# ") and not stripped.startswith("##"):
        pass  # skip main title
    elif stripped.startswith("|") and stripped.endswith("|"):
        pdf.set_font("CJK", "", 8)
        # Check if it's a header separator row
        if "---" in stripped:
            continue
        pdf.cell(0, 5, stripped, new_x="LMARGIN", new_y="NEXT")
    elif stripped.startswith("> "):
        pdf.set_font("CJK", "", 10)
        pdf.cell(0, 6, stripped.replace("> ", ""), new_x="LMARGIN", new_y="NEXT")
    elif stripped.startswith("```"):
        continue
    elif stripped.startswith("---"):
        pdf.ln(3)
    elif stripped.startswith("**"):
        pdf.set_font("CJK", "B", 10)
        pdf.cell(0, 6, stripped, new_x="LMARGIN", new_y="NEXT")
    elif stripped:
        pdf.set_font("CJK", "", 10)
        pdf.cell(0, 6, stripped, new_x="LMARGIN", new_y="NEXT")

output_path = "/home/administrator/zuoshanke/坐山客_vs_国内外AI平台_对比分析报告.pdf"
pdf.output(output_path)
print(f"PDF generated: {output_path}")
