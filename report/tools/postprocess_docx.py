#!/usr/bin/env python3
"""Apply formal academic layout, live fields, and table/figure styling to a Pandoc DOCX."""

from __future__ import annotations

import re
import sys
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


def set_run_fonts(run, latin: str, east_asia: str, size: float | None = None) -> None:
    run.font.name = latin
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    fonts.set(qn("w:ascii"), latin)
    fonts.set(qn("w:hAnsi"), latin)
    fonts.set(qn("w:eastAsia"), east_asia)
    fonts.set(qn("w:cs"), east_asia)
    if size is not None:
        run.font.size = Pt(size)


def configure_style(style, latin: str, east_asia: str, size: float, bold=False, italic=False) -> None:
    style.font.name = latin
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = italic
    style.font.color.rgb = RGBColor(0, 0, 0)
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    fonts.set(qn("w:ascii"), latin)
    fonts.set(qn("w:hAnsi"), latin)
    fonts.set(qn("w:eastAsia"), east_asia)
    fonts.set(qn("w:cs"), east_asia)


def add_field(paragraph, instruction: str, cached: str, bookmark: str | None = None, bookmark_id: int = 0):
    if bookmark:
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(bookmark_id))
        start.set(qn("w:name"), bookmark)
        paragraph._p.append(start)

    begin = OxmlElement("w:r")
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    begin.append(fld_begin)
    paragraph._p.append(begin)

    instr_run = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    instr_run.append(instr)
    paragraph._p.append(instr_run)

    separate = OxmlElement("w:r")
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    separate.append(fld_sep)
    paragraph._p.append(separate)

    value_run = paragraph.add_run(cached)

    end = OxmlElement("w:r")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    end.append(fld_end)
    paragraph._p.append(end)

    if bookmark:
        stop = OxmlElement("w:bookmarkEnd")
        stop.set(qn("w:id"), str(bookmark_id))
        paragraph._p.append(stop)
    return value_run


def clear_paragraph(paragraph) -> None:
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        # Shading must appear before textDirection/tcFitText/vAlign in tcPr.
        inserted = False
        for child in list(tc_pr):
            if child.tag in {qn("w:textDirection"), qn("w:tcFitText"), qn("w:vAlign"), qn("w:hideMark"), qn("w:headers")}:
                tc_pr.insert(tc_pr.index(child), shd)
                inserted = True
                break
        if not inserted:
            tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = tr_pr.find(qn("w:tblHeader"))
    if header is None:
        header = OxmlElement("w:tblHeader")
        tr_pr.append(header)
    header.attrib.pop(qn("w:val"), None)


def set_fixed_column_widths(table, widths) -> None:
    """Set a stable printable grid so narrow numeric columns do not split digits."""
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")
    for column, width in zip(table.columns, widths):
        column.width = width
        for cell in column.cells:
            cell.width = width


def add_footer_fields(section, english: bool, latin: str, east_asia: str) -> None:
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    clear_paragraph(p)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    if english:
        set_run_fonts(p.add_run("Page "), latin, east_asia, 9)
        set_run_fonts(add_field(p, "PAGE", "1"), latin, east_asia, 9)
        set_run_fonts(p.add_run(" of "), latin, east_asia, 9)
        set_run_fonts(add_field(p, "NUMPAGES", "1"), latin, east_asia, 9)
    else:
        set_run_fonts(p.add_run("第 "), latin, east_asia, 9)
        set_run_fonts(add_field(p, "PAGE", "1"), latin, east_asia, 9)
        set_run_fonts(p.add_run(" 页，共 "), latin, east_asia, 9)
        set_run_fonts(add_field(p, "NUMPAGES", "1"), latin, east_asia, 9)
        set_run_fonts(p.add_run(" 页"), latin, east_asia, 9)


