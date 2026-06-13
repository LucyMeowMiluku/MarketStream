"""Qualitative case study: CEP vs ML on real historical market events.

The synthetic backtest (``ml/compare_methods.py``) gives labelled P/R/F1, but the
advisor wants validation on *real* data. This script replays genuine daily OHLCV
around a handful of well-known large-move sessions (earnings, sell-offs) and
reports what each method flags near the event — a sanity check that the
detectors fire on real market dislocations, not just injected ones.

Scope/caveat: this uses **real price & volume** but a **neutral (zero) sentiment
placeholder** — real historical headline sentiment is out of scope this round,
so sentiment-driven patterns are not exercised here. Features are daily returns,
so "fires on the event" means the anomaly lands on (or adjacent to) the event
session. This is qualitative — there are no ground-truth labels, hence no P/R/F1.

Usage:
    uv run python -m ml.event_case_study
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import yfinance as yf

from config.logging_config import get_logger
from config.settings import settings
from cep.cep_detector import CEPDetector
from ml.detector import FEATURE_COLUMNS, AnomalyDetector
from ml.detectors.ewma_detector import EWMADetector
from ml.detectors.hst_detector import HSTDetector
from ml.ensemble import EnsembleDetector

log = get_logger("case_study")

# (ticker, approximate event date, description). The script picks the largest
# absolute daily move within +/-2 sessions of the date as the event session, so
# being a day off (e.g. an after-close earnings print) is fine.
EVENTS = [
    ("NVDA", "2024-02-22", "Q4 FY24 earnings beat"),
    ("NVDA", "2025-01-27", "DeepSeek-driven sell-off"),
    ("TSLA", "2024-10-24", "Q3 2024 earnings pop"),
    ("AAPL", "2024-08-05", "global risk-off sell-off"),
]


def download_daily(ticker: str, start: str, end: str) -> pd.DataFrame:
    hist = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
    if hist.empty:
        return pd.DataFrame()
    hist = hist.reset_index()
    for col in ("Date", "Datetime"):
        if col in hist.columns:
            hist = hist.rename(columns={col: "timestamp"})
            break
    hist["ticker"] = ticker
    return hist


def compute_daily_features(hist: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """One row per trading day: daily return + that day's volume, neutral sentiment."""
    hist = hist.sort_values("timestamp").reset_index(drop=True)
    rows = []
    for i in range(1, len(hist)):
        prev_close = float(hist.iloc[i - 1]["Close"])
        close = float(hist.iloc[i]["Close"])
        rows.append(
            {
                "ticker": ticker,
                "timestamp": pd.to_datetime(hist.iloc[i]["timestamp"]).tz_localize(None).normalize(),
                "avg_close": round(close, 4),
                "price_change_rate": round((close - prev_close) / prev_close, 6) if prev_close else 0.0,
                "total_volume": float(hist.iloc[i]["Volume"]),
                "avg_sentiment": 0.0,
                "sentiment_shift": 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_ml_reference(warmup_df: pd.DataFrame) -> EnsembleDetector:
    """EWMA + HST + Isolation Forest (LSTM omitted for a per-event sanity check)."""
    isolation = AnomalyDetector()
    isolation.fit(warmup_df[FEATURE_COLUMNS].values)
    detectors = [
        EWMADetector(span=settings.ewma_span),
        HSTDetector(
            n_trees=settings.hst_n_trees,
            height=settings.hst_height,
            window_size=settings.hst_window_size,
        ),
        isolation,
    ]
    return EnsembleDetector(detectors, weights=[0.45, 0.05, 0.50], threshold=settings.ensemble_threshold)


def locate_event(feats: pd.DataFrame, date_str: str) -> int:
    target = pd.Timestamp(date_str)
    dist = (feats["timestamp"] - target).abs()
    center = int(dist.idxmin())
    lo, hi = max(0, center - 2), min(len(feats) - 1, center + 2)
    return int(feats.loc[lo:hi, "price_change_rate"].abs().idxmax())


def run_event(ticker: str, date_str: str, desc: str) -> dict | None:
    target = pd.Timestamp(date_str)
    feats_raw = download_daily(
        ticker,
        start=(target - pd.Timedelta(days=160)).strftime("%Y-%m-%d"),
        end=(target + pd.Timedelta(days=8)).strftime("%Y-%m-%d"),
    )
    if feats_raw.empty:
        log.warning("no_data", ticker=ticker, date=date_str)
        return None
    feats = compute_daily_features(feats_raw, ticker)
    if len(feats) < 40:
        log.warning("insufficient_history", ticker=ticker, rows=len(feats))
        return None

    event_idx = locate_event(feats, date_str)

    # Fit the ML reference's Isolation Forest on history strictly before the event window.
    warmup = feats.iloc[: max(20, event_idx - 3)]
    cep = CEPDetector()
    ml = build_ml_reference(warmup)

    # Replay the full series in order; both methods warm up online as we go.
    per_row = []
    for i, row in feats.iterrows():
        feat = row.to_dict()
        cep_score = cep.score(feat)
        cep.update(feat)
        ml_score, _ = ml.score(feat)
        ml.update(feat)
        per_row.append(
            {
                "date": row["timestamp"].strftime("%Y-%m-%d"),
                "ret": round(float(row["price_change_rate"]), 6),
                "cep_score": round(float(cep_score), 4),
                "cep_pattern": cep.last_match(ticker) or "",
                "cep_flag": bool(cep_score < settings.cep_threshold),
                "ml_score": round(float(ml_score), 4),
                "ml_flag": bool(ml_score < settings.ensemble_threshold),
            }
        )

    event = per_row[event_idx]
    window = per_row[max(0, event_idx - 2) : min(len(per_row), event_idx + 3)]
    return {
        "ticker": ticker,
        "description": desc,
        "event_date": event["date"],
        "event_return": event["ret"],
        "cep": {"flag": event["cep_flag"], "score": event["cep_score"], "pattern": event["cep_pattern"]},
        "ml": {"flag": event["ml_flag"], "score": event["ml_score"]},
        "window": window,
    }


def print_report(results: list[dict]) -> None:
    print("\n" + "=" * 92)
    print("CEP vs ML on REAL historical events (daily returns, neutral sentiment placeholder)")
    print("=" * 92)
    print(f"{'Event':<34}{'Date':<12}{'Move':>8}   {'CEP':<26}{'ML':<12}")
    print("-" * 92)
    for r in results:
        cep = r["cep"]
        cep_str = f"{'FLAG' if cep['flag'] else '  - '} {cep['score']:+.2f} {cep['pattern']}".strip()
        ml = r["ml"]
        ml_str = f"{'FLAG' if ml['flag'] else '  - '} {ml['score']:+.2f}"
        label = f"{r['ticker']} {r['description']}"[:33]
        print(f"{label:<34}{r['event_date']:<12}{r['event_return']:>7.1%}   {cep_str:<26}{ml_str:<12}")
    print()
    # Per-event day-by-day window.
    for r in results:
        print(f"--- {r['ticker']} {r['description']} (event {r['event_date']}) ---")
        for w in r["window"]:
            mark = "<<" if w["date"] == r["event_date"] else "  "
            print(
                f"  {w['date']}  ret={w['ret']:+7.2%}  CEP={w['cep_score']:+.2f} "
                f"{w['cep_pattern']:<22} ML={w['ml_score']:+.2f} {mark}"
            )
        print()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CEP vs ML real-event case study")
    p.add_argument("--output-dir", default="data/comparison_results")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for ticker, date_str, desc in EVENTS:
        log.info("running_event", ticker=ticker, date=date_str)
        res = run_event(ticker, date_str, desc)
        if res:
            results.append(res)

    if not results:
        log.error("no_events_processed")
        return

    print_report(results)
    out_path = output_dir / "event_case_study.json"
    out_path.write_text(json.dumps(results, indent=2))
    log.info("saved", path=str(out_path), events=len(results))


if __name__ == "__main__":
    main()
