"""
流式调用定义好的函数
Kafka runner for the source-independent lightweight factor engine"""

from __future__ import annotations

import json
import signal
from dataclasses import replace
from datetime import timedelta

from confluent_kafka import Consumer, Producer

from config.logging_config import get_logger
from config.settings import settings
from processing.data_quality import EventQualityGate
from processing.event_models import FactorSnapshot, MarketEvent
from processing.factor_engine import LightweightFactorEngine
from storage.db import get_session
from storage.models import (
    FactorSnapshotRecord,
    FeatureVector,
    MarketEventRecord,
    SentimentScore,
)

log = get_logger("factor_stream")
running = True


def shutdown(sig, frame) -> None:
    del frame
    global running
    log.info("shutting_down", signal=sig)
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def _message_mode(headers: list[tuple[str, bytes | None]] | None) -> str:
    for name, value in headers or []:
        if name == "marketstream-mode" and value:
            return value.decode()
    return "live"


def _persist(event: MarketEvent, snapshots: list[FactorSnapshot]) -> None:
    session = get_session()
    try:
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
        if event.event_type.value == "news" and "duplicate" not in event.quality_flags:
            score = float(event.payload.get("sentiment_score", 0.0))
            label = "positive" if score > 0 else "negative" if score < 0 else "neutral"
            session.add(
                SentimentScore(
                    time=event.event_time,
                    ticker=event.ticker,
                    headline=str(event.payload.get("headline", "")),
                    source=str(event.payload.get("source", event.feed)),
                    sentiment_score=score,
                    sentiment_label=label,
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
                    legacy_features=snapshot.legacy_features,
                )
            )
            if snapshot.cadence == "5m":
                legacy = snapshot.legacy_features
                session.merge(
                    FeatureVector(
                        window_start=snapshot.window_start,
                        window_end=snapshot.event_time,
                        ticker=snapshot.ticker,
                        avg_close=legacy.get("avg_close", 0.0),
                        price_change_rate=legacy.get("price_change_rate", 0.0),
                        total_volume=legacy.get("total_volume", 0),
                        avg_sentiment=0.0,
                        sentiment_shift=0.0,
                        headline_count=0,
                        anomaly_score=None,
                        is_anomaly=False,
                        detector_scores=None,
                    )
                )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": settings.factor_consumer_group,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([settings.raw_market_events_topic])
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    quality = EventQualityGate(
        stale_after=timedelta(seconds=settings.factor_stale_after_seconds),
        gap_after=timedelta(seconds=settings.factor_gap_after_seconds),
    )
    engine = LightweightFactorEngine(
        cadences=tuple(settings.factor_cadences_seconds),
        min_history_days=settings.factor_min_history_days,
        baseline_days=settings.factor_baseline_days,
        max_tickers=settings.factor_max_tickers,
    )
    log.info(
        "started", tickers=settings.tickers, cadences=settings.factor_cadences_seconds
    )
    while running:
        message = consumer.poll(1.0)
        if message is None:
            continue
        if message.error():
            log.error("consumer_error", error=str(message.error()))
            continue
        try:
            event = MarketEvent.from_dict(json.loads(message.value().decode()))
            transport_mode = _message_mode(message.headers())
            event = replace(event, mode=event.mode or transport_mode)
            event = quality.assess(event, mode=transport_mode)
            snapshots = engine.process(event)
            for snapshot in snapshots:
                snapshot.data_quality["mode"] = event.mode
            _persist(event, snapshots)
            for snapshot in snapshots:
                producer.produce(
                    settings.factor_snapshots_topic,
                    key=snapshot.ticker.encode(),
                    value=json.dumps(snapshot.to_dict()).encode(),
                )
                if snapshot.cadence == "5m":
                    producer.produce(
                        "stream.features",
                        key=snapshot.ticker.encode(),
                        value=json.dumps(snapshot.legacy_features).encode(),
                    )
            producer.poll(0)
        except Exception as exc:
            log.error("factor_processing_failed", error=str(exc))
    producer.flush()
    consumer.close()
    log.info("stopped", state=engine.state_size)


if __name__ == "__main__":
    main()
