"""Prepare an append-only, detector-blind review packet; never approve labels.

Run from the repository root with .venv/bin/python scripts/prepare_reviewed_replay.py.
--probe performs small read-only Alpaca requests, not a dataset collection or replay.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def probe_access(intervals: list[dict], output: Path) -> dict:
    from replay.alpaca_history import AlpacaHistoricalClient, AlpacaReplayCollector
    from processing.event_models import as_utc

    try:
        client = AlpacaHistoricalClient.from_settings()
    except RuntimeError:
        return {"status": "credentials_missing", "requests": []}
    client.timeout_seconds = 8
    client.max_retries = 1
    collector = AlpacaReplayCollector(client)
    # One oldest candidate per target plus the latest candidate: capability only.
    selected = {}
    for item in sorted(intervals, key=lambda row: row["started_at"]):
        selected.setdefault(item["ticker"], item)
    latest = max(intervals, key=lambda row: row["ended_at"])
    selected["latest"] = latest
    records = []
    for index, item in enumerate(selected.values()):
        for kind in ("trades", "quotes"):
            params = {"start": item["started_at"], "end": item["ended_at"],
                      "feed": "iex", "limit": 1, "sort": "asc"}
            endpoint = f"/v2/stocks/{item['ticker']}/{kind}"
            record = {"interval_id": item["interval_id"], "endpoint": endpoint,
                      "params": params, "complete_dataset": False}
            try:
                payload = client.request_json(endpoint, params)
                filename = f"probe-{index}-{kind}.json"
                write_json(output / filename, payload)
                record.update(status="accessible" if payload.get(kind) else "empty",
                              rows=len(payload.get(kind, [])), artifact=filename)
            except Exception as exc:
                # Do not serialize exception repr, request objects, headers or secrets.
                record.update(status="failed", error_type=type(exc).__name__,
                              error=str(exc) if isinstance(exc, RuntimeError) else "request failed")
            records.append(record)
        record = {"interval_id": item["interval_id"], "kind": "prior_session_calendar",
                  "required_sessions": 20, "event_coverage_verified": False}
        try:
            days = collector.previous_sessions(item["ticker"], as_utc(item["started_at"]),
                                               count=20, timezone_name="America/New_York")
            record.update(status="accessible", sessions=[day.isoformat() for day in days])
        except Exception as exc:
            record.update(status="failed", error_type=type(exc).__name__,
                          error=str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "request failed")
        records.append(record)
    return {"status": "sampled_only", "full_event_coverage_verified": False,
            "license_and_retention_terms_verified": False, "requests": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "data/replay/preflight" / stamp
    output.mkdir(parents=True, exist_ok=False)
    labels = ROOT / "data/replay/labels"
    draft = json.loads((labels / "iex_benchmark_v1.draft.json").read_text())
    versions = {}
    for source in sorted(labels.glob("*.json")):
        shutil.copy2(source, output / source.name)
        value = json.loads(source.read_text())
        versions[source.name] = value
    rows = []
    for item in draft["intervals"]:
        rows.append({**item, "candidate_kind": item["kind"],
                     "evidence_urls": " | ".join(item.get("evidence_urls", [])),
                     "human_decision": "pending", "anomaly_definition": "",
                     "boundary_rationale": "", "direction_reference": "",
                     "independent_evidence_checked": "", "uncertainty": "",
                     "normality_check": "", "reviewer": "", "reviewed_at": "",
                     "detector_outputs_not_seen": ""})
    fields = ["interval_id", "ticker", "candidate_kind", "started_at", "ended_at",
              "direction", "pattern", "evidence_urls", "notes", "anomaly_definition",
              "boundary_rationale", "direction_reference", "independent_evidence_checked",
              "uncertainty", "normality_check", "human_decision", "reviewer", "reviewed_at",
              "detector_outputs_not_seen"]
    write_csv(output / "human_review.csv", fields, rows)
    original = {row["interval_id"]: row for row in draft["intervals"]}
    changes = []
    for filename, version in versions.items():
        current = {row["interval_id"]: row for row in version["intervals"]}
        for interval_id in sorted(original.keys() | current.keys()):
            before, after = original.get(interval_id), current.get(interval_id)
            for field in ("kind", "ticker", "started_at", "ended_at", "direction",
                          "pattern", "evidence_urls", "notes", "approval_status"):
                old, new = (before or {}).get(field), (after or {}).get(field)
                if old != new:
                    changes.append({"version": filename, "interval_id": interval_id,
                                    "field": field, "draft": old, "candidate": new})
    write_json(output / "candidate_changes.json", changes)
    manifest_paths, event_paths = [], []
    for path in sorted((ROOT / "data").rglob("*")):
        if output in path.parents or not path.is_file():
            continue
        if path.name == "manifest.json":
            try:
                value = json.loads(path.read_text())
                manifest_paths.append({"path": str(path.relative_to(ROOT)),
                                       "schema_version": value.get("schema_version"),
                                       "sha256": digest(path)})
            except (ValueError, OSError):
                pass
        if path.name.endswith("events.jsonl"):
            event_paths.append(str(path.relative_to(ROOT)))
    code_dir = output / "code_snapshot"
    for folder in ("replay", "processing", "cep", "evaluation", "config", "producers"):
        for path in sorted((ROOT / folder).glob("*.py")):
            target = code_dir / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for name in ("pyproject.toml", "uv.lock", "scripts/prepare_reviewed_replay.py"):
        source = ROOT / name
        if source.exists():
            target = code_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (output / "git_status.txt").write_text(subprocess.check_output(
        ["git", "status", "--short"], cwd=ROOT, text=True))
    (output / "environment.txt").write_text(subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze"], cwd=ROOT, text=True))
    access = probe_access(draft["intervals"], output) if args.probe else {"status": "not_probed"}
    write_json(output / "access_probe.json", access)
    counts = {kind: sum(row["kind"] == kind for row in draft["intervals"])
              for kind in ("anomaly", "normal")}
    write_json(output / "preflight.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED_BEFORE_FREEZE", "detector_executed": False,
        "metrics": None, "counts": counts, "manifests_found": manifest_paths,
        "canonical_event_files_found": event_paths,
        "label_versions": {name: {"frozen": value.get("frozen"),
            "approved": sum(row.get("approval_status") == "approved"
                            for row in value["intervals"])} for name, value in versions.items()},
        "blockers": ["independent human label review missing",
                     "complete verified trade/quote/baseline package missing",
                     "protocol and independent holdout not frozen",
                     "CEP/IF target and alert-policy parity unresolved"],
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "code_snapshot_is_experimental_freeze": False,
        "access_probe": "access_probe.json",
    })
    write_csv(output / "fp_fn_cases.TEMPLATE.csv", [
        "run_id", "method", "case_id", "FP_or_FN", "interval_id", "ticker",
        "truth_event_id", "detection_id", "trace_lines", "source_event_ids",
        "raw_input_paths", "factor_values", "baseline_hash", "thresholds",
        "state_before", "state_after", "suppression_reason", "matching_reason",
        "root_cause", "evidence", "uncertainty", "followup_on_holdout_only"], [])
    write_json(output / "SHA256SUMS.json", {
        str(path.relative_to(output)): digest(path)
        for path in sorted(output.rglob("*")) if path.is_file()
    })
    print(json.dumps({"output": str(output), "status": "BLOCKED_BEFORE_FREEZE"}))


if __name__ == "__main__":
    main()
