"""Ephemeral Kafka factor runner for demonstrations and ordinary replay.

It is intentionally separate from the live durable-baseline runner: replay
traffic may write trace records and snapshots, but never reads or mutates a
live baseline epoch.
"""

from __future__ import annotations

import json
import signal
from dataclasses import replace

from confluent_kafka import Consumer, Producer

from config.logging_config import get_logger
from config.settings import settings
from processing.data_quality import EventQualityGate
from processing.event_models import MarketEvent
from processing.factor_engine import LightweightFactorEngine
from storage.db import get_session
from storage.models import FactorSnapshotRecord, MarketEventRecord

log = get_logger("replay_factor_stream")
running = True


def shutdown(sig, frame) -> None:
    del frame
    global running
    running = False
    log.info("shutting_down", signal=sig)


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def _persist(event, snapshots) -> None:
    with get_session() as session, session.begin():
        session.merge(
            MarketEventRecord(
                event_id=event.event_id,
                source=event.source,
                feed=event.feed,
                event_type=event.event_type.value,
                ticker=event.ticker,
                event_time=event.event_time,
                received_at=event.received_at,
                payload=event.payload,
                quality_flags=list(event.quality_flags),
            )
        )
        for snapshot in snapshots:
            session.merge(
                FactorSnapshotRecord(
                    event_time=snapshot.event_time,
                    window_start=snapshot.window_start,
                    ticker=snapshot.ticker,
                    cadence=snapshot.cadence,
                    factor_values=snapshot.factor_values,
                    factor_states=snapshot.factor_states,
                    baseline_version=snapshot.baseline_version,
                    data_quality=snapshot.data_quality,
                    warmup_status=snapshot.warmup_status,
                    source_event_ids=snapshot.source_event_ids,
                    input_summary=snapshot.input_summary,
                )
            )


def main() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": f"{settings.factor_consumer_group}-replay",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([settings.raw_market_events_topic])
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    engine = LightweightFactorEngine(
        cadences=tuple(settings.factor_cadences_seconds),
        min_history_days=settings.factor_min_history_days,
        baseline_days=settings.factor_baseline_days,
        max_tickers=settings.factor_max_tickers,
    )
    quality = EventQualityGate()
    while running:
        message = consumer.poll(1.0)
        if message is None:
            continue
        if message.error():
            log.error("consumer_error", error=str(message.error()))
            continue
        if ("marketstream-mode", b"live") in (message.headers() or []):
            # Live and replay share the raw topic; live events belong to the
            # durable runner and must not enter this ephemeral engine.
            continue
        try:
            event = MarketEvent.from_dict(json.loads(message.value().decode()))
            event = replace(event, mode=event.mode or "replay")
            event = quality.assess(event, mode="replay", now=event.event_time)
            snapshots = engine.process(event)
            _persist(event, snapshots)
            for snapshot in snapshots:
                producer.produce(
                    settings.factor_snapshots_topic,
                    key=snapshot.ticker.encode(),
                    value=json.dumps(snapshot.to_dict()).encode(),
                )
            producer.poll(0)
        except Exception as exc:
            log.error("replay_factor_processing_failed", error=str(exc))
    producer.flush()
    consumer.close()


if __name__ == "__main__":
    main()
