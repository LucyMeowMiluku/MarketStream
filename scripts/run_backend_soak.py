"""Run an isolated MarketEvent -> Kafka -> factor -> CEP -> PostgreSQL soak.

The generated events are explicitly marked ``soak``. They exercise the same
consumers and persistence path as production without being reported as live
Alpaca observations.

Usage:
    uv run python -m scripts.run_backend_soak
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import text

from config.settings import settings
from processing.event_models import EventType, MarketEvent
from storage.db import get_engine
from storage.init_db import init_database


SOAK_TICKERS = (
    "AAPL",
    "TSLA",
    "NVDA",
    "QQQ",
    "SPY",
    "MSFT",
    "AMZN",
    "GOOGL",
    "META",
    "AMD",
    "NFLX",
    "AVGO",
)


def _trading_days(count: int) -> list[date]:
    cursor = date.today() - timedelta(days=count * 2 + 10)
    result: list[date] = []
    while len(result) < count:
        if cursor.weekday() < 5:
            result.append(cursor)
        cursor += timedelta(days=1)
    return result


def _event_time(day: date, minute_offset: int) -> datetime:
    # 15:00 UTC is regular US trading time in both standard and daylight time.
    return datetime.combine(
        day,
        datetime_time(hour=15, minute=minute_offset, tzinfo=timezone.utc),
    )


def _create_topics(topics: list[str]) -> None:
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    futures = admin.create_topics([NewTopic(topic, 3, 1) for topic in topics])
    for topic, future in futures.items():
        try:
            future.result(20)
        except Exception as exc:
            if "TOPIC_ALREADY_EXISTS" not in str(exc):
                raise RuntimeError(f"could not create soak topic {topic}") from exc


def _delete_topics(topics: list[str]) -> None:
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    futures = admin.delete_topics(topics, operation_timeout=20)
    for future in futures.values():
        try:
            future.result(20)
        except Exception:
            pass


def _generate_events(
    run_id: str,
    *,
    baseline_days: int,
    anomaly_days: int,
    minute_offset: int,
) -> list[MarketEvent]:
    days = _trading_days(baseline_days + anomaly_days)
    prices = {ticker: 100.0 + index * 10 for index, ticker in enumerate(SOAK_TICKERS)}
    result: list[MarketEvent] = []
    for day_index, day in enumerate(days):
        for ticker in SOAK_TICKERS:
            if day_index >= baseline_days:
                anomaly_index = day_index - baseline_days
                market_return = 0.01 * (2 ** (anomaly_index + 1) - 1)
                prices[ticker] *= 1 + market_return
            start = _event_time(day, minute_offset)
            for event_index, event_time in enumerate((start, start + timedelta(seconds=10))):
                result.append(
                    MarketEvent.create(
                        source="marketstream_soak",
                        feed="synthetic_transport_probe",
                        event_type=EventType.TRADE,
                        ticker=ticker,
                        event_time=event_time,
                        received_at=datetime.now(timezone.utc),
                        event_id=f"{run_id}:{ticker}:{day_index}:{event_index}",
                        trade={"price": prices[ticker], "size": 100, "side": "buy"},
                    )
                )
    return sorted(result, key=lambda event: (event.event_time, event.ticker, event.event_id))


def _publish(events: list[MarketEvent], topic: str) -> None:
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    for event in events:
        event.received_at = datetime.now(timezone.utc)
        producer.produce(
            topic,
            key=event.ticker.encode(),
            value=json.dumps(event.to_dict()).encode(),
            headers=[("marketstream-mode", b"soak")],
        )
        producer.poll(0)
    remaining = producer.flush(30)
    if remaining:
        raise RuntimeError(f"{remaining} soak events were not delivered to Kafka")


def _counts(run_id: str) -> tuple[int, int]:
    with get_engine().connect() as connection:
        raw_count = connection.execute(
            text("SELECT COUNT(*) FROM market_events WHERE event_id LIKE :prefix"),
            {"prefix": f"{run_id}:%"},
        ).scalar_one()
        alert_count = connection.execute(
            text(
                """
                SELECT COUNT(*) FROM anomaly_alerts
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(trigger_event_ids::jsonb) AS ids(event_id)
                    WHERE ids.event_id LIKE :prefix
                )
                """
            ),
            {"prefix": f"{run_id}:%"},
        ).scalar_one()
    return int(raw_count), int(alert_count)


def _load_alerts(run_id: str) -> list[dict[str, Any]]:
    query = text(
        """
        SELECT a.detected_at, a.persisted_at, a.ticker, a.pattern_name, a.direction,
               a.dedupe_key, a.trigger_event_ids, a.data_quality,
               EXISTS (
                   SELECT 1 FROM factor_snapshots fs
                   WHERE fs.ticker = a.ticker
                     AND fs.event_time = a.event_end
                     AND fs.cadence = a.features ->> 'cadence'
               ) AS factor_found,
               NOT EXISTS (
                   SELECT 1
                   FROM jsonb_array_elements_text(a.trigger_event_ids::jsonb) AS ids(event_id)
                   WHERE NOT EXISTS (
                       SELECT 1 FROM market_events me WHERE me.event_id = ids.event_id
                   )
               ) AS raw_events_found
        FROM anomaly_alerts a
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(a.trigger_event_ids::jsonb) AS ids(event_id)
            WHERE ids.event_id LIKE :prefix
        )
        ORDER BY a.persisted_at
        """
    )
    with get_engine().connect() as connection:
        return [
            dict(row)
            for row in connection.execute(query, {"prefix": f"{run_id}:%"}).mappings()
        ]


def _report(
    alerts: list[dict[str, Any]],
    *,
    run_id: str,
    event_count: int,
    raw_count: int,
    expected_alerts: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    for alert in alerts:
        quality = alert.get("data_quality") or {}
        received = datetime.fromisoformat(quality["last_received_at"].replace("Z", "+00:00"))
        persisted = alert["persisted_at"]
        latencies.append((persisted - received).total_seconds())
    percentiles = {
        name: float(np.percentile(latencies, percentile)) if latencies else None
        for name, percentile in (("p50", 50), ("p95", 95), ("p99", 99))
    }
    dedupe_keys = [row["dedupe_key"] for row in alerts]
    traceable = all(row["factor_found"] and row["raw_events_found"] for row in alerts)
    gates = {
        "all_events_persisted": raw_count == event_count,
        "expected_alert_sample": len(alerts) >= expected_alerts,
        "p95_le_15_seconds": percentiles["p95"] is not None and percentiles["p95"] <= 15,
        "no_duplicate_alerts": len(dedupe_keys) == len(set(dedupe_keys)),
        "all_alerts_traceable": bool(alerts) and traceable,
    }
    gates["kafka_to_database_soak"] = all(gates.values())
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": "synthetic events explicitly marked mode=soak; not live Alpaca data",
        "path": "MarketEvent -> Kafka -> factor engine -> Kafka -> CEP -> PostgreSQL",
        "sample": {
            "input_events": event_count,
            "persisted_events": raw_count,
            "persisted_alerts": len(alerts),
        },
        "receipt_to_alert_persistence_seconds": percentiles,
        "gates": gates,
    }


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-days", type=int, default=5)
    parser.add_argument("--anomaly-days", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument(
        "--output", type=Path, default=Path("data/evaluation/kafka_db_soak.json")
    )
    parser.add_argument("--keep-topics", action="store_true")
    args = parser.parse_args()

    init_database()
    run_id = "soak-" + uuid.uuid4().hex[:10]
    suffix = run_id.replace("-", ".")
    raw_topic = f"soak.raw.{suffix}"
    factor_topic = f"soak.factor.{suffix}"
    anomaly_topic = f"soak.alert.{suffix}"
    topics = [raw_topic, factor_topic, anomaly_topic]
    _create_topics(topics)

    output_dir = args.output.parent / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    minute_offset = int(run_id[-2:], 16) % 30
    expected_alerts = len(SOAK_TICKERS) * args.anomaly_days
    events = _generate_events(
        run_id,
        baseline_days=args.baseline_days,
        anomaly_days=args.anomaly_days,
        minute_offset=minute_offset,
    )
    child_env = {
        **os.environ,
        "RAW_MARKET_EVENTS_TOPIC": raw_topic,
        "FACTOR_SNAPSHOTS_TOPIC": factor_topic,
        "ANOMALIES_TOPIC": anomaly_topic,
        "FACTOR_CONSUMER_GROUP": f"factor-{run_id}",
        "CEP_CONSUMER_GROUP": f"cep-{run_id}",
        "FACTOR_MIN_HISTORY_DAYS": str(args.baseline_days),
        "FACTOR_BASELINE_DAYS": "20",
        "FACTOR_CADENCES_SECONDS": "[10]",
    }
    processes: list[subprocess.Popen] = []
    try:
        with (output_dir / "factor.log").open("w") as factor_log, (
            output_dir / "cep.log"
        ).open("w") as cep_log:
            processes = [
                subprocess.Popen(
                    [sys.executable, "-m", "processing.factor_stream"],
                    env=child_env,
                    stdout=factor_log,
                    stderr=subprocess.STDOUT,
                ),
                subprocess.Popen(
                    [sys.executable, "-m", "cep.online_scorer"],
                    env=child_env,
                    stdout=cep_log,
                    stderr=subprocess.STDOUT,
                ),
            ]
            time.sleep(3)
            if any(process.poll() is not None for process in processes):
                raise RuntimeError(f"a soak consumer exited early; inspect {output_dir}")
            _publish(events, raw_topic)

            deadline = time.monotonic() + args.timeout_seconds
            raw_count = alert_count = 0
            while time.monotonic() < deadline:
                raw_count, alert_count = _counts(run_id)
                if raw_count == len(events) and alert_count >= expected_alerts:
                    break
                time.sleep(0.25)
            alerts = _load_alerts(run_id)
    finally:
        for process in processes:
            _stop(process)
        if not args.keep_topics:
            _delete_topics(topics)

    report = _report(
        alerts,
        run_id=run_id,
        event_count=len(events),
        raw_count=raw_count,
        expected_alerts=expected_alerts,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2)
    args.output.write_text(serialized, encoding="utf-8")
    (output_dir / "report.json").write_text(serialized, encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Consumer logs: {output_dir}")
    return 0 if report["gates"]["kafka_to_database_soak"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
