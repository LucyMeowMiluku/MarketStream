"""Infrastructure-backed acceptance report for a designated normal soak period."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import text

from config.settings import settings
from storage.db import get_engine


def _parse_time(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None}
    return {
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
    }


def analyze_alerts(
    alerts: list[dict],
    *,
    hours: float,
    cooldown_seconds: int,
    latency_modes: frozenset[str] = frozenset({"live"}),
) -> dict:
    rates = {
        ticker: sum(row["ticker"] == ticker for row in alerts) / hours
        for ticker in settings.tickers
    }
    duplicates = 0
    last: dict[tuple[str, str, str], datetime] = {}
    latencies = []
    traceable = 0
    for row in sorted(alerts, key=lambda item: item["detected_at"]):
        key = (row["ticker"], row.get("pattern_name") or "", row.get("direction") or "")
        detected_at = _parse_time(row["detected_at"])
        persisted_at = _parse_time(row.get("persisted_at")) or detected_at
        previous = last.get(key)
        if previous and detected_at - previous < timedelta(seconds=cooldown_seconds):
            duplicates += 1
        else:
            last[key] = detected_at
        quality = row.get("data_quality") or {}
        if quality.get("mode") in latency_modes:
            received_at = _parse_time(quality.get("last_received_at"))
            if received_at is not None:
                latencies.append((persisted_at - received_at).total_seconds())
        if row.get("trigger_event_ids") and row.get("factor_found") and row.get("raw_events_found"):
            traceable += 1
    latency = _percentiles(latencies)
    duplicate_rate = duplicates / len(alerts) if alerts else 0.0
    traceability = traceable / len(alerts) if alerts else 1.0
    max_rate = max(rates.values(), default=0.0)
    return {
        "sample": {
            "hours": hours,
            "alerts": len(alerts),
            "latency_modes": sorted(latency_modes),
            "latency_samples": len(latencies),
            "live_latency_samples": len(latencies) if latency_modes == {"live"} else 0,
        },
        "alerts_per_ticker_hour": rates,
        "max_alerts_per_ticker_hour": max_rate,
        "duplicate_alert_rate": duplicate_rate,
        "receipt_to_persistence_seconds": latency,
        "traceability_rate": traceability,
        "gates": {
            "alert_budget_le_2": max_rate <= 2.0,
            "duplicate_rate_le_5pct": duplicate_rate <= 0.05,
            "live_p95_le_15s": latency["p95"] <= 15.0 if latency["p95"] is not None else None,
            "all_alerts_traceable": traceability == 1.0,
        },
    }


def load_alerts(hours: float) -> list[dict]:
    query = text(
        """
        SELECT a.detected_at, a.persisted_at, a.ticker, a.pattern_name, a.direction,
               a.trigger_event_ids, a.data_quality,
               EXISTS (
                   SELECT 1 FROM factor_snapshots fs
                   WHERE fs.ticker = a.ticker
                     AND fs.event_time = a.event_end
                     AND fs.cadence = a.features ->> 'cadence'
               ) AS factor_found
               ,NOT EXISTS (
                   SELECT 1
                   FROM jsonb_array_elements_text(
                       COALESCE(a.trigger_event_ids::jsonb, '[]'::jsonb)
                   ) AS ids(event_id)
                   WHERE NOT EXISTS (
                       SELECT 1 FROM market_events me WHERE me.event_id = ids.event_id
                   )
               ) AS raw_events_found
        FROM anomaly_alerts a
        WHERE a.detected_at >= NOW() - (:hours * INTERVAL '1 hour')
        ORDER BY a.detected_at
        """
    )
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(query, {"hours": hours}).mappings()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify MarketStream backend acceptance gates")
    parser.add_argument("--normal-period-hours", type=float, default=24.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/evaluation/backend_acceptance.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    alerts = load_alerts(args.normal_period_hours)
    report = analyze_alerts(
        alerts,
        hours=args.normal_period_hours,
        cooldown_seconds=settings.cep_cooldown_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
