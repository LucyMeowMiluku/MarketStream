"""
CEP 实时运行的程序， 负责把 CEP 接入 Kafka 和数据库。
运行流程： Kafka接受factor snapshot -> cepdetector.process() -> detection result
        -> 如果报警，则发到 Kafka topic:anomaly

Production CEP consumer: FactorSnapshot -> DetectionResult -> alert storage."""

from __future__ import annotations

import json
import signal
from datetime import datetime, timezone

from confluent_kafka import Consumer, Producer

from cep.cep_detector import CEPDetector, PATTERN_SEVERITY
from config.logging_config import get_logger
from config.settings import settings
from processing.event_models import DetectionResult, FactorSnapshot
from storage.db import get_session
from storage.models import AnomalyAlert

log = get_logger("cep_online_scorer")
running = True


def shutdown(sig, frame) -> None:
    del frame
    global running
    log.info("shutting_down", signal=sig)
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def _primary_pattern(result: DetectionResult):
    completed = [
        pattern for pattern in result.patterns if pattern.status == "completed"
    ]
    return max(
        completed, key=lambda item: PATTERN_SEVERITY.get(item.name, 0.0), default=None
    )


def _persist_alert(snapshot: FactorSnapshot, result: DetectionResult) -> bool:
    if not result.is_alert:
        return False
    primary = _primary_pattern(result)
    if primary is None:
        return False
    session = get_session()
    try:
        existing = (
            session.query(AnomalyAlert.id)
            .filter(AnomalyAlert.dedupe_key == result.dedupe_key)
            .first()
        )
        if existing:
            return False
        session.add(
            AnomalyAlert(
                detected_at=result.detected_at,
                ticker=result.ticker,
                anomaly_score=result.score,
                features={
                    **snapshot.legacy_features,
                    "factor_values": snapshot.factor_values,
                    "cadence": snapshot.cadence,
                },
                reason=result.explanation,
                detector_scores={"cep": result.score},
                pattern_name=primary.name,
                direction=primary.direction,
                severity=result.severity,
                event_start=primary.started_at,
                event_end=primary.completed_at,
                first_detected_at=result.detected_at,
                factor_evidence=result.factor_evidence,
                trigger_event_ids=result.source_event_ids,
                data_quality=result.data_quality,
                dedupe_key=result.dedupe_key,
            )
        )
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    detector = CEPDetector(max_factor_frames=settings.cep_max_factor_frames)
    # Consumer 订阅 factor snapshots topic
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": settings.cep_consumer_group,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([settings.factor_snapshots_topic])
    # Kafka producer
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    log.info("started", input_topic=settings.factor_snapshots_topic)
    while running:
        message = consumer.poll(1.0)
        if message is None:
            continue
        if message.error():
            log.error("consumer_error", error=str(message.error()))
            continue
        try:
            snapshot = FactorSnapshot.from_dict(
                json.loads(message.value().decode())
            )  # Kafka中存储的json，需要还原成snapshot原结构
            result = detector.process(
                snapshot, detected_at=datetime.now(timezone.utc)
            )  # 调用cep detector
            if _persist_alert(snapshot, result):
                payload = result.to_dict()
                payload["features"] = {
                    **snapshot.legacy_features,
                    "factor_values": snapshot.factor_values,
                }
                payload["reason"] = result.explanation
                producer.produce(
                    settings.anomalies_topic,
                    key=result.ticker.encode(),
                    value=json.dumps(payload).encode(),
                )
                producer.poll(0)
                received_at = snapshot.data_quality.get("last_received_at")
                latency_seconds = None
                if received_at:
                    received = datetime.fromisoformat(
                        received_at.replace("Z", "+00:00")
                    )
                    latency_seconds = (result.detected_at - received).total_seconds()
                log.warning(
                    "anomaly_detected",
                    ticker=result.ticker,
                    pattern=_primary_pattern(result).name,
                    severity=result.severity,
                    end_to_end_seconds=latency_seconds,
                )
        except Exception as exc:
            log.error("cep_processing_failed", error=str(exc))
    producer.flush()
    consumer.close()
    log.info("stopped")


if __name__ == "__main__":
    main()
