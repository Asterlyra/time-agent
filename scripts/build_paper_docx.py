"""Render paper/main.md into a Word document (small markdown subset).

Supported: #/##/### headings, paragraphs, bullet and numbered lists, pipe tables,
images (![alt](path)), **bold**, *italic*, inline `code`, and block quotes.
Run with the bundled Python that provides python-docx.
"""
import argparse
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

EMPHASIS = re.compile(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)')


def add_runs(paragraph, text):
    for piece in EMPHASIS.split(text):
        if not piece:
            continue
        if piece.startswith('**') and piece.endswith('**'):
            run = paragraph.add_run(piece[2:-2])
            run.bold = True
        elif piece.startswith('`') and piece.endswith('`'):
            run = paragraph.add_run(piece[1:-1])
            run.font.name = 'Menlo'
            run.font.size = Pt(9)
        elif piece.startswith('*') and piece.endswith('*') and len(piece) > 2:
            run = paragraph.add_run(piece[1:-1])
            run.italic = True
        else:
            paragraph.add_run(piece)


def style_document(document):
    normal = document.styles['Normal']
    normal.font.name = 'Times New Roman'
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.15
    for name, size, color in (('Heading 1', 15, 0x1a1a1a), ('Heading 2', 12.5, 0x1a1a1a),
                              ('Heading 3', 11, 0x333333)):
        style = document.styles[name]
        style.font.size = Pt(size)
        style.font.name = 'Times New Roman'
        style.font.color.rgb = RGBColor((color >> 16) & 255, (color >> 8) & 255, color & 255)
        style.paragraph_format.space_before = Pt(10)
        style.paragraph_format.space_after = Pt(4)


def add_table(document, rows):
    header, body = rows[0], rows[1:]
    table = document.add_table(rows=1, cols=len(header))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, cell in enumerate(header):
        paragraph = table.rows[0].cells[i].paragraphs[0]
        run = paragraph.add_run(cell)
        run.bold = True
        run.font.size = Pt(9)
    for row in body:
        cells = table.add_row().cells
        for i, value in enumerate(row[:len(header)]):
            paragraph = cells[i].paragraphs[0]
            run = paragraph.add_run(value)
            run.font.size = Pt(9)
            if i > 0:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER


def build(markdown_path, out_path, figure_root):
    document = Document()
    style_document(document)
    lines = Path(markdown_path).read_text().splitlines()
    i, first_heading = 0, True
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith('|') and i + 1 < len(lines) and set(lines[i + 1].replace('|', '').strip()) <= set('-: '):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not set(''.join(cells)) <= set('-: '):
                    rows.append(cells)
                i += 1
            add_table(document, rows)
            document.add_paragraph()
            continue
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            text = line[level:].strip()
            if level == 1 and first_heading:
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = paragraph.add_run(text)
                run.bold = True
                run.font.size = Pt(17)
                first_heading = False
            else:
                document.add_heading(text, level=min(level - 1, 3))
            i += 1
            continue
        image = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line)
        if image:
            path = Path(figure_root) / image.group(2)
            if path.exists():
                document.add_picture(str(path), width=Inches(6.4))
                document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1
            continue
        if line.startswith('---'):
            i += 1
            continue
        if line.startswith('- '):
            paragraph = document.add_paragraph(style='List Bullet')
            add_runs(paragraph, line[2:])
            i += 1
            continue
        if re.match(r'^\d+\.\s', line):
            paragraph = document.add_paragraph(style='List Number')
            add_runs(paragraph, re.sub(r'^\d+\.\s', '', line))
            i += 1
            continue
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.first_line_indent = Pt(0)
        add_runs(paragraph, line)
        i += 1
    document.save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--markdown', default='paper/main.md')
    parser.add_argument('--out', default='paper/latency_summaries_paper.docx')
    args = parser.parse_args()
    print(build(args.markdown, args.out, Path(args.markdown).parent))


if __name__ == '__main__':
    main()
