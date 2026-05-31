#!/usr/bin/env python3
import os
from fpdf import FPDF

md_dir = "/home/administrator/zuoshanke"
# List files to find the md file
files = os.listdir(md_dir)
for f in files:
    if f.endswith(".md") and "对比" in f:
        md_file = os.path.join(md_dir, f)
        break

pdf_file = os.path.join(md_dir, "zuoshanke_vs_ai_platforms_report.pdf")

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_font("CJK", "", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
pdf.add_font("CJK", "B", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")

with open(md_file, "r", encoding="utf-8") as f:
    content = f.read()

pdf.add_page()
pdf.set_font("CJK", "B", 18)
pdf.cell(0, 10, "Zuoshanke vs AI Agent Platforms", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 10, "Capability Comparison Report", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("CJK", "", 10)
pdf.cell(0, 8, "Date: 2025.07 | Sources: Official docs/websites", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)

lines = content.split("\n")
for line in lines:
    s = line.strip()
    if s.startswith("### "):
        pdf.set_font("CJK", "B", 13)
        pdf.cell(0, 8, s[4:], new_x="LMARGIN", new_y="NEXT")
    elif s.startswith("## "):
        pdf.set_font("CJK", "B", 15)
        pdf.ln(3)
        pdf.cell(0, 9, s[3:], new_x="LMARGIN", new_y="NEXT")
    elif s.startswith("|") and s.endswith("|"):
        if "---" in s:
            continue
        pdf.set_font("CJK", "", 7)
        pdf.cell(0, 4, s, new_x="LMARGIN", new_y="NEXT")
    elif s.startswith("> "):
        pdf.set_font("CJK", "", 9)
        pdf.cell(0, 6, s[2:], new_x="LMARGIN", new_y="NEXT")
    elif s.startswith("---"):
        pdf.ln(3)
    elif s.startswith("**") and s.endswith("**"):
        pdf.set_font("CJK", "B", 10)
        pdf.cell(0, 6, s, new_x="LMARGIN", new_y="NEXT")
    elif s.startswith("```"):
        continue
    elif s:
        pdf.set_font("CJK", "", 10)
        pdf.cell(0, 6, s, new_x="LMARGIN", new_y="NEXT")

pdf.output(pdf_file)
print(f"PDF saved: {pdf_file}")
