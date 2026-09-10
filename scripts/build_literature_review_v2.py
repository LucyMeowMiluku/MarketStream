"""Build the styled English MarketStream literature review DOCX."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "LITERATURE_REVIEW_V2.docx"

BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
NAVY = "203748"
SUBTITLE = "2B5163"
GOLD = "7A5A00"
MUTED = "666666"
LIGHT_FILL = "F4F6F9"
WHITE = "FFFFFF"
CONTENT_DXA = 9360
TABLE_INDENT_DXA = 120


def rgb(hex_value: str) -> RGBColor:
    return RGBColor.from_string(hex_value)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths_dxa: list[int]) -> None:
    if sum(widths_dxa) != CONTENT_DXA:
        raise ValueError("table widths must sum to 9360 DXA")
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    tbl_w.set(qn("w:w"), str(CONTENT_DXA))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.first_child_found_in("w:tblInd")
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(TABLE_INDENT_DXA))
    tbl_ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_dxa:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for index, cell in enumerate(row.cells):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.first_child_found_in("w:tcW")
            tc_w.set(qn("w:w"), str(widths_dxa[index]))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def add_hyperlink(paragraph, text: str, url: str, color: str = BLUE) -> None:
    part = paragraph.part
    relationship_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    run_properties = OxmlElement("w:rPr")
    run_color = OxmlElement("w:color")
    run_color.set(qn("w:val"), color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_properties.extend((run_color, underline))
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.extend((run_properties, text_node))
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run()
    field_begin = OxmlElement("w:fldChar")
    field_begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    field_end = OxmlElement("w:fldChar")
    field_end.set(qn("w:fldCharType"), "end")
    run._r.extend((field_begin, instruction, field_end))


def add_numbering(doc: Document, *, bullet: bool) -> int:
    numbering = doc.part.numbering_part.element
    abstract_ids = [int(node.get(qn("w:abstractNumId"))) for node in numbering.findall(qn("w:abstractNum"))]
    num_ids = [int(node.get(qn("w:numId"))) for node in numbering.findall(qn("w:num"))]
    abstract_id = max(abstract_ids, default=0) + 1
    num_id = max(num_ids, default=0) + 1

    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi = OxmlElement("w:multiLevelType")
    multi.set(qn("w:val"), "singleLevel")
    abstract.append(multi)
    level = OxmlElement("w:lvl")
    level.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), "bullet" if bullet else "decimal")
    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(qn("w:val"), "•" if bullet else "%1.")
    lvl_jc = OxmlElement("w:lvlJc")
    lvl_jc.set(qn("w:val"), "left")
    p_pr = OxmlElement("w:pPr")
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "num")
    tab.set(qn("w:pos"), "540")
    tabs.append(tab)
    indent = OxmlElement("w:ind")
    indent.set(qn("w:left"), "540")
    indent.set(qn("w:hanging"), "280")
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:after"), "80")
    spacing.set(qn("w:line"), "290")
    spacing.set(qn("w:lineRule"), "auto")
    p_pr.extend((tabs, indent, spacing))
    level.extend((start, num_fmt, lvl_text, lvl_jc, p_pr))
    abstract.append(level)
    numbering.append(abstract)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), str(abstract_id))
    num.append(abstract_ref)
    numbering.append(num)
    return num_id


def apply_num(paragraph, num_id: int) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = p_pr.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        p_pr.append(num_pr)
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_id_node = OxmlElement("w:numId")
    num_id_node.set(qn("w:val"), str(num_id))
    num_pr.extend((ilvl, num_id_node))


def configure_document(doc: Document) -> tuple[int, int]:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = rgb("000000")
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.333

    tokens = {
        "Heading 1": (16, BLUE, 18, 10),
        "Heading 2": (13, BLUE, 12, 6),
        "Heading 3": (12, DARK_BLUE, 8, 4),
    }
    for style_name, (size, color, before, after) in tokens.items():
        style = doc.styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = rgb(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    for name in ("Review Bullet", "Review Number"):
        style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.base_style = normal
        style.font.name = "Calibri"
        style.font.size = Pt(11)
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.208

    citation = doc.styles.add_style("Table Citation", WD_STYLE_TYPE.PARAGRAPH)
    citation.base_style = normal
    citation.font.name = "Calibri"
    citation.font.size = Pt(9)
    citation.font.italic = True
    citation.font.color.rgb = rgb(MUTED)
    citation.paragraph_format.space_before = Pt(4)
    citation.paragraph_format.space_after = Pt(4)
    citation.paragraph_format.line_spacing = 1.0

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header.paragraph_format.space_after = Pt(0)
    run = header.add_run("MARKETSTREAM  /  CROSS-DOMAIN ANOMALY DETECTION")
    run.font.name = "Calibri"
    run.font.size = Pt(8.5)
    run.font.bold = True
    run.font.color.rgb = rgb(MUTED)
    footer = section.footer.paragraphs[0]
    footer_run = footer.add_run("Literature Review V2   •   ")
    footer_run.font.name = "Calibri"
    footer_run.font.size = Pt(8.5)
    footer_run.font.color.rgb = rgb(MUTED)
    add_page_number(footer)
    return add_numbering(doc, bullet=True), add_numbering(doc, bullet=False)


def add_body(doc: Document, text: str, *, bold_lead: str | None = None) -> None:
    paragraph = doc.add_paragraph()
    if bold_lead and text.startswith(bold_lead):
        run = paragraph.add_run(bold_lead)
        run.bold = True
        paragraph.add_run(text[len(bold_lead) :])
    else:
        paragraph.add_run(text)


def add_bullets(doc: Document, items: list[str], num_id: int) -> None:
    for item in items:
        paragraph = doc.add_paragraph(style="Review Bullet")
        apply_num(paragraph, num_id)
        paragraph.add_run(item)


def add_table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    set_table_geometry(table, widths)
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        shade_cell(cell, LIGHT_FILL)
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(header)
        run.bold = True
        run.font.color.rgb = rgb(NAVY)
    set_repeat_table_header(table.rows[0])
    for row_values in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row_values):
            paragraph = cells[index].paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
            run = paragraph.add_run(value)
            run.font.size = Pt(9.5)
    set_table_geometry(table, widths)


def add_cover(doc: Document) -> None:
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(100)
    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_after = Pt(18)
    run = kicker.add_run("LITERATURE REVIEW  /  VERSION 2")
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = rgb(GOLD)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(8)
    run = title.add_run("Lightweight, Explainable Anomaly Detection\nfor Streaming Financial Markets")
    run.bold = True
    run.font.size = Pt(30)
    run.font.color.rgb = rgb(NAVY)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(28)
    run = subtitle.add_run(
        "A cross-domain synthesis of medical early warning, industrial and aerospace monitoring, "
        "cybersecurity, streaming benchmarks, and market microstructure"
    )
    run.font.size = Pt(15)
    run.font.color.rgb = rgb(SUBTITLE)

    descriptor = doc.add_paragraph()
    descriptor.alignment = WD_ALIGN_PARAGRAPH.CENTER
    descriptor.paragraph_format.space_after = Pt(82)
    run = descriptor.add_run("—  Design basis for the MarketStream factor-and-CEP architecture  —")
    run.italic = True
    run.font.size = Pt(10.5)
    run.font.color.rgb = rgb(GOLD)

    metadata = doc.add_paragraph()
    metadata.alignment = WD_ALIGN_PARAGRAPH.CENTER
    metadata.paragraph_format.space_after = Pt(4)
    run = metadata.add_run("6 August 2026")
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = rgb(NAVY)
    prepared = doc.add_paragraph()
    prepared.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = prepared.add_run("MarketStream Capstone Project  •  Nanyang Technological University")
    run.italic = True
    run.font.size = Pt(9.5)
    run.font.color.rgb = rgb(MUTED)
    prepared.add_run().add_break(WD_BREAK.PAGE)


def build() -> Path:
    doc = Document()
    bullet_id, _ = configure_document(doc)
    add_cover(doc)

    doc.add_heading("Executive Summary", level=1)
    add_body(
        doc,
        "This review reframes MarketStream from a four-model anomaly ensemble into a lightweight, "
        "factor-and-complex-event-processing system. The cross-domain evidence does not imply that "
        "machine learning is useless. It shows something more specific: in online anomaly detection, "
        "data definitions, robust baselines, persistence, event context, and evaluation design often "
        "matter more than adding a more elaborate model. The strongest transferable ideas are few "
        "interpretable measurements, bounded incremental state, context-conditioned baselines, "
        "multi-signal confirmation, and event-level evaluation. [1–9]"
    )
    add_body(
        doc,
        "The recommended production design therefore computes eight financially meaningful factors "
        "from trades, quotes, bars, market benchmarks, and timestamped news. It evaluates six "
        "directional temporal patterns and stores the evidence chain from alert to factor snapshot to "
        "source event. The existing ensemble remains valuable as an offline baseline and shadow system, "
        "but it should not block the real-time path."
    )
    add_table(
        doc,
        ["Decision", "Evidence from the review", "MarketStream consequence"],
        [
            ["Prefer factors over model proliferation", "Simple methods remain competitive on large time-series benchmarks; domain transformations improve interpretability.", "Eight fixed factors; no new deep anomaly model."],
            ["Make temporal semantics explicit", "Medical scores, industrial residuals, and cyber event correlation depend on persistence and sequence.", "Six CEP patterns with direction, start time, completion time, and cooldown."],
            ["Treat coverage and quality as data", "Streaming systems fail through gaps, duplicates, stale inputs, and changing operating contexts.", "Unified MarketEvent, quality flags, separate pre/regular/post baselines."],
            ["Evaluate events, not nearby points", "Tolerance-window scoring can reward early or duplicate detections and obscure operational burden.", "Forward one-to-one matching, delay, alert rate, duplicate rate, and bootstrap intervals."],
        ],
        [1800, 3600, 3960],
    )
    paragraph = doc.add_paragraph(style="Table Citation")
    paragraph.add_run("Synthesis based on sources [1–16]; implementation implications are the author's design inference.")

    doc.add_page_break()
    doc.add_heading("Contents", level=1)
    contents = [
        ("1. Research Problem and Scope", 4),
        ("2. Cross-Domain Design Patterns", 4),
        ("3. Medical Early Warning", 5),
        ("4. Industrial and Aerospace Monitoring", 6),
        ("5. Cybersecurity", 6),
        ("6. General Streaming Detection", 7),
        ("7. Financial Market Anomaly Evidence", 8),
        ("8. Proposed Factor and CEP Architecture", 9),
        ("9. Research Protocol and Falsifiable Claims", 9),
        ("10. Threats to Validity and Limitations", 10),
        ("11. Conclusion", 11),
        ("References", 11),
    ]
    for label, page in contents:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(3)
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(6.25))
        run = paragraph.add_run(label)
        run.font.size = Pt(10)
        page_run = paragraph.add_run(f"\t{page}")
        page_run.bold = True
        page_run.font.size = Pt(10)
    doc.add_heading("Reading Guide", level=2)
    add_body(
        doc,
        "Sections 1–7 establish the problem definition and cross-domain evidence. Section 8 turns "
        "that evidence into the eight-factor, six-pattern architecture. Sections 9–10 define the "
        "falsifiable protocol and limitations that must govern the final experiments."
    )
    add_body(
        doc,
        "Readers reviewing implementation choices can begin with Sections 8–10; readers evaluating "
        "the academic rationale should follow the document in order."
    )
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    doc.add_heading("1. Research Problem and Scope", level=1)
    doc.add_heading("1.1 The operational definition of an anomaly", level=2)
    add_body(
        doc,
        "A market anomaly is not simply a large return. A large price move may be expected after an "
        "earnings release, shared across the market during a macro shock, mechanically widened during "
        "post-market trading, or corrupted by a stale or crossed quote. Conversely, a modest price move "
        "may be operationally important when it follows persistent one-sided order pressure or "
        "stock-specific news. The research object is therefore a contextual event: a time-bounded "
        "combination of deviations with direction, duration, market regime, and evidence provenance."
    )
    add_body(
        doc,
        "This definition changes the detector's job. A point score is still useful as an atomic signal, "
        "but the final decision must distinguish signal groups and event timing. Price, activity, "
        "liquidity, market context, and news are deliberately separated so that two correlated price "
        "statistics do not masquerade as independent confirmation."
    )
    doc.add_heading("1.2 Why the earlier ensemble is now a baseline", level=2)
    add_body(
        doc,
        "The original EWMA, Half-Space Trees, Isolation Forest, and LSTM Autoencoder ensemble proved "
        "that multiple detectors could be integrated into Kafka and TimescaleDB. It also exposed "
        "research risks. Normalized detector scores concealed different meanings; the strongest weights "
        "concentrated on EWMA and Isolation Forest; historical sentiment was often absent; and synthetic "
        "point injection favored methods designed for isolated feature spikes. The appropriate response "
        "is not to discard the work, but to move it into a controlled comparison role."
    )
    add_bullets(
        doc,
        [
            "Production question: can a bounded, interpretable factor-and-CEP path detect meaningful market events with acceptable alert burden and latency?",
            "Comparative question: under a frozen event-level protocol, where does the legacy ML ensemble add recall or robustness beyond CEP?",
            "Scientific constraint: negative, null, and adverse results must be retained after thresholds are frozen.",
        ],
        bullet_id,
    )

    doc.add_heading("2. Cross-Domain Design Patterns", level=1)
    add_body(
        doc,
        "The reviewed fields use different sensors and consequences, but their successful online systems "
        "share a compact architecture. Raw observations are checked, transformed into domain variables, "
        "compared with a relevant baseline, accumulated across time or related entities, and emitted with "
        "an explanation and confidence. This is closer to a disciplined measurement system than to a "
        "leaderboard of interchangeable anomaly algorithms."
    )
    add_table(
        doc,
        ["Domain", "Typical lightweight evidence", "Temporal/context rule", "Transfer to markets"],
        [
            ["Medical early warning", "Small set of vital signs; piecewise scores", "Persistence, escalation, clinician review", "Factor groups, severity bands, warm-up suppression"],
            ["Industrial/aerospace", "Derived physical quantities; residuals", "Operating mode and confidence", "Session baselines, market residual, data quality"],
            ["Cybersecurity", "Counts, ratios, sketches, graph updates", "Correlation across events/entities", "Bounded ticker state, cross-asset pattern"],
            ["Generic streaming", "Robust statistics, online trees", "Prequential or chronological evaluation", "Median/MAD, frozen thresholds, replay parity"],
            ["Financial microstructure", "Returns, relative volume, spread, imbalance", "News and benchmark context", "Eight factors and six directional patterns"],
        ],
        [1500, 2600, 2500, 2760],
    )
    paragraph = doc.add_paragraph(style="Table Citation")
    paragraph.add_run("Cross-domain synthesis from [1], [4–9], and [14–18].")

    doc.add_heading("3. Medical Early Warning: Sparse Scores and Persistence", level=1)
    add_body(
        doc,
        "Clinical early warning systems demonstrate the value and the limits of sparse additive scores. "
        "The ViEWS study combined routinely recorded vital signs into a transparent aggregate and "
        "evaluated its ability to identify deterioration. [7] The transferable principle is not any "
        "particular clinical threshold; it is that a small number of measurements can be converted into "
        "severity bands that users understand and can audit."
    )
    add_body(
        doc,
        "A single abnormal measurement is rarely interpreted without context. Repeat observations, rate "
        "of change, and escalation protocols matter because measurements are noisy and interventions have "
        "cost. This maps directly to financial alerting: isolated elevated volume updates state, while a "
        "move confirmed by liquidity pressure or persistent imbalance can create a formal alert. Warm-up "
        "suppression plays the role of refusing to make strong claims before enough baseline observations "
        "exist."
    )
    add_body(
        doc,
        "The main warning is that simple point totals can lose information and create threshold effects. "
        "MarketStream therefore stores raw factor values, robust z-scores, state bands, and triggering "
        "event IDs rather than retaining only a total score. The score is an ordering aid; the evidence "
        "object is the scientific record."
    )

    doc.add_heading("4. Industrial and Aerospace Monitoring: Derived Quantities, Residuals, and Confidence", level=1)
    add_body(
        doc,
        "Industrial anomaly detection often benefits from variables with physical meaning: pressure "
        "ratios, temperature differences, rates, efficiencies, or residuals from an operating baseline. "
        "NIST's behavioral work for industrial control systems emphasizes detecting deviations while "
        "respecting the behavior of the monitored process. [8] This is more useful for MarketStream than "
        "treating every raw market field as an exchangeable input dimension."
    )
    add_body(
        doc,
        "NASA's MEDOS work describes an expert system for spaceflight telemetry that derives meaningful "
        "quantities, represents expectations with fuzzy sets, and exposes confidence and supporting "
        "information. [6] The important transfer is epistemic: a detector should say not only that a "
        "value is unusual, but which operating expectation was violated and how trustworthy the input "
        "was. MarketStream implements this with baseline versions, session labels, factor states, and "
        "quality flags."
    )
    add_body(
        doc,
        "Operating modes are essential. A spread that is extreme at noon may be normal after the close; "
        "volume at the opening should not be compared with volume at lunch. Baselines must therefore be "
        "conditioned on ticker, trading session, cadence, and intraday slot. The market residual is the "
        "financial analogue of a model residual: subtracting recent QQQ or SPY movement helps separate "
        "stock-specific dislocation from a broad shock."
    )

    doc.add_heading("5. Cybersecurity: Bounded State and Event Correlation", level=1)
    add_body(
        doc,
        "Network-security streams are high-volume, heterogeneous, and adversarial. Systems cannot retain "
        "an unbounded graph or complete packet history. StreamSpot showed that heterogeneous graph "
        "behavior can be summarized for fast, memory-efficient streaming anomaly detection. [5] More "
        "generally, security monitoring uses counts, ratios, sketches, and correlation across identities "
        "and time windows."
    )
    add_body(
        doc,
        "Complex event processing has also been applied to cyber monitoring of critical infrastructures, "
        "where the significance of an observation depends on event relationships rather than a single "
        "record. [9] The transfer to markets is direct: a news item, quote imbalance, and return are more "
        "informative as an ordered pattern than as three independently thresholded points."
    )
    add_bullets(
        doc,
        [
            "Bound all keyed state: tracked tickers, pattern history, source-event references, and deduplication memory.",
            "Keep ticker state isolated; only an explicit cross-asset rule may join entities.",
            "Treat cooldown and merge semantics as detector logic, not dashboard cleanup.",
        ],
        bullet_id,
    )

    doc.add_heading("6. General Streaming Detection and Benchmark Evidence", level=1)
    doc.add_heading("6.1 Simple methods remain serious baselines", level=2)
    add_body(
        doc,
        "Robust Random Cut Forests and Half-Space Trees illustrate two families of incremental anomaly "
        "detection that can operate without retraining a deep sequence model. [4,17] They remain useful "
        "offline comparators, especially when feature interactions are not easily expressed as rules. "
        "However, adding an online tree is not automatically a scientific contribution; its value must be "
        "shown under the same event labels, timing constraints, and alert budget."
    )
    doc.add_heading("6.2 Large benchmarks challenge architectural fashion", level=2)
    add_body(
        doc,
        "TSB-AD provides a broad benchmark for time-series anomaly detection and reports substantial "
        "variation across datasets and methods. [1] A central implication is that complex neural methods "
        "do not reliably dominate simple statistical or classical approaches. Benchmark rank is also "
        "sensitive to anomaly type, data preprocessing, and metric choice. This supports a factor-first "
        "design in which deep models must earn their production cost through a pre-specified ablation."
    )
    doc.add_heading("6.3 Evaluation can dominate the conclusion", level=2)
    add_body(
        doc,
        "The literature on unbiased time-series anomaly evaluation documents problems with point "
        "adjustment and tolerance rules that can inflate apparent performance. [2] NAB usefully included "
        "time-sensitive scoring and operational streams, but every application still needs a domain "
        "definition of what counts as a timely event. [3] For MarketStream, a detection cannot occur "
        "before event start, one detection can match only one event, and duplicate alerts remain counted."
    )
    add_table(
        doc,
        ["Evaluation choice", "Bias avoided", "Primary MarketStream implementation"],
        [
            ["Chronological 60/20/20", "Training on future regimes", "Thresholds selected on validation, frozen before test"],
            ["One-to-one forward matching", "Early hits and one alert claiming multiple events", "Detection time ≥ event start; unique pairing"],
            ["Detection delay", "Equal credit for late warnings", "First matched detection minus event start"],
            ["Alert burden and duplicates", "High recall through alert flooding", "Alerts/ticker/hour; cooldown duplicate rate"],
            ["Bootstrap intervals", "Overinterpreting one sample", "Event-level 95% confidence intervals"],
            ["Negative controls", "Only testing injected positives", "Volume-only, orderly market, stale news, after-hours spread"],
        ],
        [2300, 3200, 3860],
    )
    paragraph = doc.add_paragraph(style="Table Citation")
    paragraph.add_run("Evaluation design informed by [1–3]; matching semantics are project-specific.")

    doc.add_heading("7. Financial Market Anomaly Evidence", level=1)
    doc.add_heading("7.1 Price and volatility", level=2)
    add_body(
        doc,
        "Returns are scale-free and directionally meaningful, but fixed percentage rules treat all "
        "tickers, sessions, and regimes alike. A robust surprise statistic compares the return with the "
        "historical distribution for the same context. A separate volatility-burst factor measures the "
        "window range, because a reversal or unstable auction can have a large range but a small net "
        "return."
    )
    doc.add_heading("7.2 Relative activity and liquidity", level=2)
    add_body(
        doc,
        "Absolute volume is not comparable across securities or time of day. Relative volume uses the "
        "same intraday slot as its baseline. Bid-ask spread and order imbalance add information that OHLCV "
        "alone cannot provide. Research on price jumps and liquidity connects discontinuous price behavior "
        "with changing market depth and trading conditions, supporting explicit liquidity evidence rather "
        "than treating volume as a universal proxy. [14,15]"
    )
    doc.add_heading("7.3 Market context and cross-asset structure", level=2)
    add_body(
        doc,
        "A stock move shared by SPY, QQQ, and peers has a different interpretation from a stock-specific "
        "residual. The system therefore keeps both possibilities: `market_residual` supports the "
        "stock-specific pattern, while the `cross_asset_shock` pattern recognizes broad movement as its "
        "own event. Broad movement is a negative control only for stock-specific claims, not necessarily "
        "for every system-level alert."
    )
    doc.add_heading("7.4 News timing", level=2)
    add_body(
        doc,
        "News features are scientifically useful only when their timestamps and coverage are credible. "
        "Alpaca's news API provides historical and real-time news sourced from Benzinga, while its Basic "
        "market data plan has IEX constraints that must be stated. [10–12] A news-confirmed move must use "
        "the source event time and a finite confirmation window; stale news is an explicit negative "
        "control. Sentiment models can be compared offline, but the production factor should remain "
        "bounded and should expose the headline cluster that produced it."
    )

    doc.add_page_break()
    doc.add_heading("8. Proposed Factor and CEP Architecture", level=1)
    add_table(
        doc,
        ["Factor", "Incremental input/state", "Baseline or range", "CEP role"],
        [
            ["return_surprise", "Previous close; current first/last", "Median/MAD of same slot", "Direction and price confirmation"],
            ["volatility_burst", "Window high/low/first", "Range ratio by slot", "Fast unstable movement"],
            ["relative_volume", "Trade volume or bar fallback", "Volume median by slot", "Activity confirmation"],
            ["spread_stress", "Latest bid and ask", "Spread-bps median by slot", "Liquidity-pressure precondition"],
            ["quote_imbalance", "Latest bid/ask sizes", "Bounded [-1, 1] plus robust state", "Displayed supply/demand pressure"],
            ["signed_trade_imbalance", "Buy/sell classified volume", "Bounded [-1, 1] plus robust state", "Executed pressure and persistence"],
            ["market_residual", "Asset return minus QQQ/SPY", "Robust residual distribution", "Stock-specific versus broad move"],
            ["news_shock", "Mean direction × log event count", "Robust news distribution", "News-to-price confirmation"],
        ],
        [1900, 2600, 2300, 2560],
    )
    paragraph = doc.add_paragraph(style="Table Citation")
    paragraph.add_run("Factor definitions are the MarketStream design synthesis; no test-set magnitude participates in calibration.")
    add_body(
        doc,
        "The architecture separates three responsibilities. The data plane decides what happened and "
        "whether the observation is trustworthy. The factor plane computes source-independent state. The "
        "CEP plane decides whether a temporal pattern is complete, in progress, suppressed, or merged. "
        "This separation makes a replay scientifically meaningful because it can reuse the same Kafka and "
        "detector code rather than a simplified notebook implementation."
    )
    add_body(
        doc,
        "The five-minute compatibility output is intentionally downstream of the new factor engine. It "
        "lets the old Streamlit charts and ML backtests continue without allowing legacy fields to define "
        "the new production contract. Once the contracts and acceptance tests stabilize, a redesigned "
        "frontend can consume `FactorSnapshot` and `DetectionResult` directly."
    )

    doc.add_heading("9. Research Protocol and Falsifiable Claims", level=1)
    add_body(
        doc,
        "The project should be presented as a comparative systems study, not as a guaranteed claim that "
        "CEP always beats machine learning. The following hypotheses are falsifiable and align with the "
        "implemented measurements."
    )
    add_bullets(
        doc,
        [
            "H1 — At a matched normal-period alert budget, factor CEP achieves event-level F1 no worse than the legacy ensemble on pre-registered market events and six synthetic sequence classes.",
            "H2 — CEP calculation p99 is at most 5 ms on the project hardware, and infrastructure receipt-to-persistence p95 is at most 15 seconds.",
            "H3 — Removing liquidity, news, or market context materially reduces recall on the corresponding event class without improving all negative controls.",
            "H4 — Directional cooldown keeps repeated-alert rate at or below 5% while preserving the first detection for a matched event.",
            "H5 — Live and replay produce identical factor and pattern decisions for the same ordered MarketEvents, excluding wall-clock receipt metadata.",
        ],
        bullet_id,
    )
    add_body(
        doc,
        "OHLCV and news should cover at least twelve months. Microstructure evaluation should combine "
        "ordinary days with an event list registered before download. Synthetic experiments use twenty "
        "seeds and three intensities. Ablations remove factor groups, news, microstructure inputs, and "
        "individual patterns. All threshold choices occur on training and validation data; the held-out "
        "test is run only after freezing the baseline version."
    )
    add_body(
        doc,
        "Adverse results are informative. For example, the implemented high-intensity protocol shows that "
        "an extreme single-factor exception can generate alerts in some negative controls. The correct "
        "response is to report this result and use a pre-specified validation alert budget to decide "
        "whether the exception should require context—not to delete the control or tune on the test set."
    )

    doc.add_heading("10. Threats to Validity and Limitations", level=1)
    add_bullets(
        doc,
        [
            "Feed coverage: Alpaca Basic/IEX is not consolidated SIP. Quote and trade factors represent the observed venue coverage, not the full market.",
            "Historical depth: MBP-10 is quota-intensive, so event-day selection must be pre-registered and ordinary-day controls retained.",
            "News labels: headline polarity is not equivalent to causal market impact; timestamps, entity relevance, novelty, and already-priced information remain confounders.",
            "Baseline adaptation: rolling robust baselines can absorb a persistent abnormal regime. Baseline versions and freeze points must be recorded.",
            "Synthetic realism: injected sequences test detector semantics, not the full joint distribution of real order books. Real-event evidence remains necessary.",
            "Ground truth: market anomaly labels are contestable. The study should separate event detection from claims about manipulation, causality, or investment profitability.",
            "Latency: in-process microbenchmarks do not prove Kafka-to-database service levels. A soak test with receipt and persistence timestamps is required.",
        ],
        bullet_id,
    )

    doc.add_heading("11. Conclusion", level=1)
    add_body(
        doc,
        "The literature supports a disciplined reduction in model complexity. Medical warning systems "
        "motivate sparse, interpretable evidence and persistence; industrial and aerospace monitoring "
        "motivate derived quantities, mode-conditioned baselines, residuals, and confidence; cybersecurity "
        "motivates bounded state and event correlation; streaming benchmarks motivate strong simple "
        "baselines and careful metrics; financial microstructure motivates explicit liquidity, pressure, "
        "market, and news context."
    )
    add_body(
        doc,
        "For MarketStream, the correct next scientific step is not a fifth model. It is to validate the "
        "eight-factor, six-pattern architecture on frozen chronological splits, pre-registered event days, "
        "negative controls, and operational alert budgets. The legacy ensemble should remain visible in "
        "the comparison precisely because a lightweight system must demonstrate—not assume—its advantage."
    )

    doc.add_heading("References", level=1)
    references = [
        ("[1] TSB-AD: A comprehensive benchmark for time-series anomaly detection. NeurIPS Datasets and Benchmarks, 2024.", "https://proceedings.neurips.cc/paper_files/paper/2024/hash/c3f3c690b7a99fba16d0efd35cb83b2c-Abstract-Datasets_and_Benchmarks_Track.html"),
        ("[2] Towards Unbiased Evaluation of Time-Series Anomaly Detection. arXiv:2409.13053, 2024.", "https://arxiv.org/abs/2409.13053"),
        ("[3] The Numenta Anomaly Benchmark. arXiv:1510.03336, 2015.", "https://arxiv.org/abs/1510.03336"),
        ("[4] Guha et al. Robust Random Cut Forest Based Anomaly Detection on Streams. ICML/PMLR, 2016.", "https://proceedings.mlr.press/v48/guha16.html"),
        ("[5] StreamSpot: Fast Memory-efficient Anomaly Detection in Streaming Heterogeneous Graphs. KDD, 2016.", "https://www.kdd.org/kdd2016/subtopic/view/fast-memory-efficient-anomaly-detection-in-streaming-heterogeneous-graphs"),
        ("[6] NASA MEDOS: Model-based Expert Diagnostic and Operational System. NASA Technical Reports Server, 2025.", "https://ntrs.nasa.gov/citations/20250002215"),
        ("[7] Prytherch et al. ViEWS—Towards a national early warning score for detecting adult inpatient deterioration. Resuscitation, 2010.", "https://pubmed.ncbi.nlm.nih.gov/20637974/"),
        ("[8] NIST. Securing Manufacturing Industrial Control Systems: Behavioral Anomaly Detection.", "https://www.nist.gov/publications/securing-manufacturing-industrial-control-systems-behavioral-anomaly-detection"),
        ("[9] Complex Event Processing for cyber security in critical infrastructures.", "https://iris.uniroma1.it/handle/11573/415712"),
        ("[10] Alpaca. Real-time Stock Pricing Data documentation.", "https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data"),
        ("[11] Alpaca. About Market Data API and plan coverage.", "https://docs.alpaca.markets/us/docs/about-market-data-api"),
        ("[12] Alpaca. Historical News Data documentation.", "https://docs.alpaca.markets/us/docs/historical-news-data"),
        ("[13] Databento. Market-by-Price schemas and data formats.", "https://databento.com/docs/schemas-and-data-formats/market-by-price"),
        ("[14] Price jumps and liquidity evidence in financial markets. Journal article landing page.", "https://www.sciencedirect.com/science/article/pii/S1386418113000177"),
        ("[15] Recent research on market liquidity and price jumps. SSRN abstract 5199540.", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5199540"),
        ("[16] Chandola, Banerjee, and Kumar. Anomaly Detection: A Survey. ACM Computing Surveys, 2009.", "https://doi.org/10.1145/1541880.1541882"),
        ("[17] Tan, Ting, and Liu. Fast Anomaly Detection for Streaming Data. IJCAI, 2011.", "https://www.ijcai.org/Proceedings/11/Papers/254.pdf"),
    ]
    for label, url in references:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Inches(0.25)
        paragraph.paragraph_format.first_line_indent = Inches(-0.25)
        paragraph.paragraph_format.space_after = Pt(5)
        paragraph.paragraph_format.line_spacing = 1.0
        paragraph.add_run(label + " ")
        add_hyperlink(paragraph, "Source", url)

    core_properties = doc.core_properties
    core_properties.title = "Lightweight, Explainable Anomaly Detection for Streaming Financial Markets"
    core_properties.subject = "MarketStream Literature Review V2"
    core_properties.author = "MarketStream Capstone Project"
    core_properties.keywords = "anomaly detection, CEP, market microstructure, streaming, factors"
    core_properties.comments = (
        "Preset: narrative_proposal. First-page pattern: editorial_cover. "
        "Named cover override: 30pt navy title, 15pt blue-gray subtitle, gold kicker."
    )
    doc.settings.element.append(OxmlElement("w:updateFields"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(build())
