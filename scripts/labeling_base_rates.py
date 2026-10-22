"""Base rates of the proposed labeling rules on a disjoint period (2023-08..11).

Applies the market-data parts of docs/LABELING_CRITERIA.md (A1, A2, A4, A5 and
N1, N2, N3, N6) to every ticker, window and session; catalyst, news and macro
rules need human judgement and are not applied.  The period overlaps no
candidate interval, baseline or holdout.  Informative only: thresholds are not
tuned on these numbers.
"""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
from collections import Counter
from datetime import date, time
from pathlib import Path

from replay.alpaca_history import AlpacaHistoricalClient
from replay.review_metrics import (
    THRESHOLDS,
    fetch_sip_bars,
    interval_measurements,
    regular_bars,
    rule_inputs,
)

TICKERS = ("AAPL", "TSLA", "NVDA", "QQQ", "SPY")
WINDOWS = {"09:30-11:00": (time(9, 30), time(11, 0)), "14:00-15:30": (time(14, 0), time(15, 30))}
FETCH = (date(2023, 7, 10), date(2023, 11, 10))
MEASURE_FROM = date(2023, 8, 14)


def classify(inputs: dict) -> dict[str, bool]:
    full = all(value >= THRESHOLDS["min_coverage"] for value in inputs["coverage"].values())
    a1 = (
        inputs["move_ratio"] is not None
        and inputs["move_ratio"] >= THRESHOLDS["anomaly_move_ratio"]
        and inputs["abs_total_move"] >= inputs["move_floor"]
    )
    a2 = inputs["volume_ratio"] is not None and inputs["volume_ratio"] >= THRESHOLDS["anomaly_volume_ratio"]
    quiet = THRESHOLDS["normal_ratio"]
    n1 = (inputs["move_ratio"] or 0) <= quiet and (inputs["range_ratio"] or 0) <= quiet
    n2 = (inputs["volume_ratio"] or 0) <= quiet
    n3 = all(value is not None and value <= quiet for value in inputs["market_move_ratios"].values())
    return {
        "A1": a1, "A2": a2, "A4": not inputs["direction_conflict"], "A5": full,
        "N1": n1, "N2": n2, "N3": n3, "N6": full,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/review_bars/base_rates_2023.pkl.gz"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.cache.exists():
        raw = pickle.loads(gzip.decompress(args.cache.read_bytes()))
    else:
        raw = fetch_sip_bars(AlpacaHistoricalClient.from_settings(), list(TICKERS), *FETCH)
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        args.cache.write_bytes(gzip.compress(pickle.dumps(raw)))
    sessions = {symbol: regular_bars(bars) for symbol, bars in raw.items()}
    measured_days = [day for day in sorted(sessions["SPY"]) if day >= MEASURE_FROM]
    rows, counts = [], Counter()
    for day in measured_days:
        for window, (start, end) in WINDOWS.items():
            for ticker in TICKERS:
                inputs = rule_inputs(interval_measurements(sessions, ticker, day, start, end))
                if not inputs["available"]:
                    counts["unavailable"] += 1
                    continue
                flags = classify(inputs)
                anomaly = flags["A1"] and flags["A2"] and flags["A4"] and flags["A5"]
                normal = flags["N1"] and flags["N2"] and flags["N3"] and flags["N6"]
                group = "anomaly_market_data" if anomaly else "normal_market_data" if normal else "grey"
                counts[group] += 1
                counts["A1_only_magnitude"] += flags["A1"]
                counts["total"] += 1
                rows.append({
                    "date": day.isoformat(), "window": window, "ticker": ticker, "group": group,
                    **flags,
                    "move_ratio": inputs["move_ratio"], "volume_ratio": inputs["volume_ratio"],
                    "range_ratio": inputs["range_ratio"], "total_move": inputs["abs_total_move"],
                    "direction": inputs["total_move_sign"],
                })
    total = counts["total"]
    summary = {
        "period": {"fetched": [d.isoformat() for d in FETCH], "measured_from": MEASURE_FROM.isoformat(),
                   "sessions_measured": len(measured_days)},
        "feed": "sip", "adjustment": "split", "thresholds": THRESHOLDS,
        "not_applied": ["A3 documented cause", "N4 company news", "N5 macro calendar"],
        "counts": dict(counts),
        "shares": {key: counts[key] / total for key in ("anomaly_market_data", "normal_market_data", "grey", "A1_only_magnitude")},
        "anomaly_market_data_cases": [row for row in rows if row["group"] == "anomaly_market_data"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "rows.json").write_text(json.dumps(rows) + "\n")
    print(json.dumps({key: summary[key] for key in ("counts", "shares")}, indent=2))
    for row in summary["anomaly_market_data_cases"]:
        print(row["date"], row["window"], row["ticker"], row["direction"],
              f'move x{row["move_ratio"]:.1f} vol x{row["volume_ratio"]:.1f} |M|={row["total_move"]:.2%}')


if __name__ == "__main__":
    main()