def append_ref_field_after(run, label: str, number: int, bookmark: str, latin: str, east_asia: str) -> None:
    parent = run._r.getparent()
    insert_at = parent.index(run._r) + 1
    pieces = []
    prefix_r = OxmlElement("w:r")
    if run._r.rPr is not None:
        prefix_r.append(deepcopy(run._r.rPr))
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = label
    prefix_r.append(t)
    pieces.append(prefix_r)
    for kind, text in (("begin", None), ("instr", f" REF {bookmark} \\h "), ("separate", None), ("text", str(number)), ("end", None)):
        r = OxmlElement("w:r")
        if run._r.rPr is not None:
            r.append(deepcopy(run._r.rPr))
        if kind in {"begin", "separate", "end"}:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), kind)
            r.append(fld)
        elif kind == "instr":
            node = OxmlElement("w:instrText")
            node.set(qn("xml:space"), "preserve")
            node.text = text
            r.append(node)
        else:
            node = OxmlElement("w:t")
            node.text = text
            r.append(node)
        pieces.append(r)
    for offset, element in enumerate(pieces):
        parent.insert(insert_at + offset, element)


def convert_body_refs(doc, english: bool, latin: str, east_asia: str) -> None:
    pattern = re.compile(r"\b(Figure|Table)\s+(\d+)" if english else r"(图|表)\s*(\d+)")
    for paragraph in doc.paragraphs:
        if paragraph.style and paragraph.style.name in {"Caption", "Title", "TOC Heading"}:
            continue
        for run in list(paragraph.runs):
            text = run.text
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            # Process only the first reference in a run; source paragraphs rarely group multiple labeled refs.
            match = matches[0]
            before, after = text[:match.start()], text[match.end():]
            run.text = before
            label = match.group(1) + (" " if english else " ")
            number = int(match.group(2))
            key = ("fig" if match.group(1) in {"Figure", "图"} else "tbl") + str(number)
            append_ref_field_after(run, label, number, key, latin, east_asia)
            tail = OxmlElement("w:r")
            if run._r.rPr is not None:
                tail.append(deepcopy(run._r.rPr))
            t = OxmlElement("w:t")
            t.set(qn("xml:space"), "preserve")
            t.text = after
            tail.append(t)
            parent = run._r.getparent()
            parent.insert(parent.index(run._r) + 7, tail)


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[3] not in {"cn", "en"}:
        raise SystemExit("usage: postprocess_docx.py INPUT.docx OUTPUT.docx cn|en")
    source, output, language = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    english = language == "en"
    # LibreOffice on macOS may ignore w:eastAsia and select w:hAnsi for CJK runs.
    # Use one CJK-capable serif family for every script in the Chinese edition so
    # Chinese stays visible both in Word and in the required PDF render check.
    latin = "Times New Roman" if english else "Arial Unicode MS"
    east_asia = "Times New Roman" if english else "Arial Unicode MS"
    doc = Document(source)

    # Ask Word to refresh PAGE/NUMPAGES, SEQ, and REF fields on open.
    update_fields = doc.settings.element.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        # CT_Settings is order-sensitive; updateFields belongs before rsids and
        # the language/color/list separator tail elements.
        rsids = doc.settings.element.find(qn("w:rsids"))
        if rsids is None:
            doc.settings.element.append(update_fields)
        else:
            doc.settings.element.insert(doc.settings.element.index(rsids), update_fields)
    update_fields.set(qn("w:val"), "true")

    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)
        section.header_distance = Cm(1.25)
        section.footer_distance = Cm(1.25)
        add_footer_fields(section, english, latin, east_asia)

    styles = doc.styles
    configure_style(styles["Normal"], latin, east_asia, 11)
    normal = styles["Normal"].paragraph_format
    normal.line_spacing = 1.5
    normal.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.first_line_indent = Cm(0.74 if not english else 1.0)
    normal.space_after = Pt(0)

    configure_style(styles["Title"], latin, east_asia, 20, bold=True)
    styles["Title"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    styles["Title"].paragraph_format.space_after = Pt(18)
    styles["Title"].paragraph_format.keep_with_next = True

    heading_specs = [("Heading 1", 16, True, False, 18, 9), ("Heading 2", 14, True, False, 15, 6),
                     ("Heading 3", 12, True, False, 12, 4), ("Heading 4", 11, True, True, 10, 3),
                     ("Heading 5", 11, False, True, 8, 3), ("Heading 6", 11, False, True, 8, 3)]
    for name, size, bold, italic, before, after in heading_specs:
        configure_style(styles[name], latin, east_asia, size, bold=bold, italic=italic)
        pf = styles[name].paragraph_format
        pf.space_before = Pt(before)
        pf.space_after = Pt(after)
        pf.keep_with_next = True
        pf.keep_together = True
        pf.first_line_indent = Cm(0)
        if name == "Heading 1":
            pf.page_break_before = True

    if "Caption" not in [style.name for style in styles]:
        styles.add_style("Caption", WD_STYLE_TYPE.PARAGRAPH)
    configure_style(styles["Caption"], latin, east_asia, 10.5, italic=False)
    cap_pf = styles["Caption"].paragraph_format
    cap_pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap_pf.line_spacing = 1.15
    cap_pf.first_line_indent = Cm(0)
    cap_pf.space_before = Pt(6)
    cap_pf.space_after = Pt(6)
    cap_pf.keep_together = True

    for style_name in ("TOC Heading", "TOC 1", "TOC 2", "TOC 3"):
        if style_name in [style.name for style in styles]:
            configure_style(styles[style_name], latin, east_asia, 11 if style_name != "TOC Heading" else 14, bold=style_name == "TOC Heading")

    # Convert visible captions into live SEQ fields with bookmarks and deterministic cached numbers.
    caption_re = re.compile(r"^(Table|Figure)\s+(\d+)\.\s*(.*)$")
    existing_ids = [int(node.get(qn("w:id"))) for node in doc.element.body.iter(qn("w:bookmarkStart")) if (node.get(qn("w:id")) or "").isdigit()]
    bookmark_id = (max(existing_ids) + 1) if existing_ids else 1
    for paragraph in doc.paragraphs:
        match = caption_re.match(paragraph.text.strip())
        if not match:
            continue
        kind, number, title = match.group(1), int(match.group(2)), match.group(3)
        clear_paragraph(paragraph)
        paragraph.style = styles["Caption"]
        set_run_fonts(paragraph.add_run(f"{kind} "), latin, east_asia, 10.5)
        value_run = add_field(paragraph, f"SEQ {kind} \\* ARABIC", str(number), f"{'tbl' if kind == 'Table' else 'fig'}{number}", bookmark_id)
        set_run_fonts(value_run, latin, east_asia, 10.5)
        bookmark_id += 1
        set_run_fonts(paragraph.add_run(f". {title}"), latin, east_asia, 10.5)
        if kind == "Table":
            paragraph.paragraph_format.keep_with_next = True

    # Keep the source's explicit body references (for example, "Figure 1") as
    # stable visible text. Word/LibreOffice differ in REF bookmark refresh rules,
    # while the numbered captions themselves remain live SEQ fields.

    # Pandoc emits a second paragraph from image alt text. The formal numbered
    # caption below each figure already contains that title, so remove duplicates.
    for paragraph in list(doc.paragraphs):
        if paragraph.style and paragraph.style.name == "Image Caption":
            parent = paragraph._p.getparent()
            if parent is not None:
                parent.remove(paragraph._p)

    # Abstract and keywords are block paragraphs with no first-line indent.
    in_abstract = False
    in_references = False
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        style_name = paragraph.style.name if paragraph.style else ""
        if style_name == "Heading 1":
            in_abstract = text.lower() == "abstract"
            in_references = text in {"参考文献", "References"}
        elif style_name.startswith("Heading"):
            in_abstract = False
        if in_abstract or text.startswith("关键词") or text.lower().startswith("keywords"):
            paragraph.paragraph_format.first_line_indent = Cm(0)
        if in_references and re.match(r"^\[\d+\]", text):
            paragraph.paragraph_format.left_indent = Cm(0.74)
            paragraph.paragraph_format.first_line_indent = Cm(-0.74)
            paragraph.paragraph_format.line_spacing = 1.5
        if style_name in {"Body Text", "First Paragraph"} and not in_abstract:
            paragraph.paragraph_format.first_line_indent = Cm(0.74 if not english else 1.0)
            paragraph.paragraph_format.line_spacing = 1.5
            paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            paragraph.paragraph_format.space_after = Pt(0)
        for run in paragraph.runs:
            set_run_fonts(run, latin, east_asia)

    # Style all tables for readable A4 portrait layout.
    for table in doc.tables:
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True
        header_text = [cell.text.strip() for cell in table.rows[0].cells] if table.rows else []
        compact_metrics = (
            (len(table.columns) == 5 and header_text and header_text[0] in {"Setting", "Experiment"})
            or (len(table.columns) == 7 and header_text and header_text[0] == "Method")
        )
        if len(table.columns) == 4:
            # The CEP pattern table contains long hyphenated names in column 1.
            # Give it a deliberate grid so names wrap by words, not characters.
            widths = [Inches(1.50), Inches(1.85), Inches(1.40), Inches(1.50)]
            set_fixed_column_widths(table, widths)
        elif len(table.columns) == 5 and header_text and header_text[0] in {"Setting", "Experiment"}:
            # Ablation-result tables need enough width for each decimal metric.
            set_fixed_column_widths(
                table,
                [Inches(2.55), Inches(0.72), Inches(0.72), Inches(0.72), Inches(1.54)],
            )
        elif len(table.columns) == 7 and header_text and header_text[0] == "Method":
            # Keep decimal results on one line in the compact ML comparison table.
            set_fixed_column_widths(
                table,
                [Inches(1.66), Inches(0.68), Inches(0.68), Inches(0.55),
                 Inches(0.86), Inches(0.91), Inches(0.91)],
            )
        if "Table Grid" in [style.name for style in styles]:
            table.style = styles["Table Grid"]
        if table.rows:
            set_repeat_table_header(table.rows[0])
        for row_index, row in enumerate(table.rows):
            for cell in row.cells:
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                if row_index == 0:
                    shade_cell(cell, "D9E2F3")
                elif row_index % 2 == 0:
                    shade_cell(cell, "F7F9FC")
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.first_line_indent = Cm(0)
                    paragraph.paragraph_format.line_spacing = 1.15
                    paragraph.paragraph_format.space_after = Pt(2)
                    for run in paragraph.runs:
                        set_run_fonts(run, latin, east_asia, 9.5 if compact_metrics else 10.5)
                        if row_index == 0:
                            run.bold = True

    # Scale inline figures to the printable width and keep them with captions.
    max_width = Inches(6.25)
    for shape in doc.inline_shapes:
        if shape.width > max_width:
            ratio = max_width / shape.width
            shape.width = max_width
            shape.height = int(shape.height * ratio)
        parent_p = shape._inline.getparent().getparent()
        for paragraph in doc.paragraphs:
            if paragraph._p is parent_p:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.first_line_indent = Cm(0)
                paragraph.paragraph_format.keep_with_next = True
                break

    # Pandoc emits optional OMML hints that some strict validators reject.
    # They are not needed for rendering because matrix column count and run style are inferable.
    for tag in ("{http://schemas.openxmlformats.org/officeDocument/2006/math}count",
                "{http://schemas.openxmlformats.org/officeDocument/2006/math}sty"):
        for node in list(doc.element.iter(tag)):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)


if __name__ == "__main__":
    main()
