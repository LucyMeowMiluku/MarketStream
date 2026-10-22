#!/usr/bin/env python3
"""Normalize report-draft Markdown for formal DOCX production without rewriting prose."""

from __future__ import annotations

import re
import sys
from pathlib import Path


TABLE_TITLES = [
    "六种异常模式",
    "报告模块与主要代码及数据结构",
    "八种轻量因子汇总",
    "六类 CEP 模式的历史范围与完成条件",
    "实验数据划分",
    "检测效果指标",
    "告警质量指标",
    "系统运行指标",
    "事件匹配数量",
    "检测效果比例",
    "首次检测延迟",
    "告警负担",
    "删除 Stock-Specific Dislocation 后的负对照结果",
    "因子组删除实验结果",
    "CEP 与旧机器学习方法的比较",
    "规则计算与端到端持久化延迟",
    "完整链路事件处理结果",
    "Alpaca IEX 运行结果",
]

FIGURE_TITLES = [
    "MarketStream 系统架构图",
    "因子组删除后的 F1 对比",
    "ML 与因子检测效果及平均计算延迟对比",
]

CN_CHAPTERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def numbered_heading(raw: str, current_chapter: int | None) -> tuple[str, int | None]:
    m = re.match(r"^(#{1,6})\s+(.*)$", raw)
    if not m:
        return raw, current_chapter
    hashes = m.group(1)
    text = m.group(2).strip()
    if text.lower() == "abstract":
        return "# Abstract", current_chapter

    m_ch = re.match(r"^([一二三四五六七八九])、\s*(.*)$", text)
    if m_ch:
        current_chapter = CN_CHAPTERS[m_ch.group(1)]
        return f"# {current_chapter} {m_ch.group(2).strip()}", current_chapter

    m_num = re.match(r"^(\d+(?:\.\d+)*)\.?\s*(.*)$", text)
    if m_num and current_chapter:
        nums = [int(x) for x in m_num.group(1).split(".")]
        expected_depth = max(1, len(hashes) - 2)
        if len(hashes) == 3 and nums[0] == current_chapter and len(nums) > 1:
            # Source chapter 7 contains two level-2 headings accidentally marked with ###.
            full = nums
        elif nums[0] == current_chapter and len(nums) > 1 and len(nums) >= expected_depth:
            full = nums
        else:
            full = [current_chapter] + nums
        level = min(len(full), 6)
        label = ".".join(str(x) for x in full)
        title = m_num.group(2).strip()
        return f"{'#' * level} {label} {title}".rstrip(), current_chapter

    # Preserve unnumbered headings, shifted to a normal academic hierarchy.
    shifted = max(1, len(m.group(1)) - 2)
    return f"{'#' * shifted} {text}", current_chapter


def normalize_body_refs(line: str, source_line_no: int) -> str:
    line = line.replace("图4.1", "图 1").replace("图 7-2", "图 3")
    line = line.replace("如下表1", "如下表 1").replace("见下表2", "见表 3")
    if source_line_no >= 669:
        line = re.sub(r"表4\b", "表 9", line)
        line = re.sub(r"表5\b", "表 10", line)
        line = re.sub(r"表6\b", "表 11", line)
    if source_line_no == 755:
        line = line.replace("上图", "图 2")
    return line


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare_report.py INPUT.md OUTPUT.md")
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    lines = src.read_text(encoding="utf-8").splitlines()

    while lines and (not lines[-1].strip() or lines[-1].strip() == "###"):
        lines.pop()

    out: list[str] = ["---", 'title: "report draft"', "---", ""]
    current_chapter: int | None = None
    table_no = 0
    figure_no = 0
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        source_line_no = i + 1

        if source_line_no == 1 and stripped.startswith("# "):
            i += 1
            continue

        # Pipe table: place a formal caption above it and remove the old trailing HTML caption.
        if stripped.startswith("|"):
            block: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            table_no += 1
            title = TABLE_TITLES[table_no - 1] if table_no <= len(TABLE_TITLES) else f"表格 {table_no}"
            out.extend([f"Table {table_no}. {title}", "", *block, ""])
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and re.match(r"^<center>Table\s*\d+", lines[i].strip(), flags=re.I):
                i += 1
            continue

        # Figure: keep the source image, add a consistent caption below, and suppress old duplicate captions.
        if re.match(r"^!\[[^]]*\]\([^)]+\)\s*$", stripped):
            figure_no += 1
            out.extend([raw, "", f"Figure {figure_no}. {FIGURE_TITLES[figure_no - 1]}", ""])
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and (
                re.match(r"^<center>图", lines[i].strip())
                or re.match(r"^\*\*图\s*7-2", lines[i].strip())
            ):
                i += 1
            continue

        if re.match(r"^<center>Table\s*\d+", stripped, flags=re.I) or re.match(r"^<center>图", stripped):
            i += 1
            continue

        if stripped == "参考文献":
            out.extend(["# 参考文献", ""])
            i += 1
            continue

        if stripped.startswith("#"):
            normalized, current_chapter = numbered_heading(raw, current_chapter)
            out.extend([normalized, ""])
            i += 1
            continue

        out.append(normalize_body_refs(raw, source_line_no))
        i += 1

    # Collapse excessive blank lines while preserving paragraph boundaries.
    clean: list[str] = []
    blank = False
    for line in out:
        if not line.strip():
            if not blank:
                clean.append("")
            blank = True
        else:
            clean.append(line.rstrip())
            blank = False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(clean).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
