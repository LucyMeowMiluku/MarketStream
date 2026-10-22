"""Collect an Alpaca IEX calibration set for the zero-MAD sensitivity study.

The calibration period (2023-10-02 .. 2023-11-10, 30 sessions) ends before the
earliest baseline session of any reviewed candidate interval (2024-01) and is
disjoint from the proposed 2025-05/06 holdout, so choosing a parameter on it
cannot leak into the formal evaluation.

Quotes are streamed in full but only the last quote of each second is kept:
the factor engine only uses the last quote of a window, so window-final quote
state is identical at 10 s and longer cadences; trade-side inference may use a
midpoint up to one second stale.  Raw provider data stays local (gitignored).
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from processing.event_models import as_utc
from replay.alpaca_history import (
    AlpacaHistoricalClient,
    news_row_to_events,
    stock_row_to_event,
)
from replay.models import file_sha256

NY = ZoneInfo("America/New_York")
TICKERS = ("AAPL", "TSLA", "NVDA", "QQQ", "SPY")
BLOCKS = {"open_0930_1100": (time(9, 30), time(11, 0)), "pm_1400_1530": (time(14, 0), time(15, 30))}
DATASET_ID = "calibration-zero-mad-2023q4"
# No NYSE holidays fall on weekdays in this range.
SESSIONS = [
    date(2023, 10, 2) + timedelta(days=offset)
    for offset in range(40)
    if (date(2023, 10, 2) + timedelta(days=offset)).weekday() < 5
]


def _window(session: date, block: str) -> tuple[datetime, datetime]:
    start, end = BLOCKS[block]
    return (
        datetime.combine(session, start, NY).astimezone(timezone.utc),
        datetime.combine(session, end, NY).astimezone(timezone.utc),
    )


def _params(start: datetime, end: datetime, **extra) -> dict:
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "feed": "iex",
        "limit": 10_000,
        "sort": "asc",
        **extra,
    }


def _collect_ticker(client, session, block, ticker, part: Path) -> dict:
    start, end = _window(session, block)
    interval_id = f"{block}:{session.isoformat()}"
    events, stats = [], {"ticker": ticker}
    for kind, plural, extra in (
        ("trade", "trades", {}),
        ("bar", "bars", {"timeframe": "1Min", "adjustment": "raw"}),
    ):
        rows, pages = [], 0
        for page, _ in client.iter_pages(
            f"/v2/stocks/{ticker}/{plural}", _params(start, end, **extra), row_key=plural
        ):
            rows.extend(page)
            pages += 1
        stats[plural] = {"rows": len(rows), "pages": pages}
        events.extend(
            stock_row_to_event(
                kind, ticker, row, dataset_id=DATASET_ID, interval_id=interval_id, phase="calibration"
            )
            for row in rows
        )
    last_per_second: dict[int, dict] = {}
    seen, pages = 0, 0
    for page, _ in client.iter_pages(
        f"/v2/stocks/{ticker}/quotes", _params(start, end), row_key="quotes"
    ):
        pages += 1
        for row in page:
            seen += 1
            last_per_second[int(as_utc(row["t"]).timestamp())] = row
    stats["quotes"] = {"rows": seen, "kept": len(last_per_second), "pages": pages}
    events.extend(
        stock_row_to_event(
            "quote", ticker, row, dataset_id=DATASET_ID, interval_id=interval_id, phase="calibration"
        )
        for row in last_per_second.values()
    )
    _write_sorted(part, events)
    return stats


def _collect_news(client, session, block, part: Path) -> dict:
    start, end = _window(session, block)
    rows = []
    for page, _ in client.iter_pages(
        "/v1beta1/news",
        {"symbols": ",".join(TICKERS), "start": start.isoformat(), "end": end.isoformat(),
         "limit": 50, "sort": "asc"},
        row_key="news",
    ):
        rows.extend(page)
    events = [
        event
        for row in rows
        for event in news_row_to_events(
            row,
            symbols=set(TICKERS),
            dataset_id=DATASET_ID,
            interval_id=f"{block}:{session.isoformat()}",
            phase="calibration",
        )
    ]
    _write_sorted(part, events)
    return {"news_rows": len(rows), "news_events": len(events)}


def _write_sorted(path: Path, events) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as destination:
        for event in sorted(events, key=lambda item: (item.event_time, item.event_id)):
            destination.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")
    tmp.replace(path)


def _merge(parts: list[Path], output: Path) -> int:
    rows = []
    for part in parts:
        rows.extend(json.loads(line) for line in part.read_text().splitlines())
    rows.sort(key=lambda item: (as_utc(item["event_time"]), item["event_id"]))
    with output.open("w") as destination:
        for row in rows:
            destination.write(json.dumps(row, separators=(",", ":")) + "\n")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/calibration/zero_mad_2023q4"))
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    client = AlpacaHistoricalClient.from_settings()
    tasks = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for block in BLOCKS:  # open block first so analysis can start early
            for session in SESSIONS:
                parts_dir = args.output / block / "parts" / session.isoformat()
                for ticker in TICKERS:
                    part = parts_dir / f"{ticker}.jsonl"
                    stats_path = part.with_suffix(".stats.json")
                    if not stats_path.exists():
                        tasks[pool.submit(_collect_ticker, client, session, block, ticker, part)] = stats_path
                part = parts_dir / "news.jsonl"
                stats_path = part.with_suffix(".stats.json")
                if not stats_path.exists():
                    tasks[pool.submit(_collect_news, client, session, block, part)] = stats_path
        for done, future in enumerate(as_completed(tasks), start=1):
            tasks[future].write_text(json.dumps(future.result()) + "\n")
            print(f"{done}/{len(tasks)} {tasks[future]}", flush=True)

    manifest = {"dataset_id": DATASET_ID, "provider": "alpaca", "feed": "iex",
                "quote_thinning": "last quote per second", "tickers": list(TICKERS),
                "blocks": {name: [str(a), str(b)] for name, (a, b) in BLOCKS.items()},
                "sessions": [item.isoformat() for item in SESSIONS], "files": []}
    for block in BLOCKS:
        for session in SESSIONS:
            parts_dir = args.output / block / "parts" / session.isoformat()
            output = args.output / block / f"{session.isoformat()}.events.jsonl"
            count = _merge(sorted(parts_dir.glob("*.jsonl")), output)
            manifest["files"].append({
                "block": block, "session": session.isoformat(), "path": str(output),
                "events": count, "sha256": file_sha256(output),
                "requests": [json.loads(item.read_text()) for item in sorted(parts_dir.glob("*.stats.json"))],
            })
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("manifest written", flush=True)


if __name__ == "__main__":
    main()
