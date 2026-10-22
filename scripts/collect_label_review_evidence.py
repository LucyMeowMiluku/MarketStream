"""Collect detector-blind label evidence. This does not approve or freeze labels.

Minute bars support evidence review only; they never replace trade/quote replay.
No detector, factor engine, scores, alerts or evaluation results are imported/read.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from replay.alpaca_history import AlpacaHistoricalClient  # noqa: E402

NY = ZoneInfo("America/New_York")


def parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fetch(client, directory, name, endpoint, params, key):
    pages, rows, token, seen = [], [], None, set()
    for _ in range(100):
        payload = client.request_json(endpoint, {**params, "page_token": token})
        pages.append(payload)
        rows.extend(payload.get(key, []))
        token = payload.get("next_page_token")
        if not token:
            break
        if token in seen:
            raise ValueError("pagination repeated token")
        seen.add(token)
    else:
        raise ValueError("pagination cap reached; evidence incomplete")
    write(directory / f"{name}.json", {"endpoint": endpoint, "params": params,
          "retrieved_at": datetime.now(timezone.utc).isoformat(), "complete": True,
          "pages": pages})
    return rows


def review_window(item, output):
    directory = output / "raw" / item["interval_id"]
    client = AlpacaHistoricalClient.from_settings()
    client.timeout_seconds = 12
    client.max_retries = 2
    start, end = parse(item["started_at"]), parse(item["ended_at"])
    local = start.astimezone(NY)
    day_start = local.replace(hour=0, minute=0, second=0)
    day_end = day_start + timedelta(days=1)
    symbols = sorted(set([item["ticker"], "SPY", "QQQ"]))
    summary = {"interval_id": item["interval_id"], "candidate_kind": item["kind"],
               "ticker": item["ticker"], "started_at": item["started_at"],
               "ended_at": item["ended_at"], "local_start": local.isoformat(),
               "local_end": end.astimezone(NY).isoformat(), "symbols": {},
               "status": "complete", "errors": []}
    for symbol in symbols:
        try:
            minutes = fetch(client, directory, f"{symbol}.minutes", f"/v2/stocks/{symbol}/bars",
                            {"start": start.isoformat(), "end": end.isoformat(),
                             "timeframe": "1Min", "feed": "iex", "adjustment": "raw",
                             "limit": 10000, "sort": "asc"}, "bars")
            # Exclude the end-stamped minute: its close contains post-boundary data.
            inside = sorted([r for r in minutes if start <= parse(r["t"]) < end],
                            key=lambda r: r["t"])
            daily = fetch(client, directory, f"{symbol}.prior_daily", f"/v2/stocks/{symbol}/bars",
                          {"start": (day_start - timedelta(days=65)).isoformat(),
                           "end": day_start.isoformat(), "timeframe": "1Day", "feed": "iex",
                           "adjustment": "raw", "limit": 10000, "sort": "asc"}, "bars")
            prior = sorted([r for r in daily if parse(r["t"]).astimezone(NY).date() < local.date()],
                           key=lambda r: r["t"])
            # Daily 'close' may include extended hours. Fetch actual regular-session reference.
            if not prior or not inside:
                raise ValueError("missing minute bars or prior daily reference")
            prev_day = parse(prior[-1]["t"]).astimezone(NY).date()
            prev_start = datetime.combine(prev_day, local.time().replace(hour=15, minute=45), NY)
            prev_end = prev_start.replace(hour=16, minute=0)
            close_rows = fetch(client, directory, f"{symbol}.prior_close_minutes",
                               f"/v2/stocks/{symbol}/bars",
                               {"start": prev_start.isoformat(), "end": prev_end.isoformat(),
                                "timeframe": "1Min", "feed": "iex", "adjustment": "raw",
                                "limit": 10000, "sort": "asc"}, "bars")
            close_rows = sorted([r for r in close_rows if parse(r["t"]) < prev_end],
                                key=lambda r: r["t"])
            if not close_rows:
                raise ValueError("missing prior regular-session close")
            reference = close_rows[-1]["c"]
            opening, closing = inside[0]["o"], inside[-1]["c"]
            times = {parse(r["t"]) for r in inside}
            expected = int((end-start).total_seconds()//60)
            missing = [(start+timedelta(minutes=i)).isoformat() for i in range(expected)
                       if start+timedelta(minutes=i) not in times]
            summary["symbols"][symbol] = {
                "bars": len(inside), "expected_minutes": expected, "missing_minutes": missing,
                "duplicate_minute_timestamps": len(inside)-len(times),
                "excluded_end_or_outside_bars": len(minutes)-len(inside),
                "prior_daily_sessions_found": len(prior[-20:]),
                "prior_close_time": close_rows[-1]["t"], "prior_close": reference,
                "first_minute": inside[0]["t"], "last_minute": inside[-1]["t"],
                "first_open": opening, "last_close": closing,
                "gap_pct": (opening/reference-1)*100,
                "end_vs_prior_pct": (closing/reference-1)*100,
                "window_return_pct": (closing/opening-1)*100,
                "window_range_pct": (max(r["h"] for r in inside)-min(r["l"] for r in inside))/opening*100,
                "volume": sum(r["v"] for r in inside),
                "raw_artifact": str((directory/f"{symbol}.minutes.json").relative_to(output))}
        except Exception as exc:
            summary["status"] = "incomplete"
            summary["errors"].append({"symbol": symbol, "type": type(exc).__name__,
                                      "error": str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "request failed"})
    try:
        news = fetch(client, directory, "news_day", "/v1beta1/news",
                     {"symbols": ",".join(symbols), "start": day_start.isoformat(),
                      "end": day_end.isoformat(), "limit": 50, "sort": "asc"}, "news")
        summary["news"] = [{"id": r.get("id"), "headline": r.get("headline"),
                            "created_at": r.get("created_at"), "updated_at": r.get("updated_at"),
                            "symbols": r.get("symbols"), "url": r.get("url"),
                            "after_window": parse(r["created_at"]) >= end,
                            "updated_after_window": parse(r.get("updated_at", r["created_at"])) >= end}
                           for r in news if r.get("created_at")]
    except Exception as exc:
        summary["status"] = "incomplete"
        summary["errors"].append({"kind": "news", "type": type(exc).__name__})
    write(output/"summaries"/f"{item['interval_id']}.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    intervals, versions = {}, {}
    for suffix in ("draft", "ai_preannotated.v3"):
        source = ROOT/f"data/replay/labels/iex_benchmark_v1.{suffix}.json"
        value = json.loads(source.read_text())
        write(args.output/source.name, value)
        versions[suffix] = hashlib.sha256(source.read_bytes()).hexdigest()
        for row in value["intervals"]:
            intervals.setdefault(row["interval_id"], row)
    write(args.output/"review_scope.json", {"created_at": datetime.now(timezone.utc).isoformat(),
          "purpose": "AI-assisted evidence review; no human approval or detector execution",
          "source_label_hashes": versions, "interval_ids": list(intervals),
          "boundary_rule": "minute start >= start and < end; exclude end-stamped minute",
          "direction_references": ["prior regular-session close", "window first open"],
          "normality_rule": "No automatic normal approval from quiet bars or absent news.",
          "baseline_note": "Prior daily sessions are context only, not event baseline coverage."})
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(review_window, item, args.output) for item in intervals.values()]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(result["interval_id"], result["status"], flush=True)
    write(args.output/"evidence_index.json", sorted(results, key=lambda r:r["interval_id"]))
    write(args.output/"SHA256SUMS.json", {
        str(p.relative_to(args.output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(args.output.rglob("*")) if p.is_file()})


if __name__ == "__main__":
    main()
