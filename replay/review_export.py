"""Turn human review records into the review CSV and a reviewed label registry.

Mechanical only: every value comes from what the reviewer recorded in the
label review app; nothing is inferred.  Excluded intervals stay in the CSV but
not in the registry, because a frozen registry may contain approved intervals
only.
"""

from __future__ import annotations

import copy
import csv
import io
import re
from pathlib import Path
from typing import Any

from replay.labels import LabelRegistry

CSV_FIELDS = [
    "display_id", "interval_id", "ticker", "started_at", "ended_at", "decision", "direction",
    "event_type", "scope", "confidence", "exclusion_reason", "cause_urls", "cause_published_at",
    "company_news_found", "company_news_note", "macro_release_found", "macro_release_note",
    "calendar_checked", "move_ratio", "volume_ratio", "range_ratio", "gap", "in_window",
    "direction_conflict", "market_move_ratios", "coverage", "reasoning", "reviewer",
    "reviewed_at", "criteria_version", "draft_revealed_before_decision",
    "detector_outputs_not_seen",
]

STATUS = re.compile(r"\*\*Status: (APPROVED|PROPOSED)[^*]*\*\*")
VOLUME_OPTION = re.compile(r"volume option (\d)")


def criteria_status(path: Path) -> dict[str, Any]:
    """Read the approval line of docs/LABELING_CRITERIA.md."""

    text = path.read_text()
    match = STATUS.search(text)
    option = VOLUME_OPTION.search(match.group(0)) if match else None
    return {
        "approved": bool(match and match.group(1) == "APPROVED"),
        "line": match.group(0) if match else "status line not found",
        "volume_option": int(option.group(1)) if option else None,
    }


def review_csv(records: dict[str, dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for display_id in sorted(records):
        row = dict(records[display_id])
        for key in ("cause_urls", "market_move_ratios", "coverage"):
            if isinstance(row.get(key), (list, dict)):
                row[key] = str(row[key])
        writer.writerow(row)
    return buffer.getvalue()


def reviewed_registry(
    draft: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    records: dict[str, dict],
) -> tuple[dict[str, Any], list[str]]:
    """Build a non-frozen registry of approved intervals and list what is missing.

    ``candidates`` maps interval_id to the candidate record (draft or pool).
    """

    intervals = []
    for record in sorted(records.values(), key=lambda item: item["interval_id"]):
        if record["decision"] not in {"anomaly", "normal"}:
            continue
        item = copy.deepcopy(candidates[record["interval_id"]])
        anomaly = record["decision"] == "anomaly"
        item.update({
            "kind": record["decision"],
            "direction": record["direction"] if anomaly else None,
            "pattern": record["event_type"] if anomaly else None,
            "event_id": (item.get("event_id") or f"{item['interval_id']}-event") if anomaly else None,
            "evidence_urls": list(record.get("cause_urls") or []),
            "confidence": record["confidence"],
            "approval_status": "approved",
            "reviewed_by": record["reviewer"],
            "reviewed_at": record["reviewed_at"],
            "notes": f"{record['reasoning']} [criteria {record['criteria_version']}]",
        })
        intervals.append(item)
    registry = {**copy.deepcopy(draft), "frozen": False, "frozen_at": None, "intervals": intervals}
    problems = []
    anomalies = sum(item["kind"] == "anomaly" for item in intervals)
    normals = sum(item["kind"] == "normal" for item in intervals)
    if anomalies != 12 or normals != 12:
        problems.append(f"approved {anomalies} anomaly + {normals} normal; 12 + 12 required")
    try:
        LabelRegistry.from_dict(registry).validate(
            expected_anomalies=12 if anomalies == 12 and normals == 12 else None,
            expected_normals=12 if anomalies == 12 and normals == 12 else None,
        )
    except ValueError as exc:
        problems.append(str(exc))
    return registry, problems
