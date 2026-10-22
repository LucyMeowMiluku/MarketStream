"""Prepare the local data for the label review app (no detector involved).

For every candidate interval it stores consolidated SIP minute bars for the
window (ticker, SPY, QQQ), the measurements of docs/LABELING_CRITERIA.md
against the 20 previous sessions, per-minute typical volume, and Alpaca news
for the ticker published between the reference time and the window end.
Intervals get neutral display IDs in a seeded random order so the review can be
blind to the draft.  Only counts are printed; the data is meant for the
reviewer, and the output directory is gitignored (provider data).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from replay.alpaca_history import AlpacaHistoricalClient
from replay.review_metrics import (
    NY,
    REGULAR_OPEN,
    fetch_sip_bars,
    interval_measurements,
    regular_bars,
    rule_inputs,
)

SEED = 20261023


def _local(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(NY)


def _news(client, ticker: str, start: datetime, end: datetime) -> list[dict]:
    rows, token = [], None
    while True:
        payload = client.request_json("/v1beta1/news", {
            "symbols": ticker,
            "start": start.astimezone(timezone.utc).isoformat(),
            "end": end.astimezone(timezone.utc).isoformat(),
            "limit": 50, "sort": "asc", "page_token": token,
        })
        rows.extend(payload.get("news", []))
        token = payload.get("next_page_token")
        if not token:
            break
    return [
        {
            "headline": row.get("headline", ""),
            "summary": row.get("summary", ""),
            "source": row.get("source"),
            "url": row.get("url"),
            "symbols": row.get("symbols", []),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]


def build_item(client, interval: dict, display_id: str, group: str) -> dict:
    start, end = _local(interval["started_at"]), _local(interval["ended_at"])
    day, ticker = start.date(), interval["ticker"].upper()
    symbols = list(dict.fromkeys([ticker, "SPY", "QQQ"]))
    raw = fetch_sip_bars(client, symbols, day - timedelta(days=45), day)
    sessions = {symbol: regular_bars(bars) for symbol, bars in raw.items()}
    measurement = interval_measurements(sessions, ticker, day, start.time(), end.time())
    prior = [datetime.fromisoformat(item).date() for item in measurement["reference_sessions"]]
    if start.time() == REGULAR_OPEN:
        previous = max(item for item in sessions["SPY"] if item < day)
        reference_time = sessions["SPY"][previous][-1].start + timedelta(minutes=1)
    else:
        reference_time = start
    chart = {}
    for symbol in symbols:
        chart[symbol] = [
            [bar.start.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
            for bar in sessions[symbol].get(day, [])
            if start.time() <= bar.start.time() < end.time()
        ]
    typical_minute_volume = []
    minute = datetime.combine(day, start.time(), NY)
    while minute.time() < end.time():
        volumes = [
            bar.volume
            for session in prior
            for bar in sessions[ticker].get(session, [])
            if bar.start.time() == minute.time()
        ]
        typical_minute_volume.append([minute.isoformat(), statistics.median(volumes) if volumes else None])
        minute += timedelta(minutes=1)
    return {
        "display_id": display_id,
        "group": group,
        "candidate": interval,  # hidden by the app while blind
        "ticker": ticker,
        "window": {"start": start.isoformat(), "end": end.isoformat(),
                   "reference_time": reference_time.isoformat()},
        "measurement": measurement,
        "rule_inputs": rule_inputs(measurement),
        "chart": chart,
        "typical_minute_volume": typical_minute_volume,
        "news": _news(client, ticker, reference_time - timedelta(hours=12), end + timedelta(hours=2)),
        "feed": "sip", "adjustment": "split",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/replay/labels/iex_benchmark_v1.draft.json"))
    parser.add_argument("--pool", type=Path, default=Path("data/replay/labels/iex_benchmark_v1.ai_preannotated.v3.json"))
    parser.add_argument("--output", type=Path, default=Path("data/replay/review/workbench"))
    parser.add_argument("--prefix", default="R", help="display-ID prefix (D for demo)")
    parser.add_argument("--no-pool", action="store_true")
    args = parser.parse_args()
    labels = json.loads(args.labels.read_text())
    review = labels["intervals"]
    known = {item["interval_id"] for item in review}
    pool = []
    if not args.no_pool and args.pool.exists():
        pool = [item for item in json.loads(args.pool.read_text())["intervals"]
                if item["interval_id"] not in known]
    rng = random.Random(SEED)
    order = rng.sample(review, len(review))
    pool_order = rng.sample(pool, len(pool))
    client = AlpacaHistoricalClient.from_settings()
    args.output.mkdir(parents=True, exist_ok=True)
    index = []
    for group, items, prefix in (("review", order, args.prefix), ("pool", pool_order, "P")):
        for number, interval in enumerate(items, start=1):
            display_id = f"{prefix}{number:02d}"
            path = args.output / f"{display_id}.json"
            if not path.exists():
                path.write_text(json.dumps(build_item(client, interval, display_id, group)) + "\n")
            index.append({"display_id": display_id, "group": group, "file": path.name})
            print(f"prepared {display_id}", flush=True)
    (args.output / "index.json").write_text(json.dumps({
        "seed": SEED,
        "labels_file": str(args.labels),
        "labels_sha256": hashlib.sha256(args.labels.read_bytes()).hexdigest(),
        "pool_file": str(args.pool) if pool else None,
        "items": index,
    }, indent=2) + "\n")
    print(f"{len(order)} review intervals, {len(pool_order)} pool intervals", flush=True)


if __name__ == "__main__":
    main()
